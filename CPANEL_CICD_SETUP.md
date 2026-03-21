# cPanel CI/CD Setup (Backend - Django)

This deploys the backend automatically from GitHub to cPanel shared hosting whenever you push to `master`.

## 1. What Was Created

- Workflow: `.github/workflows/deploy-cpanel.yml`
- Passenger entry: `passenger_wsgi.py`

## 2. GitHub Secrets (Only 3 Required)

In GitHub repo settings for `LuluBingo_Back_End`:
`Settings -> Secrets and variables -> Actions -> New repository secret`

Create these **exact** names:

- `CPANEL_HOST`
- `CPANEL_USERNAME`
- `CPANEL_PASSWORD`

### Fill This Table

| Secret Name     | What to put                   | Example                |
| --------------- | ----------------------------- | ---------------------- |
| CPANEL_HOST     | FTP/FTPS hostname from cPanel | `ftp.yourdomain.com`   |
| CPANEL_USERNAME | cPanel account username       | `lulubingo`            |
| CPANEL_PASSWORD | cPanel account password       | `your-cpanel-password` |

## 3. cPanel First-Time Python App Setup (One-Time)

1. In cPanel, open **Setup Python App**.
2. Create app with:
   - Python version: `3.11` (or closest available)
   - Application root: your API subdomain root folder (for example `apiludisbingo`)
   - Application URL: your backend URL/subdomain
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`
3. Save/Create.

## 4. Server-Side First-Time Commands (One-Time)

Run in cPanel Terminal (or SSH if available):

```bash
cd ~/apiludisbingo
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## 5. Required Backend `.env` on Server

Create and keep this file on server only:

`/home/<CPANEL_USERNAME>/apiludisbingo/.env`

Minimum fields to set:

```env
DJANGO_ENV=production
DEBUG=False
SECRET_KEY=YOUR_LONG_RANDOM_SECRET
ALLOWED_HOSTS=your-api-domain.com,www.your-api-domain.com
DATABASE_URL=YOUR_DATABASE_URL
```

Notes:

- Do not commit `.env` to GitHub.
- Workflow is already configured to skip deploying local `.env`.

## 6. How Deploy Works

- Trigger: push to `master`
- Upload target: FTP root `./` (your API subdomain root)
- Protocol: `ftp` on port `21` (set in workflow for better compatibility on some cPanel shared hosts)
- Auto restart signal: workflow updates `tmp/restart.txt`

If your provider requires FTPS, switch workflow `protocol` from `ftp` to `ftps`.

## 6.1 Admin CSS/JS (Important)

If Django admin appears without styles/scripts, run:

```bash
cd ~/apiludisbingo
python manage.py collectstatic --noinput
```

This project is configured with WhiteNoise, so static files (including admin CSS/JS) are served by Django when `DEBUG=False`.

## 7. Verify Deployment

1. In GitHub Actions, confirm workflow passed.
2. In browser, open your API health endpoint (or `/api/schema/`).
3. In cPanel Python App UI, click **Restart** if needed.

## 8. If Deploy Fails

- Wrong host: update `CPANEL_HOST`.
- Login denied: verify `CPANEL_USERNAME` and `CPANEL_PASSWORD`.
- 500 error: check cPanel error logs and validate server `.env`.
- Missing packages: rerun `pip install -r requirements.txt` in app root.
- If you see `Server sent FIN packet unexpectedly`, keep the current workflow setup (direct FTP sync + excludes). If your host explicitly requires FTPS, change protocol to `ftps` and retry.

## 9. Fix `RecursionError` in `passenger_wsgi.py`

If stderr shows repeated lines like `wsgi = load_source('wsgi', 'passenger_wsgi.py')`, the server is using an old recursive startup file.

Run this in cPanel Terminal:

```bash
cd ~/apiludisbingo
cat > passenger_wsgi.py << 'PYEOF'
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
   sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lulu_bingo.settings")

from lulu_bingo.wsgi import application
PYEOF
```

Then restart app and verify:

```bash
touch tmp/restart.txt
python -c "import passenger_wsgi; print('passenger_wsgi ok')"
```

Expected output:

```text
passenger_wsgi ok
```
