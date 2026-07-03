# systemd

<span class="read-badge">⏱ 90s · boot persistence</span>

Two ways to make TINY survive reboots. Both use **user** systemd units with
linger enabled, so they start at power-on without a login session.

## option A · docker compose unit (recommended)

One unit boots the whole stack (`docker compose up -d`):

```bash
make install-compose-service
```

This installs `tiny-compose.service`, enables linger for your user, and starts
the stack. On every boot, `voice + telegram + thinker` come up together.

```bash
systemctl --user status tiny-compose.service
```

## option B · bare-metal per-persona units

Run directly on the CM4 (no docker) — three separate units against your venv:

```bash
make venv                    # ensure .venv + deps exist first
make install-bare-services
```

Installs and enables:

| unit | persona | entry |
|---|---|---|
| `tiny-voice.service` | bidi voice | `voice_listener.py` |
| `tiny-telegram.service` | telegram | `telegram_listener.py` |
| `tiny-thinker.service` | 30s heartbeat | `thinker_loop.py` |

Each unit is ordered `After=reachy-mini.service` so the personas wait for the
daemon to be up before connecting.

```bash
make service-status          # systemctl --user status tiny-*.service
```

!!! tip "Linger"
    `loginctl enable-linger $USER` is run for you by both install targets — it
    lets the user units run without an active login. Verify with
    `loginctl show-user $USER | grep Linger`.
