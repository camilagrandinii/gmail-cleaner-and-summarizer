# Gmail Cleaner & Summarizer

Automated Gmail inbox cleaner that runs every morning via **GitHub Actions** and delivers a WhatsApp digest using the **official Meta Cloud API**. No server required. Completely free.

---

## Features

- **Automatic daily cleanup** — runs at 7 AM BRT via GitHub Actions, no machine needed
- **Smart classification** — categorises every incoming email using Gmail's own labels (no AI API cost)
- **Spam removal** — promotional and social emails are moved to Trash automatically
- **Coupon extraction** — detects discount codes, saves them to a Notion database, then trashes the email
- **Newsletter labelling** — newsletters, financial updates, GitHub notifications, and job offers get labelled and kept
- **WhatsApp digest** — a daily summary of important emails lands in your WhatsApp via Meta's official API
- **Multi-account** — add new Gmail accounts with a single config entry, no code changes
- **Local mode** — run with `--dry-run` to preview actions, or `--notifier telegram` for the classic Telegram digest

---

## How It Works

```
GitHub Actions (cron: 07:00 BRT)
        │
        ▼
  main.py ──► Gmail API (OAuth2)
        │         Fetch emails since last run
        │         Classify via Gmail category labels
        │         Trash spam/promos
        │         Save coupons → Notion API
        │         Label newsletters
        ▼
  WhatsApp (Meta Cloud API)
        Send daily digest with important emails
```

### Classification logic

Gmail automatically assigns category labels to every email. The classifier maps them to actions with no external API calls:

| Gmail category | Action |
|---|---|
| `CATEGORY_PROMOTIONS`, `CATEGORY_SOCIAL`, `CATEGORY_FORUMS` | Move to Trash |
| `CATEGORY_UPDATES` | Move to Trash |
| Contains coupon keywords | Extract code → save to Notion → Trash |
| Matches newsletter senders | Apply Gmail label, keep in inbox |
| No category (Primary tab) | Keep in inbox, include in digest |

---

## Project Structure

```
main.py                      Entry point — orchestrates the per-account loop
config.py                    Loads accounts.yaml + environment variables
accounts.yaml                Per-account config (email, Notion DB, WhatsApp number)
backfill_labels.py           One-time utility to label existing inbox emails

modules/
  gmail_client.py            OAuth2 auth, email fetching, trash, label management
  classifier.py              Rule-based email classification (no AI)
  notion_client.py           Saves coupon records to Notion
  whatsapp_notifier.py       Sends digest via Meta WhatsApp Cloud API
  telegram_notifier.py       Sends digest via Telegram Bot API (local/v1 mode)

credentials/{name}/
  credentials.json           GCP OAuth client secret (you provide, never committed)
  token.json                 Auto-generated on first OAuth run (never committed)

.github/workflows/
  daily-clean.yml            GitHub Actions workflow — scheduled daily at 10:00 UTC

state/last_run.json          Tracks last successful run per account (auto-managed)
logs/cleaner.log             Rotating daily log, 7-day retention
```

---

## Setup

Full step-by-step instructions are in **[SETUP_V2.md](SETUP_V2.md)**.

High-level checklist:

- [ ] **Gmail API** — create a GCP project, enable Gmail API, download `credentials.json` as a Desktop App credential, and run the OAuth flow once locally
- [ ] **Notion** — create an integration and a database with the required schema; link them
- [ ] **Meta WhatsApp** — create a Meta Developer app, add WhatsApp, register your number as a test recipient, and create the `email_digest_daily` message template
- [ ] **Permanent token** — generate a non-expiring System User token in Meta Business Manager
- [ ] **GitHub repo** — push the project (respecting `.gitignore`) and add the six required secrets
- [ ] **Test** — trigger the workflow manually with `dry_run = true`, then a real run

---

## GitHub Secrets

Configure these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `GMAIL_CREDENTIALS_CAMILA` | `base64 -w 0 credentials/camila/credentials.json` |
| `GMAIL_TOKEN_CAMILA` | `base64 -w 0 credentials/camila/token.json` |
| `NOTION_TOKEN` | Notion internal integration token |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta sender Phone Number ID |
| `WHATSAPP_ACCESS_TOKEN` | Meta System User permanent token |
| `PAT_UPDATE_SECRETS` | GitHub PAT (scope: `repo`) — lets the workflow refresh the Gmail token secret |

---

## WhatsApp Message Template

Create a template named exactly `email_digest_daily` in the Meta dashboard (category: **Utility**, language: **Portuguese Brazil**):

```
📧 Email Digest — {{1}}

{{2}}

Gerado automaticamente · Clean Email Inbox
```

`{{1}}` receives the date, `{{2}}` receives the digest body.

---

## Local Development

```bash
# Create and activate the virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run OAuth flow once per account (opens a browser)
python3 main.py --dry-run

# Preview classification for the last 7 days — no changes, no notifications
python3 main.py --dry-run

# Preview a specific lookback window
python3 main.py --dry-run --lookback-days 3

# Run normally, sending the digest to Telegram (v1 mode)
python3 main.py --notifier telegram

# Run normally, sending the digest to WhatsApp
python3 main.py --notifier whatsapp

# Backfill labels on all existing inbox emails (one-time utility)
python3 backfill_labels.py --dry-run   # preview
python3 backfill_labels.py             # apply
```

---

## Notion Database Schema

Each coupon is saved as a page in a Notion database. The database must have exactly these properties:

| Property | Type |
|----------|------|
| `Name` | Title |
| `Discount` | Rich Text |
| `Sender` | Rich Text |
| `Expiry` | Date |
| `Saved On` | Date |

---

## Adding a New Account

1. Create `credentials/{name}/credentials.json` from GCP
2. Add an entry to `accounts.yaml`:
   ```yaml
   - name: newaccount
     enabled: true
     email: newaccount@gmail.com
     credentials_dir: credentials/newaccount
     notion_database_id: "your_database_id"
     telegram_chat_id: "your_chat_id"
     whatsapp_phone: "5511987654321"
   ```
3. Run `python3 main.py --dry-run` locally — a browser window opens for OAuth consent
4. Add `GMAIL_CREDENTIALS_{NEWACCOUNT_UPPER}` and `GMAIL_TOKEN_{NEWACCOUNT_UPPER}` secrets to GitHub
5. Add the new number as a test recipient in the Meta dashboard
6. Update `.github/workflows/daily-clean.yml` to restore the new account's credentials

---

## Tech Stack

- **Python 3.12**
- **Gmail API** (google-api-python-client) — OAuth2, read + modify scope
- **Meta WhatsApp Cloud API** — official Graph API, template messages
- **Notion API** (notion-client) — coupon database
- **Telegram Bot API** (requests) — optional local notification channel
- **GitHub Actions** — free cloud scheduler, cron-based
