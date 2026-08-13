import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.counter_handler import CounterHandler


def test_create_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("create", {"name": "deaths"})

    assert result["action"] == "create"
    assert result["counter"]["name"] == "deaths"
    query = handler.handle("query", {"name": "deaths"})
    assert query["value"] == 0


def test_increment_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})

    result = handler.handle("increment", {"name": "deaths"})
    assert result["value"] == 1

    result = handler.handle("increment", {"name": "deaths", "amount": 5})
    assert result["value"] == 6


def test_decrement_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    handler.handle("increment", {"name": "deaths", "amount": 10})

    result = handler.handle("decrement", {"name": "deaths", "amount": 3})

    assert result["value"] == 7


def test_set_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})

    result = handler.handle("set", {"name": "deaths", "value": 42})

    assert result["value"] == 42


def test_reset_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    handler.handle("increment", {"name": "deaths", "amount": 5})

    result = handler.handle("reset", {"name": "deaths"})

    assert result["value"] == 0


def test_delete_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})

    result = handler.handle("delete", {"name": "deaths"})

    assert result["deleted"] is True
    # delete never auto-creates; a follow-up query returns missing_name (no
    # name resolution) — but query auto-creates, so it now reports value 0.
    query = handler.handle("query", {"name": "deaths"})
    assert query["value"] == 0
    assert handler._resolve({"name": "deaths"}) is not None


def test_increment_nonexistent_auto_creates(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {"name": "ghost"})

    assert result["value"] == 1
    assert result["action"] == "increment"
    assert handler._resolve({"name": "ghost"}) is not None


def test_delete_without_create_returns_not_found(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("delete", {"name": "ghost"})

    assert result["error"] == "counter_not_found"


def test_increment_auto_creates_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {"name": "auto"})

    assert result["value"] == 1
    assert handler._resolve({"name": "auto"}) is not None


def test_increment_coerces_string_amount(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {"name": "x", "amount": "5"})

    assert result["value"] == 5


def test_increment_unparseable_amount_falls_back_to_one(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {"name": "x", "amount": "abc"})

    assert result["value"] == 1


def test_set_coerces_string_value(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("set", {"name": "x", "value": "10"})

    assert result["value"] == 10


def test_set_unparseable_value_falls_back_to_zero(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("set", {"name": "x", "value": "abc"})

    assert result["value"] == 0


def test_query_auto_creates_empty_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("query", {"name": "fresh"})

    assert result["value"] == 0
    assert result["key"] == "fresh:default"
    assert handler._resolve({"name": "fresh"}) is not None


def test_add_subcounter_auto_creates_counter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("add_subcounter", {"name": "new", "subcounter_name": "s1"})

    assert result["subcounter"] == "s1"
    assert handler._resolve({"name": "new"}) is not None


def test_increment_preserves_int_amount(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {"name": "x", "amount": 5})

    assert result["value"] == 5


def test_missing_name_increment_returns_missing_name(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("increment", {})

    assert result["error"] == "missing_name"


def test_persistence(tmp_path):
    store = tmp_path / "counters.json"
    handler = CounterHandler(store_path=store)
    handler.handle("create", {"name": "deaths"})
    handler.handle("increment", {"name": "deaths", "amount": 3})

    reloaded = CounterHandler(store_path=store)
    query = reloaded.handle("query", {"name": "deaths"})

    assert query["value"] == 3


def test_add_subcounter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})

    result = handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    assert result["subcounter"] == "boss1"
    assert "boss1" in result["subcounters"]


def test_select_and_clear_subcounter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    selected = handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    assert selected["active_subcounter"] == "boss1"

    cleared = handler.handle("clear_active_subcounter", {"name": "bosses"})
    assert cleared["active_subcounter"] is None


def test_delete_subcounter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    result = handler.handle("delete_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    assert result["subcounter"] == "boss1"
    assert "boss1" not in result["subcounters"]


def test_replace_placeholders(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    counter = handler._resolve({"name": "deaths"})

    replaced = handler.replace_placeholders("Value: {counter:deaths:value}", counter)
    assert replaced == "Value: 0"

    handler.handle("increment", {"name": "deaths"})
    replaced = handler.replace_placeholders("Value: {counter:deaths:value}", counter)
    assert replaced == "Value: 1"


def test_unknown_action_returns_error(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")

    result = handler.handle("frobnicate", {})

    assert result["error"] == "unknown_action"


def test_increment_with_active_subcounter_increments_both(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    result = handler.handle("increment", {"name": "bosses", "amount": 2})

    assert result["value"] == 2
    assert result["subcounter_value"] == 2
    assert result["target"] == "both"
    assert result["active_subcounter"] == "boss1"


def test_decrement_with_active_subcounter_decrements_both(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("increment", {"name": "bosses", "amount": 10})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    counter = handler._resolve({"name": "bosses"})
    counter.subcounters["boss1"]["value"] = 5

    result = handler.handle("decrement", {"name": "bosses", "amount": 3})

    assert result["value"] == 7
    assert result["subcounter_value"] == 2
    assert result["target"] == "both"


def test_set_with_active_subcounter_targets_subcounter_only(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("increment", {"name": "bosses", "amount": 10})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})

    result = handler.handle("set", {"name": "bosses", "value": 99})

    assert result["value"] == 10
    assert result["subcounter_value"] == 99
    assert result["target"] == "subcounter"


def test_reset_with_active_subcounter_targets_subcounter_only(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("increment", {"name": "bosses", "amount": 10})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    counter = handler._resolve({"name": "bosses"})
    counter.subcounters["boss1"]["value"] = 5

    result = handler.handle("reset", {"name": "bosses"})

    assert result["value"] == 10
    assert result["subcounter_value"] == 0
    assert result["target"] == "subcounter"


def test_increment_without_subcounter_returns_none_subcounter_value(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})

    result = handler.handle("increment", {"name": "deaths"})

    assert result["subcounter_value"] is None
    assert result["target"] == "counter"
    assert result["active_subcounter"] is None


def test_result_shape_always_has_subcounter_fields(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})

    result = handler.handle("set", {"name": "deaths", "value": 1})

    assert result["active_subcounter"] is None
    assert result["subcounter_value"] is None
    assert result["target"] == "counter"


def test_stale_active_subcounter_falls_back_to_main_and_heals(tmp_path):
    store = tmp_path / "counters.json"
    handler = CounterHandler(store_path=store)
    handler.handle("create", {"name": "bosses"})
    counter = handler._resolve({"name": "bosses"})
    counter.active_subcounter = "ghost"

    result = handler.handle("increment", {"name": "bosses", "amount": 4})

    assert result["value"] == 4
    assert result["target"] == "counter"
    assert result["active_subcounter"] is None

    reloaded = CounterHandler(store_path=store)
    reloaded_counter = reloaded._resolve({"name": "bosses"})
    assert reloaded_counter.active_subcounter is None


def test_subcounter_label_placeholder_with_active_subcounter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    handler.handle("add_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("select_subcounter", {"name": "bosses", "subcounter_name": "boss1"})
    handler.handle("increment", {"name": "bosses", "amount": 2})
    counter = handler._resolve({"name": "bosses"})

    replaced = handler.replace_placeholders("V{counter:bosses:subcounter_label}", counter)

    assert replaced == "V (boss1: 2)"


def test_subcounter_label_placeholder_without_subcounter(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    counter = handler._resolve({"name": "deaths"})

    replaced = handler.replace_placeholders("V{counter:deaths:subcounter_label}", counter)

    assert replaced == "V"


def test_subcounter_label_placeholder_stale_no_heal(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "bosses"})
    counter = handler._resolve({"name": "bosses"})
    counter.active_subcounter = "ghost"

    replaced = handler.replace_placeholders("V{counter:bosses:subcounter_label}", counter)

    assert replaced == "V"
    assert counter.active_subcounter == "ghost"


def test_subcounter_value_placeholder_still_zero_without_active(tmp_path):
    handler = CounterHandler(store_path=tmp_path / "counters.json")
    handler.handle("create", {"name": "deaths"})
    counter = handler._resolve({"name": "deaths"})

    replaced = handler.replace_placeholders("{counter:deaths:subcounter_value}", counter)

    assert replaced == "0"
