"""Deterministic entity resolution: mention surfaces → canonical entities.

Groups extracted mentions into canonical entities using explainable rules
(no ML, no gold-catalog lookups):

- PERSON: full names group exactly; "O. Tran" folds by first-initial +
  surname; bare surnames ("Reyes") and bare first names ("Daniel") fold when
  they match exactly one known full name. Ambiguous short forms stay separate.
- ORGANIZATION / LOCATION: exact grouping, then a short surface folds into a
  longer name when it is a unique word-boundary prefix ("Northgate" →
  "Northgate Supply Solutions") or, for locations, a unique ", suffix"
  ("Colorado" → "Denver, Colorado").
- MONEY: canonical by numeric amount. DATE: canonical by parsed ISO date.
- PROJECT: exact grouping.

Canonical entity IDs are minted deterministically from (type, canonical key),
so repeated runs over the same corpus produce identical entities.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from legal_discovery_graph.extraction.patterns import RawSpan
from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.models import Entity, EntityType

_INITIAL_NAME_RE = re.compile(r"^([A-Z])\. (\w[\w'-]+)$")


@dataclass(frozen=True)
class ResolvedMention:
    """An extracted mention bound to its canonical entity."""

    document_id: str
    entity_type: EntityType
    surface: str
    start: int
    end: int
    entity_id: str
    canonical_name: str


def _normalize(surface: str) -> str:
    return " ".join(surface.split())


def _money_key(surface: str) -> str:
    return surface.replace("$", "").replace(",", "").strip()


def _date_key(surface: str) -> str:
    try:
        return datetime.strptime(surface, "%B %d, %Y").date().isoformat()
    except ValueError:
        return _normalize(surface)


def _is_full_person_name(surface: str) -> bool:
    tokens = surface.split()
    return len(tokens) >= 2 and not _INITIAL_NAME_RE.match(surface)


def _fold_person(surface: str, full_names: list[str]) -> str | None:
    """Fold a short person form into a unique matching full name, else None."""
    initial_match = _INITIAL_NAME_RE.match(surface)
    if initial_match:
        initial, surname = initial_match.group(1), initial_match.group(2)
        candidates = [
            name for name in full_names if name.split()[-1] == surname and name[0] == initial
        ]
    else:
        candidates = [name for name in full_names if surface in (name.split()[0], name.split()[-1])]
    return candidates[0] if len(set(candidates)) == 1 else None


def _fold_name(surface: str, full_names: list[str], allow_suffix: bool) -> str | None:
    """Fold a short org/location form into a unique longer name, else None."""
    candidates = {
        name
        for name in full_names
        if name != surface
        and (
            name.startswith(surface + " ")
            or name.startswith(surface + ",")
            or (allow_suffix and name.endswith(", " + surface))
        )
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _canonical_key(entity_type: EntityType, surface: str, full_names: list[str]) -> str:
    surface = _normalize(surface)
    if entity_type is EntityType.MONEY:
        return _money_key(surface)
    if entity_type is EntityType.DATE:
        return _date_key(surface)
    if entity_type is EntityType.PERSON:
        if _is_full_person_name(surface):
            return surface
        return _fold_person(surface, full_names) or surface
    if entity_type in (EntityType.ORGANIZATION, EntityType.LOCATION):
        folded = _fold_name(surface, full_names, allow_suffix=entity_type is EntityType.LOCATION)
        return folded or surface
    return surface  # PROJECT and any future exact-grouped types


def _full_name_index(
    spans: list[tuple[str, RawSpan]],
) -> dict[EntityType, list[str]]:
    """Collect the corpus-wide long-form names short forms may fold into."""
    names: dict[EntityType, Counter[str]] = {
        EntityType.PERSON: Counter(),
        EntityType.ORGANIZATION: Counter(),
        EntityType.LOCATION: Counter(),
    }
    for _, span in spans:
        surface = _normalize(span.surface)
        if span.entity_type is EntityType.PERSON and _is_full_person_name(surface):
            names[EntityType.PERSON][surface] += 1
        elif span.entity_type in (EntityType.ORGANIZATION, EntityType.LOCATION):
            names[span.entity_type][surface] += 1
    # Deterministic order: most frequent first, ties alphabetical.
    return {
        etype: [name for name, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
        for etype, counter in names.items()
    }


def resolve_mentions(
    spans_by_document: list[tuple[str, RawSpan]],
) -> tuple[list[Entity], list[ResolvedMention]]:
    """Resolve (document_id, span) pairs into canonical entities + mentions."""
    full_names = _full_name_index(spans_by_document)

    entities: dict[str, Entity] = {}
    aliases: dict[str, set[str]] = {}
    mentions: list[ResolvedMention] = []
    for document_id, span in spans_by_document:
        names = full_names.get(span.entity_type, [])
        key = _canonical_key(span.entity_type, span.surface, names)
        entity_id = stable_id("resolved-entity", span.entity_type.value, key)
        if entity_id not in entities:
            if span.entity_type is EntityType.MONEY and key.isdigit():
                display = f"${int(key):,}"
            elif span.entity_type is EntityType.MONEY:
                display = f"${key}"
            else:
                display = key
            entities[entity_id] = Entity(
                entity_id=entity_id, entity_type=span.entity_type, name=display
            )
        surface = _normalize(span.surface)
        if surface != entities[entity_id].name:
            aliases.setdefault(entity_id, set()).add(surface)
        mentions.append(
            ResolvedMention(
                document_id=document_id,
                entity_type=span.entity_type,
                surface=span.surface,
                start=span.start,
                end=span.end,
                entity_id=entity_id,
                canonical_name=entities[entity_id].name,
            )
        )

    for entity_id, alias_set in aliases.items():
        entities[entity_id].aliases = sorted(alias_set)
    entity_list = sorted(entities.values(), key=lambda entity: entity.entity_id)
    return entity_list, mentions
