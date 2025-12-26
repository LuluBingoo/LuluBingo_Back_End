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

## Apps & Features

- `accounts`: shop auth, TOTP 2FA, wallet balance, bank details, login attempts.
- `games`: shop-scoped game creation, per-cartella draw sequences, status updates, public cartella draw endpoint.
- `transactions`: deposits/withdrawals and history with balance tracking.

## API Notes

- Auth: Token auth (login endpoint under `api/` from accounts app).
- Games: routes under `/api/games/`. Public cartella draw: `/api/games/games/<code>/cartellas/<n>/draw`.
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
