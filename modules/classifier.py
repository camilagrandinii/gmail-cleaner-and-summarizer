import re
import logging

logger = logging.getLogger(__name__)

# Gmail applies these labels to non-personal emails automatically
PROMO_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
UPDATE_LABELS = {"CATEGORY_UPDATES"}

# Protected newsletter senders — matched as substrings of the lowercase From header.
# Add entries here to protect more senders from being trashed.
NEWSLETTER_SENDERS = [
    ("contato@thenewscc.com.br", "The News"),
    ("thebizness@thenewscc.com.br", "The Bizness"),
    ("newsletter@radarfin.com.br", "Radar Fin"),
    ("newsletter@mail.aidrop.news", "AI Drop"),
    ("aidrop.news", "AI Drop"),
    ("aidrop@mail.beehiiv.com", "AI Drop"),
    ("tech-drops-newsletter@mail.beehiiv.com", "Tech Drops"),
    ("superhuman.com", "Superhuman"),
    ("joinsuperhuman.ai", "Superhuman"),
    ("superhuman@mail.joinsuperhuman.ai", "Superhuman"),
    ("daily.therundown.ai", "The Rundown AI"),
    ("crew@technews.therundown.ai", "The Rundown AI"),
    ("substack.com", "Substack"),
    ("newsletter@mail.datahackers.com.br", "Data Hackers"),
    ("agentai@mail.beehiiv.com", "Agent AI"),
    ("aisolo@mail.beehiiv.com", "AI Solo"),
    ("notice@email.anthropic.com", "Anthropic"),
    ("contatobiz@cesar.school", "CESAR School"),
]

# Financial/investment newsletter senders — kept, labeled, AND included in the Telegram daily digest.
FINANCIAL_NEWSLETTER_SENDERS = [
    ("relacionamento@info.infomoney.com.br", "InfoMoney"),
    ("naoresponda@auvpcapital.com.br", "AUVP Capital"),
]

# GitHub notification senders — kept, labeled, and included in the Telegram daily digest.
GITHUB_SENDERS = [
    "notifications@github.com",
]

# Ticket platform senders — matched as substrings of the lowercase From header.
CONCERT_TICKET_SENDERS = [
    "ticketmaster",
    "eventbrite",
    "sympla.com.br",
    "ingresso.com",
    "livenation",
    "seetickets",
    "axs.com",
    "ticket.com",
]

# Keywords that indicate a concert/event ticket email
CONCERT_TICKET_KEYWORDS = [
    "your ticket", "your tickets", "e-ticket", "eticket",
    "ticket confirmation", "event ticket", "concert ticket",
    "seu ingresso", "seus ingressos", "ingressos para",
    "bilhete", "bilhetes",
    "event confirmation",
]

# Gmail label colors (must be from Gmail's allowed palette).
LABEL_COLORS = {
    "The News":        {"backgroundColor": "#fb4c2f", "textColor": "#ffffff"},
    "The Bizness":     {"backgroundColor": "#efa093", "textColor": "#000000"},
    "Radar Fin":       {"backgroundColor": "#16a766", "textColor": "#ffffff"},
    "AI Drop":         {"backgroundColor": "#a479e2", "textColor": "#ffffff"},
    "Tech Drops":      {"backgroundColor": "#4a86e8", "textColor": "#ffffff"},
    "Superhuman":      {"backgroundColor": "#43d692", "textColor": "#ffffff"},
    "The Rundown AI":  {"backgroundColor": "#ffad47", "textColor": "#000000"},
    "Substack":        {"backgroundColor": "#e66550", "textColor": "#ffffff"},
    "Job Offers":      {"backgroundColor": "#fad165", "textColor": "#000000"},
    "Concert Tickets": {"backgroundColor": "#e07798", "textColor": "#ffffff"},
    "Data Hackers":    {"backgroundColor": "#8e63ce", "textColor": "#ffffff"},
    "Agent AI":        {"backgroundColor": "#4a86e8", "textColor": "#ffffff"},
    "AI Solo":         {"backgroundColor": "#c9daf8", "textColor": "#000000"},
    "Anthropic":       {"backgroundColor": "#434343", "textColor": "#ffffff"},
    "CESAR School":    {"backgroundColor": "#f2c960", "textColor": "#000000"},
    "InfoMoney":       {"backgroundColor": "#149e60", "textColor": "#ffffff"},
    "AUVP Capital":    {"backgroundColor": "#0b804b", "textColor": "#ffffff"},
    "GitHub":          {"backgroundColor": "#666666", "textColor": "#ffffff"},
}
DEFAULT_LABEL_COLOR = {"backgroundColor": "#cccccc", "textColor": "#000000"}

# Keywords that indicate a job-offer or recruitment email
JOB_KEYWORDS = [
    "job opportunity", "job opening", "job offer", "career opportunity",
    "we're hiring", "we are hiring", "is hiring", "open position", "open role",
    "talent acquisition", "joining our team", "join our team",
    "developer opportunity", "engineering opportunity",
    "you're a great fit", "perfect fit for", "we found a match",
    # Portuguese
    "vaga de ", "vagas de", "oportunidade de carreira", "oportunidade profissional",
    "processo seletivo", "recrutamento",
]

# Keywords that indicate spam even when Gmail places the email in Primary (no category label).
# These catch marketing/promotional emails that slipped past Gmail's categorisation.
SPAM_IN_PRIMARY_KEYWORDS = [
    "unsubscribe", "opt out", "opt-out", "email preferences", "marketing preferences",
    "you are receiving this", "you're receiving this",
    "limited time offer", "limited time only", "today only", "ends tonight", "expires soon",
    "last chance", "don't miss out", "act now",
    "exclusive offer", "special offer", "exclusive deal",
    "you've been selected", "you have been selected", "you've won", "you were selected",
    "claim your", "click here to claim", "claim now",
    "você está recebendo", "cancelar inscrição", "descadastrar",
    "oferta exclusiva", "oferta por tempo limitado", "ultima chance",
]

# Keywords that strongly indicate a coupon/promo code is present
COUPON_KEYWORDS = [
    "coupon", "promo code", "promocode", "discount code", "use code", "enter code",
    "voucher", "redeem", "% off", "%off", "save $", "save up to", "free shipping code",
    "exclusive code", "special code", "gift code", "referral code",
]

# Regex to extract coupon codes: uppercase alphanumeric strings 4–20 chars,
# optionally with hyphens, that look like codes (not common English words)
_CODE_RE = re.compile(r'\b([A-Z0-9][A-Z0-9\-]{3,19})\b')
_COMMON_WORDS = {
    "FROM", "SUBJECT", "DATE", "REPLY", "EMAIL", "GMAIL", "HTTP", "HTTPS",
    "HTML", "TEXT", "MIME", "UTF", "YOUR", "THIS", "THAT", "WITH", "FREE",
    "SALE", "SHOP", "SAVE", "DEAL", "OFFER", "ORDER", "CLICK", "HERE",
}


def _looks_like_code(token: str) -> bool:
    if token in _COMMON_WORDS:
        return False
    if len(token) < 4 or len(token) > 20:
        return False
    has_digit = any(c.isdigit() for c in token)
    has_letter = any(c.isalpha() for c in token)
    return has_digit and has_letter


def _extract_code(text: str) -> str | None:
    for match in _CODE_RE.finditer(text):
        token = match.group(1)
        if _looks_like_code(token):
            return token
    return None


def _extract_discount_description(subject: str, snippet: str) -> str | None:
    text = f"{subject} {snippet}"
    # Look for "X% off", "save $X", "up to X% off" patterns
    patterns = [
        re.compile(r'(\d+\s*%\s*off)', re.IGNORECASE),
        re.compile(r'(save\s+\$[\d,.]+)', re.IGNORECASE),
        re.compile(r'(up to\s+\d+\s*%\s*off)', re.IGNORECASE),
        re.compile(r'(\$[\d,.]+\s+off)', re.IGNORECASE),
        re.compile(r'(free\s+shipping)', re.IGNORECASE),
        re.compile(r'(buy\s+\d+\s+get\s+\d+)', re.IGNORECASE),
    ]
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(1)
    return None


def _has_coupon_keywords(subject: str, snippet: str) -> bool:
    text = f"{subject} {snippet}".lower()
    return any(kw in text for kw in COUPON_KEYWORDS)


def _is_job_offer(subject: str, snippet: str) -> bool:
    text = f"{subject} {snippet}".lower()
    return any(kw in text for kw in JOB_KEYWORDS)


def _is_concert_ticket(sender: str, subject: str, snippet: str) -> bool:
    if any(p in sender for p in CONCERT_TICKET_SENDERS):
        return True
    text = f"{subject} {snippet}".lower()
    return any(kw in text for kw in CONCERT_TICKET_KEYWORDS)


def classify_email(email: dict) -> dict:
    label_ids = set(email.get("label_ids", []))
    subject = email.get("subject", "")
    snippet = email.get("snippet", "")
    sender = email.get("sender", "")
    sender_lower = sender.lower()

    null_coupon = {"code": None, "discount_description": None, "expiry_date": None, "sender": sender}

    # Financial newsletters — label, keep, and include in Telegram digest
    for pattern, label_name in FINANCIAL_NEWSLETTER_SENDERS:
        if pattern in sender_lower:
            logger.debug(f"Financial newsletter ({label_name}): '{subject}'")
            return {"category": "financial_newsletter", "label_name": label_name}

    # GitHub notifications — label, keep, and include in Telegram digest
    if any(p in sender_lower for p in GITHUB_SENDERS):
        logger.debug(f"GitHub notification: '{subject}'")
        return {"category": "github_notification", "label_name": "GitHub"}

    # Protected newsletter senders — keep in inbox and label, never trash
    for pattern, label_name in NEWSLETTER_SENDERS:
        if pattern in sender_lower:
            logger.debug(f"Newsletter ({label_name}): '{subject}'")
            return {"category": "newsletter", "label_name": label_name}

    # Concert/event tickets — label and keep, never trash, skip Telegram
    if _is_concert_ticket(sender_lower, subject, snippet):
        logger.debug(f"Concert ticket: '{subject}'")
        return {"category": "concert_ticket", "label_name": "Concert Tickets"}

    # Job-offer emails — label and keep, skip Telegram digest
    if _is_job_offer(subject, snippet):
        logger.debug(f"Job offer: '{subject}'")
        return {"category": "job_offer", "coupon_data": null_coupon}

    is_promo = bool(PROMO_LABELS & label_ids)
    is_update = bool(UPDATE_LABELS & label_ids)

    if is_promo or is_update:
        if _has_coupon_keywords(subject, snippet):
            combined = f"{subject} {snippet}"
            code = _extract_code(combined.upper())
            discount = _extract_discount_description(subject, snippet)
            logger.debug(f"Coupon detected: '{subject}' | code={code}")
            return {
                "category": "coupon",
                "coupon_data": {
                    "code": code,
                    "discount_description": discount,
                    "expiry_date": None,
                    "sender": sender,
                },
            }
        logger.debug(f"Spam/promo: '{subject}'")
        return {"category": "spam_promo", "coupon_data": null_coupon}

    # Even without a promo label, trash it if the content looks like spam
    combined_lower = f"{subject} {snippet}".lower()
    if any(kw in combined_lower for kw in SPAM_IN_PRIMARY_KEYWORDS):
        logger.debug(f"Spam-in-primary: '{subject}'")
        return {"category": "spam_promo", "coupon_data": null_coupon}

    logger.debug(f"Important: '{subject}'")
    return {"category": "important", "coupon_data": null_coupon}
