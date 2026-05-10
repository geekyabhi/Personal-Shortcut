# Personal Shortcut

A personal Django web app that pulls data from Notion databases and renders dashboards for **Expenses** and **Habits** tracking.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 4.2, Python 3.11 |
| Data source | Notion API (Internal Integration) |
| Frontend | Vanilla JS + Chart.js 4.4 |
| Deployment | Railway (gunicorn via Procfile) |
| No database | All data lives in Notion; Django has no DB |

---

## Project Structure

```
Personal Shortcut/
├── core/
│   ├── settings.py          # Django settings (no DB, no CSRF middleware)
│   ├── urls.py              # Root router: /, /expenses/, /habits/
│   ├── wsgi.py
│   └── templates/
│       └── home.html        # Landing page with tile links to each app
│
├── expenses/
│   ├── views.py             # All expense logic + Notion API calls
│   ├── urls.py
│   └── templates/expenses/
│       ├── dashboard.html   # Summary + trend chart + breakdown
│       └── charts.html      # Line + bar + donut charts
│
├── habits/
│   ├── views.py             # All habits logic + Notion API calls
│   ├── urls.py
│   └── templates/habits/
│       ├── dashboard.html   # Stats + per-habit completion list
│       └── charts.html      # Score trend + binary heatmap grid + days-done bar
│
├── script.py                # One-off backfill script (run locally)
├── manage.py
├── requirements.txt         # Django, gunicorn, requests, python-dotenv
├── Procfile                 # web: gunicorn core.wsgi --bind 0.0.0.0:$PORT
└── runtime.txt              # python-3.11.9
```

---

## Environment Variables

Stored in `.env` locally (never committed). Set as Railway Variables in production.

| Variable | Used by |
|---|---|
| `NOTION_TOKEN` | Both apps — Notion Internal Integration token |
| `NOTION_EXPENSES_DB_ID` | Expenses app — 32-char Notion database ID |
| `NOTION_HABITS_DB_ID` | Habits app — 32-char Notion database ID |
| `SECRET_KEY` | Django |
| `DEBUG` | `True` locally, `False` in production |

Load locally:
```bash
export $(cat .env | xargs)
python manage.py runserver
```

---

## URL Map

| URL | View | Description |
|---|---|---|
| `/` | `core.urls.home` | Landing page |
| `/expenses/` | `DashboardView` | Expenses summary dashboard |
| `/expenses/charts/` | `ChartsView` | Expenses charts page |
| `/expenses/summary/` | `ExpensesSummaryView` | JSON: totals + group breakdown |
| `/expenses/chart/` | `ExpensesChartView` | JSON: trend + breakdown (used by both pages) |
| `/expenses/timeseries/` | `ExpensesTimeseriesView` | JSON: time-series only |
| `/habits/` | `DashboardView` | Habits summary dashboard |
| `/habits/charts/` | `ChartsView` | Habits charts page |
| `/habits/summary/` | `HabitsSummaryView` | JSON: per-habit stats |
| `/habits/chart/` | `HabitsChartView` | JSON: score trend + binary grid + counts |
| `/habits/backfill/` | `BackfillView` | POST: create missing Notion entries for current year |

---

## Period / Date Filtering

All API endpoints accept a `period` query param. Both apps support the same set:

| `period` | Extra params | Notes |
|---|---|---|
| `all` | — | No date filter |
| `yearly` | `year=YYYY` | Defaults to current year |
| `monthly` | `month=YYYY-MM` | Defaults to current month |
| `weekly` | `week=YYYY-Www` | Defaults to current week |
| `daily` | `day=YYYY-MM-DD` | Defaults to today |
| `custom` | `start=YYYY-MM-DD&end=YYYY-MM-DD` | Inclusive on both ends |

The UI also exposes preset buttons for custom: **Last 7 days**, **Last 30 days**, **Last 3 months**, **Last 6 months**, **Year to date**.

---

## Expenses App

**Notion database required properties:**

| Property | Type |
|---|---|
| `Expense` | Title |
| `Date` | Date |
| `Amount` | Number |
| `Category` | Multi-select |
| `Source` | Select or Multi-select |

**Group-by:** pass `group_by=category` or `group_by=source` to any endpoint to get a breakdown.

**Chart logic (`_build_timeseries`):**
- `daily` → single bar
- `weekly` / `monthly` → one bar per day
- `yearly` → one bar per month (12 fixed buckets)
- `all` → one bar per month (dynamic from data)
- `custom` ≤60 days → one bar per day; >60 days → one bar per month

---

## Habits App

**Notion database required properties:**

| Property | Type |
|---|---|
| `Date` | Date |
| `Score` | Formula (number, 0–100) |
| *(any checkbox)* | Checkbox — auto-detected as habits |

All checkbox properties are treated as habits. Their names come from the Notion schema automatically — no hardcoding needed.

**Key views:**

- `HabitsSummaryView` — per-habit done/total/rate for any period
- `HabitsChartView` — returns:
  - `score_trend`: bucketed score over time (daily/monthly depending on range)
  - `habit_grid`: binary per-day grid (1=done, 0=not done, null=no entry) — only returned for ranges ≤60 days
  - `habit_counts`: integer days-done per habit (used for bar chart, max=total_days)
- `BackfillView` (POST `/habits/backfill/`) — finds all dates from Jan 1 of the current year to today that have no Notion entry and creates them

**`script.py`** does the same backfill but as a standalone script using hardcoded credentials — useful for one-off runs without the server.

---

## Key Design Decisions

- **No Django ORM / database** — settings has no `DATABASES` key; all data is fetched live from Notion on each request.
- **No CSRF middleware** — `settings.py` only has `SecurityMiddleware` and `CommonMiddleware`, so POST endpoints (backfill) work from plain `fetch()` calls without tokens.
- **Templates use `APP_DIRS: False`** with explicit `DIRS` pointing to each app's template folder.
- **Chart.js served from CDN** — no build step, no bundler.
- **`_common_fetch` helper** in `habits/views.py` centralises validation + Notion fetching into one shared function used by all habits views.
- **Binary habit data** — the heatmap grid treats each habit per day as strictly done (1) or not done (0); percentages only appear in the summary dashboard, not the charts page.

---

## Local Development

```bash
# 1. Install deps (ideally in a venv)
pip install -r requirements.txt

# 2. Load env vars
export $(cat .env | xargs)

# 3. Run
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`

---

## Deployment (Railway)

The app is deployed on Railway. `Procfile` runs gunicorn:

```
web: gunicorn core.wsgi --bind 0.0.0.0:$PORT
```

Railway injects `PORT` automatically. Set all env vars in the Railway dashboard under **Variables**.
