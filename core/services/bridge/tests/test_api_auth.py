"""Hardened fork: the bridge's :4098 API refuses browsers, foreign Host
headers and token-less callers (api_auth.py)."""
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api_auth  # noqa: E402

TOKEN = "t" * 43
PORT = 4098


class _H(dict):
    """Case-insensitive enough for these tests (aiohttp's CIMultiDict is)."""
    def get(self, k, d=None):
        for key, v in self.items():
            if key.lower() == k.lower():
                return v
        return d


def _check(method="POST", path="/send", **h):
    headers = _H({"Host": f"127.0.0.1:{PORT}", **h})
    return api_auth.check_request(method, path, headers, PORT, TOKEN)


def test_token_holder_allowed():
    assert _check(Authorization=f"Bearer {TOKEN}") is None
    assert _check(Host=f"localhost:{PORT}", Authorization=f"bearer {TOKEN}") is None


def test_no_or_wrong_token_refused():
    assert _check()[0] == 401
    assert _check(Authorization="Bearer nope")[0] == 401
    assert _check("GET", "/history")[0] == 401
    assert _check("GET", "/stream")[0] == 401


def test_browser_request_refused_even_with_token():
    assert _check(Origin="https://evil.example", Authorization=f"Bearer {TOKEN}")[0] == 403
    assert _check(Origin="null")[0] == 403


def test_dns_rebinding_host_refused():
    assert _check(Host=f"evil.example:{PORT}", Authorization=f"Bearer {TOKEN}")[0] == 403
    assert _check(Host="127.0.0.1", Authorization=f"Bearer {TOKEN}")[0] == 403


def test_health_is_public_but_still_host_and_origin_checked():
    assert _check("GET", "/health") is None
    assert _check("GET", "/health", Origin="https://evil.example")[0] == 403
    assert _check("POST", "/health")[0] == 401


def test_token_file_created_private_and_reused(tmp_path, monkeypatch):
    f = tmp_path / "api.token"
    monkeypatch.setenv("AOS_BRIDGE_API_TOKEN_FILE", str(f))
    t1 = api_auth.load_or_create_token()
    assert len(t1) >= 32
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    assert api_auth.load_or_create_token() == t1
    assert api_auth.read_token() == t1
