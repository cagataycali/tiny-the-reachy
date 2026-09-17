"""Reachy Mini showcase dashboard — FastAPI on :8097 (behind the reachy.cagatay.my tunnel).

    /venvs/apps_venv/bin/python -m dashboard.server        # on the robot, cwd = repo root

Public READ
  GET  /api/health           liveness + auth summary
  GET  /api/state            daemon state/full (deg/mm) + motors + daemon + wifi + camera + reel, cached 150 ms
  GET  /api/emotions         the ~80 recorded moves grouped by family, + now_playing
  GET  /api/stream           MJPEG (multipart/x-mixed-replace), one capture thread shared by every viewer
  GET  /api/snapshot.jpg     latest JPEG frame
  GET  /api/log?n=           last N rows of the personas' shared agent_log (thinker/telegram/voice/dashboard)
  WS   /ws                   {type:"state"} @10 Hz, {type:"log"} new agent_log rows, {type:"event"} dashboard
                             events, {type:"agent", …} streamed Ask-Tiny turns
Gated WRITE (dashboard/auth.py — bearer REACHY_TOKEN or a passkey session; 5 POST/s per client)
  POST /api/control/look      {roll,pitch,yaw (deg), x,y,z (mm), body_yaw (deg|null), antennas?, duration}
  POST /api/control/antennas  {right,left (deg), duration?}
  POST /api/control/express   {name}
  POST /api/control/stop      {}                       stops every running move + aborts the reel
  POST /api/control/home      {}
  POST /api/control/wake | /sleep
  POST /api/control/motors    {mode: enabled|disabled|gravity_compensation}
  POST /api/control/volume    {level 0..100}
  POST /api/control/say       {text}    → local Piper (tiny-tts) + daemon play_sound, head wobbling
  POST /api/control/ask       {text}    → ONE Strands agent turn, streamed over /ws as "agent" events (429 if busy)
  POST /api/control/reel      {action: start|abort}     the scripted 60–90 s showcase
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import __version__, auth
from .robot import Robot, agent_log_tail

log = logging.getLogger("reachy.dash")
REPO = Path(__file__).resolve().parent.parent
DIST = Path(os.getenv("REACHY_DIST", str(REPO / "dashboard" / "frontend" / "dist")))
RATE_LIMIT_PER_S = int(os.getenv("REACHY_RATE_LIMIT", "5"))
WS_HZ = float(os.getenv("REACHY_WS_HZ", "15"))
ASK_TIMEOUT = float(os.getenv("REACHY_ASK_TIMEOUT", "60"))


class Ask:
    """One Strands agent turn at a time; events fan out to every WS client via app.state.bus."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.busy = False
        self.agent = None
        self.history: List[Dict[str, Any]] = []
        self.last: Optional[Dict[str, Any]] = None

    @staticmethod
    def warm() -> None:
        """Import the robot's agent stack once at startup so the first Ask isn't a 10 s cold import."""
        try:
            import sys  # noqa: PLC0415
            if str(REPO) not in sys.path:
                sys.path.insert(0, str(REPO))
            import tiny  # noqa: F401, PLC0415
            log.info("ask: tiny agent stack pre-warmed")
        except Exception as e:  # noqa: BLE001
            log.warning("ask: pre-warm failed (%s) — /api/control/ask will import lazily", e)

    def _build(self, emit):
        import sys  # noqa: PLC0415
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        import tiny  # noqa: PLC0415  — the robot's own agent factory (repo root)
        from strands import Agent  # noqa: PLC0415

        seen_tools: set = set()

        def cb(**kw: Any) -> None:
            if "data" in kw and kw["data"]:
                emit({"type": "agent", "event": "text", "text": kw["data"]})
            tu = kw.get("current_tool_use")
            if tu and tu.get("name") and tu.get("toolUseId") not in seen_tools:   # once per tool call, not per delta
                seen_tools.add(tu.get("toolUseId"))
                emit({"type": "agent", "event": "tool", "name": tu.get("name"), "id": tu.get("toolUseId"),
                      "input": str(tu.get("input", ""))[:400]})

        return Agent(model=tiny.MODEL_ID, tools=tiny.build_voice_tools(),
                     system_prompt=tiny._shell_prompt()
                     + "\n\nYou are being driven from the public web dashboard (reachy.cagatay.my) during a live "
                       "showcase. Answer in 1–3 short sentences, use one expressive move when it fits, never sleep.",
                     callback_handler=cb)

    def run(self, text: str, who: str, emit, robot: Robot) -> Dict[str, Any]:
        with self.lock:
            if self.busy:
                raise HTTPException(429, {"error": "an ask is already running"})
            self.busy = True
        started = time.time()
        emit({"type": "agent", "event": "start", "text": text, "who": who})
        robot.log("ask", text, who)

        def work() -> None:
            result: Dict[str, Any] = {"ok": False}
            try:
                agent = self._build(emit)                   # fresh agent per turn: no cross-visitor memory
                out = agent(text)
                reply = str(out)
                result = {"ok": True, "reply": reply, "seconds": round(time.time() - started, 1)}
                robot.log("ask-reply", reply[:600], "tiny")
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "error": str(e)[:400], "seconds": round(time.time() - started, 1)}
                robot.log("error", f"ask failed: {e}", "tiny")
            finally:
                self.last = {"text": text, **result, "t": time.time()}
                emit({"type": "agent", "event": "end", **result})
                self.busy = False

        t = threading.Thread(target=work, name="ask", daemon=True)
        t.start()

        def watchdog() -> None:
            t.join(ASK_TIMEOUT)
            if t.is_alive():
                emit({"type": "agent", "event": "timeout", "seconds": ASK_TIMEOUT})
                robot.log("error", f"ask timeout after {ASK_TIMEOUT}s (thread left to finish)", "tiny")
                self.busy = False

        threading.Thread(target=watchdog, daemon=True).start()
        return {"ok": True, "accepted": True, "text": text}


def create_app(robot: Optional[Robot] = None) -> FastAPI:
    robot = robot or Robot()
    app = FastAPI(title="Reachy Mini dashboard", version=__version__, docs_url=None, redoc_url=None)
    app.state.robot = robot
    app.state.clients: Set[WebSocket] = set()
    app.state.rate: Dict[str, Deque[float]] = defaultdict(deque)
    app.state.bus: List[Dict[str, Any]] = []            # broadcast queue drained by every WS pump
    app.state.bus_seq = 0
    app.state.ask = Ask()
    app.include_router(auth.router)
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=1)

    @app.middleware("http")
    async def _headers(req: Request, call_next):
        resp = await call_next(req)
        p = req.url.path
        if p.startswith("/assets/") or p.startswith("/mujoco/") or (p.startswith("/model/") and "v=" in str(req.url.query)):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # hashed / versioned (?v=sha)
        elif p.startswith("/model/"):
            resp.headers["Cache-Control"] = "public, max-age=60, must-revalidate"   # geoms.json carries the shas
        elif req.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def emit(ev: Dict[str, Any]) -> None:
        ev.setdefault("t", time.time())
        app.state.bus_seq += 1
        ev["seq"] = app.state.bus_seq
        app.state.bus.append(ev)
        del app.state.bus[:-500]

    # dashboard events → WS
    _orig_log = robot.log

    def _log(kind: str, text: str, who: str = "dashboard", **meta: Any) -> Dict[str, Any]:
        ev = _orig_log(kind, text, who, **meta)
        emit({"type": "event", **ev})
        return ev

    robot.log = _log  # type: ignore[method-assign]

    # ── helpers ──
    def _rate_ok(req: Request) -> bool:
        key = req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")
        q = app.state.rate[key]
        now = time.monotonic()
        while q and q[0] < now - 1.0:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_S:
            return False
        q.append(now)
        return True

    def _control(req: Request) -> str:
        who = auth.require(req)
        if not _rate_ok(req):
            raise HTTPException(429, {"error": f"rate limit {RATE_LIMIT_PER_S}/s"})
        if not auth._origin_is_self(req.headers):
            raise HTTPException(403, {"error": "cross-origin control refused"})
        return who

    def _num(body: Dict[str, Any], key: str, default: Optional[float] = 0.0) -> Optional[float]:
        v = body.get(key, default)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise HTTPException(422, {"error": f"{key} must be a number"})
        return float(v)

    def _do(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ValueError as e:
            raise HTTPException(422, {"error": str(e)})
        except RuntimeError as e:
            robot.log("error", str(e)[:300], "daemon")
            raise HTTPException(502, {"error": str(e)[:400]})

    # ── public reads ──
    @app.get("/api/health")
    async def health():
        return {"ok": True, "name": "reachy", "version": __version__, "t": time.time(),
                "daemon": robot._daemon.get(), "camera": robot.cam.status(), "last_error": robot.last_error,
                "auth": {"open": auth.CFG.open, "token": auth.CFG.token is not None, "passkeys": auth.CFG.passkeys_enabled},
                "clients": len(app.state.clients), "ask_busy": app.state.ask.busy}

    @app.get("/api/state")
    async def state():
        return await asyncio.to_thread(robot.state)

    @app.get("/api/emotions")
    async def emotions():
        return await asyncio.to_thread(robot.emotions)

    @app.get("/api/log")
    async def get_log(n: int = 50, after: int = 0):
        rows = await asyncio.to_thread(agent_log_tail, max(1, min(n, 300)), after)
        return {"rows": rows, "events": robot.events[-50:]}

    @app.get("/api/snapshot.jpg")
    async def snapshot():
        f = robot.cam.frame
        if f is None:
            raise HTTPException(503, {"error": robot.cam.error or "no frame yet"})
        return Response(f, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/stream")
    async def stream():
        cam = robot.cam
        if not cam.enabled:
            raise HTTPException(503, {"error": "camera disabled"})
        boundary = "reachyframe"

        async def gen():
            last = 0
            cam.clients += 1
            try:
                while True:
                    frame = await asyncio.to_thread(cam.wait_frame, last, 1.0)
                    if frame is None:
                        await asyncio.sleep(0.05)
                        continue
                    last = cam.frame_id
                    yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n").encode() \
                        + frame + b"\r\n"
            finally:
                cam.clients -= 1

        return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ── control ──
    @app.post("/api/control/look")
    async def look(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        ant = body.get("antennas")
        if ant is not None and not (isinstance(ant, list) and len(ant) == 2):
            raise HTTPException(422, {"error": "antennas must be [right, left]"})
        return await asyncio.to_thread(_do, robot.look, _num(body, "roll"), _num(body, "pitch"), _num(body, "yaw"),
                                       _num(body, "x"), _num(body, "y"), _num(body, "z"),
                                       _num(body, "body_yaw", 0.0), ant, _num(body, "duration", 0.8), who)

    @app.post("/api/control/antennas")
    async def antennas(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.antennas, _num(body, "right"), _num(body, "left"),
                                       _num(body, "duration", 0.5), who)

    @app.post("/api/control/express")
    async def express(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        name = str(body.get("name", "")).strip()
        return await asyncio.to_thread(_do, robot.express, name, who)

    @app.post("/api/control/stop")
    async def stop(req: Request):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.stop, who)

    @app.post("/api/control/home")
    async def home(req: Request):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.home, who)

    @app.post("/api/control/wake")
    async def wake(req: Request):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.wake, who)

    @app.post("/api/control/sleep")
    async def sleep(req: Request):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.sleep, who)

    @app.post("/api/control/motors")
    async def motors(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.motors, str(body.get("mode", "")), who)

    @app.post("/api/control/volume")
    async def volume(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        lvl = _num(body, "level", None)
        if lvl is None:
            raise HTTPException(422, {"error": "level required"})
        return await asyncio.to_thread(_do, robot.volume, int(lvl), who)

    @app.post("/api/control/say")
    async def say(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        return await asyncio.to_thread(_do, robot.say, str(body.get("text", "")), who)

    @app.post("/api/control/ask")
    async def ask(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        text = str(body.get("text", "")).strip()[:600]
        if not text:
            raise HTTPException(422, {"error": "text required"})
        return app.state.ask.run(text, who, emit, robot)

    @app.get("/api/ask/last")
    async def ask_last():
        return {"busy": app.state.ask.busy, "last": app.state.ask.last}

    @app.post("/api/control/reel")
    async def reel(req: Request, body: Dict[str, Any] = Body(default={})):
        who = _control(req)
        action = body.get("action", "start")
        if action == "abort":
            robot.reel.abort("abort button")
            await asyncio.to_thread(_do, robot.stop, who)
            return robot.reel.status()
        return await asyncio.to_thread(_do, robot.reel.start, who)

    # ── websocket ──
    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        who = auth.who_ws(sock.headers, sock.client.host if sock.client else None, sock.cookies,
                          sock.query_params.get("token"))
        await sock.accept()
        app.state.clients.add(sock)
        await sock.send_json({"type": "hello", "who": who, "can_control": who is not None, "version": __version__})
        rows = await asyncio.to_thread(agent_log_tail, 40, 0)
        last_id = rows[-1]["id"] if rows else 0
        await sock.send_json({"type": "log", "rows": rows})
        for ev in robot.events[-30:]:
            await sock.send_json({"type": "event", **ev})
        seen_seq = app.state.bus_seq
        period = 1.0 / WS_HZ
        tick = 0
        try:
            while True:
                snap = await asyncio.to_thread(robot.state)
                await sock.send_json({"type": "state", **snap})
                new = [e for e in app.state.bus if e["seq"] > seen_seq]
                for e in new:
                    await sock.send_json(e)
                    seen_seq = e["seq"]
                tick += 1
                if tick % 10 == 0:                       # agent_log poll @1 Hz
                    rows = await asyncio.to_thread(agent_log_tail, 50, last_id)
                    if rows:
                        last_id = rows[-1]["id"]
                        await sock.send_json({"type": "log", "rows": rows})
                try:
                    msg = await asyncio.wait_for(sock.receive_text(), timeout=period)
                    if msg and '"ping"' in msg:
                        await sock.send_json({"type": "pong", "t": time.time()})
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.debug("ws closed: %s", e)
        finally:
            app.state.clients.discard(sock)

    @app.on_event("startup")
    async def _start():
        robot.cam.start()
        threading.Thread(target=robot.emotions, daemon=True).start()   # warm the cache
        if os.getenv("REACHY_ASK_PREWARM", "1") != "0":
            threading.Thread(target=Ask.warm, daemon=True).start()
        robot.log("system", f"dashboard {__version__} up", "system")

    @app.on_event("shutdown")
    async def _stop():
        robot.reel.abort("shutdown")
        robot.cam.stop()

    # ── SPA ──
    if (DIST / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            f = DIST / path
            if path and f.is_file() and ".." not in path:
                return FileResponse(f)
            return FileResponse(DIST / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def placeholder():
            return HTMLResponse("<!doctype html><meta charset=utf-8><title>Reachy</title>"
                                "<body style='background:#0b0b10;color:#ddd;font:14px ui-monospace,monospace;padding:2rem'>"
                                "<h1>🤖 Reachy Mini</h1><p>frontend not built — see dashboard/frontend</p>"
                                f"<pre>{json.dumps(robot.state(), indent=1, default=str)}</pre></body>")

    return app


app = create_app() if os.getenv("REACHY_NO_AUTOAPP") is None else None


def main() -> None:
    import uvicorn
    logging.basicConfig(level=os.getenv("REACHY_LOG", "INFO"), format="%(asctime)s %(name)s %(message)s")
    uvicorn.run("dashboard.server:app", host=os.getenv("REACHY_HOST", "127.0.0.1"),
                port=int(os.getenv("REACHY_HTTP_PORT", "8097")), log_level="info", ws_ping_interval=20)


if __name__ == "__main__":
    main()
