#!/usr/bin/env bash
# Ship dashboard/ (+ prebuilt frontend/dist) to the Reachy Mini and restart the user unit.
#   dashboard/deploy/sync.sh            # rsync + restart
#   REACHY_SSH=pollen@192.168.1.5 dashboard/deploy/sync.sh
# Never copies .env, node_modules or frontend sources. Password auth: export SSHPASS=… and it uses sshpass.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${REACHY_SSH:-pollen@192.168.1.5}"
SSH=(ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=no)
[ -n "${SSHPASS:-}" ] && SSH=(sshpass -e "${SSH[@]}")
RS="${SSH[*]}"
rsync -az --delete -e "$RS" \
  --exclude node_modules --exclude src --exclude public --exclude 'package*.json' --exclude '*.ts' --exclude 'tsconfig*' \
  --exclude '.vite' --exclude '__pycache__' --exclude 'index.html' --exclude scripts \
  "$HERE/dashboard/" "$HOST:tiny-the-reachy/dashboard/"
# index.html is the built one in dist/ — re-include it explicitly
rsync -az -e "$RS" "$HERE/dashboard/frontend/dist/" "$HOST:tiny-the-reachy/dashboard/frontend/dist/" 2>/dev/null || true
"${SSH[@]}" "$HOST" 'mkdir -p ~/.config/systemd/user && cp tiny-the-reachy/dashboard/deploy/reachy-dashboard.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now reachy-dashboard.service && systemctl --user restart reachy-dashboard.service && sleep 2 && systemctl --user is-active reachy-dashboard.service && curl -s localhost:8097/api/health'
echo
