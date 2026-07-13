"""The fictional "Project Falcon" procurement-fraud scenario.

Entirely fictional fact pattern (people, companies, amounts, and events are
invented; email domains use ``.example``): a procurement director at Meridian
Aerospace Systems steers the Project Falcon avionics contract to a shell
vendor, Northgate Supply Solutions, in exchange for kickbacks routed through
Crestline Holdings — until an internal audit unravels it.

This module defines the cast, the planted evidence documents, the event
timeline, and the gold investigative queries. Noise documents live in
``generator.py``.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from legal_discovery_graph.datagen.composer import Composer, MentionSpan
from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.models import DocumentType, Entity, EntityType


def make_entity(etype: EntityType, slug: str, name: str, aliases: tuple[str, ...] = ()) -> Entity:
    return Entity(
        entity_id=stable_id("entity", etype.value, slug),
        entity_type=etype,
        name=name,
        aliases=list(aliases),
    )


def money_entity(amount: int) -> Entity:
    """Canonical MONEY entity for a dollar amount, e.g. ``$2,400,000``."""
    return make_entity(EntityType.MONEY, f"usd-{amount}", f"${amount:,}")


def date_entity(moment: datetime) -> Entity:
    """Canonical DATE entity, e.g. ``March 24, 2023``."""
    name = f"{moment.strftime('%B')} {moment.day}, {moment.year}"
    return make_entity(EntityType.DATE, moment.date().isoformat(), name)


def dt(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@dataclass
class DraftEvent:
    """A planted timeline event, attached to the document that evidences it."""

    occurred_at: datetime
    description: str
    entities: list[Entity]


@dataclass
class DraftDocument:
    """A generated document plus its by-construction gold annotations."""

    doc_type: DocumentType
    title: str
    custodian: str
    sent_at: datetime
    body: str
    mentions: list[MentionSpan]
    events: list[DraftEvent] = field(default_factory=list)


QUERY_CATEGORIES = ("entity", "relationship", "event", "document", "financial", "negative")


@dataclass
class DraftQuery:
    """A gold investigative question anchored to planted evidence snippets.

    ``category`` is one of :data:`QUERY_CATEGORIES`. Negative queries have no
    evidence: their gold relevant-chunk set is empty, for later
    refusal/no-evidence evaluation.
    """

    question: str
    category: str
    evidence: list[tuple[DraftDocument, str]]

    def __post_init__(self) -> None:
        if self.category not in QUERY_CATEGORIES:
            raise ValueError(f"unknown query category: {self.category!r}")
        if (self.category == "negative") != (not self.evidence):
            raise ValueError("negative queries (and only those) must have empty evidence")


class Cast:
    """The scenario's canonical entities."""

    def __init__(self) -> None:
        self.reyes = make_entity(EntityType.PERSON, "daniel-reyes", "Daniel Reyes", ("D. Reyes",))
        self.tran = make_entity(EntityType.PERSON, "olivia-tran", "Olivia Tran", ("O. Tran",))
        self.webb = make_entity(EntityType.PERSON, "marcus-webb", "Marcus Webb")
        self.sharma = make_entity(EntityType.PERSON, "priya-sharma", "Priya Sharma")
        self.vasquez = make_entity(EntityType.PERSON, "elena-vasquez", "Elena Vasquez")
        self.okafor = make_entity(EntityType.PERSON, "james-okafor", "James Okafor")
        self.meridian = make_entity(
            EntityType.ORGANIZATION,
            "meridian-aerospace",
            "Meridian Aerospace Systems",
            ("Meridian",),
        )
        self.northgate = make_entity(
            EntityType.ORGANIZATION,
            "northgate-supply",
            "Northgate Supply Solutions",
            ("Northgate",),
        )
        self.apex = make_entity(
            EntityType.ORGANIZATION, "apex-components", "Apex Components Inc.", ("Apex",)
        )
        self.crestline = make_entity(
            EntityType.ORGANIZATION, "crestline-holdings", "Crestline Holdings LLC"
        )
        self.falcon = make_entity(EntityType.PROJECT, "project-falcon", "Project Falcon")
        self.denver = make_entity(EntityType.LOCATION, "denver", "Denver, Colorado")
        self.reno = make_entity(EntityType.LOCATION, "reno", "Reno, Nevada")

        self.contract_value = money_entity(2_400_000)
        self.apex_bid = money_entity(1_800_000)
        self.kickback = money_entity(45_000)

    def people(self) -> list[Entity]:
        return [self.reyes, self.tran, self.webb, self.sharma, self.vasquez, self.okafor]


INVOICE_AMOUNTS = [310_000, 335_000, 360_000, 395_000, 430_000, 470_000]
INVOICE_NUMBERS = ["INV-1042", "INV-1045", "INV-1048", "INV-1051", "INV-1054", "INV-1057"]
INVOICE_MONTHS = [5, 6, 7, 8, 9, 10]


def _email_header(
    c: Composer,
    sender: Entity,
    sender_addr: str,
    recipient: Entity,
    recipient_addr: str,
    when: datetime,
    subject: str | None,
) -> None:
    """Write the email header. Pass ``subject=None`` when the subject line
    contains entity names; the caller must then compose it with mentions so
    the gold labels stay complete (see composer.py)."""
    c.text("From: ").mention(sender).text(f" <{sender_addr}>").line()
    c.text("To: ").mention(recipient).text(f" <{recipient_addr}>").line()
    c.text("Date: ").mention(date_entity(when)).line()
    if subject is not None:
        c.text(f"Subject: {subject}").para()


def build_planted_documents(cast: Cast) -> tuple[list[DraftDocument], list[DraftQuery]]:
    """Return the planted evidence documents and the gold queries they answer."""
    docs: list[DraftDocument] = []

    # 1. Kickoff memo — Jan 12, 2023
    c = Composer()
    c.text("INTERNAL MEMORANDUM — ").mention(cast.meridian).para()
    c.text("Date: ").mention(date_entity(dt(2023, 1, 12))).line()
    c.text("From: ").mention(cast.webb).text(", Chief Financial Officer").line()
    c.text("Re: ").mention(cast.falcon).text(" avionics upgrade program kickoff").para()
    c.text("The board has approved funding for ").mention(cast.falcon)
    c.text(", the avionics upgrade program for our regional fleet. Procurement will be ")
    c.text("led by ").mention(cast.reyes).text(", Director of Procurement, out of the ")
    c.mention(cast.denver).text(" headquarters. A competitive request for proposals is ")
    c.text("expected in February, with vendor selection in March.").para()
    c.text("Finance will require monthly invoice review for all program spend.")
    kickoff = DraftDocument(
        doc_type=DocumentType.MEMO,
        title="Project Falcon program kickoff",
        custodian="Marcus Webb",
        sent_at=dt(2023, 1, 12, 10, 15),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 1, 12),
                description="Project Falcon avionics upgrade program approved and kicked off",
                entities=[cast.webb, cast.meridian, cast.falcon],
            )
        ],
    )
    docs.append(kickoff)

    # 2. Private meeting notes — Feb 3, 2023
    c = Composer()
    c.text("MEETING NOTES (personal file of ").mention(cast.reyes).text(")").para()
    c.text("Date: ").mention(date_entity(dt(2023, 2, 3))).line()
    c.text("Location: Hillside Grill, ").mention(cast.denver).line()
    c.text("Attendees: ").mention(cast.reyes).text(", ").mention(cast.tran).para()
    c.text("Met with ").mention(cast.tran).text(" regarding the upcoming ")
    c.mention(cast.falcon).text(" solicitation. She confirmed ")
    c.mention(cast.northgate).text(" can be positioned for the award; entity is ")
    c.text("registered in ").mention(cast.reno).text(" with her as sole officer. ")
    c.text("Discussed a services arrangement through ").mention(cast.crestline)
    c.text(" once payments begin. Agreed to keep correspondence off company systems ")
    c.text("where possible.")
    meeting = DraftDocument(
        doc_type=DocumentType.MEETING_NOTES,
        title="Notes — Reyes and Tran, Hillside Grill",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 2, 3, 19, 40),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 2, 3),
                description=(
                    "Daniel Reyes and Olivia Tran meet privately to arrange the "
                    "Northgate award and Crestline payment structure"
                ),
                entities=[cast.reyes, cast.tran, cast.northgate, cast.crestline],
            )
        ],
    )
    docs.append(meeting)

    # 3. Tran follow-up email — Feb 4, 2023
    c = Composer()
    _email_header(
        c,
        cast.tran,
        "otran@northgate-supply.example",
        cast.reyes,
        "d.reyes@meridian-aero.example",
        dt(2023, 2, 4),
        "yesterday",
    )
    c.text("Daniel — good to catch up. ").mention(cast.northgate, "Northgate")
    c.text(" will be ready when the solicitation posts. I'll have ")
    c.mention(cast.crestline).text(" paperwork finalized this month so the consulting ")
    c.text("arrangement is in place before any funds move. Talk soon. — ")
    c.mention(cast.tran, "O. Tran")
    followup = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="Re: yesterday",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 2, 4, 8, 5),
        body=c.build(),
        mentions=c.spans,
    )
    docs.append(followup)

    # 4. RFP memo — Feb 20, 2023
    c = Composer()
    c.text("PROCUREMENT NOTICE — ").mention(cast.meridian).para()
    c.text("Date: ").mention(date_entity(dt(2023, 2, 20))).line()
    c.text("Issued by: ").mention(cast.reyes).text(", Director of Procurement").para()
    c.text("Request for proposals RFP-2023-011 is issued today for the ")
    c.mention(cast.falcon).text(" avionics upgrade program. Sealed bids are due ")
    c.mention(date_entity(dt(2023, 3, 10)))
    c.text(". Evaluation criteria: price (40%), schedule (30%), ")
    c.text("technical responsiveness (30%).")
    rfp = DraftDocument(
        doc_type=DocumentType.MEMO,
        title="RFP-2023-011 issued for Project Falcon",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 2, 20, 14, 0),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 2, 20),
                description="RFP-2023-011 issued for Project Falcon avionics work",
                entities=[cast.reyes, cast.meridian, cast.falcon],
            )
        ],
    )
    docs.append(rfp)

    # 5. Apex bid email — Mar 10, 2023
    c = Composer()
    _email_header(
        c,
        cast.okafor,
        "j.okafor@apex-components.example",
        cast.reyes,
        "d.reyes@meridian-aero.example",
        dt(2023, 3, 10),
        None,
    )
    c.text("Subject: RFP-2023-011 — ").mention(cast.apex, "Apex Components")
    c.text(" bid submission").para()
    c.text("Dear Mr. Reyes,").para()
    c.text("Please find attached the sealed bid from ").mention(cast.apex)
    c.text(" for RFP-2023-011. Our total fixed price for the ").mention(cast.falcon)
    c.text(" avionics scope is ").mention(cast.apex_bid)
    c.text(", inclusive of installation and certification support, with a ")
    c.text("14-month delivery schedule.").para()
    c.text("Regards,").line().mention(cast.okafor).line()
    c.text("VP Sales, ").mention(cast.apex, "Apex")
    apex_bid = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="RFP-2023-011 — Apex Components bid submission",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 3, 10, 11, 22),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 3, 10),
                description="Apex Components submits a $1,800,000 bid for RFP-2023-011",
                entities=[cast.okafor, cast.apex, cast.apex_bid],
            )
        ],
    )
    docs.append(apex_bid)

    # 6. Northgate bid email — Mar 10, 2023
    c = Composer()
    _email_header(
        c,
        cast.tran,
        "otran@northgate-supply.example",
        cast.reyes,
        "d.reyes@meridian-aero.example",
        dt(2023, 3, 10),
        None,
    )
    c.text("Subject: RFP-2023-011 — ").mention(cast.northgate).text(" proposal").para()
    c.text("Mr. Reyes,").para()
    c.text("On behalf of ").mention(cast.northgate).text(", I am pleased to submit our ")
    c.text("proposal for RFP-2023-011. Our total price for the ").mention(cast.falcon)
    c.text(" avionics scope is ").mention(cast.contract_value)
    c.text(", with a 12-month accelerated delivery schedule.").para()
    c.text("Sincerely,").line().mention(cast.tran).line()
    c.text("Principal, ").mention(cast.northgate, "Northgate")
    northgate_bid = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="RFP-2023-011 — Northgate Supply Solutions proposal",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 3, 10, 16, 48),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 3, 10),
                description=(
                    "Northgate Supply Solutions submits a $2,400,000 bid for RFP-2023-011"
                ),
                entities=[cast.tran, cast.northgate, cast.contract_value],
            )
        ],
    )
    docs.append(northgate_bid)

    # 7. Award memo — Mar 24, 2023
    c = Composer()
    c.text("AWARD DECISION MEMORANDUM — RFP-2023-011").para()
    c.text("Date: ").mention(date_entity(dt(2023, 3, 24))).line()
    c.text("Approved by: ").mention(cast.reyes).text(", Director of Procurement").para()
    c.text("The ").mention(cast.falcon).text(" avionics contract is awarded to ")
    c.mention(cast.northgate).text(" at a total value of ").mention(cast.contract_value)
    c.text(". Two responsive bids were received: ").mention(cast.apex).text(" at ")
    c.mention(cast.apex_bid).text(" and ").mention(cast.northgate, "Northgate")
    c.text(" at ").mention(cast.contract_value, "$2,400,000").text(".").para()
    c.text("Justification: although ").mention(cast.apex, "Apex")
    c.text(" submitted the lower price, ").mention(cast.northgate, "Northgate")
    c.text(" was selected on schedule risk and vendor responsiveness grounds; its ")
    c.text("12-month accelerated schedule avoids projected fleet downtime penalties. ")
    c.text("This determination was made solely by the Director of Procurement under ")
    c.text("delegated authority.")
    award = DraftDocument(
        doc_type=DocumentType.MEMO,
        title="Award decision memorandum — RFP-2023-011",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 3, 24, 15, 30),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 3, 24),
                description=(
                    "Daniel Reyes awards the Project Falcon contract to Northgate "
                    "despite Apex's lower bid"
                ),
                entities=[cast.reyes, cast.northgate, cast.apex, cast.falcon],
            )
        ],
    )
    docs.append(award)

    # 8. Congratulations email — Mar 25, 2023
    c = Composer()
    _email_header(
        c,
        cast.reyes,
        "d.reyes@meridian-aero.example",
        cast.tran,
        "otran@northgate-supply.example",
        dt(2023, 3, 25),
        "award posted",
    )
    c.text("Olivia — the award memo went out yesterday. ")
    c.mention(cast.northgate, "Northgate").text(" should receive the countersignature ")
    c.text("package next week. Let's keep the other matter to the channel we discussed. — D.")
    congrats = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="award posted",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 3, 25, 9, 2),
        body=c.build(),
        mentions=c.spans,
    )
    docs.append(congrats)

    # 9. Master supply agreement — Apr 5, 2023
    c = Composer()
    c.text("MASTER SUPPLY AGREEMENT No. MSA-2023-004").para()
    c.text("Effective Date: ").mention(date_entity(dt(2023, 4, 5))).para()
    c.text("This Master Supply Agreement is entered into between ")
    c.mention(cast.meridian).text(", a Delaware corporation with principal offices in ")
    c.mention(cast.denver).text(' ("Buyer"), and ').mention(cast.northgate)
    c.text(", a Nevada limited liability company registered in ").mention(cast.reno)
    c.text(' ("Supplier").').para()
    c.text("1. Scope. Supplier shall furnish avionics units, integration hardware, and ")
    c.text("certification support for the ").mention(cast.falcon).text(" program.").para()
    c.text("2. Contract Value. The total not-to-exceed value of this Agreement is ")
    c.mention(cast.contract_value)
    c.text(", payable against monthly invoices for delivered milestones.").para()
    c.text("3. Term. Twelve (12) months from the Effective Date.").para()
    c.text("Signed: ").mention(cast.reyes).text(" for Buyer; ").mention(cast.tran)
    c.text(" for Supplier.")
    contract = DraftDocument(
        doc_type=DocumentType.CONTRACT,
        title="Master Supply Agreement MSA-2023-004",
        custodian="Legal Department",
        sent_at=dt(2023, 4, 5, 12, 0),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 4, 5),
                description=(
                    "Master Supply Agreement MSA-2023-004 signed with Northgate for $2,400,000"
                ),
                entities=[
                    cast.meridian,
                    cast.northgate,
                    cast.reyes,
                    cast.tran,
                    cast.contract_value,
                ],
            )
        ],
    )
    docs.append(contract)

    # 10-15. Monthly invoices — May..Oct 2023
    invoices: list[DraftDocument] = []
    for number, amount, month in zip(INVOICE_NUMBERS, INVOICE_AMOUNTS, INVOICE_MONTHS, strict=True):
        due = money_entity(amount)
        last_day = {5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31}[month]
        when = dt(2023, month, last_day)
        c = Composer()
        c.mention(cast.northgate).line()
        c.text(f"Invoice {number}").line()
        c.text("Date: ").mention(date_entity(when)).line()
        c.text("Bill To: ").mention(cast.meridian).text(", ").mention(cast.denver).line()
        c.text("Reference: MSA-2023-004, ").mention(cast.falcon).para()
        c.text("Avionics units and integration services delivered for the month — ")
        c.text("milestone billing per Section 2.").para()
        c.text("Total Due: ").mention(due)
        invoices.append(
            DraftDocument(
                doc_type=DocumentType.INVOICE,
                title=f"Northgate invoice {number}",
                custodian="Accounts Payable",
                sent_at=when,
                body=c.build(),
                mentions=c.spans,
            )
        )
    docs.extend(invoices)

    # 16. Kickback email — Jun 18, 2023
    c = Composer()
    _email_header(
        c,
        cast.tran,
        "otran@northgate-supply.example",
        cast.reyes,
        "dreyes.personal@fastmail.example",
        dt(2023, 6, 18),
        "consulting arrangement — first installment",
    )
    c.text("D — first installment went out today: ").mention(cast.northgate, "Northgate")
    c.text(" wired ").mention(cast.kickback).text(" to ").mention(cast.crestline)
    c.text(" under the consulting services agreement. Same schedule each quarter while ")
    c.text("invoicing continues. Delete after reading. — O.")
    kickback = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="consulting arrangement — first installment",
        custodian="Daniel Reyes",
        sent_at=dt(2023, 6, 18, 21, 17),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 6, 18),
                description=(
                    "Northgate wires $45,000 to Crestline Holdings LLC as the first "
                    "kickback installment"
                ),
                entities=[cast.northgate, cast.crestline, cast.kickback, cast.tran],
            )
        ],
    )
    docs.append(kickback)

    # 17. AP flag email — Aug 8, 2023
    c = Composer()
    _email_header(
        c,
        cast.vasquez,
        "e.vasquez@meridian-aero.example",
        cast.webb,
        "m.webb@meridian-aero.example",
        dt(2023, 8, 8),
        None,
    )
    c.text("Subject: ").mention(cast.northgate, "Northgate").text(" invoice growth").para()
    c.text("Marcus,").para()
    c.text("Flagging a pattern in accounts payable: ").mention(cast.northgate)
    c.text(" invoices on ").mention(cast.falcon).text(" have increased every month ")
    c.text("since May while the delivery reports attached to them are nearly ")
    c.text("identical. August's draft invoice is ").mention(money_entity(395_000))
    c.text(" against a May baseline of ").mention(money_entity(310_000)).text(".").para()
    c.text("Elena")
    ap_flag = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="Northgate invoice growth",
        custodian="Marcus Webb",
        sent_at=dt(2023, 8, 8, 10, 41),
        body=c.build(),
        mentions=c.spans,
    )
    docs.append(ap_flag)

    # 18. CFO variance email — Aug 9, 2023
    c = Composer()
    _email_header(
        c,
        cast.webb,
        "m.webb@meridian-aero.example",
        cast.reyes,
        "d.reyes@meridian-aero.example",
        dt(2023, 8, 9),
        None,
    )
    c.text("Subject: ").mention(cast.falcon).text(" invoice variance").para()
    c.text("Daniel,").para()
    c.text("Finance is seeing a 27% escalation in ").mention(cast.northgate, "Northgate")
    c.text(" monthly billing on ").mention(cast.falcon).text(" with no corresponding ")
    c.text("change in delivered scope. Before I approve the August payment run, I need ")
    c.text("a milestone-by-milestone reconciliation against MSA-2023-004. Please have ")
    c.text("it to me by Friday.").para()
    c.mention(cast.webb, "Marcus Webb").line().text("CFO, ").mention(cast.meridian, "Meridian")
    variance = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="Project Falcon invoice variance",
        custodian="Marcus Webb",
        sent_at=dt(2023, 8, 9, 9, 5),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 8, 9),
                description=(
                    "CFO Marcus Webb questions Northgate invoice variance and demands "
                    "reconciliation"
                ),
                entities=[cast.webb, cast.reyes, cast.northgate, cast.falcon],
            )
        ],
    )
    docs.append(variance)

    # 19. Audit request email — Sep 14, 2023
    c = Composer()
    _email_header(
        c,
        cast.sharma,
        "p.sharma@meridian-aero.example",
        cast.reyes,
        "d.reyes@meridian-aero.example",
        dt(2023, 9, 14),
        None,
    )
    c.text("Subject: Internal audit — ").mention(cast.falcon)
    c.text(" procurement (document hold)").para()
    c.text("Mr. Reyes,").para()
    c.text("Internal Audit has opened engagement IA-2023-19 covering ")
    c.mention(cast.falcon).text(" procurement, effective today. Please preserve and ")
    c.text("produce: the RFP-2023-011 evaluation file, all ")
    c.mention(cast.northgate, "Northgate").text(" invoices and delivery reports, and ")
    c.text("all correspondence with ").mention(cast.northgate, "Northgate")
    c.text(" principals. ").mention(cast.vasquez).text(" is assisting with the AP ")
    c.text("records pull.").para()
    c.mention(cast.sharma).line().text("Senior Internal Auditor")
    audit_req = DraftDocument(
        doc_type=DocumentType.EMAIL,
        title="Internal audit — Project Falcon procurement (document hold)",
        custodian="Priya Sharma",
        sent_at=dt(2023, 9, 14, 8, 30),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 9, 14),
                description=(
                    "Priya Sharma opens internal audit IA-2023-19 into Project Falcon procurement"
                ),
                entities=[cast.sharma, cast.falcon, cast.reyes],
            )
        ],
    )
    docs.append(audit_req)

    # 20. Audit findings memo — Oct 30, 2023
    c = Composer()
    c.text("INTERNAL AUDIT MEMORANDUM — IA-2023-19 (PRIVILEGED AND CONFIDENTIAL)").para()
    c.text("Date: ").mention(date_entity(dt(2023, 10, 30))).line()
    c.text("Author: ").mention(cast.sharma).text(", Senior Internal Auditor").line()
    c.text("Distribution: ").mention(cast.webb).text("; Audit Committee").para()
    c.text("Finding 1 — Duplicate billing. ").mention(cast.northgate)
    c.text(" invoice INV-1051 was paid twice: once as submitted and once as a ")
    c.text('resubmission labeled "INV-1051R" with an identical delivery report. ')
    c.text("Combined overpayment: ").mention(money_entity(395_000)).text(".").para()
    c.text("Finding 2 — Undisclosed related party. Public records show ")
    c.mention(cast.northgate, "Northgate").text(" is registered in ").mention(cast.reno)
    c.text(" with ").mention(cast.tran).text(" as sole officer, and that quarterly ")
    c.text("payments from ").mention(cast.northgate, "Northgate").text(" flow to ")
    c.mention(cast.crestline).text(", whose registered agent address matches a ")
    c.text("property associated with ").mention(cast.reyes).text(".").para()
    c.text("Finding 3 — Award irregularity. The RFP-2023-011 file contains no ")
    c.text("evaluation scoring sheets; the award to ").mention(cast.northgate, "Northgate")
    c.text(" over the lower ").mention(cast.apex).text(" bid rests on a single ")
    c.text("unsupported memorandum.").para()
    c.text("Recommendation: suspend payments, refer to outside counsel, and restrict ")
    c.text("the procurement authority of ").mention(cast.reyes).text(" pending review.")
    audit_memo = DraftDocument(
        doc_type=DocumentType.MEMO,
        title="Internal audit memorandum IA-2023-19",
        custodian="Priya Sharma",
        sent_at=dt(2023, 10, 30, 17, 45),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 10, 30),
                description=(
                    "Audit IA-2023-19 finds duplicate invoice INV-1051/INV-1051R and "
                    "the Northgate–Crestline–Reyes link"
                ),
                entities=[cast.sharma, cast.northgate, cast.crestline, cast.reyes],
            )
        ],
    )
    docs.append(audit_memo)

    # 21. HR leave memo — Nov 15, 2023
    c = Composer()
    c.text("HUMAN RESOURCES — CONFIDENTIAL PERSONNEL ACTION").para()
    c.text("Date: ").mention(date_entity(dt(2023, 11, 15))).para()
    c.text("Effective immediately, ").mention(cast.reyes)
    c.text(", Director of Procurement, is placed on paid administrative leave pending ")
    c.text("the outcome of audit IA-2023-19 and an external investigation. Building ")
    c.text("and systems access are suspended. Inquiries to the Office of the General ")
    c.text("Counsel, ").mention(cast.meridian).text(", ").mention(cast.denver).text(".")
    hr_memo = DraftDocument(
        doc_type=DocumentType.MEMO,
        title="Personnel action — administrative leave",
        custodian="Human Resources",
        sent_at=dt(2023, 11, 15, 13, 20),
        body=c.build(),
        mentions=c.spans,
        events=[
            DraftEvent(
                occurred_at=dt(2023, 11, 15),
                description=("Daniel Reyes placed on administrative leave pending investigation"),
                entities=[cast.reyes, cast.meridian],
            )
        ],
    )
    docs.append(hr_memo)

    queries = [
        # --- entity lookup ---
        DraftQuery(
            "Who is the Director of Procurement at Meridian Aerospace Systems?",
            "entity",
            [(kickoff, "led by")],
        ),
        DraftQuery(
            "Who is the Chief Financial Officer of Meridian Aerospace Systems?",
            "entity",
            [(kickoff, "Chief Financial Officer")],
        ),
        DraftQuery(
            "Where is Northgate Supply Solutions registered and who controls it?",
            "entity",
            [
                (audit_memo, "as sole officer, and that quarterly"),
                (meeting, "with her as sole officer"),
            ],
        ),
        DraftQuery(
            "Which auditor led internal audit engagement IA-2023-19?",
            "entity",
            [(audit_memo, "Senior Internal Auditor")],
        ),
        DraftQuery(
            "Who assisted with the accounts payable records pull for the audit?",
            "entity",
            [(audit_req, "is assisting with the AP")],
        ),
        # --- relationship ---
        DraftQuery(
            "What is the relationship between Daniel Reyes and Crestline Holdings?",
            "relationship",
            [(audit_memo, "property associated with")],
        ),
        DraftQuery(
            "How are Olivia Tran and Northgate Supply Solutions connected?",
            "relationship",
            [(meeting, "can be positioned for the award; entity is")],
        ),
        DraftQuery(
            "Which vendors submitted bids for RFP-2023-011?",
            "relationship",
            [
                (apex_bid, "Please find attached the sealed bid from"),
                (northgate_bid, "I am pleased to submit our"),
            ],
        ),
        DraftQuery(
            "Who did Elena Vasquez report the invoice pattern to?",
            "relationship",
            [(ap_flag, "Flagging a pattern in accounts payable")],
        ),
        DraftQuery(
            "Who communicated with Daniel Reyes at a personal email address?",
            "relationship",
            [(kickback, "first installment went out today")],
        ),
        DraftQuery(
            "Who raised concerns about Northgate invoice variances on Project Falcon?",
            "relationship",
            [
                (variance, "Finance is seeing a 27% escalation in"),
                (ap_flag, "have increased every month"),
            ],
        ),
        # --- event / timeline ---
        DraftQuery(
            "When was Project Falcon approved and kicked off?",
            "event",
            [(kickoff, "The board has approved funding for")],
        ),
        DraftQuery(
            "When was RFP-2023-011 issued for Project Falcon?",
            "event",
            [(rfp, "Request for proposals RFP-2023-011 is issued today")],
        ),
        DraftQuery(
            "When was the master supply agreement with Northgate signed?",
            "event",
            [(contract, "This Master Supply Agreement is entered into between")],
        ),
        DraftQuery(
            "When did Northgate make its first payment to Crestline Holdings?",
            "event",
            [(kickback, "Same schedule each quarter while")],
        ),
        DraftQuery(
            "When did the internal audit of Project Falcon procurement begin?",
            "event",
            [(audit_req, "Internal Audit has opened engagement IA-2023-19")],
        ),
        DraftQuery(
            "When did Daniel Reyes and Olivia Tran first meet about Project Falcon?",
            "event",
            [(meeting, "solicitation. She confirmed")],
        ),
        DraftQuery(
            "What happened to Daniel Reyes after the audit findings?",
            "event",
            [(hr_memo, "is placed on paid administrative leave pending")],
        ),
        # --- document-specific evidence ---
        DraftQuery(
            "Who approved the award of the Project Falcon contract?",
            "document",
            [(award, "This determination was made solely by the Director of Procurement")],
        ),
        DraftQuery(
            "Why was Northgate selected over Apex despite the higher bid?",
            "document",
            [(award, "was selected on schedule risk and vendor responsiveness grounds")],
        ),
        DraftQuery(
            "What did the internal audit find about Northgate invoices?",
            "document",
            [(audit_memo, "invoice INV-1051 was paid twice")],
        ),
        DraftQuery(
            "What irregularity did the audit find in the RFP-2023-011 evaluation file?",
            "document",
            [(audit_memo, "contains no")],
        ),
        DraftQuery(
            "What did Reyes and Tran agree about communications during their February meeting?",
            "document",
            [(meeting, "Agreed to keep correspondence off company systems")],
        ),
        # --- financial / invoice ---
        DraftQuery(
            "What is the total value of the master supply agreement with Northgate?",
            "financial",
            [(contract, "The total not-to-exceed value of this Agreement is")],
        ),
        DraftQuery(
            "What was Apex Components' bid for the Project Falcon avionics work?",
            "financial",
            [(apex_bid, "inclusive of installation and certification support")],
        ),
        DraftQuery(
            "What payments did Northgate make to Crestline Holdings?",
            "financial",
            [
                (kickback, "under the consulting services agreement"),
                (audit_memo, "whose registered agent address matches a"),
            ],
        ),
        DraftQuery(
            "Which invoice did the audit flag as billed twice?",
            "financial",
            [(audit_memo, 'resubmission labeled "INV-1051R"')],
        ),
        DraftQuery(
            "How did Northgate's monthly invoice amounts change on Project Falcon?",
            "financial",
            [(ap_flag, "against a May baseline of")],
        ),
        # --- negative / unsupported (empty gold evidence, for refusal evaluation) ---
        DraftQuery(
            "What did outside counsel's final investigation report conclude?",
            "negative",
            [],
        ),
        DraftQuery(
            "Were any Project Falcon payments routed to accounts outside the United States?",
            "negative",
            [],
        ),
        DraftQuery(
            "What criminal charges were filed against Daniel Reyes?",
            "negative",
            [],
        ),
        DraftQuery(
            "Did Apex Components file a bid protest after losing RFP-2023-011?",
            "negative",
            [],
        ),
    ]
    return docs, queries
