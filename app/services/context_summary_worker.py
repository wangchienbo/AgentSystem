from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, build_context_storage_paths
from app.services.context_writer import ContextWriter


@dataclass
class ContextSummaryWorker:
    paths: ContextStoragePaths
    max_concurrency: int = 1
    rate_limit: int = 1
    active_jobs: int = 0
    queued_jobs: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> "ContextSummaryWorker":
        return cls(paths=build_context_storage_paths(base_dir))

    def enqueue_summary_write(self, *, session_id: str, summary_text: str, role: str = "system", replace: bool = True) -> dict[str, int | str]:
        job = {
            "session_id": session_id,
            "summary_text": summary_text,
            "role": role,
            "replace": "1" if replace else "0",
        }
        self.queued_jobs.append(job)
        return self.drain_once()

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
            if job.get("replace") == "1":
                writer.replace_summary_event(
                    session_id=job["session_id"],
                    role=job["role"],
                    message=job["summary_text"],
                )
            else:
                writer.append_summary_event(
                    session_id=job["session_id"],
                    role=job["role"],
                    message=job["summary_text"],
                )
            return {
                "processed": 1,
                "queued": len(self.queued_jobs),
                "active": self.active_jobs,
                "session_id": job["session_id"],
            }
        finally:
            self.active_jobs -= 1
