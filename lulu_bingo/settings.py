
# --- PyMySQL auto-enable for MySQL ---
import sys
if 'mysql' in (get_env("DATABASE_URL") or '').lower():
    try:
        import pymysql
        pymysql.install_as_MySQLdb()
    except ImportError:
        print("PyMySQL not installed, but required for MySQL connections.", file=sys.stderr)
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def normalize_origin(origin: str) -> str:
    parsed = urlparse(origin.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return origin.strip()


# --------------------------------------------------
# Core settings
# --------------------------------------------------

SECRET_KEY = get_env("SECRET_KEY", "dev-secret-key-change-me")

ENVIRONMENT = get_env("DJANGO_ENV", "development") or "development"
DEBUG = str_to_bool(get_env("DEBUG"), default=ENVIRONMENT != "production")

ALLOWED_HOSTS = [
    h.strip()
    for h in (get_env("ALLOWED_HOSTS", "*") or "*").split(",")
    if h.strip()
]


# --------------------------------------------------
# CORS
# --------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = str_to_bool(os.getenv("CORS_ALLOW_ALL_ORIGINS"), default=False)
CORS_ALLOWED_ORIGINS = [
    normalize_origin(origin)
    for origin in (get_env("CORS_ALLOWED_ORIGINS", "http://localhost:5173") or "http://localhost:5173").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = str_to_bool(os.getenv("CORS_ALLOW_CREDENTIALS"), default=True)


# --------------------------------------------------
# Applications
# --------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",

    # Local
    "accounts",
    "games",
    "transactions",
]


# --------------------------------------------------
# Middleware
# --------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# --------------------------------------------------
# URLs / WSGI
# --------------------------------------------------

ROOT_URLCONF = "lulu_bingo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "lulu_bingo.wsgi.application"


# --------------------------------------------------
# Database
# --------------------------------------------------


# --- Database: supports PostgreSQL and MySQL via DATABASE_URL ---
database_url = get_env("DATABASE_URL")

if database_url:
    parsed = urlparse(database_url)
    engine = None
    if parsed.scheme in {"postgres", "postgresql"}:
        engine = "django.db.backends.postgresql"
        default_port = 5432
    elif parsed.scheme in {"mysql"}:
        engine = "django.db.backends.mysql"
        default_port = 3306
    else:
        raise ValueError("DATABASE_URL must use a postgres, postgresql, or mysql scheme")

    if not all([parsed.path, parsed.username, parsed.hostname]):
        raise ValueError("DATABASE_URL is missing required connection parts")

    DATABASES = {
        'default': {
            'ENGINE': engine,
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username,
            'PASSWORD': parsed.password,
            'HOST': parsed.hostname,
            'PORT': parsed.port or default_port,
            'OPTIONS': dict(parse_qsl(parsed.query)),
        }
    }
elif ENVIRONMENT == "production":
    raise ValueError("DATABASE_URL is required in production")
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --------------------------------------------------
# Password validation
# --------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# --------------------------------------------------
# Internationalization
# --------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True


# --------------------------------------------------
# Static files
# --------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# --------------------------------------------------
# Django REST Framework
# --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


SPECTACULAR_SETTINGS = {
    "TITLE": "Lulu Bingo API",
    "DESCRIPTION": (
        "Authentication & shop identity endpoints for Lulu Bingo. "
        "Shops are provisioned by HQ admins only; no self-signup is allowed. "
        "Each shop receives temporary credentials, must change the password on first login, "
        "and can be activated, suspended, or blocked centrally. Tokens issued here secure "
        "all subsequent Bingo operations."
    ),
    "VERSION": "0.1.0",
}


# --------------------------------------------------
# Email
# --------------------------------------------------

EMAIL_HOST = get_env("EMAIL_HOST", "") or ""
EMAIL_PORT = int(get_env("EMAIL_PORT", "587") or "587")
EMAIL_HOST_USER = get_env("EMAIL_HOST_USER", "") or ""
EMAIL_HOST_PASSWORD = get_env("EMAIL_HOST_PASSWORD", "") or ""
EMAIL_HOST_USER = get_env("EMAIL_LOGIN_USER", EMAIL_HOST_USER) or ""
EMAIL_HOST_PASSWORD = get_env("EMAIL_LOGIN_PASSWORD", EMAIL_HOST_PASSWORD) or ""
EMAIL_USE_TLS = str_to_bool(get_env("EMAIL_USE_TLS"), True)
EMAIL_USE_SSL = str_to_bool(get_env("EMAIL_USE_SSL"), False)
EMAIL_TIMEOUT = int(get_env("EMAIL_TIMEOUT", "10") or "10")
EMAIL_FAIL_SILENTLY = str_to_bool(get_env("EMAIL_FAIL_SILENTLY"), True)
EMAIL_RAISE_EXCEPTIONS = str_to_bool(get_env("EMAIL_RAISE_EXCEPTIONS"), False)
EMAIL_SEND_ASYNC = str_to_bool(get_env("EMAIL_SEND_ASYNC"), True)

# Prefer SMTP when host is provided; otherwise fall back to console for local dev.
EMAIL_BACKEND = get_env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
) or ("django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = get_env("DEFAULT_FROM_EMAIL", "noreply@lulubingo.com") or "noreply@lulubingo.com"

# Branded email presentation
BRAND_NAME = get_env("BRAND_NAME", "LULU Bingo") or "LULU Bingo"
BRAND_LOGO_URL = get_env("BRAND_LOGO_URL", "") or ""
APP_BASE_URL = get_env("APP_BASE_URL", "http://localhost:5173") or "http://localhost:5173"


# --------------------------------------------------
# Custom User
# --------------------------------------------------

AUTH_USER_MODEL = "accounts.ShopUser"


# --------------------------------------------------
# Defaults
# --------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
