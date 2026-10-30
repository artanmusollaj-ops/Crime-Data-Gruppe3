"""Fail-closed Cloudflare Access JWT authentication and server-side RBAC."""

import hmac
from urllib.parse import urlsplit

from flask import abort, g, request

ROLES = {"viewer", "engineer", "reviewer", "operator", "release_manager"}
WRITE_ROLES = {
    "/api/review-claim": {"reviewer"},
    "/api/review-release": {"reviewer"},
    "/api/review-read": ROLES,
    "/api/mapping": {"engineer"},
    "/api/settings": {"engineer"},
    "/api/rebase": {"engineer"},
    "/api/impact-retry": {"engineer"},
    "/api/decision": {"reviewer"},
    "/api/publish-approved": {"reviewer"},
    "/api/job": {"operator"},
    "/api/git-open": {"engineer"},
    "/api/git-merge": {"release_manager"},
    "/api/git-withdraw": {"reviewer"},
    "/api/archive-retry": {"engineer", "operator"},
    "/api/backup": {"operator"},
    "/api/serving": {"operator"},
}


def install_auth(app, operator, token):
    mode = app.config["ADMIN_AUTH"]
    verifier = None
    if mode == "cloudflare":
        import jwt

        issuer = app.config["CF_ACCESS_ISSUER"].rstrip("/")
        url = urlsplit(issuer)
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(".cloudflareaccess.com")
            or url.path
            or url.query
            or url.fragment
            or url.port
        ):
            raise ValueError("CF_ACCESS_ISSUER muss die HTTPS-Teamdomain sein")
        if not app.config["CF_ACCESS_AUD"] or not app.config["ADMIN_PUBLIC_ORIGIN"].startswith(
            "https://"
        ):
            raise ValueError("Access AUD und HTTPS ADMIN_PUBLIC_ORIGIN erforderlich")
        app.config["TRUSTED_HOSTS"] = [
            urlsplit(app.config["ADMIN_PUBLIC_ORIGIN"]).hostname,
            "admin",
        ]
        client = jwt.PyJWKClient(issuer + "/cdn-cgi/access/certs", timeout=10)

        def verifier(raw):
            return jwt.decode(
                raw,
                client.get_signing_key_from_jwt(raw).key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=app.config["CF_ACCESS_AUD"],
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )

        # Inject a verifier through app.extensions only in tests, never via HTTP.
        app.extensions["access_verifier"] = verifier
    elif mode == "local":
        if not operator or not token:
            raise ValueError("Local auth nur ueber CLI mit Operator und zufaelligem Token")
    else:
        raise ValueError("ADMIN_AUTH muss cloudflare oder local sein")

    @app.before_request
    def authenticate():
        if mode == "local":
            if request.host.split(":")[0] not in {"localhost", "127.0.0.1"}:
                abort(403, "Nur lokale Hostadresse erlaubt")
            expected_origin = "http://" + request.host
        else:
            expected_origin = app.config["ADMIN_PUBLIC_ORIGIN"].rstrip("/")
        origin = request.headers.get("Origin")
        if origin and origin != expected_origin:
            abort(403, "Fremder Origin")
        if request.path == "/healthz":
            return None
        if request.path == "/metrics":
            secret = app.config.get("ADMIN_METRICS_TOKEN", "")
            if not secret or not hmac.compare_digest(
                request.headers.get("Authorization", ""), "Bearer " + secret
            ):
                abort(401)
            return None
        if mode == "local":
            if request.path != "/" and not hmac.compare_digest(
                request.headers.get("Authorization", ""), "Bearer " + token
            ):
                abort(401, "Lokales Sitzungstoken erforderlich")
            g.actor, g.identity, g.roles = operator, operator, ROLES
        else:
            try:
                claims = app.extensions["access_verifier"](
                    request.headers.get("Cf-Access-Jwt-Assertion", "")
                )
                subject = claims["sub"]
                if not isinstance(subject, str) or not subject:
                    raise ValueError("subject")
            except Exception:
                abort(401, "Ungueltiges Access-Token")
            # Stable subject is the audit identity; email is display-only.
            g.actor = subject
            g.identity = claims.get("email", subject)
            g.roles = set(app.config["ADMIN_ROLE_BINDINGS"].get(subject, [])) & ROLES
            if not g.roles:
                abort(403, "Keine Konsolenrolle zugewiesen")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if origin != expected_origin or request.headers.get("X-Admin-Request") != "1":
                    abort(403, "Same-Origin-Schreibzugriff erforderlich")
        if request.method == "POST" and not (g.roles & WRITE_ROLES.get(request.path, set())):
            abort(403, "Rolle fuer diese Aktion fehlt")
