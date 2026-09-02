"""Visual reordering of Hebrew for the robot's LVGL screen (which has no BIDI support).

LVGL draws text strictly left-to-right, so a logical-order Hebrew string appears *reversed*
on the robot. We reorder it to VISUAL order here — on the dravix side — so the robot shows
Hebrew correctly, while speech (TTS) still receives the untouched logical text.

This is a pragmatic single-level reorder (reverse the line, then un-reverse the Latin/number
runs and mirror the brackets) — plenty for the short Hebrew lines dravix shows (greetings,
wellness tips, the permission line). LTR runs keep their internal separators ("22.5",
"12:30", "24>21", "hello world") so numbers, times and English phrases stay readable.
The fully-correct fix is enabling ``LV_USE_BIDI`` in the firmware; when that happens, set
``DRAVIX_ROBOT_RTL_FIX=false`` so we don't double-reverse.
"""
from __future__ import annotations

import re

_HEBREW = re.compile(r"[֐-׿יִ-ﭏ]")
# An LTR run: alphanumeric words INCLUDING the neutral separators between them, so
# "22.5" / "12:30" / "24>21" / "hello world" survive as one readable unit.
_LTR_RUN = re.compile(r"[A-Za-z0-9]+(?:[ .,:;/%&*+=<>'\"-]+[A-Za-z0-9]+)*")
# Paired characters must be mirrored on a reversed line: "(יציבה)" must not become ")יציבה(".
_MIRROR = str.maketrans("()[]{}", ")(][}{")


def has_hebrew(text: str) -> bool:
    return bool(_HEBREW.search(text or ""))


def to_visual(text: str) -> str:
    """Reorder (mostly) Hebrew text to visual order for a left-to-right renderer. Text with
    NO Hebrew is returned unchanged, so ASCII commands / agent names are never touched."""
    if not text or not _HEBREW.search(text):
        return text
    out = []
    for line in text.split("\n"):
        # reversing the whole line makes Hebrew read correctly right-to-left when drawn LTR…
        rev = line[::-1]
        # …but Latin/number runs got reversed too, so flip each of those back (whole runs,
        # separators included — "5.22" is the reversed "22.5" and must come back intact)…
        rev = _LTR_RUN.sub(lambda m: m.group(0)[::-1], rev)
        # …and brackets now face the wrong way (runs can't contain them), so mirror them.
        out.append(rev.translate(_MIRROR))
    return "\n".join(out)


def fit_bytes(text: str, limit: int) -> str:
    """Trim ``text`` to at most ``limit`` UTF-8 **bytes**, never splitting a character.

    Every ``text`` slot on the robot has a ``max_length``, and ESPHome enforces it in BYTES
    (``text_call.cpp``: ``this->value_.value().size()``). Python's ``text[:limit]`` counts
    CHARACTERS, so a Hebrew string — two bytes per letter — sails past a character check and
    is then REJECTED by the robot with no error anyone sees: the card, bubble or tip simply
    never updates and keeps showing whatever was there before. Always size a robot-bound
    string with this, and do it BEFORE ``for_robot`` (visual order puts the logical start at
    the end of the string, so trimming after reordering eats the beginning of the sentence).
    """
    if not text:
        return text
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    # "ignore" drops the partial character the cut may have left dangling
    return raw[:limit].decode("utf-8", "ignore")


def for_robot(text: str) -> str:
    """``to_visual`` unless the RTL fix is disabled (firmware BIDI is doing the job)."""
    try:
        from .config import get_settings

        if not getattr(get_settings(), "robot_rtl_fix", True):
            return text
    except Exception:  # noqa: BLE001 — if settings can't load, still fix (default behaviour)
        pass
    return to_visual(text)
