"""Tests for running behind AWS: load balancer health checks, logging to
CloudWatch, the shared rate-limit cache, gunicorn and the container image.

Settings are read once when Python starts, so the production cases run a fresh
interpreter with production environment variables, as a real container would."""

import json
import os
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path

from django.conf import settings
from django.core.cache import caches
from django.test import SimpleTestCase, TestCase, override_settings

from recommendations.tests import PRODUCTION_DB, STRONG_KEY, valid_answers

ROOT = Path(settings.BASE_DIR)
SITE = "retrofit.example.com"
PRODUCTION = {
    **PRODUCTION_DB,
    "DJANGO_SECRET_KEY": STRONG_KEY,
    "DJANGO_ALLOWED_HOSTS": SITE,
    "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{SITE}",
    "DJANGO_TRUST_PROXY_HEADERS": "1",
    "DJANGO_TRUSTED_PROXY_COUNT": "1",
}

# Runs in the fresh interpreter. Sends each request in REQUESTS, prints one JSON
# line per answer, then prints what the app logged.
REQUEST_SCRIPT = textwrap.dedent("""
    import io, json, logging, os, sys
    sys.path.insert(0, os.getcwd())
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.test import Client
    captured = io.StringIO()
    logging.getHandlerByName("console").setStream(captured)
    from unittest import mock
    results = []
    for req in json.loads(sys.argv[1]):
        client = Client(raise_request_exception=False, enforce_csrf_checks=True)
        headers = {"HTTP_HOST": req["host"]}
        if req.get("https"):
            headers["HTTP_X_FORWARDED_PROTO"] = "https"
        headers.update(req.get("headers", {}))
        patches = [mock.patch(req["break"], side_effect=RuntimeError("deliberate failure"))] if req.get("break") else []
        for p in patches: p.start()
        if req["method"] == "post":
            r = client.post(req["path"], data=req["body"], content_type="application/json",
                            HTTP_ORIGIN="https://" + req["host"], **headers)
        else:
            r = getattr(client, req["method"])(req["path"], **headers)
        for p in patches: p.stop()
        results.append({"status": r.status_code, "location": r.get("Location", ""),
                        "headers": {k: r.get(k, "") for k in ("X-Frame-Options", "Content-Security-Policy",
                                                              "X-Content-Type-Options")},
                        "body": r.content.decode()[:200]})
    print(json.dumps({"results": results, "log": captured.getvalue()}))
""")


def run_production(requests, **env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "GUNICORN_"))}
    result = subprocess.run(
        [sys.executable, "-c", REQUEST_SCRIPT, json.dumps(requests)],
        cwd=ROOT, capture_output=True, text=True, env={**clean, **PRODUCTION, **env},
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def get(path, host=SITE, https=False, method="get"):
    return {"method": method, "path": path, "host": host, "https": https}


class LoadBalancerTests(SimpleTestCase):
    """What an ALB and CloudFront send, against the real production settings."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cases = {
            "check at private ip": get("/api/health", host="10.0.1.23"),
            "check head": get("/api/health", host="10.0.1.23", method="head"),
            "check with site name": get("/api/health"),
            "spec at private ip": get("/api/form-spec", host="10.0.1.23", https=True),
            "health with slash at private ip": get("/api/health/", host="10.0.1.23"),
            "delete health at private ip": get("/api/health", host="10.0.1.23", method="delete"),
            "spec over http": get("/api/form-spec"),
            "spec over https": get("/api/form-spec", https=True),
            "spec via alb dns name": get("/api/form-spec", host="retrofit-alb-1.ca-central-1.elb.amazonaws.com", https=True),
            "recommend": {**get("/api/recommend", https=True, method="post"),
                          "body": json.dumps({"answers": valid_answers()})},
        }
        cls.out = run_production(list(cls.cases.values()))
        cls.by_name = dict(zip(cls.cases, cls.out["results"]))

    def test_health_check_answers_at_the_containers_private_address_over_http(self):
        r = self.by_name["check at private ip"]
        self.assertEqual(r["status"], 200)
        self.assertEqual(json.loads(r["body"]), {"status": "ok"})
        self.assertEqual(self.by_name["check head"]["status"], 200)
        self.assertEqual(self.by_name["check with site name"]["status"], 200)  # not redirected to https

    def test_health_check_still_carries_the_security_headers(self):
        headers = self.by_name["check at private ip"]["headers"]
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

    def test_only_the_health_check_skips_the_host_check(self):
        self.assertEqual(self.by_name["spec at private ip"]["status"], 400)
        self.assertEqual(self.by_name["health with slash at private ip"]["status"], 400)
        self.assertEqual(self.by_name["delete health at private ip"]["status"], 400)
        self.assertEqual(self.by_name["spec via alb dns name"]["status"], 400)  # CloudFront must forward Host

    def test_everything_else_is_still_redirected_to_https(self):
        r = self.by_name["spec over http"]
        self.assertEqual(r["status"], 301)
        self.assertEqual(r["location"], f"https://{SITE}/api/form-spec")

    def test_a_visit_through_the_load_balancer_works_end_to_end(self):
        self.assertEqual(self.by_name["spec over https"]["status"], 200)
        r = self.by_name["recommend"]
        self.assertEqual(r["status"], 200, r["body"])
        self.assertIn("package", json.loads(r["body"]))

    def test_each_recommendation_is_logged_without_the_answers(self):
        log = self.out["log"]
        self.assertIn("INFO recommendations.views recommendation package=", log)
        self.assertNotIn("N9A", log)  # the sample postal code


class BeforeThereIsADomainTests(SimpleTestCase):
    """CloudFront's own address, with CloudFront reaching an internal ALB over HTTP:
    the ALB says "http" and only CloudFront-Forwarded-Proto knows it was HTTPS."""

    CLOUDFRONT = "d1234abcd.cloudfront.net"
    ENV = {"DJANGO_ALLOWED_HOSTS": CLOUDFRONT, "DJANGO_CSRF_TRUSTED_ORIGINS": "",
           "DJANGO_PROXY_SSL_HEADER": "CloudFront-Forwarded-Proto", "DJANGO_TRUSTED_PROXY_COUNT": "2"}

    def request(self, path, method="get", **headers):
        req = {"method": method, "path": path, "host": self.CLOUDFRONT,
               "headers": {"HTTP_X_FORWARDED_PROTO": "http", **headers}}
        if method == "post":
            req["body"] = json.dumps({"answers": valid_answers()})
        return req

    def test_a_visit_through_cloudfront_works_end_to_end_without_csrf_trusted_origins(self):
        out = run_production([
            self.request("/api/form-spec", HTTP_CLOUDFRONT_FORWARDED_PROTO="https"),
            self.request("/api/recommend", method="post", HTTP_CLOUDFRONT_FORWARDED_PROTO="https"),
        ], **self.ENV)
        self.assertEqual([r["status"] for r in out["results"]], [200, 200], out["results"][-1]["body"])
        self.assertIn("package", json.loads(out["results"][1]["body"]))

    def test_without_cloudfronts_header_the_request_is_sent_to_https(self):
        out = run_production([self.request("/api/form-spec")], **self.ENV)
        self.assertEqual(out["results"][0]["status"], 301)
        self.assertEqual(out["results"][0]["location"], f"https://{self.CLOUDFRONT}/api/form-spec")

    def test_the_albs_header_is_not_trusted_in_this_mode(self):
        out = run_production([self.request("/api/form-spec", HTTP_X_FORWARDED_PROTO="https")], **self.ENV)
        self.assertEqual(out["results"][0]["status"], 301)

    def test_with_the_default_setting_the_same_request_would_loop(self):
        # Why the setting exists: the ALB says http, so Django keeps redirecting to https.
        env = {**self.ENV, "DJANGO_PROXY_SSL_HEADER": ""}
        out = run_production([self.request("/api/form-spec", HTTP_CLOUDFRONT_FORWARDED_PROTO="https")], **env)
        self.assertEqual(out["results"][0]["status"], 301)

    def test_the_real_domain_can_be_added_next_to_the_cloudfront_address(self):
        env = {**self.ENV, "DJANGO_ALLOWED_HOSTS": f"{SITE},{self.CLOUDFRONT}"}
        out = run_production([
            self.request("/api/form-spec", HTTP_CLOUDFRONT_FORWARDED_PROTO="https"),
            {**self.request("/api/form-spec", HTTP_CLOUDFRONT_FORWARDED_PROTO="https"), "host": SITE},
            {**self.request("/api/form-spec", HTTP_CLOUDFRONT_FORWARDED_PROTO="https"), "host": "other.example"},
        ], **env)
        self.assertEqual([r["status"] for r in out["results"]], [200, 200, 400])


class ProductionLoggingTests(SimpleTestCase):
    def test_a_crash_is_logged_with_its_traceback(self):
        out = run_production([{**get("/api/recommend", https=True, method="post"),
                               "body": json.dumps({"answers": valid_answers()}),
                               "break": "recommendations.views.recommend_package"}])
        self.assertEqual(out["results"][0]["status"], 500)
        self.assertIn("ERROR django.request Internal Server Error: /api/recommend", out["log"])
        self.assertIn("Traceback", out["log"])
        self.assertIn("RuntimeError: deliberate failure", out["log"])

    def test_the_log_level_can_be_raised_to_keep_only_problems(self):
        out = run_production([{**get("/api/recommend", https=True, method="post"),
                               "body": json.dumps({"answers": valid_answers()})}], DJANGO_LOG_LEVEL="warning")
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertNotIn("recommendation package=", out["log"])

    def test_an_unknown_log_level_stops_startup(self):
        with self.assertRaisesMessage(AssertionError, "DJANGO_LOG_LEVEL"):
            run_production([], DJANGO_LOG_LEVEL="loud")


class CacheSettingsTests(SimpleTestCase):
    def cache_backend(self, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        code = "import json, config.settings as s; print(json.dumps(s.CACHES['default']))"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                                env={**clean, **PRODUCTION, **env})
        return result

    def test_production_uses_a_shared_redis_over_tls_when_given_one(self):
        result = self.cache_backend(DJANGO_REDIS_URL="rediss://cache.example.internal:6379/0")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        cache = json.loads(result.stdout)
        self.assertEqual(cache["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(cache["LOCATION"], "rediss://cache.example.internal:6379/0")

    def test_production_refuses_redis_without_tls_and_other_schemes(self):
        for url in ("redis://cache.example.internal:6379/0", "http://cache.example.internal", "cache:6379"):
            with self.subTest(url=url):
                result = self.cache_backend(DJANGO_REDIS_URL=url)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_REDIS_URL", result.stderr)

    def test_local_work_may_use_plain_redis_or_none(self):
        result = self.cache_backend(DJANGO_DEBUG="1", DJANGO_REDIS_URL="redis://127.0.0.1:6379/0")
        self.assertEqual(json.loads(result.stdout)["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        result = self.cache_backend(DJANGO_DEBUG="1")
        self.assertEqual(json.loads(result.stdout)["BACKEND"], "django.core.cache.backends.locmem.LocMemCache")

    def deploy_check(self, **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        return subprocess.run([sys.executable, "manage.py", "check", "--deploy"], cwd=ROOT,
                              capture_output=True, text=True, env={**clean, **PRODUCTION, **env})

    def test_deploy_check_warns_when_rate_limits_are_not_shared(self):
        result = self.deploy_check()
        self.assertIn("recommendations.W001", result.stdout + result.stderr)
        result = self.deploy_check(DJANGO_REDIS_URL="rediss://cache.example.internal:6379/0")
        self.assertNotIn("recommendations.W001", result.stdout + result.stderr)


UNREACHABLE_REDIS = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:1/0",  # nothing listens on port 1
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}


@override_settings(CACHES=UNREACHABLE_REDIS, RATELIMIT_ENABLE=True)
class CacheOutageTests(TestCase):
    def tearDown(self):
        caches["default"].close()

    def test_a_cache_outage_lets_requests_through_and_logs_an_error(self):
        with self.assertLogs("recommendations.views", level="ERROR") as logs:
            response = self.client.post("/api/recommend", data={"answers": valid_answers()},
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("package", response.json())
        self.assertIn("Rate-limit cache unavailable", logs.output[0])

    def test_bad_answers_are_still_refused_during_an_outage(self):
        with self.assertLogs("recommendations.views", level="ERROR"):
            response = self.client.post("/api/recommend", data={"answers": {}},
                                        content_type="application/json")
        self.assertEqual(response.status_code, 422)


class GunicornConfigTests(SimpleTestCase):
    def load(self, **env):
        names = ("PORT", "GUNICORN_WORKERS", "GUNICORN_TIMEOUT")
        saved = {name: os.environ.pop(name, None) for name in names}
        os.environ.update(env)
        try:
            return runpy.run_path(str(ROOT / "gunicorn.conf.py"))
        finally:
            for name in names:
                os.environ.pop(name, None)
                if saved[name] is not None:
                    os.environ[name] = saved[name]

    def test_defaults_listen_on_8000_and_log_to_stdout(self):
        conf = self.load()
        self.assertEqual(conf["bind"], "0.0.0.0:8000")
        self.assertEqual((conf["workers"], conf["timeout"]), (3, 30))
        self.assertEqual((conf["accesslog"], conf["errorlog"]), ("-", "-"))

    def test_port_and_workers_can_be_set(self):
        conf = self.load(PORT="9000", GUNICORN_WORKERS="5", GUNICORN_TIMEOUT="60")
        self.assertEqual((conf["bind"], conf["workers"], conf["timeout"]), ("0.0.0.0:9000", 5, 60))

    def test_bad_numbers_stop_startup(self):
        for env in ({"PORT": "abc"}, {"GUNICORN_WORKERS": "0"}, {"GUNICORN_WORKERS": "-2"},
                    {"GUNICORN_TIMEOUT": "1.5"}, {"GUNICORN_WORKERS": "²"}):
            with self.subTest(env=env), self.assertRaises(SystemExit):
                self.load(**env)


class ContainerImageTests(SimpleTestCase):
    """The Dockerfile cannot be built here, so check what it promises."""

    dockerfile = (ROOT / "Dockerfile").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    def test_secrets_and_local_files_never_enter_the_image(self):
        rules = [line.strip() for line in self.dockerignore if line.strip() and not line.startswith("#")]
        self.assertEqual(rules[0], "*")  # everything is excluded unless listed
        allowed = [rule[1:] for rule in rules if rule.startswith("!")]
        for name in allowed:
            self.assertFalse(name.startswith((".env", ".venv", "db.sqlite3", "frontend")), name)

    def test_every_file_the_image_copies_exists_and_is_allowed_in(self):
        allowed = {line[1:].rstrip("/") for line in self.dockerignore if line.startswith("!")}
        for line in self.dockerfile.splitlines():
            if line.startswith("COPY "):
                for source in line.split()[1:-1]:
                    with self.subTest(source=source):
                        self.assertTrue((ROOT / source).exists())
                        self.assertIn(source.rstrip("/"), allowed)

    def test_the_image_runs_gunicorn_as_a_normal_user_in_production_mode(self):
        self.assertIn('CMD ["gunicorn", "config.wsgi"]', self.dockerfile)
        self.assertRegex(self.dockerfile, r"\nUSER app\n")
        self.assertIn("DJANGO_DEBUG=0", self.dockerfile)
        self.assertIn("DJANGO_DB_SSLMODE=verify-full", self.dockerfile)

    def test_runtime_packages_are_pinned(self):
        lines = (ROOT / "requirements.txt").read_text().splitlines()
        for package in ("gunicorn", "redis", "psycopg[binary]", "Django", "django-ratelimit"):
            with self.subTest(package=package):
                self.assertTrue(any(line.startswith(f"{package}==") for line in lines))
