# Clean Email Inbox — Setup Guide v1 (Local + Telegram)

> **Existe uma v2** que roda na nuvem sem depender do computador e envia o resumo pelo WhatsApp.
> Veja **SETUP_V2.md** para configurar.

Everything you need to do once before the script runs on its own every day at 7 AM via Windows Task Scheduler.

---

## Prerequisites

- Python 3.10+ installed in WSL2
- A Google account for the inbox you want to clean
- A Notion account
- A Telegram account

---

## Step 1 — Gmail API (Google Cloud Console)

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com) and create a new project (name it anything, e.g. `email-cleaner`).
2. In the left menu go to **APIs & Services → Library**, search for **Gmail API** and click **Enable**.
3. Go to **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - Fill in app name (anything) and your email as support email
   - On the **Scopes** step, skip (no need to add scopes here)
   - On the **Test users** step, click **Add users** and add `camilagrandini@gmail.com`
   - Save and continue
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**:
   - Application type: **Desktop app**
   - Name it anything
   - Click **Create**
5. Download the JSON file and save it as:
   ```
   credentials/camila/credentials.json
   ```

---

## Step 2 — Telegram Bot

1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot`, follow the prompts, choose a name and username.
3. Copy the **Bot Token** (looks like `123456789:ABCdef...`).
4. Start a conversation with your new bot — send it any message.
5. Get your **Chat ID**: open this URL in your browser, replacing `TOKEN` with your bot token:
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
   Find `"chat":{"id": XXXXXXX}` in the response — that number is your Chat ID.

---

## Step 3 — Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) and click **New integration**.
2. Name it (e.g. `Email Coupon Saver`), select your workspace, click **Submit**.
3. Copy the **Internal Integration Token** (starts with `secret_...`).
4. Create a new Notion database (or use an existing page) with exactly these property names and types:

   | Property name | Type      |
   |---------------|-----------|
   | `Name`        | Title     |
   | `Discount`    | Rich Text |
   | `Sender`      | Rich Text |
   | `Expiry`      | Date      |
   | `Saved On`    | Date      |

5. Open that database in Notion, click the **...** menu (top right) → **Connections** → find and add your integration.
6. Copy the **Database ID** from the URL:
   ```
   https://www.notion.so/yourworkspace/DATABASE_ID?v=...
   ```
   The Database ID is the 32-character alphanumeric string before `?v=`.

---

## Step 4 — Fill in configuration files

**`.env`** — open the file and replace the placeholder values:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
NOTION_TOKEN=secret_your_token_here
```

**`accounts.yaml`** — replace the two placeholder values under the `camila` account:
```yaml
notion_database_id: "your_32_char_database_id"
telegram_chat_id: "your_chat_id_number"
```

---

## Step 5 — First run (OAuth browser flow)

This step only happens once. It opens a browser for you to authorize Gmail access.

Open a WSL2 terminal in the project directory and run:

```bash
cd '/mnt/c/Users/camila/OneDrive/Área de Trabalho/Camila/1.6 Freelances/Claude Utils/Clean-Email-Inbox'
source .venv/bin/activate
python3 main.py --dry-run
```

A browser window will open. Log in with `camilagrandini@gmail.com` and click **Allow**.

After authorizing, the script will fetch emails and print a full dry-run report to the terminal showing exactly what it would do — without actually trashing anything, writing to Notion, or sending a Telegram message.

Review the output carefully. If the classifications look correct, proceed to Step 6.

---

## Step 6 — First real run

```bash
python3 main.py
```

This will:
- Trash all spam/promo emails
- Save coupon emails to Notion and trash them
- Keep important emails in the inbox
- Send a Telegram digest to your bot

---

## Step 7 — Verify the Task Scheduler

The daily 7 AM task was already registered. To confirm it's active:

1. Press `Win + R`, type `taskschd.msc`, press Enter.
2. In **Task Scheduler Library**, find **Email Inbox Cleaner**.
3. The **Status** column should show `Ready`.
4. To test it immediately: right-click → **Run**.

From this point on the script runs automatically every day at 7 AM. If your machine is off at 7 AM it will run as soon as it turns on.

---

## Adding a new account

1. Create a new folder under `credentials/`:
   ```
   credentials/newaccount/credentials.json
   ```
2. Add an entry to `accounts.yaml`:
   ```yaml
   - name: newaccount
     enabled: true
     email: newaccount@gmail.com
     credentials_dir: credentials/newaccount
     notion_database_id: "their_database_id"
     telegram_chat_id: "their_chat_id"
   ```
3. Run `python3 main.py --dry-run` — a new browser window will open for the new account's OAuth consent.
4. No code changes needed.

---

## File reference

```
.env                        → Telegram + Notion API keys
accounts.yaml               → Per-account config (email, Notion DB, Telegram chat)
credentials/camila/
  credentials.json          → Downloaded from Google Cloud Console (you provide)
  token.json                → Auto-generated after first OAuth run (do not delete)
state/last_run.json         → Auto-managed; tracks when each account was last processed
logs/cleaner.log            → Rotating daily log, kept for 7 days
```
