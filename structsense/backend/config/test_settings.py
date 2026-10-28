"""Test-only settings. Uses SQLite so the structsense PostgreSQL role does not
need CREATEDB privilege. All other settings are inherited from the production
settings module; only the DATABASES entry is replaced.
"""
# Import everything from the normal settings file first.
from config.settings import *  # noqa: F401, F403

import os
from pathlib import Path

# Override DATABASES for the test runner: use an in-memory SQLite database.
# This keeps production on PostgreSQL while allowing `manage.py test` to run
# without needing CREATEDB on the structsense role.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Use :memory: for the fastest possible test run.
        "NAME": ":memory:",
    }
}

# Disable the STRUCTSENSE_REQUIRE_POSTGRESQL guard during testing.
# (The production setting is already applied by the import above; we just
#  override DATABASES so the test runner never tries to CREATE DATABASE.)
