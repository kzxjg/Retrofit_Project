# The Django API, for Amazon ECS (Fargate), App Runner or Elastic Beanstalk.
# The React page is not in here: build it separately and serve it from S3 +
# CloudFront (see DEPLOY.md).
#
#   docker build -t retrofit-api .
#   docker run --env-file prod.env -p 8000:8000 retrofit-api

FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Amazon RDS certificate bundle, so the app can check it is talking to the real
# database (DJANGO_DB_SSLMODE=verify-full below).
ADD --chmod=644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/certs/rds-global-bundle.pem

COPY manage.py gunicorn.conf.py ./
COPY config ./config
COPY recommendations ./recommendations

# Never run as root inside the container.
RUN useradd --system --uid 10001 --no-create-home app
USER app

# Safe production defaults; anything here can be overridden by the task definition.
ENV DJANGO_DEBUG=0 \
    DJANGO_DB_SSLMODE=verify-full \
    DJANGO_DB_SSLROOTCERT=/etc/ssl/certs/rds-global-bundle.pem \
    DJANGO_TRUST_PROXY_HEADERS=1 \
    DJANGO_TRUSTED_PROXY_COUNT=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

CMD ["gunicorn", "config.wsgi"]
