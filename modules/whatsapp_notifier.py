import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v21.0"
# WhatsApp template body components allow up to 1024 chars per variable; we stay safe
MAX_BODY_LENGTH = 900


def _send_template(phone_number_id: str, access_token: str, recipient: str, template_name: str, body_params: list[str]):
    """Send a WhatsApp template message via Meta Cloud API."""
    # Template parameters forbid newlines/tabs — flatten multi-line content
    body_params = [p.replace("\n", " | ").replace("\t", " ") for p in body_params]
    url = f"{GRAPH_API_URL}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in body_params],
                }
            ],
        },
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        logger.info(f"WhatsApp message sent to {recipient}")
    except requests.HTTPError as e:
        detail = e.response.text if e.response is not None else ""
        logger.error(f"WhatsApp API error (to {recipient}): {e} — {detail}")
    except Exception as e:
        logger.error(f"WhatsApp send failed (to {recipient}): {e}")


def _sender_display(sender: str) -> str:
    try:
        if "<" in sender:
            name = sender.split("<")[0].strip().strip('"')
            if name:
                return name
            return sender.split("<")[1].strip(" >")
        return sender.strip()
    except Exception:
        return sender[:40]


def _format_newsletter_labels(labels: list[str]) -> str:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    parts = [f"{name} ({n})" if n > 1 else name for name, n in counts.items()]
    return " - ".join(parts)


def _format_trashed_senders(senders: list[str]) -> str:
    counts: dict[str, int] = {}
    for s in senders:
        name = _sender_display(s)
        counts[name] = counts.get(name, 0) + 1
    parts = [f"{name} ({n})" if n > 1 else name for name, n in counts.items()]
    # Cap to 12 entries to stay within WhatsApp body limit
    if len(parts) > 12:
        extra = len(parts) - 12
        parts = parts[:12] + [f"...+{extra} outros"]
    return "\n".join(f"• {p}" for p in parts)


def send_digest(
    phone_number_id: str,
    access_token: str,
    template_name: str,
    recipient: str,
    important_emails: list[dict],
    counts: dict,
    account_name: str,
    newsletter_labels: list[str] | None = None,
    trashed_senders: list[str] | None = None,
):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")
    total = counts.get("total", 0)
    newsletter_labels = newsletter_labels or []
    trashed_senders = trashed_senders or []

    if total == 0:
        body = f"Nenhum email novo desde a ultima execucao.\n\nExecutado as {time_str} UTC"
        _send_template(phone_number_id, access_token, recipient, template_name, [date_str, body])
        return

    spam = counts.get("spam", 0)
    coupons = counts.get("coupons", 0)
    important_count = counts.get("important", 0)
    newsletters = counts.get("newsletters", 0)
    fin_news = counts.get("financial_newsletters", 0)
    github = counts.get("github_notifications", 0)
    job_offers = counts.get("job_offers", 0)

    lines = [f"Resumo: {total} emails processados"]
    if spam:
        lines.append(f"• {spam} spam/promo descartados")
    if coupons:
        lines.append(f"• {coupons} cupons salvos no Notion")
    if important_count:
        lines.append(f"• {important_count} importantes mantidos")
    if newsletters:
        lines.append(f"• {newsletters} newsletters rotuladas")
    if fin_news:
        lines.append(f"• {fin_news} financeiros rotulados")
    if github:
        lines.append(f"• {github} notif. GitHub")
    if job_offers:
        lines.append(f"• {job_offers} vagas rotuladas")
    if newsletter_labels:
        lines.append(f"  ({_format_newsletter_labels(newsletter_labels)})")

    if trashed_senders:
        lines.append(f"\nDescartados ({len(trashed_senders)}):")
        lines.append(_format_trashed_senders(trashed_senders))

    if important_emails:
        lines.append("\nImportantes:")
        for email in important_emails:
            subj = email["subject"][:60]
            sender_name = _sender_display(email["sender"])
            snippet = email.get("snippet", "").strip()[:80]
            lines.append(f"• {sender_name}: {subj}")
            if snippet:
                lines.append(f"  {snippet}...")
    else:
        lines.append("\nNenhum email importante — caixa limpa!")

    lines.append(f"\nExecutado as {time_str} UTC")

    body = "\n".join(lines)

    if len(body) > MAX_BODY_LENGTH:
        cutoff = body[:MAX_BODY_LENGTH - 40].rfind("\n")
        shown = body[:cutoff] if cutoff > 0 else body[:MAX_BODY_LENGTH - 40]
        hidden = len(important_emails) - shown.count("•")
        body = shown + f"\n...mais {hidden} emails\n\nExecutado as {time_str} UTC"

    _send_template(phone_number_id, access_token, recipient, template_name, [date_str, body])


def send_error_alert(phone_number_id: str, access_token: str, template_name: str, recipient: str, error_message: str, account_name: str):
    body = f"ERRO no processamento ({account_name})\n\n{error_message[:700]}\n\nVerifique os logs no GitHub Actions."
    _send_template(phone_number_id, access_token, recipient, template_name, ["ERRO", body])
