# سجل عمل الوكيل — مُعين الداعية (جزء نادر)

> السجل الرسمي لكل خطوة في بناء الوكيل والـ API. يُحدَّث بعد كل خطوة.
> المستودع: `fawazabdullah25/hikmah-dev` — فرع المعرفة: `claude/loving-heisenberg-oekuju` — فرع العمل: `nader/agent`

## طريقة التوثيق
كل خطوة تُسجَّل بـ: التاريخ، الهدف، ما تم (الملفات)، الأوامر حرفيًا، النتيجة الفعلية، القرار وسببه، رقم الـ commit.
وأي أداة أو نموذج جديد يُضاف فورًا إلى `docs/DISCLOSURE.md`.

---

## 1. القرارات المعتمدة

| # | التاريخ | القرار | السبب |
|---|---|---|---|
| D1 | 2026-09-25 | معمارية الوكيل: LangGraph بخمس مراحل (Analyze → Route → Retrieve → Generate → Verify) + refer/abstain | مطابقة المعيار العلمي للحزمة وقابلية الإفصاح |
| D2 | 2026-09-25 | النموذج لا يكتب نص آية/حديث؛ يكتب معرّفات `[[Q:..]]`/`[[H:..]]` تُستبدل من مخزن النصوص | منع تحريف النصوص بالتصميم |
| D3 | 2026-10-01 | إلغاء تيليجرام؛ الوكيل يُنشر كـ API يربطه فريق موقع شيخك (sheykak.com) | تحديث من الفريق |
| D4 | 2026-10-01 | دور نادر: الوكيل + ربطه بطبقة المعرفة + الجاهزية + الـ RAG من جهة الوكيل؛ الربط بالموقع على فريق الموقع | تحديث من الفريق |
| D5 | 2026-10-01 | `with_structured_output(..., method="function_calling")` في كل الاستدعاءات | `space-bunny-free` يتجاهل JSON-schema (HANDOFF §4) |
| D6 | 2026-10-01 | تمرير كلام السائل + صياغة عربية (+ السؤال الجوهري) إلى `retrieve()` | Recall@6 من 93% إلى 98% (قياس فواز) |
| D7 | 2026-10-01 | الامتناع تحت `ABSTAIN_THRESHOLD`؛ طلب الحديث بـ `types=["hadith"]` فقط والامتناع إن لم يرجع شيء | مقاومة الهلوسة (HANDOFF §5.7) |
| D8 | 2026-10-01 | `retrieve(["warm up"], "en")` عند تشغيل الـ API (في خيط خلفي) | أول استدعاء 15–30 ثانية |
| D9 | 2026-10-01 | ﴿﴾ للقرآن فقط، والحديث بـ «» مع المصدر والدرجة؛ إضافة الآية الصحيحة للمنقولة بخطأ إلى الأدلة | HANDOFF §5.1 و §5.2 |
| D10 | 2026-10-01 | الدرر مطفأة | تحجب السيرفرات السحابية؛ تُختبر من سيرفر النشر |
| D11 | 2026-10-01 | مصدر الحديث المقترح: fawazahmed0/hadith-api (الصحيحان) + sunnah.com احتياط | بعد موافقة المنظمين على مصادر معروفة إضافية — **لم يُدمج بعد** |
| D12 | 2026-10-01 | التحكم بعد الهاكثون: تشغيل على سيرفر نادر + مفاتيح `X-API-Key` + تاريخ انتهاء معلن `MUEEN_SERVICE_UNTIL` + اتفاق مكتوب | حفظ الحقوق بشفافية |
| D13 | 2026-10-03 | منصة النشر: sheykak.com، والاستدعاء من سيرفر الموقع فقط | HANDOFF §7 |
| D14 | 2026-10-03 | ⚠️ مفتوح: المستودع مرخّص MIT؛ يلزم قرار رخصة كود الوكيل قبل الدمج في الفرع الرئيسي | MIT تسمح بإعادة الاستخدام لأي أحد |
| D15 | 2026-10-03 | قاعدة D بإشارتين: كلمات (ضمير متكلم **و** كلمة حكم **و** ظرف شخصي) كتلميح، وتُرفع إلى D إذا اتفق المحلل والقاعدة | تصحيح HANDOFF §5.3 |
| D16 | 2026-10-03 | المستوى D يرجّع نصًا ثابتًا مراجَعًا (عربي/إنجليزي/أردو/إندونيسي/فرنسي) بدون توليد ولا استرجاع؛ اللغات الأخرى تُترجم من الإنجليزي | HANDOFF §5.4 |
| D17 | 2026-10-03 | سجل التشغيل بدون نصوص الرسائل والردود؛ `/feedback` يحفظ الإجراء ونسبة التعديل فقط | HANDOFF §5.6 و PRIVACY.md |
| D18 | 2026-10-03 | المسودة التي تفشل التحقق مرتين تُعرض بحالة `unverified` مع تحذير، والمراجع غير الصحيحة تُستبدل بعلامة ⚠ | DECISIONS: لا تُخفى عن الداعية |
| D19 | 2026-10-03 | طبقة التحقق الثانية (LLM-judge) اختيارية `VERIFY_LLM_JUDGE=0` افتراضيًا | الزمن؛ الطبقة الحتمية تعمل دائمًا |

---

## 2. خطوات العمل

| الخطوة | الوصف | الحالة |
|---|---|---|
| S0 | الوصول للمستودع | ✅ 2026-10-03 |
| S1 | قراءة HANDOFF وCLAUDE.md وتوثيق الواجهات | ✅ |
| S2 | البيئة + التشغيل على `RETRIEVER=mock` | ✅ (بدون torch — انظر العوائق) |
| S3 | `python -m ingest.build_all` + الفهرس | ⛔ محجوب من بيئة التطوير (الشبكة) |
| S4 | `agent/state.py` + `agent/llm.py` | ✅ |
| S5 | عقدة Analyze | ✅ |
| S6 | عقدة Retrieve | ✅ |
| S7 | عقدة Route + refer + abstain | ✅ |
| S8 | عقدة Generate + الـ prompts | ✅ |
| S9 | عقدة Verify + اختبارات | ✅ |
| S10 | الـ API: `/suggest` `/suggest/regenerate` `/feedback` `/stats` `/health` + المفاتيح + تاريخ الانتهاء | ✅ |
| S11 | التقييم الكامل `eval.run_eval agent --judge` → EVALUATION §4 | ⏳ يحتاج الفهرس + مفتاح الموديل |
| S12 | وثيقة التكامل لفريق الموقع `docs/API_INTEGRATION.md` | ✅ |
| S13 | DISCLOSURE + AGENT.md + README + CLAUDE.md | ✅ |
| S14 | فحص الجاهزية للنشر (نسخة نظيفة، الزمن، Qdrant كسيرفر، الدرر من السيرفر) | ⏳ |

---

## 3. العوائق المفتوحة

| العائق | الأثر | الحل |
|---|---|---|
| بيئة التطوير السحابية محجوبة عن huggingface.co و quranpedia.net و dawa.center و opencode.ai و download.pytorch.org | لا يمكن بناء الفهرس ولا استدعاء الموديل الحقيقي من بيئة التطوير | فتح النطاقات من إعدادات Claude (Capabilities) أو التشغيل على جهاز/سيرفر (القسم 5) |
| مفتاح `AI_API_KEY` (OpenCode Zen) غير متوفر لنادر | لا تقييم حقيقي | يُطلب من فواز |
| مراجعة شرعية للـ prompts والقوالب | شرط قبل الديمو | عضو المحتوى يراجع `agent/prompts/*.md` و `agent/templates.py` |
| قرار الرخصة (D14) والاتفاق المكتوب (D12) | حقوق نادر | اتفاق الفريق |

---

## 4. سجل التنفيذ

### 2026-10-01 — S0: محاولة الوصول
- **الأوامر:** `git clone https://github.com/fawazabdullah25/hikmah-dev.git`
- **النتيجة:** فشل — المستودع خاص.

### 2026-10-03 — S0/S1: الوصول وقراءة التسليم
- **ما تم:** سحب المستودع بـ token (بدون حفظه في إعدادات git)، التحويل إلى `claude/loving-heisenberg-oekuju`، إنشاء الفرع `nader/agent`، قراءة `CLAUDE.md` و `docs/HANDOFF.md` والكود (`contract.py`, `config.py`, `mock.py`, `ayah_match.py`, `glossary.py`, `langid.py`, `verbatim.py`, `eval/run_eval.py`).
- **النتيجة:** نجاح. آخر commit لفواز: `cd28ebd`.

### 2026-10-03 — S2/S3: البيئة
- **الأوامر:** `python3.11 -m venv .venv` ، `pip install -r requirements-dev.txt`
- **النتيجة:** فشل تنزيل torch — `download.pytorch.org` محجوب (403 من سياسة الشبكة). وفحص الاتصال: huggingface.co و quranpedia.net و dawa.center و dl.fbaipublicfiles.com و opencode.ai كلها محجوبة.
- **القرار:** تثبيت مكتبات الوكيل فقط من PyPI (langgraph 1.2.12، langchain-openai 1.6.7، fastapi 0.142.2، uvicorn 0.54.0 + pydantic/httpx/rapidfuzz/qdrant-client/fasttext-wheel/pymupdf) والعمل على `RETRIEVER=mock` مع موديل وهمي في الاختبارات.

### 2026-10-03 — S4–S10: بناء الوكيل والـ API
- **الملفات الجديدة:**
  - `agent/settings.py` — الإعدادات (الموديل لكل مرحلة، المحاولات، المفاتيح، تاريخ الانتهاء، السجل).
  - `agent/state.py` — `Analysis`, `Routing`, `Draft`, `Judgement`, `Citation`, `AgentState`.
  - `agent/llm.py` — مصنع الموديل (`function_calling`)، قابل للاستبدال في الاختبارات.
  - `agent/rules.py` — قواعد حتمية: المعرّفات، تغطية النطاقات، تلميح D، عبارات الإجماع، العرض (﴿﴾ / «»).
  - `agent/templates.py` — نصوص الإحالة والامتناع (5 لغات).
  - `agent/prompts/{analyze,route,generate,judge}.md` — الـ prompts (تعريفات المستويات منقولة من الحزمة).
  - `agent/nodes.py` — المراحل السبع + `check_draft`.
  - `agent/graph.py` — الرسم البياني + `suggest()`.
  - `api/main.py`, `api/schemas.py` — الخدمة.
  - `requirements-agent.txt`, `Dockerfile.api`, خدمة `api` في `docker-compose.yml`، متغيرات الوكيل في `.env.example`.
- **النتيجة:** تشغيل `uvicorn` على mock ناجح؛ `/health` = 200؛ `/suggest` بدون مفتاح موديل = 503 برسالة واضحة.

### 2026-10-03 — S9: الاختبارات
- **الملفات:** `tests/agent_fakes.py`, `tests/test_agent_rules.py` (15), `tests/test_agent_graph.py` (12), `tests/test_api.py` (7).
- **الأوامر:** `python -m pytest -q`
- **النتيجة:** **56 نجاح، 15 متخطّى** (المتخطّاة تحتاج المخزن/الفهرس). تشمل: المسار السليم، مرجع مختلق ← إعادة، فشل مرتين ← unverified، أقواس كتبها النموذج، ادعاء إجماع في C، المستوى D، طلب حديث ← امتناع، ثقة منخفضة ← امتناع، ترجمة القالب، المفاتيح، تاريخ الانتهاء، خلو السجل من النصوص.

### 2026-10-03 — S12/S13: التوثيق
- **الملفات:** `docs/AGENT.md`، `docs/API_INTEGRATION.md`، تحديث `docs/DISCLOSURE.md` (جدول الوكيل)، `docs/EVALUATION.md` (حالة §4)، `README.md`، `CLAUDE.md`، وهذا السجل.

---

## 5. دليل التشغيل خطوة بخطوة (على جهاز أو سيرفر فيه إنترنت)

```bash
# 1) سحب الفرع
git clone https://github.com/fawazabdullah25/hikmah-dev.git && cd hikmah-dev
git checkout nader/agent

# 2) البيئة (Python 3.11)
python3.11 -m venv .venv && . .venv/bin/activate        # ويندوز: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 3) الإعدادات
cp .env.example .env
#   AI_API_KEY=<مفتاح OpenCode Zen>
#   MUEEN_API_KEYS=<مفتاح تعطيه لسيرفر موقع شيخك>
#   MUEEN_SERVICE_UNTIL=<آخر يوم للخدمة، اختياري>

# 4) بناء المعرفة (مرة وحدة، ~دقيقتين + تنزيل BGE-M3 ~2.3GB أول مرة)
python -m ingest.build_all
python -m pytest -q                      # المفروض كل الاختبارات تنجح بدون تخطّي

# 5) تشغيل الـ API
uvicorn api.main:app --port 8000
curl localhost:8000/health               # models_loaded=true, verbatim_store=true, llm_configured=true

# 6) تجربة يدوية
curl -X POST localhost:8000/suggest -H "Content-Type: application/json" -H "X-API-Key: <المفتاح>" \
  -d '{"conversation_id":"t1","messages":[{"role":"seeker","text":"Why do Muslims worship the Kaaba?"}]}'

# 7) التقييم الكامل (41 حالة) ثم نسخ الجدول إلى docs/EVALUATION.md القسم 4
python -m eval.run_eval agent --api http://localhost:8000 --judge --api-key <المفتاح>
```

**بـ Docker على السيرفر:**
```bash
docker compose up -d qdrant
docker compose --profile build run --rm kb-build
docker compose up -d api        # على 127.0.0.1:8000؛ ضع أمامه reverse proxy بـ HTTPS
```

### 2026-10-03 — الرفع
- **الأوامر:** `git push -u origin nader/agent`
- **النتيجة:** نجاح — الفرع `nader/agent` على GitHub.
- **Commit:** `fc2c174` (الوكيل + الـ API + الاختبارات + التوثيق)
