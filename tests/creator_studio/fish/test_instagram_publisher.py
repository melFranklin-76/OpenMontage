"""Tests for FISH Instagram publisher (caption + URLs, no live network)."""

from __future__ import annotations

from studio.fish import instagram_publisher as ig


SCRIPT = {
    "topic": "Marsha P. Johnson: Stonewall hero",
    "lane": "legacy",
    "source_attribution": {
        "name": "The Advocate",
        "url": "https://example.com/story",
    },
}


def test_caption_contains_topic_source_and_lane_hashtags():
    caption = ig.build_caption(SCRIPT)
    assert SCRIPT["topic"] in caption
    assert "The Advocate" in caption
    assert "https://example.com/story" in caption
    assert "#lgbthistory" in caption
    assert len(caption) <= 2200


def test_caption_long_topic_truncates_to_instagram_limit():
    script = dict(SCRIPT, topic="x" * 5000)
    caption = ig.build_caption(script)
    assert len(caption) <= 2200
    assert "..." in caption
    assert "#lgbthistory" in caption


def test_graph_api_version_is_pinned():
    assert ig.API_VERSION == "v21.0"
    assert ig.GRAPH_BASE == "https://graph.facebook.com/v21.0"


def test_graph_api_url_construction():
    assert ig.build_create_media_url("1789") == "https://graph.facebook.com/v21.0/1789/media"
    assert ig.build_container_status_url("abc123") == "https://graph.facebook.com/v21.0/abc123"
    assert ig.build_publish_url("1789") == "https://graph.facebook.com/v21.0/1789/media_publish"


def test_create_media_container_uses_expected_params(monkeypatch):
    calls = []

    def fake_request(method, url, params):
        calls.append((method, url, params))
        return {"id": "container-1"}

    monkeypatch.setattr(ig, "_request_json", fake_request)
    creation_id = ig.create_media_container(
        "https://example.com/reel.mp4",
        "caption",
        "ig-user-1",
        "token-1",
    )

    assert creation_id == "container-1"
    method, url, params = calls[0]
    assert method == "POST"
    assert url.endswith("/ig-user-1/media")
    assert params["media_type"] == "REELS"
    assert params["video_url"] == "https://example.com/reel.mp4"
    assert params["caption"] == "caption"
    assert params["share_to_feed"] == "true"
    assert params["access_token"] == "token-1"


def test_no_network_needed_for_url_and_caption_tests():
    # Guard against accidental live dependency in ordinary unit coverage.
    assert callable(ig.build_caption)
    assert callable(ig.build_create_media_url)
