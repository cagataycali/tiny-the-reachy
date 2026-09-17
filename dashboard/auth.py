"""🔐 Who may move Reachy.

reachy.cagatay.my is a PUBLIC tunnel and /api/control/* moves a robot on the owner's desk. Reading is free,
moving is gated. Three keys open the gate, checked in this order (`who()` names the one that did):

  1. "token"    Authorization: Bearer <REACHY_TOKEN>  (or ?token=) — the owner's machine key, same
                pattern as fomo's FOMO_TOKEN; also what the CLI/tools on the robot use.
  2. "passkey"  a WebAuthn session cookie minted by /api/auth/login/complete — leaf's pattern
                (py_webauthn, JSON credential store, TOFU first enrol, REACHY_REG_TOKEN afterwards).
  3. "loopback" 127.0.0.1 / ::1 with a loopback Host header and no foreign Origin — ONLY while
                neither REACHY_TOKEN nor REACHY_RP_ID is configured (bare `python -m dashboard.server`
                on a laptop). The moment either is set, loopback is just another peer.
                Host + Origin are checked because "loopback peer" ≠ "the operator": the operator's
                browser is a loopback peer for any page it loads (DNS rebinding / CSRF —
                strands-labs/robots#3695 review).

Fail CLOSED: with a token or RP_ID configured, an unauthenticated POST /api/control/* is 401.

Config (env):
  REACHY_TOKEN        owner bearer token (recommended on any deployment)
  REACHY_RP_ID        WebAuthn Relying-Party ID = the domain ("reachy.cagatay.my"); unset ⇒ passkeys off
  REACHY_ORIGIN       expected origin(s), comma-separated (default https://<RP_ID>)
  REACHY_REG_TOKEN    secret needed to enrol a passkey once one exists
  REACHY_AUTH_STORE   credentials JSON (default ~/.reachy-auth/credentials.json)
  REACHY_SESSION_TTL  seconds (default 43200)
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

try:  # py_webauthn is optional at import time so the read-only server runs without it
    from webauthn import (
        base64url_to_bytes,
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    HAVE_WEBAUTHN = True
except Exception:  # noqa: BLE001
    HAVE_WEBAUTHN = False


class Config:
    """Read the environment once; tests call `configure()` to re-read after monkeypatching."""

    def __init__(self) -> None:
        self.token: Optional[str] = os.getenv("REACHY_TOKEN", "").strip() or None
        self.rp_id: Optional[str] = os.getenv("REACHY_RP_ID", "").strip() or None
        self.rp_name: str = os.getenv("REACHY_RP_NAME", "REACHY").strip() or "REACHY"
        origin_env = os.getenv("REACHY_ORIGIN", "").strip()
        if origin_env:
            self.origins: List[str] = [o.strip() for o in origin_env.split(",") if o.strip()]
        elif self.rp_id:
            self.origins = [f"https://{self.rp_id}"]
        else:
            self.origins = []
        self.reg_token: Optional[str] = os.getenv("REACHY_REG_TOKEN", "").strip() or None
        self.session_ttl: int = int(os.getenv("REACHY_SESSION_TTL", "43200"))
        self.store_path = Path(os.getenv("REACHY_AUTH_STORE", str(Path.home() / ".reachy-auth" / "credentials.json")))
        self.sessions_path = Path(os.getenv("REACHY_SESSION_STORE", str(self.store_path.with_name("sessions.json"))))
        self.passkeys_enabled: bool = bool(self.rp_id) and HAVE_WEBAUTHN
        # loopback may control only in the bare-laptop case
        self.loopback_controls: bool = self.token is None and self.rp_id is None
        self.secure_cookies: bool = any(o.startswith("https://") for o in self.origins)

    @property
    def open(self) -> bool:
        """True when NOTHING gates control (dev). The UI shows a banner in this state."""
        return self.loopback_controls


CFG = Config()


def configure() -> Config:
    """Re-read env (tests). Also drops in-memory sessions/challenges."""
    global CFG
    CFG = Config()
    with _LOCK:
        _SESSIONS.clear()
        _SESSIONS.update(_load_sessions())
        _CHALLENGES.clear()
    return CFG


SESSION_COOKIE = "reachy_session"
CHALLENGE_COOKIE = "reachy_chal"
CHALLENGE_TTL = 300
USER_ID = b"reachy-owner-000000000000000000000"[:32].ljust(32, b"\0")
USER_NAME = os.getenv("REACHY_USER_NAME", "owner").strip() or "owner"

_LOCK = threading.Lock()
_CHALLENGES: Dict[str, tuple] = {}


def _now() -> float:
    return time.time()


# ── persistence ──────────────────────────────────────────────────────────────
def _load_sessions() -> Dict[str, float]:
    try:
        if CFG.sessions_path.exists():
            return {str(k): float(v) for k, v in json.loads(CFG.sessions_path.read_text()).items()}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_sessions(sessions: Dict[str, float]) -> None:
    try:
        CFG.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = CFG.sessions_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sessions))
        tmp.replace(CFG.sessions_path)
        os.chmod(CFG.sessions_path, 0o600)
    except Exception:  # noqa: BLE001
        pass


_SESSIONS: Dict[str, float] = _load_sessions()


def _gc() -> None:
    now = _now()
    for k in [k for k, exp in _SESSIONS.items() if exp < now]:
        _SESSIONS.pop(k, None)
    for k in [k for k, (_, exp) in _CHALLENGES.items() if exp < now]:
        _CHALLENGES.pop(k, None)


def _load_store() -> List[Dict[str, Any]]:
    try:
        if CFG.store_path.exists():
            return json.loads(CFG.store_path.read_text()).get("credentials", [])
    except Exception:  # noqa: BLE001
        pass
    return []


def _save_store(creds: List[Dict[str, Any]]) -> None:
    CFG.store_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = CFG.store_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"credentials": creds}, indent=2))
    tmp.replace(CFG.store_path)
    try:
        os.chmod(CFG.store_path, 0o600)
    except Exception:  # noqa: BLE001
        pass


def has_credentials() -> bool:
    return len(_load_store()) > 0


# ── sessions ─────────────────────────────────────────────────────────────────
def new_session() -> str:
    sid = secrets.token_urlsafe(32)
    with _LOCK:
        _SESSIONS[sid] = _now() + CFG.session_ttl
        _gc()
        _save_sessions(_SESSIONS)
    return sid


def _valid_session(request: Request) -> bool:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return False
    with _LOCK:
        exp = _SESSIONS.get(sid)
        if exp and exp > _now():
            return True
        if _SESSIONS.pop(sid, None) is not None:
            _save_sessions(_SESSIONS)
    return False


def _set_session_cookie(resp: Response, sid: str) -> None:
    resp.set_cookie(SESSION_COOKIE, sid, max_age=CFG.session_ttl, httponly=True,
                    samesite="lax", secure=CFG.secure_cookies, path="/")


def _stash_challenge(resp: Response, challenge: bytes) -> None:
    cid = secrets.token_urlsafe(24)
    with _LOCK:
        _CHALLENGES[cid] = (challenge, _now() + CHALLENGE_TTL)
        _gc()
    resp.set_cookie(CHALLENGE_COOKIE, cid, max_age=CHALLENGE_TTL, httponly=True,
                    samesite="lax", secure=CFG.secure_cookies, path="/")


def _pop_challenge(request: Request) -> Optional[bytes]:
    cid = request.cookies.get(CHALLENGE_COOKIE)
    if not cid:
        return None
    with _LOCK:
        entry = _CHALLENGES.pop(cid, None)
    if not entry:
        return None
    challenge, exp = entry
    return challenge if exp > _now() else None


# ── the gate ─────────────────────────────────────────────────────────────────
LOOPBACK_READS = os.getenv("REACHY_LOOPBACK_READS", "1") != "0"   # see loopback_read()
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _host_is_loopback(host: str) -> bool:
    h = host.strip().lower()
    if h.startswith("["):                         # [::1]:8097
        h = h.split("]")[0] + "]"
    else:
        h = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    return h in _LOOPBACK_HOSTS


def _origin_is_self(headers) -> bool:
    origin = headers.get("origin")
    if origin is None:
        return True                                # curl / same-origin GET
    if origin == "null":
        return False
    host = headers.get("host", "")
    try:
        o_host = origin.split("://", 1)[1].split("/", 1)[0]
    except IndexError:
        return False
    return o_host.lower() == host.lower()


def _bearer(request: Request) -> Optional[str]:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip() or None
    return request.query_params.get("token") or None


def who(request: Request) -> Optional[str]:
    """Which key opened the gate for this request, or None. Pure read — never raises."""
    tok = _bearer(request)
    if CFG.token and tok and hmac.compare_digest(tok, CFG.token):
        return "token"
    if CFG.passkeys_enabled and _valid_session(request):
        return "passkey"
    if CFG.loopback_controls and request.client and request.client.host in ("127.0.0.1", "::1"):
        if _host_is_loopback(request.headers.get("host", "")) and _origin_is_self(request.headers):
            return "loopback"
    return None


def loopback_read(request: Request) -> bool:
    """Documented allowance for READS from the robot itself (REACHY_LOOPBACK_READS=0 disables).

    The personas' `tools/reachy_camera.py` fetches `/api/snapshot.jpg` from 127.0.0.1:8097 without a key.
    cloudflared ALSO connects from 127.0.0.1, so loopback alone proves nothing: tunnel requests carry the public
    Host (reachy.cagatay.my) and a `cf-connecting-ip` header — both are refused here. Never grants writes.
    """
    if not LOOPBACK_READS or request.method != "GET":
        return False
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        return False
    if "cf-connecting-ip" in request.headers or "cf-ray" in request.headers:
        return False
    return _host_is_loopback(request.headers.get("host", ""))


def who_read(request: Request) -> Optional[str]:
    """Gate for reads: any control key, or the loopback read allowance."""
    return who(request) or ("loopback-read" if loopback_read(request) else None)


# Writes the personas on the robot may do without a key — ONLY the face-tracking toggle/hold. Same proof as
# loopback_read (client 127.0.0.1, loopback Host, no Cloudflare headers), listed explicitly so nothing else
# under /api/* ever inherits it. REACHY_LOOPBACK_READS=0 switches this off as well.
LOOPBACK_WRITE_PATHS = {"/api/tracking", "/api/tracking/hold", "/api/doa"}


def loopback_write(request: Request) -> bool:
    if request.url.path not in LOOPBACK_WRITE_PATHS or request.method not in ("POST", "PUT"):
        return False
    if not LOOPBACK_READS or not request.client or request.client.host not in ("127.0.0.1", "::1"):
        return False
    if "cf-connecting-ip" in request.headers or "cf-ray" in request.headers:
        return False
    return _host_is_loopback(request.headers.get("host", ""))


def who_write(request: Request) -> Optional[str]:
    """Gate for the loopback-writable routes: any control key, or the loopback write allowance."""
    return who(request) or ("loopback-write" if loopback_write(request) else None)


def require_read(request: Request) -> str:
    v = who_read(request)
    if not v:
        raise HTTPException(401, {"error": "login required", "login": "/api/auth/status",
                                  "how": "passkey session, Authorization: Bearer <REACHY_TOKEN> or ?token="})
    return v


def require(request: Request) -> str:
    v = who(request)
    if not v:
        raise HTTPException(401, {"error": "control requires auth", "login": "/api/auth/status",
                                  "how": "Authorization: Bearer <REACHY_TOKEN> or a passkey session"})
    return v


def who_ws(headers, client_host: Optional[str], cookies: Dict[str, str], query_token: Optional[str]) -> Optional[str]:
    """Same gate for a WebSocket handshake (no Request object)."""
    tok = None
    h = headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        tok = h[7:].strip() or None
    tok = tok or query_token
    if CFG.token and tok and hmac.compare_digest(tok, CFG.token):
        return "token"
    sid = cookies.get(SESSION_COOKIE)
    if CFG.passkeys_enabled and sid:
        with _LOCK:
            exp = _SESSIONS.get(sid)
        if exp and exp > _now():
            return "passkey"
    if CFG.loopback_controls and client_host in ("127.0.0.1", "::1"):
        if _host_is_loopback(headers.get("host", "")) and _origin_is_self(headers):
            return "loopback"
    return None


# ── /api/auth router ─────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/auth")


@router.get("/status")
async def status(request: Request):
    return {
        "who": who(request),
        "authenticated": who(request) is not None,
        "open": CFG.open,
        "token_configured": CFG.token is not None,
        "passkeys": CFG.passkeys_enabled,
        "rp_id": CFG.rp_id,
        "has_credentials": has_credentials() if CFG.passkeys_enabled else False,
        "registration_open": CFG.passkeys_enabled and ((not has_credentials()) or (CFG.reg_token is not None)),
    }


@router.post("/logout")
async def logout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        with _LOCK:
            _SESSIONS.pop(sid, None)
            _save_sessions(_SESSIONS)
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


def _passkeys_off():
    return JSONResponse({"status": "error", "message": "passkeys disabled (set REACHY_RP_ID)"}, status_code=400)


def _expected_origin():
    return CFG.origins if len(CFG.origins) > 1 else CFG.origins[0]


@router.post("/register/begin")
async def register_begin(request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        pass
    token = (body or {}).get("token", "")
    creds = _load_store()
    if who(request) in ("token", "passkey"):
        pass                                        # owner adds another device
    elif CFG.reg_token is not None:
        if not secrets.compare_digest(str(token).encode(), CFG.reg_token.encode()):
            return JSONResponse({"status": "error", "message": "invalid enrollment token"}, status_code=403)
    elif creds:
        return JSONResponse({"status": "error",
                             "message": "enrollment closed (a passkey exists; set REACHY_REG_TOKEN to add more)"},
                            status_code=403)
    exclude = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in creds]
    opts = generate_registration_options(
        rp_id=CFG.rp_id, rp_name=CFG.rp_name, user_id=USER_ID, user_name=USER_NAME,
        user_display_name=USER_NAME, exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED),
    )
    resp = Response(content=options_to_json(opts), media_type="application/json")
    _stash_challenge(resp, opts.challenge)
    return resp


@router.post("/register/complete")
async def register_complete(request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    challenge = _pop_challenge(request)
    if not challenge:
        return JSONResponse({"status": "error", "message": "no active challenge"}, status_code=400)
    body = await request.body()
    label = "passkey"
    try:
        parsed = json.loads(body)
        label = parsed.get("label") or parsed.get("authenticatorAttachment") or "passkey"
    except Exception:  # noqa: BLE001
        pass
    try:
        v = verify_registration_response(credential=body.decode("utf-8"), expected_challenge=challenge,
                                         expected_rp_id=CFG.rp_id, expected_origin=_expected_origin())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": f"verification failed: {e}"}, status_code=400)
    creds = _load_store()
    new_id = bytes_to_base64url(v.credential_id)
    creds = [c for c in creds if c["id"] != new_id]
    creds.append({"id": new_id, "public_key": bytes_to_base64url(v.credential_public_key),
                  "sign_count": v.sign_count, "label": str(label)[:64],
                  "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    _save_store(creds)
    resp = JSONResponse({"status": "ok", "credential_id": new_id})
    _set_session_cookie(resp, new_session())
    resp.delete_cookie(CHALLENGE_COOKIE, path="/")
    return resp


@router.post("/login/begin")
async def login_begin(request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    creds = _load_store()
    allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in creds]
    opts = generate_authentication_options(rp_id=CFG.rp_id, allow_credentials=allow or None,
                                           user_verification=UserVerificationRequirement.PREFERRED)
    resp = Response(content=options_to_json(opts), media_type="application/json")
    _stash_challenge(resp, opts.challenge)
    return resp


@router.post("/login/complete")
async def login_complete(request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    challenge = _pop_challenge(request)
    if not challenge:
        return JSONResponse({"status": "error", "message": "no active challenge"}, status_code=400)
    body = await request.body()
    try:
        parsed = json.loads(body)
        raw_id = parsed.get("id") or parsed.get("rawId")
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": "malformed assertion"}, status_code=400)
    creds = _load_store()
    match = next((c for c in creds if c["id"] == raw_id), None)
    if not match:
        return JSONResponse({"status": "error", "message": "unknown credential"}, status_code=400)
    try:
        v = verify_authentication_response(
            credential=body.decode("utf-8"), expected_challenge=challenge, expected_rp_id=CFG.rp_id,
            expected_origin=_expected_origin(), credential_public_key=base64url_to_bytes(match["public_key"]),
            credential_current_sign_count=int(match.get("sign_count", 0)))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": f"verification failed: {e}"}, status_code=400)
    match["sign_count"] = v.new_sign_count
    _save_store(creds)
    resp = JSONResponse({"status": "ok"})
    _set_session_cookie(resp, new_session())
    resp.delete_cookie(CHALLENGE_COOKIE, path="/")
    return resp


@router.get("/credentials")
async def list_credentials(request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    if who(request) is None:
        return JSONResponse({"status": "error", "message": "authentication required"}, status_code=401)
    out = [{"id": c["id"], "label": c.get("label", "passkey"), "created": c.get("created"),
            "sign_count": int(c.get("sign_count", 0))} for c in _load_store()]
    return {"status": "ok", "credentials": out, "count": len(out)}


@router.delete("/credentials/{cid}")
async def delete_credential(cid: str, request: Request):
    if not CFG.passkeys_enabled:
        return _passkeys_off()
    if who(request) is None:
        return JSONResponse({"status": "error", "message": "authentication required"}, status_code=401)
    creds = _load_store()
    if not any(c["id"] == cid for c in creds):
        return JSONResponse({"status": "error", "message": "unknown credential"}, status_code=404)
    if len(creds) <= 1 and CFG.token is None:
        return JSONResponse({"status": "error", "message": "cannot remove the last passkey (no REACHY_TOKEN fallback)"},
                            status_code=409)
    remaining = [c for c in creds if c["id"] != cid]
    _save_store(remaining)
    return {"status": "ok", "count": len(remaining)}
