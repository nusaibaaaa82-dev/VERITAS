#!/usr/bin/env python3
"""VERITAS Evidence Curation Command Line Interface (Local-Only Tooling).

Allows human reviewers and researchers to safely inspect, evaluate, curate,
and trace scientific evidence without exposing web administrative endpoints.

Commands:
    list        View paginated evidence records waiting for review or filtered by status.
    inspect     Inspect one evidence record in detail with content, quality, and provenance.
    review      Submit an explicit, human-confirmed review decision (UNDER_REVIEW, APPROVED_VERIFIED, REJECTED_*).
    history     View the full chronological audit history for an evidence record.
    stats       View aggregate curation status breakdown and verification counts.
    export      Safely export curated records and complete audit history to a new timestamped JSON file.

Usage:
    python -m backend.curation.curate list [--status STATUS] [--domain DOMAIN] [--limit LIMIT] [--offset OFFSET]
    python -m backend.curation.curate inspect <evidence_id>
    python -m backend.curation.curate review --id <id> --status <status> --reviewer <reviewer> [--stance <stance>] [--notes <notes>] [--peer-reviewed] [--yes]
    python -m backend.curation.curate history <evidence_id>
    python -m backend.curation.curate stats
    python -m backend.curation.curate export [--status STATUS] [--output PATH] [--overwrite]
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import List, Optional

# Ensure workspace root is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.config import settings
from backend.schemas.claim import (
    CurationAuditLogEntry,
    CurationReviewDecision,
    CurationStatus,
    EvidenceItem,
    ReviewerConfirmedStance,
)
from backend.services.evidence_repository import EvidenceRepository
from backend.services.normalization import normalize_domain

VALID_STATUSES = [
    "UNREVIEWED",
    "UNDER_REVIEW",
    "APPROVED_VERIFIED",
    "REJECTED_IRRELEVANT",
    "REJECTED_UNRELIABLE",
    "SUPERSEDED",
]

DECISIVE_STANCES = ["SUPPORTING", "CONTRADICTING"]
VALID_STANCES = ["SUPPORTING", "CONTRADICTING", "NEUTRAL"]


def get_repository(db_path: Optional[str] = None) -> EvidenceRepository:
    """Initialize EvidenceRepository for the specified or default database path."""
    return EvidenceRepository(db_path=db_path or settings.EVIDENCE_DB_PATH)


def get_text_availability_label(availability: str, is_full_text: bool) -> str:
    """Return explicit human-readable description for text availability tier."""
    avail_upper = (availability or "").upper()
    if is_full_text or avail_upper == "FULL_TEXT":
        return "FULL_TEXT (Complete original article text verified and stored locally)"
    elif avail_upper == "ABSTRACT":
        return "ABSTRACT (Publisher abstract only; full study body must be inspected externally)"
    elif avail_upper == "EXCERPT":
        return "EXCERPT (Extracted passage/snippet; reviewer must verify verbatim presence in primary source)"
    elif avail_upper == "METADATA_ONLY":
        return "METADATA_ONLY (Citation and bibliographic metadata only; NO body text stored locally)"
    else:
        return f"{avail_upper} (Unclassified availability level)"


def get_text_provenance_label(provenance: str) -> str:
    """Return explicit human-readable description for text provenance tier."""
    prov_upper = (provenance or "").upper()
    if prov_upper == "VERBATIM":
        return "VERBATIM (Exact word-for-word excerpt/quotation from primary source document)"
    elif prov_upper == "SUMMARY":
        return "SUMMARY (Faithful summarized or paraphrased overview; NOT a direct quotation)"
    elif prov_upper == "INTERPRETATION":
        return "INTERPRETATION (Legal analysis, statutory synthesis, or editorial commentary; NOT a direct quotation)"
    elif prov_upper == "UNAVAILABLE":
        return "UNAVAILABLE (No substantive body text stored locally; metadata/citation only)"
    else:
        return f"{prov_upper} (Unclassified text provenance)"


def get_retrieval_method_label(method: str) -> str:
    """Return explicit human-readable description for retrieval origin."""
    meth_upper = (method or "").upper()
    if meth_upper == "LIVE":
        return "LIVE (Retrieved directly over live network connection from official provider)"
    elif meth_upper == "OFFLINE_FALLBACK":
        return "OFFLINE_FALLBACK (Loaded from local/resilient offline catalog; not live-verified)"
    elif meth_upper == "UNKNOWN":
        return "UNKNOWN (Retrieval origin unspecified; cannot assume live verification)"
    else:
        return f"{meth_upper} (Unknown retrieval method)"


def display_content_accessibility_warnings(item: EvidenceItem) -> None:
    """Display prominent reviewer warnings if original source text, domain, or URL has integrity issues."""
    has_warning = False

    # 1. Inconsistent domain check (URL host vs stored database domain)
    derived_domain = normalize_domain(item.canonical_url or item.url or item.original_url)
    stored_domain = (item.source_domain or "").lower()
    if derived_domain and stored_domain and derived_domain != stored_domain:
        print(f"  ! [CRITICAL DOMAIN MISMATCH]")
        print(f"      Stored Database Domain: '{item.source_domain}'")
        print(f"      Actual URL Host Domain: '{derived_domain}'")
        print("      Inconsistent publisher/domain metadata detected! The source URL belongs to a different domain.")
        has_warning = True

    # 2. Text provenance warnings (Prevent summaries/interpretations from being represented as direct quotations)
    if item.text_provenance in ("SUMMARY", "INTERPRETATION"):
        article = "an" if item.text_provenance == "INTERPRETATION" else "a"
        print(f"  ! [WARNING: {item.text_provenance} TEXT]")
        print(f"      Text is {article} {item.text_provenance.lower()}, NOT an exact verbatim quotation.")
        print("      Reviewer must NOT represent this content as a direct quotation.")
        print("      Inspect canonical URL directly to obtain authentic source wording.")
        has_warning = True
    elif item.text_provenance == "UNAVAILABLE":
        print("  ! [WARNING: TEXT UNAVAILABLE]")
        print("      No substantive body text is stored for this record.")
        has_warning = True

    # 3. Text accessibility tier warnings
    if item.text_availability in ("METADATA_ONLY", "UNDETERMINED"):
        print("  ! [WARNING: METADATA ONLY]")
        print("      Full textual content is NOT stored locally (Availability: METADATA_ONLY).")
        print("      The reviewer MUST independently inspect the primary source document before approving.")
        has_warning = True
    elif item.text_availability == "EXCERPT" and not item.is_full_text and item.text_provenance == "VERBATIM":
        print("  ! [NOTICE: EXCERPT TEXT]")
        print("      Snippet is an extracted passage, not the full document.")
        print("      Reviewer must verify that the quoted text genuinely appears in the cited source.")
        has_warning = True

    # 4. Retrieval method warning
    if item.retrieval_method == "OFFLINE_FALLBACK":
        print("  ! [NOTICE: OFFLINE FALLBACK CATALOG ENTRY]")
        print("      Record originated from offline catalog fallback, NOT a verified live network response.")
        print("      Do NOT describe this content as live-verified without independent confirmation.")
        has_warning = True
    elif item.retrieval_method == "UNKNOWN":
        print("  ! [NOTICE: UNKNOWN RETRIEVAL ORIGIN]")
        print("      Retrieval origin is unspecified. Do NOT assume live retrieval without external verification.")
        has_warning = True

    # 5. Missing or inaccessible URL
    if not item.canonical_url and not item.original_url and not item.url:
        print("  ! [CRITICAL: INACCESSIBLE SOURCE]")
        print("      No source URL or DOI is associated with this record. Provenance cannot be verified externally.")
        has_warning = True

    # 6. Syndication notice
    if item.is_potential_syndication:
        syn_notes = item.syndication_notes or "Potential syndicated wire dispatch"
        print(f"  ! [NOTICE: SYNDICATED DISPATCH]")
        print(f"      {syn_notes}")
        print("      Do not count as an independent source from the original wire agency.")
        has_warning = True

    if has_warning:
        print("  " + "-" * 76)


def cmd_stats(args) -> int:
    """Display aggregate counts across all curation statuses."""
    repo = get_repository(args.db)
    stats = repo.get_curation_stats()
    total_records = sum(stats.values())

    print("=" * 68)
    print("VERITAS EVIDENCE CURATION STATUS SUMMARY")
    print("=" * 68)
    print(f"Database Path:          {repo.db_path}")
    print(f"Total Evidence Records: {total_records}")
    print("-" * 68)
    print(f"{'STATUS':<25} {'COUNT':<10} {'PERCENTAGE':<12}")
    print("-" * 68)

    for status in VALID_STATUSES:
        count = stats.get(status, 0)
        pct = (count / total_records * 100.0) if total_records > 0 else 0.0
        verified_tag = " [VERIFIED]" if status == "APPROVED_VERIFIED" else ""
        print(f"{status:<25} {count:<10} {pct:>6.1f}%{verified_tag}")

    print("=" * 68)
    return 0


def cmd_list(args) -> int:
    """List paginated evidence records filtered by status and domain."""
    repo = get_repository(args.db)
    status_filter = args.status.upper() if args.status else "UNREVIEWED"
    total_count, items = repo.get_curation_queue(
        status=status_filter,
        limit=args.limit,
        offset=args.offset,
        domain=args.domain,
    )

    print("=" * 110)
    print(f"VERITAS EVIDENCE CURATION QUEUE (Filter: {status_filter})")
    print(f"Showing records {args.offset + 1} - {min(args.offset + len(items), total_count)} of {total_count} total")
    print("=" * 110)

    if not items:
        print(f"No records found matching status '{status_filter}'" + (f" and domain '{args.domain}'" if args.domain else "") + ".")
        print("=" * 110)
        return 0

    header = f"{'#':<3} {'ID':<26} {'VERIFIED':<10} {'STATUS':<20} {'STANCE':<15} {'PUBLISHER':<25}"
    print(header)
    print("-" * 110)

    for idx, item in enumerate(items, start=args.offset + 1):
        v_tag = "[YES]" if item.is_verified else "[NO]"
        pub = (item.canonical_publisher or item.publisher or "Unknown")[:24]
        title_snip = (item.title or "")[:75]
        print(f"{idx:<3} {item.id:<26} {v_tag:<10} {item.curation_status:<20} {item.stance:<15} {pub:<25}")
        print(f"    Title: {title_snip}")

    print("=" * 110)
    print("Commands:")
    print("  Inspect record:  python -m backend.curation.curate inspect <evidence_id>")
    print("  Review record:   python -m backend.curation.curate review --id <id> --status <status> --reviewer <name>")
    return 0


def cmd_inspect(args) -> int:
    """Inspect complete details and metadata of an individual evidence record across all 4 curation dimensions."""
    repo = get_repository(args.db)
    item = repo.get_item_by_id(args.id)
    if not item:
        print(f"Error: Evidence record with ID '{args.id}' not found.", file=sys.stderr)
        return 1

    derived_domain = normalize_domain(item.canonical_url or item.url or item.original_url)
    stored_domain = item.source_domain or "N/A"
    domain_match_str = "MATCH" if (derived_domain and stored_domain and derived_domain == stored_domain.lower()) else f"MISMATCH (Derived: {derived_domain}, Stored: {stored_domain})"

    history = repo.get_curation_audit_history(item.id)
    text_tier_str = get_text_availability_label(item.text_availability, item.is_full_text)
    text_prov_str = get_text_provenance_label(item.text_provenance)
    ret_meth_str = get_retrieval_method_label(item.retrieval_method)

    print("=" * 84)
    print(f"EVIDENCE RECORD INSPECTION: {item.id}")
    print("=" * 84)
    print(f"Title:                    {item.title}")
    print(f"Publisher:                {item.publisher or 'N/A'}")
    print(f"Canonical Publisher:      {item.canonical_publisher or 'N/A'}")
    print(f"Published Date:           {item.published_date or 'N/A'}")
    print(f"Language:                 {item.original_language or 'und'}")
    print(f"DOI:                      {item.doi or 'N/A'}")
    print(f"Canonical URL:            {item.canonical_url or item.url or 'N/A'}")
    print(f"Original URL:             {item.original_url or 'N/A'}")
    print("-" * 84)
    print("DIMENSION 1: SOURCE AUTHENTICITY & DOMAIN PROVENANCE")
    print(f"  Source Tier:            {item.source_tier}")
    print(f"  Source Type:            {item.source_type}")
    print(f"  Stored Source Domain:   {stored_domain}")
    print(f"  Derived URL Domain:     {derived_domain or 'None'}")
    print(f"  Domain Integrity:       {domain_match_str}")
    print("-" * 84)
    print("DIMENSION 2: TEXT PROVENANCE & CONTENT VERIFIABILITY")
    print(f"  Text Availability:      {text_tier_str}")
    print(f"  Text Provenance:        {text_prov_str}")
    print(f"  Retrieval Origin:       {ret_meth_str}")
    print(f"  Full Text Available:    {'Yes' if item.is_full_text else 'No'}")
    print(f"  Machine Translated:     {'Yes' if item.is_machine_translated else 'No'}")
    if item.translation_engine:
        print(f"  Translation Engine:     {item.translation_engine}")
    print("-" * 84)
    print("DIMENSION 3: CLAIM-SPECIFIC TOPICAL RELEVANCE")
    print(f"  Relevance Status:       {item.relevance_status}")
    print(f"  Relevance Score:        {item.relevance_score if item.relevance_score is not None else 'N/A'}")
    if item.relevance_justification:
        print(f"  Relevance Notes:        {item.relevance_justification}")
    print("-" * 84)
    print("DIMENSION 4: EVIDENTIARY STANCE & SOURCE INDEPENDENCE")
    print(f"  Initial Stance:         {item.stance}")
    print(f"  Confirmed Stance:       {item.reviewer_confirmed_stance or 'None'}")
    print(f"  Independence Status:    {item.independence_status}")
    if item.underlying_source_id:
        print(f"  Underlying Source ID:   {item.underlying_source_id}")
    print(f"  Potential Syndication:  {'Yes' if item.is_potential_syndication else 'No'}")
    if item.syndication_notes:
        print(f"  Syndication Notes:      {item.syndication_notes}")
    print("-" * 84)
    print("DIMENSION 5: CURATION STATUS & AUDIT TRAIL")
    print(f"  Curation Status:        {item.curation_status}")
    print(f"  Is Verified:            {item.is_verified}")
    print(f"  Peer Review Confirmed:  {'Yes (Academic Journal)' if item.peer_review_confirmed else 'No'}")
    print(f"  Reviewer ID:            {item.reviewer_id or 'None'}")
    print(f"  Review Timestamp:       {item.review_timestamp or 'None'}")
    if item.reviewer_notes:
        print(f"  Reviewer Notes:         {item.reviewer_notes}")
    print(f"  Total Audit Log Entries:{len(history)}")
    print("-" * 84)
    print("CONTENT SNIPPET & PROVENANCE:")
    if item.text_provenance == "VERBATIM":
        print("  [VERBATIM DIRECT QUOTATION]:")
        print(f"  \"{item.snippet}\"")
    elif item.text_provenance == "SUMMARY":
        print("  [FAITHFUL SUMMARY - NOT A DIRECT QUOTATION]:")
        print(f"  {item.snippet}")
    elif item.text_provenance == "INTERPRETATION":
        print("  [LEGAL / EDITORIAL INTERPRETATION - NOT A DIRECT QUOTATION]:")
        print(f"  {item.snippet}")
    else:
        print("  [TEXT UNAVAILABLE / METADATA ONLY]:")
        print(f"  {item.snippet}")
    print(f"Content SHA-256:          {item.content_sha256 or 'N/A'}")
    print("-" * 84)
    display_content_accessibility_warnings(item)
    print("=" * 84)
    return 0


def cmd_review(args) -> int:
    """Submit and apply a human review decision for an evidence record with strict safety checks."""
    repo = get_repository(args.db)

    # 1. Validate status
    target_status = args.status.upper()
    if target_status not in VALID_STATUSES:
        print(f"Error: Invalid status '{args.status}'. Must be one of: {', '.join(VALID_STATUSES)}", file=sys.stderr)
        return 1

    # 2. Check reviewer identity
    reviewer = (args.reviewer or "").strip()
    if not reviewer:
        print("Error: Reviewer identifier (--reviewer) cannot be empty or whitespace.", file=sys.stderr)
        return 1

    # 3. Retrieve existing record to inspect before deciding
    existing = repo.get_item_by_id(args.id)
    if not existing:
        print(f"Error: Evidence record with ID '{args.id}' not found.", file=sys.stderr)
        return 1

    # 4. Enforce rejection justification requirement
    if target_status in ("REJECTED_IRRELEVANT", "REJECTED_UNRELIABLE"):
        if not args.notes or not args.notes.strip():
            print(
                f"Error: Rejecting evidence as '{target_status}' requires an explanation in --notes describing why it was rejected.",
                file=sys.stderr,
            )
            return 1

    # 5. Enforce APPROVED_VERIFIED stance and source-verification requirements
    target_stance = None
    if target_status == "APPROVED_VERIFIED":
        if not args.source_verified:
            print(
                "Error: APPROVED_VERIFIED requires explicit reviewer confirmation that the external primary source document\n"
                "was inspected and that the snippet text genuinely appears there.\n"
                "An offline fallback or unverified record cannot become approved merely because a reviewer adds notes.\n"
                "Please add --source-verified to confirm after performing external source verification.",
                file=sys.stderr,
            )
            return 1

        if existing.text_availability == "METADATA_ONLY":
            print(
                "Error: Cannot approve evidence with text_availability='METADATA_ONLY' as APPROVED_VERIFIED.\n"
                "Metadata-only citations lack empirical source text and cannot serve as primary fact-checking proof.",
                file=sys.stderr,
            )
            return 1

        # Check source domain consistency (must match actual canonical URL domain)
        derived_domain = normalize_domain(existing.canonical_url or existing.url or existing.original_url)
        stored_domain = (existing.source_domain or "").lower().strip()
        stored_norm = normalize_domain(stored_domain)
        if derived_domain and stored_domain and derived_domain != stored_domain and derived_domain != stored_norm:
            print(
                "Error: Cannot approve record with domain mismatch as APPROVED_VERIFIED.\n"
                f"Stored source domain is '{existing.source_domain}', but actual canonical URL domain is '{derived_domain}'.\n"
                "Reviewer must investigate and resolve the provenance metadata inconsistency before approving.\n"
                "Publisher name cannot be treated as proof of domain ownership.",
                file=sys.stderr,
            )
            return 1

        if not existing.canonical_url and not existing.original_url and not existing.url:
            print(
                "Error: Cannot approve evidence without an accessible external primary source URL or DOI.",
                file=sys.stderr,
            )
            return 1

        if not args.stance:
            print(
                "Error: APPROVED_VERIFIED status requires an explicit decisive stance (--stance SUPPORTING or --stance CONTRADICTING).\n"
                "Reviewers must actively verify whether the evidence supports or contradicts the claim before approving.",
                file=sys.stderr,
            )
            return 1
        target_stance = args.stance.upper()
        if target_stance not in DECISIVE_STANCES:
            print(
                f"Error: APPROVED_VERIFIED requires a decisive stance ('SUPPORTING' or 'CONTRADICTING'), got '{args.stance}'.\n"
                "Neutral evidence cannot be approved as verified fact-checking evidence.",
                file=sys.stderr,
            )
            return 1

        # Check text provenance: prevent summaries/interpretations from being approved without explicit notes acknowledging their nature
        target_prov = args.text_provenance.upper() if args.text_provenance else existing.text_provenance
        if target_prov == "UNAVAILABLE" or existing.text_availability == "METADATA_ONLY":
            print(
                "Error: Cannot approve evidence with text_provenance='UNAVAILABLE' or text_availability='METADATA_ONLY' as APPROVED_VERIFIED.\n"
                "Metadata-only citations lack empirical source text and cannot serve as primary fact-checking proof.",
                file=sys.stderr,
            )
            return 1

        if target_prov in ("SUMMARY", "INTERPRETATION"):
            print(f"Notice: Evidence has text_provenance='{target_prov}'. It is NOT an exact verbatim quotation.")
            if not args.notes or len(args.notes.strip()) < 10:
                print(
                    f"Error: Approving evidence with text_provenance='{target_prov}' requires explicit documentation in --notes\n"
                    "acknowledging that the text is a summary or interpretation rather than an unverified verbatim quote.",
                    file=sys.stderr,
                )
                return 1

    elif args.stance:
        target_stance = args.stance.upper()
        if target_stance not in VALID_STANCES:
            print(f"Error: Invalid stance '{args.stance}'. Must be one of: {', '.join(VALID_STANCES)}", file=sys.stderr)
            return 1

    # Prevent reclassifying summary/interpretation to VERBATIM without source verification and notes
    if args.text_provenance and args.text_provenance.upper() == "VERBATIM":
        if existing.text_provenance in ("SUMMARY", "INTERPRETATION"):
            if not args.source_verified or not args.notes:
                print(
                    "Error: Cannot reclassify synthetic summary/interpretation to VERBATIM without --source-verified and --notes confirming verbatim match.",
                    file=sys.stderr,
                )
                return 1

    # Enforce strict peer-review protection
    if args.peer_reviewed:
        if existing.source_type == "GOVERNMENT_PUBLICATION":
            print(
                "Error: Government technical publications and datasets cannot be marked as academically peer-reviewed.\n"
                "Official government publications undergo institutional agency review, not independent academic journal peer review.\n"
                "Leave peer-reviewed status false (--peer-reviewed omitted) to preserve this distinction.",
                file=sys.stderr,
            )
            return 1

        has_doi = bool(existing.doi and existing.doi.strip())
        has_journal_notes = bool(args.notes and any(w in args.notes.lower() for w in ("journal", "doi", "peer-review", "peer review", "proceedings", "conference")))
        if not has_doi and not has_journal_notes:
            print(
                "Error: Cannot establish academic peer-review status without a documented basis.\n"
                "The record lacks a DOI, and --notes does not document the academic journal or peer-review venue.\n"
                "Document the academic journal citation in --notes or omit --peer-reviewed.",
                file=sys.stderr,
            )
            return 1

    # 6. Display evidence summary and warnings before confirmation
    print("-" * 75)
    print(f"PROPOSED CURATION DECISION FOR: {existing.id}")
    print(f"Title:                 {existing.title}")
    print(f"Publisher:             {existing.canonical_publisher or existing.publisher}")
    print(f"Current Status:        {existing.curation_status} (is_verified={existing.is_verified})")
    print(f"Proposed Status:       {target_status}")
    print(f"Current Stance:        {existing.stance}")
    print(f"Proposed Stance:       {target_stance or existing.stance}")
    print(f"Text Provenance:       {args.text_provenance.upper() if args.text_provenance else existing.text_provenance}")
    print(f"Retrieval Origin:      {existing.retrieval_method}")
    print(f"Reviewer ID:           {reviewer}")
    print(f"Peer-Reviewed:         {'Yes' if args.peer_reviewed else 'No'}")
    if args.notes:
        print(f"Reviewer Notes:        {args.notes.strip()}")
    print("-" * 75)
    display_content_accessibility_warnings(existing)

    # 7. Require explicit confirmation
    if not args.yes:
        confirm = input("Confirm applying this curation decision to the database? (yes/no): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Curation decision cancelled. Database was not modified.")
            return 0

    # 8. Construct Pydantic model and execute atomic update
    try:
        decision = CurationReviewDecision(
            evidence_id=args.id,
            claim_id=args.claim_id,
            curation_status=target_status,
            reviewer_id=reviewer,
            reviewer_notes=args.notes.strip() if args.notes else None,
            reviewer_confirmed_stance=target_stance,
            peer_review_confirmed=args.peer_reviewed,
            text_provenance=args.text_provenance.upper() if args.text_provenance else None,
        )
        updated = repo.apply_curation_decision(decision)
    except Exception as exc:
        print(f"Error applying curation decision: {exc}", file=sys.stderr)
        return 1

    print("=" * 75)
    print(f"CURATION DECISION APPLIED SUCCESSFULLY: {updated.id}")
    print("=" * 75)
    print(f"Previous Status:     {existing.curation_status} -> New Status: {updated.curation_status}")
    print(f"Previous Stance:     {existing.stance} -> New Stance: {updated.stance}")
    print(f"Verified Status:     {updated.is_verified} ({'CONFIRMED VERIFIED' if updated.is_verified else 'NOT VERIFIED'})")
    print(f"Reviewer:            {updated.reviewer_id}")
    print(f"Peer Review:         {'Confirmed' if updated.peer_review_confirmed else 'Not confirmed'}")
    print(f"Review Timestamp:    {updated.review_timestamp}")
    if updated.reviewer_notes:
        print(f"Reviewer Notes:      {updated.reviewer_notes}")
    print("=" * 75)
    print("Audit log entry saved atomically. No automated approval occurred.")
    return 0


def cmd_history(args) -> int:
    """Display the full chronological audit history for an evidence record."""
    repo = get_repository(args.db)
    existing = repo.get_item_by_id(args.id)
    if not existing:
        print(f"Error: Evidence record with ID '{args.id}' not found.", file=sys.stderr)
        return 1

    history = repo.get_curation_audit_history(args.id)

    print("=" * 95)
    print(f"CURATION AUDIT HISTORY: {args.id}")
    print(f"Title: {existing.title}")
    print("=" * 95)

    if not history:
        print("No curation decisions have been recorded for this record yet (Status: UNREVIEWED).")
        print("=" * 95)
        return 0

    print(f"{'#':<3} {'TIMESTAMP':<25} {'REVIEWER':<15} {'STATUS TRANSITION':<32} {'STANCE'}")
    print("-" * 95)

    for entry in history:
        trans_status = f"{entry.previous_status} -> {entry.new_status}"
        trans_stance = f"{entry.previous_stance or 'N/A'} -> {entry.new_stance or 'N/A'}"
        print(f"{entry.audit_id:<3} {entry.decision_timestamp[:19]:<25} {entry.reviewer_id:<15} {trans_status:<32} {trans_stance}")
        if entry.reviewer_notes:
            print(f"    Notes: {entry.reviewer_notes}")

    print("=" * 95)
    return 0


def cmd_export(args) -> int:
    """Non-destructively export curated evidence records and audit history to a new timestamped JSON file."""
    repo = get_repository(args.db)
    status_filter = args.status.upper() if args.status else "APPROVED_VERIFIED"

    # Generate timestamped filename by default to prevent overwriting
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")

    if args.output:
        output_path = Path(args.output)
        if output_path.exists() and not args.overwrite:
            print(
                f"Error: Target export file '{output_path}' already exists.\n"
                "To prevent accidental data loss, existing export files are never overwritten automatically.\n"
                "Specify a different output path or use --overwrite if intentional.",
                file=sys.stderr,
            )
            return 1
    else:
        output_filename = f"curated_evidence_export_{timestamp_str}.json"
        output_path = Path("backend/data") / output_filename

    total_count, items = repo.get_curation_queue(
        status=status_filter,
        limit=10000,
        offset=0,
    )

    export_records = []
    publisher_counts = {}

    for item in items:
        history = repo.get_curation_audit_history(item.id)
        pub = item.canonical_publisher or item.publisher or "Unknown"
        publisher_counts[pub] = publisher_counts.get(pub, 0) + 1

        export_records.append({
            "evidence": item.model_dump(),
            "audit_history": [h.model_dump() for h in history],
        })

    payload = {
        "export_metadata": {
            "version": "1.0.0",
            "exported_at": now_utc.isoformat(),
            "source_database": str(repo.db_path),
            "filter_status": status_filter,
            "total_records": len(export_records),
        },
        "publisher_distribution": publisher_counts,
        "records": export_records,
    }

    # Ensure target directory exists safely
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    file_size = output_path.stat().st_size

    print("=" * 75)
    print("VERITAS CURATED EVIDENCE NON-DESTRUCTIVE EXPORT")
    print("=" * 75)
    print(f"Filter Status:       {status_filter}")
    print(f"Records Exported:    {len(export_records)}")
    print(f"Export File Path:    {output_path.resolve()}")
    print(f"File Size:           {file_size:,} bytes")
    print("-" * 75)
    if publisher_counts:
        print("Publisher Distribution:")
        for pub, count in sorted(publisher_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {pub}: {count} records")
    else:
        print("No records matched the filter status. Empty archive generated safely.")
    print("=" * 75)
    print("Notice: Export is strictly non-destructive. Active database was not modified.")
    print("Notice: No Git operations were performed. Manual review of export file is required.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.curation.curate",
        description="VERITAS Evidence Review and Curation CLI (Local-Only Administrative Tooling).",
    )
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite evidence database (defaults to config setting).")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: stats
    p_stats = subparsers.add_parser("stats", help="Display curation queue status breakdown.")
    p_stats.set_defaults(func=cmd_stats)

    # Subcommand: list
    p_list = subparsers.add_parser("list", help="List evidence records with pagination and filters.")
    p_list.add_argument("--status", type=str, default="UNREVIEWED", help="Filter by status (default: UNREVIEWED, or ALL).")
    p_list.add_argument("--domain", type=str, default=None, help="Filter by publisher domain.")
    p_list.add_argument("--limit", type=int, default=20, help="Page size (default: 20).")
    p_list.add_argument("--offset", type=int, default=0, help="Page offset (default: 0).")
    p_list.set_defaults(func=cmd_list)

    # Subcommand: inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect complete details and metadata of an evidence record.")
    p_inspect.add_argument("id", type=str, help="Evidence record ID to inspect.")
    p_inspect.set_defaults(func=cmd_inspect)

    # Subcommand: review
    p_review = subparsers.add_parser("review", help="Submit human curation decision for an evidence record.")
    p_review.add_argument("--id", type=str, required=True, help="Evidence record ID to review.")
    p_review.add_argument("--status", type=str, required=True, choices=VALID_STATUSES, help="Target curation status.")
    p_review.add_argument("--reviewer", type=str, required=True, help="Reviewer username or identifier.")
    p_review.add_argument("--stance", type=str, choices=VALID_STANCES, default=None, help="Confirmed stance (required for APPROVED_VERIFIED).")
    p_review.add_argument("--notes", type=str, default=None, help="Reviewer rationale and scientific justification.")
    p_review.add_argument("--peer-reviewed", action="store_true", help="Confirm peer-reviewed publication status.")
    p_review.add_argument("--source-verified", action="store_true", help="Confirm that reviewer accessed and verified the original source document.")
    p_review.add_argument(
        "--text-provenance",
        type=str,
        default=None,
        choices=["VERBATIM", "SUMMARY", "INTERPRETATION", "UNAVAILABLE"],
        help="Update text provenance classification upon review (VERBATIM, SUMMARY, INTERPRETATION, UNAVAILABLE).",
    )
    p_review.add_argument("--claim-id", type=str, default=None, help="Optional claim statement ID.")
    p_review.add_argument("-y", "--yes", action="store_true", help="Confirm decision automatically without interactive prompt.")
    p_review.set_defaults(func=cmd_review)

    # Subcommand: history
    p_history = subparsers.add_parser("history", help="Show chronological audit trail for an evidence record.")
    p_history.add_argument("id", type=str, help="Evidence record ID.")
    p_history.set_defaults(func=cmd_history)

    # Subcommand: export
    p_export = subparsers.add_parser("export", help="Safely export curated records and audit history to JSON.")
    p_export.add_argument("--status", type=str, default="APPROVED_VERIFIED", help="Status filter (default: APPROVED_VERIFIED, or ALL).")
    p_export.add_argument("--output", type=str, default=None, help="Output JSON path (defaults to timestamped file in backend/data/).")
    p_export.add_argument("--overwrite", action="store_true", help="Overwrite existing output file if explicitly provided.")
    p_export.set_defaults(func=cmd_export)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
