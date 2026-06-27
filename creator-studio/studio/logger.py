"""Lightweight dual-output logger for Creator Studio."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class StudioLogger:
    """Mirror messages to stdout, a text log, and a structured summary."""

    project_id: str
    logs_dir: Path
    echo: bool = True
    entries: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.logs_dir / f"{self.project_id}.log"
        self.summary_path = self.logs_dir / f"{self.project_id}.json"

    def info(self, message: str) -> None:
        """Write an informational log line."""

        timestamp = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": timestamp, "level": "INFO", "message": message}
        self.entries.append(entry)

        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} INFO {message}\n")

        if self.echo:
            print(message)

    def write_summary(self, **summary: Any) -> Path:
        """Persist a JSON summary that tooling can read later."""

        payload = {
            "project_id": self.project_id,
            "generated": datetime.now(timezone.utc).isoformat(),
            "entries": self.entries,
            **summary,
        }
        self.summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.summary_path


def get_logger(project_id: str, logs_dir: Path, echo: bool = True) -> StudioLogger:
    """Create a project-scoped logger."""

    return StudioLogger(project_id=project_id, logs_dir=logs_dir, echo=echo)

