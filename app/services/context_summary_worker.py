from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, DEFAULT_CONTEXT_CENTER_DIR, build_context_storage_paths
from app.services.context_writer import ContextWriter
from app.services.summary_prompt_policy import SummaryPromptPolicy


@dataclass
class ContextSummaryWorker:
    paths: ContextStoragePaths
    max_concurrency: int = 1
    rate_limit: int = 1
    active_jobs: int = 0
    queued_jobs: list[dict[str, str]] = field(default_factory=list)
    failed_jobs: list[dict[str, str]] = field(default_factory=list)
    prompt_policy: SummaryPromptPolicy = field(default_factory=SummaryPromptPolicy)

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = DEFAULT_CONTEXT_CENTER_DIR) -> "ContextSummaryWorker":
        return cls(paths=build_context_storage_paths(base_dir))

    def enqueue_summary_write(self, *, session_id: str, summary_text: str, role: str = "system", replace: bool = True) -> dict[str, int | str]:
        job = {
            "session_id": session_id,
            "summary_text": summary_text,
            "role": role,
            "replace": "1" if replace else "0",
            "prompt": self.build_summary_prompt(summary_text),
        }
        self.queued_jobs.append(job)
        return self.drain_once()

    def build_summary_prompt(self, summary_text: str) -> str:
        return self.prompt_policy.build_prompt(record_text=summary_text)

    def drain_once(self) -> dict[str, int | str]:
        if self.active_jobs >= self.max_concurrency or not self.queued_jobs:
            return {
                "processed": 0,
                "queued": len(self.queued_jobs),
                "active": self.active_jobs,
            }
        job = self.queued_jobs.pop(0)
        self.active_jobs += 1
        try:
            writer = ContextWriter(paths=self.paths)
            summary_text = job["summary_text"]
            if summary_text.startswith("FAIL:"):
                raise RuntimeError(summary_text)
            if job.get("replace") == "1":
                writer.replace_summary_event(
                    session_id=job["session_id"],
                    role=job["role"],
                    message=summary_text,
                )
            else:
                writer.append_summary_event(
                    session_id=job["session_id"],
                    role=job["role"],
                    message=summary_text,
                )
            return {
                "processed": 1,
                "queued": len(self.queued_jobs),
                "active": self.active_jobs,
                "session_id": job["session_id"],
            }
        except Exception:
            self.failed_jobs.append(job)
            return {
                "processed": 0,
                "queued": len(self.queued_jobs),
                "active": self.active_jobs,
                "failed": len(self.failed_jobs),
                "session_id": job["session_id"],
            }
        finally:
            self.active_jobs -= 1
