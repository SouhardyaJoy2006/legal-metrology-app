# Legal Metrology App

A Flask web application that helps enforcement officers and suppliers check whether packaged-product labels comply with India's Legal Metrology (Packaged Commodities) Rules, 2011 and the Legal Metrology Rules, 2009. Officers upload a photo of a product and its label, and the app runs an AI pipeline to classify the product category, extract the label's declarations, and flag any missing mandatory fields.

## Features

- **Role-based accounts** — Supplier, Enforcement Officer, and Developer roles, each with their own dashboard.
- **AI compliance pipeline** (`ai_services.py`) — classifies the product photo (CLIP, with a Gemini vision fallback) and extracts label declarations (Gemini), then checks them against category-specific rules (`standards.py`).
- **Compliance reports** — each scan is marked Compliant / Non-Compliant, with a downloadable PDF report and the ability to re-run analysis.
- **BIS Standards Recommendation Engine** — a standalone `/bis_standards` page and `/api/standards/search` endpoint for hybrid semantic search over BIS standards.
- **Hidden developer gateway** (`/sih_hidden_gateway`) — PIN-protected route for provisioning developer/admin accounts.
- **Deployable to Vercel** — with Turso (libSQL) for the database and Vercel Blob for persistent image storage; falls back to local SQLite and local disk storage for development.

## Tech Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Jinja, django
- **Database:** SQLite (local) or Turso/libSQL (Vercel)
- **AI:** CLIP (product classification), Google Gemini (label extraction), pgvector-backed retrieval for BIS standards
- **PDF generation:** fpdf
- **Frontend:** HTML, CSS with Bootstrap 5

## Project Structure

```
legal-metrology-app-main/
├── main.py                  # Flask app: routes, models, auth, upload/scan workflow
├── form.py                  # WTForms form definitions
├── ai_services.py           # AI pipeline: classification + label extraction + compliance check
├── standards.py             # Legal Metrology / Cosmetics Rules field definitions
├── api/
│   └── index.py             # Vercel serverless entrypoint (imports `app` from main.py)
├── templates/                # Jinja2 templates (dashboards, forms, reports, etc.)
├── static/
│   ├── css/style.css
│   └── scanned_labels/       # Uploaded label/product images (local dev)
├── requirements.txt          # Vercel deployment dependencies (no CLIP/torch)
├── requirements-full.txt     # Full local/dev dependencies (includes CLIP/torch)
├── vercel.json                # Vercel routing/build config
├── DEPLOY_VERCEL.md           # Vercel deployment guide
└── PS_108/                    # BIS Standards RAG engine (see its own contents separately)
```

> **Note:** The `PS_108/` directory contains a separate BIS Standards RAG (retrieval-augmented generation) subsystem, imported by `main.py` for the `/bis_standards` and `/api/standards/search` routes. Its internal contents are not detailed in this README.

## Getting Started

### 1. Install dependencies

For local development with full AI category classification:

```bash
pip install -r requirements-full.txt
```

For a lighter install without CLIP/torch (label extraction via Gemini still works):

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```
SECRET_KEY=<random string>
GEMINI_API_KEY=<your Gemini API key>
DEVELOPER_EMAILS=dev1@example.com,dev2@example.com
DEV_PIN=<a pin of your choice>
```

Optional (for Vercel/production persistence — see `DEPLOY_VERCEL.md`):

```
TURSO_DATABASE_URL=libsql://<db>-<org>.turso.io
TURSO_AUTH_TOKEN=<token>
BLOB_READ_WRITE_TOKEN=<vercel blob token>
```

Optional (for the BIS Standards Engine, `PS_108/`):

```
POSTGRES_HOST=...
POSTGRES_PORT=...
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...
```

### 3. Run the app

```bash
python main.py
```

The app will be available at `http://localhost:5000`, with a local SQLite database (`metrology.db`) created automatically on first run.

## Key Routes

| Route | Description |
|---|---|
| `/` | Home — redirects to the appropriate dashboard once logged in |
| `/sign_up`, `/login`, `/logout` | Authentication |
| `/supplier/dashboard` | Supplier's view of their submitted scans |
| `/officer/dashboard` | Officer's view of scans they've uploaded |
| `/officer/upload` | Upload a label + product image and run the compliance check |
| `/officer/scan/<id>` | View a scan's compliance report |
| `/officer/scan/<id>/rerun` | Re-run AI analysis on an existing scan |
| `/scan/<id>/download_pdf` | Download a scan's compliance report as PDF |
| `/developer/dashboard` | Developer/admin overview of users and scans |
| `/delete_account` | Permanently delete the current user's account and data |
| `/sih_hidden_gateway` | PIN-protected developer account provisioning |
| `/bis_standards` | BIS Standards Recommendation Engine page |
| `/api/standards/search` | REST API for hybrid semantic search over BIS standards |

## Deployment

See [`DEPLOY_VERCEL.md`](./DEPLOY_VERCEL.md) for full instructions on deploying to Vercel with Turso and Vercel Blob.

## License

Not specified.
