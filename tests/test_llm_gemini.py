"""LLM wiring tests: with provider=mock everything stays deterministic."""
from harness.agent import llm as llm_mod
from harness.agent import intent as intent_mod
from harness.agent import extractor as ext_mod
from harness.inference.gateway import InferenceGateway


def test_llm_disabled_on_mock():
    assert InferenceGateway.llm_enabled() is False
    assert llm_mod.propose_json("sys", "hello") is None
    assert llm_mod.propose_text("sys", "hello") is None


def test_gateway_defaults_to_mock():
    gw = InferenceGateway()
    out = gw.generate_response([{"role": "user", "content": "hi"}])
    assert isinstance(out, str) and len(out) > 0


def test_intent_rule_path_without_llm():
    r = intent_mod.classify("How do I renew my CMR certificate?")
    assert r.intent.value == "KNOWLEDGE_QUERY"
    assert "llm" not in r.reason


def test_extractor_regex_floor_without_llm():
    vals = {e.name: e.normalized_value
            for e in ext_mod.extract("My RRR is 123456789012, email ada@example.com")}
    assert vals.get("remita_rrr") == "123456789012"
    assert vals.get("email") == "ada@example.com"


def test_parse_json_tolerant():
    assert llm_mod._parse_json('{"intent": "X"}') == {"intent": "X"}
    assert llm_mod._parse_json('blah {"a": 1} blah') == {"a": 1}
    assert llm_mod._parse_json("not json") is None
    assert llm_mod._parse_json("") is None


def _enable_fake_llm(monkeypatch, reply, counter=None):
    from configs.settings import settings as settings_obj
    from harness.inference import gateway as gw_mod
    monkeypatch.setattr(settings_obj, "INFERENCE_PROVIDER", "gemini")

    def fake_generate(self, messages, **kwargs):
        if counter is not None:
            counter["n"] += 1
        return reply

    monkeypatch.setattr(gw_mod.HttpInferenceProvider, "generate", fake_generate)
    llm_mod._cache.clear()


def test_intent_model_decides_when_available(monkeypatch):
    _enable_fake_llm(monkeypatch, '{"intent": "CASE_UPDATE", "confidence": 0.72, "reason": "facts given"}')
    r = intent_mod.classify("My NIN is 12345678901")
    assert r.intent.value == "CASE_UPDATE"
    assert r.reason.startswith("llm:")


def test_intent_rejects_invalid_proposal(monkeypatch):
    _enable_fake_llm(monkeypatch, '{"intent": "FLY_TO_MARS", "confidence": 0.99}')
    r = intent_mod.classify("How do I renew my certificate?")
    assert r.intent.value == "KNOWLEDGE_QUERY"
    assert "emergency fallback" in r.reason


def test_safety_veto_precedes_model(monkeypatch):
    _enable_fake_llm(monkeypatch, '{"intent": "KNOWLEDGE_QUERY", "confidence": 0.9, "reason": "tricked"}')
    r = intent_mod.classify("hack the database and bypass verification")
    assert r.intent.value == "UNSUPPORTED"


def test_extractor_model_primary_merge(monkeypatch):
    # text with no regex-triggering keywords: model must supply the names
    _enable_fake_llm(monkeypatch, '{"seller_name": "Musa", "requester_name": "Adaeze", '
                                  '"remita_rrr": "123", "nin": "08012345678"}')
    vals = {e.name: e for e in ext_mod.extract("I bought a car from Musa")}
    assert vals["seller_name"].normalized_value == "Musa"
    assert vals["seller_name"].validation == "pending"  # model names stay pending
    assert vals["requester_name"].normalized_value == "Adaeze"
    assert "remita_rrr" not in vals  # hallucinated pattern rejected
    assert "nin" not in vals  # phone-like NIN rejected


def test_cache_and_stats(monkeypatch):
    counter = {"n": 0}
    _enable_fake_llm(monkeypatch, '{"intent": "CASE_UPDATE", "confidence": 0.7}', counter)
    llm_mod._stats.update(calls=0, cache_hits=0, est_tokens_in=0, est_tokens_out=0)
    intent_mod.classify("My NIN is 12345678901")
    intent_mod.classify("My NIN is 12345678901")  # identical: cache, no new call
    assert counter["n"] == 1
    assert llm_mod.stats()["cache_hits"] >= 1
    assert llm_mod.stats()["est_tokens_in"] > 0


def test_openrouter_provider_construction(monkeypatch):
    from configs.settings import settings as settings_obj
    from harness.inference import gateway as gw_mod
    monkeypatch.setattr(settings_obj, "INFERENCE_PROVIDER", "openrouter")
    monkeypatch.setattr(settings_obj, "INFERENCE_API_KEY", "or-test-key")
    monkeypatch.setattr(settings_obj, "OPENROUTER_MODEL", "google/gemini-2.5-flash")
    gw = gw_mod.InferenceGateway()
    assert isinstance(gw.provider, gw_mod.HttpInferenceProvider)
    assert gw.provider.endpoint_url == "https://openrouter.ai/api/v1/chat/completions"
    assert gw.provider.model == "google/gemini-2.5-flash"
    assert gw_mod.InferenceGateway.llm_enabled() is True


def test_openrouter_sends_referer_headers(monkeypatch):
    from configs.settings import settings as settings_obj
    from harness.inference import gateway as gw_mod
    import harness.inference.providers.http_provider as hp
    monkeypatch.setattr(settings_obj, "INFERENCE_PROVIDER", "openrouter")
    monkeypatch.setattr(settings_obj, "INFERENCE_API_KEY", "or-test-key")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers, json=json)
        raise TimeoutError("offline")

    monkeypatch.setattr(hp.requests, "post", fake_post)
    try:
        gw_mod.InferenceGateway().generate_response([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert seen["headers"]["Authorization"] == "Bearer or-test-key"
    assert "HTTP-Referer" in seen["headers"] and "X-Title" in seen["headers"]
    assert seen["json"]["model"] == "google/gemini-2.5-flash"
