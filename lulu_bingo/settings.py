import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qsl

# --------------------------------------------------
# Base
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------
# Core settings
# --------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

ENVIRONMENT = os.getenv("DJANGO_ENV", "development")
DEBUG = str_to_bool(os.getenv("DEBUG"), default=ENVIRONMENT != "production")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]


# --------------------------------------------------
# CORS
# --------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = str_to_bool(os.getenv("CORS_ALLOW_ALL_ORIGINS"), default=False)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
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

if ENVIRONMENT == "production":
    required = ["DATABASE_URL"]
    missing = [key for key in required if not os.getenv(key)]
    
    if missing:
        raise ValueError(
            f"Missing database env vars for production: {', '.join(missing)}"
        )
    
    tmpPostgres = urlparse(os.getenv("DATABASE_URL"))

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': tmpPostgres.path.replace('/', ''),
            'USER': tmpPostgres.username,
            'PASSWORD': tmpPostgres.password,
            'HOST': tmpPostgres.hostname,
            'PORT': 5432,
            'OPTIONS': dict(parse_qsl(tmpPostgres.query)),
        }
    }
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

STATIC_URL = "static/"


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
    "TITLE": "Dallol Bingo API",
    "DESCRIPTION": (
        "Authentication & shop identity endpoints for Dallol Bingo. "
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

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = str_to_bool(os.getenv("EMAIL_USE_TLS"), True)
EMAIL_USE_SSL = str_to_bool(os.getenv("EMAIL_USE_SSL"), False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))
EMAIL_FAIL_SILENTLY = str_to_bool(os.getenv("EMAIL_FAIL_SILENTLY"), False)

# Prefer SMTP when host is provided; otherwise fall back to console for local dev.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@lulu-bingo.local")

# Branded email presentation
BRAND_NAME = os.getenv("BRAND_NAME", "LULU Bingo")
BRAND_LOGO_URL = os.getenv("BRAND_LOGO_URL", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")


# --------------------------------------------------
# Custom User
# --------------------------------------------------

AUTH_USER_MODEL = "accounts.ShopUser"


# --------------------------------------------------
# Defaults
# --------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
