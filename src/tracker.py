"""
tracker.py — Tracks daily application counts, prevents duplicates,
and maintains the master applications log.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("job_autopilot.tracker")


class ApplicationTracker:
    def __init__(self, cfg: dict):
        self.db_path = Path(cfg["output"]["applications_db"])
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        """Load the applications database from disk."""
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"applications": [], "daily_counts": {}}

    def _save(self):
        """Persist the applications database to disk."""
        self.db_path.write_text(
            json.dumps(self._data, indent=2, default=str),
            encoding="utf-8"
        )

    def count_today(self) -> int:
        """Return how many applications have been logged today."""
        today = str(date.today())
        return self._data.get("daily_counts", {}).get(today, 0)

    def already_applied(self, url: str) -> bool:
        """Check if we've already applied to this job URL."""
        applied_urls = {app.get("url", "") for app in self._data.get("applications", [])}
        return url in applied_urls

    def log_application(self, job: dict):
        """Log a completed/attempted application."""
        today = str(date.today())
        
        record = {
            "date": today,
            "timestamp": datetime.now().isoformat(),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "platform": job.get("platform", ""),
            "url": job.get("url", ""),
            "location": job.get("location", ""),
            "status": job.get("form_status", "unknown"),
            "tab_index": job.get("tab_index"),
            "resume_file": job.get("resume_path", ""),
            "cover_letter_file": job.get("cover_letter_path", ""),
        }
        
        self._data.setdefault("applications", []).append(record)
        
        # Update daily count
        counts = self._data.setdefault("daily_counts", {})
        counts[today] = counts.get(today, 0) + 1
        
        self._save()
        log.debug(f"Logged: {record['company']} — {record['title']} [{record['status']}]")

    def get_all(self) -> list[dict]:
        return self._data.get("applications", [])

    def get_today(self) -> list[dict]:
        today = str(date.today())
        return [a for a in self.get_all() if a.get("date") == today]

    def stats(self) -> dict:
        apps = self.get_all()
        today_count = self.count_today()
        platforms = {}
        for a in apps:
            p = a.get("platform", "Unknown")
            platforms[p] = platforms.get(p, 0) + 1
        
        return {
            "total_applications": len(apps),
            "applied_today": today_count,
            "by_platform": platforms,
        }
