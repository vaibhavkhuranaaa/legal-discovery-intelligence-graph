"""Corpus assembly: planted scenario documents plus seeded routine noise.

Noise documents (facilities notices, unrelated invoices, routine memos) make
retrieval non-trivial. They are generated from the same composer discipline as
planted documents, so their entity mentions are gold-labeled too.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from legal_discovery_graph.datagen.composer import Composer
from legal_discovery_graph.datagen.scenario import (
    Cast,
    DraftDocument,
    DraftQuery,
    build_planted_documents,
    date_entity,
    make_entity,
    money_entity,
)
from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.models import Document, DocumentType, EntityType

NOISE_PEOPLE = [
    ("hannah-cole", "Hannah Cole"),
    ("peter-lindqvist", "Peter Lindqvist"),
    ("grace-liu", "Grace Liu"),
    ("tom-barrett", "Tom Barrett"),
    ("aisha-mahmoud", "Aisha Mahmoud"),
    ("victor-sokolov", "Victor Sokolov"),
    ("maria-fuentes", "Maria Fuentes"),
    ("sam-whitaker", "Sam Whitaker"),
    ("nadia-osei", "Nadia Osei"),
    ("colin-reilly", "Colin Reilly"),
]

NOISE_ORGS = [
    ("summit-facilities", "Summit Facilities Group"),
    ("brightpath-travel", "BrightPath Travel"),
    ("ironwood-legal", "Ironwood Legal LLP"),
    ("cedartech-it", "CedarTech IT Services"),
    ("lakeshore-catering", "Lakeshore Catering"),
    ("pinnacle-office", "Pinnacle Office Supply"),
]

EMAIL_TOPICS = [
    ("Parking garage maintenance", "the west parking structure will be closed for resurfacing"),
    ("Quarterly all-hands", "the quarterly all-hands is confirmed for the main auditorium"),
    ("Travel policy update", "the updated travel policy takes effect next month"),
    ("Password rotation reminder", "your network password expires this Friday"),
    ("Office move logistics", "the third-floor teams will relocate to the annex"),
    ("Wellness program enrollment", "open enrollment for the wellness program has begun"),
    ("Holiday schedule", "the site holiday calendar for the year is now posted"),
    ("Expense report deadline", "expense reports for the quarter are due by close of business"),
    ("Printer fleet replacement", "the managed print vendor will swap devices this weekend"),
    ("Badge reader upgrade", "badge readers in the lobby will be offline briefly"),
]

MEMO_TOPICS = [
    ("Facilities notice", "routine HVAC maintenance is scheduled for the coming weekend"),
    ("IT change window", "a network change window is scheduled overnight"),
    ("Safety refresher", "annual workplace safety training is due this quarter"),
    ("Records retention", "teams are reminded to follow the records retention schedule"),
    ("Visitor policy", "all visitors must be escorted and badged at reception"),
    ("Procurement threshold", "purchases under the micro-threshold may use the P-card"),
]

INVOICE_SERVICES = [
    "janitorial services",
    "catering for the leadership offsite",
    "software license renewal",
    "office supply replenishment",
    "shuttle service",
    "conference room AV maintenance",
]

MEETING_TOPICS = [
    "weekly operations sync",
    "budget planning session",
    "vendor onboarding review",
    "facilities walkthrough",
    "quarterly planning workshop",
]


@dataclass
class CorpusBundle:
    """Everything the generator knows about the corpus, pre-serialization."""

    seed: int
    cast: Cast
    documents: list[tuple[Document, DraftDocument]]
    queries: list[DraftQuery]


def _random_datetime(rng: random.Random) -> datetime:
    month = rng.randint(1, 11)
    day = rng.randint(1, 28)
    return datetime(2023, month, day, rng.randint(8, 17), rng.choice([0, 15, 30, 45]), tzinfo=UTC)


def _noise_email(rng: random.Random) -> DraftDocument:
    slug_a, name_a = rng.choice(NOISE_PEOPLE)
    slug_b, name_b = rng.choice([p for p in NOISE_PEOPLE if p[0] != slug_a])
    sender = make_entity(EntityType.PERSON, slug_a, name_a)
    recipient = make_entity(EntityType.PERSON, slug_b, name_b)
    subject, blurb = rng.choice(EMAIL_TOPICS)
    when = _random_datetime(rng)
    c = Composer()
    c.text("From: ").mention(sender).text(f" <{slug_a.split('-')[0]}@meridian-aero.example>")
    c.line()
    c.text("To: ").mention(recipient).text(f" <{slug_b.split('-')[0]}@meridian-aero.example>")
    c.line()
    c.text("Date: ").mention(date_entity(when)).line()
    c.text(f"Subject: {subject}").para()
    c.text("Hi ").mention(recipient, name_b.split()[0]).text(",").para()
    c.text(f"A quick note that {blurb}. Details are on the intranet page; reply if your ")
    c.text("team is affected.").para()
    c.text("Thanks,").line().mention(sender, name_a.split()[0])
    return DraftDocument(
        doc_type=DocumentType.EMAIL,
        title=subject,
        custodian=name_b,
        sent_at=when,
        body=c.build(),
        mentions=c.spans,
    )


def _noise_memo(rng: random.Random, cast: Cast) -> DraftDocument:
    slug, name = rng.choice(NOISE_PEOPLE)
    author = make_entity(EntityType.PERSON, slug, name)
    title, blurb = rng.choice(MEMO_TOPICS)
    when = _random_datetime(rng)
    c = Composer()
    c.text("INTERNAL MEMORANDUM — ").mention(cast.meridian).para()
    c.text("Date: ").mention(date_entity(when)).line()
    c.text("From: ").mention(author).para()
    c.text(f"Please be advised that {blurb}. Contact the issuing office with questions.")
    return DraftDocument(
        doc_type=DocumentType.MEMO,
        title=title,
        custodian=name,
        sent_at=when,
        body=c.build(),
        mentions=c.spans,
    )


def _noise_invoice(rng: random.Random, cast: Cast, sequence: int) -> DraftDocument:
    slug, name = rng.choice(NOISE_ORGS)
    vendor = make_entity(EntityType.ORGANIZATION, slug, name)
    service = rng.choice(INVOICE_SERVICES)
    amount = rng.randrange(1_200, 48_000, 100)
    total = money_entity(amount)
    when = _random_datetime(rng)
    number = f"AP-{7000 + sequence}"
    c = Composer()
    c.mention(vendor).line()
    c.text(f"Invoice {number}").line()
    c.text("Date: ").mention(date_entity(when)).line()
    c.text("Bill To: ").mention(cast.meridian).text(", ").mention(cast.denver).para()
    c.text(f"For {service} rendered during the period.").para()
    c.text("Total Due: ").mention(total)
    return DraftDocument(
        doc_type=DocumentType.INVOICE,
        title=f"{name} invoice {number}",
        custodian="Accounts Payable",
        sent_at=when,
        body=c.build(),
        mentions=c.spans,
    )


def _noise_meeting_notes(rng: random.Random) -> DraftDocument:
    attendees = rng.sample(NOISE_PEOPLE, 3)
    topic = rng.choice(MEETING_TOPICS)
    when = _random_datetime(rng)
    c = Composer()
    c.text(f"MEETING NOTES — {topic}").para()
    c.text("Date: ").mention(date_entity(when)).line()
    c.text("Attendees: ")
    for i, (slug, name) in enumerate(attendees):
        if i:
            c.text(", ")
        c.mention(make_entity(EntityType.PERSON, slug, name))
    c.para()
    c.text("Action items were reviewed and owners confirmed. Standing agenda resumes ")
    c.text("next cycle; no decisions requiring escalation were taken.")
    return DraftDocument(
        doc_type=DocumentType.MEETING_NOTES,
        title=f"Notes — {topic}",
        custodian=attendees[0][1],
        sent_at=when,
        body=c.build(),
        mentions=c.spans,
    )


def _build_noise(rng: random.Random, cast: Cast) -> list[DraftDocument]:
    drafts: list[DraftDocument] = []
    drafts.extend(_noise_email(rng) for _ in range(55))
    drafts.extend(_noise_memo(rng, cast) for _ in range(12))
    drafts.extend(_noise_invoice(rng, cast, i) for i in range(15))
    drafts.extend(_noise_meeting_notes(rng) for _ in range(8))
    return drafts


def generate_corpus(seed: int) -> CorpusBundle:
    """Build the full corpus (planted + noise) deterministically for `seed`."""
    rng = random.Random(seed)
    cast = Cast()
    planted, queries = build_planted_documents(cast)
    drafts = planted + _build_noise(rng, cast)
    drafts.sort(key=lambda d: (d.sent_at, d.title))

    documents: list[tuple[Document, DraftDocument]] = []
    for index, draft in enumerate(drafts):
        doc = Document(
            document_id=stable_id("doc", seed, index),
            doc_type=draft.doc_type,
            title=draft.title,
            custodian=draft.custodian,
            sent_at=draft.sent_at,
            created_at=draft.sent_at,
            source_path=f"data/raw/{index:03d}_{draft.doc_type.value}.json",
        )
        documents.append((doc, draft))
    return CorpusBundle(seed=seed, cast=cast, documents=documents, queries=queries)
