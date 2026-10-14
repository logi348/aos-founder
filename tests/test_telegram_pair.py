"""core/bin/cli/telegram-pair — only a private message carrying the one-time
code, from the @username the operator typed, can become TELEGRAM_CHAT_ID."""
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAIR = REPO / "core" / "bin" / "cli" / "telegram-pair"
_loader = importlib.machinery.SourceFileLoader("telegram_pair", str(PAIR))
_spec = importlib.util.spec_from_loader("telegram_pair", _loader)
pair = importlib.util.module_from_spec(_spec)
_loader.exec_module(pair)

CODE = "K7Q2XM"


def _upd(text=CODE, username="alex", uid=111, chat_id=None, chat_type="private", is_bot=False):
    return {"update_id": 1, "message": {
        "text": text,
        "chat": {"id": uid if chat_id is None else chat_id, "type": chat_type},
        "from": {"id": uid, "username": username, "is_bot": is_bot, "first_name": "Alex"},
    }}


def test_matching_message_accepted():
    assert pair.match_update(_upd(), CODE, "alex")
    assert pair.match_update(_upd(text=f"/start {CODE.lower()}"), CODE, "@alex".lstrip("@"))
    assert pair.match_update(_upd(username="Alex"), CODE, "alex")  # usernames are case-insensitive


def test_most_recent_stranger_is_not_taken():
    assert pair.match_update(_upd(username="mallory", uid=666), CODE, "alex") is None


def test_wrong_or_missing_code_rejected():
    assert pair.match_update(_upd(text="hello"), CODE, "alex") is None
    assert pair.match_update(_upd(text=CODE + "X"), CODE, "alex") is None


def test_group_and_bot_messages_rejected():
    assert pair.match_update(_upd(chat_type="group", chat_id=-100), CODE, "alex") is None
    assert pair.match_update(_upd(is_bot=True), CODE, "alex") is None
    assert pair.match_update(_upd(chat_id=222), CODE, "alex") is None


def test_non_message_updates_rejected():
    assert pair.match_update({"update_id": 2, "callback_query": {}}, CODE, "alex") is None


def test_refuses_without_terminal():
    r = subprocess.run([sys.executable, str(PAIR)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 3
