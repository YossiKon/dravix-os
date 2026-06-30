#!/usr/bin/env sh
# Map Home Assistant add-on options (/data/options.json) to DRAVIX_* env, then run.
# Uses python (always present) so no bashio/hassio base image is required.
set -e

opt() {
  python3 - "$1" <<'PY'
import json, sys
try:
    v = json.load(open("/data/options.json")).get(sys.argv[1])
except Exception:
    v = None
# Render bools as true/false (not "" — which would break a bool env var).
print("" if v is None else ("true" if v is True else ("false" if v is False else v)))
PY
}

export DRAVIX_HOST="0.0.0.0"
export DRAVIX_PORT="8800"
export DRAVIX_DATA_DIR="/data"
export DRAVIX_LOG_LEVEL="$(opt log_level)"
export DRAVIX_HA_URL="$(opt ha_url)"
export DRAVIX_HA_TOKEN="$(opt ha_token)"
export DRAVIX_AI_PROVIDER="$(opt ai_provider)"
export DRAVIX_IDLE_MOTION="$(opt idle_motion)"
export DRAVIX_LOCAL_ONLY="$(opt local_only)"
export DRAVIX_FRIGATE_URL="$(opt frigate_url)"
export DRAVIX_FRIGATE_CAMERA="$(opt frigate_camera)"
export DRAVIX_ROBOT_MCP_URL="$(opt robot_mcp_url)"
export DRAVIX_ROBOT_MCP_TRANSPORT="$(opt robot_mcp_transport)"
export DRAVIX_XIAOZHI_MCP_URL="$(opt xiaozhi_mcp_url)"

# Robot driver: explicit option (mock|ha|mcp).
export DRAVIX_ROBOT_DRIVER="$(opt robot_driver)"
[ -z "$DRAVIX_ROBOT_DRIVER" ] && export DRAVIX_ROBOT_DRIVER="mock"

# For the `ha` driver, assemble the entity map (StackChan ESPHome entities) as JSON.
export DRAVIX_HA_ROBOT_ENTITIES="$(
  python3 - <<'PY'
import json
o = {}
try:
    o = json.load(open("/data/options.json"))
except Exception:
    pass
m = {
    "face_select": o.get("robot_entity_face", ""),
    "head_yaw": o.get("robot_entity_head_yaw", ""),
    "head_pitch": o.get("robot_entity_head_pitch", ""),
    "media_player": o.get("robot_entity_media_player", ""),
    "tts_engine": o.get("robot_entity_tts", ""),
    "led_light": o.get("robot_entity_light", ""),
    "camera": o.get("robot_entity_camera", ""),
}
print(json.dumps({k: v for k, v in m.items() if v}))
PY
)"

cd /app/core
exec python3 -m dravix
