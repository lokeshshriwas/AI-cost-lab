from costlab.cache import ResponseCache


def test_key_ignores_dict_order():
    a = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    b = {"max_tokens": 10, "messages": [{"content": "hi", "role": "user"}], "model": "m"}
    assert ResponseCache.key(a) == ResponseCache.key(b)


def test_key_changes_with_any_setting():
    base = {"model": "m", "messages": [], "max_tokens": 10}
    assert ResponseCache.key(base) != ResponseCache.key({**base, "max_tokens": 11})


def test_put_then_get_round_trips(tmp_path):
    cache = ResponseCache(tmp_path)
    key = ResponseCache.key({"x": 1})
    assert cache.get(key) is None
    cache.put(key, {"text": "hello"})
    assert cache.get(key) == {"text": "hello"}
