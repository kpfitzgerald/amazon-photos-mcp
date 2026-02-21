#!/bin/bash
# Amazon Photos MCP — Cookie Setup Helper
#
# To get your cookies:
# 1. Open https://www.amazon.com/photos in Chrome/Firefox
# 2. Log in to your Amazon account
# 3. Open DevTools (F12) > Application > Cookies > amazon.com
# 4. Copy the values for: ubid_main, at_main, session-id
#
# Then run this script and paste them when prompted.

CONFIG_DIR="$HOME/.config/amazon-photos-mcp"
COOKIE_FILE="$CONFIG_DIR/cookies.json"

mkdir -p "$CONFIG_DIR"

echo "=== Amazon Photos MCP — Cookie Setup ==="
echo ""
echo "Open https://www.amazon.com/photos in your browser."
echo "DevTools (F12) > Application > Cookies > amazon.com"
echo ""

read -p "ubid_main: " UBID
read -p "at_main: " AT
read -p "session-id: " SESSION

cat > "$COOKIE_FILE" << EOF
{
  "ubid_main": "$UBID",
  "at_main": "$AT",
  "session-id": "$SESSION"
}
EOF

chmod 600 "$COOKIE_FILE"
echo ""
echo "Cookies saved to $COOKIE_FILE"
echo "You can now start the MCP server."
