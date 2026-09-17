# Fleet bridge — tiny.technology MCP inside the robot

`tools/tiny_mcp.py` mounts the **tiny-tech MCP server** (the same `npx tiny-tech`
that Claude Code / the Mac TUI use) as Strands tools inside TINY's personas.
With it the robot's agent can reach the owner's *other* devices:

| tool | what it gives the robot |
|---|---|
| `use_device` (list / invoke / result) | ask **fomo the arm**, **q-the-brain**, **the Mac**, **scout the rover**, the phone… to do something and get the answer back. The Sticky e-ink is reached by invoking the Mac. |
| `mesh_peers`, `mesh_send` | agents on this LAN (zenoh mesh) — only when `TINY_MCP_MESH=1` |
| `tiny_recall`, `tiny_learn` | the owner's cross-agent memory graph (facts, not chatter) |
| `tiny_whoami`, `tiny_events`, `tiny_send_message` | identity, activity feed, DMs |

Everything else the server offers (wallet, x402 payments, schedules, `tiny_unlearn`,
`use_npm/pypi/openapi/memory/image`, shell-ish device tools, forged `my_*` tools) is
**filtered out** by an allow-list in the module (`ALLOWED_TOOLS` + `REJECTED_PREFIXES`).

## Off by default

Nothing changes until `TINY_MCP=1`. With the flag on, the bridge is still **fail-open**:
no node, no `tiny-tech`, no/expired token, server crash at start → the persona simply
starts without fleet tools and logs one warning (`tiny_mcp: … persona runs WITHOUT fleet
tools`). A persona is never blocked or crashed by this feature.

Per-persona: `TINY_MCP_PERSONAS` (default `telegram,dashboard,shell`). The autonomous
**thinker** and the **voice** BidiAgent are opt-in (`TINY_MCP_PERSONAS=telegram,dashboard,thinker`)
— a 30 s heartbeat that can move other robots is a decision for the owner, and Realtime
voice is latency-critical.

## Security model

* **Credential**: a tiny.technology user CLI JWT (aud `tiny-cli`, 90 days) passed to the
  server as `TINY_TOKEN`. It lives in `/home/pollen/.tiny-mcp/token` (mode 600), pointed
  to by `TINY_TOKEN_FILE` in `~/.tiny-mcp.env` (600). It is **never** in the repo, never
  logged, never returned by `/api/state` (`state.fleet` only says `token: true/false`
  and days left). The server gets a minimal env (`server_env()`) — the persona's own
  API keys are not forwarded.
* **Server isolation**: `TINY_HOME=~/.tiny-mcp` (no shared credentials/device files),
  `TINY_MESH=false` unless opted in, `TINY_DISABLE_LOAD_TOOL=true`, node heap capped.
* **Self-invoke guard**: `TINY_SELF_DEVICE_IDS` (this robot's endpoint device id + name).
  `use_device invoke` on itself is refused before it reaches the network.
* **Depth cap = 1**: every relayed prompt is prefixed `[fleet depth=1 from <name>]`; the
  wrapper refuses to relay a prompt that already carries the marker, and a turn that
  ARRIVES from the fleet (`POST /api/chat`, the platform's endpoint-proxy chat) is built
  with `fleet=True` → **no fleet tools at all**. Robot A → Robot B works; B cannot fan
  out further.
* **One server per process**, spawned lazily at the first agent build and reused
  (module singleton with `add_consumer` semantics), retried at most every 5 min after
  a failure.

## Install (Reachy Mini Wireless, CM4, Debian 13 arm64 — done 2026-09-17)

```sh
# node 22 from the official tarball (no root, ~130 MB) + tiny-tech pinned
curl -fsSL https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-arm64.tar.xz | tar -xJ -C ~/.local/node --strip-components=1
mkdir -p ~/.local/lib/tiny-mcp && cd ~/.local/lib/tiny-mcp && ~/.local/node/bin/npm init -y && \
  PATH=~/.local/node/bin:$PATH npm i tiny-tech@0.13.9 --omit=dev
# python side: `mcp` is already in /venvs/apps_venv (strands-agents 1.20 MCPClient)
```

Config is **outside the repo**:

```
~/.tiny-mcp.env      (600)   TINY_MCP=1|0, TINY_TOKEN_FILE, TINY_SELF_DEVICE_IDS, TINY_SELF_NAME,
                             TINY_MCP_PERSONAS, TINY_MCP_MESH
~/.tiny-mcp/token    (600)   the JWT, one line
~/.config/systemd/user/{tiny-thinker,tiny-telegram,tiny-voice,reachy-dashboard}.service.d/tiny-mcp.conf
                             → [Service] EnvironmentFile=-%h/.tiny-mcp.env
```

`resolve_command()` finds `~/.local/node/bin/node ~/.local/lib/tiny-mcp/node_modules/tiny-tech/dist/cli.js serve`
automatically; override with `TINY_MCP_COMMAND`.

### Getting / renewing the token (owner, browser needed)

tiny.technology has no headless device-code login — the consent click *is* the login.
On the Mac:

```sh
TINY_HOME=$(mktemp -d) npx tiny-tech@0.13.9 login        # approve in the browser
python3 -c "import json,os;print(json.load(open(os.environ['TINY_HOME']+'/credentials.json'))['token'])" \
  | ssh reachy 'umask 077; cat > ~/.tiny-mcp/token'      # then: rm -rf $TINY_HOME
ssh reachy 'systemctl --user restart reachy-dashboard tiny-telegram'
```

The JWT is the owner's full account token (there is no scoped/device Bearer yet) — treat
the robot's SD card accordingly; revoke by rotating (`tiny_devices` / `/devices` on the web).

## Disable / roll back

* Soft: `sed -i s/^TINY_MCP=1/TINY_MCP=0/ ~/.tiny-mcp.env && systemctl --user restart reachy-dashboard tiny-telegram`
* Hard: delete `~/.tiny-mcp/token` (fail-open → tools vanish on next restart).
* Code roll-back: `~/backups/pre-mcp-<ts>.tgz` on the CM4 holds `tiny.py tools/ dashboard/{server,robot}.py`.

## Verify

* `GET /api/state` (bearer) → `fleet: {enabled, running, token, token_days_left, tools}`.
* Dashboard Ask *"list my devices and ask fomo for its status"* → tool receipts
  `use_device {action:list}` then `use_device {action:invoke, device_id: <fomo>}` in the
  mind timeline, answer names the device (proven 2026-09-17, 33 s round trip).
* `pytest tests/test_tiny_mcp.py` — allow-list, self-invoke refusal, depth cap, fail-open
  (no network, no node needed).
