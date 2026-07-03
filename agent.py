"""TINY — Reachy Mini expressive agent (REPL entry point).

Thin wrapper around `tiny.build_shell_agent()`. All persona/tool/prompt logic
lives in `tiny.py` — the single source of truth shared by every persona
(shell / voice / telegram / thinker).

Run:  make run  ·  make run-bare  ·  make ask Q="..."  ·  python agent.py
"""
import os

from tiny import build_shell_agent, _shell_prompt

agent = build_shell_agent()


def main() -> None:
    print("TINY ready.")
    print(f"Tools loaded: {len(agent.tool_names)}")
    print("Type 'exit' / 'quit' / 'q' to leave, Ctrl-C to force.\n")

    while True:
        try:
            user_input = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.strip().lower() in ("exit", "quit", "q"):
            break
        if not user_input.strip():
            continue
        # refresh live state into system prompt each turn
        try:
            agent.system_prompt = _shell_prompt()
        except Exception as e:
            print(f"⚠️  state refresh failed: {e}")
        agent(user_input)


if __name__ == "__main__":
    main()
