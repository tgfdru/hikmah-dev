"""Selected Shamela books -> search records (type "dawah").

    python -m ingest.shamela            # download (once), extract, build shamela.jsonl

Source: the official full database from shamela.ws/page/download (13 GB zip). All
book text sits in one Lucene index; we fetch only the stored-text files of that
index (~4.8 GB) with HTTP range requests, plus the catalogue and the per-book page
tables, then read the pages of the books listed in ingest/shamela_books.yaml with a
small Java program (ingest/java/ShamelaDump.java; needs Java 21+, downloads
lucene-core from Maven Central).

Output: WORK_DIR/processed/shamela.jsonl — passages of ~1,400 characters, each with
the book, the printed volume/page ("ج 2 ص 45") and a link to the page on shamela.ws.
The modern editors' footnotes are left out: they are not the author's text.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import httpx
import yaml

from retrieval import config
from retrieval.verbatim import quran_refs_in

DB_ZIP = "https://dev.shamela.ws/downloads/shamela-database-1448.zip"
LUCENE_JAR = "https://repo1.maven.org/maven2/org/apache/lucene/lucene-core/10.4.0/lucene-core-10.4.0.jar"
BOOK_URL = "https://shamela.ws/book/{book}/{page}"
SELECTION = Path(__file__).with_name("shamela_books.yaml")
JAVA_SRC = Path(__file__).parent / "java" / "ShamelaDump.java"
RAW = config.RAW_DIR / "shamela"
TEXT_EXT = ("fdt", "fdx", "fdm", "fnm", "si", "cfs", "cfe")
HEADERS = {"User-Agent": "MueenKnowledgeBuilder/1.0 (+https://sheykak.com)",
           "Accept-Encoding": "identity"}  # with compression offered the server ignores Range
CHUNK_MIN, CHUNK_MAX = 900, 1800


# ------------------------------------------------------------- download ---
def _range(a: int, b: int) -> bytes:
    r = httpx.get(DB_ZIP, headers={**HEADERS, "Range": f"bytes={a}-{b}"}, timeout=120)
    if r.status_code != 206:
        raise RuntimeError(f"range request not honoured (HTTP {r.status_code})")
    return r.content


def _central_directory() -> list[tuple[str, int, int, int, int]]:
    """(name, compressed size, size, local header offset, method) for every zip entry."""
    head = httpx.head(DB_ZIP, headers=HEADERS, timeout=60, follow_redirects=True)
    total = int(head.headers["content-length"])
    tail = _range(total - (8 << 20), total - 1)
    base = total - len(tail)
    i = tail.rfind(b"PK\x06\x06")  # zip64 end of central directory
    n, _, cd_off = struct.unpack("<QQQ", tail[i + 32:i + 56])
    p, out = cd_off - base, []
    for _ in range(n):
        (_, _, _, _, comp, _, _, _, cs, us, fnl, exl, cml, _, _, _, lho) = struct.unpack(
            "<IHHHHHHIIIHHHHHII", tail[p:p + 46])
        name = tail[p + 46:p + 46 + fnl].decode("utf-8")
        extra, q = tail[p + 46 + fnl:p + 46 + fnl + exl], 0
        while q + 4 <= len(extra):
            hid, hs = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:  # zip64 sizes / offset
                vals, k = list(struct.unpack("<" + "Q" * (hs // 8), extra[q + 4:q + 4 + hs // 8 * 8])), 0
                if us == 0xFFFFFFFF:
                    us, k = vals[k], k + 1
                if cs == 0xFFFFFFFF:
                    cs, k = vals[k], k + 1
                if lho == 0xFFFFFFFF:
                    lho = vals[k]
            q += 4 + hs
        out.append((name, cs, us, lho, comp))
        p += 46 + fnl + exl + cml
    return out


def _fetch_entry(entry: tuple, dest: Path) -> None:
    name, cs, us, lho, comp = entry
    if dest.exists() and dest.stat().st_size == us:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    fnl, exl = struct.unpack("<HH", _range(lho, lho + 29)[26:30])
    start = lho + 30 + fnl + exl
    tmp = dest.with_suffix(dest.suffix + ".part")
    d = zlib.decompressobj(-15) if comp == 8 else None
    with httpx.stream("GET", DB_ZIP, headers={**HEADERS, "Range": f"bytes={start}-{start + cs - 1}"},
                      timeout=None) as r, open(tmp, "wb") as f:
        if r.status_code != 206:
            raise RuntimeError(f"range request not honoured for {name}")
        for chunk in r.iter_bytes(1 << 20):
            f.write(d.decompress(chunk) if d else chunk)
        if d:
            f.write(d.flush())
    if tmp.stat().st_size != us:
        raise RuntimeError(f"size mismatch for {name}")
    tmp.replace(dest)


def download(book_ids: list[int]) -> None:
    entries = _central_directory()
    wanted = []
    for e in entries:
        name = e[0]
        if name == "database/master.db":
            wanted.append(e)
        elif name.startswith("database/store/page/") and (
                name.rsplit(".", 1)[-1] in TEXT_EXT or "/segments_" in name):
            wanted.append(e)
        elif name.startswith("database/book/") and name.endswith(".db"):
            if int(Path(name).stem) in book_ids:
                wanted.append(e)
    total = sum(e[1] for e in wanted)
    print(f"  Shamela: {len(wanted)} files, {total / 1e9:.1f} GB (of the 13 GB database)")
    for e in wanted:
        _fetch_entry(e, RAW / e[0].replace("database/", ""))


# -------------------------------------------------------------- extract ---
def extract(book_ids: list[int]) -> Path:
    out = RAW / "pages.jsonl"
    jar = RAW / "lucene-core-10.4.0.jar"
    if not jar.exists():
        jar.write_bytes(httpx.get(LUCENE_JAR, timeout=120).content)
    build = RAW / "java"
    build.mkdir(exist_ok=True)
    shutil.copy(JAVA_SRC, build / JAVA_SRC.name)
    subprocess.run(["javac", "-cp", str(jar), JAVA_SRC.name], cwd=build, check=True)
    ids_file = RAW / "book_ids.txt"
    ids_file.write_text("\n".join(map(str, book_ids)), encoding="utf-8")
    print("  reading the Shamela page index (about 15 minutes) ...")
    with open(out, "wb") as f:
        subprocess.run(["java", "-cp", f"{jar}:{build}", "ShamelaDump", str(RAW / "store" / "page"),
                        str(ids_file)], stdout=f, check=True)
    return out


# -------------------------------------------------------------- process ---
_TAG = re.compile(r"<[^>]+>")
_FOOTNOTE_MARK = re.compile(r"\(?¬[\d٠-٩*]*\)?|\[¬\*?\]")


def clean(body: str) -> str:
    text = body.replace("\r", "\n")
    text = _TAG.sub("", text)
    text = _FOOTNOTE_MARK.sub("", text)
    text = text.replace("﷽", "بسم الله الرحمن الرحيم")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", text)).strip()


def _ref(pages: list[tuple[str | None, int | None]]) -> str:
    part, first = pages[0]
    last = pages[-1][1]
    span = f"{first}" if first == last or last is None else f"{first}-{last}"
    return (f"ج {part} " if part else "") + f"ص {span}" if first else "—"


def build() -> None:
    selection = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    books = {b["id"]: {**b, "group": g} for g, items in selection.items() for b in items}
    pages_file = RAW / "pages.jsonl"
    if not pages_file.exists() or "--refresh" in sys.argv:
        download(list(books))
        extract(list(books))
    pages: dict[int, list[tuple[int, str]]] = {}
    with open(pages_file, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            book, page = (int(x) for x in d["id"].split("-"))
            if book in books and d.get("body"):
                pages.setdefault(book, []).append((page, clean(d["body"])))

    records = []
    for book, info in books.items():
        db = RAW / "book" / f"{book % 1000:03d}" / f"{book}.db"
        printed = {}
        if db.exists():
            with sqlite3.connect(db) as c:
                printed = {pid: (part, pg) for pid, part, pg in c.execute("SELECT id, part, page FROM page")}
        source = f"{info['title']} — {info['author']} (المكتبة الشاملة)"
        buf, buf_pages, first_id, n = [], [], None, 0
        seen: dict[int, int] = {}

        def flush():
            nonlocal buf, buf_pages, first_id, n
            text = "\n".join(buf).strip()
            if len(text) >= 80:
                n += 1
                # A long page becomes several passages: SH:<book>:<page>, then :<page>:2, :3 ...
                seen[first_id] = seen.get(first_id, 0) + 1
                pid_part = f"{first_id}" if seen[first_id] == 1 else f"{first_id}:{seen[first_id]}"
                records.append({
                    "id": f"SH:{book}:{pid_part}", "type": "dawah", "title": info["title"],
                    "text_ar": text, "translations": {}, "source": source,
                    "ref": f"{info['title']}، {_ref(buf_pages)}", "grade": None,
                    "source_url": BOOK_URL.format(book=book, page=first_id),
                    "book_id": book, "group": info["group"], "quran_refs": quran_refs_in(text),
                })
            buf, buf_pages, first_id = [], [], None

        for pid, text in sorted(pages.get(book, [])):
            if not text:
                continue
            for para in _split_long(text):
                if buf and sum(map(len, buf)) + len(para) > CHUNK_MAX:
                    flush()
                if first_id is None:
                    first_id = pid
                buf.append(para)
                if not buf_pages or buf_pages[-1] != printed.get(pid, (None, None)):
                    buf_pages.append(printed.get(pid, (None, None)))
                if sum(map(len, buf)) >= CHUNK_MIN * 1.4:
                    flush()
        flush()
        if not n:
            print(f"  warning: no text extracted for book {book} ({info['title']})")

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / "shamela.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Shamela: {len(books)} books, {len(records)} passages -> {out}")


def _split_long(text: str) -> list[str]:
    """Pages longer than CHUNK_MAX are split at paragraph (then sentence) boundaries."""
    if len(text) <= CHUNK_MAX:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"(?<=[.؟!:])\s+|\n", text):
        if cur and len(cur) + len(para) > CHUNK_MAX:
            parts.append(cur)
            cur = ""
        cur = f"{cur} {para}".strip()
    if cur:
        parts.append(cur)
    return parts


if __name__ == "__main__":
    build()
