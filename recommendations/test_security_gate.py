"""Adversarial security-gate tests for SECURITY_THREATS.md.

Each class maps to a finding in that document. The tests exercise the real
view, settings loader and container files where possible; they are deliberately
hostile about the one control this app has (the per-IP rate limit).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from redis.exceptions import RedisError

from .checks import proxy_headers_have_an_origin_secret, proxy_topology_is_consistent
from .formspec import FIELD_BY_ID, public_spec, validate
from .tests import PRODUCTION_DB, STRONG_KEY, valid_answers
from .views import (
    CACHE_FAILURE_THRESHOLD, CACHE_OPEN_SECONDS, UNKNOWN_CLIENT, _fallback_cache,
    _is_allowed_origin, _refusal_log, _reset_circuit_breaker, client_ip, over_rate_limit,
)

ROOT = Path(settings.BASE_DIR)
ORIGIN_SECRET = "security-gate-origin-secret-0123456789"
REDIS_URL = "rediss://127.0.0.1:1/0"  # nothing listens on port 1: fails fast

_AWS_RUNTIME_VARS = (
    "AWS_EXECUTION_ENV",
    "ECS_CONTAINER_METADATA_URI",
    "ECS_CONTAINER_METADATA_URI_V4",
    "AWS_APP_RUNNER_ENVIRONMENT",
)


def production_env(**env):
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "GUNICORN_")) and key not in _AWS_RUNTIME_VARS
    }
    return {
        **clean,
        **PRODUCTION_DB,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_SECRET_KEY": STRONG_KEY,
        "DJANGO_ALLOWED_HOSTS": "retrofit.example.com",
        "DJANGO_REDIS_URL": REDIS_URL,
        "DJANGO_ORIGIN_VERIFY_SECRET": ORIGIN_SECRET,
        "DJANGO_TRUST_PROXY_HEADERS": "1",
        "DJANGO_TRUSTED_PROXY_COUNT": "2",
        **env,
    }


def run_settings(code, **env):
    return subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
        env=production_env(**env),
    )


class RateLimitConfigurationTests(SimpleTestCase):
    """T-01: a zero-period rate must never start and silently disable the limit."""

    def test_zero_period_rates_stop_startup(self):
        for rate in ("30/0m", "30/00s", "30/0h", "30/0d", "30/000m"):
            with self.subTest(rate=rate):
                result = run_settings("import config.settings", DJANGO_RECOMMEND_RATE_LIMIT=rate)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DJANGO_RECOMMEND_RATE_LIMIT", result.stderr)

    def test_valid_rates_still_load(self):
        for rate in ("30/m", "1/s", "10/5m", "500/h", "1000/d"):
            with self.subTest(rate=rate):
                result = run_settings(
                    "import json, config.settings as s; print(json.dumps(s.RECOMMEND_RATE_LIMIT))",
                    DJANGO_RECOMMEND_RATE_LIMIT=rate,
                )
                self.assertEqual(result.returncode, 0, result.stderr[-500:])
                self.assertEqual(json.loads(result.stdout), rate)

    def test_programming_errors_are_not_treated_as_a_cache_outage(self):
        request = RequestFactory().post(
            "/api/recommend", data="{}", content_type="application/json", REMOTE_ADDR="203.0.113.1"
        )
        _reset_circuit_breaker()
        with mock.patch("recommendations.views.is_ratelimited", side_effect=ZeroDivisionError("boom")):
            with self.assertRaises(ZeroDivisionError):
                over_rate_limit(request)

    def test_only_cache_errors_are_swallowed(self):
        request = RequestFactory().post(
            "/api/recommend", data="{}", content_type="application/json", REMOTE_ADDR="203.0.113.2"
        )
        _reset_circuit_breaker()
        _fallback_cache.clear()
        with mock.patch("recommendations.views.is_ratelimited", side_effect=RedisError("down")):
            self.assertFalse(over_rate_limit(request))


class CacheOutageTests(SimpleTestCase):
    """T-02: a slow/dead Redis must not become an unlimited pass or hold workers."""

    def setUp(self):
        _reset_circuit_breaker()
        _fallback_cache.clear()

    def test_redis_timeouts_are_sub_second(self):
        result = run_settings(
            "import json, config.settings as s; print(json.dumps(s.CACHES['default']['OPTIONS']))"
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        options = json.loads(result.stdout)
        self.assertLessEqual(options["socket_connect_timeout"], 0.5)
        self.assertLessEqual(options["socket_timeout"], 0.5)

    def test_the_breaker_stops_hammering_a_dead_cache(self):
        request = RequestFactory().post(
            "/api/recommend", data="{}", content_type="application/json", REMOTE_ADDR="203.0.113.3"
        )
        with mock.patch("recommendations.views.is_ratelimited", side_effect=RedisError("down")) as call:
            for _ in range(10):
                over_rate_limit(request)
        self.assertEqual(call.call_count, CACHE_FAILURE_THRESHOLD)

    def test_the_breaker_reopens_the_primary_cache_after_the_cooldown(self):
        request = RequestFactory().post(
            "/api/recommend", data="{}", content_type="application/json", REMOTE_ADDR="203.0.113.4"
        )
        with mock.patch("recommendations.views.is_ratelimited", side_effect=RedisError("down")):
            for _ in range(CACHE_FAILURE_THRESHOLD):
                over_rate_limit(request)
        later = time.monotonic() + CACHE_OPEN_SECONDS + 1
        with mock.patch("recommendations.views.time.monotonic", return_value=later):
            with mock.patch("recommendations.views.is_ratelimited", return_value=False) as call:
                self.assertFalse(over_rate_limit(request))
        self.assertEqual(call.call_count, 1)


class ProxyTopologyTests(SimpleTestCase):
    """T-03 and N-02: the image trusts no proxy; the deployment template opts in to two hops."""

    def test_the_image_trusts_no_proxy_and_the_template_opts_in(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        env_example = (ROOT / ".env.example").read_text()
        self.assertIn("DJANGO_TRUSTED_PROXY_COUNT=0", dockerfile)
        self.assertIn("DJANGO_TRUST_PROXY_HEADERS=0", dockerfile)
        self.assertIn("DJANGO_TRUSTED_PROXY_COUNT=2", env_example)
        self.assertIn("DJANGO_TRUST_PROXY_HEADERS=1", env_example)

    def test_fewer_than_two_hops_plus_cloudfronts_proto_header_is_a_deploy_warning(self):
        for hops in (0, 1):
            with self.subTest(hops=hops), override_settings(
                TRUSTED_PROXY_COUNT=hops,
                SECURE_PROXY_SSL_HEADER=("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https"),
            ):
                warnings = proxy_topology_is_consistent(None)
            self.assertEqual([warning.id for warning in warnings], ["recommendations.W002"])

    def test_two_hops_with_cloudfronts_proto_header_is_consistent(self):
        with override_settings(
            TRUSTED_PROXY_COUNT=2,
            SECURE_PROXY_SSL_HEADER=("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https"),
        ):
            self.assertEqual(proxy_topology_is_consistent(None), [])

    def test_trusted_proxy_headers_require_an_origin_secret(self):
        for kwargs in (
            {"SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https")},
            {"TRUSTED_PROXY_COUNT": 2, "SECURE_PROXY_SSL_HEADER": None},
        ):
            with self.subTest(kwargs=kwargs), override_settings(
                ORIGIN_VERIFY_SECRET="", **kwargs
            ):
                warnings = proxy_headers_have_an_origin_secret(None)
            self.assertEqual([warning.id for warning in warnings], ["recommendations.W003"])

    def test_direct_requests_without_proxy_trust_need_no_secret(self):
        with override_settings(
            TRUSTED_PROXY_COUNT=0, SECURE_PROXY_SSL_HEADER=None, ORIGIN_VERIFY_SECRET=""
        ):
            self.assertEqual(proxy_headers_have_an_origin_secret(None), [])


class IPv6RateLimitTests(TestCase):
    """T-04: rotating addresses inside one IPv6 /64 must not reset the allowance."""

    def setUp(self):
        cache.clear()
        _reset_circuit_breaker()
        _fallback_cache.clear()

    def test_client_ip_masks_ipv6_to_the_64_prefix(self):
        request = RequestFactory().post("/", REMOTE_ADDR="2001:db8:1:2:aaaa:bbbb:cccc:dddd")
        self.assertEqual(client_ip(None, request), "2001:db8:1:2::/64")

    def test_client_ip_keeps_ipv4_whole(self):
        request = RequestFactory().post("/", REMOTE_ADDR="198.51.100.7")
        self.assertEqual(client_ip(None, request), "198.51.100.7")

    def test_ipv4_mapped_ipv6_is_normalised_to_ipv4(self):
        request = RequestFactory().post("/", REMOTE_ADDR="::ffff:198.51.100.7")
        self.assertEqual(client_ip(None, request), "198.51.100.7")

    def test_missing_or_unreadable_addresses_share_a_constant_sentinel(self):
        request = RequestFactory().post("/", REMOTE_ADDR="")
        self.assertEqual(client_ip(None, request), UNKNOWN_CLIENT)
        request = RequestFactory().post(
            "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="not-an-address"
        )
        with self.settings(TRUSTED_PROXY_COUNT=1):
            self.assertEqual(client_ip(None, request), UNKNOWN_CLIENT)

    def test_forwarded_ipv6_is_masked_too(self):
        request = RequestFactory().post(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="2001:db8:1:2::1, 2001:db8:9:9::9",
        )
        with self.settings(TRUSTED_PROXY_COUNT=2):
            self.assertEqual(client_ip(None, request), "2001:db8:1:2::/64")

    @override_settings(RATELIMIT_ENABLE=True, TRUSTED_PROXY_COUNT=0, RECOMMEND_RATE_LIMIT="2/m")
    def test_rotating_within_one_64_does_not_reset_the_allowance(self):
        body = json.dumps({"answers": valid_answers()})
        post = lambda ip: self.client.post(
            "/api/recommend", data=body, content_type="application/json", REMOTE_ADDR=ip
        ).status_code
        self.assertEqual(post("2001:db8:1:2::1"), 200)
        self.assertEqual(post("2001:db8:1:2::2"), 200)
        self.assertEqual(post("2001:db8:1:2::3"), 429)
        # A different /64 is a different visitor.
        self.assertEqual(post("2001:db8:1:3::1"), 200)


class QuotaBurnTests(TestCase):
    """T-05: cheap rejections must happen before the counter is incremented."""

    def setUp(self):
        cache.clear()
        _reset_circuit_breaker()
        _fallback_cache.clear()

    @override_settings(RATELIMIT_ENABLE=True, RECOMMEND_RATE_LIMIT="2/m")
    def test_non_json_posts_do_not_consume_a_visitors_quota(self):
        for _ in range(10):
            response = self.client.post("/api/recommend", data="{}", content_type="text/plain")
            self.assertEqual(response.status_code, 415)
        for _ in range(2):
            response = self.client.post(
                "/api/recommend", data={"answers": valid_answers()}, content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 429)

    @override_settings(RATELIMIT_ENABLE=True, TRUSTED_PROXY_COUNT=0, RECOMMEND_RATE_LIMIT="2/m")
    def test_a_forged_forwarded_for_buys_nothing_when_no_proxy_is_trusted(self):
        # N-02: the image default. The header is ignored, so every request is one client.
        codes = [
            self.client.post(
                "/api/recommend", data={"answers": valid_answers()}, content_type="application/json",
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 1.1.1.1",
            ).status_code
            for i in range(4)
        ]
        self.assertEqual(codes, [200, 200, 429, 429])

    @override_settings(RATELIMIT_ENABLE=True, RECOMMEND_RATE_LIMIT="2/m")
    def test_malformed_json_is_counted(self):
        # N-03: a JSON post cannot come from a third-party page, so it is counted before the
        # body is read. Otherwise large or malformed bodies would be unlimited free work.
        for _ in range(2):
            self.assertEqual(
                self.client.post("/api/recommend", data="{bad", content_type="application/json").status_code,
                422,
            )
        for body in ("{bad", '{"answers": [1, 2]}'):
            self.assertEqual(
                self.client.post("/api/recommend", data=body, content_type="application/json").status_code,
                429,
            )
        self.assertEqual(
            self.client.post(
                "/api/recommend", data={"answers": valid_answers()}, content_type="application/json"
            ).status_code,
            429,
        )

    @override_settings(RATELIMIT_ENABLE=True, RECOMMEND_RATE_LIMIT="2/m")
    def test_a_client_over_the_limit_does_not_get_its_body_read(self):
        for _ in range(2):
            self.client.post("/api/recommend", data="{}", content_type="application/json")
        with mock.patch("recommendations.views.json.loads") as loads:
            response = self.client.post("/api/recommend", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 429)
        loads.assert_not_called()

    @override_settings(RATELIMIT_ENABLE=True, RECOMMEND_RATE_LIMIT="2/m")
    def test_cross_site_origin_and_fetch_metadata_are_refused_before_counting(self):
        body = json.dumps({"answers": valid_answers()})
        for headers in (
            {"HTTP_ORIGIN": "https://evil.example"},
            {"HTTP_SEC_FETCH_SITE": "cross-site"},
        ):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/api/recommend", data=body, content_type="application/json", **headers
                )
                self.assertEqual(response.status_code, 403)
        for _ in range(2):
            self.assertEqual(
                self.client.post("/api/recommend", data=body, content_type="application/json").status_code,
                200,
            )
        self.assertEqual(
            self.client.post("/api/recommend", data=body, content_type="application/json").status_code,
            429,
        )

    @override_settings(RATELIMIT_ENABLE=False, ALLOWED_HOSTS=["retrofit.example.com"])
    def test_an_invalid_host_with_an_origin_is_refused_not_crashed(self):
        response = self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json",
            HTTP_HOST="evil.example", HTTP_ORIGIN="http://evil.example",
        )
        self.assertEqual(response.status_code, 400)  # host check, before the view

    @override_settings(ALLOWED_HOSTS=["retrofit.example.com"])
    def test_the_origin_helper_treats_a_disallowed_host_as_cross_site(self):
        request = RequestFactory().post(
            "/api/recommend", HTTP_HOST="evil.example", HTTP_ORIGIN="http://evil.example"
        )
        self.assertFalse(_is_allowed_origin(request))

    @override_settings(RATELIMIT_ENABLE=False)
    def test_same_origin_requests_are_accepted(self):
        response = self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json",
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(response.status_code, 200)


class RefusalLoggingTests(TestCase):
    """N-05: a refusal must say which client was refused, without flooding the log."""

    def setUp(self):
        cache.clear()
        _reset_circuit_breaker()
        _fallback_cache.clear()
        _refusal_log.clear()

    def post(self, **headers):
        return self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json",
            REMOTE_ADDR="203.0.113.9", **headers,
        )

    @override_settings(RATELIMIT_ENABLE=True, TRUSTED_PROXY_COUNT=0, RECOMMEND_RATE_LIMIT="2/5m")
    def test_a_429_names_the_client_once_and_says_when_to_retry(self):
        self.post(), self.post()
        with self.assertLogs("recommendations.views", level="WARNING") as logs:
            responses = [self.post() for _ in range(5)]
        self.assertEqual({r.status_code for r in responses}, {429})
        self.assertEqual(responses[0]["Retry-After"], "300")
        self.assertEqual(len(logs.output), 1)  # five refusals, one line
        self.assertIn("reason=rate-limit client=203.0.113.9", logs.output[0])

    def test_a_cross_site_refusal_names_the_client_but_not_the_origin(self):
        with self.assertLogs("recommendations.views", level="WARNING") as logs:
            response = self.post(HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)
        self.assertIn("reason=cross-site client=203.0.113.9", logs.output[0])
        self.assertNotIn("evil", logs.output[0])  # nothing the sender wrote reaches the log


class SharedCacheTests(SimpleTestCase):
    """T-06: production must not silently use per-process LocMem counters."""

    def test_production_refuses_to_start_without_a_shared_cache(self):
        result = run_settings("import config.settings", DJANGO_REDIS_URL="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_REDIS_URL", result.stderr)

    def test_production_loads_with_a_shared_cache(self):
        result = run_settings(
            "import json, config.settings as s; print(json.dumps(s.CACHES['default']['BACKEND']))"
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertEqual(json.loads(result.stdout), "django.core.cache.backends.redis.RedisCache")


class OriginVerifyTests(TestCase):
    """T-07: a direct client must not be able to forge trusted proxy headers."""

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_requests_without_the_cloudfront_header_are_refused(self):
        self.assertEqual(self.client.get("/api/form-spec").status_code, 403)

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_the_correct_header_is_accepted(self):
        response = self.client.get("/api/form-spec", HTTP_X_ORIGIN_VERIFY=ORIGIN_SECRET)
        self.assertEqual(response.status_code, 200)

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_a_wrong_header_is_refused(self):
        self.assertEqual(
            self.client.get("/api/form-spec", HTTP_X_ORIGIN_VERIFY="wrong").status_code, 403
        )

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_a_non_ascii_header_is_refused_instead_of_crashing(self):
        response = self.client.get("/api/form-spec", HTTP_X_ORIGIN_VERIFY="s\u00e9cret")
        self.assertEqual(response.status_code, 403)

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_the_load_balancer_health_check_needs_no_secret(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    @override_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET, RATELIMIT_ENABLE=False)
    def test_a_valid_recommendation_carries_the_header_through(self):
        response = self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json",
            HTTP_X_ORIGIN_VERIFY=ORIGIN_SECRET,
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(ORIGIN_VERIFY_SECRET="", RATELIMIT_ENABLE=False)
    def test_no_secret_configured_is_a_no_op_for_local_work(self):
        self.assertEqual(self.client.get("/api/form-spec").status_code, 200)

    def test_a_short_secret_stops_startup(self):
        result = run_settings("import config.settings", DJANGO_ORIGIN_VERIFY_SECRET="short")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ORIGIN_VERIFY_SECRET", result.stderr)


class SupplyChainTests(SimpleTestCase):
    """T-08: the RDS trust anchor and the base image must be pinned."""

    def test_base_image_is_pinned_by_digest(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"FROM python:[^\s]+@sha256:[0-9a-f]{64}")

    def test_rds_bundle_download_has_a_checksum(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"ADD --chmod=644 --checksum=sha256:[0-9a-f]{64}")

    def test_runtime_requirements_are_hash_locked(self):
        requirements = (ROOT / "requirements.txt").read_text()
        self.assertIn("--hash=sha256:", requirements)
        self.assertIn("--require-hashes", (ROOT / "Dockerfile").read_text())


class ManualInfrastructureTests(SimpleTestCase):
    """T-09: the deployment document must keep the manual CloudFront controls visible."""

    def test_deploy_document_names_the_response_header_and_waf_controls(self):
        deploy = (ROOT / "DEPLOY.md").read_text()
        for text in ("frame-ancestors 'none'", "X-Content-Type-Options", "AWS WAF", "X-Origin-Verify"):
            with self.subTest(text=text):
                self.assertIn(text, deploy)


class SpecImmutabilityTests(SimpleTestCase):
    """T-10: per-request data must not leak through the shared form definition."""

    def test_public_spec_is_a_deep_copy(self):
        first = public_spec()
        first["sections"][0]["fields"][0]["label"] = "tampered"
        first["sections"][0]["fields"][0]["options"] = ["tampered"]
        second = public_spec()
        self.assertNotEqual(second["sections"][0]["fields"][0]["label"], "tampered")
        self.assertNotEqual(second["sections"][0]["fields"][0].get("options"), ["tampered"])

    def test_year_rollover_does_not_mutate_the_shared_field(self):
        from datetime import date
        from unittest import mock

        class NextYear(date):
            @classmethod
            def today(cls):
                return date(date.today().year + 1, 1, 1)

        original = FIELD_BY_ID["year_built"]["max"]
        with mock.patch("recommendations.formspec.date", NextYear):
            validate({**valid_answers(), "year_built": date.today().year + 1})
            self.assertEqual(FIELD_BY_ID["year_built"]["max"], original)
            spec = public_spec()
            year = next(
                field for section in spec["sections"] for field in section["fields"]
                if field["id"] == "year_built"
            )
            self.assertEqual(year["max"], date.today().year + 1)


class DebugGuardTests(SimpleTestCase):
    """T-11: DEBUG=1 must not silently remove every production guard in AWS."""

    def test_debug_is_refused_inside_an_aws_container(self):
        result = run_settings(
            "import config.settings", DJANGO_DEBUG="1", AWS_EXECUTION_ENV="AWS_ECS_FARGATE"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG=1 is refused", result.stderr)

    def test_debug_is_refused_inside_the_image_on_any_host(self):
        # N-06: the Dockerfile sets the marker, so no AWS variable is needed.
        self.assertIn("DJANGO_IN_CONTAINER=1", (ROOT / "Dockerfile").read_text())
        result = run_settings("import config.settings", DJANGO_DEBUG="1", DJANGO_IN_CONTAINER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG=1 is refused", result.stderr)

    def test_the_container_marker_does_not_affect_production_mode(self):
        result = run_settings(
            "import json, config.settings as s; print(json.dumps(s.DEBUG))", DJANGO_IN_CONTAINER="1"
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertFalse(json.loads(result.stdout))

    def test_debug_can_be_opted_into_explicitly_for_a_debug_task(self):
        result = run_settings(
            "import json, config.settings as s; print(json.dumps(s.DEBUG))",
            DJANGO_DEBUG="1",
            AWS_EXECUTION_ENV="AWS_ECS_FARGATE",
            DJANGO_ALLOW_DEBUG_IN_CONTAINER="1",
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertTrue(json.loads(result.stdout))

    def test_debug_is_still_allowed_outside_a_container(self):
        result = run_settings("import json, config.settings as s; print(json.dumps(s.DEBUG))", DJANGO_DEBUG="1")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertTrue(json.loads(result.stdout))


class UnusedFrameworkSurfaceTests(SimpleTestCase):
    """T-12: auth, sessions and messages are not used and should not be installed."""

    def test_unused_apps_and_middleware_are_gone(self):
        for app in (
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
        ):
            self.assertNotIn(app, settings.INSTALLED_APPS)
        for middleware in (
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ):
            self.assertNotIn(middleware, settings.MIDDLEWARE)

    def test_no_session_or_auth_cookie_is_set(self):
        response = self.client.get("/api/form-spec")
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotIn("csrftoken", response.cookies)


class PersonalDataTests(TestCase):
    """T-13: the report and logs must not echo the postal code."""

    @override_settings(RATELIMIT_ENABLE=False)
    def test_the_report_does_not_echo_the_postal_code(self):
        response = self.client.post(
            "/api/recommend", data={"answers": valid_answers()}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("N9A", response.content.decode())

    @override_settings(RATELIMIT_ENABLE=False)
    def test_a_refused_answer_does_not_log_it(self):
        with self.assertNoLogs("recommendations.views", level="INFO"):
            self.client.post(
                "/api/recommend", data={"answers": {**valid_answers(), "floor_area": 1}},
                content_type="application/json",
            )
