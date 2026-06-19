import logging
from datetime import date

from notion_client import Client

logger = logging.getLogger(__name__)

_client: Client | None = None


def init(notion_token: str):
    global _client
    _client = Client(auth=notion_token)


def save_coupon(coupon_data: dict, database_id: str) -> bool:
    try:
        code = coupon_data.get("code") or "Unknown Code"
        discount = coupon_data.get("discount_description") or ""
        sender = coupon_data.get("sender") or ""
        expiry = coupon_data.get("expiry_date")

        properties = {
            "Name": {"title": [{"text": {"content": code}}]},
            "Discount": {"rich_text": [{"text": {"content": discount[:2000]}}]},
            "Sender": {"rich_text": [{"text": {"content": sender[:2000]}}]},
            "Saved On": {"date": {"start": date.today().isoformat()}},
        }

        if expiry:
            properties["Expiry"] = {"date": {"start": expiry}}

        _client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        logger.info(f"Saved coupon '{code}' to Notion database {database_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save coupon to Notion: {e}")
        return False
