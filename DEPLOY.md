# Deploying to AWS

The tool has two parts, deployed separately:

| Part | What it is | Where it runs |
| --- | --- | --- |
| Page | The React app in `frontend/`, built to static files | S3 bucket behind CloudFront |
| API | The Django app (`config/`, `recommendations/`) in the `Dockerfile` | ECS Fargate (or App Runner) behind an Application Load Balancer |

The page and the API must be on **one address**: CloudFront sends `/api/*` to the
load balancer and everything else to S3. Leave `VITE_API_URL` unset when you
build the page. On a separate API address the browser would need CORS, which the
API does not allow, so every form submission would fail.

**No domain yet?** That's fine. Every CloudFront distribution gets its own HTTPS
address like `d1234abcd.cloudfront.net`; use that until the domain is chosen. See
[Before there is a domain](#before-there-is-a-domain) for the two settings that
differ, and [Adding the domain later](#adding-the-domain-later) for the switch.

```
browser ──https──▶ CloudFront ─┬─ /api/*  ──https──▶ ALB ──http──▶ ECS tasks (gunicorn + Django)
                               │                                    │        │
                               └─ default ─────────▶ S3 (page)      ▼        ▼
                                                              ElastiCache   RDS PostgreSQL
                                                              (rate limit)  (not used yet)
```

## 1. Database: RDS for PostgreSQL

- Keep it in private subnets, reachable only from the API tasks' security group.
- Put the password in Secrets Manager and pass it to the task as `DJANGO_DB_PASSWORD`.
- The image checks the server certificate (`DJANGO_DB_SSLMODE=verify-full`), using the RDS
  certificate bundle it downloads at build time.
- The app stores nothing in the database yet; no request opens a connection. Still,
  run the migrations once per release, as a one-off ECS task with the same image:
  `python manage.py migrate`. Then any future table is created the same way.

## 2. Cache: ElastiCache (Redis or Valkey)

Holds the rate-limit counts so that every task shares one allowance per visitor.

- Turn on in-transit encryption and set `DJANGO_REDIS_URL=rediss://<endpoint>:6379/0`
  (production refuses `redis://` and refuses to start without a shared cache).
- If the cache is unreachable, a circuit breaker opens after three failures and
  each process applies a local fallback limit, so an outage degrades the limit
  instead of removing it. Errors are logged.
- `python manage.py check --deploy` warns (`recommendations.W001`) only for a
  development-style LocMem cache.

## 3. API: image, task and load balancer

Build and push the image to ECR:

```bash
docker build -t retrofit-api .
```

Task definition environment (see `.env.example` for all of them):

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | From Secrets Manager. At least 50 random characters. |
| `DJANGO_ALLOWED_HOSTS` | The public address: `d1234abcd.cloudfront.net` for now, later also your domain. Required. |
| `DJANGO_DB_NAME`, `_USER`, `_HOST`, `_PASSWORD` | The RDS database |
| `DJANGO_REDIS_URL` | `rediss://…` (required) |
| `DJANGO_TRUST_PROXY_HEADERS` | `1` behind the ALB. Required: with `0` every request is redirected to HTTPS forever. |
| `DJANGO_TRUSTED_PROXY_COUNT` | `2` behind CloudFront + ALB. Required: with `0` every visitor shares one rate-limit allowance. |
| `DJANGO_ORIGIN_VERIFY_SECRET` | From Secrets Manager. CloudFront adds it as `X-Origin-Verify`. |
| `GUNICORN_WORKERS` | About 2 × vCPUs + 1 (default 3) |

The image already sets `DJANGO_DEBUG=0`. It trusts no proxy by default
(`DJANGO_TRUST_PROXY_HEADERS=0`, `DJANGO_TRUSTED_PROXY_COUNT=0`), so that run on
its own a client cannot forge its address; the two rows above turn trust on
for this deployment.

Target group:

- Protocol HTTP, port 8000, health check path `/api/health`, success code `200`.
  The health check needs no `ALLOWED_HOSTS` entry and is not redirected to HTTPS.
- Listener: HTTPS (443) with an ACM certificate once there is a domain;
  HTTP (80) before that (see below).

Before going live, run the deploy check inside the image with the production
variables. It should report no issues:

```bash
python manage.py check --deploy
```

## 4. Page: S3 + CloudFront

```bash
npm --prefix frontend ci
```

```bash
npm --prefix frontend run build
```

Upload `frontend/dist/` to a private S3 bucket, read by CloudFront through Origin Access Control.

CloudFront distribution:

- Default behavior → the S3 origin.
- Behavior `/api/*` → the ALB origin, with:
  - Origin protocol policy **HTTPS only** once there is a domain, so the ALB tells
    Django the request was HTTPS (before that, see below).
  - Cache policy **CachingDisabled**.
  - Origin request policy **AllViewerAndCloudFrontHeaders-2022-06** (forwards the
    `Host` header and `CloudFront-Forwarded-Proto`). Without
    the Host header, Django sees the ALB's own name and answers 400.
  - Allowed methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE.
  - Add an origin request header `X-Origin-Verify: <DJANGO_ORIGIN_VERIFY_SECRET>`
    (CloudFront custom header, value from Secrets Manager).
- Add the security headers as a response headers policy, including the same
  Content-Security-Policy the build puts in `index.html` plus `frame-ancestors 'none'`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and HSTS.
- Put an AWS WAF rate-based rule on the distribution as an independent second
  layer, so an attacker cannot use up the application's per-IP allowance.

**Lock the ALB to CloudFront.** With a VPC origin (below) the ALB is internal and
only CloudFront can reach it. With a public ALB, allow inbound 443 on its security
group only from the AWS-managed prefix list
`com.amazonaws.global.cloudfront.origin-facing`. Either way, nothing but
CloudFront may reach the ALB: `DJANGO_TRUSTED_PROXY_COUNT=2` trusts the address
CloudFront adds to `X-Forwarded-For`, and `CloudFront-Forwarded-Proto` is trusted
as CloudFront's. Anyone reaching the ALB directly could write both themselves and
dodge the rate limit, so also require `X-Origin-Verify` (the app returns 403
without it) and add an ALB listener rule that returns 403 when it is absent.

## Before there is a domain

An ALB can only serve HTTPS with an ACM certificate, and ACM only issues
certificates for domains you own. So until there is a domain:

- Visitors still get HTTPS, from CloudFront's own `*.cloudfront.net` certificate.
- CloudFront reaches the ALB over **HTTP**. Make the ALB **internal** and connect it
  with a CloudFront **VPC origin**, so that hop never leaves AWS's network and
  nothing else can reach the ALB at all. (A public ALB over HTTP would send the
  answers across the internet unencrypted, and would let anyone skip CloudFront.)
- The ALB now tells Django every request was HTTP, so Django would redirect it to
  HTTPS forever. Have Django read CloudFront's header instead:

| Variable | Before a domain | After |
| --- | --- | --- |
| `DJANGO_ALLOWED_HOSTS` | `d1234abcd.cloudfront.net` | `retrofit.example.com,d1234abcd.cloudfront.net` |
| `DJANGO_PROXY_SSL_HEADER` | `CloudFront-Forwarded-Proto` | `X-Forwarded-Proto` (or leave unset) |
| CloudFront → ALB | HTTP, VPC origin | HTTPS only |
| ALB listener | HTTP 80 | HTTPS 443, ACM certificate for the domain |

`DJANGO_TRUSTED_PROXY_COUNT` stays `2` either way. After the first deploy, check
in the CloudWatch logs that the rate limit sees visitors' addresses and not
CloudFront's: two visitors from different networks must not share an allowance.

## Adding the domain later

1. Request an ACM certificate for the domain: in **us-east-1** for CloudFront, and
   in the ALB's region for the ALB.
2. CloudFront: add the domain as an alternate domain name, with the us-east-1 certificate.
3. DNS: point the domain at the distribution (a Route 53 alias, or a CNAME elsewhere).
4. ALB: add an HTTPS listener with the regional certificate; set CloudFront's
   origin protocol to HTTPS only.
5. Task: add the domain to `DJANGO_ALLOWED_HOSTS` and set
   `DJANGO_PROXY_SSL_HEADER=X-Forwarded-Proto`, then redeploy.

The page does not need rebuilding: it calls `/api/...` on whatever address it was loaded from.

## 5. Logs

The API and gunicorn log to standard output; ECS sends that to CloudWatch Logs
with the `awslogs` driver. Errors are logged with their tracebacks. Set
`DJANGO_LOG_LEVEL` to `WARNING` to keep only problems. Answers to the
questionnaire (postal code and so on) are never logged.

## 6. HSTS preload

Production sends `Strict-Transport-Security` with `includeSubDomains; preload`.
On the `cloudfront.net` address this does nothing beyond HTTPS-only for that one
address; it matters once the real domain is in use.
Do not submit the domain to hstspreload.org unless every subdomain, now and
later, will only ever use HTTPS: removal takes months. To send HSTS without it,
set `DJANGO_SECURE_HSTS_SECONDS` lower or change the settings.
