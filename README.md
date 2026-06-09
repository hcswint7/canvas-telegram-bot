# Canvas → Telegram + Notion Bot

Automated student-responsibility bot: pulls assignments/announcements from Canvas,
syncs them into Notion (with dashboard charts), and pushes **three Telegram briefings
a day**. It's also **two-way** — you can message the bot to run commands.

Runs free in the cloud on **GitHub Actions** (scheduled cron workflows), so it fires
on time even when your laptop is off.

## How it runs

```
GitHub Actions (cloud, free on a public repo)
├── briefings.yml   3 crons/day → python run_briefing.py --mode {morning|midday|evening}
│     morning  → assignment radar + announcements  (+ Notion sync + dashboard charts)
│     midday   → announcements pulse + brain teaser
│     evening  → spaced-rep recall drill + exam prep + "due tomorrow" preview
│
└── bot-poll.yml   every ~5 min → python bot_poll.py --once
      handles /sync /today /week /done /check /quiz /help  (locked to your chat id)
```

`run_briefing.py` and `bot_poll.py` reuse the existing modules
(`fetcher`, `builder`, `exporter`, `spaced_rep_scheduler`, `telegram_utils`).

## Bot commands

| Command | Action |
|---|---|
| `/sync` | Re-fetch Canvas, update Notion + charts, send a fresh radar |
| `/today` | What's due today (plus overdue) |
| `/week` | What's due in the next 7 days |
| `/done <name>` | Mark an assignment **Submitted** in Notion (fuzzy title match) |
| `/check` | Recent Canvas announcements + emails |
| `/quiz` | A brain teaser or active-recall question |
| `/help` | List commands |

## Local use

```powershell
# one-time
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt   # canvasapi, python-dotenv, requests, notion-client

# preview any briefing without sending/writing anything
python run_briefing.py --mode morning --dry-run
python run_briefing.py --mode midday --dry-run
python run_briefing.py --mode evening --dry-run

# handle any pending Telegram commands once, then exit
python bot_poll.py --once
# or run a continuous local listener (instant replies while the PC is on)
python bot_poll.py --loop
```

Local runs read credentials from `.env` (git-ignored). See the variable list below.

## Cloud deploy (GitHub Actions)

1. **Init + push to a PUBLIC repo** (public = unlimited free Actions minutes; the
   code holds no secrets, and `.env` is git-ignored):
   ```powershell
   git init
   git add .
   git commit -m "Canvas bot: cloud cron + two-way Telegram control"
   # create an empty PUBLIC repo on github.com, then:
   git remote add origin https://github.com/<you>/<repo>.git
   git branch -M main
   git push -u origin main
   ```
2. **Add repository secrets** (repo → Settings → Secrets and variables → Actions →
   *New repository secret*) — one per variable below.
3. **Enable workflows** in the Actions tab if prompted, then test each via
   *Run workflow* (workflow_dispatch) before trusting the schedule.

### Required secrets / `.env` variables

| Variable | Used for |
|---|---|
| `CANVAS_API_URL`, `CANVAS_API_TOKEN` | Canvas assignments + announcements |
| `NOTION_TOKEN`, `NOTION_DATABASE_ID` | Tasks (Canvas_API) database sync |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Sending + command auth |
| `NOTION_DASHBOARD_BAR_BLOCK_ID`, `NOTION_DASHBOARD_RADAR_BLOCK_ID` | Dashboard charts |
| `NOTION_COURSES_DB_ID`, `NOTION_SCHEDULE_DB_ID`, `NOTION_EXAMS_DB_ID`, `NOTION_KB_DB_ID` | Study recall + exam prep (see below) |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | `/check` email lookup (optional) |

## Study recall + exam prep (one-time Notion setup)

The evening drill and exam prep need extra Notion databases that don't exist yet:

1. In Notion, create a parent Page, share your integration with it, and put its id in
   `.env` as `NOTION_PARENT_PAGE_ID`.
2. Run `python setup_workspace.py` — it creates **Courses**, **Master Schedule**,
   **Knowledge Base**, and **Exams & Quizzes** databases and prints their ids.
   ⚠️ Check Notion first so you don't create duplicates.
3. Copy the four printed ids into `.env` **and** GitHub secrets
   (`NOTION_COURSES_DB_ID`, `NOTION_SCHEDULE_DB_ID`, `NOTION_KB_DB_ID`, `NOTION_EXAMS_DB_ID`).
4. Add a few Knowledge Base cards (Topic + `Next Review Date`) — an empty KB means the
   evening recall drill stays silent.

## Changing the schedule

Edit the `cron:` lines in `.github/workflows/briefings.yml`. **Cron is UTC.** Current
targets (America/Chicago): morning `0 12 * * *`, midday `30 17 * * *`, evening
`30 0 * * *`. Actual local time shifts ~1h between CDT and CST.

## Caveats

- **Scheduled Actions are best-effort** and can run a few–30 min late under load.
- **Command latency is ~5–15 min** (5-min poll floor). For instant replies, run
  `bot_poll.py --loop` locally, or add a Telegram webhook → serverless trigger later.
- **GitHub disables scheduled workflows after 60 days of repo inactivity** — an
  occasional commit keeps them alive.
- If the **old Antigravity cron** ever fires again you'll get duplicate messages —
  disable it inside Antigravity.
