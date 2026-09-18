from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class PendingJob:
    job_id: str
    user_id: int
    chat_id: int
    text: str
    created_at: float = field(default_factory=time.time)
    engine: str | None = None  # "gemini" | "edge" | "fish"
    gender: str | None = None  # "male" | "female"
    handled: bool = False


class PendingStore:
    """In-memory pending TTS selections; expire after TTL."""

    def __init__(self, ttl_sec: int = 600) -> None:
        self.ttl_sec = ttl_sec
        self._by_user: dict[int, PendingJob] = {}
        self._by_id: dict[str, PendingJob] = {}

    def _purge(self) -> None:
        now = time.time()
        expired = [
            uid
            for uid, job in self._by_user.items()
            if now - job.created_at > self.ttl_sec or job.handled
        ]
        for uid in expired:
            job = self._by_user.pop(uid, None)
            if job:
                self._by_id.pop(job.job_id, None)

    def create(self, user_id: int, chat_id: int, text: str) -> PendingJob:
        self._purge()
        old = self._by_user.pop(user_id, None)
        if old:
            self._by_id.pop(old.job_id, None)
        job = PendingJob(
            job_id=uuid.uuid4().hex[:12],
            user_id=user_id,
            chat_id=chat_id,
            text=text,
        )
        self._by_user[user_id] = job
        self._by_id[job.job_id] = job
        return job

    def get(self, job_id: str) -> PendingJob | None:
        self._purge()
        job = self._by_id.get(job_id)
        if not job:
            return None
        if time.time() - job.created_at > self.ttl_sec:
            self.discard(job)
            return None
        return job

    def discard(self, job: PendingJob) -> None:
        self._by_user.pop(job.user_id, None)
        self._by_id.pop(job.job_id, None)

    def mark_handled(self, job: PendingJob) -> None:
        job.handled = True
        self.discard(job)
