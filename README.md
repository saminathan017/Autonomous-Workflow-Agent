# Autonomous Workflow Agent

I built this to stop manually triaging my inbox every morning. It connects to Gmail, runs each email through OpenAI to classify and score it, syncs the results to a Google Sheet, and generates a short briefing I can read in two minutes. There's a web dashboard for managing everything, and I can schedule it to run automatically or trigger it manually.

---

## What it actually does

When you trigger a run (manually or on a schedule), the agent does this in order:

1. **Fetches emails** from Gmail using the read-only API. Parses headers, body, and snippet — no third-party email parsing library, just the raw Gmail API response.

2. **Classifies each email** using OpenAI function calling. The model returns one of six categories: `URGENT`, `CUSTOMER_INQUIRY`, `INVOICE`, `NEWSLETTER`, `SPAM`, or `GENERAL`, plus a confidence score and one-sentence reasoning. If the OpenAI call fails (rate limit, bad key, etc.), it falls back to a keyword ruleset so the pipeline doesn't just stop.

3. **Scores urgency and sentiment** — also via OpenAI function calling. Returns `POSITIVE / NEGATIVE / NEUTRAL`, an urgency score from 0 to 1, and whether the email needs immediate human attention. Emails scoring ≥ 0.7 get labelled "Important", 0.4–0.7 is "Needed Review", under that is "Take Your Time". Same keyword fallback applies.

4. **Writes to Google Sheets** — appends new rows only. It reads column A first, builds a set of existing email IDs, and skips anything already there. Idempotent, so re-running a workflow won't duplicate rows.

5. **Generates draft replies** for emails that scored `requires_human=true` or belong to URGENT / CUSTOMER_INQUIRY / INVOICE. The tone adjusts by category — customer inquiries get a warm, solution-focused reply; invoices get a formal one. Capped at five drafts per run to keep costs predictable. Newsletter and spam emails are skipped entirely.

6. **Extracts action items** concurrently across all emails. Each extraction runs in `asyncio.gather`, so it's not sequential. Skips NEWSLETTER and SPAM. Returns structured tasks with HIGH / MEDIUM / LOW priority and any due dates mentioned in the email.

7. **Builds a Markdown report** with two OpenAI calls — one for the executive summary paragraph, one for four key insights. Saves to `data/reports/report_YYYYMMDD_HHMMSS.md`. Startup auto-purges old reports, keeping the newest 50.

All steps except fetching emails are non-critical — if Sheets or draft generation fails, the run still completes. Only a Gmail fetch failure aborts the workflow entirely.

---

## Other things the dashboard can do

Beyond the core workflow, the dashboard has a few extra AI features:

- **Morning briefing** — pulls up to 100 processed emails, sends them to OpenAI, and returns a structured briefing with urgent items, key themes, and recommended next steps. Cached in the database so it doesn't hit OpenAI on every page load. Force-refresh with `?refresh=true`.

- **Email composer** — give it a recipient, your intent, and a tone (professional / friendly / direct / persuasive / apologetic / formal). Returns a full subject + body via function calling.

- **Topic clustering** — groups your processed emails into 4–8 themes. Useful after a big run to understand what's actually going on in your inbox.

- **Translation** — detects the language of any processed email and translates it to English if needed. Stores the result in the database so it only calls OpenAI once per email.

- **Follow-ups** — manually add follow-up reminders tied to emails, with a date and note.

- **Contact intelligence** — aggregates email frequency and urgency patterns by sender.

- **Anomaly detection** — simple statistical check for unusual spikes in email volume or urgency.

- **CSV export** — download the last N days of processed emails as a CSV file.

---

## How the backend is structured

The FastAPI app runs with two uvicorn workers. Each worker has its own asyncpg connection pool to PostgreSQL. WebSocket events during a workflow run are published to a Redis channel (`workflow:events:<run_id>`) — any worker can publish, any worker's WebSocket subscriber picks them up. This is why you don't lose real-time updates if the browser happens to connect to a different worker than the one running the workflow.

The APScheduler only runs in one worker. The first worker to call `pg_try_advisory_lock(42424242)` at startup wins. The other worker logs that it's a follower and skips starting the scheduler entirely. The lock is a PostgreSQL session-level advisory lock — it releases automatically when that worker's process exits.

On startup, any runs stuck in `RUNNING` or `PENDING` for more than two hours get marked as `FAILED`. This handles the case where the server crashed mid-run.

The OpenAI client has two cost controls built in: an `asyncio.Semaphore(5)` that hard-caps concurrent outbound requests to OpenAI, and a per-run call budget (default 50) that blocks further calls once hit. Rate limit errors (429) trigger exponential backoff — 5s, 10s, 20s — before retrying.

---

## Database

PostgreSQL with asyncpg. Twelve tables:

| Table | What it stores |
|---|---|
| `workflow_runs` | Run history, status, email count, report path |
| `step_logs` | Individual step timing and errors per run |
| `processed_emails` | Enriched email records with category, sentiment, urgency |
| `email_classifications` | Classification + sentiment results (separate from email records) |
| `draft_replies` | AI-generated reply drafts |
| `action_items` | Extracted tasks with priority and due date |
| `analytics` | Generic metric events |
| `schedule_config` | Saved scheduler settings (persisted across restarts) |
| `user_settings` | Dashboard preferences |
| `follow_ups` | Manual follow-up reminders |
| `email_translations` | Cached translation results |
| `briefing_cache` | Cached morning briefing content |

Schema is applied on startup via `state_store.initialize()`. Running it multiple times is safe — all statements use `CREATE TABLE IF NOT EXISTS`.

---

## Setup

### What you need before starting

- Python 3.11+ (I use miniconda — any environment where you can `pip install` works)
- PostgreSQL 16 running locally
- Redis 7 running locally
- An OpenAI API key
- A Google Cloud project with Gmail API and Sheets API enabled
- A `credentials.json` file downloaded from Google Cloud Console (OAuth 2.0 Desktop App type)
- The ID of a Google Sheet you want data written to

If you're on macOS, the easiest way to get PostgreSQL and Redis is:

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
createdb workflow_agent
```

### Install

```bash
git clone <repo-url>
cd "Autonomous Workflow Agent"
pip install -r autonomous_workflow_agent/requirements.txt
```

### Configure

```bash
cp autonomous_workflow_agent/.env.example autonomous_workflow_agent/.env
```

Open `.env` and fill in:
- `OPENAI_API_KEY` — your OpenAI key
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` — from Google Cloud Console
- `GOOGLE_SHEET_ID` — the long ID in your Sheet's URL
- `DATABASE_URL` — something like `postgresql://your_username@localhost:5432/workflow_agent`

Everything else has sensible defaults.

### Set up the database

```bash
PYTHONPATH=. python autonomous_workflow_agent/scripts/init_db.py
```

This creates all 12 tables. Safe to run again if you're not sure whether it's been run — it won't drop anything.

### Authenticate with Google

Put your `credentials.json` inside `autonomous_workflow_agent/`, then:

```bash
PYTHONPATH=. python authenticate.py
```

A browser window opens. Sign in with the Google account whose Gmail you want to read. Grant both Gmail (read-only) and Sheets permissions. A `token.json` is saved and used on every subsequent run — you shouldn't need to do this again unless the token expires and can't be refreshed.

---

## Running

**macOS:** double-click `Start_App.command` in Finder. It checks that PostgreSQL and Redis are running, initialises the database, starts the server with two workers, and opens the browser at `http://127.0.0.1:8001`.

**Terminal or Linux:**

```bash
./start_server.sh
```

Both do the same thing. The server listens on port 8001.

To run a one-off workflow without the web UI:

```bash
PYTHONPATH=. python autonomous_workflow_agent/scripts/run_once.py --emails 20
```

---

## API

The full OpenAPI docs are at `http://127.0.0.1:8001/docs` once the server is running. The main endpoints:

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/health` | Returns status of PostgreSQL and Redis |
| `POST` | `/api/run` | Starts a workflow run in the background |
| `GET` | `/api/runs` | Lists all runs with step details |
| `WS` | `/api/ws/runs/{id}` | Live WebSocket updates for a run in progress |
| `GET` | `/api/emails` | Paginated email list with category/urgency filters |
| `GET` | `/api/emails/priority-inbox` | Emails flagged as Important or Needed Review |
| `GET` | `/api/emails/{id}` | Single email |
| `POST` | `/api/emails/{id}/translate` | Detect language and translate to English |
| `GET` | `/api/drafts` | All draft replies |
| `GET` | `/api/emails/{id}/draft` | Draft for a specific email |
| `POST` | `/api/emails/{id}/draft/generate` | Generate a draft on demand |
| `GET` | `/api/actions` | Action items (filter by completed, priority) |
| `PUT` | `/api/actions/{id}/toggle` | Mark complete/incomplete |
| `GET` | `/api/analytics/summary` | 7-day stats: runs, emails, category/sentiment breakdown |
| `GET` | `/api/analytics/anomalies` | Volume and urgency anomaly flags |
| `GET` | `/api/reports` | List saved report files |
| `GET` | `/api/reports/{filename}` | Read a report's Markdown content |
| `GET` | `/api/briefing` | Morning briefing (cached; add `?refresh=true` to regenerate) |
| `POST` | `/api/compose` | Compose a new email from intent + tone |
| `GET` | `/api/topics` | Cluster processed emails into themes |
| `GET` | `/api/contacts` | Sender frequency and urgency breakdown |
| `GET` | `/api/export/csv` | Download processed emails as CSV |
| `GET` | `/api/schedule` | Current schedule config and next run time |
| `POST` | `/api/schedule` | Update schedule (daily cron or interval in hours) |
| `GET` | `/api/settings` | User preferences (auto-draft, action items, etc.) |
| `GET` | `/api/follow-ups` | Follow-up reminders |
| `POST` | `/api/webhooks/gmail` | Gmail push notification receiver |

---

## Project structure

```
Autonomous Workflow Agent/
├── .gitignore
├── README.md
├── Start_App.command          macOS double-click launcher
├── start_server.sh            CLI launcher
├── authenticate.py            one-time Google OAuth flow
├── verify_security.py         checks that secrets aren't staged for git
└── autonomous_workflow_agent/
    ├── .env.example
    ├── requirements.txt
    ├── docker-compose.yml     optional — runs PostgreSQL + Redis in Docker
    ├── app/
    │   ├── main.py            FastAPI app, lifespan (startup/shutdown)
    │   ├── config.py          Pydantic-settings config class
    │   ├── api/
    │   │   └── routes.py      all endpoints in one file
    │   ├── ai/
    │   │   ├── openai_client.py      async wrapper, semaphore, budget, backoff
    │   │   ├── email_classifier.py   classify_email() + keyword fallback
    │   │   ├── sentiment_analyzer.py analyze_sentiment() + keyword fallback
    │   │   ├── draft_generator.py    generate_draft_reply()
    │   │   ├── action_extractor.py   extract_action_items()
    │   │   ├── briefing_generator.py generate_briefing()
    │   │   ├── topic_clusterer.py    cluster_topics()
    │   │   └── email_composer.py     compose_email()
    │   ├── auth/
    │   │   ├── google_oauth.py       OAuth 2.0 flow, Gmail + Sheets service builders
    │   │   └── gmail_push.py         Gmail push notification handler
    │   ├── workflows/
    │   │   ├── engine.py             runs the six-step pipeline
    │   │   ├── event_bus.py          Redis pub/sub for WebSocket events
    │   │   ├── scheduler.py          APScheduler, daily or interval
    │   │   ├── state_store.py        all PostgreSQL queries in one place
    │   │   ├── models.py             Pydantic models for everything
    │   │   └── tasks/
    │   │       ├── gmail_reader.py   fetches and parses Gmail messages
    │   │       ├── sheets_writer.py  idempotent Sheets append
    │   │       └── report_builder.py builds and saves Markdown report
    │   ├── frontend/
    │   │   ├── index.html
    │   │   ├── app.js         React 18 via ESM imports — no npm, no build step
    │   │   └── styles.css
    │   └── utils/
    │       └── logging.py     Loguru setup, rotating daily log files
    ├── scripts/
    │   ├── init_db.py         creates the 12 PostgreSQL tables
    │   ├── run_once.py        manual CLI trigger with Rich output
    │   └── start_backend.sh   service checks + uvicorn
    └── data/                  gitignored — created at runtime
        ├── logs/
        └── reports/
```

---

## Notes on cost

The default is `gpt-4o-mini` with a 50-call budget per run. At current pricing ($0.15 / 1M input, $0.60 / 1M output), processing 10 emails with classification + sentiment + draft + actions + report comes to roughly $0.01–0.02 per run. The budget cap is a hard stop — once hit, remaining AI steps are skipped and the run completes with whatever was already done.

If you want to run this without an OpenAI key at all, classification and sentiment will use the keyword fallback, and draft generation / action extraction / reports will be skipped. The pipeline still runs and writes to Sheets.

---

## Running multiple workers

The server defaults to 2 workers in the launcher scripts. You can increase this:

```bash
uvicorn autonomous_workflow_agent.app.main:app \
  --host 127.0.0.1 --port 8001 --workers 4
```

WebSocket events go through Redis so no worker needs to be the "right" one for a given WebSocket connection. The scheduler advisory lock means only one worker will fire scheduled runs regardless of how many workers are up.

---

## Docker

If you'd rather not install PostgreSQL and Redis natively:

```bash
cd autonomous_workflow_agent
docker compose up -d
PYTHONPATH=.. python scripts/init_db.py
```

Update `DATABASE_URL` in `.env` to use the credentials from `docker-compose.yml`.

---

## Security

Before pushing to GitHub, run:

```bash
python verify_security.py
```

It checks that `.env`, `credentials.json`, and `token.json` are gitignored and scans tracked files for common secret patterns. These three files should never be committed.

CORS is locked to the origins in `ALLOWED_ORIGINS` — not wildcard. If you want to protect the API behind a key, set `API_SECRET_KEY` in `.env` and all `/api/*` requests will require an `X-API-Key` header.
