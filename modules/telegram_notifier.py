import html
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_bot_token: str = ""
MAX_MESSAGE_LENGTH = 4096


def init(bot_token: str):
    global _bot_token
    _bot_token = bot_token


def _send(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed (chat {chat_id}): {e}")


def _sender_display(sender: str) -> str:
    """Extract display name from 'Name <email>' or fall back to the email address."""
    try:
        if "<" in sender:
            name = sender.split("<")[0].strip().strip('"')
            if name:
                return name
            email = sender.split("<")[1].strip(" >")
            return email
        return sender.strip()
    except Exception:
        return sender[:40]


def _format_newsletter_labels(labels: list[str]) -> str:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    parts = [f"{name} ({n})" if n > 1 else name for name, n in counts.items()]
    return " · ".join(parts)


def send_digest(
    important_emails: list[dict],
    counts: dict,
    chat_id: str,
    account_name: str,
    newsletter_labels: list[str] | None = None,
    newsletter_emails: list[dict] | None = None,
    trashed_senders: list[str] | None = None,
):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%H:%M")
    total = counts.get("total", 0)
    newsletter_labels = newsletter_labels or []
    newsletter_emails = newsletter_emails or []
    trashed_senders = trashed_senders or []

    safe_account = html.escape(account_name)

    if total == 0:
        _send(chat_id, f"📬 <b>Email Digest — {date_str}</b> ({safe_account})\n\nNo new emails since last run.")
        return

    spam = counts.get("spam", 0)
    coupons = counts.get("coupons", 0)
    important_count = counts.get("important", 0)

    lines = [
        f"📬 <b>Email Digest — {date_str}</b> ({safe_account})",
        "",
        f"📊 <b>Summary:</b> {total} emails processed",
        f"  🗑 {spam} spam/promo → trashed",
        f"  🏷 {coupons} coupons → saved to Notion + trashed",
        f"  ⭐ {important_count} important → kept in inbox",
    ]

    if newsletter_labels:
        lines.append(f"  📰 {_format_newsletter_labels(newsletter_labels)}")

    if trashed_senders:
        sender_counts: dict[str, int] = {}
        for s in trashed_senders:
            name = _sender_display(s)
            sender_counts[name] = sender_counts.get(name, 0) + 1
        parts = [f"{n} ({c})" if c > 1 else n for n, c in sender_counts.items()]
        if len(parts) > 15:
            extra = len(parts) - 15
            parts = parts[:15] + [f"+{extra} others"]
        lines += ["", f"🗑 <b>Trashed ({len(trashed_senders)}):</b>"]
        lines += [f"  • {html.escape(p)}" for p in parts]

    if newsletter_emails:
        lines += ["", "📰 <b>Newsletters:</b>"]
        for email in newsletter_emails:
            subj = email["subject"][:70]
            label = email.get("label_name", "")
            tag = f"[{html.escape(label)}] " if label else ""
            lines.append(f'• {tag}"{html.escape(subj)}"')

    if important_emails:
        lines += ["", "⭐ <b>Important Emails:</b>"]
        for email in important_emails:
            subj = email["subject"][:70]
            sender_name = _sender_display(email["sender"])
            label = email.get("label_name", "")
            label_tag = f" [{html.escape(label)}]" if label else ""
            lines.append(f'• <b>{html.escape(sender_name)}</b>{label_tag} — "{html.escape(subj)}"')
    else:
        lines += ["", "No important emails today — inbox is clean."]

    lines += ["", f"✅ Run completed at {time_str} UTC"]

    message = "\n".join(lines)

    if len(message) > MAX_MESSAGE_LENGTH:
        cutoff = message[:MAX_MESSAGE_LENGTH - 60].rfind("\n")
        shown = message[:cutoff] if cutoff > 0 else message[:MAX_MESSAGE_LENGTH - 60]
        hidden = len(important_emails) - shown.count("•")
        message = shown + f"\n...(and {hidden} more emails)\n\n✅ Run completed at {time_str} UTC"

    _send(chat_id, message)


def send_error_alert(error_message: str, chat_id: str, account_name: str):
    text = f"🚨 <b>Email cleaner failed</b> ({account_name})\n\n{html.escape(error_message)}\n\nCheck logs/cleaner.log"
    _send(chat_id, text)
