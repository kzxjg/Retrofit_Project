from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .database import database_config

BASE = Path("/app")
PROD = {"DJANGO_DB_NAME": "retrofit", "DJANGO_DB_USER": "app", "DJANGO_DB_HOST": "db.example.internal",
        "DJANGO_DB_PASSWORD": "secret"}


class DatabaseConfigTests(SimpleTestCase):
    def test_local_work_without_settings_uses_sqlite(self):
        config = database_config({}, debug=True, base_dir=BASE)
        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], BASE / "db.sqlite3")

    def test_production_refuses_sqlite(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_DB_NAME"):
            database_config({}, debug=False, base_dir=BASE)

    def test_production_postgres_requires_encryption_by_default(self):
        config = database_config(PROD, debug=False, base_dir=BASE)
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((config["NAME"], config["USER"], config["HOST"], config["PORT"]),
                         ("retrofit", "app", "db.example.internal", "5432"))
        self.assertEqual(config["PASSWORD"], "secret")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})
        self.assertTrue(config["CONN_HEALTH_CHECKS"])
        self.assertEqual(config["CONN_MAX_AGE"], 60)

    def test_production_refuses_unencrypted_connections(self):
        for mode in ("disable", "allow", "prefer"):
            with self.subTest(mode=mode), self.assertRaises(ImproperlyConfigured):
                database_config({**PROD, "DJANGO_DB_SSLMODE": mode}, debug=False, base_dir=BASE)

    def test_production_can_verify_the_server_certificate(self):
        config = database_config(
            {**PROD, "DJANGO_DB_SSLMODE": "verify-full", "DJANGO_DB_SSLROOTCERT": "/certs/rds.pem"},
            debug=False, base_dir=BASE,
        )
        self.assertEqual(config["OPTIONS"], {"sslmode": "verify-full", "sslrootcert": "/certs/rds.pem"})

    def test_production_requires_user_and_host(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_DB_USER, DJANGO_DB_HOST"):
            database_config({"DJANGO_DB_NAME": "retrofit"}, debug=False, base_dir=BASE)

    def test_local_postgres_prefers_ssl_and_allows_defaults(self):
        config = database_config({"DJANGO_DB_NAME": "retrofit"}, debug=True, base_dir=BASE)
        self.assertEqual(config["OPTIONS"], {"sslmode": "prefer"})
        self.assertEqual(config["HOST"], "")  # local Unix socket

    def test_bad_port_and_ssl_mode_are_refused(self):
        # "²" and "٥٤٣٢" pass str.isdigit(); the first used to crash int() with a bare ValueError.
        for env in ({**PROD, "DJANGO_DB_PORT": "abc"}, {**PROD, "DJANGO_DB_PORT": "70000"},
                    {**PROD, "DJANGO_DB_PORT": "0"}, {**PROD, "DJANGO_DB_PORT": "-1"},
                    {**PROD, "DJANGO_DB_PORT": "²"}, {**PROD, "DJANGO_DB_PORT": "٥٤٣٢"},
                    {**PROD, "DJANGO_DB_SSLMODE": "yes"}):
            with self.subTest(env=env), self.assertRaises(ImproperlyConfigured):
                database_config(env, debug=False, base_dir=BASE)

    def test_port_and_connection_age_can_be_set(self):
        config = database_config({**PROD, "DJANGO_DB_PORT": " 6543 ", "DJANGO_DB_CONN_MAX_AGE": "0"},
                                 debug=False, base_dir=BASE)
        self.assertEqual((config["PORT"], config["CONN_MAX_AGE"]), ("6543", 0))

    def test_a_blank_port_or_connection_age_uses_the_default(self):
        config = database_config({**PROD, "DJANGO_DB_PORT": "", "DJANGO_DB_CONN_MAX_AGE": " "},
                                 debug=False, base_dir=BASE)
        self.assertEqual((config["PORT"], config["CONN_MAX_AGE"]), ("5432", 60))

    def test_a_bad_connection_age_is_refused_with_a_clear_message(self):
        for value in ("abc", "-5", "1.5", "²"):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_DB_CONN_MAX_AGE"):
                    database_config({**PROD, "DJANGO_DB_CONN_MAX_AGE": value}, debug=False, base_dir=BASE)

    def test_every_ssl_mode_that_encrypts_is_allowed_in_production(self):
        for mode in ("require", "verify-ca", "verify-full"):
            with self.subTest(mode=mode):
                config = database_config({**PROD, "DJANGO_DB_SSLMODE": mode}, debug=False, base_dir=BASE)
                self.assertEqual(config["OPTIONS"]["sslmode"], mode)
