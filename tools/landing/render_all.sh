#!/bin/sh
# render_all.sh — every landing asset from the same look (twin.js VIEWS): hero still (+660w), the 48-frame curious1 sequence,
# the four THE BODY layers. Offline, from the full-res pack tools/landing/model-hi (gitignored; build_twin_model.py without decimation).
# usage: sh tools/landing/render_all.sh [hero|seq|body|all]   (~10 min for all on SwiftShader)
set -e
cd "$(dirname "$0")/../.."
HI="model=/tools/landing/model-hi/"
R="node tools/landing/render_twin.mjs"
what=${1:-all}
if [ "$what" = hero ] || [ "$what" = all ]; then
  # f00 = the LCP still (the hero scrub starts here); f24 = the reduced-motion still and the scrub's last frame
  NOTRIM=1 $R still curious1 0 docs/assets/landing/hero-curious1-f00.webp 1100 1300 "view=hero&$HI"
  NOTRIM=1 $R still curious1 0 docs/assets/landing/hero-curious1-f00-660.webp 660 780 "view=hero&$HI"
  NOTRIM=1 $R still curious1 24 docs/assets/landing/hero-curious1-f24.webp 1100 1300 "view=hero&$HI"
  NOTRIM=1 $R still curious1 24 docs/assets/landing/hero-curious1-f24-660.webp 660 780 "view=hero&$HI"
fi
if [ "$what" = seq ] || [ "$what" = all ]; then
  RESUME=1 NOTRIM=1 $R seq curious1 docs/assets/landing/seq/curious1 48 660 780 "view=emotion&$HI"
fi
if [ "$what" = heroseq ] || [ "$what" = all ]; then
  # the hero's scroll-turn: poses 0..24 of curious1 (t 0 → 2.0 s) from the hero camera; frame 24 = the still
  SEQ_FROM=0 SEQ_TO=24 RESUME=1 NOTRIM=1 $R seq curious1 docs/assets/landing/seq/hero 25 660 780 "view=hero&$HI"
fi
if [ "$what" = body ] || [ "$what" = all ]; then
  # one camera, NOTRIM, so the four layers stack pixel-exact; only the base keeps the ground shadow
  NOTRIM=1 $R still curious1 0 docs/assets/landing/body/base.webp 760 900 "view=body&$HI&only=body_foot_3dprint,body_down_3dprint"
  NOTRIM=1 $R still curious1 0 docs/assets/landing/body/stewart.webp 760 900 "view=body&$HI&noshadow=1&only=dc15_a01_horn_dummy,dc15_a01_horn_dummy_2,dc15_a01_horn_dummy_3,dc15_a01_horn_dummy_4,dc15_a01_horn_dummy_5,dc15_a01_horn_dummy_6,stewart_link_rod,stewart_link_rod_2,stewart_link_rod_3,stewart_link_rod_4,stewart_link_rod_5,stewart_link_rod_6"
  NOTRIM=1 $R still curious1 0 docs/assets/landing/body/head.webp 760 900 "view=body&$HI&noshadow=1&only=xl_330,null"
  NOTRIM=1 $R still curious1 0 docs/assets/landing/body/antennas.webp 760 900 "view=body&$HI&noshadow=1&only=dc15_a01_horn_dummy_7,dc15_a01_horn_dummy_8"
fi
