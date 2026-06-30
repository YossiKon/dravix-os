#!/usr/bin/env sh
# Map Home Assistant add-on options (/data/options.json) to DRAVIX_* env, then run.
# Uses python (always present) so no bashio/hassio base image is required.
set -e

opt() {
  python3 - "$1" <<'PY'
import json, sys
try:
    print(json.load(open("/data/options.json")).get(sys.argv[1], "") or "")
except Exception:
    print("")
PY
}

export DRAVIX_HOST="0.0.0.0"
export DRAVIX_PORT="8800"
export DRAVIX_DATA_DIR="/data"
export DRAVIX_LOG_LEVEL="$(opt log_level)"
export DRAVIX_HA_URL="$(opt ha_url)"
export DRAVIX_HA_TOKEN="$(opt ha_token)"
export DRAVIX_AI_PROVIDER="$(opt ai_provider)"
export DRAVIX_LOCAL_ONLY="$(opt local_only)"
export DRAVIX_FRIGATE_URL="$(opt frigate_url)"
export DRAVIX_FRIGATE_CAMERA="$(opt frigate_camera)"
export DRAVIX_ROBOT_MCP_URL="$(opt robot_mcp_url)"
export DRAVIX_ROBOT_MCP_TRANSPORT="$(opt robot_mcp_transport)"

# Use the real robot driver when a MCP URL is configured, else the mock.
if [ -n "$DRAVIX_ROBOT_MCP_URL" ]; then
  export DRAVIX_ROBOT_DRIVER="mcp"
else
  export DRAVIX_ROBOT_DRIVER="mock"
fi

cd /app/core
exec python3 -m dravix
