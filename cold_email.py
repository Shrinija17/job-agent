#!/usr/bin/env python3
"""
H1B Cold Email Agent — Automated outreach to H1B-sponsoring companies.

Usage:
    python cold_email.py --filter                # Filter CSV, show relevant contacts
    python cold_email.py --draft                 # Filter + draft emails with Gemini
    python cold_email.py --draft --enrich        # Also check for current openings first
    python cold_email.py --send --batch 20       # Send 20 drafted emails
    python cold_email.py --preview 5             # Preview first 5 drafted emails
    python cold_email.py --followup              # Draft follow-ups for sent emails (5+ days ago)
    python cold_email.py --status                # Pipeline status
"""

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

from cold_email.loader import load_and_filter, deduplicate, Contact
from cold_email.enricher import enrich_contacts
from cold_email.drafter import EmailDrafter
from cold_email.sender import EmailSender


STATE_FILE = Path(__file__).parent / "data" / "cold_email_state.json"
DEFAULT_CSV = str(Path.home() / "Desktop" / "dol-hr-contacts.csv")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"contacts": [], "stats": {}, "last_updated": ""}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def cmd_filter(csv_path: str):
    """Step 1: Filter CSV and show stats."""
    print("\n  Loading and filtering CSV...\n")
    contacts, stats = load_and_filter(csv_path)

    print(f"  Total contacts in CSV:   {stats['total']}")
    print(f"  Tier 1 (exact match):    {stats['tier_1']}")
    print(f"  Tier 2 (adjacent):       {stats['tier_2']}")
    print(f"  Skipped (irrelevant):    {stats['skipped']}")

    deduped = deduplicate(contacts)
    print(f"\n  After dedup (1 per company): {len(deduped)} companies")

    # Show tier breakdown
    t1 = [c for c in deduped if c.tier == 1]
    t2 = [c for c in deduped if c.tier == 2]
    print(f"    Tier 1 companies: {len(t1)}")
    print(f"    Tier 2 companies: {len(t2)}")

    # Show sample
    print(f"\n  --- Top 10 Tier 1 matches ---\n")
    for c in t1[:10]:
        print(f"    {c.company}")
        print(f"      Role: {c.role_filed} | Contact: {c.hr_name} ({c.hr_title})")
        print(f"      Email: {c.hr_email} | Location: {c.city}, {c.state}")
        print()

    # Save state
    state = load_state()
    state["contacts"] = [c.to_dict() for c in deduped]
    state["stats"] = stats
    state["stats"]["deduped"] = len(deduped)
    save_state(state)

    print(f"  State saved to {STATE_FILE}")
    print(f"  Next step: python cold_email.py --draft\n")


def cmd_draft(enrich: bool = False):
    """Step 2: Draft personalized emails with Gemini."""
    state = load_state()
    if not state["contacts"]:
        print("\n  No contacts in state. Run --filter first.\n")
        return

    contacts = [Contact.from_dict(c) for c in state["contacts"]]

    # Only draft for contacts that haven't been drafted/sent yet
    to_draft = [c for c in contacts if c.status in ("Not Contacted", "")]
    print(f"\n  {len(to_draft)} contacts to draft (skipping already drafted/sent)\n")

    if not to_draft:
        print("  All contacts already have drafts. Use --send to send them.\n")
        return

    # Optional enrichment
    if enrich:
        print("  Enriching: checking company career pages for current openings...\n")
        to_draft, enriched_count = enrich_contacts(to_draft)
        print(f"\n  {enriched_count} companies have current relevant openings\n")

    # Draft emails
    print("  Drafting emails with Gemini...\n")
    drafter = EmailDrafter()

    drafted = 0
    for i, contact in enumerate(to_draft):
        try:
            subject, body = drafter.draft(contact)
            contact.draft_subject = subject
            contact.draft_body = body
            contact.status = "Drafted"
            drafted += 1

            company_short = contact.company[:30]
            print(f"  [{i + 1}/{len(to_draft)}] {company_short} -> {subject}")
        except Exception as e:
            print(f"  [{i + 1}/{len(to_draft)}] {contact.company[:30]} FAILED: {e}")

    # Merge back and save
    contact_map = {c.hr_email: c for c in to_draft}
    for j, c in enumerate(contacts):
        if c.hr_email in contact_map:
            contacts[j] = contact_map[c.hr_email]

    state["contacts"] = [c.to_dict() for c in contacts]
    save_state(state)

    print(f"\n  {drafted} emails drafted. State saved.")
    print(f"  Next: python cold_email.py --preview 5")
    print(f"  Then: python cold_email.py --send --batch 20\n")


def cmd_preview(count: int = 5):
    """Preview drafted emails before sending."""
    state = load_state()
    contacts = [Contact.from_dict(c) for c in state["contacts"]]
    drafted = [c for c in contacts if c.status == "Drafted"]

    if not drafted:
        print("\n  No drafted emails. Run --draft first.\n")
        return

    show = drafted[:count]
    print(f"\n  Showing {len(show)} of {len(drafted)} drafted emails:\n")

    for i, c in enumerate(show):
        print(f"  {'='*60}")
        print(f"  Email #{i + 1}")
        print(f"  To: {c.hr_name} <{c.hr_email}>")
        print(f"  Company: {c.company} | Role filed: {c.role_filed}")
        if c.current_openings:
            print(f"  Current openings found: {', '.join(c.current_openings)}")
        print(f"  {'='*60}")
        print(f"  Subject: {c.draft_subject}")
        print(f"  {'-'*60}")
        print(f"  {c.draft_body}")
        print()


def cmd_send(batch_size: int = 20, resume_path: str = None):
    """Step 3: Send drafted emails."""
    state = load_state()
    contacts = [Contact.from_dict(c) for c in state["contacts"]]
    drafted = [c for c in contacts if c.status == "Drafted"]

    if not drafted:
        print("\n  No drafted emails ready to send. Run --draft first.\n")
        return

    print(f"\n  {len(drafted)} emails ready. Sending batch of {min(batch_size, len(drafted))}...\n")

    # Build email dicts for sender
    emails = []
    for c in drafted[:batch_size]:
        emails.append({
            "to": c.hr_email,
            "name": c.hr_name,
            "subject": c.draft_subject,
            "body": c.draft_body,
            "contact_id": c.hr_email,
        })

    sender = EmailSender(batch_size=batch_size)
    results = sender.send_batch(emails, resume_path=resume_path)

    # Update statuses
    result_map = {r["contact_id"]: r for r in results}
    sent_count = 0
    for j, c in enumerate(contacts):
        if c.hr_email in result_map:
            r = result_map[c.hr_email]
            if r["status"] == "sent":
                contacts[j].status = "Sent"
                contacts[j].notes = f"Sent {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                sent_count += 1
            elif r["status"] == "failed":
                contacts[j].status = "Failed"
                contacts[j].notes = f"Error: {r.get('error', 'unknown')}"

    state["contacts"] = [c.to_dict() for c in contacts]
    save_state(state)

    print(f"\n  {sent_count} emails sent. State saved.")
    remaining = len([c for c in contacts if c.status == "Drafted"])
    if remaining:
        print(f"  {remaining} drafts remaining. Run --send again for next batch.\n")


def cmd_followup():
    """Draft follow-up emails for contacts sent 5+ days ago with no reply."""
    state = load_state()
    contacts = [Contact.from_dict(c) for c in state["contacts"]]

    # Find contacts sent 5+ days ago
    cutoff = datetime.now() - timedelta(days=5)
    needs_followup = []
    for c in contacts:
        if c.status == "Sent" and c.notes.startswith("Sent "):
            try:
                sent_str = c.notes.replace("Sent ", "")
                sent_date = datetime.strptime(sent_str, "%Y-%m-%d %H:%M")
                if sent_date < cutoff:
                    needs_followup.append(c)
            except ValueError:
                continue

    if not needs_followup:
        print("\n  No contacts ready for follow-up (need 5+ days since initial send).\n")
        return

    print(f"\n  {len(needs_followup)} contacts ready for follow-up.\n")
    print("  Drafting follow-ups with Gemini...\n")

    drafter = EmailDrafter()
    for i, c in enumerate(needs_followup):
        try:
            subject, body = drafter.draft_followup(c, c.draft_subject)
            c.draft_subject = subject
            c.draft_body = body
            c.status = "Followup Drafted"
            print(f"  [{i + 1}/{len(needs_followup)}] {c.company[:30]} -> follow-up drafted")
        except Exception as e:
            print(f"  [{i + 1}/{len(needs_followup)}] {c.company[:30]} FAILED: {e}")

    # Save back
    email_map = {c.hr_email: c for c in needs_followup}
    for j, c in enumerate(contacts):
        if c.hr_email in email_map:
            contacts[j] = email_map[c.hr_email]

    state["contacts"] = [c.to_dict() for c in contacts]
    save_state(state)

    print(f"\n  Follow-ups drafted. Preview with --preview, send with --send.\n")


def cmd_status():
    """Show pipeline status."""
    state = load_state()
    if not state["contacts"]:
        print("\n  No data yet. Run --filter first.\n")
        return

    contacts = [Contact.from_dict(c) for c in state["contacts"]]
    stats = state.get("stats", {})

    print(f"\n  Pipeline Status (last updated: {state.get('last_updated', 'never')[:16]})")
    print(f"  {'='*50}")
    print(f"  Source CSV:         {stats.get('total', '?')} total contacts")
    print(f"  After filtering:   {stats.get('tier_1', 0) + stats.get('tier_2', 0)} relevant")
    print(f"  After dedup:       {stats.get('deduped', len(contacts))} companies")
    print()

    # Status breakdown
    status_counts = {}
    for c in contacts:
        s = c.status or "Not Contacted"
        status_counts[s] = status_counts.get(s, 0) + 1

    for status, count in sorted(status_counts.items()):
        bar = "#" * min(count, 40)
        print(f"    {status:<20} {count:>4}  {bar}")

    # Enrichment stats
    with_openings = len([c for c in contacts if c.current_openings])
    if with_openings:
        print(f"\n  Companies with confirmed current openings: {with_openings}")

    print()


def main():
    os.chdir(Path(__file__).parent)
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="H1B Cold Email Agent — Automated outreach to H1B sponsors"
    )
    parser.add_argument("--filter", action="store_true", help="Filter CSV and show stats")
    parser.add_argument("--draft", action="store_true", help="Draft emails with Gemini")
    parser.add_argument("--enrich", action="store_true", help="Check career pages for openings (use with --draft)")
    parser.add_argument("--send", action="store_true", help="Send drafted emails")
    parser.add_argument("--batch", type=int, default=20, help="Emails per send batch (default: 20)")
    parser.add_argument("--preview", type=int, nargs="?", const=5, help="Preview N drafted emails")
    parser.add_argument("--followup", action="store_true", help="Draft follow-ups for old sends")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    parser.add_argument("--csv", type=str, default=DEFAULT_CSV, help="Path to contacts CSV")
    parser.add_argument("--resume", type=str, help="Path to resume PDF to attach")

    args = parser.parse_args()

    print("=" * 60)
    print(f"  H1B Cold Email Agent — {datetime.now().strftime('%B %d, %Y %I:%M %p')}")
    print("=" * 60)

    if args.filter:
        cmd_filter(args.csv)
    elif args.draft:
        cmd_draft(enrich=args.enrich)
    elif args.send:
        cmd_send(batch_size=args.batch, resume_path=args.resume)
    elif args.preview is not None:
        cmd_preview(count=args.preview)
    elif args.followup:
        cmd_followup()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
