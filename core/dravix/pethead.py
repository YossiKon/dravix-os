"""Pet reaction: lift the head when petted, then lower it after a hold.

When the robot's head is petted (``touch.pet``), it tilts its head UP — a pleased,
"that feels nice" gesture — and returns to centre after ``hold_s`` seconds. Petting again
extends the hold (the head stays up). Only active when the robot can move its head; the
happy *face* on a pet is handled separately by the mood engine.
"""
from __future__ import annotations

import asyncio

from .dal.base import CAP_HEAD, RobotController
from .events import Event, EventBus
from .logging import get_logger

log = get_logger("pethead")


class PetHeadBehavior:
    def __init__(
        self,
        bus: EventBus,
        controller: RobotController,
        hold_s: float = 10.0,
        raise_pitch: float = 30.0,
    ) -> None:
        self._bus = bus
        self._robot = controller
        self._hold = hold_s
        self._raise = raise_pitch
        self._raised = False
        self._pump_task: asyncio.Task | None = None
        self._return_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._pump_task = asyncio.create_task(self._pump(), name="dravix-pethead")

    async def stop(self) -> None:
        for t in (self._pump_task, self._return_task):
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    async def _pump(self) -> None:
        q = self._bus.subscribe()
        try:
            while True:
                event: Event = await q.get()
                if event.type == "touch.pet":
                    await self._on_pet()
        except asyncio.CancelledError:
            raise
        finally:
            self._bus.unsubscribe(q)

    async def _on_pet(self) -> None:
        if not self._robot.supports(CAP_HEAD):
            return
        # Restart the "return to centre" timer on every pet (keeps the head up while petted).
        if self._return_task and not self._return_task.done():
            self._return_task.cancel()
        if not self._raised:
            try:
                await self._robot.move_head(0.0, self._raise)  # +pitch = look up (pleased)
                self._raised = True
            except Exception as exc:  # noqa: BLE001 — never let a pet crash the pump
                log.debug("pet head-raise failed: %s", exc)
                return
        self._return_task = asyncio.create_task(
            self._return_after(), name="dravix-pethead-return"
        )

    async def _return_after(self) -> None:
        try:
            await asyncio.sleep(self._hold)
            await self._robot.move_head(0.0, 0.0)  # back to straight ahead
            self._raised = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.debug("pet head-return failed: %s", exc)
            self._raised = False
