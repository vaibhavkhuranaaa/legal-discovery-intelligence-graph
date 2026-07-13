"""Neo4j AuraDB driver boundary: constraints, loading, and expansion queries.

This module is the only place the Neo4j driver is imported (mirroring how
``retrieval/store.py`` is the only PostgreSQL boundary — see
``docs/architecture.md``). All Cypher is parameterized; node labels come from
a fixed mapping and are never built from data. Callers interact through
:class:`Neo4jGraphStore` and catch :class:`GraphUnavailableError` — the
degraded-mode signal when the graph leg is down or unconfigured.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType

import neo4j
import neo4j.exceptions

from legal_discovery_graph.graph.loader import GraphPayload
from legal_discovery_graph.models import EntityType

# Server-side errors (Neo4jError: auth, Cypher, …) and driver-side errors
# (DriverError: ServiceUnavailable, SessionExpired, …) are disjoint
# hierarchies; the degraded-mode boundary must convert both.
_NEO4J_FAILURES = (neo4j.exceptions.Neo4jError, neo4j.exceptions.DriverError)

# Fixed entity-type → node-label mapping (docs/DATA_MODEL.md). DATE entities
# are timeline data, not graph nodes: the data model defines no Date label,
# and a shared date would edge-connect otherwise unrelated documents.
NODE_LABELS: dict[EntityType, str] = {
    EntityType.PERSON: "Person",
    EntityType.ORGANIZATION: "Organization",
    EntityType.PROJECT: "Project",
    EntityType.LOCATION: "Location",
    EntityType.MONEY: "Money",
}

_CONSTRAINTS = tuple(
    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
    for label, key in (
        ("Document", "document_id"),
        ("Event", "event_id"),
        *((label, "entity_id") for label in NODE_LABELS.values()),
    )
)

_EXPAND_CO_MENTION = """
    MATCH (e)-[seed:MENTIONED_IN]->(:Document)
    WHERE seed.chunk_id IN $chunk_ids
    MATCH (e)-[m:MENTIONED_IN]->(d:Document)
    WHERE NOT m.chunk_id IN $chunk_ids
    RETURN DISTINCT e.entity_id AS entity_id, e.name AS entity_name,
           seed.chunk_id AS source_chunk_id,
           'co_mentioned' AS relation, d.document_id AS document_id,
           m.chunk_id AS chunk_id
"""

_EXPAND_CORRESPONDENCE = """
    MATCH (p:Person)-[seed:MENTIONED_IN]->(:Document)
    WHERE seed.chunk_id IN $chunk_ids
    MATCH (p)-[r:SENT|RECEIVED]->(d:Document)
    MATCH ()-[m:MENTIONED_IN]->(d)
    WHERE NOT m.chunk_id IN $chunk_ids
    RETURN DISTINCT p.entity_id AS entity_id, p.name AS entity_name, r.chunk_id AS source_chunk_id,
           toLower(type(r)) AS relation, d.document_id AS document_id,
           m.chunk_id AS chunk_id
"""

_EXPAND_EVENTS = """
    MATCH (e)-[seed:MENTIONED_IN]->(:Document)
    WHERE seed.chunk_id IN $chunk_ids
    MATCH (ev:Event)-[involves:INVOLVES]->(e)
    MATCH (ev)-[evidenced:EVIDENCED_BY]->(d:Document)
    MATCH ()-[m:MENTIONED_IN]->(d)
    WHERE NOT m.chunk_id IN $chunk_ids
    RETURN DISTINCT e.entity_id AS entity_id, e.name AS entity_name,
           coalesce(involves.chunk_id, evidenced.chunk_id) AS source_chunk_id,
           'event' AS relation, d.document_id AS document_id,
           m.chunk_id AS chunk_id
"""


class GraphUnavailableError(Exception):
    """The Neo4j graph is unconfigured or unreachable; the vector leg must carry on."""


@dataclass(frozen=True)
class GraphEvidence:
    """One evidence-backed reason a chunk was pulled in by graph expansion."""

    entity_id: str
    entity_name: str
    relation: str  # co_mentioned | sent | received | event
    document_id: str
    source_chunk_id: str
    chunk_id: str


class Neo4jGraphStore:
    """Relationship store backed by Neo4j AuraDB."""

    def __init__(self, uri: str, username: str, password: str) -> None:
        if not (uri and username and password):
            raise GraphUnavailableError(
                "Neo4j is not configured — set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD"
            )
        try:
            self._driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))
        except (*_NEO4J_FAILURES, ValueError) as exc:
            raise GraphUnavailableError(f"invalid Neo4j configuration: {exc}") from exc

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jGraphStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def verify_connectivity(self) -> None:
        """Raise :class:`GraphUnavailableError` if the graph cannot be reached."""
        try:
            self._driver.verify_connectivity()
        except _NEO4J_FAILURES as exc:
            raise GraphUnavailableError(f"Neo4j unreachable: {exc}") from exc

    def _run(self, query: str, **parameters: object) -> list[neo4j.Record]:
        try:
            return self._driver.execute_query(query, **parameters).records
        except _NEO4J_FAILURES as exc:
            raise GraphUnavailableError(f"Neo4j query failed: {exc}") from exc

    def apply_constraints(self) -> None:
        """Create the per-label shared-ID uniqueness constraints (idempotent)."""
        for statement in _CONSTRAINTS:
            self._run(statement)

    def replace_graph(self, payload: GraphPayload) -> None:
        """Wipe and reload the whole graph from a :class:`GraphPayload`.

        The corpus is small and deterministically regenerated, so wipe-and-
        reload (mirroring ``PgVectorStore.replace_corpus``) is simpler and
        safer than diffing; MERGE keeps each batch idempotent regardless.
        """
        try:
            with self._driver.session() as session:
                session.execute_write(self._replace_graph_transaction, payload)
        except _NEO4J_FAILURES as exc:
            raise GraphUnavailableError(f"Neo4j graph replacement failed: {exc}") from exc

    @staticmethod
    def _run_transaction(
        transaction: neo4j.ManagedTransaction, query: str, **parameters: object
    ) -> None:
        transaction.run(query, **parameters).consume()

    def _replace_graph_transaction(
        self, transaction: neo4j.ManagedTransaction, payload: GraphPayload
    ) -> None:
        """Replace the graph in one write transaction; retries roll back fully."""
        self._run_transaction(transaction, "MATCH (n) DETACH DELETE n")
        self._run_transaction(
            transaction,
            "UNWIND $rows AS row MERGE (d:Document {document_id: row.document_id}) "
            "SET d.doc_type = row.doc_type, d.title = row.title, d.sent_at = row.sent_at",
            rows=[
                {
                    "document_id": document.document_id,
                    "doc_type": document.doc_type.value,
                    "title": document.title,
                    "sent_at": document.sent_at,
                }
                for document in payload.documents
            ],
        )
        for entity_type, label in NODE_LABELS.items():
            rows = [
                {"entity_id": entity.entity_id, "name": entity.name}
                for entity in payload.entities
                if entity.entity_type is entity_type
            ]
            if rows:
                self._run_transaction(
                    transaction,
                    f"UNWIND $rows AS row MERGE (e:{label} {{entity_id: row.entity_id}}) "  # noqa: S608 — label from fixed mapping, values parameterized
                    "SET e.name = row.name",
                    rows=rows,
                )
        self._run_transaction(
            transaction,
            "UNWIND $rows AS row MERGE (ev:Event {event_id: row.event_id}) "
            "SET ev.occurred_at = row.occurred_at, ev.description = row.description "
            "WITH ev, row MATCH (d:Document {document_id: row.document_id}) "
            "MERGE (ev)-[:EVIDENCED_BY {chunk_id: row.chunk_id}]->(d)",
            rows=[
                {
                    "event_id": event.event_id,
                    "document_id": event.document_id,
                    "occurred_at": event.occurred_at,
                    "description": event.description,
                    "chunk_id": event.chunk_id,
                }
                for event in payload.events
            ],
        )
        self._run_transaction(
            transaction,
            "UNWIND $rows AS row MATCH (ev:Event {event_id: row.event_id}) "
            "MATCH (e {entity_id: row.entity_id}) "
            "MERGE (ev)-[:INVOLVES {chunk_id: row.chunk_id}]->(e)",
            rows=[
                {"event_id": event.event_id, "entity_id": entity_id, "chunk_id": event.chunk_id}
                for event in payload.events
                for entity_id in event.entity_ids
            ],
        )
        self._run_transaction(
            transaction,
            "UNWIND $rows AS row MATCH (e {entity_id: row.entity_id}) "
            "MATCH (d:Document {document_id: row.document_id}) "
            "MERGE (e)-[:MENTIONED_IN {chunk_id: row.chunk_id}]->(d)",
            rows=[
                {
                    "entity_id": edge.entity_id,
                    "document_id": edge.document_id,
                    "chunk_id": edge.chunk_id,
                }
                for edge in payload.mention_edges
            ],
        )
        for relation, cypher_type in (("sent", "SENT"), ("received", "RECEIVED")):
            rows = [
                {
                    "entity_id": edge.entity_id,
                    "document_id": edge.document_id,
                    "chunk_id": edge.chunk_id,
                }
                for edge in payload.participant_edges
                if edge.relation == relation
            ]
            if rows:
                self._run_transaction(
                    transaction,
                    "UNWIND $rows AS row MATCH (p:Person {entity_id: row.entity_id}) "
                    "MATCH (d:Document {document_id: row.document_id}) "
                    f"MERGE (p)-[:{cypher_type} {{chunk_id: row.chunk_id}}]->(d)",  # noqa: S608 — type from fixed pair, values parameterized
                    rows=rows,
                )

    def expand_from_chunks(self, seed_chunk_ids: Sequence[str]) -> list[GraphEvidence]:
        """Evidence-backed expansion from seed chunks to related chunks.

        Follows co-mentions, correspondence (SENT/RECEIVED), and event
        involvement from the entities evidenced in the seed chunks, returning
        one row per (entity, relation, target chunk) — every row is traceable
        to a MENTIONED_IN provenance edge.
        """
        seeds = list(seed_chunk_ids)
        if not seeds:
            return []
        evidence: list[GraphEvidence] = []
        for query in (_EXPAND_CO_MENTION, _EXPAND_CORRESPONDENCE, _EXPAND_EVENTS):
            for record in self._run(query, chunk_ids=seeds):
                evidence.append(
                    GraphEvidence(
                        entity_id=record["entity_id"],
                        entity_name=record["entity_name"],
                        relation=record["relation"],
                        document_id=record["document_id"],
                        source_chunk_id=record["source_chunk_id"],
                        chunk_id=record["chunk_id"],
                    )
                )
        return evidence

    def graph_counts(self) -> dict[str, int]:
        """Node/relationship counts for post-load verification."""
        counts: dict[str, int] = {}
        for name, query in (
            ("nodes", "MATCH (n) RETURN count(n) AS c"),
            ("relationships", "MATCH ()-[r]->() RETURN count(r) AS c"),
            ("documents", "MATCH (d:Document) RETURN count(d) AS c"),
            ("events", "MATCH (ev:Event) RETURN count(ev) AS c"),
            ("mention_edges", "MATCH ()-[m:MENTIONED_IN]->() RETURN count(m) AS c"),
        ):
            counts[name] = self._run(query)[0]["c"]
        return counts
