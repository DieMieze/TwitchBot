import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.expression import C, R
from twitchbot_runtime.reaction_engine import ReactionEngine


def _engine(sent=None, overlay=None, counter=None):
    sent = sent if sent is not None else []
    overlay = overlay if overlay is not None else []
    counter = counter if counter is not None else (lambda action, payload: None)
    return ReactionEngine(
        send_chat=lambda broadcaster_id, message: sent.append((broadcaster_id, message)),
        overlay_dispatch=lambda action: overlay.append(action),
        create_clip=lambda: "",
        counter_handler=counter,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
    )


def test_evaluate_reaction_seq_executes_all_children():
    sent = []
    engine = _engine(sent=sent)
    ast = R.seq(
        R.reaction("chat_reply", message="a"),
        R.reaction("chat_reply", message="b"),
    ).to_dict()

    results = engine.execute([ast], context={"channel": "streamer"})

    assert sent == [("streamer", "a"), ("streamer", "b")]
    assert [r["type"] for r in results] == ["chat_reply", "chat_reply"]


def test_evaluate_reaction_if_true_branch():
    sent = []
    engine = _engine(sent=sent)
    ast = R.if_(
        C.leaf("follow"),
        then=R.reaction("chat_reply", message="yes"),
        else_=R.reaction("chat_reply", message="no"),
    ).to_dict()

    engine.execute([ast], context={"event_name": "event.follow", "channel": "streamer"})

    assert sent == [("streamer", "yes")]


def test_evaluate_reaction_if_false_branch():
    sent = []
    engine = _engine(sent=sent)
    ast = R.if_(
        C.leaf("follow"),
        then=R.reaction("chat_reply", message="yes"),
        else_=R.reaction("chat_reply", message="no"),
    ).to_dict()

    engine.execute([ast], context={"event_name": "event.sub", "channel": "streamer"})

    assert sent == [("streamer", "no")]


def test_evaluate_reaction_switch_match():
    sent = []
    engine = _engine(sent=sent)
    ast = R.switch(
        "{args[0]}",
        {"red": R.reaction("chat_reply", message="r"), "blue": R.reaction("chat_reply", message="b")},
        default=R.reaction("chat_reply", message="other"),
    ).to_dict()

    engine.execute([ast], context={"args": ["red"], "channel": "streamer"})

    assert sent == [("streamer", "r")]


def test_evaluate_reaction_switch_default():
    sent = []
    engine = _engine(sent=sent)
    ast = R.switch(
        "{args[0]}",
        {"red": R.reaction("chat_reply", message="r")},
        default=R.reaction("chat_reply", message="other"),
    ).to_dict()

    engine.execute([ast], context={"args": ["green"], "channel": "streamer"})

    assert sent == [("streamer", "other")]


def test_evaluate_reaction_nested_if_in_seq():
    sent = []
    engine = _engine(sent=sent)
    ast = R.seq(
        R.reaction("chat_reply", message="start"),
        R.if_(
            C.leaf("follow"),
            then=R.reaction("chat_reply", message="followed"),
        ),
    ).to_dict()

    engine.execute([ast], context={"event_name": "event.follow", "channel": "streamer"})

    assert sent == [("streamer", "start"), ("streamer", "followed")]


def test_evaluate_reaction_switch_on_counter_placeholder():
    class CounterStub:
        def resolve_placeholders(self, message):
            return message.replace("{counter:color:value}", "red")

        def __call__(self, action, payload):
            return None

    sent = []
    engine = _engine(sent=sent, counter=CounterStub())
    ast = R.switch(
        "{counter:color:value}",
        {"red": R.reaction("chat_reply", message="r")},
        default=R.reaction("chat_reply", message="other"),
    ).to_dict()

    engine.execute([ast], context={"channel": "streamer"})

    assert sent == [("streamer", "r")]


def test_execute_accepts_ast_root_and_plain_dict_mixed():
    sent = []
    overlay = []
    engine = _engine(sent=sent, overlay=overlay)
    ast = R.reaction("chat_reply", message="ast").to_dict()
    plain = {"type": "overlay_text", "text": "plain"}

    results = engine.execute([ast, plain], context={"channel": "streamer"})

    assert sent == [("streamer", "ast")]
    assert overlay == [{"action": "overlay_text", "data": {"text": "plain"}}]
    assert [r["type"] for r in results] == ["chat_reply", "overlay_text"]


def test_plain_dict_with_type_chat_reply_is_not_treated_as_ast():
    sent = []
    engine = _engine(sent=sent)
    results = engine.execute(
        [{"type": "chat_reply", "message": "hi"}],
        context={"channel": "streamer"},
    )
    assert sent == [("streamer", "hi")]
    assert results == [{"type": "chat_reply", "channel": "streamer", "message": "hi"}]


def test_if_when_compare_leaf_with_counter():
    class CounterStub:
        def resolve_placeholders(self, message):
            return message.replace("{counter:deaths:value}", "7")

        def __call__(self, action, payload):
            return None

    sent = []
    engine = _engine(sent=sent, counter=CounterStub())
    ast = R.if_(
        C.compare("{counter:deaths:value}", ">=", 5),
        then=R.reaction("chat_reply", message="many"),
        else_=R.reaction("chat_reply", message="few"),
    ).to_dict()

    engine.execute([ast], context={"channel": "streamer"})

    assert sent == [("streamer", "many")]
