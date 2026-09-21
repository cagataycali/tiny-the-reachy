---
title: Deploying to the robot
description: "How the code reaches the CM4 (rsync, not git), which venv it lands in, how to restart only what you touched, and how to know it came back."
for: whoever ships changes to the desk
proof: robot
verified: 2026-09-17
---

# Deploying to the robot

!!! abstract "In 10 seconds"
    - `~/tiny-the-reachy/` on the CM4 is an **rsync target, not a clone** — the Mac checkout is the truth.
    - Python goes into Pollen's `/venvs/apps_venv`; `/venvs/mini_daemon` is hands-off.
    - `rsync`, then restart only what you touched; `dist/` needs no restart.

## Where things live

| on the CM4 (Debian 13, aarch64, 4 GB, 14 GB SD) | what |
|---|---|
| `~/tiny-the-reachy/` | this repo, rsync'd — *not a git repo* there |
| `~/tiny-the-reachy/.env` | keys — never in git |
| `~/.reachy-dashboard.env` | `REACHY_TOKEN`, `REACHY_REG_TOKEN`, `REACHY_RP_ID`, `REACHY_ORIGIN` |
| `~/.tiny-mcp.env` (600) | tiny.technology token for the fleet tools |
| `/venvs/apps_venv` | Pollen's Python 3.12 — install into it, never replace it |
| `/venvs/mini_daemon` | the daemon's — hands off |
| `~/tts-venv` + `~/tiny-tts/` | Piper TTS |
| `~/.local/node` + `~/.local/lib/tiny-mcp` | node 22 + the MCP server |
| `~/.config/systemd/user/` | [the eight units](systemd.md) |
| `~/.cloudflared/` | tunnel credentials + `config.yml` |

## Ship a change

=== "Python (tools, personas, prompts)"

    ```bash
    rsync -az --delete --exclude .git --exclude .env --exclude node_modules \
          --exclude 'dashboard/frontend/src' --exclude '__pycache__' \
          ./ pollen@reachy-mini.local:tiny-the-reachy/
    ssh reachy 'systemctl --user restart tiny-voice tiny-telegram tiny-thinker'
    ```

    A voice restart drops the current conversation.

=== "Dashboard backend"

    ```bash
    dashboard/deploy/sync.sh                                  # rsync dashboard/ + dist → restart → curl /api/health
    REACHY_SSH=pollen@192.168.1.5 dashboard/deploy/sync.sh    # by IP
    ```

=== "Dashboard frontend only"

    ```bash
    cd dashboard/frontend && npm run build
    rsync -az dist/ pollen@reachy-mini.local:tiny-the-reachy/dashboard/frontend/dist/
    ```

    No restart: `index.html` is `no-cache`, assets are content-hashed.

## Verify it came back

```bash
ssh reachy 'systemctl --user is-active tiny-voice tiny-telegram tiny-thinker reachy-dashboard reachy-tunnel'
curl -s localhost:8097/api/health | jq '{daemon: .daemon.state, camera: .camera.fps, fds: .pressure.fds}'
```

## Network and constraints

- Wi-Fi: home network first, hotspot **`neon_net`** as fallback; `reachy-mini.local` resolves on either.
- `:8000` is unauthenticated — never exposed; the tunnel publishes `:8097` only.
- Disk 89 % full: `df -h /` before any `pip install`.
- Load ~3 on four cores; tracking +1.5 — `F` turns it off when the temperature pill goes amber.
- Camera is imx708 behind libcamera: `cv2.VideoCapture` returns nothing — use the daemon's IPC socket.
- `journalctl --user` finds nothing: `journalctl _SYSTEMD_USER_UNIT=tiny-voice.service`.

## First-time setup on a fresh CM4

1. Flash Pollen's image, join Wi-Fi, `curl localhost:8000/api/daemon/status`.
2. `ssh-copy-id pollen@reachy-mini.local`; change the factory password.
3. Raise the daemon's fd limit first:
   ```bash
   sudo mkdir -p /etc/systemd/system/reachy-mini-daemon.service.d
   printf '[Service]\nLimitNOFILE=65536\n' | sudo tee /etc/systemd/system/reachy-mini-daemon.service.d/nofile.conf
   sudo systemctl daemon-reload && sudo systemctl restart reachy-mini-daemon
   ```
4. rsync (above); `/venvs/apps_venv/bin/pip install -r requirements-robot.txt`.
5. `cp scripts/systemd/robot/*.service ~/.config/systemd/user/`; `loginctl enable-linger pollen`; `systemctl --user enable --now` the units.
6. Dashboard: `~/.reachy-dashboard.env`, `dashboard/deploy/sync.sh`, enrol your passkey — **the gate is open until the first credential (TOFU)**.
7. Tunnel: `cloudflared tunnel create reachy`, `config.yml`, user unit — **after** step 6.
8. Optional: Piper, tiny-mcp token, watchdog.
