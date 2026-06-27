from __future__ import annotations

import json
from pathlib import Path

from studio.logger import get_logger


def test_logger_writes_terminal_log_and_summary(tmp_path: Path, capsys) -> None:
    logger = get_logger(project_id="demo-project", logs_dir=tmp_path, echo=True)

    logger.info("Scanning inbox...")
    summary_path = logger.write_summary(status="ready", total=3)

    captured = capsys.readouterr()
    log_path = tmp_path / "demo-project.log"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert "Scanning inbox..." in captured.out
    assert "Scanning inbox..." in log_path.read_text(encoding="utf-8")
    assert summary["project_id"] == "demo-project"
    assert summary["status"] == "ready"
    assert summary["total"] == 3
    assert summary["entries"][0]["message"] == "Scanning inbox..."

