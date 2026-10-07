"""
Voice payments: "I added 500 rupees on 5 October in DG" -> a draft payment.

The recording is transcribed by 60db speech-to-text (English, Hindi and
Hinglish), then ``parse_payment`` pulls out the amount, date and meter with
plain rules. Nothing is saved here: the app shows the draft for the person to
check and save.

Try the parser on its own:
    python -m app.voice "maine kal dedh hazaar ka DG recharge kiya"
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

STT_URL = "https://api.60db.ai/stt"
STT_TIMEOUT = 30  # seconds

# Hints for the speech model: what the recording is about and words to expect.
STT_CONTEXT = (
    "A flatmate recording a prepaid electricity meter payment: the amount in rupees, "
    "the date, and the meter (main meter or DG / generator). English, Hindi or Hinglish."
)
STT_KEYWORDS = "DG:5,recharge:3,rupees:3,main meter:3,generator:2,hazaar:2,sau:2"


class VoiceError(Exception):
    """Transcription failed; ``status`` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def api_key() -> str:
    return os.environ.get("SIXTYDB_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


# Each recording uses 60db credits: a few per person per minute is plenty.
LIMIT_PER_MINUTE = 5
_recent: Dict[str, List[float]] = {}
_recent_lock = threading.Lock()


def allow(user_id: str) -> bool:
    """Record one recording for ``user_id``; False once they're over the per-minute limit."""
    now = time.monotonic()
    with _recent_lock:
        times = [t for t in _recent.get(user_id, []) if now - t < 60]
        if len(times) >= LIMIT_PER_MINUTE:
            _recent[user_id] = times
            return False
        _recent[user_id] = times + [now]
        return True


def transcribe(audio: bytes, content_type: str) -> str:
    """The recording as text, via 60db STT. Raises VoiceError with a message fit for users."""
    key = api_key()
    if not key:
        raise VoiceError(503, "Voice entry isn't set up on this server")
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
           "audio/wav": "wav", "audio/x-wav": "wav"}.get(content_type.split(";")[0].strip(), "webm")
    try:
        resp = requests.post(
            STT_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (f"payment.{ext}", audio, content_type or "audio/webm")},
            data={
                "languages": "en,hi",
                "script_correction": "true",
                "context": STT_CONTEXT,
                "keywords": STT_KEYWORDS,
            },
            timeout=STT_TIMEOUT,
        )
    except requests.RequestException:
        raise VoiceError(502, "Couldn't reach the speech service. Try again.")
    if resp.status_code == 402:
        raise VoiceError(503, "Voice entry is out of credits for this month. Type the payment instead.")
    if resp.status_code == 429:
        raise VoiceError(429, "Voice entry is busy. Try again in a minute.")
    if resp.status_code >= 400:
        # Never pass the provider's error body on: it may echo request details.
        raise VoiceError(502, f"The speech service couldn't read that recording (HTTP {resp.status_code}).")
    try:
        return str(resp.json().get("text") or "").strip()
    except ValueError:
        raise VoiceError(502, "The speech service sent an unexpected reply.")


# ---------------------------------------------------------------------------
# Parsing: amount, date and meter from what was said
# ---------------------------------------------------------------------------
def _nukta_free(text: str) -> str:
    """ज़ and ज (and precomposed/decomposed forms) compare equal: STT may give either."""
    return unicodedata.normalize("NFC", text).replace("\u093c", "")


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Number words. Hindi in both scripts, since STT may give either.
_UNITS: Dict[str, float] = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    # Hindi, Latin script
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "panj": 5,
    "chhe": 6, "chhah": 6, "chah": 6, "che": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9,
    "das": 10, "dus": 10, "gyarah": 11, "gyara": 11, "barah": 12, "bara": 12, "baarah": 12,
    "terah": 13, "tera": 13, "chaudah": 14, "chauda": 14, "pandrah": 15, "pandra": 15,
    "solah": 16, "sola": 16, "satrah": 17, "satra": 17, "atharah": 18, "athara": 18,
    "unnis": 19, "unees": 19, "bees": 20, "bis": 20, "pachchis": 25, "pachis": 25, "tees": 30,
    "tis": 30, "chalis": 40, "chaalis": 40, "chalees": 40, "pachas": 50, "pachaas": 50,
    "saath": 60, "sattar": 70, "pachattar": 75, "pachhattar": 75, "assi": 80, "nabbe": 90,
    # Hindi, Devanagari
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "पन्द्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
    "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "पचहत्तर": 75,
    "अस्सी": 80, "नब्बे": 90,
}
_SCALES: Dict[str, int] = {
    "hundred": 100, "sau": 100, "सौ": 100,
    "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000,
    "हज़ार": 1000, "हजार": 1000, "k": 1000,
    "lakh": 100000, "lac": 100000, "लाख": 100000,
}
# Indian fractions: dedh hazaar = 1500, dhai sau = 250, saadhe teen sau = 350.
_FRACTIONS: Dict[str, float] = {"dedh": 1.5, "डेढ़": 1.5, "डेढ": 1.5, "dhai": 2.5, "dhaai": 2.5, "ढाई": 2.5}
_ADJUST: Dict[str, float] = {"saadhe": 0.5, "sadhe": 0.5, "sade": 0.5, "साढ़े": 0.5, "साढे": 0.5,
                             "sava": 0.25, "sawa": 0.25, "सवा": 0.25, "paune": -0.25, "पौने": -0.25}
# Common English/Hindi words that are also number words; alone they're not amounts.
_AMBIGUOUS = {"do", "sat", "tin", "che", "bis", "tis", "tera", "bara", "sola", "ath", "k", "saath", "one"}
_CURRENCY = {"rupees", "rupee", "rs", "inr", "₹", "rupay", "rupaye", "rupaiye", "rupiya", "rupiye",
             "रुपये", "रुपए", "रूपए", "रूपये", "रुपया", "bucks"}

_UNITS, _SCALES, _FRACTIONS, _ADJUST = (
    {_nukta_free(k): v for k, v in d.items()} for d in (_UNITS, _SCALES, _FRACTIONS, _ADJUST)
)

_MONTHS: Dict[str, int] = {}
for _num, _names in enumerate([
    "january jan janvari janwari जनवरी",
    "february feb farvari farwari फ़रवरी फरवरी",
    "march मार्च",  # not "mar": a Hindi word too
    "april apr aprail अप्रैल",
    "may मई",  # not "mai": Hinglish for "in"
    "june jun joon जून",
    "july jul julai जुलाई",
    "august aug agast अगस्त",
    "september sept sep sitambar सितंबर सितम्बर",
    "october oct aktubar aktoobar अक्टूबर अक्तूबर",
    "november nov navambar नवंबर नवम्बर",
    "december dec disambar दिसंबर दिसम्बर",
], start=1):
    for _name in _names.split():
        _MONTHS[_nukta_free(_name)] = _num

_WEEKDAYS: Dict[str, int] = {}
for _num, _names in enumerate([
    "monday somvar somwar सोमवार",
    "tuesday mangalvar mangalwar मंगलवार",
    "wednesday budhvar budhwar बुधवार",
    "thursday guruvar guruwar brihaspativar गुरुवार बृहस्पतिवार",
    "friday shukravar shukrawar शुक्रवार",
    "saturday shanivar shaniwar शनिवार",
    "sunday ravivar raviwar itvaar itwar रविवार इतवार",
]):
    for _name in _names.split():
        _WEEKDAYS[_nukta_free(_name)] = _num

_RELATIVE_DAYS = [
    (("day before yesterday", "parso", "parson", "परसों", "परसो"), 2),
    (("yesterday", "kal", "कल"), 1),  # payments are in the past, so "kal" is yesterday
    (("today", "aaj", "आज", "abhi", "अभी", "just now"), 0),
]

_DG_WORDS = re.compile(r"\bd\.?\s?g\b|\bdg\b|डीजी|डी\s?जी|generator|genset|जनरेटर|diesel|डीज़ल|डीजल")
_ORDINAL = r"(?:st|nd|rd|th)?"
_DAY_WORDS = r"(?:tarikh|tareekh|tarik|तारीख|तारीख़|date)"


def _tokens(text: str) -> List[str]:
    # Devanagari first: Python's \w doesn't count vowel signs, so "पांच" would split.
    return re.findall(r"[ऀ-ॣ॰-ॿ]+|[0-9]+(?:\.[0-9]+)?|₹|[^\W\d_]+", text)


def _clean(text: str) -> str:
    text = _nukta_free(text.lower()).translate(_DEVANAGARI_DIGITS).replace("।", " ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)          # 1,500 -> 1500
    text = re.sub(r"(\d)(k)\b", r"\1 \2", text)         # 2k -> 2 k
    text = re.sub(r"(₹|rs\.?)(?=\d)", r"\1 ", text)     # ₹500 / rs500 -> ₹ 500
    text = text.replace("/-", " ")                       # "500/-"
    return re.sub(r"(?<=[^\W\d])-(?=[^\W\d])", " ", text)  # twenty-five -> twenty five


def _number_runs(tokens: List[str]) -> List[Tuple[float, int, int]]:
    """Every run of number words/digits as (value, first token, last token)."""
    runs = []
    i = 0
    while i < len(tokens):
        start, total, current, adjust, seen, words = i, 0.0, 0.0, 0.0, False, []
        while i < len(tokens):
            tok = tokens[i]
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", tok):
                if seen and current and not words[-1] in _SCALES:
                    break  # two numbers in a row ("5 500") are separate
                current += float(tok) + adjust
            elif tok in _FRACTIONS:
                current += _FRACTIONS[tok]
            elif tok in _ADJUST:
                adjust = _ADJUST[tok]
            elif tok in _UNITS:
                current += _UNITS[tok] + adjust
            elif tok in _SCALES and seen:
                scale = _SCALES[tok]
                if scale == 100:
                    current = (current or 1) * 100
                else:
                    total += (current or 1) * scale
                    current = 0.0
            elif tok == "and" and seen:
                pass
            else:
                break
            if tok not in _ADJUST:
                adjust = 0.0
            seen = seen or tok not in _ADJUST
            words.append(tok)
            i += 1
        if seen:
            ambiguous_alone = len(words) == 1 and words[0] in _AMBIGUOUS
            if not ambiguous_alone:
                runs.append((total + current, start, i - 1))
        else:
            i = start + 1
    return runs


def _latest(candidate: date, today: date) -> date:
    """A date said without a year: the most recent one not in the future."""
    return candidate if candidate <= today else candidate.replace(year=candidate.year - 1)


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _find_date(text: str, today: date) -> Tuple[Optional[date], str]:
    """The payment date mentioned in ``text`` and the text with it removed."""
    month_names = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))

    m = re.search(r"\b(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})\b", text)  # 2026-10-05
    if m:
        d = _safe_date(int(m[1]), int(m[2]), int(m[3]))
        if d:
            return d, text.replace(m[0], " ")

    # Day first, as written in India: 5/10, 05/10/2026, 05.10.2026, 5-10-26.
    m = (re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
         or re.search(r"\b(\d{1,2})[.-](\d{1,2})[.-](\d{2,4})\b", text))
    if m:
        year = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else today.year
        d = _safe_date(year, int(m[2]), int(m[1]))
        if d:
            return (d if m[3] else _latest(d, today)), text.replace(m[0], " ")

    patterns = [
        rf"\b(?P<day>\d{{1,2}}){_ORDINAL}\s+(?:of\s+)?(?P<month>{month_names})\b(?:\s+(?P<year>20\d\d))?",
        rf"\b(?P<month>{month_names})\s+(?P<day>\d{{1,2}}){_ORDINAL}\b(?:\s*,?\s*(?P<year>20\d\d))?",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            year = int(m["year"]) if m["year"] else today.year
            d = _safe_date(year, _MONTHS[m["month"]], int(m["day"]))
            if d:
                return (d if m["year"] else _latest(d, today)), text.replace(m[0], " ")

    # "5 tarikh", "on the 5th": a day of this month (or last month if still ahead).
    m = re.search(rf"\b(?:on\s+)?(?:the\s+)?(\d{{1,2}})\s*(?:st|nd|rd|th)\b|\b(\d{{1,2}})\s*{_DAY_WORDS}", text)
    if m:
        day = int(m[1] or m[2])
        d = _safe_date(today.year, today.month, day)
        if d is None or d > today:
            last_month = today.replace(day=1) - timedelta(days=1)
            d = _safe_date(last_month.year, last_month.month, day)
        if d:
            return d, text.replace(m[0], " ")

    for words, days_ago in _RELATIVE_DAYS:
        for word in words:
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
                return today - timedelta(days=days_ago), re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", " ", text)

    for word, weekday in _WEEKDAYS.items():
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
            back = (today.weekday() - weekday) % 7  # the latest one, today included
            return today - timedelta(days=back), re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", " ", text)

    return None, text


def parse_payment(text: str, today: Optional[date] = None) -> Dict[str, Any]:
    """
    Amount, date and meter from a spoken payment. Anything not said is None
    (the date then defaults to today, flagged by ``date_said``).
    """
    today = today or date.today()
    cleaned = _clean(text)
    when, rest = _find_date(cleaned, today)

    tokens = _tokens(rest)
    runs = [r for r in _number_runs(tokens) if r[0] > 0]
    amount = None
    if runs:
        def by_currency(run: Tuple[float, int, int]) -> bool:
            near = tokens[max(run[1] - 1, 0):run[2] + 2]
            return any(t in _CURRENCY for t in near)
        priced = [r for r in runs if by_currency(r)]
        amount = round(max(priced or runs, key=lambda r: r[0])[0], 2)

    meter = "dg" if _DG_WORDS.search(cleaned) else "main"
    return {
        "amount": amount,
        "date": (when or today).isoformat(),
        "date_said": when is not None,
        "meter": meter,
        "meter_said": meter == "dg" or bool(re.search(r"\bmain\b|मेन|मुख्य", cleaned)),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Usage: python -m app.voice "I added 500 rupees today"')
    print(parse_payment(sys.argv[1]))
