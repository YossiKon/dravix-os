"""RTL fix for the robot's no-BIDI LVGL screen: reorder Hebrew, leave ASCII/TTS untouched."""
from __future__ import annotations

from dravix.bidi import for_robot, has_hebrew, to_visual


def test_ascii_untouched():
    assert to_visual("rm -rf build/") == "rm -rf build/"
    assert to_visual("claude: working") == "claude: working"
    assert has_hebrew("hello world") is False


def test_pure_hebrew_is_reversed_for_ltr_screen():
    assert has_hebrew("שלום") is True
    # reversing the string makes it read correctly right-to-left when drawn left-to-right
    assert to_visual("שלום") == "שלום"[::-1]
    assert to_visual("צריך אישור") == "צריך אישור"[::-1]


def test_mixed_keeps_latin_and_numbers_readable():
    out = to_visual("שלום Yossi")
    assert "Yossi" in out and "issoY" not in out       # the name is NOT mangled
    assert out.startswith("Yossi")                     # Latin run sits at the visual start
    assert "23" in to_visual("טמפרטורה 23")            # numbers read correctly


def test_multiline_each_line_reordered():
    assert to_visual("שלום\nעולם") == "שלום"[::-1] + "\n" + "עולם"[::-1]


def test_numbers_keep_internal_separators():
    # decimals, times and ranges are single LTR units — they must come back intact
    assert "22.5" in to_visual("טמפרטורה 22.5")
    assert "12:30" in to_visual("תזכורת 12:30")
    assert "24>21" in to_visual("סלון 24>21")
    assert "20-20-20" in to_visual("כלל 20-20-20")


def test_adjacent_latin_words_keep_their_order():
    out = to_visual("תריץ hello world עכשיו")
    assert "hello world" in out  # not "world hello"


def test_brackets_are_mirrored():
    # "(יציבה)" logical → the visual line must still OPEN toward the word
    out = to_visual("שב זקוף (יציבה)")
    assert ")" + "יציבה"[::-1] + "(" not in out
    assert "(" + "יציבה"[::-1] + ")" in out


def test_for_robot_can_be_disabled(monkeypatch):
    from dravix.config import get_settings

    monkeypatch.setenv("DRAVIX_ROBOT_RTL_FIX", "false")
    get_settings.cache_clear()
    try:
        assert for_robot("שלום") == "שלום"             # disabled → logical text passes through
    finally:
        monkeypatch.delenv("DRAVIX_ROBOT_RTL_FIX", raising=False)
        get_settings.cache_clear()
