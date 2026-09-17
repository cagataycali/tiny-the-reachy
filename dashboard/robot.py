"""Reachy Mini bridge for the dashboard — talks to the daemon's REST (localhost:8000), the camera,
and the personas' shared SQLite (.memory/mem.db).

Units: the daemon speaks radians + metres; every public function here takes DEGREES + MILLIMETRES
(same as tools/reachy_motion.py) and applies the same clamps as tools/_reachy_common.py.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib import error, request

log = logging.getLogger("reachy.dash.robot")

REPO = Path(__file__).resolve().parent.parent
DAEMON = os.getenv("REACHY_DAEMON_URL", "http://localhost:8000").rstrip("/")
MEM_DB = Path(os.getenv("REACHY_MEM_DB", str(REPO / ".memory" / "mem.db")))
DATASET = "pollen-robotics/reachy-mini-emotions-library"
CAMERA_INDEX = int(os.getenv("REACHY_DASH_CAMERA_INDEX", "0"))
CAM_W, CAM_H, CAM_FPS = 640, 360, int(os.getenv("REACHY_DASH_CAM_FPS", "12"))

# safety envelope (degrees) — mirrors tools/_reachy_common.py
LIM_HEAD_PITCH = (-40.0, 40.0)
LIM_HEAD_ROLL = (-40.0, 40.0)
LIM_HEAD_YAW = (-180.0, 180.0)
LIM_BODY_YAW = (-160.0, 160.0)
LIM_ANTENNA = (-150.0, 150.0)
LIM_XYZ_MM = (-25.0, 25.0)

# emotion families for the grid — anything unlisted lands in "other"
FAMILIES: Dict[str, List[str]] = {
    "happy": ["cheerful", "laughing", "enthusiastic", "success", "proud", "grateful", "loving", "relief", "serenity", "amazed", "electric"],
    "welcome": ["welcoming", "helpful", "attentive", "understanding", "calming", "come"],
    "curious": ["curious", "inquiring", "thoughtful", "surprised", "confused", "uncertain", "incomprehensible", "lost"],
    "yes/no": ["yes", "no", "no_excited", "no_sad", "yes_sad"],
    "dance": ["dance"],
    "sad": ["sad", "downcast", "lonely", "exhausted", "tired", "boredom", "resigned", "dying", "shy", "uncomfortable", "anxiety", "scared", "fear", "indifferent"],
    "angry": ["rage", "furious", "irritated", "frustrated", "displeased", "disgusted", "contempt", "reprimand", "impatient", "go_away", "oops"],
    "sleep": ["sleep"],
}


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── daemon REST ──────────────────────────────────────────────────────────────
def daemon(method: str, path: str, body: Optional[dict] = None, timeout: float = 4.0) -> Any:
    """One call to the Reachy daemon. Raises RuntimeError with the daemon's message on failure."""
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(DAEMON + path, data=data, method=method,
                          headers={"Content-Type": "application/json"} if data is not None else {})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except error.HTTPError as e:
        try:
            detail = json.loads(e.read())
        except Exception:  # noqa: BLE001
            detail = e.reason
        raise RuntimeError(f"daemon {method} {path} → {e.code}: {detail}") from None
    except (error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"daemon unreachable ({path}): {e}") from None


# ── local TTS (tiny-tts.service → Piper, offline) ────────────────────────────
TTS_URL = os.getenv("REACHY_DASH_TTS_URL", os.getenv("TINY_TTS_URL", "http://127.0.0.1:5002")).rstrip("/")


def _tts_synth(text: str, timeout: float = 30.0) -> str:
    """Synthesize on the robot's Piper service; returns a local .wav path. Raises if unavailable."""
    data = json.dumps({"text": text, "as": "path"}).encode()
    req = request.Request(TTS_URL + "/tts", data=data, method="POST",
                          headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read() or b"{}")
    except error.HTTPError as e:
        raise RuntimeError(f"tiny-tts → {e.code}: {e.reason}") from None
    except (error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"tiny-tts unreachable at {TTS_URL}: {e}") from None
    path = out.get("path")
    if not path or not Path(path).is_file():
        raise RuntimeError(f"tiny-tts returned {out!r}")
    return str(path)


def _wav_seconds(path: str) -> Optional[float]:
    try:
        import wave

        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:  # noqa: BLE001
        return None



class Cached:
    def __init__(self, fn: Callable[[], Any], ttl: float):
        self.fn, self.ttl = fn, ttl
        self._v: Any = None
        self._t = 0.0
        self._lock = threading.Lock()

    def get(self) -> Any:
        with self._lock:
            now = time.monotonic()
            if self._v is None or now - self._t > self.ttl:
                self._v = self.fn()
                self._t = now
            return self._v

    def invalidate(self) -> None:
        with self._lock:
            self._t = 0.0


def _emotions() -> List[str]:
    return sorted(daemon("GET", f"/api/move/recorded-move-datasets/list/{DATASET}", timeout=8))


def family_of(name: str) -> str:
    stem = name.rstrip("0123456789")
    for fam, stems in FAMILIES.items():
        if stem in stems:
            return fam
    return "other"


class Robot:
    """Everything the server needs; one instance per process."""

    def __init__(self) -> None:
        self.boot = time.time()
        self.events: List[Dict[str, Any]] = []            # dashboard-local log (also mirrored to agent_log)
        self.now_playing: Optional[Dict[str, Any]] = None  # {name, started, duration?}
        self.last_error: Optional[str] = None
        self._emotions = Cached(self._emotions_safe, 3600)
        self._state = Cached(self._state_uncached, float(os.getenv("REACHY_STATE_CACHE_S", "0.06")))
        self._wifi = Cached(self._wifi_safe, 30)
        self._system = Cached(self._system_safe, 5)
        self._services = Cached(self._services_safe, 4)
        self._daemon = Cached(self._daemon_safe, 5)
        self.cam = Camera()
        self.reel = DemoReel(self)

    # ── reads ──
    def _emotions_safe(self) -> List[str]:
        try:
            return _emotions()
        except RuntimeError as e:
            self.last_error = str(e)
            return []

    def emotions(self) -> Dict[str, Any]:
        names = self._emotions.get()
        groups: Dict[str, List[str]] = {}
        for n in names:
            groups.setdefault(family_of(n), []).append(n)
        order = list(FAMILIES) + ["other"]
        return {"names": names, "groups": [{"family": f, "moves": groups[f]} for f in order if f in groups],
                "dataset": DATASET, "now_playing": self.now_playing}

    def _wifi_safe(self) -> Dict[str, Any]:
        try:
            w = daemon("GET", "/wifi/status") or {}
            return {"ssid": w.get("connected_network"), "mode": w.get("mode")}
        except RuntimeError:
            return {"ssid": None, "mode": None}

    # ── host telemetry (CM4): cpu temp/load, memory, disk, wifi signal ──
    def _system_safe(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            out["cpu_c"] = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
        except Exception:  # noqa: BLE001
            out["cpu_c"] = None
        try:
            out["load1"] = round(os.getloadavg()[0], 2)
            out["cores"] = os.cpu_count()
        except Exception:  # noqa: BLE001
            out["load1"] = None
        try:
            mem = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in Path("/proc/meminfo").read_text().splitlines()[:5])}
            out["mem_used_pct"] = round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]))
        except Exception:  # noqa: BLE001
            out["mem_used_pct"] = None
        try:
            du = shutil.disk_usage("/")
            out["disk_free_gb"] = round(du.free / 1e9, 1)
            out["disk_used_pct"] = round(100 * du.used / du.total)
        except Exception:  # noqa: BLE001
            out["disk_free_gb"] = None
        try:
            for ln in Path("/proc/net/wireless").read_text().splitlines()[2:]:
                parts = ln.split()
                out["wifi_signal_dbm"] = int(float(parts[3].rstrip(".")))
                out["wifi_link"] = int(float(parts[2].rstrip(".")))
                break
        except Exception:  # noqa: BLE001
            out["wifi_signal_dbm"] = None
        try:
            out["host_uptime_s"] = int(float(Path("/proc/uptime").read_text().split()[0]))
        except Exception:  # noqa: BLE001
            out["host_uptime_s"] = None
        return out

    SERVICES = ("tiny-voice", "tiny-telegram", "tiny-thinker", "tiny-mhs", "tiny-tts", "reachy-tunnel")

    def _services_safe(self) -> Dict[str, str]:
        try:
            r = subprocess.run(["systemctl", "--user", "is-active", *self.SERVICES], capture_output=True, text=True, timeout=3)
            states = r.stdout.split()
            return dict(zip(self.SERVICES, states)) if len(states) == len(self.SERVICES) else {}
        except Exception:  # noqa: BLE001
            return {}

    def demo_mode(self, on: bool, who: str = "dashboard") -> Dict[str, Any]:
        """Demo mode = pause the thinker persona (it emotes every 30 s and overlaps manual moves)."""
        verb = "stop" if on else "start"
        try:
            subprocess.run(["systemctl", "--user", verb, "tiny-thinker"], capture_output=True, text=True, timeout=15, check=True)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"systemctl {verb} tiny-thinker failed: {e}") from e
        self._services.invalidate()
        self.log("control", f"demo mode {'ON (thinker paused)' if on else 'OFF (thinker resumed)'}", who)
        return {"ok": True, "demo": on, "services": self._services.get()}

    def _daemon_safe(self) -> Dict[str, Any]:
        try:
            d = daemon("GET", "/api/daemon/status") or {}
            bs = d.get("backend_status") or {}
            return {"state": d.get("state"), "wireless": d.get("wireless_version"),
                    "media_released": d.get("media_released"),
                    "loop_hz": round((bs.get("control_loop_stats") or {}).get("mean_control_loop_frequency") or 0, 1),
                    "version": d.get("version") or "1.8.1"}
        except RuntimeError as e:
            return {"state": "unreachable", "error": str(e)}

    def _state_uncached(self) -> Dict[str, Any]:
        try:
            # with_head_joints → head_joints = [yaw_body, stewart_1..6] (rad): the twin's motor targets.
            # with_target_* → what the daemon is currently commanding (the twin's "ghost").
            s = daemon("GET", "/api/state/full?with_head_joints=true&with_target_head_pose=true"
                              "&with_target_head_joints=true&with_target_body_yaw=true&with_target_antenna_positions=true",
                       timeout=2) or {}
            hp = s.get("head_pose") or {}
            ant = s.get("antennas_position") or [0.0, 0.0]
            hj = s.get("head_joints") or []
            tj = s.get("target_head_joints") or []
            tant = s.get("target_antennas_position") or s.get("target_antenna_positions") or []
            joints = [float(v) for v in hj] + [float(v) for v in ant] if len(hj) == 7 else None
            target = ([float(v) for v in tj] + [float(v) for v in (tant if len(tant) == 2 else ant)]) if len(tj) == 7 else None
            try:
                running = daemon("GET", "/api/move/running", timeout=2) or []
            except RuntimeError:
                running = []
            out = {
                "ok": True,
                "control_mode": s.get("control_mode"),
                "head": {"x_mm": hp.get("x", 0) * 1000, "y_mm": hp.get("y", 0) * 1000, "z_mm": hp.get("z", 0) * 1000,
                         "roll": math.degrees(hp.get("roll", 0)), "pitch": math.degrees(hp.get("pitch", 0)),
                         "yaw": math.degrees(hp.get("yaw", 0))},
                "head_rad": hp,
                "body_yaw": math.degrees(s.get("body_yaw") or 0),
                "antennas": [math.degrees(ant[0]), math.degrees(ant[1])],
                "doa": s.get("doa"),
                "joints": joints,                      # rad: yaw_body, stewart_1..6, right_antenna, left_antenna
                "target": target,                      # rad, same order — daemon's commanded pose (ghost), or null
                "target_head_rad": s.get("target_head_pose"),
                "moves_running": len(running),
                "ts": s.get("timestamp"),
            }
            self.last_error = None
        except RuntimeError as e:
            self.last_error = str(e)
            out = {"ok": False, "error": str(e), "control_mode": None, "head": None, "body_yaw": None,
                   "antennas": None, "moves_running": 0}
        # now-playing auto-expiry: emotions report no duration; clear when no move is running 1.5 s after start
        np_ = self.now_playing
        if np_ and out["moves_running"] == 0 and time.time() - np_["started"] > 1.5:
            self.now_playing = None
        out.update({"now_playing": self.now_playing, "daemon": self._daemon.get(), "wifi": self._wifi.get(),
                    "uptime_s": round(time.time() - self.boot, 1), "camera": self.cam.status(),
                    "reel": self.reel.status(), "system": self._system.get(), "services": self._services.get(),
                    "demo": self._services.get().get("tiny-thinker") not in ("active", "activating"), "t": time.time()})
        return out

    def state(self) -> Dict[str, Any]:
        return self._state.get()

    # ── log ──
    def log(self, kind: str, text: str, who: str = "dashboard", **meta: Any) -> Dict[str, Any]:
        ev = {"t": time.time(), "kind": kind, "who": who, "text": text, **({"meta": meta} if meta else {})}
        self.events.append(ev)
        del self.events[:-300]
        try:
            agent_log_record("dashboard", "user" if kind == "control" else "system", f"[{who}] {text}",
                             {"kind": kind, **meta} if meta else {"kind": kind})
        except Exception as e:  # noqa: BLE001
            log.debug("agent_log write failed: %s", e)
        return ev

    # ── writes (degrees / mm in, radians / metres out) ──
    def look(self, roll: float = 0, pitch: float = 0, yaw: float = 0, x: float = 0, y: float = 0, z: float = 0,
             body_yaw: Optional[float] = 0, antennas: Optional[List[float]] = None, duration: float = 0.8,
             who: str = "dashboard") -> Dict[str, Any]:
        roll, pitch, yaw = clamp(roll, *LIM_HEAD_ROLL), clamp(pitch, *LIM_HEAD_PITCH), clamp(yaw, *LIM_HEAD_YAW)
        x, y, z = (clamp(v, *LIM_XYZ_MM) for v in (x, y, z))
        duration = clamp(float(duration), 0.3, 6.0)
        body = {"head_pose": {"x": x / 1000, "y": y / 1000, "z": z / 1000, "roll": math.radians(roll),
                              "pitch": math.radians(pitch), "yaw": math.radians(yaw)},
                "duration": duration, "interpolation": "minjerk"}
        if body_yaw is not None:
            body["body_yaw"] = math.radians(clamp(body_yaw, *LIM_BODY_YAW))
        if antennas is not None:
            body["antennas"] = [math.radians(clamp(a, *LIM_ANTENNA)) for a in antennas[:2]]
        r = daemon("POST", "/api/move/goto", body)
        self.log("control", f"look roll={roll:.0f} pitch={pitch:.0f} yaw={yaw:.0f} body={body_yaw} d={duration}s", who)
        return {"ok": True, "move": r, "sent": body}

    def antennas(self, right: float, left: float, duration: float = 0.5, who: str = "dashboard") -> Dict[str, Any]:
        body = {"antennas": [math.radians(clamp(right, *LIM_ANTENNA)), math.radians(clamp(left, *LIM_ANTENNA))],
                "duration": clamp(float(duration), 0.2, 4.0), "interpolation": "minjerk"}
        r = daemon("POST", "/api/move/goto", body)
        self.log("control", f"antennas right={right:.0f} left={left:.0f}", who)
        return {"ok": True, "move": r}

    def express(self, name: str, who: str = "dashboard") -> Dict[str, Any]:
        names = self._emotions.get()
        if name not in names:
            raise ValueError(f"unknown emotion {name!r}")
        r = daemon("POST", f"/api/move/play/recorded-move-dataset/{DATASET}/{name}", timeout=8)
        self.now_playing = {"name": name, "started": time.time(), "family": family_of(name), "uuid": (r or {}).get("uuid")}
        self.log("control", f"express {name}", who, emotion=name)
        return {"ok": True, "move": r, "name": name}

    def stop(self, who: str = "dashboard") -> Dict[str, Any]:
        self.reel.abort("stop")
        stopped: List[Any] = []
        try:
            running = daemon("GET", "/api/move/running") or []
        except RuntimeError:
            running = []
        for m in running:
            uid = m.get("uuid") if isinstance(m, dict) else m
            try:
                daemon("POST", "/api/move/stop", {"uuid": uid})
                stopped.append(uid)
            except RuntimeError as e:
                log.warning("stop %s: %s", uid, e)
        self.now_playing = None
        self.log("control", f"STOP ({len(stopped)} moves)", who)
        return {"ok": True, "stopped": stopped}

    def wake(self, who: str = "dashboard") -> Dict[str, Any]:
        r = daemon("POST", "/api/move/play/wake_up", timeout=8)
        self.log("control", "wake_up", who)
        return {"ok": True, "move": r}

    def sleep(self, who: str = "dashboard") -> Dict[str, Any]:
        r = daemon("POST", "/api/move/play/goto_sleep", timeout=8)
        self.log("control", "goto_sleep", who)
        return {"ok": True, "move": r}

    def motors(self, mode: str, who: str = "dashboard") -> Dict[str, Any]:
        if mode not in ("enabled", "disabled", "gravity_compensation"):
            raise ValueError("mode must be enabled | disabled | gravity_compensation")
        r = daemon("POST", f"/api/motors/set_mode/{mode}")
        self.log("control", f"motors {mode}", who)
        return {"ok": True, "result": r}

    def volume(self, level: int, who: str = "dashboard") -> Dict[str, Any]:
        level = int(clamp(int(level), 0, 100))
        r = daemon("POST", "/api/volume/set", {"volume": level})
        self.log("control", f"volume {level}", who)
        return {"ok": True, "result": r}

    def say(self, text: str, who: str = "dashboard", wobble: bool = True) -> Dict[str, Any]:
        """Speak text NOW: local Piper (tiny-tts) → daemon play_sound, head wobbling while it plays.

        The voice persona (voice_bridge) is only a last-resort queue: it is disabled for the
        showcase (invalid OpenAI key), so a queued line would never be spoken — we say so.
        Audio goes out on a separate playbin → ALSA, so it does NOT need daemon media acquired
        and never fights the rpicam camera.
        """
        text = text.strip()[:500]
        if not text:
            raise ValueError("empty text")
        try:
            path = _tts_synth(text)
        except Exception as e:  # noqa: BLE001 — any TTS failure falls back to the queue
            rid = voice_bridge_push("dashboard", f"Say this out loud, verbatim: {text}", importance=2)
            self.log("control", f"say QUEUED (local TTS down): {text}", who, voice_bridge_id=rid, error=str(e)[:200])
            return {"ok": False, "engine": "voice_bridge", "queued": rid,
                    "warning": f"local TTS unreachable ({e}); queued for the voice persona, which is disabled — "
                               "nothing will be spoken until tiny-tts.service is back"}
        secs = _wav_seconds(path) or max(1.5, len(text) * 0.06)
        if wobble:
            try:
                daemon("POST", "/api/media/wobbling/enable")
            except RuntimeError as e:
                log.warning("wobbling enable: %s", e)
                wobble = False
        daemon("POST", "/api/media/play_sound", {"file": path}, timeout=8)
        self.log("control", f"say ({secs:.1f}s): {text}", who, engine="piper-local", file=path)
        if wobble:
            t = threading.Timer(min(secs + 0.3, 30.0), self._wobble_off)
            t.daemon = True
            t.start()
        return {"ok": True, "engine": "piper-local", "seconds": round(secs, 2), "file": path}

    def _wobble_off(self) -> None:
        try:
            daemon("POST", "/api/media/wobbling/disable")
        except RuntimeError as e:
            log.warning("wobbling disable: %s", e)

    def home(self, who: str = "dashboard") -> Dict[str, Any]:
        return self.look(0, 0, 0, 0, 0, 0, body_yaw=0, antennas=[0, 0], duration=1.2, who=who)


# ── shared SQLite (personas) ─────────────────────────────────────────────────
def _mem() -> sqlite3.Connection:
    c = sqlite3.connect(MEM_DB, timeout=5)
    c.execute("PRAGMA busy_timeout=5000")
    return c


def agent_log_record(persona: str, role: str, text: str, meta: Optional[dict] = None) -> int:
    if not MEM_DB.parent.exists():
        return 0
    c = _mem()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS agent_log(id INTEGER PRIMARY KEY AUTOINCREMENT, persona TEXT NOT NULL,
                     role TEXT NOT NULL, text TEXT NOT NULL, meta TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur = c.execute("INSERT INTO agent_log(persona, role, text, meta) VALUES(?,?,?,?)",
                        (persona, role, str(text)[:8000], json.dumps(meta) if meta else None))
        c.commit()
        return cur.lastrowid or 0
    finally:
        c.close()


def agent_log_tail(limit: int = 50, after_id: int = 0) -> List[Dict[str, Any]]:
    if not MEM_DB.exists():
        return []
    c = _mem()
    try:
        if after_id:
            rows = c.execute("SELECT id, persona, role, text, meta, ts FROM agent_log WHERE id>? ORDER BY id ASC LIMIT ?",
                             (after_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT id, persona, role, text, meta, ts FROM agent_log ORDER BY id DESC LIMIT ?",
                             (limit,)).fetchall()
            rows.reverse()
    except sqlite3.OperationalError:
        return []
    finally:
        c.close()
    out = []
    for i, p, r, t, m, ts in rows:
        try:
            meta = json.loads(m) if m else None
        except Exception:  # noqa: BLE001
            meta = None
        out.append({"id": i, "persona": p, "role": r, "text": t[:1200], "meta": meta, "ts": ts})
    return out


def voice_bridge_push(source: str, text: str, importance: int = 1) -> int:
    c = _mem()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS voice_bridge(id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
                     text TEXT NOT NULL, importance INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     delivered INTEGER DEFAULT 0)""")
        cur = c.execute("INSERT INTO voice_bridge(source, text, importance) VALUES(?,?,?)", (source, text[:2000], importance))
        c.commit()
        return cur.lastrowid or 0
    finally:
        c.close()


# ── camera: ONE capture process/thread, latest JPEG shared by every client ───
# The Wireless CM4 camera (imx708) is a CSI sensor behind libcamera: plain V4L2 reads of /dev/video0 return nothing,
# so we pipe `rpicam-vid --codec mjpeg` (present on the robot) and split the stream on JPEG SOI/EOI markers.
# REACHY_DASH_CAMERA=cv2 uses cv2.VideoCapture (UVC webcams, dev laptops).
class Camera:
    def __init__(self) -> None:
        self.frame: Optional[bytes] = None
        self.frame_id = 0
        self.fps = 0.0
        self.error: Optional[str] = None
        self.clients = 0
        self.backend = os.getenv("REACHY_DASH_CAMERA", "rpicam" if shutil.which("rpicam-vid") else "cv2")
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self.enabled = os.getenv("REACHY_DASH_CAMERA_OFF", "") == ""

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def status(self) -> Dict[str, Any]:
        return {"ok": self.frame is not None and self.error is None, "fps": round(self.fps, 1), "frame_id": self.frame_id,
                "error": self.error, "clients": self.clients, "enabled": self.enabled, "backend": self.backend}

    def _publish(self, jpg: bytes, stats: list) -> None:
        with self._cv:
            self.frame = jpg
            self.frame_id += 1
            self._cv.notify_all()
        stats[0] += 1
        now = time.monotonic()
        if now - stats[1] >= 2.0:
            self.fps = stats[0] / (now - stats[1])
            stats[0], stats[1] = 0, now

    def _run(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                ok = self._run_rpicam() if self.backend == "rpicam" else self._run_cv2()
            except Exception as e:  # noqa: BLE001
                self.error = f"camera: {e}"
                ok = False
            if self._stop.is_set():
                break
            self._stop.wait(backoff if not ok else 1.0)
            backoff = min(backoff * 1.5, 20)

    def _run_rpicam(self) -> bool:
        cmd = ["rpicam-vid", "-n", "-t", "0", "--codec", "mjpeg", "--width", str(CAM_W), "--height", str(CAM_H),
               "--framerate", str(CAM_FPS), "--quality", "70", "--flush", "-o", "-"]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        assert self._proc.stdout is not None
        buf = bytearray()
        stats = [0, time.monotonic()]
        got_any = False
        while not self._stop.is_set():
            chunk = self._proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                soi = buf.find(b"\xff\xd8\xff")
                if soi < 0:
                    del buf[:]
                    break
                eoi = buf.find(b"\xff\xd9", soi + 2)
                if eoi < 0:
                    if soi:
                        del buf[:soi]
                    break
                jpg = bytes(buf[soi:eoi + 2])
                del buf[:eoi + 2]
                self.error = None
                got_any = True
                self._publish(jpg, stats)
            if len(buf) > 4_000_000:
                del buf[:]
        rc = self._proc.poll()
        if self._proc.poll() is None:
            self._proc.terminate()
        if not got_any:
            self.error = f"rpicam-vid produced no frames (rc={rc}) — camera busy? try POST daemon /api/media/release"
        return got_any

    def _run_cv2(self) -> bool:
        import cv2  # noqa: PLC0415
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            self.error = f"/dev/video{CAMERA_INDEX} busy or missing"
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        cap.set(cv2.CAP_PROP_FPS, CAM_FPS)
        self.error = None
        stats = [0, time.monotonic()]
        period = 1.0 / CAM_FPS
        fails = 0
        got_any = False
        while not self._stop.is_set():
            t = time.monotonic()
            ok, img = cap.read()
            if not ok:
                fails += 1
                if fails > 30:
                    self.error = "camera read failed"
                    break
                time.sleep(0.05)
                continue
            fails = 0
            if img.shape[1] != CAM_W:
                img = cv2.resize(img, (CAM_W, CAM_H), interpolation=cv2.INTER_AREA)
            ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                got_any = True
                self._publish(enc.tobytes(), stats)
            dt = period - (time.monotonic() - t)
            if dt > 0:
                time.sleep(dt)
        cap.release()
        return got_any

    def wait_frame(self, last_id: int, timeout: float = 1.0) -> Optional[bytes]:
        with self._cv:
            if self.frame_id == last_id:
                self._cv.wait(timeout)
            return self.frame if self.frame_id != last_id else None


# ── demo reel: a scripted 60–90 s show with a visible timeline ───────────────
REEL: List[Dict[str, Any]] = [
    {"label": "wake up", "kind": "wake", "wait": 4.0},
    {"label": "welcoming1", "kind": "express", "name": "welcoming1", "wait": 6.0},
    {"label": "look left", "kind": "look", "args": {"yaw": 35, "pitch": 5, "duration": 1.2}, "wait": 1.6},
    {"label": "look right", "kind": "look", "args": {"yaw": -35, "pitch": 5, "duration": 1.4}, "wait": 1.8},
    {"label": "curious1", "kind": "express", "name": "curious1", "wait": 7.0},
    {"label": "look up", "kind": "look", "args": {"pitch": -20, "roll": 10, "duration": 1.2}, "wait": 1.6},
    {"label": "dance1", "kind": "express", "name": "dance1", "wait": 14.0},
    {"label": "laughing1", "kind": "express", "name": "laughing1", "wait": 7.0},
    {"label": "antenna wiggle", "kind": "antennas", "seq": [[40, -40], [-40, 40], [40, -40], [0, 0]], "wait": 0.5},
    {"label": "proud1", "kind": "express", "name": "proud1", "wait": 7.0},
    {"label": "home", "kind": "home", "wait": 1.5},
]


class DemoReel:
    def __init__(self, robot: Robot) -> None:
        self.robot = robot
        self.running = False
        self.step = -1
        self.started = 0.0
        self.aborted: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._abort = threading.Event()

    def status(self) -> Dict[str, Any]:
        total = sum(float(s["wait"]) * (len(s.get("seq", [1])) if s["kind"] == "antennas" else 1) for s in REEL)
        return {"running": self.running, "step": self.step, "steps": [s["label"] for s in REEL],
                "elapsed": round(time.time() - self.started, 1) if self.running else 0, "total_s": round(total),
                "aborted": self.aborted}

    def start(self, who: str) -> Dict[str, Any]:
        if self.running:
            raise RuntimeError("demo reel already running")
        self._abort.clear()
        self.aborted = None
        self.running, self.step, self.started = True, 0, time.time()
        self._thread = threading.Thread(target=self._run, args=(who,), daemon=True)
        self._thread.start()
        self.robot.log("control", "demo reel START", who)
        return self.status()

    def abort(self, why: str = "abort") -> None:
        if self.running:
            self.aborted = why
            self._abort.set()

    def _run(self, who: str) -> None:
        try:
            for i, s in enumerate(REEL):
                if self._abort.is_set():
                    break
                self.step = i
                try:
                    if s["kind"] == "wake":
                        self.robot.wake(who="reel")
                    elif s["kind"] == "express":
                        self.robot.express(s["name"], who="reel")
                    elif s["kind"] == "look":
                        self.robot.look(**s["args"], who="reel")
                    elif s["kind"] == "home":
                        self.robot.home(who="reel")
                    elif s["kind"] == "antennas":
                        for r, l in s["seq"]:
                            if self._abort.is_set():
                                break
                            self.robot.antennas(r, l, duration=0.4, who="reel")
                            self._abort.wait(s["wait"])
                        continue
                except Exception as e:  # noqa: BLE001
                    self.robot.log("error", f"reel step {s['label']}: {e}", "reel")
                self._abort.wait(float(s["wait"]))
        finally:
            self.running = False
            self.step = -1
            self.robot.log("control", f"demo reel {'ABORTED: ' + self.aborted if self.aborted else 'done'}", who)
