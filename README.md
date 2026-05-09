# Notion Expenses API

A Django REST API that fetches and aggregates expense data from a Notion database.

## Endpoint

```
GET /expenses/summary/
```

**Response:**
```json
{
  "month": "2026-05",
  "grand_total": 1234.56,
  "summary": [
    { "category": "Food", "total": 450.00 },
    { "category": "Transport", "total": 120.50 }
  ]
}
```

---

## Local Setup

### 1. Clone and create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your actual values
```

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Internal Integration Token from Notion (starts with `secret_`) |
| `NOTION_EXPENSES_DB_ID` | The 32-char ID from your Notion database URL |
| `SECRET_KEY` | Any long random string for Django |
| `DEBUG` | `True` for local development, `False` in production |

### 3. Run the development server

```bash
export $(cat .env | xargs)      # load env vars (macOS/Linux)
python manage.py runserver
```

Visit: http://127.0.0.1:8000/expenses/summary/

---

## Railway Deployment

### 1. Install the Railway CLI (optional)

```bash
npm install -g @railway/cli
railway login
```

### 2. Create a new project and deploy

```bash
railway init          # creates a new project
railway up            # deploys the current directory
```

Or connect via the Railway dashboard by linking your GitHub repo.

### 3. Set environment variables in Railway

In your Railway project → **Variables**, add:

- `NOTION_TOKEN`
- `NOTION_EXPENSES_DB_ID`
- `SECRET_KEY`
- `DEBUG` = `False`

Railway automatically injects `PORT`; the `Procfile` binds gunicorn to it.

### 4. Verify the deploy

```
https://<your-app>.railway.app/expenses/summary/
```

---

## Notion Setup

1. Go to [Notion Integrations](https://www.notion.so/my-integrations) and create an **Internal Integration**.
2. Copy the **Internal Integration Token** → `NOTION_TOKEN`.
3. Open your expenses database in Notion. The URL contains the database ID:
   `https://www.notion.so/{workspace}/{DATABASE_ID}?v=...`
   Copy the 32-char segment → `NOTION_EXPENSES_DB_ID`.
4. In your database page, click **...** → **Add connections** and add your integration.

### Required database properties

| Property | Type |
|----------|------|
| `Expense` | Title |
| `Date` | Date |
| `Amount` | Number |
| `Category` | Multi-select |
