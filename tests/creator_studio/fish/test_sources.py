from studio.fish.sources import list_sources


def test_sources_have_required_fields() -> None:
    sources = list_sources()
    assert sources
    for source in sources:
        assert source["name"]
        assert source["url"].startswith("http")
        assert source["source_type"] == "rss"
        assert source["category"]


def test_no_duplicate_source_names() -> None:
    sources = list_sources()
    names = [s["name"] for s in sources]
    assert len(names) == len(set(names))


def test_no_duplicate_source_urls() -> None:
    sources = list_sources()
    urls = [s["url"] for s in sources]
    assert len(urls) == len(set(urls))


def test_editorial_lane_coverage() -> None:
    sources = list_sources()
    categories = {s["category"] for s in sources}
    assert "lesbian" in categories
    assert "bisexual" in categories
    assert "black-trans" in categories


def test_minimum_source_count() -> None:
    assert len(list_sources()) >= 5
