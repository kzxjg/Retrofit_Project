import secrets

from django.conf import settings
from django.http import JsonResponse


class OriginVerifyMiddleware:
    """Refuses requests that did not come through CloudFront.

    CloudFront adds ``X-Origin-Verify`` with a value held in Secrets Manager. A
    client that reaches the ALB directly cannot know it, so it cannot forge the
    proxy headers the app trusts (``X-Forwarded-For`` and the HTTPS header).

    The ALB health check is answered by HealthCheckMiddleware, which runs
    earlier, so it does not need the secret. When no secret is configured the
    middleware is a no-op, which keeps local development and direct deployments
    working.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        secret = getattr(settings, "ORIGIN_VERIFY_SECRET", "")
        if secret:
            supplied = request.META.get("HTTP_X_ORIGIN_VERIFY", "")
            # Compare bytes: compare_digest() raises TypeError on non-ASCII
            # str, and a hostile header must get 403, not a 500.
            if not secrets.compare_digest(
                supplied.encode("utf-8", "surrogateescape"), secret.encode("utf-8")
            ):
                return JsonResponse(
                    {"errors": [{"field": "", "message": "Forbidden."}]}, status=403
                )
        return self.get_response(request)
