#!/usr/bin/env python3
"""
One-time backfill: scan every inbox email and apply newsletter/category labels.

Applies labels for: newsletter, financial_newsletter, github_notification,
concert_ticket, job_offer. Everything else (spam, important, coupons) is
left completely untouched.

Usage:
    python3 backfill_labels.py --dry-run        # preview (no changes)
    python3 backfill_labels.py                  # apply labels
    python3 backfill_labels.py --account camila   # single account
"""

import argparse
import logging
import sys
from collections import defaultdict

from config import load_config
from modules import gmail_client as gmail_module
from modules import classifier
from modules.classifier import LABEL_COLORS, DEFAULT_LABEL_COLOR

LABEL_CATEGORIES = {
    "newsletter",
    "financial_newsletter",
    "github_notification",
    "concert_ticket",
    "job_offer",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _label_name_for(result: dict) -> str:
    name = result.get("label_name")
    if name:
        return name
    cat = result["category"]
    if cat == "job_offer":
        return "Job Offers"
    if cat == "concert_ticket":
        return "Concert Tickets"
    return cat


def fetch_all_inbox(gmail: gmail_module.GmailClient) -> list[dict]:
    service = gmail._service
    name = gmail.account.name

    logger.info(f"[{name}] Listing all inbox messages...")
    msg_refs = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": "in:inbox", "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        msg_refs.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        logger.info(f"[{name}]   ... {len(msg_refs)} message IDs collected")
        if not page_token:
            break

    total = len(msg_refs)
    logger.info(f"[{name}] Fetching details for {total} messages (this may take a while)...")

    emails = []
    for i, ref in enumerate(msg_refs):
        if i % 100 == 0 and i > 0:
            logger.info(f"[{name}]   {i}/{total} fetched...")
        try:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            emails.append(gmail._parse_message(msg))
        except Exception as e:
            logger.warning(f"[{name}] Could not fetch {ref['id']}: {e}")

    logger.info(f"[{name}] Done fetching. {len(emails)} emails ready for classification.")
    return emails


def backfill(account_filter: str | None, dry_run: bool):
    config = load_config()
    accounts = [a for a in config.accounts if a.enabled]
    if account_filter:
        accounts = [a for a in accounts if a.name == account_filter]
        if not accounts:
            logger.error(f"No enabled account named '{account_filter}'")
            sys.exit(1)

    for account in accounts:
        logger.info(f"=== Backfilling labels for {account.email} ===")
        gmail = gmail_module.GmailClient(account)
        emails = fetch_all_inbox(gmail)

        # Pre-fetch existing Gmail label IDs so we can skip already-labeled emails.
        existing_label_ids: set[str] = set()
        label_id_map: dict[str, str] = {}  # label_name -> label_id

        stats: dict[str, int] = defaultdict(int)
        stats["total"] = len(emails)

        for email in emails:
            result = classifier.classify_email(email)
            category = result["category"]

            if category not in LABEL_CATEGORIES:
                stats["skipped"] += 1
                continue

            label_name = _label_name_for(result)
            current_ids = set(email.get("label_ids", []))

            if dry_run:
                stats[category] += 1
                subject = email["subject"][:65]
                sender = email["sender"][:45]
                print(f"  [{label_name}] {subject!r}")
                print(f"              from: {sender}")
            else:
                # Resolve label ID (cached after first lookup per label name)
                if label_name not in label_id_map:
                    color = LABEL_COLORS.get(label_name, DEFAULT_LABEL_COLOR)
                    label_id_map[label_name] = gmail.ensure_label(label_name, color)

                label_id = label_id_map[label_name]

                if label_id in current_ids:
                    stats["already_had_label"] += 1
                    continue

                gmail.apply_label(email["id"], label_id)
                stats[category] += 1
                logger.debug(f"  Labeled '{label_name}': {email['subject'][:60]}")

        sep = "=" * 72
        mode = "DRY-RUN — no changes made" if dry_run else "COMPLETE"
        print(f"\n{sep}")
        print(f"  BACKFILL {mode}  |  {account.email}")
        print(sep)
        print(f"  Total inbox emails scanned       : {stats['total']}")
        print(f"  Skipped (not label-eligible)     : {stats['skipped']}")
        print(f"  Newsletters labeled              : {stats['newsletter']}")
        print(f"  Financial newsletters labeled    : {stats['financial_newsletter']}")
        print(f"  GitHub notifications labeled     : {stats['github_notification']}")
        print(f"  Concert tickets labeled          : {stats['concert_ticket']}")
        print(f"  Job offers labeled               : {stats['job_offer']}")
        if not dry_run:
            print(f"  Already had label (skipped)      : {stats['already_had_label']}")
        print(sep)
        if dry_run:
            print("  Re-run without --dry-run to apply labels.")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill Gmail labels for all existing inbox emails."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be labeled without making any changes.",
    )
    parser.add_argument(
        "--account",
        metavar="NAME",
        help="Only process this account name (default: all enabled accounts).",
    )
    args = parser.parse_args()
    backfill(account_filter=args.account, dry_run=args.dry_run)
