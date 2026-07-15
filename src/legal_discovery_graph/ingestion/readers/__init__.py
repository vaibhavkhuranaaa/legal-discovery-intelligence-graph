"""File-format readers that produce ``(Document, body)`` pairs for ingestion.

Each reader extracts plain text from a source file and normalizes it into
paragraphs separated by blank lines (``"\\n\\n"``), matching the input the
downstream chunker (``legal_discovery_graph.ingestion.chunker``) expects.
"""

from legal_discovery_graph.ingestion.readers.docx import read_docx
from legal_discovery_graph.ingestion.readers.eml import read_eml
from legal_discovery_graph.ingestion.readers.pdf import read_pdf

__all__ = ["read_docx", "read_eml", "read_pdf"]
