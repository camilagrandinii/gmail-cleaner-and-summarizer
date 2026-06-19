# CLAUDE.md — Project context for AI assistants

This file exists so the next AI working on this project has full context without needing to reconstruct it from the code. Read this before touching anything.

---

## What this project does

Automated daily Gmail inbox cleaner. Runs every morning at 7 AM via Windows Task Scheduler. For each configured Gmail account it:

1. Fetches all emails received since the last run
2. Classifies each email into one of three categories using Gmail's own category labels (no AI API, completely free)
3. Acts on the classification:
   - **spam_promo** → moves to Gmail Trash
   - **coupon** → extracts the coupon data, saves a record to a Notion database, then moves to Trash
   - **important** → leaves in inbox, includes in daily digest
4. Sends a Telegram message to the account owner summarising what happened

The script is multi-account: one `accounts.yaml` entry per person. Adding a new client requires no code changes.

---

## Environment

- **OS**: Windows 11 with WSL2 (Ubuntu). All Python runs inside WSL2.
- **Python**: 3.12, virtualenv at `.venv/`
- **Scheduler**: Windows Task Scheduler calls `C:\Users\camila\email_cleaner_run.bat`, which calls `wsl.exe` to run `python3 main.py`. The `.bat` lives outside the project directory deliberately — see "Known quirks" below.
- **Working directory**: `/mnt/c/Users/camila/OneDrive/Área de Trabalho/Camila/1.6 Freelances/Claude Utils/Clean-Email-Inbox`
  - Note: the `Á` in `Área` causes encoding issues when passed through PowerShell or schtasks.exe. This is why the wrapper `.bat` lives at `C:\Users\camila\email_cleaner_run.bat` (plain ASCII path).

---

## File map

```
main.py                     Entry point. Handles CLI args, orchestrates per-account loop.
config.py                   Loads accounts.yaml + .env into AccountConfig / AppConfig dataclasses.
accounts.yaml               Per-account config. Edit this to add/remove accounts.
.env                        Shared secrets: TELEGRAM_BOT_TOKEN, NOTION_TOKEN.

modules/
  gmail_client.py           GmailClient class. OAuth2 token caching, fetch, trash.
  classifier.py             Pure label + keyword logic. No external API calls.
  notion_client.py          Thin wrapper around notion-client SDK. save_coupon().
  telegram_notifier.py      Sends digest and error alerts via Telegram Bot API (plain requests.post).

credentials/{name}/
  credentials.json          Downloaded from GCP. Provided by the user per account.
  token.json                Auto-generated on first OAuth run. Never commit this.

state/last_run.json         Dict of {account_name: ISO8601 timestamp}. Updated after each successful run.
logs/cleaner.log            TimedRotatingFileHandler, daily rotation, 7-day retention.

C:\Users\camila\email_cleaner_run.bat   Windows Task Scheduler entry point (outside project dir).
setup_scheduler.ps1         One-time script that registered the Task Scheduler task. Keep for reference.
SETUP.md                    Human-readable setup guide for first-time configuration.
```

---

## Classification logic

**No AI is used.** Classification is entirely rule-based and free.

Gmail automatically assigns category labels to every email:
- `CATEGORY_PROMOTIONS`, `CATEGORY_SOCIAL`, `CATEGORY_FORUMS` → treated as spam/promo
- `CATEGORY_UPDATES` → also treated as spam/promo (shipping notifications, newsletters)
- No category label (landed in Primary tab) → treated as important

**Coupon detection** runs as a second pass on emails already identified as promo/update:
- Keyword scan on subject + body snippet (see `COUPON_KEYWORDS` list in `classifier.py`)
- If keywords match → attempt to extract the coupon code via regex (`_CODE_RE`) and discount description via a set of patterns
- The regex looks for uppercase alphanumeric strings 4–20 chars with at least one digit and one letter, filtered against a `_COMMON_WORDS` blocklist

**What this means in practice**: classification quality is tied to how well Google has categorised the inbox. Emails that Gmail puts in Primary but are actually promotional will be classified as important. If the user wants more aggressive filtering, the place to improve this is `classifier.py` — either expand the keyword lists or add an optional AI classification layer (see "Possible improvements").

---

## How the Gmail OAuth flow works

OAuth credentials are per-account and stored in `credentials/{name}/`:
- `credentials.json` — downloaded from GCP once by the user. Type must be **Desktop App**, not Web App.
- `token.json` — auto-generated on first run. Contains both access token and refresh token.

On every run, `GmailClient.__init__()` in `modules/gmail_client.py`:
1. Loads `token.json` if present
2. If the access token is expired, refreshes it silently using the refresh token (no browser)
3. Writes the refreshed token back to `token.json`
4. If `token.json` is missing entirely, runs `InstalledAppFlow.run_local_server()` which opens a browser — this only happens on first run per account

The refresh token for a personal Gmail account in "Testing" mode on the OAuth consent screen does not expire unless manually revoked. If `token.json` is ever deleted, the next scheduled run will fail silently (no browser available). Recovery: run `python3 main.py --dry-run` manually.

OAuth scope: `https://www.googleapis.com/auth/gmail.modify` — read messages + move to trash. No send, no delete permanent.

---

## Dry-run mode

```bash
python3 main.py --dry-run
```

- Connects to Gmail and classifies all emails normally
- Prints a full report to stdout (subject, sender, labels, action that would be taken, coupon data if applicable)
- Does **nothing** else: no trashing, no Notion writes, no Telegram message, no `last_run.json` update
- Does not write to `logs/cleaner.log` (console only in dry-run)

Use this to verify classifications before the first real run, or after adding a new account.

---

## State management

`state/last_run.json` is a flat dict:
```json
{
  "camila": "2026-06-18T07:02:14.123456+00:00"
}
```

- If an account has no entry (first ever run), the script defaults to looking back `default_lookback_hours` (24h, set in `accounts.yaml` under `shared`).
- The timestamp is written **after** a successful run, not before. If the script crashes mid-run for an account, that account's timestamp is not updated, so the next run will reprocess the same window. This is intentional — better to re-classify than to miss emails. Re-classifying already-trashed emails is harmless (Gmail ignores a trash call on an already-trashed message).
- State is saved once at the end of `main()`, after all accounts are processed. Per-account timestamps are updated inside the loop only on success.

---

## Telegram notifications

Each account has its own `telegram_chat_id`. A single bot token (in `.env`) serves all accounts — different accounts just send to different chat IDs.

`telegram_notifier.py` uses `requests.post()` directly against the Telegram Bot API — no SDK. `parse_mode="HTML"` is used instead of Markdown to avoid breakage from `*` or `_` characters in email subjects.

Two functions:
- `send_digest()` — the daily summary with counts and list of important emails
- `send_error_alert()` — fires when an account's processing block raises an uncaught exception; the error traceback is truncated to 800 chars to fit Telegram's message size limit

---

## Notion integration

`notion_client.py` saves one Notion page per coupon email. The database schema (must match exactly):

| Property  | Notion type |
|-----------|-------------|
| `Name`    | Title       |
| `Discount`| Rich Text   |
| `Sender`  | Rich Text   |
| `Expiry`  | Date        |
| `Saved On`| Date        |

Each account points to its own Notion database via `notion_database_id` in `accounts.yaml`. All accounts share the same Notion integration token (`NOTION_TOKEN` in `.env`) — the integration just needs to be connected to each database separately in the Notion UI.

`save_coupon()` is wrapped in try/except and returns `False` on failure without raising. The calling code in `main.py` does not check the return value — a Notion failure logs an error but does not prevent the email from being trashed.

---

## Known quirks

**Unicode path (`Área`)**: The project lives in a path containing `Á` (U+00C1). This character gets mangled (`A?`) when passed through PowerShell's default encoding or `schtasks.exe`. Workaround: the Task Scheduler action points to `C:\Users\camila\email_cleaner_run.bat` (ASCII path), which in turn calls `wsl.exe` with the full Unicode path as a bash string literal. The VBS/BAT files inside the project dir still have the correct Unicode path — they just can't be used as the direct Task Scheduler target.

**Gmail body extraction**: `gmail_client.py` recursively walks the MIME tree to extract `text/plain` first, then `text/html`. Only the first 400 characters are used. For classification purposes this is sufficient — coupon keywords almost always appear in the subject or email opening lines.

**`google-api-python-client` metadata warning**: `pip list` shows a warning about an invalid metadata entry for `google-api-python-client`. This is a known cosmetic issue on NTFS-mounted WSL2 paths. The package imports and functions correctly — `from googleapiclient.discovery import build` works fine.

---

## Possible improvements

- **Smarter coupon extraction**: The regex misses codes that are all-alpha (e.g. `SUMMERSALE`). Improving `_looks_like_code()` to allow all-alpha codes would increase recall but also increase false positives. Tuning `_COMMON_WORDS` is the lever to pull here.
- **Expiry date extraction**: `coupon_data["expiry_date"]` is always `None` currently. The classifier makes no attempt to extract expiry dates — they're buried deep in HTML email bodies that we don't fully decode. A future improvement would be to decode the full HTML body and run a date regex over it.
- **AI fallback for ambiguous emails**: Emails landing in `CATEGORY_UPDATES` include both newsletters (should trash) and transactional emails like invoices and shipping confirmations (should keep). Currently all updates are trashed. An optional AI classification pass for `CATEGORY_UPDATES` emails specifically would improve accuracy without adding cost for the clearly promotional ones.
- **Unsubscribe instead of trash**: For persistent newsletters, the Gmail API exposes `List-Unsubscribe` headers. A future version could attempt to unsubscribe before trashing.
- **Web dashboard**: `state/last_run.json` and `logs/cleaner.log` are the only observability surfaces. A simple read-only Flask page or Notion dashboard summarising run history could be useful as the number of accounts grows.
