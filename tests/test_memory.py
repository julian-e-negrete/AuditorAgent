"""Unit tests for ConversationMemory (Requirements 4.5, 5.1–5.5)."""
from arch_agent.memory import ConversationMemory


def test_messages_stored_in_insertion_order():
    mem = ConversationMemory()
    mem.add_message("user", "hello")
    mem.add_message("assistant", "hi there")
    mem.add_message("user", "how are you?")

    history = mem.get_history()
    assert [m.content for m in history] == ["hello", "hi there", "how are you?"]
    assert [m.role for m in history] == ["user", "assistant", "user"]


def test_get_history_respects_max_tokens():
    mem = ConversationMemory()
    # Each message content is 40 chars → token cost = 40 // 4 = 10
    for i in range(5):
        mem.add_message("user", f"message_{i:031d}")  # 40 chars each

    # max_tokens=25 → fits 2 messages (cost 10 each = 20 ≤ 25)
    history = mem.get_history(max_tokens=25)
    assert len(history) == 2
    # Should be the two most recent
    assert history[0].content.endswith("3")
    assert history[1].content.endswith("4")


def test_get_history_returns_all_when_budget_sufficient():
    mem = ConversationMemory()
    mem.add_message("user", "a")       # cost 0
    mem.add_message("assistant", "bb") # cost 0
    history = mem.get_history(max_tokens=10)
    assert len(history) == 2


def test_add_context_get_context_roundtrip():
    mem = ConversationMemory()
    mem.add_context("repo", "my-repo")
    mem.add_context("version", 42)

    ctx = mem.get_context()
    assert ctx["repo"] == "my-repo"
    assert ctx["version"] == 42


def test_clear_removes_messages_and_context():
    mem = ConversationMemory()
    mem.add_message("user", "hello")
    mem.add_context("key", "value")

    mem.clear()

    assert mem.get_history() == []
    assert mem.get_context() == {}


def test_separate_instances_do_not_share_state():
    mem1 = ConversationMemory()
    mem2 = ConversationMemory()

    mem1.add_message("user", "from mem1")
    mem1.add_context("owner", "mem1")

    assert mem2.get_history() == []
    assert mem2.get_context() == {}
