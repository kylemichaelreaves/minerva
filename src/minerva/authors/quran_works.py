"""Per-work configuration for the Quran ingest.

Source: Tanzil Uthmani XML (CC-attribution, free for any use).
114 surahs / 6,236 ayahs.

Citation system: ``surah_ayah`` (new in migration 0017). Each surah
is its own ``works`` row keyed by the transliterated English title
(``Al-Fatihah``, ``Al-Baqarah``, …) — the transliteration is the
canonical URL-safe identifier; the Arabic-script name and English
gloss are surfaced as display titles via the Reader handler.

Display in the Reader heading (mirroring the Hebrew Bible pattern):

  display_title    = Arabic script   (``الفاتحة``)
  display_subtitle = ``<transliteration> · <English>``
                     (``Al-Fatihah · The Opening``)

Sidebar shows the Arabic script alone.

Sidebar order is Mushaf canonical (1..114) — the order every printed
Quran uses. The revelation place (Meccan vs Medinan) is recorded
here for editorial/teaching context but not used in sort key
(future UI may group by revelation period).
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class _Surah:
    """Per-surah metadata.

    * ``number`` — canonical Mushaf surah number (1..114). Drives
      both the work-list display order and the surah_ayah sort key
      (``surah * 1000 + ayah``).
    * ``arabic`` — Arabic-script title from Tanzil verbatim. Used
      as the Reader ``display_title``.
    * ``transliteration`` — Latin-script title (popular convention,
      no macrons: ``Al-Fatihah``, ``Aal-Imran``, ``An-Nisaa``).
      Doubles as the canonical ``works.title`` (URL-safe id).
    * ``english`` — Conventional English meaning gloss (``The
      Opening``, ``The Cow``). Surfaced in the Reader subtitle.
    * ``revelation`` — ``"meccan"`` (85 surahs, earlier in the
      tradition) or ``"medinan"`` (29 surahs, post-Hijra).
    """

    number: int
    arabic: str
    transliteration: str
    english: str
    revelation: str


# Mushaf order, 1..114. Arabic names are verbatim from the Tanzil
# Uthmani XML; transliterations are the standard popular-print
# convention (Sahih International / Penguin) without macrons.
_SURAHS: tuple[_Surah, ...] = (
    _Surah(1, "الفاتحة", "Al-Fatihah", "The Opening", "meccan"),
    _Surah(2, "البقرة", "Al-Baqarah", "The Cow", "medinan"),
    _Surah(3, "آل عمران", "Aal-Imran", "The Family of Imran", "medinan"),
    _Surah(4, "النساء", "An-Nisaa", "The Women", "medinan"),
    _Surah(5, "المائدة", "Al-Maaidah", "The Table Spread", "medinan"),
    _Surah(6, "الأنعام", "Al-Anaam", "The Cattle", "meccan"),
    _Surah(7, "الأعراف", "Al-Araf", "The Heights", "meccan"),
    _Surah(8, "الأنفال", "Al-Anfal", "The Spoils of War", "medinan"),
    _Surah(9, "التوبة", "At-Tawbah", "The Repentance", "medinan"),
    _Surah(10, "يونس", "Yunus", "Jonah", "meccan"),
    _Surah(11, "هود", "Hud", "Hud", "meccan"),
    _Surah(12, "يوسف", "Yusuf", "Joseph", "meccan"),
    _Surah(13, "الرعد", "Ar-Rad", "The Thunder", "medinan"),
    _Surah(14, "ابراهيم", "Ibrahim", "Abraham", "meccan"),
    _Surah(15, "الحجر", "Al-Hijr", "The Rocky Tract", "meccan"),
    _Surah(16, "النحل", "An-Nahl", "The Bee", "meccan"),
    _Surah(17, "الإسراء", "Al-Isra", "The Night Journey", "meccan"),
    _Surah(18, "الكهف", "Al-Kahf", "The Cave", "meccan"),
    _Surah(19, "مريم", "Maryam", "Mary", "meccan"),
    _Surah(20, "طه", "Ta-Ha", "Ta-Ha", "meccan"),
    _Surah(21, "الأنبياء", "Al-Anbiyaa", "The Prophets", "meccan"),
    _Surah(22, "الحج", "Al-Hajj", "The Pilgrimage", "medinan"),
    _Surah(23, "المؤمنون", "Al-Muminun", "The Believers", "meccan"),
    _Surah(24, "النور", "An-Nur", "The Light", "medinan"),
    _Surah(25, "الفرقان", "Al-Furqan", "The Criterion", "meccan"),
    _Surah(26, "الشعراء", "Ash-Shuaraa", "The Poets", "meccan"),
    _Surah(27, "النمل", "An-Naml", "The Ant", "meccan"),
    _Surah(28, "القصص", "Al-Qasas", "The Stories", "meccan"),
    _Surah(29, "العنكبوت", "Al-Ankabut", "The Spider", "meccan"),
    _Surah(30, "الروم", "Ar-Rum", "The Romans", "meccan"),
    _Surah(31, "لقمان", "Luqman", "Luqman", "meccan"),
    _Surah(32, "السجدة", "As-Sajdah", "The Prostration", "meccan"),
    _Surah(33, "الأحزاب", "Al-Ahzab", "The Combined Forces", "medinan"),
    _Surah(34, "سبأ", "Saba", "Sheba", "meccan"),
    _Surah(35, "فاطر", "Fatir", "Originator", "meccan"),
    _Surah(36, "يس", "Ya-Sin", "Ya-Sin", "meccan"),
    _Surah(37, "الصافات", "As-Saffat", "Those Ranged in Ranks", "meccan"),
    _Surah(38, "ص", "Sad", "Sad", "meccan"),
    _Surah(39, "الزمر", "Az-Zumar", "The Groups", "meccan"),
    _Surah(40, "غافر", "Ghafir", "The Forgiver", "meccan"),
    _Surah(41, "فصلت", "Fussilat", "Explained in Detail", "meccan"),
    _Surah(42, "الشورى", "Ash-Shura", "The Consultation", "meccan"),
    _Surah(43, "الزخرف", "Az-Zukhruf", "The Gold Adornments", "meccan"),
    _Surah(44, "الدخان", "Ad-Dukhan", "The Smoke", "meccan"),
    _Surah(45, "الجاثية", "Al-Jathiyah", "The Kneeling", "meccan"),
    _Surah(46, "الأحقاف", "Al-Ahqaf", "The Wind-Curved Sandhills", "meccan"),
    _Surah(47, "محمد", "Muhammad", "Muhammad", "medinan"),
    _Surah(48, "الفتح", "Al-Fath", "The Victory", "medinan"),
    _Surah(49, "الحجرات", "Al-Hujurat", "The Rooms", "medinan"),
    _Surah(50, "ق", "Qaf", "Qaf", "meccan"),
    _Surah(51, "الذاريات", "Adh-Dhariyat", "The Scatterers", "meccan"),
    _Surah(52, "الطور", "At-Tur", "The Mount", "meccan"),
    _Surah(53, "النجم", "An-Najm", "The Star", "meccan"),
    _Surah(54, "القمر", "Al-Qamar", "The Moon", "meccan"),
    _Surah(55, "الرحمن", "Ar-Rahman", "The Most Merciful", "medinan"),
    _Surah(56, "الواقعة", "Al-Waqiah", "The Inevitable", "meccan"),
    _Surah(57, "الحديد", "Al-Hadid", "The Iron", "medinan"),
    _Surah(58, "المجادلة", "Al-Mujadilah", "The Pleading Woman", "medinan"),
    _Surah(59, "الحشر", "Al-Hashr", "The Exile", "medinan"),
    _Surah(60, "الممتحنة", "Al-Mumtahanah", "The Examined One", "medinan"),
    _Surah(61, "الصف", "As-Saff", "The Ranks", "medinan"),
    _Surah(62, "الجمعة", "Al-Jumuah", "Friday", "medinan"),
    _Surah(63, "المنافقون", "Al-Munafiqun", "The Hypocrites", "medinan"),
    _Surah(64, "التغابن", "At-Taghabun", "The Mutual Loss", "medinan"),
    _Surah(65, "الطلاق", "At-Talaq", "The Divorce", "medinan"),
    _Surah(66, "التحريم", "At-Tahrim", "The Prohibition", "medinan"),
    _Surah(67, "الملك", "Al-Mulk", "The Sovereignty", "meccan"),
    _Surah(68, "القلم", "Al-Qalam", "The Pen", "meccan"),
    _Surah(69, "الحاقة", "Al-Haqqah", "The Reality", "meccan"),
    _Surah(70, "المعارج", "Al-Maarij", "The Ascending Stairways", "meccan"),
    _Surah(71, "نوح", "Nuh", "Noah", "meccan"),
    _Surah(72, "الجن", "Al-Jinn", "The Jinn", "meccan"),
    _Surah(73, "المزمل", "Al-Muzzammil", "The Enshrouded", "meccan"),
    _Surah(74, "المدثر", "Al-Muddaththir", "The Cloaked", "meccan"),
    _Surah(75, "القيامة", "Al-Qiyamah", "The Resurrection", "meccan"),
    _Surah(76, "الانسان", "Al-Insan", "Man", "medinan"),
    _Surah(77, "المرسلات", "Al-Mursalat", "Those Sent Forth", "meccan"),
    _Surah(78, "النبأ", "An-Naba", "The Announcement", "meccan"),
    _Surah(79, "النازعات", "An-Naziat", "Those Who Pull Out", "meccan"),
    _Surah(80, "عبس", "Abasa", "He Frowned", "meccan"),
    _Surah(81, "التكوير", "At-Takwir", "The Folding Up", "meccan"),
    _Surah(82, "الإنفطار", "Al-Infitar", "The Cleaving", "meccan"),
    _Surah(83, "المطففين", "Al-Mutaffifin", "The Defrauders", "meccan"),
    _Surah(84, "الإنشقاق", "Al-Inshiqaq", "The Splitting Asunder", "meccan"),
    _Surah(85, "البروج", "Al-Buruj", "The Constellations", "meccan"),
    _Surah(86, "الطارق", "At-Tariq", "The Night-Comer", "meccan"),
    _Surah(87, "الأعلى", "Al-Ala", "The Most High", "meccan"),
    _Surah(88, "الغاشية", "Al-Ghashiyah", "The Overwhelming", "meccan"),
    _Surah(89, "الفجر", "Al-Fajr", "The Dawn", "meccan"),
    _Surah(90, "البلد", "Al-Balad", "The City", "meccan"),
    _Surah(91, "الشمس", "Ash-Shams", "The Sun", "meccan"),
    _Surah(92, "الليل", "Al-Layl", "The Night", "meccan"),
    _Surah(93, "الضحى", "Ad-Duhaa", "The Morning Hours", "meccan"),
    _Surah(94, "الشرح", "Ash-Sharh", "The Relief", "meccan"),
    _Surah(95, "التين", "At-Tin", "The Fig", "meccan"),
    _Surah(96, "العلق", "Al-Alaq", "The Clinging Substance", "meccan"),
    _Surah(97, "القدر", "Al-Qadr", "The Power", "meccan"),
    _Surah(98, "البينة", "Al-Bayyinah", "The Clear Evidence", "medinan"),
    _Surah(99, "الزلزلة", "Az-Zalzalah", "The Earthquake", "medinan"),
    _Surah(100, "العاديات", "Al-Adiyat", "The Coursers", "meccan"),
    _Surah(101, "القارعة", "Al-Qariah", "The Striking Calamity", "meccan"),
    _Surah(102, "التكاثر", "At-Takathur", "The Rivalry", "meccan"),
    _Surah(103, "العصر", "Al-Asr", "The Declining Day", "meccan"),
    _Surah(104, "الهمزة", "Al-Humazah", "The Slanderer", "meccan"),
    _Surah(105, "الفيل", "Al-Fil", "The Elephant", "meccan"),
    _Surah(106, "قريش", "Quraysh", "Quraysh", "meccan"),
    _Surah(107, "الماعون", "Al-Maun", "Small Kindnesses", "meccan"),
    _Surah(108, "الكوثر", "Al-Kawthar", "The Abundance", "meccan"),
    _Surah(109, "الكافرون", "Al-Kafirun", "The Disbelievers", "meccan"),
    _Surah(110, "النصر", "An-Nasr", "The Divine Help", "medinan"),
    _Surah(111, "المسد", "Al-Masad", "The Palm Fiber", "meccan"),
    _Surah(112, "الإخلاص", "Al-Ikhlas", "The Sincerity", "meccan"),
    _Surah(113, "الفلق", "Al-Falaq", "The Daybreak", "meccan"),
    _Surah(114, "الناس", "An-Nas", "Mankind", "meccan"),
)


_BY_NUMBER: dict[int, _Surah] = {s.number: s for s in _SURAHS}
_BY_TRANSLITERATION: dict[str, _Surah] = {s.transliteration: s for s in _SURAHS}


def find_surah(number: int) -> _Surah | None:
    """Lookup a surah by canonical Mushaf number (1..114)."""
    return _BY_NUMBER.get(number)


def find_surah_by_transliteration(name: str) -> _Surah | None:
    """Lookup by transliterated title (``Al-Baqarah``, ``Al-Fatihah``).

    Used by the Reader handler to resolve the trilingual display
    title from the canonical ``works.title`` stored on chunks."""
    return _BY_TRANSLITERATION.get(name)


# Public list used by author_ordering + tests.
SURAHS: tuple[_Surah, ...] = _SURAHS
