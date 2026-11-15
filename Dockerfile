# syntax=docker/dockerfile:1

############################
# Builder: resolve deps with uv into a venv
############################
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.11@sha256:0ac957607303916420297a4c9c213bb33fbd3c888f9cd7f4f7273596ebf42b85 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
# Install only runtime deps against the lockfile (no dev group, no project).
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null \
    || uv sync --no-dev --no-install-project

############################
# Runtime: slim, non-root
############################
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Security patches for CVEs Trivy flags in the base image:
#  - OS: upgrade zlib1g to the Debian security build.
#  - Python: strip the base image's build tooling (pip / setuptools / wheel and
#    setuptools' *vendored* wheel + jaraco.context, which carry the CVEs). It is
#    unused at runtime — the app runs from the isolated /opt/venv
#    (include-system-site-packages=false), so removing it is safe and shrinks the
#    image. A plain `pip upgrade` cannot fix the copies vendored inside setuptools.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/pkg_resources \
        /usr/local/lib/python3.11/site-packages/_distutils_hack \
        /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/wheel* \
        /usr/local/lib/python3.11/site-packages/jaraco* \
        /usr/local/lib/python3.11/ensurepip \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

# confluent-kafka wheels bundle librdkafka; no apt build deps needed.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin e2e

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY src ./src
COPY schemas ./schemas
COPY tests ./tests
COPY pyproject.toml ./

USER 10001

# Exit non-zero on any failure so ArgoCD marks the PostSync hook (and the
# Application) degraded. JUnit XML is emitted for CI artifact collection.
ENTRYPOINT ["pytest"]
CMD ["-m", "smoke", "--junitxml=/tmp/results/report.xml"]
