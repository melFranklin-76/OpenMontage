import json

import pytest

from studio.fish import approval_queue
from studio.fish.approval_queue import (
    get_approved,
    list_queue,
    make_item_id,
    review,
    submit,
)


SCRIPT = {
    "show": "What's the LGBT, Fish?",
    "script_date": "2026-07-06",
    "format": "reel",
    "target_duration_seconds": 45,
    "topic": "Black trans organizer leads Milwaukee safety initiative",
    "lane": "trans",
    "sections": [
        {"id": "hook", "narration": "What's the LGBT, Fish?", "duration_seconds": 6, "visual_hint": ""},
        {"id": "story", "narration": "Community safety.", "duration_seconds": 19, "visual_hint": ""},
        {"id": "why_it_matters", "narration": "This matters.", "duration_seconds": 12, "visual_hint": ""},
        {"id": "cta", "narration": "Follow.", "duration_seconds": 8, "visual_hint": ""},
    ],
    "caption": "test caption",
    "hashtags": ["#lgbtq"],
    "source_attribution": {"name": "TransGriot", "url": "https://example.com/1"},
}


def test_make_item_id_uses_date_and_slug() -> None:
    item_id = make_item_id(SCRIPT)
    assert item_id.startswith("2026-07-06_")
    assert "black-trans" in item_id


def test_submit_creates_pending_item(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)

    assert item["status"] == "pending"
    assert item["submitted_at"]
    assert item["script"]["topic"] == SCRIPT["topic"]

    path = tmp_path / f"{item['item_id']}.json"
    assert path.exists()
    stored = json.loads(path.read_text())
    assert stored["status"] == "pending"


def test_review_approves_item(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)
    updated = review(item["item_id"], "approved", notes="Looks good", queue_dir=tmp_path)

    assert updated["status"] == "approved"
    assert updated["reviewed_at"]
    assert updated["review_notes"] == "Looks good"


def test_review_rejects_item(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)
    updated = review(item["item_id"], "rejected", notes="Wrong angle", queue_dir=tmp_path)

    assert updated["status"] == "rejected"


def test_review_rejects_invalid_status(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid status"):
        review(item["item_id"], "bogus", queue_dir=tmp_path)


def test_review_raises_on_missing_item(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        review("nonexistent", "approved", queue_dir=tmp_path)


def test_list_queue_returns_all_items(tmp_path) -> None:
    submit(SCRIPT, queue_dir=tmp_path)
    script2 = dict(SCRIPT, topic="Gay artist wins award", script_date="2026-07-07")
    submit(script2, queue_dir=tmp_path)

    items = list_queue(queue_dir=tmp_path)
    assert len(items) == 2


def test_list_queue_filters_by_status(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)
    script2 = dict(SCRIPT, topic="Gay artist wins award", script_date="2026-07-07")
    submit(script2, queue_dir=tmp_path)

    review(item["item_id"], "approved", queue_dir=tmp_path)

    approved = list_queue(queue_dir=tmp_path, status_filter="approved")
    pending = list_queue(queue_dir=tmp_path, status_filter="pending")

    assert len(approved) == 1
    assert len(pending) == 1


def test_get_approved_returns_only_approved(tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)
    submit(dict(SCRIPT, topic="Another story"), queue_dir=tmp_path)

    review(item["item_id"], "approved", queue_dir=tmp_path)

    approved = get_approved(queue_dir=tmp_path)
    assert len(approved) == 1
    assert approved[0]["status"] == "approved"


def test_list_queue_empty_dir(tmp_path) -> None:
    assert list_queue(queue_dir=tmp_path / "nonexistent") == []


def test_main_submit_and_list(monkeypatch, tmp_path) -> None:
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(SCRIPT))
    queue_dir = tmp_path / "queue"

    monkeypatch.setattr(
        "sys.argv",
        ["approval_queue", "submit", "--script", str(script_path), "--queue-dir", str(queue_dir)],
    )
    assert approval_queue.main() == 0

    monkeypatch.setattr(
        "sys.argv",
        ["approval_queue", "list", "--queue-dir", str(queue_dir)],
    )
    assert approval_queue.main() == 0


def test_main_review(monkeypatch, tmp_path) -> None:
    item = submit(SCRIPT, queue_dir=tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "approval_queue", "review", item["item_id"],
            "--status", "approved",
            "--notes", "Ship it",
            "--queue-dir", str(tmp_path),
        ],
    )
    assert approval_queue.main() == 0

    stored = json.loads((tmp_path / f"{item['item_id']}.json").read_text())
    assert stored["status"] == "approved"
    assert stored["review_notes"] == "Ship it"
