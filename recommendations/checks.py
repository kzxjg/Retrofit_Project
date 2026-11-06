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

