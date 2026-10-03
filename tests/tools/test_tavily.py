from homelab_creator.tools.search import parse_tavily, tavily_search


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_parse_tavily_drops_poc_and_keeps_urls():
    hits = parse_tavily(
        {
            "results": [
                {"title": "Edge case", "url": "https://example.invalid/writeup", "content": "auth bypass class"},
                {"title": "bad", "url": "https://example.invalid/exploit-poc", "content": "clean"},
            ]
        }
    )
    assert hits == [
        {
            "title": "Edge case",
            "url": "https://example.invalid/writeup",
            "snippet": "auth bypass class",
        }
    ]


def test_tavily_search_posts_bearer_not_query_key():
    captured: dict = {}

    def opener(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = req.data or b""
        return _Resp(b'{"results":[{"title":"A","url":"https://example.invalid/a","content":"note"}]}')

    hits = tavily_search("public pentest clinic", "tvly-test", opener=opener)
    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["auth"] == "Bearer tvly-test"
    assert b"tvly-test" not in captured["body"]
    assert hits[0]["title"] == "A"
