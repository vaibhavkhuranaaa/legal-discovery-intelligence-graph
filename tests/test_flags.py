"""Tests for the deterministic privilege/PII detector in review.flags."""

from legal_discovery_graph.review.flags import TextFlags, flag_text

# --- Privilege marker phrases -----------------------------------------------


def test_attorney_client_privileged_hyphenated() -> None:
    flags = flag_text("This memo is Attorney-Client Privileged in its entirety.")
    assert flags.privileged is True
    assert flags.privilege_markers == ("Attorney-Client Privileged",)


def test_attorney_client_privileged_no_hyphen() -> None:
    flags = flag_text("Marked attorney client privileged before distribution.")
    assert flags.privileged is True
    assert flags.privilege_markers == ("attorney client privileged",)


def test_attorney_work_product() -> None:
    flags = flag_text("Prepared as Attorney Work Product for litigation.")
    assert flags.privileged is True
    assert "Attorney Work Product" in flags.privilege_markers


def test_privileged_and_confidential() -> None:
    flags = flag_text("Privileged and Confidential - do not forward.")
    assert flags.privileged is True
    assert "Privileged and Confidential" in flags.privilege_markers


def test_prepared_at_direction_of_counsel() -> None:
    flags = flag_text("This report was prepared at the direction of counsel.")
    assert flags.privileged is True
    assert "prepared at the direction of counsel" in flags.privilege_markers


# --- "legal advice" context requirement -------------------------------------


def test_legal_advice_seeking_context_flags() -> None:
    flags = flag_text("The client is seeking legal advice on the merger.")
    assert flags.privileged is True
    assert flags.privilege_markers == ("seeking legal advice",)


def test_legal_advice_requesting_context_flags() -> None:
    flags = flag_text("She is requesting legal advice before signing.")
    assert flags.privileged is True


def test_legal_advice_provide_variants_flag() -> None:
    for phrase in ("provide legal advice", "provides legal advice", "provided legal advice"):
        flags = flag_text(f"Counsel {phrase} regularly.")
        assert flags.privileged is True, phrase


def test_legal_advice_for_context_flags() -> None:
    flags = flag_text("We reached out for legal advice on the contract.")
    assert flags.privileged is True


def test_legal_advice_bare_phrase_does_not_flag() -> None:
    flags = flag_text("Please route the ticket to the legal advice department.")
    assert flags.privileged is False
    assert flags.privilege_markers == ()


# --- Counsel-domain email matching ------------------------------------------


def test_counsel_domain_email_flags() -> None:
    flags = flag_text(
        "Please loop in jdoe@hartwellpace.com on this thread.",
        counsel_domains=("hartwellpace.com",),
    )
    assert flags.privileged is True
    assert flags.privilege_markers == ("jdoe@hartwellpace.com",)


def test_counsel_domain_is_case_insensitive() -> None:
    flags = flag_text(
        "Cc: JDOE@HARTWELLPACE.COM",
        counsel_domains=("hartwellpace.com",),
    )
    assert flags.privileged is True


def test_counsel_domain_subdomain_matches() -> None:
    flags = flag_text(
        "From: jdoe@mail.hartwellpace.com",
        counsel_domains=("hartwellpace.com",),
    )
    assert flags.privileged is True


def test_counsel_domain_not_a_suffix_match() -> None:
    flags = flag_text(
        "From: jdoe@nothartwellpace.com",
        counsel_domains=("hartwellpace.com",),
    )
    assert flags.privileged is False
    assert flags.privilege_markers == ()


def test_no_counsel_domains_provided_no_email_flag() -> None:
    flags = flag_text("From: jdoe@hartwellpace.com")
    assert flags.privileged is False


# --- PII: ssn -----------------------------------------------------------


def test_ssn_hyphenated_matches() -> None:
    flags = flag_text("SSN on file: 123-45-6789.")
    assert flags.pii_types == ("ssn",)


def test_ssn_context_nine_digit_run_matches() -> None:
    flags = flag_text("The applicant's social security number is 123456789 per HR.")
    assert flags.pii_types == ("ssn",)


def test_ssn_context_ssn_label_matches() -> None:
    flags = flag_text("SSN: 987654321 confirmed against the W-2.")
    assert flags.pii_types == ("ssn",)


# --- PII: bank_account ----------------------------------------------------


def test_bank_account_number_context_matches() -> None:
    flags = flag_text("Wire funds to account number 123456789012 by Friday.")
    assert flags.pii_types == ("bank_account",)


def test_bank_account_iban_context_matches() -> None:
    flags = flag_text("IBAN reference 12345678 was used for the transfer.")
    assert flags.pii_types == ("bank_account",)


# --- PII: routing_number --------------------------------------------------


def test_routing_number_context_matches() -> None:
    flags = flag_text("Our routing number is 021000021 for domestic wires.")
    assert flags.pii_types == ("routing_number",)


def test_routing_number_aba_context_matches() -> None:
    flags = flag_text("ABA 021000021 confirmed with the bank.")
    assert flags.pii_types == ("routing_number",)


def test_routing_context_nine_digits_not_also_ssn() -> None:
    flags = flag_text("Please confirm the routing number 021000021 before wiring.")
    assert flags.pii_types == ("routing_number",)


# --- PII: negatives --------------------------------------------------------


def test_invoice_number_does_not_flag_pii() -> None:
    flags = flag_text("Reference invoice INV-2024-0042 for this charge.")
    assert flags.pii_types == ()


def test_bare_nine_digit_number_no_context_does_not_flag() -> None:
    flags = flag_text("The reference code was 123456789 and nothing else.")
    assert flags.pii_types == ()


def test_hyphenated_boundary_does_not_partially_match_ssn() -> None:
    flags = flag_text("Please review order 123-45-67890 from the warehouse.")
    assert flags.pii_types == ()


# --- Combined dedup / ordering ----------------------------------------------


def test_markers_deduped_and_ordered_by_first_appearance() -> None:
    text = (
        "This is attorney work product. Later we repeat: ATTORNEY WORK PRODUCT. "
        "Also attorney-client privileged applies."
    )
    flags = flag_text(text)
    assert flags.privilege_markers == (
        "attorney work product",
        "attorney-client privileged",
    )


def test_multiple_marker_types_combined_in_order() -> None:
    text = "We are seeking legal advice. This is privileged and confidential."
    flags = flag_text(text)
    assert flags.privilege_markers == (
        "seeking legal advice",
        "privileged and confidential",
    )


# --- Empty input -------------------------------------------------------------


def test_empty_text_returns_no_flags() -> None:
    flags = flag_text("")
    assert flags == TextFlags(privileged=False, privilege_markers=(), pii_types=())
