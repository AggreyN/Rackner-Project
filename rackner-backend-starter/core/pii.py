"""PII pre-upload scanner (security requirement).

The frontend sends the file to /documents/scan BEFORE committing to upload.
If we find likely PII, the UI shows a confirmation popup:
"Sensitive info has been detected — are you sure you want to upload?"
The user can then proceed knowingly. Nothing is stored during a scan.
"""

import re
from dataclasses import dataclass


@dataclass
class PiiFinding:
    kind: str      # e.g. "SSN"
    count: int
    sample_masked: str  # masked example so the user can recognize it safely


# Transparent, auditable regexes. Tuned for US federal-contracting docs.
_PATTERNS: dict[str, re.Pattern] = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "Email address": re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b"),
    "Phone number": re.compile(r"\b(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    "Credit card number": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "Date of birth": re.compile(r"\b(?:DOB|date of birth)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.I),
    "Passport number": re.compile(r"\b(?:passport(?:\s*(?:no|number))?)[:\s#]*[A-Z0-9]{6,9}\b", re.I),
}


def _mask(value: str) -> str:
    """Show only the last 2 characters: '***-**-**89'."""
    keep = 2
    return "*" * max(len(value) - keep, 0) + value[-keep:]


def _luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in re.sub(r"\D", "", digits)]
    if len(ds) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def scan_text(text: str) -> list[PiiFinding]:
    """Scan extracted document text and report findings by kind."""
    findings: list[PiiFinding] = []
    for kind, pattern in _PATTERNS.items():
        matches = pattern.findall(text)
        if kind == "Credit card number":
            matches = [m for m in matches if _luhn_ok(m)]  # cut false positives
        if matches:
            findings.append(
                PiiFinding(kind=kind, count=len(matches), sample_masked=_mask(str(matches[0])))
            )
    return findings
