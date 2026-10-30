"""Environment contract for the single-host Compose deployment."""

import json
import os
from pathlib import Path


def secret(name, default=""):
    file = os.getenv(name + "_FILE")
    return Path(file).read_text(encoding="utf-8").strip() if file else os.getenv(name, default)


def role_bindings():
    """Access subject -> roles, from a file or as JSON from the environment.

    srv01 passes everything through the stack's .env; a file would need a
    mount that exists nowhere else in the stack. Both at once is refused, so
    nobody edits the one that is not read.
    """
    path, value = os.getenv("ADMIN_ROLE_BINDINGS_FILE"), os.getenv("ADMIN_ROLE_BINDINGS")
    if path and value:
        raise ValueError("ADMIN_ROLE_BINDINGS oder ADMIN_ROLE_BINDINGS_FILE, nur eines")
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(value) if value else {}


def settings():
    return {
        "ADMIN_AUTH": os.getenv("ADMIN_AUTH", "cloudflare"),
        "CF_ACCESS_ISSUER": os.getenv("CF_ACCESS_ISSUER", ""),
        "CF_ACCESS_AUD": os.getenv("CF_ACCESS_AUD", ""),
        "ADMIN_PUBLIC_ORIGIN": os.getenv("ADMIN_PUBLIC_ORIGIN", ""),
        "ADMIN_ROLE_BINDINGS": role_bindings(),
        "ADMIN_METRICS_TOKEN": secret("ADMIN_METRICS_TOKEN"),
    }


def make_store():
    from .store import Store

    return Store(
        Path(os.getenv("ADMIN_PROJECT_ROOT", "/app")), Path(os.getenv("ADMIN_DATA_ROOT", "/data"))
    )
