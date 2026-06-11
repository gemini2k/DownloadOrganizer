from __future__ import annotations

from download_organizer.bookmarks import duplicate_urls
from download_organizer.config import categorize_bookmark


def test_categorize_bookmark():
    assert categorize_bookmark("github.com", "repo", "https://github.com/x") == "Development"
    assert categorize_bookmark("openai.com", "OpenAI", "https://openai.com") == "AI"
    assert categorize_bookmark("data.go.kr", "공공데이터", "https://data.go.kr") == "Public"
    assert categorize_bookmark("example.org", "random", "https://example.org") == "Etc"


def test_duplicate_urls():
    rows = [
        {"url": "https://a.com", "name": "a1"},
        {"url": "https://a.com", "name": "a2"},
        {"url": "https://b.com", "name": "b"},
    ]
    dups = duplicate_urls(rows)
    assert {r["name"] for r in dups} == {"a1", "a2"}
