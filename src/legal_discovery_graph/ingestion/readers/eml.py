"""EML reader: extract a header block and text body from an email message file."""

import email
import email.policy
import re
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path

from legal_discovery_graph.ingestion.readers._common import file_document_id, normalize_paragraphs
from legal_discovery_graph.models import Document, DocumentType

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")


def read_eml(path: Path, custodian: str = "") -> tuple[Document, str]:
    """Read an EML file, returning its ``Document`` metadata and a header-block plus body.

    Raises:
        ValueError: if the file cannot be parsed as an email or no body text is found.
    """
    try:
        with path.open("rb") as handle:
            message = BytesParser(policy=email.policy.default).parse(handle)
    except (email.errors.MessageError, ValueError) as exc:
        raise ValueError(f"Unable to read EML '{path}': {exc}") from exc

    subject = message.get("subject")
    sent_at = _parse_sent_at(message)
    body_text = _extract_body_text(message)
    if not body_text.strip():
        raise ValueError(f"No extractable body text found in EML '{path}'")

    header_block = _build_header_block(message)
    body = normalize_paragraphs([header_block, body_text])

    document = Document(
        document_id=file_document_id(path),
        doc_type=DocumentType.EMAIL,
        title=str(subject) if subject else path.stem,
        source_path=str(path),
        custodian=custodian,
        sent_at=sent_at,
    )
    return document, body


def _build_header_block(message: email.message.Message) -> str:
    lines: list[str] = []
    from_ = message.get("from")
    to = message.get("to")
    date = message.get("date")
    subject = message.get("subject")
    if from_:
        lines.append(f"From: {from_}")
    if to:
        lines.append(f"To: {to}")
    if date:
        sent_at = _parse_sent_at(message)
        lines.append(f"Date: {sent_at.isoformat() if sent_at else str(date)}")
    if subject:
        lines.append(f"Subject: {subject}")
    return "\n".join(lines)


def _parse_sent_at(message: email.message.Message) -> datetime | None:
    date_value = message.get("date")
    if date_value is None:
        return None
    if isinstance(date_value, datetime):
        parsed = date_value
    else:
        try:
            parsed = email.utils.parsedate_to_datetime(str(date_value))
        except (TypeError, ValueError):
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _extract_body_text(message: email.message.Message) -> str:
    body_part = message.get_body(preferencelist=("plain", "html"))
    if body_part is None:
        return ""
    content = body_part.get_content()
    if body_part.get_content_type() == "text/html":
        content = _TAG_RE.sub(" ", content)
        content = _WHITESPACE_RE.sub(" ", content)
    return content
