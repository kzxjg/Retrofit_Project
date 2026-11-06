from django.http import JsonResponse

HEALTH_PATH = "/api/health"


class HealthCheckMiddleware:
    """Answers GET/HEAD /api/health before the host check.

    An AWS load balancer checks each container at its private IP address (for
    example Host: 10.0.1.23), which is not in ALLOWED_HOSTS, so the normal host
    check would answer 400 and the load balancer would never send traffic. The
    reply says only {"status": "ok"}, so answering it for any host leaks nothing.

    It sits after SecurityMiddleware, XFrameOptionsMiddleware and the CSP
    middleware so the reply still carries their headers, and before
    CommonMiddleware, which does the host check. SECURE_REDIRECT_EXEMPT keeps
    SecurityMiddleware from redirecting the plain-HTTP check to HTTPS. Every
    other path, and any other method on this one, goes through every check.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == HEALTH_PATH and request.method in ("GET", "HEAD"):
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
