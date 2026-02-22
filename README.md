# Amazon Photos MCP Server

FastMCP server wrapping the unofficial [amazon-photos](https://github.com/trevorhobenshield/amazon_photos) Python library (MIT license).

## Setup

### 1. Get your Amazon cookies

1. Open https://www.amazon.com/photos in Chrome
2. Log in to your Amazon account
3. Open DevTools (F12) > Application > Cookies > amazon.com
4. Copy these three values:
   - `ubid_main`
   - `at_main`
   - `session-id`

### 2. Save cookies

Run the setup helper:
```bash
~/amazon-photos-mcp/setup-cookies.sh
```

Or manually create `~/.config/amazon-photos-mcp/cookies.json`:
```json
{
  "ubid_main": "your-value-here",
  "at_main": "your-value-here",
  "session-id": "your-value-here"
}
```

### 3. Register with Claude Code

```bash
claude mcp add amazon-photos -- uvx --from ~/amazon-photos-mcp amazon-photos-mcp
```

## Tools (15)

| Tool | Description |
|------|-------------|
| `check_connection` | Test API access and get storage usage |
| `search_photos` | Search with query filters (things, dates, locations) |
| `get_photos` | Get recent photos |
| `get_videos` | Get recent videos |
| `get_storage_usage` | Storage plan and usage stats |
| `get_aggregations` | Auto-detected labels (people, things, places) |
| `list_folders` | List all folders |
| `get_folder_tree` | Display folder hierarchy |
| `search_by_date` | Search by year/month/day |
| `search_by_things` | Search by detected objects (beach, dog, etc.) |
| `trash_items` | Move items to trash |
| `list_trashed` | View trash contents |
| `restore_items` | Restore from trash |
| `upload_file` | Upload a file |
| `download_files` | Download by node ID |

## Auth Notes

- Uses cookie-based auth (not OAuth) — cookies expire and need periodic refresh
- Cookies stored at `~/.config/amazon-photos-mcp/cookies.json` (chmod 600)
- This is an unofficial API — may break if Amazon changes their frontend
