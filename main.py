import argparse
import json
import logging
import logging.handlers
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import load_config, AccountConfig
from modules import gmail_client as gmail_module
from modules import classifier
from modules import notion_client
from modules import telegram_notifier
from modules import whatsapp_notifier
from modules.classifier import LABEL_COLORS, DEFAULT_LABEL_COLOR

STATE_FILE = Path("state/last_run.json")
LOG_FILE = Path("logs/cleaner.log")

CATEGORY_LABEL = {
    "spam_promo": "TRASH",
    "coupon": "NOTION + TRASH",
    "important": "KEEP",
    "newsletter": "LABEL + KEEP",
    "financial_newsletter": "LABEL + KEEP + DIGEST",
    "github_notification": "LABEL + KEEP + DIGEST",
    "job_offer": "LABEL + KEEP",
    "concert_ticket": "LABEL + KEEP",
    "travel": "LABEL + KEEP",
}


def setup_logging(dry_run: bool = False):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)

    if not dry_run:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE, when="midnight", backupCount=7, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_last_run(state: dict, account_name: str, default_lookback_hours: int) -> datetime:
    ts_str = state.get(account_name)
    if ts_str:
        return datetime.fromisoformat(ts_str)
    return datetime.now(timezone.utc) - timedelta(hours=default_lookback_hours)


def print_dry_run_report(account: AccountConfig, emails: list[dict], results: list[dict], last_run: datetime):
    width = 100
    sep = "=" * width
    thin = "-" * width

    print(f"\n{sep}")
    print(f"  DRY-RUN REPORT  |  account: {account.name} ({account.email})")
    print(f"  Emails fetched since: {last_run.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Total emails found: {len(emails)}")
    print(sep)

    counts = {"spam_promo": 0, "coupon": 0, "important": 0, "newsletter": 0,
              "financial_newsletter": 0, "github_notification": 0, "job_offer": 0,
              "concert_ticket": 0, "travel": 0}

    for email, result in zip(emails, results):
        cat = result["category"]
        counts[cat] += 1
        action = CATEGORY_LABEL[cat]
        subject = email["subject"][:70]
        sender = email["sender"][:50]

        icon = {
            "spam_promo": "🗑 ", "coupon": "🏷 ", "important": "⭐",
            "newsletter": "📰", "financial_newsletter": "💰", "github_notification": "🐙",
            "job_offer": "💼", "concert_ticket": "🎟 ", "travel": "✈ ",
        }[cat]
        print(f"\n{icon} [{action}]")
        print(f"   Subject : {subject}")
        print(f"   From    : {sender}")
        print(f"   Labels  : {', '.join(email.get('label_ids', [])) or '(none)'}")

        if cat == "coupon":
            cd = result["coupon_data"]
            print(f"   Code    : {cd.get('code') or '(not extracted)'}")
            print(f"   Discount: {cd.get('discount_description') or '(not extracted)'}")
        elif cat in ("newsletter", "concert_ticket", "travel", "financial_newsletter", "github_notification"):
            print(f"   Tag     : {result.get('label_name', '')}")

    print(f"\n{sep}")
    print(f"  SUMMARY")
    print(thin)
    print(f"  🗑  Spam/promo          → would be TRASHED           : {counts['spam_promo']}")
    print(f"  🏷  Coupons             → would be SAVED+TRASHED      : {counts['coupon']}")
    print(f"  ⭐  Important           → would be KEPT               : {counts['important']}")
    print(f"  📰  Newsletters         → would be LABELED+KEPT       : {counts['newsletter']}")
    print(f"  💰  Financial news      → would be LABELED+KEPT+DIGEST: {counts['financial_newsletter']}")
    print(f"  🐙  GitHub notifs       → would be LABELED+KEPT+DIGEST: {counts['github_notification']}")
    print(f"  💼  Job offers          → would be LABELED+KEPT       : {counts['job_offer']}")
    print(f"  🎟  Concert tickets     → would be LABELED+KEPT       : {counts['concert_ticket']}")
    print(f"  ✈   Travel bookings    → would be LABELED+KEPT       : {counts['travel']}")
    print(sep)
    print("  No changes were made. Run without --dry-run to apply.")
    print(f"{sep}\n")


def process_account(account: AccountConfig, config, last_run: datetime, dry_run: bool) -> dict:
    log = logging.getLogger(f"account.{account.name}")
    log.info(f"Processing {account.email} since {last_run.isoformat()}")

    gmail = gmail_module.GmailClient(account)
    emails = gmail.fetch_emails_since(last_run)

    counts = {"total": len(emails), "spam": 0, "coupons": 0, "important": 0, "newsletters": 0,
              "financial_newsletters": 0, "github_notifications": 0, "job_offers": 0,
              "concert_tickets": 0, "travel": 0}
    important_emails = []
    newsletter_emails = []  # newsletter emails with label_name, for digest detail section
    trashed_senders = []    # sender strings for every email moved to trash
    newsletter_labels = []  # label_name strings, one per newsletter (for summary count line)
    dry_run_results = []

    for email in emails:
        result = classifier.classify_email(email)
        category = result["category"]

        if dry_run:
            dry_run_results.append(result)
            if category == "spam_promo":
                counts["spam"] += 1
            elif category == "coupon":
                counts["coupons"] += 1
            elif category == "newsletter":
                label_name = result["label_name"]
                newsletter_labels.append(label_name)
                newsletter_emails.append({**email, "label_name": label_name})
                counts["newsletters"] += 1
            elif category == "financial_newsletter":
                important_emails.append(email)
                counts["financial_newsletters"] += 1
            elif category == "github_notification":
                important_emails.append(email)
                counts["github_notifications"] += 1
            elif category == "job_offer":
                counts["job_offers"] += 1
            elif category == "concert_ticket":
                counts["concert_tickets"] += 1
            elif category == "travel":
                counts["travel"] += 1
            else:
                important_emails.append(email)
                counts["important"] += 1
        else:
            if category == "spam_promo":
                gmail.move_to_trash(email["id"])
                trashed_senders.append(email["sender"])
                counts["spam"] += 1
            elif category == "coupon":
                notion_client.save_coupon(result["coupon_data"], account.notion_database_id)
                gmail.move_to_trash(email["id"])
                trashed_senders.append(email["sender"])
                counts["coupons"] += 1
            elif category == "newsletter":
                label_name = result["label_name"]
                color = LABEL_COLORS.get(label_name, DEFAULT_LABEL_COLOR)
                label_id = gmail.ensure_label(label_name, color)
                gmail.apply_label(email["id"], label_id)
                newsletter_labels.append(label_name)
                newsletter_emails.append({**email, "label_name": label_name})
                counts["newsletters"] += 1
            elif category in ("financial_newsletter", "github_notification"):
                label_name = result["label_name"]
                color = LABEL_COLORS.get(label_name, DEFAULT_LABEL_COLOR)
                label_id = gmail.ensure_label(label_name, color)
                gmail.apply_label(email["id"], label_id)
                important_emails.append({**email, "label_name": label_name})
                if category == "financial_newsletter":
                    counts["financial_newsletters"] += 1
                else:
                    counts["github_notifications"] += 1
            elif category == "job_offer":
                label_name = "Job Offers"
                color = LABEL_COLORS[label_name]
                label_id = gmail.ensure_label(label_name, color)
                gmail.apply_label(email["id"], label_id)
                important_emails.append({**email, "label_name": label_name})
                counts["job_offers"] += 1
            elif category == "concert_ticket":
                label_name = result["label_name"]
                color = LABEL_COLORS["Concert Tickets"]
                label_id = gmail.ensure_label(label_name, color)
                gmail.apply_label(email["id"], label_id)
                important_emails.append({**email, "label_name": label_name})
                counts["concert_tickets"] += 1
            elif category == "travel":
                label_name = result["label_name"]
                color = LABEL_COLORS["Travel"]
                label_id = gmail.ensure_label(label_name, color)
                gmail.apply_label(email["id"], label_id)
                important_emails.append({**email, "label_name": label_name})
                counts["travel"] += 1
            else:
                important_emails.append(email)
                counts["important"] += 1

    if dry_run:
        print_dry_run_report(account, emails, dry_run_results, last_run)
    else:
        log.info(
            f"Done: {counts['total']} total | {counts['spam']} spam | "
            f"{counts['coupons']} coupons | {counts['important']} important | "
            f"{counts['newsletters']} newsletters | {counts['financial_newsletters']} fin.newsletters | "
            f"{counts['github_notifications']} github | {counts['job_offers']} job offers | "
            f"{counts['concert_tickets']} concert tickets | {counts['travel']} travel"
        )

    return {"counts": counts, "important_emails": important_emails,
            "newsletter_emails": newsletter_emails, "newsletter_labels": newsletter_labels,
            "trashed_senders": trashed_senders}


def _send_digest(notifier: str, account, config, result: dict):
    if notifier == "whatsapp":
        if not account.whatsapp_phone:
            raise EnvironmentError(f"[{account.name}] whatsapp_phone not set in accounts.yaml")
        if not config.whatsapp_phone_number_id or not config.whatsapp_access_token:
            raise EnvironmentError("WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN must be set in environment")
        whatsapp_notifier.send_digest(
            phone_number_id=config.whatsapp_phone_number_id,
            access_token=config.whatsapp_access_token,
            template_name=config.whatsapp_template_name,
            recipient=account.whatsapp_phone,
            important_emails=result["important_emails"],
            newsletter_emails=result["newsletter_emails"],
            newsletter_labels=result["newsletter_labels"],
            trashed_senders=result["trashed_senders"],
            counts=result["counts"],
            account_name=account.name,
        )
    else:
        telegram_notifier.send_digest(
            important_emails=result["important_emails"],
            newsletter_emails=result["newsletter_emails"],
            newsletter_labels=result["newsletter_labels"],
            trashed_senders=result["trashed_senders"],
            counts=result["counts"],
            chat_id=account.telegram_chat_id,
            account_name=account.name,
        )


def _send_error_alert(notifier: str, account, config, error_message: str):
    if notifier == "whatsapp":
        if account.whatsapp_phone and config.whatsapp_phone_number_id and config.whatsapp_access_token:
            whatsapp_notifier.send_error_alert(
                phone_number_id=config.whatsapp_phone_number_id,
                access_token=config.whatsapp_access_token,
                template_name=config.whatsapp_template_name,
                recipient=account.whatsapp_phone,
                error_message=error_message,
                account_name=account.name,
            )
    else:
        telegram_notifier.send_error_alert(
            error_message=error_message,
            chat_id=account.telegram_chat_id,
            account_name=account.name,
        )


def main():
    parser = argparse.ArgumentParser(description="Gmail inbox cleaner")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and classify emails but make no changes (no trash, no Notion, no notifications, no state update). Defaults to 7-day lookback.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Days to look back in dry-run mode (default: 7). Ignored in normal mode.",
    )
    parser.add_argument(
        "--notifier",
        choices=["telegram", "whatsapp"],
        default="telegram",
        help="Notification channel: 'telegram' (v1, default) or 'whatsapp' (v2 via CallMeBot).",
    )
    args = parser.parse_args()
    dry_run = args.dry_run
    notifier = args.notifier

    setup_logging(dry_run=dry_run)
    logger = logging.getLogger("main")

    if dry_run:
        logger.info("=== DRY-RUN MODE — no changes will be made ===")
    else:
        logger.info(f"=== Email Inbox Cleaner starting (notifier: {notifier}) ===")

    config = load_config()

    if not dry_run:
        notion_client.init(config.notion_token)
        if notifier == "telegram":
            if not config.telegram_bot_token:
                raise EnvironmentError("TELEGRAM_BOT_TOKEN is required when using --notifier telegram")
            telegram_notifier.init(config.telegram_bot_token)

    state = load_state()
    enabled_accounts = [a for a in config.accounts if a.enabled]
    logger.info(f"Processing {len(enabled_accounts)} account(s)")

    for account in enabled_accounts:
        try:
            if dry_run:
                last_run = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
            else:
                last_run = get_last_run(state, account.name, config.default_lookback_hours)
            result = process_account(account, config, last_run, dry_run=dry_run)

            if not dry_run:
                _send_digest(notifier, account, config, result)
                state[account.name] = datetime.now(timezone.utc).isoformat()

        except Exception:
            tb = traceback.format_exc()
            logger.error(f"[{account.name}] Fatal error:\n{tb}")
            if not dry_run:
                _send_error_alert(notifier, account, config, tb[-800:])

    if not dry_run:
        save_state(state)
        logger.info("=== Email Inbox Cleaner finished ===")


if __name__ == "__main__":
    main()
