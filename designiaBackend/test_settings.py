from .settings import *  # noqa: F403, F405

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

# Ensure Feature Flags are set for tests (using new architecture)
FEATURE_FLAGS["USE_SERVICE_LAYER_PRODUCTS"] = True  # noqa: F405
FEATURE_FLAGS["USE_SERVICE_LAYER_MARKETPLACE"] = True  # noqa: F405
FEATURE_FLAGS["USE_SERVICE_LAYER_CART"] = True  # noqa: F405
FEATURE_FLAGS["USE_SERVICE_LAYER_ORDERS"] = True  # noqa: F405
