# First Manager Setup

Use this command to create the first manager account for the Admin portal.

## Option A: Interactive

From the backend folder:

```bash
python manage.py create_first_manager
```

You will be prompted for:

- username
- full name
- contact email
- contact phone
- password

## Option B: Non-interactive

```bash
python manage.py create_first_manager \
  --username manager1 \
  --name "Main Manager" \
  --email manager@example.com \
  --phone 0911223344 \
  --password "StrongPassword123!"
```

## Notes

- The command prevents accidental duplicate first-manager creation.
- If a manager already exists and you still need another one, add `--force`.
- Created managers are active and staff-enabled by default.
