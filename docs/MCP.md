---
title: Fleet bridge — tiny.technology MCP inside the robot
description: "tools/tiny_mcp.py mounts the tiny-tech MCP server as Strands tools so TINY can reach the owner's other devices — off by default, fail-open, allow-listed, self-invoke refused, depth-capped at 1."
for: the owner deciding what the robot may reach
proof: robot
verified: 2026-09-21
---

# Fleet bridge — tiny.technology MCP inside the robot

!!! abstract "In 10 seconds"
    - `tools/tiny_mcp.py` spawns `tiny-tech serve` (pinned `0.13.9`) and mounts an **allow-list** of its tools: `use_device`, `tiny_recall`/`tiny_learn`, `tiny_whoami`/`tiny_events`/`tiny_send_message`, `mesh_*` only with `TINY_MCP_MESH=1`. Wallet, payments, schedules, `use_npm/pypi/…` are filtered out.
    - **Off** until `TINY_MCP=1`; then **fail-open** — no node, no token, server crash → the persona starts without fleet tools and logs one warning. Personas: `TINY_MCP_PERSONAS` (default `telegram,dashboard,shell`; thinker and voice opt-in).
    - **Depth cap 1**: relayed prompts carry `[fleet depth=1 from <name>]`; a turn that *arrives* from the fleet (`POST /api/chat`) is built with `fleet=True` → no fleet tools. Robot A → Robot B works; B cannot fan out.
    - **Self-invoke refused** (`TINY_SELF_DEVICE_IDS`) before anything reaches the network.

## Security model

| what | how |
|---|---|
| credential | the owner's CLI JWT (aud `tiny-cli`, 90 days) in `~/.tiny-mcp/token` (600), via `TINY_TOKEN_FILE` in `~/.tiny-mcp.env` (600). Never in the repo, never logged; `/api/state` says only `token: true/false` + days left |
| server env | `server_env()` — minimal; the persona's own API keys are not forwarded |
| isolation | `TINY_HOME=~/.tiny-mcp`, `TINY_MESH=false` unless opted in, `TINY_DISABLE_LOAD_TOOL=true`, node heap capped |
| lifecycle | one server per process, spawned at the first agent build, retried at most every 5 min after a failure |

The JWT is a full account token — there is no scoped device bearer yet. Treat the SD card accordingly; revoke by rotating.

## Install (CM4, Debian 13 arm64 — done 2026-09-17)

```sh
curl -fsSL https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-arm64.tar.xz | tar -xJ -C ~/.local/node --strip-components=1
mkdir -p ~/.local/lib/tiny-mcp && cd ~/.local/lib/tiny-mcp && ~/.local/node/bin/npm init -y && \
  PATH=~/.local/node/bin:$PATH npm i tiny-tech@0.13.9 --omit=dev
```

```
~/.tiny-mcp.env      (600)   TINY_MCP=1|0, TINY_TOKEN_FILE, TINY_SELF_DEVICE_IDS, TINY_SELF_NAME, TINY_MCP_PERSONAS, TINY_MCP_MESH
~/.tiny-mcp/token    (600)   the JWT, one line
~/.config/systemd/user/{tiny-thinker,tiny-telegram,tiny-voice,reachy-dashboard}.service.d/tiny-mcp.conf
                             → [Service] EnvironmentFile=-%h/.tiny-mcp.env
```

The token needs a browser — the consent click *is* the login. On the Mac:

```sh
TINY_HOME=$(mktemp -d) npx tiny-tech@0.13.9 login        # approve in the browser
python3 -c "import json,os;print(json.load(open(os.environ['TINY_HOME']+'/credentials.json'))['token'])" \
  | ssh reachy 'umask 077; cat > ~/.tiny-mcp/token'      # then: rm -rf $TINY_HOME
ssh reachy 'systemctl --user restart reachy-dashboard tiny-telegram'
```

## Disable · verify

```sh
sed -i s/^TINY_MCP=1/TINY_MCP=0/ ~/.tiny-mcp.env && systemctl --user restart reachy-dashboard tiny-telegram   # soft
rm ~/.tiny-mcp/token                                                                                          # hard: fail-open, tools vanish
python -m pytest tests/test_tiny_mcp.py -q     # allow-list, self-invoke refusal, depth cap, fail-open — no network, no node
```

`GET /api/state` → `fleet: {enabled, running, token, token_days_left, tools}`. Proven 2026-09-17: Ask *"list my devices and ask fomo for its status"* → `use_device {list}` then `use_device {invoke}` receipts in the mind timeline, 33 s round trip.
