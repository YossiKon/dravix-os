"""Robot health: reboots are uptime drops, reasons become verdicts, history backfills."""
from __future__ import annotations

from dravix.health import RING_MAX, classify, detect, parse_history, sample_from_states

ENTS = {"uptime": "sensor.dravix_uptime", "reset_reason": "sensor.dravix_reset_reason",
        "heap_free": "sensor.dravix_heap_free", "loop_time": "sensor.dravix_loop_time"}


def test_classify_maps_reasons_to_actionable_kinds():
    assert classify("Task Watchdog")["kind"] == "watchdog"
    assert classify("Interrupt Watchdog")["kind"] == "watchdog"
    assert classify("Brownout")["kind"] == "power"
    assert classify("Power On Reset")["kind"] == "power"
    assert classify("Exception")["kind"] == "bug"
    assert classify("Software Reset CPU")["kind"] == "software"
    assert classify("Deep-Sleep Wake")["kind"] == "sleep"
    assert classify("")["kind"] == "none" and classify(None)["kind"] == "none"
    assert classify("Cosmic ray")["kind"] == "other"


def test_reboot_is_an_uptime_drop_with_the_pre_crash_picture():
    a = {"uptime": 900.0, "reset_reason": "Task Watchdog", "heap_free": 41000.0, "loop_time": 180.0}
    b = {"uptime": 930.0, "reset_reason": "Task Watchdog", "heap_free": 40000.0, "loop_time": 190.0}
    c = {"uptime": 12.0, "reset_reason": "Task Watchdog", "heap_free": 120000.0, "loop_time": 20.0}
    assert detect(None, a) is None                 # first sample: nothing to compare
    assert detect(a, b) is None                    # still up
    r = detect(b, c)
    assert r and r["kind"] == "watchdog"
    assert r["heap_free_before"] == 40000.0 and r["loop_time_before"] == 190.0   # from BEFORE the drop
    assert r["uptime_before"] == 930.0


def test_unavailable_uptime_is_skipped_not_a_reboot():
    up = {"uptime": 500.0, "reset_reason": "Power On Reset"}
    mid = {"uptime": None, "reset_reason": None}     # the robot is mid-reboot
    assert detect(up, mid) is None
    assert detect(mid, {"uptime": 5.0, "reset_reason": "Power On Reset"}) is None   # prev had no uptime


def test_sample_from_states_reads_roles_and_treats_unavailable_as_none():
    states = [
        {"entity_id": "sensor.dravix_uptime", "state": "123.5"},
        {"entity_id": "sensor.dravix_reset_reason", "state": "Brownout"},
        {"entity_id": "sensor.dravix_heap_free", "state": "unavailable"},
    ]
    s = sample_from_states(states, ENTS)
    assert s["uptime"] == 123.5 and s["reset_reason"] == "Brownout"
    assert s["heap_free"] is None and s["loop_time"] is None and "at" in s


def test_parse_history_finds_yesterdays_reboots_with_their_reasons():
    rows = [
        [{"entity_id": "sensor.dravix_uptime", "state": "3000", "last_changed": "2026-09-03T01:00:00+00:00"},
         {"entity_id": "sensor.dravix_uptime", "state": "3600", "last_changed": "2026-09-03T01:10:00+00:00"},
         {"entity_id": "sensor.dravix_uptime", "state": "30", "last_changed": "2026-09-03T01:12:00+00:00"},   # drop
         {"entity_id": "sensor.dravix_uptime", "state": "unavailable", "last_changed": "2026-09-03T02:00:00+00:00"},
         {"entity_id": "sensor.dravix_uptime", "state": "20", "last_changed": "2026-09-03T02:01:00+00:00"}],  # drop
        [{"entity_id": "sensor.dravix_reset_reason", "state": "Power On Reset", "last_changed": "2026-09-03T00:00:00+00:00"},
         {"entity_id": "sensor.dravix_reset_reason", "state": "Task Watchdog", "last_changed": "2026-09-03T01:12:05+00:00"}],
    ]
    found = parse_history(rows, ENTS)
    assert [r["kind"] for r in found] == ["watchdog", "watchdog"]
    assert found[0]["at"] == "2026-09-03T01:12:00+00:00" and found[0]["uptime_before"] == 3600.0
    assert all(r["from_history"] for r in found)


def test_store_ring_is_capped(tmp_path):
    from dravix.store import Store

    st = Store(tmp_path / "s.json")
    for i in range(RING_MAX + 7):
        st.add_reboot({"at": f"2026-09-03T00:00:{i:02d}+00:00", "reason": "x"}, RING_MAX)
    ring = st.reboots()
    assert len(ring) == RING_MAX and ring[-1]["at"].endswith(f"{RING_MAX + 6:02d}+00:00")
