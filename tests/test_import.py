#!/usr/bin/env python3
"""Smoke test: everything imports + tools register, no robot/daemon needed.

Run: python tests/test_import.py   (or: make test-tools)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tools_import():
    from tools import (
        TINY_ALL_TOOLS, TINY_ROBOT_TOOLS, TINY_LOOKOUT_TOOLS,
        TINY_MOTION_TOOLS, TINY_EXPRESSION_TOOLS, TINY_STATE_TOOLS,
        TINY_SENSING_TOOLS, TINY_AUDIO_TOOLS,
    )
    assert len(TINY_ROBOT_TOOLS) >= 12, f"expected >=12 robot tools, got {len(TINY_ROBOT_TOOLS)}"
    print(f"✓ TINY_ROBOT_TOOLS = {len(TINY_ROBOT_TOOLS)} tools")
    print(f"  motion={len(TINY_MOTION_TOOLS)} expression={len(TINY_EXPRESSION_TOOLS)} "
          f"state={len(TINY_STATE_TOOLS)} sensing={len(TINY_SENSING_TOOLS)} "
          f"audio={len(TINY_AUDIO_TOOLS)}")
    print(f"✓ TINY_LOOKOUT_TOOLS = {len(TINY_LOOKOUT_TOOLS)} tools")


def test_factory_import():
    # tiny.py imports must not require a live daemon
    import tiny
    assert hasattr(tiny, "build_agent")
    assert hasattr(tiny, "build_shell_agent")
    assert hasattr(tiny, "build_voice_agent")
    assert hasattr(tiny, "build_tools")
    assert hasattr(tiny, "build_voice_tools")
    print("✓ tiny.py factory functions present")


def test_prompts_build():
    import tiny
    # These build prompts (may probe daemon for live state — must not crash)
    p = tiny._telegram_prompt("123", "tester")
    assert "TELEGRAM CHAT" in p
    v = tiny._voice_prompt()
    assert "VOICE" in v
    t = tiny._thinker_prompt()
    assert "THINKER" in t
    print("✓ all persona prompts build")


def test_common_helpers():
    from tools._reachy_common import clamp, ok, err, LIM_HEAD_PITCH
    assert clamp(100, *LIM_HEAD_PITCH) == 40
    assert clamp(-100, *LIM_HEAD_PITCH) == -40
    assert ok("x")["status"] == "success"
    assert err("x")["status"] == "error"
    print("✓ _reachy_common helpers OK")


if __name__ == "__main__":
    failures = 0
    for fn in [test_common_helpers, test_tools_import, test_factory_import, test_prompts_build]:
        try:
            fn()
        except Exception as e:
            failures += 1
            print(f"✗ {fn.__name__}: {e}")
            import traceback; traceback.print_exc()
    if failures:
        print(f"\n{failures} test(s) FAILED")
        sys.exit(1)
    print("\n✅ all smoke tests passed")
