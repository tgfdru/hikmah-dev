"""Static Quran metadata: surah names and reference parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass

SURAH_NAMES_EN = [
    "Al-Fatihah", "Al-Baqarah", "Aal-Imran", "An-Nisa", "Al-Ma'idah", "Al-An'am",
    "Al-A'raf", "Al-Anfal", "At-Tawbah", "Yunus", "Hud", "Yusuf", "Ar-Ra'd", "Ibrahim",
    "Al-Hijr", "An-Nahl", "Al-Isra", "Al-Kahf", "Maryam", "Ta-Ha", "Al-Anbiya", "Al-Hajj",
    "Al-Mu'minun", "An-Nur", "Al-Furqan", "Ash-Shu'ara", "An-Naml", "Al-Qasas",
    "Al-Ankabut", "Ar-Rum", "Luqman", "As-Sajdah", "Al-Ahzab", "Saba", "Fatir", "Ya-Sin",
    "As-Saffat", "Sad", "Az-Zumar", "Ghafir", "Fussilat", "Ash-Shura", "Az-Zukhruf",
    "Ad-Dukhan", "Al-Jathiyah", "Al-Ahqaf", "Muhammad", "Al-Fath", "Al-Hujurat", "Qaf",
    "Adh-Dhariyat", "At-Tur", "An-Najm", "Al-Qamar", "Ar-Rahman", "Al-Waqi'ah",
    "Al-Hadid", "Al-Mujadilah", "Al-Hashr", "Al-Mumtahanah", "As-Saff", "Al-Jumu'ah",
    "Al-Munafiqun", "At-Taghabun", "At-Talaq", "At-Tahrim", "Al-Mulk", "Al-Qalam",
    "Al-Haqqah", "Al-Ma'arij", "Nuh", "Al-Jinn", "Al-Muzzammil", "Al-Muddaththir",
    "Al-Qiyamah", "Al-Insan", "Al-Mursalat", "An-Naba", "An-Nazi'at", "Abasa",
    "At-Takwir", "Al-Infitar", "Al-Mutaffifin", "Al-Inshiqaq", "Al-Buruj", "At-Tariq",
    "Al-A'la", "Al-Ghashiyah", "Al-Fajr", "Al-Balad", "Ash-Shams", "Al-Layl", "Ad-Duha",
    "Ash-Sharh", "At-Tin", "Al-Alaq", "Al-Qadr", "Al-Bayyinah", "Az-Zalzalah",
    "Al-Adiyat", "Al-Qari'ah", "At-Takathur", "Al-Asr", "Al-Humazah", "Al-Fil",
    "Quraysh", "Al-Ma'un", "Al-Kawthar", "Al-Kafirun", "An-Nasr", "Al-Masad",
    "Al-Ikhlas", "Al-Falaq", "An-Nas",
]
assert len(SURAH_NAMES_EN) == 114

QURAN_SOURCE_AR = "القرآن الكريم"
_REF = re.compile(r"^Q:(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$")


@dataclass(frozen=True)
class QuranRef:
    surah: int
    start: int
    end: int

    @property
    def id(self) -> str:
        if self.start == self.end:
            return f"Q:{self.surah}:{self.start}"
        return f"Q:{self.surah}:{self.start}-{self.end}"


def parse_quran_ref(ref_id: str) -> QuranRef | None:
    """Parse "Q:2:255" or "Q:112:1-4". Returns None when malformed."""
    m = _REF.match(ref_id.strip())
    if not m:
        return None
    surah, start = int(m.group(1)), int(m.group(2))
    end = int(m.group(3)) if m.group(3) else start
    if not (1 <= surah <= 114) or start < 1 or end < start:
        return None
    return QuranRef(surah, start, end)


def quran_url(surah: int, ayah: int) -> str:
    return f"https://quranpedia.net/surah/1/{surah}/{ayah}"
