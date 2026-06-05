"""Small numbered progress output for Day Zero CTO install scripts."""

from __future__ import annotations


class Progress:
    def __init__(self, total: int) -> None:
        self.total = max(total, 1)
        self.current = 0

    def step(self, message: str, detail: str | None = None) -> None:
        self.current += 1
        text = f"[{self.current}/{self.total}] {message}"
        if detail:
            text = f"{text} - {detail}"
        print(text, flush=True)

    def note(self, message: str) -> None:
        print(f"      {message}", flush=True)
