"""Companion mode — a chatty desk buddy.

Demonstrates using the AI router from inside a mode and driving the face from the reply's
emotion tag (the ``(happy)`` convention). Degrades gracefully when no AI provider is
configured (uses a canned greeting) and when the robot can't speak/emote (mock/partial
backends).
"""
from __future__ import annotations

from dravix.dal.base import CAP_FACE, CAP_SAY
from dravix.events import Event
from dravix.modes import Mode, ModeMeta
from dravix.persona import Persona, parse_expression


class CompanionMode(Mode):
    meta = ModeMeta(name="companion", description="Chatty desk buddy", kind="foreground")

    async def on_enter(self) -> None:
        self._persona = Persona()
        line = await self._greeting()
        await self._express_and_say(line)

    async def on_event(self, event: Event) -> None:
        # When something is said to/around the robot, the chat endpoint handles the reply; here
        # we just keep the face lively by reflecting our own speech as a happy beat.
        if event.type == "robot.say" and self.ctx.robot.supports(CAP_FACE):
            from dravix.dal.base import Expression

            await self.ctx.robot.set_face(Expression.HAPPY)

    async def _greeting(self) -> str:
        cfg = self.ctx.config
        if self.ctx.ai is not None:
            try:
                reply = await self.ctx.ai.converse(
                    cfg.get("greeting_prompt", "Say hi."), system=self._persona.system_prompt
                )
                if reply.text:
                    return reply.text
            except Exception as exc:  # noqa: BLE001 — fall back if AI is unavailable
                self.ctx.log.warning("companion greeting via AI failed: %s", exc)
        return cfg.get("fallback_greeting", "(happy) Hi!")

    async def _express_and_say(self, text: str) -> None:
        expr, clean = parse_expression(text)
        if self.ctx.robot.supports(CAP_FACE):
            await self.ctx.robot.set_face(expr)
        if clean and self.ctx.robot.supports(CAP_SAY):
            await self.ctx.robot.say(clean)
