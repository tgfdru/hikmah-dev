import json

from retrieval import config, glossary


def test_glossary_selects_terms_in_text(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps({"terms": [
        {"ar": "التوحيد", "en": "Tawhid / Oneness of God", "usage_rule_ar": "rule", "status": "official_challenge"},
        {"ar": "الزكاة", "en": "Zakah", "definition_en": "obligatory alms", "status": "jamhara"},
        {"ar": "الحج", "en": "Hajj", "status": "jamhara"},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "GLOSSARY_PATH", path)
    glossary.load_glossary.cache_clear()
    hits = glossary.glossary_for(["What does Tawhid mean?", "وأما الزكاةُ فهي ..."])
    assert [t["ar"] for t in hits] == ["التوحيد", "الزكاة"]
    block = glossary.format_for_prompt(hits, "en")
    assert "التوحيد → Tawhid / Oneness of God — rule" in block
    glossary.load_glossary.cache_clear()


def test_committed_glossary_is_valid():
    glossary.load_glossary.cache_clear()
    terms = glossary.load_glossary()
    if not terms:
        return
    official = [t for t in terms if t["status"] == "official_challenge"]
    assert len(official) == 10
    for t in terms:
        assert t["ar"] and (t.get("en") or t.get("jamhara_en"))
        assert t["status"] in {"official_challenge", "jamhara"}
        if t["status"] == "jamhara":
            assert t["source_url"].startswith("https://islamic-content.com/dictionary/word/")
