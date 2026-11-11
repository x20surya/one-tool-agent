from agent.search import SearchCache, SearchResult, WebSearch

RESULTS = [SearchResult("Title", "https://example.com", "a snippet", "2026-11-01")]


def test_cache_hit_avoids_second_network_call(tmp_path):
    calls = {"n": 0}

    def fake_fetcher(query, k):
        calls["n"] += 1
        return RESULTS

    cache = SearchCache(str(tmp_path / "c.db"), ttl_seconds=900)
    searcher = WebSearch(cache=cache, fetcher=fake_fetcher)
    assert searcher.search("some query") == RESULTS
    assert searcher.search("Some   Query") == RESULTS  # normalised: same cache key
    assert calls["n"] == 1


def test_cache_expiry_refetches(tmp_path):
    cache = SearchCache(str(tmp_path / "c.db"), ttl_seconds=900)
    cache.put("q", RESULTS, now=1000.0)
    assert cache.get("q", now=1500.0) == RESULTS       # within TTL
    assert cache.get("q", now=1000.0 + 901) is None    # expired


def test_no_cache_fetcher_called_each_time():
    calls = {"n": 0}

    def fake_fetcher(query, k):
        calls["n"] += 1
        return RESULTS

    searcher = WebSearch(fetcher=fake_fetcher)
    searcher.search("q")
    searcher.search("q")
    assert calls["n"] == 2
