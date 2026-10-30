"""Environment contract for the single-host Compose deployment."""

import json
import os
from pathlib import Path


def secret(name, default=""):
    file = os.getenv(name + "_FILE")
    return Path(file).read_text(encoding="utf-8").strip() if file else os.getenv(name, default)


def settings():
    bindings = os.getenv("ADMIN_ROLE_BINDINGS_FILE")
    return {
        "ADMIN_AUTH": os.getenv("ADMIN_AUTH", "cloudflare"),
        "CF_ACCESS_ISSUER": os.getenv("CF_ACCESS_ISSUER", ""),
        "CF_ACCESS_AUD": os.getenv("CF_ACCESS_AUD", ""),
        "ADMIN_PUBLIC_ORIGIN": os.getenv("ADMIN_PUBLIC_ORIGIN", ""),
        "ADMIN_ROLE_BINDINGS": json.loads(Path(bindings).read_text()) if bindings else {},
        "ADMIN_METRICS_TOKEN": secret("ADMIN_METRICS_TOKEN"),
    }


def make_store():
    from .store import Store

    return Store(
        Path(os.getenv("ADMIN_PROJECT_ROOT", "/app")), Path(os.getenv("ADMIN_DATA_ROOT", "/data"))
    )
