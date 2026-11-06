"""Tests against a real Redis and a real PostgreSQL, like the ones on AWS.

Everything else runs on SQLite and in-process memory, so these are skipped unless you
point them at real servers:

    # Redis or Valkey (rediss:// for TLS, as in production)
    DJANGO_TEST_REDIS_URL=redis://127.0.0.1:6379/15 DJANGO_DEBUG=1 python manage.py test config.test_integration

    # PostgreSQL: set the usual DJANGO_DB_* variables; the whole suite then runs on it,
    # in a throwaway test_<name> database.
    DJANGO_DB_NAME=retrofit DJANGO_DB_USER=... DJANGO_DB_PASSWORD=... DJANGO_DB_HOST=127.0.0.1 \\
        DJANGO_DEBUG=1 python manage.py test

    # Also check the connection is encrypted (set it when the server offers TLS, as RDS does)
    DJANGO_TEST_EXPECT_DB_TLS=1

The Redis tests write under a random key prefix and delete only those keys afterwards,
never the whole database.
"""

import os
import unittest
import uuid

from django.core.cache import caches
from django.db import connection
from django.test import TestCase, override_settings

from recommendations.tests import valid_answers

REDIS_URL = os.environ.get("DJANGO_TEST_REDIS_URL", "").strip()


def redis_caches(prefix):
    """Two cache connections to the same Redis: like two gunicorn workers or two containers."""
    backend = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": prefix,
        "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
    }
    return {"default": dict(backend), "other_worker": dict(backend)}


@unittest.skipUnless(REDIS_URL, "set DJANGO_TEST_REDIS_URL to test against a real Redis")
class RealRedisRateLimitTests(TestCase):
    LIMIT = 3

    def setUp(self):
        self.prefix = f"retrofit-test-{uuid.uuid4().hex}"
        self.use_cache("default")

    def use_cache(self, alias):
        overrides = override_settings(CACHES=redis_caches(self.prefix), RATELIMIT_ENABLE=True,
                                      RECOMMEND_RATE_LIMIT=f"{self.LIMIT}/m", RATELIMIT_USE_CACHE=alias)
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.addCleanup(self.delete_own_keys)

    def delete_own_keys(self):
        cache = caches["default"]
        client = cache._cache.get_client(write=True)
        for key in client.scan_iter(match=f"{self.prefix}:*"):
            client.delete(key)
        for alias in ("default", "other_worker"):
            caches[alias].close()

    def post(self, ip="203.0.113.7"):
        return self.client.post("/api/recommend", data={"answers": valid_answers()},
                                content_type="application/json", REMOTE_ADDR=ip)

    def test_the_server_can_be_reached(self):
        cache = caches["default"]
        cache.set("ping", "pong", 30)
        self.assertEqual(cache.get("ping"), "pong")

    def test_the_limit_is_enforced_through_redis(self):
        for _ in range(self.LIMIT):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(self.post(ip="198.51.100.9").status_code, 200, "other visitors keep their own allowance")

    def test_the_count_is_shared_between_workers(self):
        for _ in range(self.LIMIT):
            self.assertEqual(self.post().status_code, 200)
        # A different worker, with its own connection, must see the same count.
        self.use_cache("other_worker")
        self.assertEqual(self.post().status_code, 429)

    def test_counts_are_kept_with_an_expiry(self):
        self.post()
        client = caches["default"]._cache.get_client()
        keys = list(client.scan_iter(match=f"{self.prefix}:*"))
        self.assertTrue(keys, "the rate limiter wrote nothing to Redis")
        for key in keys:
            self.assertGreater(client.ttl(key), 0, "a count without an expiry would block a visitor forever")


@unittest.skipUnless(connection.vendor == "postgresql",
                     "set DJANGO_DB_NAME and the other DJANGO_DB_* variables to test against PostgreSQL")
class RealPostgresTests(TestCase):
    def test_the_database_answers(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))

    def test_the_settings_reach_the_driver(self):
        params = connection.get_connection_params()
        self.assertEqual(params["sslmode"], connection.settings_dict["OPTIONS"]["sslmode"])
        self.assertTrue(connection.settings_dict["CONN_HEALTH_CHECKS"])

    @unittest.skipUnless(os.environ.get("DJANGO_TEST_EXPECT_DB_TLS") == "1",
                         "set DJANGO_TEST_EXPECT_DB_TLS=1 when the server offers TLS")
    def test_the_connection_is_encrypted(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            self.assertEqual(cursor.fetchone(), (True,))

    def test_the_api_works_end_to_end_on_postgres(self):
        with override_settings(RATELIMIT_ENABLE=False):
            response = self.client.post("/api/recommend", data={"answers": valid_answers()},
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("package", response.json())
