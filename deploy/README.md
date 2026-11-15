# Delivery

This repo builds and ships the **e2e-runner image** only. The ArgoCD delivery
config (Helm chart + ApplicationSet) lives in the CD repo, where all GitOps
config belongs:

- Chart: `SAAS-Continious-Delivery/e2e/chart/`
- ApplicationSet: `SAAS-Continious-Delivery/appsets/e2e.yaml`

CI here promotes the freshly scanned image tag into
`e2e/chart/values-staging.yaml` in the CD repo; ArgoCD runs the new runner as a
`PostSync` hook on its next staging sync.
