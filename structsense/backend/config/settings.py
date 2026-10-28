"""Django web/data service settings. SQLite is for local development only."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
CORE_DIR = BASE_DIR.parent
try:
    from dotenv import load_dotenv
    load_dotenv(CORE_DIR / ".env")
except ImportError:
    pass
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in the environment before starting Django")
SECRET_KEY = SECRET_KEY or "local-development-only-insecure-key"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
                  "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
                  "rest_framework", "webdata"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
              "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
              "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates", "DIRS":[], "APP_DIRS":True,
              "OPTIONS":{"context_processors":["django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
              "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
database_url = os.environ.get("DATABASE_URL", "")
require_postgresql = os.environ.get("STRUCTSENSE_REQUIRE_POSTGRESQL", "false").lower() in ("1", "true", "yes", "on")
# STRUCTSENSE_TEST_USE_SQLITE=true lets the test runner use a local SQLite
# file so the structsense PostgreSQL role does not need CREATEDB privilege.
_test_use_sqlite = os.environ.get("STRUCTSENSE_TEST_USE_SQLITE", "false").lower() in ("1", "true", "yes", "on")
if database_url.startswith(("postgres://", "postgresql://")):
    parsed = urlparse(database_url)
    if not parsed.path.strip("/"):
        raise ImproperlyConfigured("DATABASE_URL must include a PostgreSQL database name")
    _pg = {"ENGINE":"django.db.backends.postgresql", "NAME":parsed.path.lstrip("/"),
        "USER":parsed.username or "", "PASSWORD":parsed.password or "", "HOST":parsed.hostname or "localhost", "PORT":parsed.port or 5432}
    if _test_use_sqlite:
        # Tests use a local SQLite file; production stays on PostgreSQL.
        _pg["TEST"] = {"ENGINE": "django.db.backends.sqlite3",
                       "NAME": str(BASE_DIR / "test_structsense.sqlite3")}
    else:
        # Provide a fixed test-database name so Django does not need to CREATE
        # DATABASE. A PostgreSQL superuser must run once:
        #   CREATE DATABASE structsense_test OWNER structsense;
        _pg["TEST"] = {"NAME": "structsense_test"}
    DATABASES = {"default": _pg}
elif database_url:
    raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL URL, or blank to explicitly use local SQLite")
elif require_postgresql:
    raise ImproperlyConfigured("STRUCTSENSE_REQUIRE_POSTGRESQL is enabled, but DATABASE_URL is missing")
else:
    DATABASES = {"default":{"ENGINE":"django.db.backends.sqlite3", "NAME":os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))}}
AUTH_PASSWORD_VALIDATORS = [{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
                            {"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"}]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "").strip() or str(BASE_DIR / "private_uploads"))
MEDIA_URL = "/private-media/"  # never wired to a public static file server
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
REST_FRAMEWORK = {"DEFAULT_PERMISSION_CLASSES":["rest_framework.permissions.IsAuthenticated"],
                  "DEFAULT_AUTHENTICATION_CLASSES":["rest_framework.authentication.SessionAuthentication",
                                                      "rest_framework.authentication.BasicAuthentication"]}
LOGIN_REDIRECT_URL = "/"
