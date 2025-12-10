import os

# Mock SECRET_KEY for tests BEFORE importing settings to bypass validation
os.environ.setdefault("SECRET_KEY", "django-insecure-test-key-for-unit-tests-only")

from .settings import *  # noqa: F403

# Override Database to use SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Disable S3
USE_S3 = False

# Disable other external services
INFRASTRUCTURE["STORAGE_BACKEND"] = "local"  # noqa: F405
INFRASTRUCTURE["EMAIL_BACKEND_TYPE"] = "mock"  # noqa: F405
INFRASTRUCTURE["PAYMENT_PROVIDER"] = "mock"  # noqa: F405

STRIPE_SECRET_KEY = "sk_test_mock_key"

# Enable SessionAuthentication for tests to support client.force_login()
if "DEFAULT_AUTHENTICATION_CLASSES" in REST_FRAMEWORK:  # noqa: F405
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"].append(  # noqa: F405
        "rest_framework.authentication.SessionAuthentication"
    )
else:
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [  # noqa: F405
        "rest_framework.authentication.SessionAuthentication"
    ]
