from dataclasses import dataclass
import os
import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AccountConfig:
    name: str
    email: str
    credentials_dir: str
    notion_database_id: str
    telegram_chat_id: str
    whatsapp_phone: str = ""  # recipient number, E.164 without +, e.g. 5511987654321
    enabled: bool = True


@dataclass
class AppConfig:
    accounts: list
    default_lookback_hours: int
    telegram_bot_token: str
    notion_token: str
    whatsapp_phone_number_id: str = ""   # Meta sender phone number ID
    whatsapp_access_token: str = ""      # Meta System User permanent token
    whatsapp_template_name: str = "email_digest_daily"


def load_config(accounts_file: str = "accounts.yaml") -> AppConfig:
    with open(accounts_file, "r") as f:
        raw = yaml.safe_load(f)

    shared = raw.get("shared", {})
    accounts = [
        AccountConfig(
            name=a["name"],
            email=a["email"],
            credentials_dir=a["credentials_dir"],
            notion_database_id=a["notion_database_id"],
            telegram_chat_id=str(a.get("telegram_chat_id", "")),
            whatsapp_phone=str(a.get("whatsapp_phone", "")),
            enabled=a.get("enabled", True),
        )
        for a in raw.get("accounts", [])
    ]

    notion_token = os.environ.get("NOTION_TOKEN", "")
    if not notion_token:
        raise EnvironmentError("Missing required environment variable: NOTION_TOKEN")

    return AppConfig(
        accounts=accounts,
        default_lookback_hours=shared.get("default_lookback_hours", 24),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        notion_token=notion_token,
        whatsapp_phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
        whatsapp_access_token=os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
        whatsapp_template_name=os.environ.get("WHATSAPP_TEMPLATE_NAME", "email_digest_daily"),
    )
