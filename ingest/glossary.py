"""Build data/glossary.json: approved equivalents of Islamic terms.

    python -m ingest.glossary          # uses cached pages in data/raw/jamhara/ when present

Two tiers, in priority order:
  1. "official_challenge" - the 10 terms (with usage rules) printed in the challenge's
     reference pack (docs/reference/challenge-reference-pack.md, page 8). Authoritative.
  2. "jamhara" - English (and Urdu when published) equivalents and definitions taken
     verbatim from the Jamhara dictionary (islamic-content.com/dictionary), which
     the challenge names as the reference for terminology. Each entry keeps its URL.

Nothing is written by us: a term with no published English equivalent is left out.
Crawling is polite: public pages only (robots.txt allows /dictionary/), one
request every 2 seconds, pages cached on disk so re-runs do not refetch.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from datetime import date

import httpx

from retrieval import config
from retrieval.normalize_ar import norm

BASE = "https://islamic-content.com/dictionary"
CATEGORIES = [1, 1063, 1792, 266, 428, 543, 670, 707]  # the 8 subject dictionaries
USER_AGENT = "Mozilla/5.0 (compatible; MueenKnowledgeBuilder/1.0; +https://sheykak.com)"
DELAY = 2.0
CACHE = config.RAW_DIR / "jamhara"

# From the challenge reference pack, "نماذج لقاموس المصطلحات الأساسية" (page 8).
OFFICIAL = [
    ("الإسلام", "Islam", "دين الاستسلام لله بالتوحيد والانقياد له بالطاعة، ويشرح بحسب السياق ولا يختزل في معنى ثقافي عام."),
    ("التوحيد", "Tawhid / Oneness of God", "يفضل إبقاء المصطلح مع شرح معناه إفراد الله بالربوبية والألوهية ووصفه بما جاء الوحي به من أسمائه الحسنى؛ ولا يختزل في ترجمة قد توحي بمجرد الوحدانية العددية."),
    ("العبادة", "Worship", "تشمل أعمال القلب والقول والعمل التي يتقرب بها العبد إلى الله، ولا تحصر في الشعائر فقط."),
    ("النبوة", "Prophethood", "تستخدم للدلالة على اصطفاء الأنبياء بالوحي، مع التمييز بينها وبين القيادة الدينية البشرية."),
    ("الوحي", "Revelation", "يشرح بوصفه ما أوحاه الله إلى أنبيائه، مع تجنب استعمالات فضفاضة قد توهم الإلهام الشخصي."),
    ("الشريعة", "Sharia / Islamic law and guidance", "يشرح بحسب السياق، ولا يختزل في العقوبات أو القانون الجنائي."),
    ("الحديث", "Hadith", "ما نُقل عن النبي صلى الله عليه وسلم من قول أو فعل أو تقرير ونحو ذلك، مع بيان درجة الثبوت عند الاستدلال."),
    ("السنة", "Sunnah", "هدي النبي صلى الله عليه وسلم وطريقته، ويحدد المقصود بحسب السياق العلمي."),
    ("الفتوى", "Fatwa", "جواب شرعي يصدره مؤهل في واقعة أو سؤال؛ ولا يساوى بالمعلومة العامة."),
    ("الدعوة", "Da‘wah / Invitation to Islam", "التعريف بالإسلام والدعوة إليه بالحكمة، ويختار المقابل بحسب السياق والجمهور."),
]

# Terms that come up most in da'wah conversations with non-Muslims.
TARGETS = """
الإيمان الإحسان الربوبية الألوهية الأسماء والصفات الشرك الكفر الجهاد الصلاة الزكاة الصيام الحج
العمرة الشهادتان القبلة الكعبة الطواف الحجاب الحلال الحرام المكروه الفرض الواجب المستحب البدعة
الاجتهاد الإجماع القياس الفقه المذهب العقيدة الغيب الملائكة القدر اليوم الآخر الجنة النار البعث
التوبة الاستغفار الدعاء الذكر التقوى الصبر الرسول النبي القرآن التفسير السيرة الصحابة الأمة
الحدود القصاص الردة الذمي أهل الكتاب المسلم المؤمن الإخلاص المعجزة الرسالة الآخرة الطهارة
الوضوء الغسل النية الهجرة النكاح الطلاق المهر العدة القوامة الميراث الجزية الخلافة الولاء والبراء
المحرم الرضاع التيمم الأضحية الصدقة الحسبة الفطرة الخلق التوكل الحكمة الموعظة الحسنة
""".split("\n")


# Other headwords under which Jamhara lists the same concept.
ALTERNATES = {
    "الصيام": ["الصوم"], "الآخرة": ["الدار الآخرة", "اليوم الآخر"],
    "الأسماء والصفات": ["توحيد الأسماء والصفات"], "الألوهية": ["توحيد الألوهية", "الإلهية"],
    "الربوبية": ["توحيد الربوبية"], "الولاء والبراء": ["الولاء", "الموالاة"],
    "الميراث": ["الإرث", "المواريث"], "الصدقة": ["صدقة التطوع", "الصدقات"],
    "التوكل": ["التوكل على الله"], "الطواف": ["طواف القدوم", "الطواف بالبيت"],
    "القوامة": ["قوامة الرجل"],
}


def _targets() -> list[str]:
    words: list[str] = []
    for line in TARGETS:
        # multi-word terms are joined with a space in the source list above
        for item in re.split(r"\s{2,}", line.strip()):
            words += [w for w in item.split(" ") if w]
    multi = ["الأسماء والصفات", "اليوم الآخر", "أهل الكتاب", "الولاء والبراء", "الموعظة الحسنة"]
    singles = [w for w in words if all(w not in m.split() for m in multi)]
    return list(dict.fromkeys(multi + singles))


def _key(term: str) -> str:
    return re.sub(r"[^ء-ي ]", "", norm(term)).strip()


def _get(url: str, cache_name: str) -> str | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / cache_name
    if path.exists():
        return path.read_text(encoding="utf-8") or None
    time.sleep(DELAY)
    try:
        r = httpx.get(url, timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    except httpx.HTTPError as exc:
        print(f"  failed {url}: {exc}", file=sys.stderr)
        return None
    text = r.text if r.status_code == 200 else ""
    path.write_text(text, encoding="utf-8")
    return text or None


def _word_index() -> dict[str, tuple[str, str]]:
    """{normalized term: (word id, displayed term)} from the category pages."""
    index: dict[str, tuple[str, str]] = {}
    for cat in CATEGORIES:
        page = _get(f"{BASE}/term/{cat}", f"cat_{cat}.html") or ""
        for wid, name in re.findall(r'href="https://islamic-content.com/dictionary/word/(\d+)"[^>]*>\s*(.*?)\s*</a>',
                                    page, re.S):
            name = re.sub(r"<[^>]+>", "", html.unescape(name)).strip()
            if name and not name.startswith("تعريف"):
                index.setdefault(_key(name), (wid, name))
    return index


def _parse_translation(page: str) -> tuple[str, str] | None:
    """(term, definition) from a /word/<id>/<lang> page."""
    m = re.search(r'<article class="entry-wraper">\s*<h1[^>]*>(.*?)<br', page, re.S)
    if not m:
        return None
    term = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
    d = re.search(r"<h2>التعريف</h2>(.*?)</div>", page, re.S)
    definition = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", d.group(1)))).strip() if d else ""
    return (term, definition) if term else None


def _arabic_definition(page: str) -> str:
    d = re.search(r"من معجم المصطلحات الشرعية\s*</h5>(.*?)</div>", page, re.S)
    if not d:
        return ""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", d.group(1)))).strip()
    return text[:400]


def build() -> None:
    index = _word_index()
    print(f"Jamhara: {len(index)} dictionary terms indexed")
    terms = []
    seen = set()

    def lookup(ar: str) -> dict:
        keys = [ar, *ALTERNATES.get(ar, [])]
        keys += [k[2:] for k in keys if k.startswith("ال")] + [f"ال{k}" for k in keys if not k.startswith("ال")]
        hit = next((index[_key(k)] for k in keys if _key(k) in index), None)
        if not hit:
            return {}
        wid, shown = hit
        entry = {"jamhara_id": int(wid), "jamhara_term": shown,
                 "source_url": f"{BASE}/word/{wid}"}
        ar_page = _get(f"{BASE}/word/{wid}", f"word_{wid}_ar.html") or ""
        if ar_page:
            entry["definition_ar"] = _arabic_definition(ar_page)
        for lang in ("en", "ur"):
            if f"/dictionary/word/{wid}/{lang}" not in ar_page:
                continue
            page = _get(f"{BASE}/word/{wid}/{lang}", f"word_{wid}_{lang}.html")
            parsed = _parse_translation(page or "")
            if parsed:
                entry[lang] = parsed[0]
                if parsed[1]:
                    entry[f"definition_{lang}"] = parsed[1]
        return entry

    for ar, en, rule in OFFICIAL:
        j = lookup(ar)
        terms.append({"ar": ar, "en": en, "usage_rule_ar": rule, "status": "official_challenge",
                      "source": "Challenge reference pack (المرجعية والحزمة العلمية), p. 8",
                      **{f"jamhara_{k}" if k in ("en", "ur") else k: v for k, v in j.items()}})
        seen.add(_key(ar))

    for ar in _targets():
        if _key(ar) in seen:
            continue
        seen.add(_key(ar))
        j = lookup(ar)
        if not j.get("en"):
            print(f"  skip {ar}: no published English equivalent found")
            continue
        terms.append({"ar": ar, "status": "jamhara", "source": "Jamhara dictionary", **j})

    out = {
        "version": date.today().isoformat(),
        "note": ("official_challenge entries are authoritative; jamhara entries are copied verbatim "
                 "from islamic-content.com/dictionary. Content-team review recommended before release."),
        "terms": terms,
    }
    config.GLOSSARY_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"glossary: {len(terms)} terms -> {config.GLOSSARY_PATH}")


if __name__ == "__main__":
    build()
