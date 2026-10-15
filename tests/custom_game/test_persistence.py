"""Storage boundaries and isolation for completed dialogue and unsent text."""

import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tuxemon.custom_game.persistence import (
    SCHEMA,
    ConversationStore,
    NPCMemory,
    decode,
    profile_name,
)

IDS = ("professor", "quartermaster")


def memories():
    return {
        "professor": NPCMemory(
            "Lumi, not Luma; 2 Vorpax", 4, (("I am Cedar.", "Hello, Cedar."),)
        ),
        "quartermaster": NPCMemory("Keep my crystal.", 7),
    }


def document():
    return {
        "schema": SCHEMA,
        "version": 1,
        "profile": "cedar",
        "npcs": {
            key: {
                "draft": value.draft,
                "method": value.method,
                "history": [list(turn) for turn in value.history],
            }
            for key, value in memories().items()
        },
    }


def test_exact_roundtrip_preserves_npc_identity_after_reordering(tmp_path):
    first = ConversationStore(tmp_path, "cedar", IDS)
    assert first.load() == dict.fromkeys(IDS, NPCMemory())
    assert first.save(memories())
    first.close()
    second = ConversationStore(tmp_path, "cedar", tuple(reversed(IDS)))
    assert second.load() == memories()
    if os.name == "posix":
        assert stat.S_IMODE(second.path.stat().st_mode) == 0o600
    second.close()


def test_named_profiles_never_share_drafts_or_history(tmp_path):
    first = ConversationStore(tmp_path, "cedar", IDS)
    second = ConversationStore(tmp_path, "lumi", IDS)
    assert first.save(memories())
    empty = second.load()
    assert empty == dict.fromkeys(IDS, NPCMemory())
    assert second.save(empty)
    assert first.load() == memories()
    first.close()
    second.close()


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b'{"version":', id="truncated"),
        pytest.param(b"\xff", id="invalid-utf8"),
        pytest.param(b"[]", id="wrong-root"),
        pytest.param(b'{"version":2,"version":1}', id="duplicate-field"),
        pytest.param(b"[" * 2000, id="excessive-nesting"),
        pytest.param(b"x" * (2 * 1024 * 1024 + 1), id="oversized"),
    ],
)
def test_damaged_file_is_preserved_and_never_overwritten(tmp_path, raw):
    path = tmp_path / "cedar.json"
    path.write_bytes(raw)
    store = ConversationStore(tmp_path, "cedar", IDS)
    assert store.load() == dict.fromkeys(IDS, NPCMemory())
    assert not store.writable
    assert "retained" in store.notice
    assert not store.save(memories())
    assert path.read_bytes() == raw
    store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("version", 2, id="future-version"),
        pytest.param("version", True, id="boolean-version"),
        pytest.param("profile", "someone-else", id="profile-mismatch"),
        pytest.param("schema", "other-game", id="scenario-mismatch"),
        pytest.param("npcs", {}, id="missing-npcs"),
    ],
)
def test_unsupported_identity_or_version_preserves_source(
    tmp_path, field, value
):
    data = document()
    data[field] = value
    raw = json.dumps(data).encode()
    path = tmp_path / "cedar.json"
    path.write_bytes(raw)
    store = ConversationStore(tmp_path, "cedar", IDS)
    assert store.load() == dict.fromkeys(IDS, NPCMemory())
    assert not store.save(memories())
    assert path.read_bytes() == raw
    store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("method", 9, id="unknown-method"),
        pytest.param("method", True, id="boolean-method"),
        pytest.param("draft", "a" * 97, id="long-draft"),
        pytest.param("draft", "café", id="non-ascii-draft"),
        pytest.param("history", [["hello", ""]], id="empty-reply"),
        pytest.param("history", [["hello", "a" * 8193]], id="long-reply"),
        pytest.param(
            "history", [["hello", "reply"]] * 21, id="too-many-turns"
        ),
        pytest.param("history", [[1, "reply"]], id="wrong-turn-type"),
    ],
)
def test_invalid_memory_is_rejected(field, value):
    data = document()
    data["npcs"]["professor"][field] = value
    with pytest.raises(ValueError):
        decode(data, "cedar", IDS)


def test_pending_request_fields_are_not_accepted():
    data = document()
    data["pending"] = {"text": "send automatically"}
    with pytest.raises(ValueError):
        decode(data, "cedar", IDS)


def test_failed_atomic_replace_keeps_original_and_cleans_own_temp(
    tmp_path, monkeypatch
):
    store = ConversationStore(tmp_path, "cedar", IDS)
    assert store.save(memories())
    before = store.path.read_bytes()
    changed = memories()
    changed["professor"] = replace(
        changed["professor"], draft="Unfinished new draft"
    )

    def fail(*args):
        raise OSError("disk failure fixture")

    monkeypatch.setattr(os, "replace", fail)
    assert not store.save(changed)
    assert not store.writable
    assert store.path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []
    store.close()


def test_second_store_cannot_overwrite_profile(tmp_path):
    first = ConversationStore(tmp_path, "cedar", IDS)
    assert first.save(memories())
    second = ConversationStore(tmp_path, "cedar", IDS)
    assert not second.writable
    assert not second.save(dict.fromkeys(IDS, NPCMemory()))
    assert first.load() == memories()
    second.close()
    first.close()
    reopened = ConversationStore(tmp_path, "cedar", IDS)
    assert reopened.writable
    assert reopened.load() == memories()
    reopened.close()


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("../other", id="traversal"),
        pytest.param("/tmp/profile", id="absolute"),
        pytest.param("", id="empty-name"),
        pytest.param("A", id="uppercase"),
        pytest.param("a" * 33, id="long-name"),
    ],
)
def test_profile_names_cannot_escape_storage(name):
    with pytest.raises(ValueError):
        profile_name(name)


def test_campaign_load_detaches_custom_history_and_pending_request(
    monkeypatch,
):
    from tuxemon.save_system.save_state import SaveData
    from tuxemon.session import Session

    events = []
    session = Session()
    client = SimpleNamespace(
        custom_scenario=SimpleNamespace(
            close_persistence=lambda: events.append("closed")
        ),
        custom_conversation_store=object(),
        shop_manager=SimpleNamespace(load_from_dict=lambda value: None),
        npc_manager=SimpleNamespace(
            load_persistent_npc_states=lambda *args: None
        ),
    )
    session.set_client(client)
    session._player = SimpleNamespace(
        set_state=lambda *args: events.append("player-loaded")
    )
    session._world = SimpleNamespace(set_state=lambda *args: None)
    monkeypatch.setattr(session, "set_state", lambda *args: None)
    session.load_state(SaveData())
    assert events == ["closed", "player-loaded"]
    assert not hasattr(client, "custom_scenario")
    assert not hasattr(client, "custom_conversation_store")


def test_other_process_cannot_write_locked_profile(tmp_path):
    store = ConversationStore(tmp_path, "cedar", IDS)
    assert store.save(memories())
    before = store.path.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; "
            "from tuxemon.custom_game.persistence import ConversationStore; "
            "s=ConversationStore(Path(sys.argv[1]), 'cedar', ('professor', 'quartermaster')); "
            "assert not s.writable; assert not s.save({}); s.close()",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert store.path.read_bytes() == before
    store.close()


def test_scenario_restart_restores_by_npc_id_without_replaying_request(
    tmp_path, monkeypatch
):
    from copy import deepcopy

    from tuxemon.custom_game import runtime

    world = runtime.load_world()
    ids = tuple(npc["id"] for npc in world["npcs"])
    assert len(set(ids)) == len(ids)
    monkeypatch.setattr(runtime.Scenario, "sync", lambda self: None)
    first_store = ConversationStore(tmp_path, "cedar", ids)
    first = runtime.Scenario(
        SimpleNamespace(custom_conversation_store=first_store)
    )
    first.select_npc(0)
    first.change_method(4)
    first.set_draft("My name is Cedar.")
    first.begin_request("reply")
    token = first.pending
    assert first.accept_result(token, text="Hello, Cedar.")
    first.set_draft("Lumi, not Luma; 2 Vorpax")
    first.select_npc(1)
    first.change_method(7)
    first.set_draft("Keep my crystal.")
    first.begin_request("reply")
    pending = first.pending
    assert pending is not None
    first.close_persistence()

    reordered = deepcopy(world)
    reordered["npcs"].reverse()
    monkeypatch.setattr(runtime, "load_world", lambda: reordered)
    second_store = ConversationStore(tmp_path, "cedar", tuple(reversed(ids)))
    second = runtime.Scenario(
        SimpleNamespace(custom_conversation_store=second_store)
    )
    second.select_npc(4)
    assert second.scene["id"] == "professor"
    assert second.draft == "Lumi, not Luma; 2 Vorpax"
    assert second.method == 4
    assert second.conversations[4] == [("My name is Cedar.", "Hello, Cedar.")]
    second.select_npc(3)
    assert second.scene["id"] == "quartermaster"
    assert second.draft == "Keep my crystal." and second.method == 7
    assert not second.conversations.get(3)
    assert (
        second.pending is None
        and second.worker is None
        and second.request is None
    )
    assert second.phase == "editor" and not second.keyboard
    assert not second.accept_result(
        pending, text="Late reply must be ignored."
    )
    assert not second.conversations.get(3)
    second.close_persistence()


def test_reset_with_damaged_save_clears_session_without_overwriting_evidence(
    tmp_path, monkeypatch
):
    from tuxemon.custom_game import runtime

    ids = tuple(npc["id"] for npc in runtime.load_world()["npcs"])
    path = tmp_path / "cedar.json"
    raw = b'{"version":'
    path.write_bytes(raw)
    store = ConversationStore(tmp_path, "cedar", ids)
    scenario = runtime.Scenario(
        SimpleNamespace(custom_conversation_store=store)
    )
    monkeypatch.setattr(scenario, "reset_quest_state", lambda: None)
    scenario.set_draft("Temporary only")
    scenario.reset_story()
    assert not scenario.draft and not scenario.conversations
    assert "Saved file retained" in scenario.message
    assert not store.writable and path.read_bytes() == raw
    scenario.close_persistence()
