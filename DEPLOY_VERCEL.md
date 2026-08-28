# Deploying `Integration/` to Vercel

No application logic was changed. Only deployment config was added/adjusted:

| File | What changed |
|---|---|
| `api/index.py` | **New.** Vercel's Python runtime entrypoint — imports the existing `app` from `main.py`. |
| `vercel.json` | **New.** Routes all requests to `api/index.py`. |
| `main.py` | DB URI and upload folder now read from env vars, defaulting to the original SQLite/local-disk behavior when those vars aren't set. |
| `requirements.txt` | Removed `torch`/`torchvision`/CLIP (too large for Vercel's function size limit). `ai_services.py` already catches missing CLIP and degrades gracefully — Gemini label extraction still works, AI category classification is skipped. Added `sqlalchemy-libsql` (the SQLAlchemy dialect for Turso). |
| `requirements-full.txt` | **New.** Copy of the original full requirements (with CLIP) for local development. |

## Persistent images (Vercel Blob)

Uploaded label/product images are pushed to Vercel Blob storage so they persist and display correctly on the compliance report page. To enable it:

1. In your Vercel project → **Storage** tab → **Create Database** → **Blob**.
2. Connect it to this project. Vercel automatically adds a `BLOB_READ_WRITE_TOKEN` environment variable — no manual setup needed.
3. Redeploy (or it'll pick it up on the next deploy automatically).

If you skip this, the app still works exactly as before (images just won't persist between requests, as originally discussed).

## Category classification (CLIP → Gemini fallback)

Since CLIP/torch aren't installed on Vercel, `classify_category()` now automatically falls back to a Gemini vision call to predict the category (edible/electronic/cosmetic) whenever CLIP isn't available. This only requires the `GEMINI_API_KEY` you're already setting — no extra config.

## Steps

1. **Get a Turso database**:
   ```bash
   curl -sSfL https://get.tur.so/install.sh | bash   # install Turso CLI
   turso auth login
   turso db create metrology-db
   turso db show --url metrology-db        # -> TURSO_DATABASE_URL, looks like libsql://metrology-db-<org>.turso.io
   turso db tokens create metrology-db     # -> TURSO_AUTH_TOKEN
   ```

2. **Push this folder to GitHub** (or import directly) and in Vercel:
   - New Project → Import your repo.
   - **Root Directory**: set to `Integration` (since that's where `vercel.json`/`api/` live).
   - Framework Preset: "Other".

3. **Set Environment Variables** in Vercel project settings:
   ```
   SECRET_KEY=<random string>
   TURSO_DATABASE_URL=libsql://metrology-db-<your-org>.turso.io
   TURSO_AUTH_TOKEN=<token from `turso db tokens create`>
   GEMINI_API_KEY=<your Gemini key>
   DEVELOPER_EMAILS=dev1@example.com,dev2@example.com,dev3@example.com,dev4@example.com,dev5@example.com,dev6@example.com
   DEV_PIN=<a pin of your choice>
   ```

4. **Deploy.** Vercel auto-sets `VERCEL=1` at runtime, which is what triggers the `/tmp` upload-folder path in `main.py`. `main.py` switches to Turso automatically whenever both `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are set — locally, if you leave them unset, it keeps using the plain SQLite file exactly as before.

5. First request will run `db.create_all()` against your Turso DB, creating the `users` and `label_scans` tables automatically.
