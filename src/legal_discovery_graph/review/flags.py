"""Deterministic privilege/PII detector for eDiscovery review.

Rule-shaped signals (privilege boilerplate, counsel-domain correspondence,
context-anchored digit runs) are detected with regular expressions rather
than a classifier: the pattern *is* the definition, results are exactly
reproducible, and precision is prioritized over recall — a missed flag costs
a second pass by a reviewer, a false flag costs trust in the tool.
"""

import re
from dataclasses import dataclass

# --- Privilege markers -----------------------------------------------------

_PRIVILEGE_PHRASE_RE = re.compile(
    "|".join(
        [
            r"attorney[- ]client privileged",
            r"attorney work product",
            r"privileged and confidential",
            r"prepared at the direction of counsel",
            r"\b(?:seeking|requesting|for|provide|provides|provided)\s+legal\s+advice\b",
        ]
    ),
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"\b[\w.+-]+@(?P<domain>[\w-]+(?:\.[\w-]+)+)\b")

# --- PII patterns -----------------------------------------------------------

_SSN_HYPHENATED_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SSN_CONTEXT_RE = re.compile(
    r"(?:SSN|social security).{0,40}?\b\d{9}\b", re.IGNORECASE | re.DOTALL
)
_BANK_ACCOUNT_CONTEXT_RE = re.compile(
    r"(?:account\s*number|account\s*no\.?|acct\.?|IBAN).{0,40}?\b\d{8,12}\b",
    re.IGNORECASE | re.DOTALL,
)
_ROUTING_NUMBER_CONTEXT_RE = re.compile(
    r"(?:routing\s*number|routing\s*no\.?|ABA).{0,40}?\b\d{9}\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class TextFlags:
    """Privilege/PII signals detected in a single document's text."""

    privileged: bool
    privilege_markers: tuple[str, ...]
    pii_types: tuple[str, ...]


def _domain_matches(domain: str, counsel_domains: tuple[str, ...]) -> bool:
    """Return True if `domain` equals, or is a subdomain of, a counsel domain."""
    domain = domain.casefold()
    return any(
        domain == counsel_domain or domain.endswith(f".{counsel_domain}")
        for counsel_domain in counsel_domains
    )


def _privilege_markers(text: str, counsel_domains: tuple[str, ...]) -> tuple[str, ...]:
    """Return matched privilege marker phrases, deduped, in order of first appearance."""
    hits: list[tuple[int, str]] = [
        (match.start(), match.group(0)) for match in _PRIVILEGE_PHRASE_RE.finditer(text)
    ]

    if counsel_domains:
        normalized_domains = tuple(domain.casefold() for domain in counsel_domains)
        hits.extend(
            (match.start(), match.group(0))
            for match in _EMAIL_RE.finditer(text)
            if _domain_matches(match.group("domain"), normalized_domains)
        )

    hits.sort(key=lambda hit: hit[0])
    seen: set[str] = set()
    markers: list[str] = []
    for _, phrase in hits:
        key = phrase.casefold()
        if key not in seen:
            seen.add(key)
            markers.append(phrase)
    return tuple(markers)


def _pii_types(text: str) -> tuple[str, ...]:
    """Return the subset of PII types found, sorted."""
    types: set[str] = set()
    if _SSN_HYPHENATED_RE.search(text) or _SSN_CONTEXT_RE.search(text):
        types.add("ssn")
    if _BANK_ACCOUNT_CONTEXT_RE.search(text):
        types.add("bank_account")
    if _ROUTING_NUMBER_CONTEXT_RE.search(text):
        types.add("routing_number")
    return tuple(sorted(types))


def flag_text(text: str, counsel_domains: tuple[str, ...] = ()) -> TextFlags:
    """Detect privilege boilerplate and contextual PII in `text`.

    `counsel_domains` are compared case-insensitively against email domains
    found in `text`; a match requires the full domain label (or a
    subdomain of it), not merely a suffix on the character string.
    """
    markers = _privilege_markers(text, counsel_domains)
    return TextFlags(
        privileged=bool(markers),
        privilege_markers=markers,
        pii_types=_pii_types(text),
    )
