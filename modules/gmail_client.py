import base64
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import AccountConfig

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
logger = logging.getLogger(__name__)


class GmailClient:
    def __init__(self, account: AccountConfig):
        self.account = account
        creds_dir = Path(account.credentials_dir)
        self._credentials_path = str(creds_dir / "credentials.json")
        self._token_path = str(creds_dir / "token.json")
        self._service = self._authenticate()
        self._label_cache: dict[str, str] = {}  # label_name → label_id

    def _authenticate(self):
        creds = None
        token_path = Path(self._token_path)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info(f"[{self.account.name}] Refreshing Gmail token")
                creds.refresh(Request())
            else:
                logger.info(f"[{self.account.name}] Starting OAuth browser flow for {self.account.email}")
                flow = InstalledAppFlow.from_client_secrets_file(self._credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
            logger.info(f"[{self.account.name}] Token saved to {self._token_path}")

        return build("gmail", "v1", credentials=creds)

    def fetch_emails_since(self, since: datetime) -> list[dict]:
        unix_ts = int(since.timestamp())
        query = f"in:inbox after:{unix_ts}"
        logger.info(f"[{self.account.name}] Fetching emails since {since.isoformat()} (query: {query})")

        messages = []
        page_token = None

        while True:
            kwargs = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token
            result = self._service.users().messages().list(**kwargs).execute()
            batch = result.get("messages", [])
            messages.extend(batch)
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"[{self.account.name}] Found {len(messages)} messages")

        emails = []
        for msg_ref in messages:
            try:
                msg = self._service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="full"
                ).execute()
                emails.append(self._parse_message(msg))
            except Exception as e:
                logger.warning(f"[{self.account.name}] Failed to fetch message {msg_ref['id']}: {e}")

        return emails

    def _parse_message(self, msg: dict) -> dict:
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        snippet = msg.get("snippet", "")[:400]

        body = self._extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "sender": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": body[:400] if body else snippet,
            "label_ids": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        mime_type = payload.get("mimeType", "")

        if mime_type in ("text/plain", "text/html"):
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")

        for part in payload.get("parts", []):
            body = self._extract_body(part)
            if body:
                return body

        return ""

    def move_to_trash(self, message_id: str):
        self._service.users().messages().trash(userId="me", id=message_id).execute()
        logger.debug(f"[{self.account.name}] Trashed message {message_id}")

    def ensure_label(self, label_name: str, color: dict | None = None) -> str:
        """Returns the Gmail label ID, creating the label (with color) if it doesn't exist yet."""
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        existing = self._service.users().labels().list(userId="me").execute()
        for label in existing.get("labels", []):
            if label["name"] == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]

        body: dict = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if color:
            body["color"] = color

        created = self._service.users().labels().create(userId="me", body=body).execute()
        self._label_cache[label_name] = created["id"]
        logger.info(f"[{self.account.name}] Created Gmail label '{label_name}'")
        return created["id"]

    def apply_label(self, message_id: str, label_id: str):
        self._service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]}
        ).execute()
        logger.debug(f"[{self.account.name}] Applied label {label_id} to message {message_id}")
