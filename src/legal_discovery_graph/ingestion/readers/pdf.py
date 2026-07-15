"""PDF reader: extract plain text from a PDF file into a ``Document``/body pair."""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from legal_discovery_graph.ingestion.readers._common import file_document_id, normalize_paragraphs
from legal_discovery_graph.models import Document, DocumentType


def read_pdf(path: Path, custodian: str = "") -> tuple[Document, str]:
    """Read a PDF file, returning its ``Document`` metadata and extracted plain-text body.

    Raises:
        ValueError: if the PDF cannot be read (including encrypted PDFs that cannot be
            decrypted with an empty password) or if no text can be extracted from any page.
    """
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ValueError(f"Unable to read PDF '{path}': {exc}") from exc

    body = normalize_paragraphs(pages)
    if not body:
        raise ValueError(f"No extractable text found in PDF '{path}'")

    document = Document(
        document_id=file_document_id(path),
        doc_type=DocumentType.OTHER,
        title=path.stem,
        source_path=str(path),
        custodian=custodian,
    )
    return document, body
