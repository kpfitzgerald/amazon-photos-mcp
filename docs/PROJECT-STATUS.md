# Amazon Photos MCP — Project Status

## Overview

FastMCP server wrapping the unofficial [amazon-photos](https://github.com/trevorhobenshield/amazon_photos) Python library (MIT license, by trevorhobenshield). Provides 15 tools for Claude Code to search, browse, upload, download, and manage an Amazon Photos library.

- **Repo:** https://github.com/kpfitzgerald/amazon-photos-mcp
- **Local:** `~/amazon-photos-mcp/`
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

### Open Issues on Upstream Repo
- **#24** "Does this library still work?" (Apr 2025) — unanswered
- **#22** "No Auth Method Provided" (2024) — likely the same cookie format bug

## What Needs To Be Done

### Testing (Before Contributing)
- [ ] Test all 15 MCP tools through Claude Code interactively
- [ ] Verify search_photos with various query filters
- [ ] Test upload/download cycle
- [ ] Test trash/restore cycle
- [ ] Test with expired cookies (graceful error messaging)
- [ ] Long-running stability (does the parquet DB update correctly?)

### Upstream Contribution Plan
1. **Fork** `trevorhobenshield/amazon_photos` to `kpfitzgerald/amazon_photos`
2. **Fix Bug 1:** Update `determine_tld()` to accept both hyphen and underscore formats
3. **Fix Bug 2:** Add `pyarrow` to dependencies in `pyproject.toml`
4. **Fix Bug 3:** Fix `\!` escape sequence for Python 3.14+ compat
5. **Fix Bug 4:** Fail fast on 401 instead of retrying 12 times
6. **Open PRs** — one per bug for clean review
7. If maintainer is unresponsive, maintain our fork as the active version

### MCP Server Improvements (Post-Testing)
- [ ] Add `search_by_location` tool (library supports location filters)
- [ ] Add `get_photo_details` tool for single-item metadata
- [ ] Add album management tools (create, add to, list contents)
- [ ] Consider batch download with progress reporting
- [ ] Add cookie refresh reminder (warn when approaching expiry)
