import os
import sys

# Keep project root importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lulu_bingo.settings")

from lulu_bingo.wsgi import application  # noqa: E402
