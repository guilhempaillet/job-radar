from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    value: str
    quote: str
    confidence: str = "explicit"


YEAR_PATTERN = re.compile(
    r"(?P<years>\d{1,2})\s*\+?\s*(?:years?|yrs?)",
    re.IGNORECASE,
)


def experience_requirements(text: str) -> list[Evidence]:
    """Return every explicit years requirement instead of collapsing evidence early."""
    found: list[Evidence] = []
    for match in YEAR_PATTERN.finditer(text):
        sentence_end = min(
            [end for end in (text.find(".", match.end()), text.find("\n", match.end())) if end >= 0]
            or [min(len(text), match.end() + 100)]
        )
        quote = text[match.start() : sentence_end].strip()
        found.append(Evidence(value=match.group("years"), quote=quote))
    return found


def binding_experience_minimum(text: str) -> int | None:
    """Use the highest explicit required minimum; unknown beats an unsupported guess."""
    values = [int(item.value) for item in experience_requirements(text)]
    return max(values) if values else None


def workplace_evidence(text: str, location: str = "") -> Evidence | None:
    combined = f"{location}\n{text}"
    patterns = (
        ("Remote", r"\b(?:fully\s+)?remote\b"),
        ("Hybrid", r"\bhybrid\b"),
        ("In person", r"\b(?:on[ -]?site|in[ -]?person)\b"),
    )
    for value, pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 40)
            end = min(len(combined), match.end() + 70)
            return Evidence(value=value, quote=combined[start:end].strip())
    return None


def benefits(text: str) -> list[str]:
    catalog = {
        "Equity": r"\b(?:equity|stock options?|rsus?)\b",
        "Health": r"\b(?:health|medical|dental|vision)\b",
        "Retirement": r"\b(?:401\(?k\)?|retirement|rrsp)\b",
        "Parental leave": r"\bparental leave\b",
        "Learning budget": r"\b(?:learning|education|development) (?:budget|stipend)\b",
        "Flexible PTO": r"\b(?:flexible|unlimited) (?:pto|vacation|time off)\b",
    }
    return [label for label, pattern in catalog.items() if re.search(pattern, text, re.IGNORECASE)]
