"""Local API protection for the bridge's :4098 API (hardened fork).

Upstream served /send, /stream, /history and /cancel with no auth and
`Access-Control-Allow-Origin: *`. /send feeds text into a Claude session, and
a text/plain POST is a CORS "simple request", so any web page open in a
browser on this Mac could likely drive Claude. Now:

  - Host must be 127.0.0.1:<port> or localhost:<port> (stops DNS rebinding).
  - Any request carrying an Origin header is refused: there are no browser
    clients, and browsers always send Origin on cross-site POST/fetch.
  - Everything except GET /health needs `Authorization: Bearer <token>`.
    The token is random, created on first start, and stored in
    ~/.aos/services/bridge/api.token (mode 0600) — readable by the operator's
    own processes (CLI, the approval MCP server), never by a web page.
  - No CORS headers at all.
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

PUBLIC_PATHS = {"/health"}


def token_path() -> Path:
    return Path(os.environ.get("AOS_BRIDGE_API_TOKEN_FILE",
                               Path.home() / ".aos" / "services" / "bridge" / "api.token"))


def load_or_create_token() -> str:
    p = token_path()
    try:
        tok = p.read_text().strip()
        if len(tok) >= 32:
            return tok
    except OSError:
        pass
    p.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(32)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok + "\n")
    os.chmod(p, 0o600)
    return tok


def read_token() -> str | None:
    try:
        return token_path().read_text().strip() or None
    except OSError:
        return None


def check_request(method: str, path: str, headers, port: int, token: str) -> tuple[int, str] | None:
    """None if allowed, else (status, reason). `headers` is case-insensitive."""
    host = (headers.get("Host") or "").lower()
    if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
        return (403, "bad host")
    if headers.get("Origin") is not None:
        return (403, "browser requests are not accepted")
    if path in PUBLIC_PATHS and method == "GET":
        return None
    auth = headers.get("Authorization") or ""
    supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, token):
        return (401, "missing or wrong token")
    return None
