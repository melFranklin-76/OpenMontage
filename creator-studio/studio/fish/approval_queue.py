"""Approval queue for What's the LGBT, Fish?

Human checkpoint between script generation and video rendering/publishing.
Scripts enter the queue as "pending"; a human reviews and marks them
"approved", "rejected", or "revision_needed" before the render pipeline
picks them up. Nothing renders or posts without explicit approval.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUEUE_DIR = Path("creator-studio/out/fish/queue")
VALID_STATUSES = ("pending", "approved", "rejected", "revision_needed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _queue_path(queue_dir: Path, item_id: str) -> Path:
    return queue_dir / f"{item_id}.json"


def _read_item(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_item(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_item_id(script: dict) -> str:
    """Build a queue item ID from the script date and topic."""
    date_part = script.get("script_date", "undated")
    topic = script.get("topic", "untitled")
    slug = topic.lower()[:40].strip()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = slug.strip().replace(" ", "-")
    return f"{date_part}_{slug}"


def submit(script: dict, queue_dir: Path = QUEUE_DIR) -> dict[str, Any]:
    """Submit a reel script to the approval queue as pending."""
    item_id = make_item_id(script)
    item = {
        "item_id": item_id,
        "status": "pending",
        "submitted_at": _now_iso(),
        "reviewed_at": None,
        "review_notes": None,
        "script": script,
    }
    _write_item(_queue_path(queue_dir, item_id), item)
    return item


def review(
    item_id: str,
    status: str,
    notes: str = "",
    queue_dir: Path = QUEUE_DIR,
) -> dict[str, Any]:
    """Update the status of a queued item after human review."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}, must be one of {VALID_STATUSES}")

    path = _queue_path(queue_dir, item_id)
    if not path.exists():
        raise FileNotFoundError(f"Queue item {item_id!r} not found in {queue_dir}")

    item = _read_item(path)
    item["status"] = status
    item["reviewed_at"] = _now_iso()
    item["review_notes"] = notes or None
    _write_item(path, item)
    return item


def list_queue(
    queue_dir: Path = QUEUE_DIR,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List all items in the queue, optionally filtered by status."""
    if not queue_dir.exists():
        return []

    items = []
    for path in sorted(queue_dir.glob("*.json")):
        item = _read_item(path)
        if status_filter and item.get("status") != status_filter:
            continue
        items.append(item)
    return items


def get_approved(queue_dir: Path = QUEUE_DIR) -> list[dict[str, Any]]:
    """Return only approved items, ready for rendering."""
    return list_queue(queue_dir, status_filter="approved")


def main() -> int:
    parser = argparse.ArgumentParser(description="FISH approval queue")
    sub = parser.add_subparsers(dest="command", required=True)

    submit_p = sub.add_parser("submit", help="Submit a reel script for approval")
    submit_p.add_argument("--script", required=True, help="Path to reel script JSON")
    submit_p.add_argument("--queue-dir", default=str(QUEUE_DIR))

    review_p = sub.add_parser("review", help="Review a queued item")
    review_p.add_argument("item_id")
    review_p.add_argument("--status", required=True, choices=VALID_STATUSES)
    review_p.add_argument("--notes", default="")
    review_p.add_argument("--queue-dir", default=str(QUEUE_DIR))

    list_p = sub.add_parser("list", help="List queued items")
    list_p.add_argument("--status", choices=VALID_STATUSES)
    list_p.add_argument("--queue-dir", default=str(QUEUE_DIR))

    args = parser.parse_args()
    queue_dir = Path(args.queue_dir)

    if args.command == "submit":
        script = json.loads(Path(args.script).read_text())
        item = submit(script, queue_dir=queue_dir)
        print(f"Submitted [{item['item_id']}] — status: pending")
        return 0

    if args.command == "review":
        item = review(args.item_id, args.status, args.notes, queue_dir=queue_dir)
        print(f"Reviewed [{item['item_id']}] — status: {item['status']}")
        return 0

    if args.command == "list":
        items = list_queue(queue_dir, status_filter=args.status)
        if not items:
            print("Queue is empty.")
            return 0
        for item in items:
            script = item.get("script", {})
            print(
                f"[{item['status']:16s}] {item['item_id']}"
                f"  [{script.get('lane', '?')}] {script.get('topic', '?')[:60]}"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
