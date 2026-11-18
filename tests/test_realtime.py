import random
import types

from beating_in_sync_app.brain.director import Director
from beating_in_sync_app.brain.user_model import UserModel
from beating_in_sync_app.config import Config
from beating_in_sync_app.realtime import RealtimeConversation
from beating_in_sync_app.signals import SignalHub


class FakeLog:
    def __init__(self):
        self.events = []

    def event(self, kind, t, **data):
        self.events.append((kind, data))


def fake_session(no_tease=False, stage=4):
    cfg = Config()
    s = types.SimpleNamespace(cfg=cfg, stage=stage, user=UserModel(no_tease=no_tease),
                              director=Director(cfg, random.Random(0)), hub=SignalHub(), log=FakeLog(),
                              clock=types.SimpleNamespace(now=lambda: 1.0), sim_heart=None, transcript=[])
    s.body = types.SimpleNamespace(played=[], play=lambda name, loop=False: s.body.played.append(name),
                                   dance=lambda **k: s.body.played.append("dance"))
    return s


def make(session):
    rc = RealtimeConversation.__new__(RealtimeConversation)
    rc.s, rc.sent, rc.last_mode, rc.last_note = session, [], None, ""
    rc.send = rc.sent.append
    return rc


def test_agent_tease_refused_for_opted_out_participant():
    s = fake_session(no_tease=True)
    rc = make(s)
    rc._on_tool({"tool_name": "express", "tool_call_id": "1", "parameters": {"mode": "teasing"}})
    assert s.body.played == ["curious"]
    assert "not allowed" in rc.sent[0]["result"] and rc.sent[0]["tool_call_id"] == "1"


def test_agent_moves_count_as_stage4_persona_moves():
    s = fake_session()
    rc = make(s)
    for m in ("teasing", "flirty", "scolding"):
        rc._on_tool({"tool_name": "express", "tool_call_id": m, "parameters": {"mode": m}})
    assert s.director.stage4_moves  # used to end stage 4 in the live conversation
    assert s.body.played[0] == "teasing"
