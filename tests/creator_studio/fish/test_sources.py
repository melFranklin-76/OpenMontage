from studio.fish.sources import list_sources


def test_sources_have_required_fields() -> None:
    sources = list_sources()
    assert sources
    for source in sources:
        assert source["name"]
        assert source["url"].startswith("http")
        assert source["source_type"] == "rss"
