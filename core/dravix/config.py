"""Configuration + well-known paths for dravix-os.

All settings are read from environment variables (prefixed ``DRAVIX_``) or a ``.env`` file.
See ``.env.example`` for the full list.
"""
from __future__ import annotations

import pathlib
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Well-known paths (resolved relative to this package) ──────────────────────
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
CORE_DIR = PACKAGE_DIR.parent
REPO_ROOT = CORE_DIR.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
DOCS_DIR = REPO_ROOT / "docs"
DATA_DIR = REPO_ROOT / "data"  # runtime state (gitignored); store.json lives here
WEB_STATIC_DIR = PACKAGE_DIR / "web" / "static"  # built-in vanilla fallback page
WEB_DIST_DIR = REPO_ROOT / "web" / "dist"  # the React dashboard build (Phase 2), if present


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRAVIX_",
        # Look for .env in core/ first, then the repo root.
        env_file=(".env", str(REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service
    host: str = "0.0.0.0"
    port: int = 8800
    log_level: str = "INFO"
    data_dir: str = ""  # runtime state dir (store.json); blank = repo data/
    # Optional API auth: when non-empty, every /api/* and /camera/* request (except
    # /api/health) must carry this token (Authorization: Bearer, X-API-Token, or ?token=).
    api_token: str = ""
    # Language for the built-in wellness tips (en | he). The store key `language` overrides.
    language: str = Field(
        "en", validation_alias=AliasChoices("DRAVIX_LANG", "DRAVIX_LANGUAGE")
    )

    # The robot's LVGL screen has no bidirectional-text support, so Hebrew would render
    # left-to-right (reversed). When true (default), dravix reorders Hebrew to VISUAL order
    # before sending it to the robot's text slots — TTS still gets the correct logical text.
    # Set false if the firmware ever enables LV_USE_BIDI (otherwise it double-reverses).
    robot_rtl_fix: bool = True

    # Robot (StackChan)
    robot_driver: str = "mock"  # mcp | ha | mock
    robot_mcp_url: str = ""
    robot_mcp_transport: str = "auto"  # auto | streamable_http | sse | websocket
    robot_mcp_token: str = ""

    # When False (default), the MCP server (incl. the xiaozhi cloud bridge) hides the risky
    # tools: the generic HA service call, lock/unlock, and alarm disarm. Read-only + robot +
    # benign tools stay available either way.
    expose_risky_tools: bool = False

    # xiaozhi MCP接入点 (access point): dravix connects here as an MCP *server* and exposes
    # its tools to the robot's AI (the robot can then control HA / run dravix features by
    # voice). This is the reverse of robot_mcp_url. Usually a wss://api.xiaozhi.me/mcp/?token=
    xiaozhi_mcp_url: str = ""

    # When False, the robot stops its automatic idle head movement (the ambient glances).
    # Manual control + commanded movements still work. Toggle live from the dashboard too.
    idle_motion: bool = False  # dravix's own idle glances; off by default — the ESPHome firmware
    # already glances on its own (and correctly freezes in sleep/focus/quiet), so leaving dravix's
    # idle motion off avoids two systems fighting over the head. Turn on for the mock/other backends.

    # Pet reaction: when petted, tilt the head up (pleased) then return after a hold.
    # Degrees up on a pet (0 disables the head-lift). Values ≤1 are taken as an already-
    # normalized fraction of travel; pethead converts degrees to the -1..1 head API.
    pet_head_raise: float = 30.0
    pet_head_hold_s: float = 10.0  # seconds to hold up before returning to centre

    # Home Assistant
    ha_url: str = "http://homeassistant.local:8123"
    ha_token: str = ""
    ha_mcp_url: str = ""

    # HA event bridge (motion/presence/door -> event bus)
    ha_events_enabled: bool = True
    ha_event_map: dict[str, str] = Field(default_factory=dict)
    # When DRAVIX_ROBOT_DRIVER=ha, which HA entities drive the robot. JSON, keys:
    # head_yaw, head_pitch (number.*), media_player (for TTS), led_light (light.*)
    ha_robot_entities: dict[str, str] = Field(default_factory=dict)

    # AI router
    ai_provider: str = "ha_assist"  # ha_assist | claude | openai | ollama
    ha_assist_agent: str = ""
    ai_max_tokens: int = 512
    # Per-provider model (used when DRAVIX_AI_PROVIDER selects that provider).
    claude_model: str = "claude-opus-4-8"  # fast/cheap: claude-haiku-4-5 · balanced: claude-sonnet-4-6
    openai_model: str = "gpt-4o-mini"
    ollama_model: str = "llama3.2"

    # Local-first: when true, cloud AI providers (claude/openai) are refused — keep everything
    # on your own box (HA Assist with a local pipeline, or Ollama). No M5Stack/other cloud.
    local_only: bool = True

    # Frigate / cameras
    frigate_url: str = ""  # optional direct Frigate base, e.g. http://frigate:5000
    frigate_camera: str = ""  # default camera entity, e.g. camera.front_door

    # Weather (for /api/say/weather) — a Home Assistant weather entity
    weather_entity: str = ""  # e.g. weather.home

    # Provider keys (read without the DRAVIX_ prefix too, for convenience)
    anthropic_api_key: str = Field(
        "", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "DRAVIX_ANTHROPIC_API_KEY")
    )
    openai_api_key: str = Field(
        "", validation_alias=AliasChoices("OPENAI_API_KEY", "DRAVIX_OPENAI_API_KEY")
    )
    ollama_url: str = Field(
        "http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_URL", "DRAVIX_OLLAMA_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def security_dir() -> pathlib.Path:
    """Where the security mode stores its snapshots — persistent add-on storage,
    day-folders (YYYY-MM-DD/HHMMSS.jpg). Shared by the mode and the /api/security routes."""
    s = get_settings()
    base = pathlib.Path(s.data_dir) if s.data_dir else DATA_DIR
    return base / "security"
