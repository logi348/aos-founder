"""Hardened fork: the bridge rejects every Telegram update that isn't from
the operator's own account in the authorized chat — text, voice, media,
commands, callbacks and any future update type — via one gate handler that
runs before all others (group -1).

Same conventions as test_voice_ramble_route.py: bridge dir on sys.path, fake
update objects, no network.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telegram_channel as tc  # noqa: E402
from telegram.ext import ApplicationHandlerStop, TypeHandler  # noqa: E402

OWNER = 999          # private chat: chat id == the operator's user id
STRANGER = 4242
FORUM = -100123


class _Chat:
    def __init__(self, cid):
        self.id = cid


class _User:
    def __init__(self, uid, is_bot=False):
        self.id = uid
        self.is_bot = is_bot


class _Query:
    def __init__(self, message):
        self.message = message
        self.answered = []
        self.data = "x"

    async def answer(self, text=None, **kw):
        self.answered.append(text)


class _Msg:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.chat = _Chat(chat_id)


class _Update:
    def __init__(self, chat_id, user_id, kind="text", is_bot=False):
        self.effective_chat = _Chat(chat_id) if chat_id is not None else None
        self.effective_user = _User(user_id, is_bot) if user_id is not None else None
        self.message = None
        self.callback_query = None
        if kind in ("text", "voice", "photo", "command"):
            self.message = _Msg(chat_id)
        elif kind == "callback":
            self.callback_query = _Query(_Msg(chat_id) if chat_id is not None else None)


@pytest.fixture
def ch(monkeypatch, tmp_path):
    monkeypatch.setenv("AOS_BRIDGE_DB", str(tmp_path / "bridge.db"))
    return tc.TelegramChannel("token", OWNER, forum_group_id=FORUM)


def _gate(ch, update):
    """True if the gate let it through, False if it stopped it."""
    try:
        asyncio.run(ch._gate(update, None))
        return True
    except ApplicationHandlerStop:
        return False


@pytest.mark.parametrize("kind", ["text", "voice", "photo", "command", "callback"])
def test_operator_in_private_chat_passes(ch, kind):
    assert _gate(ch, _Update(OWNER, OWNER, kind))


@pytest.mark.parametrize("kind", ["text", "voice", "photo", "command", "callback"])
def test_other_chat_rejected(ch, kind):
    assert not _gate(ch, _Update(STRANGER, STRANGER, kind))


@pytest.mark.parametrize("kind", ["text", "voice", "photo", "command", "callback"])
def test_stranger_in_forum_group_rejected(ch, kind):
    """Upstream authorized every member of the forum group."""
    assert not _gate(ch, _Update(FORUM, STRANGER, kind))


def test_operator_in_forum_group_passes(ch):
    assert _gate(ch, _Update(FORUM, OWNER, "text"))


def test_stranger_writing_into_operator_chat_id_rejected(ch):
    # Can't happen in a real private chat, but the user check must hold alone.
    assert not _gate(ch, _Update(OWNER, STRANGER, "text"))


def test_updates_without_sender_or_chat_rejected(ch):
    assert not _gate(ch, _Update(OWNER, None, "text"))      # channel post
    assert not _gate(ch, _Update(None, OWNER, "callback"))  # callback with no message


def test_bots_rejected(ch):
    assert not _gate(ch, _Update(OWNER, OWNER, "text", is_bot=True))


def test_rejected_callback_is_answered_not_acted_on(ch):
    u = _Update(STRANGER, STRANGER, "callback")
    assert not _gate(ch, u)
    assert u.callback_query.answered == ["Unauthorized"]


def test_group_chat_id_needs_explicit_owner(monkeypatch, tmp_path):
    monkeypatch.setenv("AOS_BRIDGE_DB", str(tmp_path / "bridge.db"))
    group_only = tc.TelegramChannel("token", FORUM)
    assert group_only.owner_user_id is None  # logged loudly at start()
    pinned = tc.TelegramChannel("token", FORUM, owner_user_id=OWNER)
    assert _gate(pinned, _Update(FORUM, OWNER))
    assert not _gate(pinned, _Update(FORUM, STRANGER))


def test_callback_handler_tolerates_missing_message(ch):
    u = _Update(None, OWNER, "callback")
    asyncio.run(ch._handle_callback(u, None))  # must not raise
    assert u.callback_query.answered == ["Unauthorized"]


def test_gate_is_registered_first_for_every_update(ch):
    added = []

    class _App:
        def add_handler(self, handler, group=0):
            added.append((handler, group))

    ch._register_handlers(_App())
    gate, group = added[0]
    assert isinstance(gate, TypeHandler) and group == -1
    assert gate.callback == ch._gate
    assert all(g == 0 for _, g in added[1:])
