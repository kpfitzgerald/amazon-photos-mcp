# Amazon Photos MCP — Project Status

## Overview

FastMCP server wrapping the unofficial [amazon-photos](https://github.com/trevorhobenshield/amazon_photos) Python library (MIT license, by trevorhobenshield). Provides 15 tools for Claude Code to search, browse, upload, download, and manage an Amazon Photos library.

- **Repo:** https://github.com/kpfitzgerald/amazon-photos-mcp
- **Local:** `~/amazon-photos-mcp/` (symlink → `/mnt/c/Users/kungf/OneDrive/Documents/git/amazon-photos-mcp/`)
- **Registered:** `claude mcp add --scope user amazon-photos -- uvx --from ~/amazon-photos-mcp amazon-photos-mcp`
- **Auth:** Cookie-based (`~/.config/amazon-photos-mcp/cookies.json`, chmod 600)
- **Database:** `~/.config/amazon-photos-mcp/ap.parquet` (local cache of photo metadata)

## What Was Built (2026-02-21)

### 1. MCP Server (`amazon_photos_mcp/__init__.py`)
- 15 tools covering the full amazon-photos library surface:
  - `check_connection` — test API access, return storage usage
  - `search_photos` — full query language (things, dates, locations, types)
  - `get_photos` / `get_videos` — recent media
  - `get_storage_usage` — plan details, space used, counts
  - `get_aggregations` — auto-detected labels (people, things, places, dates)
  - `list_folders` / `get_folder_tree` — folder navigation
  - `search_by_date` / `search_by_things` — convenience search wrappers
  - `trash_items` / `list_trashed` / `restore_items` — trash management
  - `upload_file` / `download_files` — file transfer
- Lazy client initialization (doesn't crash if cookies aren't configured)
- Cookie normalization layer (`_normalize_cookies`) that handles both hyphenated and underscored cookie key formats
- DataFrame-to-JSON conversion with NaN/NaT cleanup (`_safe_df_to_list`)

### 2. Cookie Setup
- `setup-cookies.sh` — interactive helper prompting for 3 cookie values
- Playwright-based extraction tested and working (open amazon.com/photos, sign in, extract via `context.cookies()`)

### 3. Package Configuration
- `pyproject.toml` — hatchling build, requires Python >=3.10.10
- Dependencies: `fastmcp>=2.0.0`, `amazon-photos>=0.0.97`, `httpx`, `pyarrow`
- Entry point: `amazon-photos-mcp = "amazon_photos_mcp:main"`

## API Test Results

Tested 2026-02-21 against Kelly's Amazon account:
- **Status:** API is live and accessible
- **Root node:** `MR9Rb9kiTYC4HdqXWRSJsg` (created 2011-04-06)
- **Owner:** `A2NI566MRQ4Y8X`
- **287 folders**
- **27,599 photos** (59.5 GB — free unlimited with Prime)
- **1,339 videos** (83.4 GB billable)
- **5 documents**, 1 other file
- Initial DB sync: ~24 seconds for 145 search pages

## Bugs Found in Upstream Library (`amazon-photos v0.0.97`)

### Bug 1: Cookie Key Format Mismatch (TLD Detection)
- **Location:** `_api.py` → `determine_tld()`
- **Issue:** Method checks `k.endswith('_main')` (underscores) to detect `.com` domain, but browser cookies use hyphens (`ubid-main`, `at-main`). When hyphens are used, TLD defaults to `None` → connects to `www.amazon.none` → DNS failure → 12 retries with exponential backoff → silent `None` return → `AttributeError`.
- **Our workaround:** `_normalize_cookies()` in MCP server adds both formats.
- **Upstream fix:** `determine_tld()` should also check `k.endswith('-main')`.

### Bug 2: Missing pyarrow Dependency
- **Location:** `_api.py` → `load_db()` → `df.to_parquet()`
- **Issue:** Uses pandas `.to_parquet()` but doesn't declare pyarrow or fastparquet in dependencies. Fails on fresh installs with `ImportError: Unable to find a usable engine`.
- **Our fix:** Added `pyarrow` to our `pyproject.toml` dependencies.
- **Upstream fix:** Add `pyarrow` to the library's dependencies.

### Bug 3: Python 3.14 Compatibility
- **Issue:** Invalid escape sequence `\!` in source code triggers `SyntaxWarning` (will become error in future Python). Also uvloop deprecation warnings on 3.14+.
- **Impact:** Warnings only for now, but will break on future Python versions.

### Bug 4: Silent Failure on Auth Errors
- **Location:** `_api.py` → `backoff()`
- **Issue:** On 401 errors, logs "Cookies expired" but continues retrying (up to 12 times with exponential backoff, ~3+ minutes total). Then returns `None` silently instead of raising. Caller gets cryptic `AttributeError: 'NoneType' object has no attribute 'json'`.
- **Upstream fix:** Should raise after first 401 with a clear error message.

### Bug 6: `aggregations()` mkdir/write Conflict for Specific Categories
- **Location:** `_api.py` → `aggregations()`, non-"all" branch
- **Issue:** For specific categories (e.g. "things"), creates `Path("things.json").mkdir()` (a directory), then immediately tries `Path("things.json").write_bytes()` → `IsADirectoryError`. The `mkdir` call was copy-pasted from the "all" branch where it makes sense (creating an output directory), but is wrong for single-category output.
- **Our workaround:** Pass `out=''` to skip disk writes entirely (we only need the return value).
- **Upstream fix:** Remove the `mkdir` call for single-category aggregations, or use different path logic.

### Open Issues on Upstream Repo
- **#24** "Does this library still work?" (Apr 2025) — unanswered
- **#22** "No Auth Method Provided" (2024) — likely the same cookie format bug

## What Needs To Be Done

### Testing (Before Contributing)
- [x] Test all 15 MCP tools through Claude Code interactively (2026-02-21)
- [x] Verify search_photos with various query filters (type, year, name, things)
- [x] Test download cycle (download_files: PASS)
- [x] Test trash/restore cycle (trash → list_trashed → restore: PASS)
- [x] Test upload cycle (2026-02-21, after restart — uploaded test file, got 201 Created)
- [x] Test get_aggregations (2026-02-21, after restart — returns dict with aggregation data)
- [x] Test list_folders (2026-02-21, after restart — returns 200 folders)
- [ ] Test with expired cookies (graceful error messaging)
- [ ] Long-running stability (does the parquet DB update correctly?)

### Upstream Contribution Plan
1. **Fork** `trevorhobenshield/amazon_photos` to `kpfitzgerald/amazon_photos`
2. **Fix Bug 1:** Update `determine_tld()` to accept both hyphen and underscore formats
3. **Fix Bug 2:** Add `pyarrow` to dependencies in `pyproject.toml`
4. **Fix Bug 3:** Fix `\!` escape sequence for Python 3.14+ compat
5. **Fix Bug 4:** Fail fast on 401 instead of retrying 12 times
6. **Fix Bug 5:** Deduplicate rows in parquet DB (every query returns each result twice)
7. **Fix Bug 6:** Remove `mkdir` for single-category aggregations (causes IsADirectoryError)
8. **Open PRs** — one per bug for clean review
9. If maintainer is unresponsive, maintain our fork as the active version

### MCP Server Improvements (Post-Testing)
- [ ] Add `search_by_location` tool (library supports location filters)
- [ ] Add `get_photo_details` tool for single-item metadata
- [ ] Add album management tools (create, add to, list contents)
- [ ] Consider batch download with progress reporting
- [ ] Add cookie refresh reminder (warn when approaching expiry)

## Build Timeline

### Session 1 (2026-02-21)
1. **Research** — confirmed official API deprecated, found `amazon-photos` lib (MIT, v0.0.97, Jan 2024), no existing MCP server
2. **Build** — created FastMCP server with 15 tools, modeled after book-library-mcp
3. **Auth** — used Playwright to open Amazon Photos in browser, user signed in interactively, extracted cookies via `page.context().cookies()`, saved to config
4. **Debug** — discovered TLD detection bug (`amazon.none`), fixed with cookie normalization; discovered missing pyarrow dep, added to deps
5. **Verify** — API confirmed working: 27,599 photos, 1,339 videos, 287 folders
6. **Publish** — initialized git, pushed to GitHub (`kpfitzgerald/amazon-photos-mcp`)
7. **Organize** — moved to Windows git dir with WSL symlink (applied to all 7 custom MCP servers)

### Session 2 (2026-02-21)
Interactive testing of all 15 MCP tools. Results:

| # | Tool | Status | Notes |
|---|------|--------|-------|
| 1 | check_connection | PASS | Cookies valid, 27,599 photos confirmed |
| 2 | get_storage_usage | PASS | Returns usage table correctly |
| 3 | get_photos | PASS | Returns recent photos with full EXIF metadata |
| 4 | get_videos | PASS | Returns recent videos with codec/duration metadata |
| 5 | get_aggregations | FAIL→FIXED | Upstream mkdir/write bug. Initial temp dir fix insufficient; final fix: pass `out=''` to skip writes. |
| 6 | search_photos | PASS | Tested with type, timeYear, name filters |
| 7 | search_by_date | PASS | Found Dec 2024 photos correctly |
| 8 | search_by_things | PASS | Found dog photos via Amazon's auto-labels |
| 9 | list_folders | FAIL→FIXED | Upstream returns list, not DataFrame. Fixed _safe_df_to_list. |
| 10 | get_folder_tree | PASS | Full 287-folder tree with ANSI colors |
| 11 | list_trashed | PASS | Empty list when clean, populated after trash |
| 12 | trash_items | PASS | Trashed photo, verified status=TRASH |
| 13 | restore_items | PASS | Restored photo, verified status=AVAILABLE |
| 14 | download_files | PASS | Downloaded 761KB HEIC to /tmp correctly |
| 15 | upload_file | FAIL→FIXED | Upstream expects directory, not file. Fixed with temp dir wrapper. |

**Bugs found in our MCP server (fixed in commit 3528471):**
1. `_safe_df_to_list` crashed on list return from `get_folders()`
2. `_safe_df_to_list` returned duplicate rows (upstream parquet DB issue) — added dedup by `id`
3. `get_aggregations` polluted CWD with JSON files — redirected to temp dir
4. `upload_file` passed file path to `upload()` which expects directory — wrapped in temp dir
5. `download_files` defaulted to CWD — changed to `~/Downloads/amazon-photos/`

**Bug #5 found in upstream lib:** Duplicate rows in parquet DB (every query returns each result twice)

### Session 3 (2026-02-21)
Post-restart verification of the 3 fixed tools:

| Tool | Status | Notes |
|------|--------|-------|
| list_folders | PASS | 200 folders returned. Fix was correct; uvx cache was serving stale code. |
| get_aggregations | FAIL→FIXED | Initial temp dir workaround failed — upstream has a second bug: `mkdir("things.json")` then `write_bytes` to it (Bug #6). Proper fix: pass `out=''` to skip disk writes entirely. |
| upload_file | PASS | Test file uploaded (201 Created), upstream DB refreshed. |

**Key discovery:** `uv cache clean --force` was required to clear 2.9 GiB of stale cached builds. The MCP server was running old code despite git commits. This is now documented as a lesson learned.

**Bug #6 found in upstream lib:** `aggregations()` for specific categories calls `Path(f"{category}.json").mkdir()` then `write_bytes()` to the same path → `IsADirectoryError`.

**Commit:** `d3f49a5` — replaced temp dir workaround with `out=''` parameter.

**All 15 tools now verified working.** 6 upstream bugs documented, ready to fork and PR.

## Runbook: Refreshing Cookies

Cookies expire periodically. When `check_connection` returns auth errors:

### Option A: Playwright (automated)
```
1. Open Playwright browser to https://www.amazon.com/photos
2. Sign in if prompted (interactive)
3. Extract via: page.context().cookies('https://www.amazon.com')
4. Save ubid_main, at_main, session-id to ~/.config/amazon-photos-mcp/cookies.json
```

### Option B: Manual DevTools
```
1. Open https://www.amazon.com/photos in Chrome
2. F12 → Application → Cookies → amazon.com
3. Copy: ubid-main (save as ubid_main), at-main (save as at_main), session-id
4. Update ~/.config/amazon-photos-mcp/cookies.json
```

Note: Browser shows hyphens (`ubid-main`), config file uses underscores (`ubid_main`).
The MCP server's `_normalize_cookies()` handles both formats.
