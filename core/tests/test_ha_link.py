"""The HA link: state mirror (subscribe_entities frames), the write gate, the websocket
dispatcher and the client's read paths — all offline (no socket is ever opened)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from dravix.integrations import ha_writes
from dravix.integrations.ha_events import (
    HAEventBridge,
    HALinkDown,
    ha_ws_url,
    ws_url_candidates,
)
from dravix.integrations.ha_state import StateMirror, apply_diff, expand
from dravix.integrations.ha_writes import MISSING, WriteGate
from dravix.integrations.homeassistant import HAEntityNotFound, HomeAssistant

# ── URLs ─────────────────────────────────────────────────────────────────────────


def test_supervisor_proxy_websocket_url_and_fallback():
    # the add-on's zero-config base → the documented Supervisor websocket path
    assert ha_ws_url("http://supervisor/core") == "ws://supervisor/core/websocket"
    assert ws_url_candidates("ws://supervisor/core/websocket") == [
        "ws://supervisor/core/websocket", "ws://supervisor/core/api/websocket",
    ]
    # a direct HA URL keeps /api/websocket and has no alternate
    assert ha_ws_url("http://homeassistant:8123") == "ws://homeassistant:8123/api/websocket"
    assert ws_url_candidates("ws://homeassistant:8123/api/websocket") == [
        "ws://homeassistant:8123/api/websocket",
    ]


# ── the mirror ───────────────────────────────────────────────────────────────────

SNAPSHOT = {"a": {
    "binary_sensor.hall": {"s": "off", "a": {"device_class": "motion", "friendly_name": "Hall"}, "lc": 1700000000.0},
    "number.r_head_pitch": {"s": "200.0", "a": {"min": 158, "max": 260, "step": 1}, "lc": 1700000000.0, "lu": 1700000005.0},
}}


def test_expand_matches_the_rest_shape():
    st = expand("number.x", {"s": "5", "a": {"min": 0}, "lc": 1700000000.0})
    assert st["entity_id"] == "number.x" and st["state"] == "5" and st["attributes"] == {"min": 0}
    assert st["last_changed"] == st["last_updated"] and st["last_changed"].startswith("2023-11-14")


def test_apply_diff_merges_attributes_and_removals():
    cur = expand("light.x", {"s": "on", "a": {"brightness": 10, "rgb_color": [1, 2, 3]}, "lc": 1.0})
    new = apply_diff(cur, {"+": {"s": "off", "a": {"brightness": 0}, "lc": 2.0}, "-": {"a": ["rgb_color"]}})
    assert new["state"] == "off" and new["attributes"] == {"brightness": 0}
    assert cur["state"] == "on" and cur["attributes"]["rgb_color"] == [1, 2, 3]  # never mutated


async def test_mirror_snapshot_then_diffs_then_removal():
    m = StateMirror()
    seen: list = []
    m.add_listener(lambda eid, old, new: seen.append((eid, old and old["state"], new and new["state"])))
    m.begin_sync()
    assert m.apply(SNAPSHOT) == [] and seen == []      # the snapshot is a sync, not transitions
    assert m.synced and await m.wait_ready(0.01) and len(m) == 2
    m.apply({"c": {"binary_sensor.hall": {"+": {"s": "on", "lc": 1700000100.0}}}})
    st = m.get("binary_sensor.hall")
    assert st["state"] == "on" and st["attributes"]["device_class"] == "motion"  # merged
    m.apply({"a": {"text.new": {"s": "hi", "lc": 1.0}}})
    m.apply({"r": ["text.new"]})
    assert seen == [("binary_sensor.hall", "off", "on"), ("text.new", None, "hi"), ("text.new", "hi", None)]
    m.mark_stale()
    assert not m.synced and not await m.wait_ready(0.01)


# ── the websocket dispatcher ─────────────────────────────────────────────────────


class _Bus:
    def __init__(self):
        self.events: list = []

    async def publish(self, type_: str, **data):
        self.events.append((type_, data))


async def test_bridge_maps_diffs_to_events_but_not_the_snapshot():
    bus = _Bus()
    br = HAEventBridge("ws://x/api/websocket", "t", bus)
    br._entities_sub = 1
    subs = {2: "esphome.dravix_card"}
    br.mirror.begin_sync()
    await br._dispatch({"id": 1, "type": "event", "event": SNAPSHOT}, subs)
    assert bus.events == []  # a motion sensor that is ALREADY on must not fire at connect
    await br._dispatch({"id": 1, "type": "event", "event": {"c": {"binary_sensor.hall": {"+": {"s": "on"}}}}}, subs)
    assert bus.events == [("ha.motion", {"entity_id": "binary_sensor.hall", "device_class": "motion"})]
    await br._dispatch({"id": 2, "type": "event", "event": {"event_type": "esphome.dravix_card", "data": {"card": 2, "row": 1}}}, subs)
    assert bus.events[-1] == ("card.tap", {"card": 2, "row": 1})


async def test_bridge_routes_command_results_and_reports_errors():
    br = HAEventBridge("ws://x/api/websocket", "t", None)
    with pytest.raises(HALinkDown):
        await br.call_service("light", "turn_on", {"entity_id": "light.x"})

    class _WS:
        def __init__(self):
            self.sent = []

        async def send(self, raw):
            import json
            msg = json.loads(raw)
            self.sent.append(msg)
            ok = msg["service"] != "bad"
            reply = {"id": msg["id"], "type": "result", "success": ok}
            reply.update({"result": {"context": {}}} if ok else {"error": {"code": "x", "message": "nope"}})
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.ensure_future(br._dispatch(reply, {})))

    br._ws, br.connected = _WS(), True
    assert await br.call_service("light", "turn_on", {"entity_id": "light.x"}) == {"context": {}}
    assert br._ws.sent[0]["service_data"] == {"entity_id": "light.x"}
    with pytest.raises(RuntimeError, match="nope"):
        await br.call_service("light", "bad", {})


# ── the write gate ───────────────────────────────────────────────────────────────


@pytest.fixture
def fast(monkeypatch):
    """Shrink every gate timing so the policy can be exercised in milliseconds."""
    monkeypatch.setattr(ha_writes, "SETTLE_S", 0.05)
    monkeypatch.setattr(ha_writes, "REASSERT_MIN_S", 0.1)
    monkeypatch.setattr(ha_writes, "FAIL_MIN_S", 0.1)
    monkeypatch.setattr(ha_writes, "PROBE_MIN_S", 0.1)
    monkeypatch.setattr(ha_writes, "PENDING_TTL_S", 5.0)


def _gate(states: dict, *, rate: float = 0.05, fail: set | None = None, lag: bool = False):
    """A gate over a fake HA. ``states`` is the mirror; unless ``lag``, an accepted write
    shows up in it at once and the gate hears about it (as subscribe_entities would)."""
    sent: list = []
    box: dict = {}

    async def send(domain, service, data):
        if fail and data.get("entity_id") in fail:
            raise RuntimeError("HA 500")
        sent.append((domain, service, dict(data)))
        eid = data.get("entity_id")
        if lag or not isinstance(eid, str) or eid not in states:
            return []
        old = states[eid]
        if domain in ("text", "number", "select"):
            new = {"state": str(data.get("value", data.get("option")))}
        elif domain in ("light", "switch"):
            new = {"state": "on" if service == "turn_on" else "off",
                   "attributes": {"rgb_color": data.get("rgb_color")}}
        else:
            return []
        states[eid] = new
        box["gate"].on_state(eid, old, new)
        return []

    async def lookup(eid):
        return states.get(eid, MISSING)

    gate = WriteGate(send, lookup, rate_s=rate)
    gate.set_scope(["r"], states.keys())   # "<domain>.r_…" = the robot
    box["gate"] = gate
    return gate, sent


def _outside(gate, states, eid, state):
    """Someone else (a tap on the robot, a reboot) changes an entity."""
    old, states[eid] = states[eid], {"state": state}
    gate.on_state(eid, old, states[eid])


async def test_gate_skips_unavailable_and_delivers_when_back(fast):
    states = {"text.r_tip": {"state": "unavailable"}}
    gate, sent = _gate(states)
    assert await gate.call("text", "set_value", {"entity_id": "text.r_tip", "value": "drink"}) == []
    assert sent == [] and gate.stats()["pending"] == 1
    _outside(gate, states, "text.r_tip", "")       # the mirror says: back
    await asyncio.sleep(0.05)
    assert sent == [("text", "set_value", {"entity_id": "text.r_tip", "value": "drink"})]


async def test_gate_skips_missing_entities_and_voice_to_an_offline_speaker(fast):
    gate, sent = _gate({"media_player.r": {"state": "unavailable"}, "tts.cloud": {"state": "unknown"}})
    assert await gate.call("select", "select_option", {"entity_id": "select.r_gone", "option": "happy"}) == []
    assert await gate.call("tts", "speak", {"entity_id": "tts.cloud", "media_player_entity_id": "media_player.r",
                                            "message": "hi"}) == []
    assert sent == []
    await gate.call("homeassistant", "toggle", {"entity_id": "light.kitchen"})   # not a setter: untouched
    assert sent == [("homeassistant", "toggle", {"entity_id": "light.kitchen"})]


async def test_gate_leaves_the_rest_of_the_house_alone(fast):
    gate, sent = _gate({"light.kitchen": {"state": "unavailable"}})
    gate.set_scope(["r"])          # the robot is "r_…" — the kitchen is not
    for _ in range(2):
        await gate.call("light", "turn_on", {"entity_id": "light.kitchen", "brightness_pct": 50})
    await gate.call("light", "turn_off", {"entity_id": "all"})
    assert len(sent) == 3          # not the robot's: no dedupe, no rate limit, no offline skip


async def test_gate_drops_a_repeat_of_our_value_while_it_is_in_place(fast):
    states = {"number.r_vital_fun": {"state": "50.0"}}
    gate, sent = _gate(states)
    await gate.call("number", "set_value", {"entity_id": "number.r_vital_fun", "value": 49})
    await asyncio.sleep(0.08)
    await gate.call("number", "set_value", {"entity_id": "number.r_vital_fun", "value": 49})
    assert len(sent) == 1                           # the repeat is dropped


async def test_gate_rewrites_after_an_outside_change(fast):
    """The dashboard asked for focus, the person tapped awake on the robot, the dashboard
    asks for focus again — that must go through, not wait out a back-off."""
    states = {"select.r_mode": {"state": "awake"}}
    gate, sent = _gate(states)
    await gate.call("select", "select_option", {"entity_id": "select.r_mode", "option": "focus"})
    _outside(gate, states, "select.r_mode", "awake")
    await asyncio.sleep(0.06)
    await gate.call("select", "select_option", {"entity_id": "select.r_mode", "option": "focus"})
    assert [d["option"] for _, _, d in sent] == ["focus", "focus"]


async def test_gate_rewrites_a_wiped_slot_and_backs_off_a_rejected_one(fast):
    states = {"text.r_card1_title": {"state": ""}, "text.r_card2_title": {"state": ""}}
    gate, sent = _gate(states)
    await gate.call("text", "set_value", {"entity_id": "text.r_card1_title", "value": "Home"})
    _outside(gate, states, "text.r_card1_title", "")   # the robot rebooted: its slot is wiped
    await asyncio.sleep(0.06)
    await gate.call("text", "set_value", {"entity_id": "text.r_card1_title", "value": "Home"})
    assert len(sent) == 2                               # self-healed at once
    # a value the robot never shows (it rejected it): re-asserted only with back-off
    gate2, rejected = _gate({"text.r_card2_title": {"state": ""}}, lag=True)
    for _ in range(3):
        await gate2.call("text", "set_value", {"entity_id": "text.r_card2_title", "value": "x" * 300})
    assert len(rejected) == 1
    await asyncio.sleep(0.12)
    await gate2.call("text", "set_value", {"entity_id": "text.r_card2_title", "value": "x" * 300})
    assert len(rejected) == 2


async def test_gate_coalesces_a_burst_to_its_last_value(fast):
    states = {"select.r_face": {"state": "neutral"}}
    gate, sent = _gate(states, rate=0.1)
    for face in ("happy", "sad", "love"):
        await gate.call("select", "select_option", {"entity_id": "select.r_face", "option": face})
    assert [d["option"] for _, _, d in sent] == ["happy"]
    await asyncio.sleep(0.15)
    assert [d["option"] for _, _, d in sent] == ["happy", "love"]   # sad never hit the robot


async def test_gate_a_revert_is_a_change_even_while_ha_lags(fast):
    """neutral → happy → neutral with HA still showing neutral must END on neutral."""
    states = {"select.r_face": {"state": "neutral"}}
    gate, sent = _gate(states, rate=0.05, lag=True)
    await gate.call("select", "select_option", {"entity_id": "select.r_face", "option": "happy"})
    await gate.call("select", "select_option", {"entity_id": "select.r_face", "option": "neutral"})
    await asyncio.sleep(0.1)
    assert [d["option"] for _, _, d in sent] == ["happy", "neutral"]


async def test_gate_a_b_a_burst_ends_on_a(fast):
    """A held older value must never land after a newer request for the value in flight."""
    states = {"select.r_face": {"state": "neutral"}}
    gate, sent = _gate(states, rate=0.1, lag=True)
    for face in ("happy", "sad", "happy"):
        await gate.call("select", "select_option", {"entity_id": "select.r_face", "option": face})
    await asyncio.sleep(0.15)
    assert [d["option"] for _, _, d in sent] == ["happy"]   # "sad" never lands after it


async def test_gate_command_entities_are_always_written(fast):
    """Every head-pitch write stamps the firmware's commanded-move marker; the same image URL
    re-shows the picture — a repeat of these is a command, never a duplicate."""
    states = {"number.r_head_pitch": {"state": "209.0"}, "text.r_show_image_url": {"state": ""}}
    gate, sent = _gate(states, rate=0.05)
    gate.set_always_write(["number.r_head_pitch", "text.r_show_image_url"])
    for _ in range(2):
        await gate.call("number", "set_value", {"entity_id": "number.r_head_pitch", "value": 209})
        await gate.call("text", "set_value", {"entity_id": "text.r_show_image_url", "value": "http://x/l.jpg"})
        await asyncio.sleep(0.07)
    assert len(sent) == 4


async def test_gate_lane_spacing_keeps_a_nod_intact(fast):
    """Head moves wait their turn on the servo lane (spaced, in order) — not the 1 s entity
    rate — so a nod whose steps come FASTER than the bus spacing (emotes step every
    0.15–0.3 s; the bus wants 0.3 s) still delivers up, down and centre."""
    states = {"number.r_head_pitch": {"state": "209.0"}}
    gate, sent = _gate(states, rate=1.0)
    gate.set_lane(["number.r_head_pitch", "number.r_servo_x_angle"], spacing=0.03, retries=1)
    gate.set_always_write(["number.r_head_pitch"])
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    stamps: list[float] = []
    for v in (230, 190, 209):
        await gate.call("number", "set_value", {"entity_id": "number.r_head_pitch", "value": v})
        stamps.append(loop.time() - t0)
        await asyncio.sleep(0.005)
    assert [d["value"] for _, _, d in sent] == [230, 190, 209]
    assert stamps[2] - stamps[0] >= 0.055          # spaced by the bus, not sent on top of each other


async def test_gate_backs_off_after_a_failure_then_delivers(fast, monkeypatch):
    monkeypatch.setattr(ha_writes, "PENDING_TTL_S", 0.01)   # shorter than the back-off on purpose
    states = {"light.r_bar": {"state": "off"}}
    fail = {"light.r_bar"}
    gate, sent = _gate(states, rate=0.0, fail=fail)
    with pytest.raises(RuntimeError):
        await gate.call("light", "turn_on", {"entity_id": "light.r_bar", "rgb_color": [255, 0, 0]})
    # within the back-off the next write is held, not sent (and not raised)
    assert await gate.call("light", "turn_on", {"entity_id": "light.r_bar", "rgb_color": [0, 0, 255]}) == []
    assert gate.stats()["pending"] == 1
    fail.clear()                   # HA is fine again
    await asyncio.sleep(0.15)      # the held value outlives its TTL because it was waiting on the back-off
    assert [d.get("rgb_color") for _, _, d in sent] == [[0, 0, 255]]


async def test_gate_probes_unknown_targets_with_backoff(fast):
    states = {"text.r_bubble": {"state": "unknown"}}
    gate, sent = _gate(states, rate=0.0, lag=True)
    await gate.call("text", "set_value", {"entity_id": "text.r_bubble", "value": "a"})
    await gate.call("text", "set_value", {"entity_id": "text.r_bubble", "value": "b"})
    assert [d["value"] for _, _, d in sent] == ["a"]   # "b" waits for the probe window
    await asyncio.sleep(0.15)
    assert [d["value"] for _, _, d in sent] == ["a", "b"]


async def test_gate_lane_serialises_and_retries(fast):
    calls: list = []
    flaky = {"n": 1}

    async def send(domain, service, data):
        calls.append(data["entity_id"])
        if flaky["n"]:
            flaky["n"] -= 1
            raise RuntimeError("bus NAK")
        return []

    async def lookup(eid):
        return {"state": "1.0"}

    gate = WriteGate(send, lookup, rate_s=0.0)
    gate.set_lane(["number.yaw", "number.pitch"], spacing=0.02, retries=3, retry_delay=0.01)
    lane = gate._lanes["number.yaw"]
    gate.set_lane(["number.yaw", "number.pitch"], spacing=0.02, retries=3, retry_delay=0.01)
    assert gate._lanes["number.pitch"] is lane      # a rebuilt driver keeps the same bus lock
    await asyncio.gather(
        gate.call("number", "set_value", {"entity_id": "number.pitch", "value": 5}),
        gate.call("number", "set_value", {"entity_id": "number.yaw", "value": 6}),
    )
    assert calls.count("number.pitch") == 2 and calls.count("number.yaw") == 1  # one retry, no overlap


async def test_gate_batch_sends_only_what_changed(fast):
    states = {f"text.r_card{n}_{k}": {"state": ""} for n in (1, 2, 3) for k in ("title", "body")}
    gate, sent = _gate(states, rate=0.02)
    calls = [("text", "set_value", {"entity_id": eid, "value": "same"}) for eid in states]
    assert len(await gate.call_many(calls)) == 6 and len(sent) == 6
    await asyncio.sleep(0.03)
    calls[0] = ("text", "set_value", {"entity_id": "text.r_card1_title", "value": "new"})
    await gate.call_many(calls)
    assert [d["entity_id"] for _, _, d in sent[6:]] == ["text.r_card1_title"]


# ── the client ───────────────────────────────────────────────────────────────────


def _client(handler) -> HomeAssistant:
    ha = HomeAssistant("http://supervisor/core", "t")
    ha._client = httpx.AsyncClient(base_url=ha.base_url, transport=httpx.MockTransport(handler))
    return ha


async def test_client_reads_the_mirror_and_never_dumps_all_states():
    paths: list[str] = []

    def handler(req: httpx.Request):
        paths.append(req.url.path)
        if req.url.path.endswith("/api/states/sensor.r_state"):
            return httpx.Response(200, json={"entity_id": "sensor.r_state", "state": "awake", "attributes": {}})
        return httpx.Response(404, json={})

    ha = _client(handler)
    link = HAEventBridge("ws://supervisor/core/websocket", "t", None)
    ha.attach_link(link)
    # mirror not synced yet → one per-entity GET (cached), never /api/states
    assert (await ha.get_state("sensor.r_state"))["state"] == "awake"
    assert (await ha.get_state("sensor.r_state"))["state"] == "awake"
    assert paths == ["/core/api/states/sensor.r_state"]
    with pytest.raises(HAEntityNotFound):
        await ha.get_state("sensor.gone")
    # synced → memory only
    link.mirror.begin_sync()
    link.mirror.apply({"a": {"sensor.r_state": {"s": "sleep", "lc": 1.0}}})
    assert (await ha.get_state("sensor.r_state"))["state"] == "sleep"
    assert [s["entity_id"] for s in await ha.states()] == ["sensor.r_state"]
    assert "/core/api/states" not in paths
    await ha.close()


async def test_client_states_without_a_synced_mirror_fails_instead_of_dumping(monkeypatch):
    ha = _client(lambda req: httpx.Response(200, json=[]))
    ha.attach_link(HAEventBridge("ws://x/api/websocket", "t", None))

    async def quick(timeout):
        return False

    monkeypatch.setattr(ha.link.mirror, "wait_ready", quick)
    with pytest.raises(RuntimeError):
        await ha.states()
    await ha.close()


async def test_client_writes_over_rest_only_when_the_socket_is_down():
    posted: list[str] = []

    def handler(req: httpx.Request):
        posted.append(req.url.path)
        return httpx.Response(200, json=[])

    ha = _client(handler)
    link = HAEventBridge("ws://x/api/websocket", "t", None)
    ha.attach_link(link)
    ha.writes._rate = 0.0  # no rate limit — this test is about the transport
    link.mirror.begin_sync()
    link.mirror.apply({"a": {"light.r_bar": {"s": "off", "lc": 1.0}}})
    await ha.call_service("light", "turn_on", {"entity_id": "light.r_bar"})   # link down → REST
    assert posted == ["/core/api/services/light/turn_on"]
    ws_calls: list = []

    async def over_ws(domain, service, data):
        ws_calls.append((domain, service))
        return {"context": {}}

    link.call_service = over_ws  # type: ignore[method-assign]
    await ha.call_service("light", "turn_off", {"entity_id": "light.r_bar"})
    assert ws_calls == [("light", "turn_off")] and len(posted) == 1   # link up → websocket
    await ha.close()


# ── vitals: an offline robot is not an awake one ─────────────────────────────────


async def test_vitals_does_not_yawn_at_a_disconnected_robot():
    from dravix.vitals import VitalsEngine

    class _Driver:
        def __init__(self, offline):
            self.offline = offline

        async def is_offline(self):
            return self.offline

        async def get_text(self, role):
            return None  # what an unavailable State sensor reads as

    for offline, expect in ((True, []), (False, ["emote:yawn", "mode:sleep"])):
        did: list[str] = []
        eng = VitalsEngine(_Bus(), SimpleNamespace(driver=_Driver(offline)), tick_interval=0.01)
        eng.energy = 1.0

        async def emote(name, gated=False, _d=did):
            _d.append(f"emote:{name}")

        async def set_mode(mode, _d=did):
            _d.append(f"mode:{mode}")

        eng._emote, eng._set_mode = emote, set_mode
        task = asyncio.create_task(eng._needs_ticker())
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert did[:2] == expect, (offline, did)


# ── the real session, against a fake HA websocket server on localhost ───────────


async def test_session_end_to_end_with_supervisor_path_fallback():
    """Auth → subscribe_entities snapshot → a diff becomes a bus event → call_service over
    the socket. The first (documented) Supervisor path is refused, so the link must fall back
    to the other one instead of staying dark."""
    import json
    from http import HTTPStatus

    from websockets.asyncio.server import serve

    calls: list = []

    def refuse_first_path(connection, request):
        if request.path == "/core/websocket":
            return connection.respond(HTTPStatus.NOT_FOUND, "no such path\n")
        return None

    async def fake_ha(ws):
        await ws.send(json.dumps({"type": "auth_required"}))
        auth = json.loads(await ws.recv())
        assert auth == {"type": "auth", "access_token": "tok"}
        await ws.send(json.dumps({"type": "auth_ok"}))
        ent_id = None
        async for raw in ws:
            msg = json.loads(raw)
            await ws.send(json.dumps({"id": msg["id"], "type": "result", "success": True, "result": None}))
            if msg["type"] == "subscribe_entities":
                ent_id = msg["id"]
                await ws.send(json.dumps({"id": ent_id, "type": "event", "event": SNAPSHOT}))
            elif msg["type"] == "subscribe_events" and msg["event_type"] == "esphome.dravix_permission":
                await ws.send(json.dumps({"id": ent_id, "type": "event", "event": {
                    "c": {"binary_sensor.hall": {"+": {"s": "on", "lc": 1700000200.0}}}}}))
            elif msg["type"] == "call_service":
                calls.append((msg["domain"], msg["service"], msg["service_data"]))

    async with serve(fake_ha, "127.0.0.1", 0, process_request=refuse_first_path) as server:
        port = server.sockets[0].getsockname()[1]
        bus = _Bus()
        link = HAEventBridge(ha_ws_url(f"http://127.0.0.1:{port}/core"), "tok", bus, reconnect_max=0.05)
        link.start()
        try:
            assert await link.mirror.wait_ready(5.0)
            assert link.url.endswith("/core/api/websocket")      # fell back to the other path
            for _ in range(100):
                if bus.events:
                    break
                await asyncio.sleep(0.02)
            assert bus.events == [("ha.motion", {"entity_id": "binary_sensor.hall", "device_class": "motion"})]
            await link.call_service("number", "set_value", {"entity_id": "number.r_head_pitch", "value": 210})
            assert calls == [("number", "set_value", {"entity_id": "number.r_head_pitch", "value": 210})]
            assert link.status()["connected"] and link.status()["entities"] == 2
        finally:
            await link.stop()

