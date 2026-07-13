"""Document text assembly with exact mention-offset tracking.

Gold entity labels are correct by construction: every entity occurrence is
inserted through :meth:`Composer.mention`, which records the character span
as the text is built. Scenario templates must never write an entity name as
plain text — that is the discipline that makes recall labels complete.
"""

from dataclasses import dataclass, field

from legal_discovery_graph.models import Entity


@dataclass(frozen=True)
class MentionSpan:
    """An entity occurrence with document-level character offsets."""

    entity: Entity
    surface: str
    start: int
    end: int


@dataclass
class Composer:
    """Accumulates text parts and the mention spans planted inside them."""

    _parts: list[str] = field(default_factory=list)
    _length: int = 0
    spans: list[MentionSpan] = field(default_factory=list)

    def text(self, value: str) -> "Composer":
        self._parts.append(value)
        self._length += len(value)
        return self

    def mention(self, entity: Entity, surface: str | None = None) -> "Composer":
        surface = surface if surface is not None else entity.name
        start = self._length
        span = MentionSpan(entity=entity, surface=surface, start=start, end=start + len(surface))
        self.spans.append(span)
        return self.text(surface)

    def line(self) -> "Composer":
        return self.text("\n")

    def para(self) -> "Composer":
        return self.text("\n\n")

    def build(self) -> str:
        return "".join(self._parts)
