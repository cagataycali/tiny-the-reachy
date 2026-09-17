# Deploying to the robot

<span class="read-badge">⏱ 5 min · the CM4 as it is</span>

The Wireless Reachy Mini has a Raspberry Pi **CM4** inside (Debian 13, aarch64, 4 GB RAM, 14 GB SD).
This is how the code gets there and comes back up. Facts checked on 2026-09-17.

## Where things live

| on the CM4 | what |
|---|---|
| `/home/pollen/tiny-the-reachy/` | this repo, **rsync'd, not a git clone** — `git status` there says *not a git repo*. The Mac clone is the source of truth. |
| `/home/pollen/tiny-the-reachy/.env` | keys (Bedrock, OpenAI, Telegram) — never in git, never in docs |
| `/home/pollen/.reachy-dashboard.env` | `REACHY_TOKEN`, `REACHY_REG_TOKEN`, `REACHY_RP_ID`, `REACHY_ORIGIN` |
| `/home/pollen/.tiny-mcp.env` | tiny.technology token for the fleet tools (mode 600) |
| `/venvs/apps_venv` | Pollen's Python 3.12 venv — strands, fastapi, opencv, reachy_mini SDK. We install into it, we do not replace it. |
| `/venvs/mini_daemon` | the daemon's venv. Hands off. |
| `/home/pollen/tts-venv` + `~/tiny-tts/` | Piper TTS service |
| `/home/pollen/.local/node` + `~/.local/lib/tiny-mcp` | node 22 + `tiny-tech` for the MCP fleet server |
| `~/.config/systemd/user/` | the eight units + drop-ins ([Systemd](systemd.md)) |
| `~/.cloudflared/` | tunnel credentials + `config.yml` |

## Ship a change

=== "Python (tools, personas, prompts)"

    ```bash
    # from the Mac clone
    rsync -az --delete --exclude .git --exclude .env --exclude node_modules \
          --exclude 'dashboard/frontend/src' --exclude '__pycache__' \
          ./ pollen@reachy-mini.local:tiny-the-reachy/
    ssh reachy 'systemctl --user restart tiny-voice tiny-telegram tiny-thinker'
    ```

    Restart only what you touched — every persona restart drops its SDK session and, for the voice
    persona, the current conversation.

=== "Dashboard backend"

    ```bash
    dashboard/deploy/sync.sh            # rsync dashboard/ (+ built dist) → restart reachy-dashboard
    REACHY_SSH=pollen@192.168.1.5 dashboard/deploy/sync.sh   # by IP
    ```

    The script never copies `.env`, `node_modules` or frontend sources, re-installs the unit file and
    ends with `curl localhost:8097/api/health` so you see the result.

=== "Dashboard frontend only"

    ```bash
    cd dashboard/frontend && npm run build
    rsync -az dist/ pollen@reachy-mini.local:tiny-the-reachy/dashboard/frontend/dist/
    ```

    **No restart needed.** `index.html`, `sw.js` and the manifest are served `Cache-Control: no-cache`;
    assets are content-hashed. (Cloudflare edge-caches `*.js` for 4 h otherwise — that is why.)

## Verify it came back

```bash
ssh reachy 'systemctl --user is-active tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel'
curl -s https://reachy.cagatay.my/api/health | jq '{daemon: .daemon.state, camera: .camera.fps, fds: .pressure.fds}'
```

`/api/health` is the one public route — everything else answers `401` without a passkey or bearer.

## Network

- Wi-Fi is NetworkManager. Home network at priority 10; the phone hotspot **`neon_net`** is a saved
  profile at priority −10 with autoconnect, so the robot falls back to it when the home network is gone
  (verified 2026-09-16 — it had the wrong PSK before). `ssh reachy` resolves `reachy-mini.local` on
  either network.
- `:8000` (daemon) is **unauthenticated**. It must never be exposed; the tunnel only publishes `:8097`.
- The tunnel is `cloudflared` on the CM4 itself, so the cockpit works from anywhere the robot has
  internet — including the hotspot.

## Constraints worth knowing

- **Disk 89 % full** (1.5 GB free). No new venvs; `pip install` into `apps_venv` only after checking `df -h /`.
- **CPU budget**: load average is normally ~3 on four cores; daemon face tracking adds ~1.5 and the
  dashboard's IPC camera ~0.5. That is why [face tracking](../FACE-TRACKING.md) is off by default.
- The camera is a CSI **imx708 behind libcamera**: `cv2.VideoCapture("/dev/video0")` opens and returns
  nothing. Read it through the daemon's IPC socket (what the dashboard does) or `rpicam-vid`.
- `journalctl` on the CM4 is volatile (no persistent journal) — the dashboard's `/api/log` and the
  agent log in SQLite are the durable record.

## First-time setup on a fresh CM4

1. Flash Pollen's image, join Wi-Fi via their app, confirm `curl localhost:8000/api/daemon/status`.
2. `ssh-copy-id pollen@reachy-mini.local` (factory password — change it).
3. `sudo mkdir -p /etc/systemd/system/reachy-mini-daemon.service.d && printf '[Service]\nLimitNOFILE=65536\n' | sudo tee …/nofile.conf && sudo systemctl daemon-reload && sudo systemctl restart reachy-mini-daemon`
4. rsync the repo (above); `/venvs/apps_venv/bin/pip install -r requirements-robot.txt`.
5. `cp scripts/systemd/robot/*.service ~/.config/systemd/user/` + `tiny-wake.service`; `loginctl enable-linger pollen`; `systemctl --user enable --now tiny-wake tiny-voice tiny-telegram tiny-thinker`.
6. Dashboard: create `~/.reachy-dashboard.env`, run `dashboard/deploy/sync.sh`, enrol your passkey at the gate (first enrol is open — TOFU).
7. Tunnel: `cloudflared tunnel create reachy`, DNS route, `~/.cloudflared/config.yml` as above, user unit with `Restart=always`.
8. Optional: Piper TTS venv, tiny-mcp token, watchdog timer.

The order matters only in one place: the passkey gate is **open until the first credential is enrolled**,
so do step 6 before step 7 publishes the host.
