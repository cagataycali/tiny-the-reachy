#!/usr/bin/env python3
"""Wake TINY (Reachy Mini) at boot: enable motors + wake_up, then exit hard.

The daemon starts with --no-wake-up-on-start, so on every boot the robot
comes up asleep with motors disabled. This runs once at boot (after the
daemon) to energize the motors, then exits IMMEDIATELY with os._exit so no
ReachyMini client connection lingers to contend with the MHS mount.
"""
import json
import os
import sys
import time
import urllib.request

# Boot volume floor: "silent" (volume 0) is meant to be a live, session-only state,
# but alsa-state persists the hardware mixer across power cycles, so a robot that was
# muted when unplugged would boot deaf-and-dumb. Restore at least BOOT_VOLUME_MIN.
BOOT_VOLUME_MIN = int(os.environ.get("REACHY_BOOT_VOLUME_MIN", "60"))
DAEMON = os.environ.get("REACHY_DAEMON_URL", "http://127.0.0.1:8000")


def restore_volume() -> None:
    try:
        with urllib.request.urlopen(f"{DAEMON}/api/volume/current", timeout=4) as r:
            cur = int(json.load(r).get("volume", -1))
        if 0 <= cur < BOOT_VOLUME_MIN:
            req = urllib.request.Request(f"{DAEMON}/api/volume/set",
                                         data=json.dumps({"volume": BOOT_VOLUME_MIN}).encode(),
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=4):
                pass
            print(f"tiny-wake: volume was {cur} at boot -> restored to {BOOT_VOLUME_MIN}", flush=True)
        else:
            print(f"tiny-wake: volume at boot = {cur} (ok)", flush=True)
    except Exception as exc:
        print(f"tiny-wake: volume restore skipped ({exc})", flush=True)

from reachy_mini import ReachyMini


def main() -> int:
    restore_volume()
    last_err = None
    for attempt in range(1, 21):
        try:
            r = ReachyMini()
            r.enable_motors()
            r.wake_up()
            print("tiny-wake: motors enabled + wake_up OK (attempt %d)" % attempt, flush=True)
            time.sleep(1.0)
            # Best-effort clean close, then HARD exit so no client socket lingers.
            for closer in ("disconnect", "close", "stop", "__exit__"):
                fn = getattr(r, closer, None)
                if callable(fn):
                    try:
                        fn() if closer != "__exit__" else fn(None, None, None)
                    except Exception:
                        pass
                    break
            os._exit(0)
        except Exception as exc:
            last_err = exc
            print("tiny-wake: attempt %d not ready (%s); retrying" % (attempt, exc), flush=True)
            time.sleep(3.0)
    print("tiny-wake: FAILED after retries: %s" % last_err, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
