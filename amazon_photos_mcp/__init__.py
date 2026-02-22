"""FastMCP Amazon Photos Server — search, browse, and manage your Amazon Photos library."""

import json
import os
import traceback
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("amazon-photos")

# Lazy-initialized client
_client = None


def _get_client():
    """Get or create the Amazon Photos client, loading cookies from config."""
    global _client
    if _client is not None:
        return _client

    from amazon_photos import AmazonPhotos

    cookies = _load_cookies()
    if not cookies:
        raise RuntimeError(
            "No Amazon cookies configured. Set AMAZON_PHOTOS_COOKIES as JSON string, "
            "or create ~/.config/amazon-photos-mcp/cookies.json with keys: "
            "ubid_main, at_main, session-id"
        )

    db_path = os.environ.get(
        "AMAZON_PHOTOS_DB",
        str(Path.home() / ".config" / "amazon-photos-mcp" / "ap.parquet"),
    )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _client = AmazonPhotos(cookies=cookies, db_path=db_path)
    return _client


def _normalize_cookies(raw: dict) -> dict:
    """Normalize cookie keys for the amazon-photos library.

    The library's determine_tld() checks for keys ending with '_main' (underscores)
    to detect .com domains, but Amazon's HTTP API expects hyphenated cookie names
    (ubid-main, at-main). We include both formats so TLD detection and auth both work.
    """
    normalized = dict(raw)
    # Map between hyphen and underscore variants
    pairs = [("ubid-main", "ubid_main"), ("at-main", "at_main")]
    for hyphen, underscore in pairs:
        if hyphen in normalized and underscore not in normalized:
            normalized[underscore] = normalized[hyphen]
        elif underscore in normalized and hyphen not in normalized:
            normalized[hyphen] = normalized[underscore]
    return normalized


def _load_cookies() -> dict | None:
    """Load cookies from environment variable or config file."""
    raw = None

    # Try env var first
    env_cookies = os.environ.get("AMAZON_PHOTOS_COOKIES")
    if env_cookies:
        raw = json.loads(env_cookies)

    # Try config file
    if raw is None:
        config_path = Path.home() / ".config" / "amazon-photos-mcp" / "cookies.json"
        if config_path.exists():
            raw = json.loads(config_path.read_text())

    if raw is None:
        return None

    return _normalize_cookies(raw)


def _safe_df_to_list(df, max_results: int = 50) -> list[dict]:
    """Convert a pandas DataFrame (or list) to a list of dicts, handling edge cases."""
    if df is None:
        return []
    # Handle plain list (e.g. from get_folders())
    if isinstance(df, list):
        return df[:max_results]
    if hasattr(df, "empty") and df.empty:
        return []
    # Deduplicate by 'id' column if present (upstream parquet DB has dupes)
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    records = df.head(max_results).to_dict(orient="records")
    # Clean up NaN/NaT values for JSON serialization
    clean = []
    for row in records:
        clean.append(
            {k: (None if _is_nan(v) else v) for k, v in row.items()}
        )
    return clean


def _is_nan(v) -> bool:
    """Check if a value is NaN or NaT."""
    try:
        import pandas as pd
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return False


# --- Tools ---


@mcp.tool()
def check_connection() -> dict:
    """Test the connection to Amazon Photos and return account storage usage.

    Use this first to verify cookies are valid and the API is accessible.

    Returns:
        Storage usage statistics including total space, used space, photo/video counts.
    """
    try:
        ap = _get_client()
        usage = ap.usage()
        if hasattr(usage, "json"):
            return usage.json()
        return {"status": "connected", "usage": str(usage)}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@mcp.tool()
def search_photos(
    query: str,
    max_results: int = 25,
) -> list[dict]:
    """Search your Amazon Photos library with a query string.

    Supports filters like:
      - type:(PHOTOS) or type:(VIDEOS)
      - things:(beach AND sunset)
      - timeYear:(2024) timeMonth:(6)
      - location:(USA#OH#Columbus)
      - extension:(jpg)
      - name:(vacation*)

    Args:
        query: Search query with optional filters (max 8 filter params).
        max_results: Maximum number of results to return (default 25, max 200).

    Returns:
        List of matching media items with metadata.
    """
    ap = _get_client()
    max_results = min(max_results, 200)
    df = ap.query(query)
    return _safe_df_to_list(df, max_results)


@mcp.tool()
def get_photos(max_results: int = 25) -> list[dict]:
    """Get recent photos from your Amazon Photos library.

    Args:
        max_results: Maximum number of results (default 25, max 200).

    Returns:
        List of photo items with metadata.
    """
    ap = _get_client()
    df = ap.photos()
    return _safe_df_to_list(df, min(max_results, 200))


@mcp.tool()
def get_videos(max_results: int = 25) -> list[dict]:
    """Get recent videos from your Amazon Photos library.

    Args:
        max_results: Maximum number of results (default 25, max 200).

    Returns:
        List of video items with metadata.
    """
    ap = _get_client()
    df = ap.videos()
    return _safe_df_to_list(df, min(max_results, 200))


@mcp.tool()
def get_storage_usage() -> dict:
    """Get current Amazon Photos storage usage statistics.

    Returns:
        Storage plan details, space used, photo/video counts.
    """
    ap = _get_client()
    usage = ap.usage()
    if hasattr(usage, "json"):
        return usage.json()
    return {"usage": str(usage)}


@mcp.tool()
def get_aggregations(category: str = "all") -> dict:
    """Get Amazon's auto-generated aggregations (people, things, locations, dates, etc.).

    Args:
        category: Aggregation category — "all", "people", "things", "dates",
                  "locations", "types", or "clusters".

    Returns:
        Aggregation data with counts and identifiers.
    """
    ap = _get_client()
    # Pass out='' to skip disk writes — upstream has a bug where it creates
    # a directory named e.g. "things.json" then tries to write bytes to it.
    result = ap.aggregations(category, out='')
    if isinstance(result, dict):
        return result
    if hasattr(result, "json"):
        return result.json()
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return {"aggregations": str(result)}


@mcp.tool()
def list_folders() -> list[dict]:
    """List all folders in your Amazon Photos library.

    Returns:
        List of folders with names and node IDs.
    """
    ap = _get_client()
    df = ap.get_folders()
    return _safe_df_to_list(df, max_results=200)


@mcp.tool()
def get_folder_tree() -> str:
    """Display the folder tree structure of your Amazon Photos library.

    Returns:
        Text representation of the folder hierarchy.
    """
    import io
    import sys

    ap = _get_client()
    # Capture print_tree output
    old_stdout = sys.stdout
    sys.stdout = buf = io.StringIO()
    try:
        ap.print_tree()
    finally:
        sys.stdout = old_stdout
    return buf.getvalue() or "No folder tree available."


@mcp.tool()
def search_by_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
    media_type: str = "PHOTOS",
    max_results: int = 25,
) -> list[dict]:
    """Search photos/videos by date.

    Args:
        year: Year to search (e.g. 2024).
        month: Optional month (1-12).
        day: Optional day (1-31).
        media_type: "PHOTOS" or "VIDEOS" (default "PHOTOS").
        max_results: Maximum results to return (default 25).

    Returns:
        List of matching media items.
    """
    ap = _get_client()
    parts = [f"type:({media_type})", f"timeYear:({year})"]
    if month:
        parts.append(f"timeMonth:({month})")
    if day:
        parts.append(f"timeDay:({day})")
    query = " ".join(parts)
    df = ap.query(query)
    return _safe_df_to_list(df, min(max_results, 200))


@mcp.tool()
def search_by_things(
    things: str,
    media_type: str = "PHOTOS",
    max_results: int = 25,
) -> list[dict]:
    """Search photos by what's in them (Amazon's auto-detected labels).

    Args:
        things: What to search for, e.g. "beach", "dog AND park", "sunset OR sunrise".
        media_type: "PHOTOS" or "VIDEOS" (default "PHOTOS").
        max_results: Maximum results (default 25).

    Returns:
        List of matching media items.
    """
    ap = _get_client()
    query = f"type:({media_type}) things:({things})"
    df = ap.query(query)
    return _safe_df_to_list(df, min(max_results, 200))


@mcp.tool()
def trash_items(node_ids: list[str]) -> dict:
    """Move items to the trash in Amazon Photos.

    Args:
        node_ids: List of node IDs to trash.

    Returns:
        Result of the trash operation.
    """
    ap = _get_client()
    result = ap.trash(node_ids)
    if hasattr(result, "json"):
        return result.json()
    return {"status": "trashed", "count": len(node_ids)}


@mcp.tool()
def list_trashed() -> list[dict]:
    """List items currently in the Amazon Photos trash.

    Returns:
        List of trashed items with metadata and node IDs.
    """
    ap = _get_client()
    df = ap.trashed()
    return _safe_df_to_list(df, max_results=100)


@mcp.tool()
def restore_items(node_ids: list[str]) -> dict:
    """Restore items from the trash back to the library.

    Args:
        node_ids: List of node IDs to restore.

    Returns:
        Result of the restore operation.
    """
    ap = _get_client()
    result = ap.restore(node_ids)
    if hasattr(result, "json"):
        return result.json()
    return {"status": "restored", "count": len(node_ids)}


@mcp.tool()
def upload_file(file_path: str) -> dict:
    """Upload a file to Amazon Photos.

    Deduplicates via MD5 hash — re-uploading the same file is a no-op.

    Args:
        file_path: Absolute path to the file to upload.

    Returns:
        Upload result with node ID of the uploaded file.
    """
    import shutil
    import tempfile

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    if not path.is_file():
        return {"error": f"Not a file: {file_path}"}

    ap = _get_client()
    # Upstream upload() expects a directory and uses rglob('*').
    # Wrap single file in a temp directory for upload.
    tmp_dir = tempfile.mkdtemp(prefix="ap_upload_")
    try:
        shutil.copy2(str(path), os.path.join(tmp_dir, path.name))
        result = ap.upload(tmp_dir)
        if isinstance(result, list) and result:
            return {"status": "uploaded", "file": path.name, "results": result}
        return {"status": "uploaded", "file": path.name, "results": result}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@mcp.tool()
def list_people() -> list[dict]:
    """List all face clusters (people) recognized in your Amazon Photos library.

    Returns each person's name, cluster ID, and photo count. Unnamed clusters
    are labeled "(unnamed)".

    Returns:
        List of people with name, cluster_id, and count.
    """
    ap = _get_client()
    people = ap.aggregations("allPeople", out="")
    results = []
    for entry in people:
        name = entry.get("searchData", {}).get("clusterName") or "(unnamed)"
        results.append({
            "name": name,
            "cluster_id": entry["value"],
            "count": entry["count"],
            "node_id": entry.get("searchData", {}).get("nodeId"),
        })
    results.sort(key=lambda x: x["count"], reverse=True)
    return results


@mcp.tool()
def search_by_person(person: str, max_results: int = 50) -> list[dict]:
    """Search photos containing a specific person by name or cluster ID.

    Args:
        person: Person's name (e.g. "Lara") or cluster ID. Name matching is case-insensitive.
        max_results: Maximum results to return (default 50, max 200).

    Returns:
        List of photo items containing the specified person.
    """
    ap = _get_client()
    max_results = min(max_results, 200)

    # Resolve name to cluster ID
    cluster_id = None
    people = ap.aggregations("allPeople", out="")
    for entry in people:
        cname = entry.get("searchData", {}).get("clusterName", "")
        if cname and cname.lower() == person.lower():
            cluster_id = entry["value"]
            break
    # If no name match, treat input as a cluster ID directly
    if cluster_id is None:
        cluster_id = person

    df = ap.query(f"type:(PHOTOS) clusterId:({cluster_id})")
    return _safe_df_to_list(df, max_results)


@mcp.tool()
def find_duplicates(max_groups: int = 50) -> dict:
    """Find exact duplicate files in your library by MD5 hash.

    Uses the local parquet database to identify files sharing the same MD5.
    Does NOT modify anything — read-only analysis.

    Args:
        max_groups: Maximum duplicate groups to return (default 50).

    Returns:
        Summary with total_duplicate_files, removable_copies, and duplicate groups
        showing each file's id, name, folder, and creation date.
    """
    import pandas as pd

    ap = _get_client()
    db = ap.db

    if "md5" not in db.columns:
        return {"error": "md5 column not found in database. Try refreshing the DB first."}

    # Find MD5s with more than one file
    md5_counts = db.groupby("md5").size()
    dupe_md5s = md5_counts[md5_counts > 1]

    if dupe_md5s.empty:
        return {"total_duplicate_files": 0, "removable_copies": 0, "groups": []}

    total_files = int(dupe_md5s.sum())
    removable = int(total_files - len(dupe_md5s))

    # Build group details
    dupe_rows = db[db["md5"].isin(dupe_md5s.index)].copy()
    groups = []
    for md5_hash, group_df in dupe_rows.groupby("md5"):
        if len(groups) >= max_groups:
            break
        files = []
        for _, row in group_df.iterrows():
            files.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "folder": row.get("parentMap.FOLDER") if not _is_nan(row.get("parentMap.FOLDER")) else None,
                "createdDate": str(row.get("createdDate")) if not _is_nan(row.get("createdDate")) else None,
                "size": int(row["size"]) if not _is_nan(row.get("size")) else None,
            })
        files.sort(key=lambda f: f["createdDate"] or "")
        groups.append({
            "md5": str(md5_hash),
            "count": len(files),
            "files": files,
        })

    groups.sort(key=lambda g: g["count"], reverse=True)

    return {
        "total_duplicate_files": total_files,
        "removable_copies": removable,
        "total_groups": len(dupe_md5s),
        "groups_shown": len(groups),
        "groups": groups,
    }


@mcp.tool()
def trash_duplicates(
    md5_hashes: list[str] | None = None,
    dry_run: bool = True,
) -> dict:
    """Trash duplicate copies, keeping the oldest (original) of each MD5 group.

    For each group of files sharing the same MD5, keeps the file with the earliest
    createdDate and trashes the rest. Items go to Amazon Photos trash (recoverable
    for 30 days).

    Args:
        md5_hashes: Optional list of specific MD5 hashes to process. If None, processes ALL duplicates.
        dry_run: If True (default), only preview what would be trashed. Set False to actually trash.

    Returns:
        Summary of action taken, groups processed, files kept, and files trashed.
    """
    import pandas as pd

    ap = _get_client()
    db = ap.db

    if "md5" not in db.columns:
        return {"error": "md5 column not found in database."}

    # Find duplicate MD5s
    md5_counts = db.groupby("md5").size()
    dupe_md5s = set(md5_counts[md5_counts > 1].index)

    if md5_hashes is not None:
        # Filter to only requested hashes that are actually dupes
        dupe_md5s = dupe_md5s & set(md5_hashes)

    if not dupe_md5s:
        return {"action": "dry_run" if dry_run else "trashed", "groups_processed": 0,
                "files_trashed": 0, "files_kept": 0, "message": "No duplicates found to process."}

    dupe_rows = db[db["md5"].isin(dupe_md5s)].copy()

    trash_ids = []
    keep_ids = []
    for md5_hash, group_df in dupe_rows.groupby("md5"):
        # Sort by createdDate ascending — keep the oldest
        sorted_group = group_df.sort_values("createdDate", ascending=True, na_position="last")
        keep_id = sorted_group.iloc[0]["id"]
        keep_ids.append(keep_id)
        for _, row in sorted_group.iloc[1:].iterrows():
            trash_ids.append(row["id"])

    result = {
        "action": "dry_run" if dry_run else "trashed",
        "groups_processed": len(dupe_md5s),
        "files_kept": len(keep_ids),
        "files_trashed": len(trash_ids),
    }

    if dry_run:
        result["message"] = f"Would trash {len(trash_ids)} duplicate copies across {len(dupe_md5s)} groups. Set dry_run=False to execute."
        # Show a sample of what would be trashed
        sample_size = min(10, len(trash_ids))
        sample_rows = db[db["id"].isin(trash_ids[:sample_size])]
        result["sample_trashed"] = [
            {"id": row["id"], "name": row.get("name"), "md5": row.get("md5")}
            for _, row in sample_rows.iterrows()
        ]
    else:
        # Actually trash in batches of 100
        batch_size = 100
        for i in range(0, len(trash_ids), batch_size):
            batch = trash_ids[i:i + batch_size]
            ap.trash(batch)
        result["message"] = f"Trashed {len(trash_ids)} duplicate copies. Items are recoverable from trash for 30 days."

    return result


@mcp.tool()
def download_files(node_ids: list[str], output_dir: str = "") -> dict:
    """Download files from Amazon Photos by node ID.

    Args:
        node_ids: List of node IDs to download.
        output_dir: Output directory (defaults to ~/Downloads/amazon-photos/).

    Returns:
        Download result with file paths and output directory.
    """
    import tempfile

    ap = _get_client()
    if not output_dir:
        output_dir = str(Path.home() / "Downloads" / "amazon-photos")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    original_dir = os.getcwd()
    os.chdir(output_dir)
    try:
        result = ap.download(node_ids)
        if hasattr(result, "json"):
            return result.json()
        return {"status": "downloaded", "count": len(node_ids), "output_dir": output_dir}
    finally:
        os.chdir(original_dir)


# --- Entrypoint ---


def main():
    """Main entrypoint for the MCP server."""
    try:
        _get_client()
        print("[amazon-photos] Connected to Amazon Photos.")
    except Exception as e:
        print(f"[amazon-photos] Warning: Could not connect at startup: {e}")
        print("[amazon-photos] Server starting anyway — configure cookies to connect.")
    mcp.run()


if __name__ == "__main__":
    main()
