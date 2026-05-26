from __future__ import annotations

from datetime import date, timedelta
import calendar
import re

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

VAGUE_DEADLINES = {"soon", "asap", "next sprint", "no rush"}
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
SOFT_WORDS = {"probably", "ideally", "maybe", "roughly", "approximately", "i think", "if possible"}


def _clean(raw_deadline: str) -> str:
    phrase = raw_deadline.lower().strip()
    phrase = phrase.replace("eod", "end of day")
    phrase = re.sub(r"^(by|before|on|for|due|due by)\s+", "", phrase).strip()
    for word in SOFT_WORDS:
        phrase = phrase.replace(word, "")
    phrase = re.sub(r"[,.!?]+", " ", phrase)
    return re.sub(r"\s+", " ", phrase).strip()


def _next_weekday(meeting_date: date, weekday_name: str, force_next_week: bool = False) -> date:
    target = WEEKDAYS[weekday_name]
    if force_next_week:
        days_until_next_monday = 7 - meeting_date.weekday()
        return meeting_date + timedelta(days=days_until_next_monday + target)
    days_ahead = target - meeting_date.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return meeting_date + timedelta(days=days_ahead)


def _ordinal_day(phrase: str, meeting_date: date) -> date | None:
    match = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", phrase)
    if not match:
        return None
    day = int(match.group(1))
    year, month = meeting_date.year, meeting_date.month
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if candidate < meeting_date:
        month = 1 if month == 12 else month + 1
        year = year + 1 if meeting_date.month == 12 else year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
    return candidate


def normalise_deadline(raw_deadline: str | None, meeting_date: date) -> date | None:
    """Normalise transcript deadline phrases against the meeting date.

    Deliberately conservative: vague planning language stays null, while concrete
    relative phrases such as tomorrow, next Wednesday, before Friday, before the
    end of the month and ordinal days are converted deterministically.
    """
    if not raw_deadline:
        return None
    phrase = _clean(raw_deadline)
    if not phrase or phrase in VAGUE_DEADLINES:
        return None

    if "today" in phrase and "tomorrow" in phrase:
        return meeting_date + timedelta(days=1)
    if "tomorrow" in phrase:
        return meeting_date + timedelta(days=1)
    if "today" in phrase or "this afternoon" in phrase or "after this" in phrase:
        return meeting_date
    if "later this week" in phrase or "end of this week" in phrase:
        return _next_weekday(meeting_date, "friday", force_next_week=False)
    for month_name, month_num in MONTHS.items():
        if f"end of {month_name}" in phrase or f"end {month_name}" in phrase:
            year = meeting_date.year + (1 if month_num < meeting_date.month else 0)
            return date(year, month_num, calendar.monthrange(year, month_num)[1])
    if "end of month" in phrase or "end of the month" in phrase:
        return date(meeting_date.year, meeting_date.month, calendar.monthrange(meeting_date.year, meeting_date.month)[1])
    if re.search(r"\bnext week\b", phrase):
        return meeting_date + timedelta(days=(7 - meeting_date.weekday()))

    ordinal = _ordinal_day(phrase, meeting_date)
    if ordinal:
        return ordinal

    for weekday in WEEKDAYS:
        if re.search(rf"\bnext\s+{weekday}\b", phrase):
            return _next_weekday(meeting_date, weekday, force_next_week=True)
    for weekday in WEEKDAYS:
        if re.search(rf"\b{weekday}\b", phrase):
            return _next_weekday(meeting_date, weekday, force_next_week=False)
    return None
