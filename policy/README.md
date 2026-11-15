# Policy as Code

Conftest / OPA (Rego) policies, matching the convention in the service repos.

## `policy/docker` — Dockerfile guardrails

`main.rego` enforces Dockerfile best practices against the repo's `Dockerfile`
(parsed with conftest's `dockerfile` parser):

- **deny** (blocking): base images pinned to an explicit non-latest tag or digest;
  the final effective `USER` is non-root; no `ADD` of a remote URL.
- **warn** (advisory): missing `HEALTHCHECK`, tag-only (non-digest) base pins,
  `apt-get install` without `--no-install-recommends`, `latest`-artifact fetches,
  and secrets baked via `ENV`.

`main_test.rego` are the Rego unit tests (`conftest verify`).

## Run locally

```bash
conftest verify -p policy/docker
conftest test Dockerfile --parser dockerfile -p policy/docker
```

Runs in CI via `.github/workflows/security.yml`.
