# The Django API, for Amazon ECS (Fargate), App Runner or Elastic Beanstalk.
# The React page is not in here: build it separately and serve it from S3 +
# CloudFront (see DEPLOY.md).
#
#   docker build -t retrofit-api .
#   docker run --env-file prod.env -p 8000:8000 retrofit-api

FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

# Amazon RDS certificate bundle, so the app can check it is talking to the real
# database (DJANGO_DB_SSLMODE=verify-full below). The checksum pins the trust
# anchor: a substituted CA would let an attacker MITM the database.
ADD --chmod=644 --checksum=sha256:90a6f1a7978a1b1b096dca6c57511ca48d3b8cf052f8e704baf358f34ea2f21b \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    /etc/ssl/certs/rds-global-bundle.pem

COPY manage.py gunicorn.conf.py ./
COPY config ./config
COPY recommendations ./recommendations

# Never run as root inside the container.
RUN useradd --system --uid 10001 --no-create-home app
USER app

# Safe production defaults; anything here can be overridden by the task definition.
# The image trusts no proxy on its own: run with nothing in front, a client could
# otherwise forge X-Forwarded-For (a fresh rate-limit allowance per request) and
# the HTTPS header. The deployment that really has the proxies turns trust on
# (DJANGO_TRUST_PROXY_HEADERS=1, DJANGO_TRUSTED_PROXY_COUNT=2; see DEPLOY.md).
# DJANGO_IN_CONTAINER makes settings refuse DJANGO_DEBUG=1 here, on any host.
ENV DJANGO_DEBUG=0 \
    DJANGO_IN_CONTAINER=1 \
    DJANGO_DB_SSLMODE=verify-full \
    DJANGO_DB_SSLROOTCERT=/etc/ssl/certs/rds-global-bundle.pem \
    DJANGO_TRUST_PROXY_HEADERS=0 \
    DJANGO_TRUSTED_PROXY_COUNT=0

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

CMD ["gunicorn", "config.wsgi"]
