"""Django portal settings. SQLite is the local default; DATABASE_URL can select PostgreSQL."""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BASE_DIR.parent


def repository_path(value: str | Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else REPOSITORY_ROOT / path).resolve()


DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-development-only-change-before-deploy")
if not DEBUG and SECRET_KEY == "local-development-only-change-before-deploy":
    raise RuntimeError("Set DJANGO_SECRET_KEY before running Django with DJANGO_DEBUG=false.")
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "patents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal_config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "portal_config.wsgi.application"
ASGI_APPLICATION = "portal_config.asgi.application"


def database_from_url(database_url: str | None) -> dict:
    if not database_url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "portal.sqlite3"}

    parsed = urlparse(database_url)
    if parsed.scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
        if os.getenv("DB_SSL_REQUIRED", "false").lower() in {"1", "true", "yes"}:
            config["OPTIONS"] = {"sslmode": "require"}
        return config

    if parsed.scheme == "sqlite":
        name = unquote(parsed.path)
        if name in {"", "/:memory:"}:
            name = ":memory:"
        elif name.startswith("/") and os.name == "nt" and len(name) > 3 and name[2] == ":":
            name = name[1:]
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name or BASE_DIR / "portal.sqlite3"}

    raise ValueError("DATABASE_URL must use sqlite:// or postgresql://")


DATABASES = {"default": database_from_url(os.getenv("DATABASE_URL"))}

AUTH_USER_MODEL = "accounts.PortalUser"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/django-static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = repository_path(os.getenv("PORTAL_MEDIA_ROOT", REPOSITORY_ROOT / "data" / "portal_media"))
MEDIA_URL = "/private-media/"

FASTAPI_PREDICT_URL = os.getenv("FASTAPI_PREDICT_URL", "http://127.0.0.1:8000/predict")
FASTAPI_TIMEOUT_SECONDS = float(os.getenv("FASTAPI_TIMEOUT_SECONDS", "6000"))
FASTAPI_REPORT_ROOT = repository_path(os.getenv("FASTAPI_REPORT_ROOT", REPOSITORY_ROOT / "data" / "reports"))
IDF_MAX_BYTES = int(os.getenv("IDF_MAX_BYTES", str(10 * 1024 * 1024)))

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in {"1", "true", "yes"}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Patent Portal <noreply@example.com>")

LOGIN_URL = "/admin/login/"

# Keep analysis failures visible in the Django terminal during development and
# in the configured process logs in deployment.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "portal": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "portal",
        },
    },
    "loggers": {
        "patents.api": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
