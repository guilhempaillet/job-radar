from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Evidence:
    value: str
    quote: str
    source_field: str = "description"
    method: str = "rule"
    confidence: str = "high"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Compensation:
    minimum: int | None
    maximum: int | None
    currency: str
    period: str
    evidence: Evidence


YEAR_PATTERN = re.compile(r"(?P<years>\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
PREFERRED_PATTERN = re.compile(r"\b(?:preferred|nice to have|bonus)\b", re.IGNORECASE)


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    candidates = [
        position for position in (text.find(".", end), text.find("\n", end)) if position >= 0
    ]
    right = min(candidates) if candidates else min(len(text), end + 140)
    return text[left:right].strip(" :;-")


def experience_requirements(text: str) -> list[Evidence]:
    """Return every explicit years statement and preserve its source sentence."""
    found: list[Evidence] = []
    for match in YEAR_PATTERN.finditer(text):
        quote = _sentence(text, match.start(), match.end())
        confidence = "medium" if PREFERRED_PATTERN.search(quote) else "high"
        found.append(Evidence(value=match.group("years"), quote=quote, confidence=confidence))
    return found


def binding_experience_minimum(text: str) -> int | None:
    """Use the highest non-preferred minimum; unknown beats an unsupported guess."""
    values = [
        int(item.value) for item in experience_requirements(text) if item.confidence == "high"
    ]
    return max(values) if values else None


def workplace_evidence(text: str, location: str = "") -> list[Evidence]:
    patterns = (
        ("Remote", r"\b(?:fully\s+)?remote\b"),
        ("Hybrid", r"\bhybrid\b"),
        ("In person", r"\b(?:on[ -]?site|in[ -]?person)\b"),
    )
    evidence: list[Evidence] = []
    for value, pattern in patterns:
        for source_field, source_text in (("location", location), ("description", text)):
            match = re.search(pattern, source_text, re.IGNORECASE)
            if match:
                evidence.append(
                    Evidence(
                        value=value,
                        quote=_sentence(source_text, match.start(), match.end()),
                        source_field=source_field,
                    )
                )
                break
    return evidence


def primary_workplace(items: list[Evidence]) -> str | None:
    values = {item.value for item in items}
    if values == {"Remote", "Hybrid"}:
        return "Remote or hybrid"
    return next((name for name in ("Remote", "Hybrid", "In person") if name in values), None)


def benefit_evidence(text: str) -> list[Evidence]:
    catalog = {
        "Equity": r"\b(?:equity|stock options?|rsus?)\b",
        "Health": r"\b(?:health|medical|dental|vision)\b",
        "Retirement": r"\b(?:401\(?k\)?|retirement|rrsp)\b",
        "Parental leave": r"\bparental leave\b",
        "Learning budget": r"\b(?:learning|education|development) (?:budget|stipend)\b",
        "Flexible PTO": r"\b(?:flexible|unlimited) (?:pto|vacation|time off)\b",
    }
    evidence: list[Evidence] = []
    for label, pattern in catalog.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            evidence.append(
                Evidence(value=label, quote=_sentence(text, match.start(), match.end()))
            )
    return evidence


MONEY_PATTERN = re.compile(
    r"(?P<currency>CA\$|US\$|USD\s*\$?|CAD\s*\$?|\$)\s*"
    r"(?P<minimum>\d{2,3}(?:\.\d+)?[kK]|\d{2,3}(?:,\d{3})?)"
    r"(?:\s*(?:-|–|—|to)\s*(?:CA\$|US\$|USD\s*\$?|CAD\s*\$?|\$)?\s*"
    r"(?P<maximum>\d{2,3}(?:\.\d+)?[kK]|\d{2,3}(?:,\d{3})?))?"
    r"(?:\s*(?P<suffix>USD|CAD))?"
    r"(?:\s*(?:per|/)\s*(?P<period>year|annum|hour|hr))?",
    re.IGNORECASE,
)


def _amount(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace(",", "").lower()
    multiplier = 1000 if normalized.endswith("k") else 1
    return round(float(normalized.rstrip("k")) * multiplier)


def compensation(text: str) -> Compensation | None:
    """Extract a clearly stated salary range; do not infer currency or annualize hourly pay."""
    for match in MONEY_PATTERN.finditer(text):
        minimum = _amount(match.group("minimum"))
        maximum = _amount(match.group("maximum"))
        currency_token = f"{match.group('currency')} {match.group('suffix') or ''}".upper()
        if match.group("currency") == "$" and not match.group("suffix"):
            continue
        currency = "CAD" if "CA$" in currency_token or "CAD" in currency_token else "USD"
        period_token = (match.group("period") or "year").lower()
        period = "hour" if period_token in {"hour", "hr"} else "year"
        quote = _sentence(text, match.start(), match.end())
        if minimum and (maximum or period == "hour"):
            return Compensation(
                minimum=minimum,
                maximum=maximum,
                currency=currency,
                period=period,
                evidence=Evidence(value=match.group(0).strip(), quote=quote),
            )
    return None
