from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def rate_limit_cache_is_shared(app_configs, **kwargs):
    """`check --deploy`: rate-limit counts kept in one process's memory are not shared."""
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend.endswith(("LocMemCache", "DummyCache")):
        return [Warning(
            "Rate-limit counts are kept in each process's own memory, so with several "
            "processes or containers a visitor gets that many times the limit.",
            hint="Set DJANGO_REDIS_URL to a shared Redis, such as Amazon ElastiCache.",
            id="recommendations.W001",
        )]
    return []


@register(Tags.security, deploy=True)
def proxy_topology_is_consistent(app_configs, **kwargs):
    """CloudFront's HTTPS header requires two proxy hops (CloudFront + ALB)."""
    header = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
    if (
        header
        and header[0] == "HTTP_CLOUDFRONT_FORWARDED_PROTO"
        and settings.TRUSTED_PROXY_COUNT < 2
    ):
        return [Warning(
            f"DJANGO_TRUSTED_PROXY_COUNT={settings.TRUSTED_PROXY_COUNT} trusts fewer than "
            "two proxies, but DJANGO_PROXY_SSL_HEADER trusts CloudFront's header, which "
            "requires two hops (CloudFront + ALB). The rate-limit key would use the "
            "wrong address: every visitor behind one CloudFront edge, or every visitor "
            "at all, could share a single allowance.",
            hint="Use DJANGO_TRUSTED_PROXY_COUNT=2 for CloudFront + ALB.",
            id="recommendations.W002",
        )]
    return []


@register(Tags.security, deploy=True)
def proxy_headers_have_an_origin_secret(app_configs, **kwargs):
    """Trusting proxy headers without an origin secret lets a direct client forge them."""
    trusts_proxy_headers = bool(getattr(settings, "SECURE_PROXY_SSL_HEADER", None))
    trusts_forwarded_for = settings.TRUSTED_PROXY_COUNT > 0
    if (trusts_proxy_headers or trusts_forwarded_for) and not getattr(
        settings, "ORIGIN_VERIFY_SECRET", ""
    ):
        return [Warning(
            "Proxy headers are trusted but DJANGO_ORIGIN_VERIFY_SECRET is empty. A "
            "client that reaches the ALB directly could forge X-Forwarded-For and the "
            "HTTPS header, bypassing the rate limit.",
            hint="Set DJANGO_ORIGIN_VERIFY_SECRET and have CloudFront add X-Origin-Verify.",
            id="recommendations.W003",
        )]
    return []
