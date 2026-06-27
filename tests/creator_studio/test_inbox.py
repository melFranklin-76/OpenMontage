from __future__ import annotations

from pathlib import Path

from studio.inbox import scan_inbox


def test_scan_inbox_classifies_media_files(tmp_path: Path) -> None:
    (tmp_path / "clip.mp4").write_bytes(b"video")
    (tmp_path / "photo.JPG").write_bytes(b"image")
    (tmp_path / "voice.m4a").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    result = scan_inbox(tmp_path)

    assert [path.name for path in result["videos"]] == ["clip.mp4"]
    assert [path.name for path in result["images"]] == ["photo.JPG"]
    assert [path.name for path in result["audio"]] == ["voice.m4a"]
    assert result["total"] == 3


def test_scan_inbox_handles_missing_directory(tmp_path: Path) -> None:
    result = scan_inbox(tmp_path / "missing")

    assert result == {"videos": [], "images": [], "audio": [], "total": 0}

