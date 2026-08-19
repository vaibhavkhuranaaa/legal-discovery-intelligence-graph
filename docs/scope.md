# Product scope

## Decision supported

The workspace helps a legal-technology reviewer or discovery analyst decide whether a relationship or event in the fictional Project Falcon matter is supported by cited evidence.

## Included

- Deterministic synthetic corpus and gold-label generation
- PDF, DOCX, and EML ingestion for controlled evaluation
- Entity, event, privilege, and synthetic-PII extraction
- PostgreSQL pgvector retrieval with Neo4j evidence expansion
- Calibrated refusal, cited passages, source documents, graph, timeline, audit, and evaluation views
- Responsive Flask interface for desktop and mobile review

## Excluded

- Real client or matter data
- Legal advice, responsiveness decisions, or privilege determinations
- Production authentication, matter isolation, retention, OCR, or confidentiality controls
- Availability, security, or production service-level claims

## Operating boundary

The public application is a read-only portfolio demonstration over a fully fictional matter. Metrics measure templated synthetic text and do not establish real-world legal discovery performance.
