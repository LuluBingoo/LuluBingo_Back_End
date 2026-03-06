# LuluBingo Back End

A Django + Django REST Framework API for managing shop accounts, bingo game logic, and wallet transactions.

## Prerequisites

- Python 3.11+
- Git
- (Optional) virtualenv/venv

## Quickstart

```bash
# clone
git clone https://github.com/LuluBingoo/LuluBingo_Back_End.git
cd LuluBingo_Back_End

# create & activate venv (Windows PowerShell)
python -m venv env
./env/Scripts/Activate.ps1

# install deps
pip install -r requirements.txt

# copy env template and edit values
copy .env.example .env
# update SECRET_KEY, DB settings (defaults use SQLite), and email/TOTP settings if needed

# apply migrations
python manage.py migrate

# create a superuser for admin access
python manage.py createsuperuser

# run server
python manage.py runserver
```

## Environment

Key variables in `.env` (or your environment):

- `SECRET_KEY`: Django secret key (required)
- `DEBUG`: `True`/`False`
- `ALLOWED_HOSTS`: comma-separated hosts
- `DATABASE_URL`: optional; defaults to SQLite if omitted (e.g., `postgres://user:pass@host:5432/db`)
- `DEFAULT_FROM_EMAIL`: sender address used by the app. Default is `noreply@lulubingo.com`
- `EMAIL_HOST`: SMTP host such as `smtp.gmail.com`
- `EMAIL_PORT`: SMTP port, usually `587` for TLS
- `EMAIL_HOST_USER`: SMTP username/login
- `EMAIL_HOST_PASSWORD`: SMTP password or app password
- `EMAIL_USE_TLS`: `True` for TLS with Gmail/most providers
- `EMAIL_FAIL_SILENTLY`: keep as `True` in development so login never breaks if email setup is wrong

## Email Setup

1. Create the env file:

```bash
copy .env.example .env
```

2. Edit `.env` and set the sender to:

```env
DEFAULT_FROM_EMAIL=noreply@lulubingo.com
```

3. Fill your SMTP details. Example for Gmail SMTP:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-smtp-login@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_LOGIN_USER=your-real-mailbox@gmail.com
EMAIL_LOGIN_PASSWORD=your-app-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_FAIL_SILENTLY=True
DEFAULT_FROM_EMAIL=noreply@lulubingo.com
```

4. Restart the Django server after editing `.env`.

Notes:

- If you use Gmail, you need an App Password, not your normal account password.
- `EMAIL_LOGIN_USER` must be the real mailbox that owns the app password.
- `DEFAULT_FROM_EMAIL` is the visible sender address. It can be `noreply@lulubingo.com`, but your provider must allow that sender or verified alias/domain.
- The visible sender address is configured by `DEFAULT_FROM_EMAIL`, but some providers only allow sending from verified domains or verified mailboxes.
- If your provider rejects `noreply@lulubingo.com`, use a verified mailbox first and later switch to your domain after DNS/domain verification.

## Apps & Features

- `accounts`: shop auth, TOTP 2FA, wallet balance, bank details, login attempts.
- `games`: shop-scoped game creation, per-cartella draw sequences, status updates, and a public multi-cartella lookup endpoint.
- `transactions`: deposits/withdrawals and history with balance tracking.

## API Notes

- Auth: Token auth (login endpoint under `api/` from accounts app).
- Games: routes under `/api/games/`.
- Public cartella lookup: `POST /api/games/game/cartellas/check`

```json
{
  "game_id": "GAME1234",
  "cartella_numbers": [1, 5, 12]
}
```

- Public lookup response returns the matching cartellas in `cartellas`, any unknown numbers in `missing_cartella_numbers`, and the shared `called_numbers` list for that game.
- Legacy single-cartella GET is still available at `/api/games/game/<game_id>/cartella/<cartella_number>` for compatibility.
- Transactions: routes under `/api/transactions/` for deposits, withdrawals, and history.
- OpenAPI/Swagger: `/api/schema/` and `/api/docs/`.

## Running Tests

```bash
python manage.py test
```

## Admin

After creating a superuser, visit `/admin/` for ShopUser, Game, and Transaction management.

## Common Tasks

- Regenerate migrations (if you change models):

```bash
python manage.py makemigrations
python manage.py migrate
```

- Load dev server on a custom port:

```bash
python manage.py runserver 0.0.0.0:8000
```

## Troubleshooting

- Missing deps: `pip install -r requirements.txt`
- DB issues: verify `DATABASE_URL` or delete `db.sqlite3` for a fresh local DB (dev only).
- Auth errors: ensure you log in via the login endpoint to get a token, and include `Authorization: Token <token>` in requests.
