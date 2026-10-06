# Sources

Only sources named in the challenge reference pack (المرجعية والحزمة العلمية,
version 20/3/1448, see `docs/reference/challenge-reference-pack.md`) are used.
Everything is downloaded from the official publisher by `python -m ingest.download`;
nothing is scraped from mirrors.

| Collection | Source (as named in the pack) | What we use | Where it lives | Retrieved |
|---|---|---|---|---|
| Quran text | quranpedia.net — "طبعة مجمع الملك فهد" | `mushafs-1.json.gz`: Hafs 'an 'Asim, "موافق لطبعة مجمع الملك فهد لطباعة المصحف الشريف" — all 114 surahs, 6,236 ayahs | Verbatim store (SQLite) + search index | Dump version 2026-09-28, SHA-256 verified against the dump manifest |
| English translation | Quranpedia translation book **1948** | Taqi-ud-Din al-Hilali & Muhsin Khan, *published by the King Fahd Complex*, 1417 AH | Verbatim store | 2026-09-28 |
| Urdu translation | Quranpedia translation book **1966** | Muhammad Ibrahim Junagarhi, *published by the King Fahd Complex*, 1417 AH (some ayahs revised by Rowad Translation Center, as noted by the publisher) | Verbatim store | 2026-09-28 |
| Quran topics | Quranpedia `topics.json.gz` | Topic labels per ayah (3,673 ayahs) — used **only** to help search, never shown as text | Search index | 2026-09-28 |
| Q&A on doubts | "بينات: أسئلة وأجوبة عن الإسلام" — dawa.center/file/7937 (Usul Center, 2024 / 1445 AH) | All 263 questions: question, similar phrasings, short answer, detailed answer | Search index (1,116 passages) | PDF downloaded 2026-09-28 |
| Classical & dawah books | Shamela full database — shamela.ws/page/download (named in the updated pack, 2026-10) | 33 selected books (`ingest/shamela_books.yaml`): 24 answering other religions and modern ideologies + 9 early creed works (authors died ≤ 300 AH) | Search index (6,766 passages, type `dawah`) | Database version 1448, read 2026-10-05 |
| Terminology | Jamhara dictionary — islamic-content.com/dictionary | English (and Urdu when published) equivalents + definitions for key terms, each with its URL | `data/glossary.json` | 2026-09-28 |
| Terminology (official) | The pack's own "نماذج لقاموس المصطلحات الأساسية" (page 8) | The 10 terms with their usage rules | `data/glossary.json` (`status: official_challenge`) | — |
| Hadith | HadeethEnc — hadeethenc.com, the organiser's Encyclopedia of Translated Prophetic Hadiths (named in the updated pack, 2026-10) | 3,573 hadith graded صحيح / حسن (1 weak one left out), each with grade, attribution, official explanation and approved translations (en 2,326 · id 2,260 · ur 2,219 · fr 1,789) | Hadith store (`store/hadith.sqlite`) + search index | API v1, 2026-10-06 |
| Hadith (optional) | dorar.net/hadith | Live search, **off by default**, authentic grades only | Not stored (a cache of returned results only) | Not tested: dorar.net blocks cloud IPs |

## Licences and terms

* **Quranpedia**: free to use inside apps and websites; republishing the data as a
  downloadable dataset requires crediting Quranpedia.net with a link and the dump
  version. We therefore do **not** commit the Quran text or translations to git —
  the build downloads them. Translations remain the property of their publishers.
  Quranpedia asks copies to be kept current: re-run `python -m ingest.build_all
  --force-download` periodically (see `https://quranpedia.net/api/v1/changes`).
* **Bayyinat**: published free by Usul Center on dawa.center. We index it for
  retrieval and always link back to the exact PDF page (`source_url` ends in
  `#page=N`). The PDF itself is not committed.
* **Jamhara**: "حقوق الاستفادة من المحتوى لكل مسلم". Pages fetched politely (public
  dictionary pages allowed by robots.txt, 2 s between requests, cached). Each glossary
  entry keeps its source URL.
* **Shamela**: the pack lists the full Shamela database as an allowed source. Most
  selected works are classical (public domain); modern books and editions may carry
  their authors'/editors' rights, so — as with every source — the text is **not**
  committed: `python -m ingest.shamela` downloads it from shamela.ws. Each passage links
  to its page on shamela.ws and cites the printed volume and page.
* **HadeethEnc**: published free by the organiser ("providing them for free through all
  available means"). Fetched through its public API (4 requests at a time, cached), never
  committed to git; every hadith links to its page on hadeethenc.com.
* **Dorar**: only its public search API, only when enabled; results are shown as
  returned with a link back; nothing is stored beyond a local cache.

## How the text was processed (and known limits)

* **Quran**: text kept exactly as published (only invisible BOM characters removed).
  Normalization (removing diacritics, unifying alef forms) is applied to search keys
  only, never to displayed text.
* **Translations**: footnotes separated from the text (kept in the store's `notes`
  column), footnote markers and HTML removed, Arabic presentation-form ligatures folded.
* **Bayyinat PDF**: made with InDesign, whose Arabic ligatures (لا، في، لله) extract
  in the wrong order. `ingest/pdf_ar.py` repairs them exactly from glyph positions,
  plus text rules that only match impossible spellings. Measured on the output:
  0 remaining broken ligatures of the known types; about 35 words (≈0.01 %) still miss
  the alef of "ال" (e.g. "لاختلاف" for "الاختلاف"), which does not affect search.
* **Bayyinat verses**: the PDF draws Quran verses with glyph fonts that contain no
  text. The book always follows a verse with its reference ("[البقرة: 144]"), so the
  exact verse text is re-inserted from the verbatim store at that reference
  (765 references across 372 passages). Where the book quoted only part of a verse,
  the full verse is inserted.
* **Bayyinat honorifics**: symbols such as «عليه السلام» are drawn with a symbol
  font whose characters cannot be mapped reliably; they are omitted rather than
  guessed.
* **Titles**: taken from the book's table of contents, matched by question number.
* **Shamela selection**: chosen with Nader and Shaker (2026-10-05), rules at the top of
  `ingest/shamela_books.yaml`: books answering other religions and modern ideologies,
  and early creed works; inner-Muslim sectarian polemics and works aimed at named
  persons are left out (the pack puts "judging persons and groups" out of scope).
  Content-team review of the list is still pending.
* **Shamela extraction**: the 13 GB database keeps all book text in one Lucene index.
  `ingest/shamela.py` downloads only the stored-text files of that index (~4.8 GB, HTTP
  range requests into the official zip), the catalogue and the selected books' page
  tables; `ingest/java/ShamelaDump.java` (Java 21+, Apache Lucene 10.4) reads the pages
  of the selected books. Text is kept as published except: HTML tags and footnote
  markers removed, ﷽ written out. The modern editors' footnotes are not indexed (they
  are not the author's text). Pages are joined into ~1,400-character passages; the
  ref gives the printed volume and page ("ج 2 ص 531"); 20 passages from the opening
  pages of 5 books have no printed page number, so their ref is the book title only.
* **Verses inside Shamela passages**: kept exactly as the book prints them (not
  replaced). When a passage cites "[سورة: n]", `quran_refs_in` turns that into a
  verse id, so the agent shows the verse from the verbatim store, never from the book.
* **HadeethEnc**: text, grade and attribution kept exactly as published. Only grades containing
  صحيح / حسن / صحّح are kept (e.g. "صحيح", "حسن لغيره", "صححه الحافظ ابن حجر"); one hadith graded
  ضعيف is left out. A translation is used only where HadeethEnc publishes one for that language;
  otherwise the hadith is shown in Arabic only.
