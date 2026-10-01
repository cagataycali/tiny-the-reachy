#!/usr/bin/env bash
# Build the strands-agents wheel TINY runs from harness-sdk SOURCE (main), not PyPI.
#
# Why: strands.bidi graduated on main (#4707) with fixes the robot needs today
# (#4642 deferred response.create, #4664 agent.cancel()). PyPI 1.57.1 predates them.
# The sha below is the ONE pin; requirements.txt and MIGRATION.md point here.
#
# Usage:  scripts/strands_wheel.sh            # -> dist/wheels/strands_agents-<ver>-py3-none-any.whl
#         STRANDS_SHA=<sha> scripts/strands_wheel.sh
#         HARNESS_SDK=~/src/harness-sdk scripts/strands_wheel.sh
# Then:   pip install --no-cache-dir "dist/wheels/strands_agents-<ver>-py3-none-any.whl[bidi,bidi-openai]"
#
# Needs: git, python3 with pip (hatchling + hatch-vcs are fetched by pip's build isolation).
# The version is derived by hatch-vcs from the python/v* TAGS, so the clone must carry
# full history and tags (a shallow clone yields a wrong or 0.0.0 version).
set -euo pipefail

STRANDS_SHA="${STRANDS_SHA:-957579a9}"
HARNESS_SDK="${HARNESS_SDK:-/tmp/harness-sdk}"
REPO_URL="${HARNESS_SDK_URL:-https://github.com/strands-agents/harness-sdk.git}"
PYTHON="${PYTHON:-python3}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$HERE/dist/wheels}"

if [ ! -d "$HARNESS_SDK/.git" ]; then
  echo "+ clone $REPO_URL -> $HARNESS_SDK" >&2
  git clone --quiet "$REPO_URL" "$HARNESS_SDK"
fi
git -C "$HARNESS_SDK" fetch --quiet --tags origin
git -C "$HARNESS_SDK" checkout --quiet --detach "$STRANDS_SHA"
if [ "$(git -C "$HARNESS_SDK" rev-list --count HEAD)" -lt 100 ]; then
  echo "refusing: $HARNESS_SDK looks shallow; hatch-vcs needs full history + tags" >&2
  exit 2
fi
if ! git -C "$HARNESS_SDK" tag --list 'python/v*' | grep -q .; then
  echo "refusing: no python/v* tags in $HARNESS_SDK; run git fetch --tags" >&2
  exit 2
fi

mkdir -p "$OUT"
echo "+ pip wheel strands-py @ $(git -C "$HARNESS_SDK" rev-parse --short=9 HEAD)" >&2
"$PYTHON" -m pip wheel --quiet --no-deps -w "$OUT" "$HARNESS_SDK/strands-py"

WHEEL="$(ls -t "$OUT"/strands_agents-*.whl | head -1)"
VERSION="$(basename "$WHEEL" | sed -E 's/^strands_agents-([^-]+)-.*$/\1/')"
echo "wheel:   $WHEEL"
echo "version: $VERSION (harness-sdk @ $STRANDS_SHA)"
