from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryPromptPolicy:
    short_record_threshold: int = 160

    def build_prompt(self, *, record_text: str) -> str:
        cleaned = " ".join(record_text.split())
        if len(cleaned) <= self.short_record_threshold:
            mode = (
                "Short record mode: keep near-verbatim wording with light cleanup only. "
                "Do not invent facts. Do not inflate attempts into confirmations. Do not inflate partial work into completed work."
            )
        else:
            mode = (
                "Long record mode: summarize only what was done and what the result was. "
                "Do not invent facts. Do not inflate attempts into confirmations. Do not inflate partial work into completed work."
            )
        return (
            "You are generating a context summary for internal working memory. "
            f"{mode}\n"
            f"Source record:\n{cleaned}"
        )
