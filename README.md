# SAAS E2E — cross-service smoke suite

End-to-end **smoke** tests for the SAAS platform. There's no frontend yet, so
these are API-level smoke tests that drive the services the way a real client
would: **through the api-gateway, with a real Keycloak JWT**. They run as an
**ArgoCD PostSync hook** after each staging deploy (staging is the
test-equivalent env for now).

## What it covers

| Area | Path (via gateway) | Marker | Notes |
|------|--------------------|--------|-------|
| Gateway health | `/healthz/live`, `/healthz/ready` | `health` | no auth; fail-fast; unauth route is challenged |
| Auth (GraphQL) | `POST /api/auth/` | `auth` | `me`, invalid-query error, **register→login→refresh** lifecycle |
| Subscription | `/api/subscription/` | `subscription` | gRPC-only business — proxy wired + exercised via billing |
| Billing | `/api/v1/billing/invoices`, `/pay`, `/active` | `billing` | **invoice lifecycle**: create→read→pay, validation, 404 |
| Agent (req/resp) | `/api/v1/agent/conversations`, `/executions`, `/feedback` | `agent` | **conversation lifecycle** + messages + archive + feedback + run |
| **Agent SSE** | `POST /api/v1/agent/executions/stream` | `sse` | `text/event-stream`; multi-frame token stream |
| Usage (read API) | `/api/v1/usage/aggregates`, `/search` | `usage` | filter correctness + query/`k` validation |
| **Usage ETL** | Kafka `billing.usage-charge.created` → `/api/v1/usage/aggregates` | `usage_etl` | event-first; no sync endpoint |

The **usage-service is an ETL** (Kafka → ingest → aggregate → pgvector), so it
has no synchronous write path. Its smoke **produces one Avro
`UsageChargeCreated` event** (the exact contract billing emits) stamped with a
unique `metric`, then **polls the read API** until the aggregate appears —
proving the whole pipeline, not just a single pod.

## Tooling (best fit per concern)

- **pytest** — suite structure, markers, and the base for sharding later
  (`pytest-xdist` for parallel, `pytest-split --splits N --group K` for shards).
- **httpx** — HTTP smoke calls (sync client, bearer header).
- **httpx-sse** — the agent SSE stream (chunked `text/event-stream` framing).
- **confluent-kafka[avro]** + Schema Registry — producing the usage ETL event
  against the real Avro schema (`schemas/usage_charge_created.avsc`).
- **aws-msk-iam-sasl-signer** — MSK SASL/IAM auth for the in-cluster producer.
- **uv** + **ruff** + **black** — packaging/lint, matching usage-service.

## Run locally

```bash
uv sync
# health only (no creds needed):
uv run pytest -m health
# full smoke against a target:
E2E_GATEWAY_URL=https://api-staging.example.com \
E2E_KEYCLOAK_URL=https://keycloak-staging.example.com \
E2E_KEYCLOAK_CLIENT_ID=saas-e2e E2E_KEYCLOAK_CLIENT_SECRET=... \
E2E_KAFKA_BOOTSTRAP=... E2E_SCHEMA_REGISTRY_URL=... E2E_KAFKA_SECURITY=MSK_IAM \
uv run pytest -m smoke
```

Tests **skip** (not fail) when their prerequisites are unset: no Keycloak creds
skips the authenticated tests; no Kafka config skips the ETL pipeline test. So a
minimally-configured run still reports gateway health instead of a red suite.

## Local harness (docker compose)

`docker-compose.yml` runs the **whole stack** on one network: shared infra —
Kafka (PLAINTEXT), Apicurio ccompat registry, Keycloak (saas realm pre-imported
with a pinned local `saas-e2e` client), one Postgres backing every service DB,
Redis, Chroma — plus all six app services (auth, subscription, billing, agent,
usage-api, api-gateway), each built from its sibling repo and wired to the infra.
The api-gateway uses `local/gateway/app.yaml` (upstreams resolved to compose DNS).
Infra images are pinned by digest.

```bash
cp .env.example .env                 # optional (OPENAI_API_KEY for agent LLM paths)
docker compose up -d --build         # infra + all services (first build is slow)
docker compose ps                    # wait until services are healthy/up
docker compose run --rm e2e          # default: smoke, minus usage_etl
docker compose run --rm e2e -m health
```

Excluded (heavy): **Airflow**. A lightweight `usage-etl-consumer` (ingest only,
`--profile etl`) runs, but aggregate/embed need Airflow, so the usage-ETL
*pipeline* assertion isn't covered locally — the default `e2e` run is
`-m "smoke and not usage_etl"`. Everything else (gateway health, auth, billing,
subscription, agent incl. SSE) runs end to end.

Notes: service containers report "started" before their apps finish booting
(Spring apps take ~30–60s) — give `docker compose ps`/logs a moment before
running the suite. The `saas-e2e` client secret is pinned in the local realm for
dev convenience only; staging/prod generate it in-cluster.

## Configuration

All config is env-driven (`src/saas_e2e/config.py`). Key vars: `E2E_GATEWAY_URL`,
`E2E_KEYCLOAK_URL`/`_REALM`/`_CLIENT_ID`/`_CLIENT_SECRET`, `E2E_KAFKA_BOOTSTRAP`,
`E2E_SCHEMA_REGISTRY_URL`, `E2E_KAFKA_SECURITY` (`PLAINTEXT`|`MSK_IAM`),
`E2E_AGENT_MODEL`/`_PROVIDER`, `E2E_PIPELINE_TIMEOUT`.

## How it ships (GitOps)

1. CI (`.github/workflows/saas-e2e-ci.yml`): lint → build image → **Trivy gate**
   → push to the `saas-e2e` ECR repo → promote the tag into the CD repo's
   `e2e/chart/values-staging.yaml`.
2. ArgoCD `e2e` ApplicationSet (`appsets/e2e.yaml`, **staging cluster only**,
   sync-wave 3) renders the chart; the suite runs as a **PostSync hook Job**
   that re-executes on every sync.
3. A failing smoke fails the hook → the `e2e-staging` Application goes
   **Degraded**, surfacing the bad deploy — without touching the services.

Chart + appset live in the CD repo (`SAAS-Continious-Delivery/e2e/`,
`appsets/e2e.yaml`); this repo owns the test code and the image.

## Sharding (later)

Not needed while this is API smoke (runs in seconds). When a frontend lands and
the suite grows, split with `pytest-split` across parallel Argo Workflow steps
or a CI matrix — the marker layout already keeps `usage_etl`/`sse` separable
from the fast HTTP smokes.

## Caution on staging

These run against real staging infra. Tests tag data they create with a per-run
id (`E2E_RUN_ID`) and target it by unique `metric`/title; keep write paths
idempotent and scoped to an `e2e-*` test tenant.
