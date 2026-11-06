"""Gunicorn settings for running the API in production (see DEPLOY.md).

    gunicorn config.wsgi

Gunicorn reads this file from the working directory on its own.
"""

import os


def _whole_number(name, default):
    raw = os.environ.get(name, "").strip() or str(default)
    if not raw.isascii() or not raw.isdigit() or int(raw) < 1:
        raise SystemExit(f"{name} must be a whole number of 1 or more.")
    return int(raw)


# The load balancer connects to this port. App Runner and some platforms set PORT.
bind = f"0.0.0.0:{_whole_number('PORT', 8000)}"

# Each request is short and CPU-bound. In a container, os.cpu_count() reports the
# host's CPUs rather than the task's share, so set GUNICORN_WORKERS to about
# 2 x vCPUs + 1 for the task size (3 suits a 1 vCPU ECS task).
workers = _whole_number("GUNICORN_WORKERS", 3)
timeout = _whole_number("GUNICORN_TIMEOUT", 30)
graceful_timeout = 30

# Restart workers now and then so a slow leak can never build up.
max_requests = 1000
max_requests_jitter = 100

# Logs to stdout/stderr, which the container platform sends to CloudWatch Logs.
accesslog = "-"
errorlog = "-"

# Heartbeat files in memory: the container's disk can be slow or read-only.
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
