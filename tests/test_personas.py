"""Off-Brand Reachy: persona catalog, the show logic, the offline interview, the agent tools and the API."""
import json
import random

from fastapi.testclient import TestClient
from test_realtime import fake_session, make

from beating_in_sync_app.body.gestures import EXPRESS_GESTURES, GESTURES
from beating_in_sync_app.brain.persona_show import PersonaShow, slot_from
from beating_in_sync_app.brain.personas import BASE, DEFAULT_ORDER, PERSONAS, normalize_cast
from beating_in_sync_app.config import Config
from beating_in_sync_app.events import EventBus
from beating_in_sync_app.personality import load_profile
from beating_in_sync_app.realtime import PERSONA_TOOLS, agent_spec
from beating_in_sync_app.runtime import SessionOptions, SessionRunner
from beating_in_sync_app.web import create_app


def test_catalog_is_complete_and_consistent():
    assert len(EXPRESS_GESTURES) == 33 and all(g in GESTURES for g in EXPRESS_GESTURES)
    for p in PERSONAS.values():
        assert p.entrance in GESTURES and all(g in GESTURES for g in p.gestures), p.key
        for v in p.camera.values():
            gesture, line = v.split("|")
            assert gesture in GESTURES and line, p.key
        assert p.questions and p.bridges and p.glitch_in and p.opener
    assert DEFAULT_ORDER[0] == BASE and all(k in PERSONAS for k in DEFAULT_ORDER)
    # head yaw always within 60 deg of the body, body within +-160 (SDK limits)
    assert all(abs(q.yaw - q.body_yaw) <= 60 and abs(q.body_yaw) <= 160 for g in EXPRESS_GESTURES for q in GESTURES[g])


def test_cast_always_starts_with_base_and_respects_no_tease():
    assert normalize_cast(["noir", "diva", "noir", "nope"]) == ["base", "noir", "diva"]
    assert normalize_cast(["bored_teen", "tia", "villain"], no_tease=True) == ["base", "tia"]


def test_show_switches_on_cadence_and_finishes():
    show = PersonaShow(["base", "noir", "diva"], switch_every=2, rng=random.Random(0))
    seen = [show.current.key]
    while not show.finished:
        show.on_exchange()
        if show.switch_due():
            p = show.advance()
            if p:
                seen.append(p.key)
    assert seen == ["base", "noir", "diva"]


def test_reset_and_discomfort_drop_teasing():
    show = PersonaShow(["base", "noir", "diva", "villain", "tia"], switch_every=3)
    show.advance()
    show.drop_teasing()
    assert show.cast == ["base", "noir", "tia"]
    assert PersonaShow.is_reset("Reachy, reset!") and not PersonaShow.is_reset("I reset my phone yesterday")
    show.reset()
    assert show.current.key == BASE and show.upcoming is None


def test_reaction_echoes_the_participant():
    assert slot_from("Well, I build robots, mostly for fun") == "You build robots"
    show = PersonaShow(["base", "villain"], rng=random.Random(1))
    show.advance()
    line = show.reaction("I collect old maps", words=4)
    assert "You collect old maps" in line and line.split()[0] in {"Da...", "Excellent.", "Nyet!"}


def test_agent_spec_for_personas():
    body, tools = agent_spec(load_profile("off_brand_reachy"), "voice", "llm")
    agent = body["conversation_config"]["agent"]
    assert agent["first_message"] == "{{opener}}" and "{{cast}}" in agent["prompt"]["prompt"]
    assert set(agent["dynamic_variables"]["dynamic_variable_placeholders"]) == {"cast", "opener"}
    assert tools is PERSONA_TOOLS and {t["tool_config"]["name"] for t in tools} >= {"reachy_gesture", "reachy_switch_persona"}
    cast = PersonaShow(["base", "noir"]).agent_cast_prompt()
    assert "Noir detective" in cast and "Diva" not in cast


def persona_rc(cast=("base", "noir", "diva"), no_tease=False):
    s = fake_session(no_tease=no_tease, stage=3)
    s.show = PersonaShow(list(cast), switch_every=2, rng=random.Random(0), no_tease=no_tease)
    s.persona_event = lambda reason, source="persona": s.log.event("persona", 1.0, persona=s.show.current.key)
    rc = make(s)
    rc.show, rc.switch_pending, rc.closing_t, rc.last_agent_t, rc.speaking_until = s.show, None, 0.0, 0.0, 0.0
    rc.context = rc.direct = lambda text: rc.sent.append({"context": text})
    return s, rc


def test_agent_switch_is_validated_against_the_cast():
    s, rc = persona_rc()
    rc._on_tool({"tool_name": "reachy_switch_persona", "tool_call_id": "a", "parameters": {"persona": "villain"}})
    assert rc.sent[-1]["is_error"] and "not in your cast" in rc.sent[-1]["result"]
    rc._on_tool({"tool_name": "reachy_switch_persona", "tool_call_id": "b", "parameters": {"persona": "noir"}})
    assert not rc.sent[-1]["is_error"] and s.show.current.key == "noir"
    assert s.body.played and isinstance(s.body.played[-1], list)        # glitch + entrance keyframes


def test_director_asks_for_switch_then_close():
    s, rc = persona_rc(cast=("base", "noir"))
    ana = type("A", (), {"cues": set()})()
    rc._persona_user("I like rain", ana)
    rc._persona_user("and coffee", ana)
    assert rc.switch_pending == "noir" and "reachy_switch_persona with noir" in rc.sent[-1]["context"]
    rc.switch_to("noir", "agent")
    rc._persona_user("yes", ana)
    rc._persona_user("no", ana)
    assert rc.closing_t and "Close now as Base Reachy" in rc.sent[-1]["context"]


def test_distress_resets_to_base():
    s, rc = persona_rc()
    rc.switch_to("diva", "agent")
    rc._persona_user("that's not funny", type("A", (), {"cues": set()})())
    assert s.show.current.key == BASE and "just joking" in rc.sent[-1]["context"]


def run_offline(tmp_path, steps, **kw):
    scen = tmp_path / "scen.json"
    scen.write_text(json.dumps(steps))
    bus = EventBus()
    runner = SessionRunner(bus, Config(sessions_dir=str(tmp_path / "s")))
    runner.start(SessionOptions(llm=False, voice="sim", listener="scenario", scenario=str(scen), time_scale=40,
                                profile="off_brand_reachy", camera=False, **kw))
    runner.wait()
    log = next((tmp_path / "s").glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_offline_interview_runs_the_selected_cast(tmp_path):
    steps = [{"say": w} for w in ["I'm Sam", "I make bread", "Pizza", "I run marathons", "Maybe", "Ha, fine",
                                  "Not really", "I sing in the shower", "Sure"]]
    ev = run_offline(tmp_path, steps, personas=["noir", "hype_bro"], switch_every=3, heart_wake=False)
    order = [e["persona"] for e in ev if e["kind"] == "persona"]
    assert order[:3] == ["base", "noir", "hype_bro"] and order[-1] == "base"     # closes as Base Reachy
    said = [e["said"] for e in ev if e["kind"] == "turn" and e["said"]]
    assert "Static... rain..." in " ".join(said) and "none of that was real" in said[-1]
    assert not any(e["kind"] == "stage" and e["stage"] in (0, 5) for e in ev)      # no heart wake, no music


def test_offline_stop_word_resets_and_session_closes(tmp_path):
    ev = run_offline(tmp_path, [{"say": "hello"}, {"say": "Reachy, reset"}, {"say": "ok"}, {"say": "thanks"}],
                     personas=["villain"], switch_every=2, heart_wake=False)
    acts = [e["act"] for e in ev if e["kind"] == "turn"]
    assert "reset" in acts and acts[-1] == "goodbye"


def test_api_personas_and_presets(tmp_path, monkeypatch):
    import beating_in_sync_app.web as web

    monkeypatch.setattr(web, "PRESETS_DIR", tmp_path / "presets")
    bus, cfg = EventBus(), Config(sessions_dir=str(tmp_path))
    client = TestClient(create_app(SessionRunner(bus, cfg), bus, cfg))
    data = client.get("/api/personas").json()
    assert len(data["personas"]) >= 9 and data["base"] == "base"
    prof = {p["name"]: p for p in client.get("/api/profiles").json()}
    assert prof["off_brand_reachy"]["kind"] == "personas" and prof["beating_in_sync"]["selectable"]
    r = client.post("/api/presets", json={"name": "Pilot A", "options": {"profile": "off_brand_reachy",
                                                                        "personas": ["base", "noir"], "evil": 1}})
    assert r.json()["id"] == "pilot-a" and "evil" not in r.json()["options"]
    assert [p["id"] for p in client.get("/api/presets").json()] == ["pilot-a"]
    assert client.delete("/api/presets/pilot-a").status_code == 200
    assert client.post("/api/gesture/nope").status_code == 404
    assert client.post("/api/gesture/eye_roll").status_code == 409          # no robot in tests


def test_agent_cannot_reset_the_tour_on_its_own():
    s, rc = persona_rc()
    rc._on_tool({"tool_name": "reachy_switch_persona", "tool_call_id": "x", "parameters": {"persona": "base"}})
    assert not s.show.reset_mode and s.show.upcoming.key == "noir"     # live test P03: tour kept going
    rc.persona_command("reset")
    rc.switch_to("base", "agent")
    assert s.show.reset_mode


def test_activities_tone_and_length_shape_the_session(tmp_path):
    from beating_in_sync_app.brain.activities import switch_every_for

    assert switch_every_for("quick", 4) == 5 and switch_every_for("long", 9) == 6 and switch_every_for(None, 4) is None
    steps = [{"say": w} for w in ["hi", "I'm Sam", "bread", "yes", "no", "maybe", "ok", "sure", "fine", "bye"]]
    ev = run_offline(tmp_path, steps, personas=["noir", "diva"], duration="quick", activities=["sing", "story"],
                     tone="warm", chattiness="brief", heart_wake=False, voice_id="cgSgspJ2msm6clMCkdW9")
    cast = next(e for e in ev if e["kind"] == "cast")
    assert cast["switch_every"] == 6                                   # 240 s / 3 personalities / 13 s
    acts = [e for e in ev if e["kind"] == "turn" and e["act"] == "activity"]
    assert [a["why"] for a in acts][:2] == ["Sing a song", "Tell a story"]
    show = PersonaShow(["base", "noir"])
    from beating_in_sync_app.brain.activities import style_prompt
    show.style = style_prompt("warm", "brief", ["sing"])
    assert "warm and gentle" in show.agent_cast_prompt() and "Sing a song" in show.agent_cast_prompt()
