"""Mode engine: discovers plugins, runs modes, dispatches events, ticks them.

Two kinds of mode:
- **foreground** — one at a time; activating one deactivates the current.
- **ambient** — background behaviors that run alongside the foreground (and each other).
  Ambient modes auto-start at boot (unless disabled in their manifest).

Plugins live in ``plugins/<name>/`` with a ``plugin.yaml`` manifest:

    name: focus
    description: Calm, minimal-distraction work companion
    kind: foreground            # or "ambient"
    entrypoint: mode:FocusMode  # <module-file>:<ClassName>
    enabled: true
    config: {}
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

from ..logging import get_logger
from .base import Mode, ModeContext, ModeMeta

if TYPE_CHECKING:
    from ..store import Store

log = get_logger("modes")


@dataclass
class LoadedMode:
    meta: ModeMeta
    cls: type[Mode]
    config: dict[str, Any]
    path: pathlib.Path


class ModeEngine:
    def __init__(
        self,
        plugins_dir: pathlib.Path,
        base_ctx: ModeContext,
        tick_interval: float = 5.0,
        store: "Store | None" = None,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._base_ctx = base_ctx
        self._bus = base_ctx.bus
        self._tick_interval = tick_interval
        self._store = store
        self._modes: dict[str, LoadedMode] = {}
        self._foreground: str | None = None
        self._fg_instance: Mode | None = None
        self._ambient: dict[str, Mode] = {}
        self._event_task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None

    # ── discovery / loading ───────────────────────────────────────────────────
    def discover(self) -> None:
        self._modes.clear()
        if not self._plugins_dir.exists():
            log.warning("plugins dir %s does not exist", self._plugins_dir)
            return
        for manifest in sorted(self._plugins_dir.glob("*/plugin.yaml")):
            try:
                self._load_one(manifest)
            except Exception as exc:  # noqa: BLE001 — one bad plugin must not kill the rest
                log.error("failed to load plugin %s: %s", manifest.parent.name, exc)
        log.info("loaded %d mode(s): %s", len(self._modes), sorted(self._modes))

    def _load_one(self, manifest_path: pathlib.Path) -> None:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        name = data.get("name") or manifest_path.parent.name
        if not data.get("enabled", True):
            log.info("plugin %s disabled by manifest", name)
            return
        entry = data.get("entrypoint")
        if not entry or ":" not in entry:
            raise ValueError("manifest needs 'entrypoint: <module>:<Class>'")
        module_file, class_name = entry.split(":", 1)
        module_path = manifest_path.parent / f"{module_file}.py"
        cls = self._import_class(name, module_path, class_name)
        meta = ModeMeta(
            name=name,
            description=data.get("description", ""),
            kind=data.get("kind", "foreground"),
            enabled=True,
        )
        self._modes[name] = LoadedMode(
            meta=meta, cls=cls, config=data.get("config") or {}, path=manifest_path.parent
        )

    @staticmethod
    def _import_class(name: str, module_path: pathlib.Path, class_name: str) -> type[Mode]:
        spec = importlib.util.spec_from_file_location(f"dravix_plugin_{name}", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, class_name)
        if not issubclass(cls, Mode):
            raise TypeError(f"{class_name} is not a Mode subclass")
        return cls

    # ── introspection ─────────────────────────────────────────────────────────
    def is_active(self, name: str) -> bool:
        return name == self._foreground or name in self._ambient

    def _is_disabled(self, name: str) -> bool:
        return self._store is not None and self._store.is_disabled(name)

    def list_modes(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self._modes.values():
            # effective per-mode config = plugin.yaml defaults + the store's overrides —
            # the dashboard's Modes manager renders and edits exactly this dict
            config = dict(m.config)
            if self._store is not None:
                config.update(self._store.mode_config(m.meta.name))
            out.append({
                "name": m.meta.name,
                "description": m.meta.description,
                "kind": m.meta.kind,
                "active": self.is_active(m.meta.name),
                "disabled": self._is_disabled(m.meta.name),
                "config": config,
            })
        return out

    @property
    def active(self) -> str | None:
        return self._foreground

    @property
    def ambient_active(self) -> list[str]:
        return sorted(self._ambient)

    # ── instantiation ─────────────────────────────────────────────────────────
    def _instantiate(self, loaded: LoadedMode) -> Mode:
        config = dict(loaded.config)
        if self._store is not None:
            config.update(self._store.mode_config(loaded.meta.name))
        ctx = ModeContext(
            robot=self._base_ctx.robot,
            bus=self._base_ctx.bus,
            ai=self._base_ctx.ai,
            ha=self._base_ctx.ha,
            config=config,
        )
        inst = loaded.cls(ctx)
        inst.meta = loaded.meta
        return inst

    # ── activation ────────────────────────────────────────────────────────────
    async def activate(self, name: str) -> None:
        if name not in self._modes:
            raise KeyError(f"unknown mode {name!r}")
        if self._is_disabled(name):
            raise ValueError(f"mode {name!r} is disabled")
        loaded = self._modes[name]
        if loaded.meta.kind == "ambient":
            # Ambient activate is a toggle (the dashboard's Stop button re-calls activate).
            if name in self._ambient:
                await self._stop_ambient(name)
            else:
                await self._start_ambient(name)
            return
        if self._foreground == name:
            return
        await self._deactivate_foreground()
        self._fg_instance = self._instantiate(loaded)
        await self._fg_instance.on_enter()
        self._foreground = name
        await self._bus.publish("mode.activated", mode=name, kind="foreground")
        log.info("activated foreground mode %s", name)

    async def deactivate(self, name: str | None = None) -> None:
        if name is not None and name in self._ambient:
            await self._stop_ambient(name)
            return
        await self._deactivate_foreground()

    async def _deactivate_foreground(self) -> None:
        if self._foreground is None:
            return
        prev = self._foreground
        if self._fg_instance is not None:
            try:
                await self._fg_instance.on_exit()
            finally:
                self._fg_instance = None
        self._foreground = None
        await self._bus.publish("mode.deactivated", mode=prev)

    async def reload(self, name: str) -> None:
        """Re-instantiate a mode if it's active (e.g. after a runtime config change)."""
        if name == self._foreground:
            await self._deactivate_foreground()
            await self.activate(name)
        elif name in self._ambient:
            await self._stop_ambient(name)
            await self._start_ambient(name)

    async def _start_ambient(self, name: str) -> None:
        if name in self._ambient:
            return
        inst = self._instantiate(self._modes[name])
        await inst.on_enter()
        self._ambient[name] = inst
        await self._bus.publish("mode.activated", mode=name, kind="ambient")
        log.info("started ambient mode %s", name)

    async def _stop_ambient(self, name: str) -> None:
        inst = self._ambient.pop(name, None)
        if inst is None:
            return
        try:
            await inst.on_exit()
        finally:
            await self._bus.publish("mode.deactivated", mode=name)
            log.info("stopped ambient mode %s", name)

    # ── runtime ───────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._event_task = asyncio.create_task(self._pump(), name="dravix-mode-pump")
        self._tick_task = asyncio.create_task(self._ticker(), name="dravix-mode-tick")
        # Auto-start enabled ambient modes (skip any disabled via the store).
        for name, loaded in self._modes.items():
            if loaded.meta.kind == "ambient" and not self._is_disabled(name):
                try:
                    await self._start_ambient(name)
                except Exception as exc:  # noqa: BLE001
                    log.error("ambient mode %s failed to start: %s", name, exc)

    async def stop(self) -> None:
        for name in list(self._ambient):
            await self._stop_ambient(name)
        await self._deactivate_foreground()
        for task in (self._event_task, self._tick_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def _live_instances(self) -> list[Mode]:
        live = list(self._ambient.values())
        if self._fg_instance is not None:
            live.append(self._fg_instance)
        return live

    async def _pump(self) -> None:
        q = self._bus.subscribe()
        try:
            while True:
                event = await q.get()
                for inst in self._live_instances():
                    try:
                        await inst.on_event(event)
                    except Exception as exc:  # noqa: BLE001
                        log.error("mode %s on_event error: %s", inst.meta.name, exc)
        except asyncio.CancelledError:
            raise
        finally:
            self._bus.unsubscribe(q)

    async def _ticker(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_interval)
                for inst in self._live_instances():
                    try:
                        await inst.tick()
                    except Exception as exc:  # noqa: BLE001
                        log.error("mode %s tick error: %s", inst.meta.name, exc)
        except asyncio.CancelledError:
            raise
