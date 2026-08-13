import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.counter_handler import CounterHandler
from twitchbot_runtime.reaction_engine import ReactionEngine


def _engine(counter_handler, stream_category_provider=None):
    return ReactionEngine(
        send_chat=lambda broadcaster_id, message: None,
        overlay_dispatch=lambda action: None,
        create_clip=lambda: "",
        counter_handler=counter_handler,
        moderation_handler=lambda action, payload: None,
        streampet_handler=lambda payload: None,
        stream_category_provider=stream_category_provider,
    )


def test_counter_resolves_args_in_amount(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle)
    engine.execute(
        [{"type": "counter", "action": "increment", "name": "deaths", "amount": "{args[1]}"}],
        context={"args": ["+", "5"]},
    )

    assert handler._resolve({"name": "deaths"}).value == 5


def test_counter_stream_category_when_dependent(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle, stream_category_provider=lambda: "Minecraft")
    engine.execute(
        [
            {
                "type": "counter",
                "action": "increment",
                "name": "deaths",
                "amount": "{args[1]}",
                "category_dependent": True,
            }
        ],
        context={"args": ["+", "5"]},
    )

    counter = handler._resolve({"name": "deaths", "category": "Minecraft"})
    assert counter is not None
    assert counter.value == 5


def test_counter_static_category_when_not_dependent(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle, stream_category_provider=lambda: "Minecraft")
    engine.execute(
        [
            {
                "type": "counter",
                "action": "increment",
                "name": "deaths",
                "amount": "3",
                "category_dependent": False,
                "category": "bosses",
            }
        ],
        context={"args": []},
    )

    assert handler._resolve({"name": "deaths", "category": "bosses"}).value == 3
    assert handler._resolve({"name": "deaths", "category": "Minecraft"}) is None


def test_counter_stream_category_empty_falls_back_to_default(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle, stream_category_provider=lambda: "")
    engine.execute(
        [{"type": "counter", "action": "increment", "name": "deaths", "category_dependent": True}],
        context={"args": []},
    )

    assert handler._resolve({"name": "deaths", "category": "default"}).value == 1


def test_counter_subcounter_name_resolves_placeholder(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle)
    engine.execute(
        [
            {
                "type": "counter",
                "action": "add_subcounter",
                "name": "bosses",
                "subcounter_name": "{args[1]}",
            }
        ],
        context={"args": ["add", "boss1"]},
    )

    counter = handler._resolve({"name": "bosses"})
    assert "boss1" in counter.subcounters


def test_counter_default_category_when_missing(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    engine = _engine(handler.handle)
    engine.execute(
        [{"type": "counter", "action": "increment", "name": "deaths"}],
        context={"args": []},
    )

    assert handler._resolve({"name": "deaths", "category": "default"}).value == 1
