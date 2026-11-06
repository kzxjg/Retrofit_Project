"""Builds the DATABASES setting from environment variables.

Set DJANGO_DB_NAME to use PostgreSQL. Leave it unset for local work with
SQLite; production (DEBUG off) refuses to start without PostgreSQL.
"""

import re

from django.core.exceptions import ImproperlyConfigured

SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def database_config(env, debug, base_dir):
    name = env.get("DJANGO_DB_NAME", "").strip()
    if not name:
        if not debug:
            raise ImproperlyConfigured(
                "DJANGO_DB_NAME must be set when DJANGO_DEBUG is false; "
                "SQLite is for local development only."
            )
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
        }

    user = env.get("DJANGO_DB_USER", "").strip()
    host = env.get("DJANGO_DB_HOST", "").strip()
    if not debug:
        missing = [var for var, value in (("DJANGO_DB_USER", user), ("DJANGO_DB_HOST", host)) if not value]
        if missing:
            raise ImproperlyConfigured(f"{', '.join(missing)} must be set when DJANGO_DEBUG is false.")

    port = env.get("DJANGO_DB_PORT", "5432").strip() or "5432"
    # [0-9], not isdigit(): isdigit() also accepts characters such as "²" that int() rejects.
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 0 < int(port) < 65536:
        raise ImproperlyConfigured("DJANGO_DB_PORT must be a port number.")

    # Production traffic to the database must be encrypted; locally, use it if offered.
    sslmode = env.get("DJANGO_DB_SSLMODE", "").strip() or ("prefer" if debug else "require")
    if sslmode not in SSL_MODES:
        raise ImproperlyConfigured(f"DJANGO_DB_SSLMODE must be one of: {', '.join(sorted(SSL_MODES))}.")
    if not debug and sslmode in {"disable", "allow", "prefer"}:
        raise ImproperlyConfigured("DJANGO_DB_SSLMODE must be require, verify-ca or verify-full in production.")

    options = {"sslmode": sslmode}
    root_cert = env.get("DJANGO_DB_SSLROOTCERT", "").strip()
    if root_cert:
        options["sslrootcert"] = root_cert

    conn_max_age = env.get("DJANGO_DB_CONN_MAX_AGE", "").strip() or "60"
    if not re.fullmatch(r"[0-9]+", conn_max_age):
        raise ImproperlyConfigured("DJANGO_DB_CONN_MAX_AGE must be a whole number of seconds.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": user,
        "PASSWORD": env.get("DJANGO_DB_PASSWORD", ""),
        "HOST": host,
        "PORT": port,
        # Reuse connections for a minute instead of opening one per request,
        # and check a reused one is still alive before handing it out.
        "CONN_MAX_AGE": int(conn_max_age),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }
