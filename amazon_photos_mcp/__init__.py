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
    import tempfile

    ap = _get_client()
    # The upstream lib writes JSON files to CWD during aggregations.
    # Use a temp dir to avoid polluting the user's working directory.
    original_dir = os.getcwd()
    tmp_dir = tempfile.mkdtemp(prefix="ap_agg_")
    os.chdir(tmp_dir)
    try:
        result = ap.aggregations(category)
        if hasattr(result, "json"):
            return result.json()
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return {"aggregations": str(result)}
    finally:
        os.chdir(original_dir)
        # Clean up temp files
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
