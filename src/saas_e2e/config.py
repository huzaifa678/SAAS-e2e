"""Environment-driven configuration for the SAAS end-to-end smoke suite.

Every knob is an env var so the same image runs unchanged from a laptop
(`docker run`), a CI job, or the in-cluster ArgoCD PostSync hook — only the
values change. Defaults point at the in-cluster service DNS names so the
ArgoCD-delivered Job needs almost no config beyond secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4


def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:

    gateway_url: str = os.getenv(
        "E2E_GATEWAY_URL",
        "http://saas-api-service.saas-apps.svc.cluster.local",
    )

    keycloak_url: str = os.getenv(
        "E2E_KEYCLOAK_URL",
        "http://keycloak-http.keycloak.svc.cluster.local",
    )
    keycloak_realm: str = os.getenv("E2E_KEYCLOAK_REALM", "saas")
    keycloak_client_id: str = os.getenv("E2E_KEYCLOAK_CLIENT_ID", "")
    keycloak_client_secret: str = os.getenv("E2E_KEYCLOAK_CLIENT_SECRET", "")
    keycloak_username: str = os.getenv("E2E_KEYCLOAK_USERNAME", "")
    keycloak_password: str = os.getenv("E2E_KEYCLOAK_PASSWORD", "")

    kafka_bootstrap: str = os.getenv("E2E_KAFKA_BOOTSTRAP", "")
    schema_registry_url: str = os.getenv("E2E_SCHEMA_REGISTRY_URL", "")
    kafka_topic: str = os.getenv("E2E_KAFKA_TOPIC", "billing.usage-charge.created")
    kafka_security: str = os.getenv("E2E_KAFKA_SECURITY", "PLAINTEXT").upper()
    aws_region: str = os.getenv("E2E_AWS_REGION", os.getenv("AWS_REGION", "us-east-1"))

    agent_model: str = os.getenv("E2E_AGENT_MODEL", "gpt-4o-mini")
    agent_provider: str = os.getenv("E2E_AGENT_PROVIDER", "openai")
    tenant_id: str = os.getenv("E2E_TENANT_ID", str(uuid4()))
    user_id: str = os.getenv("E2E_USER_ID", str(uuid4()))

    http_timeout: float = float(os.getenv("E2E_HTTP_TIMEOUT", "15"))
    sse_timeout: float = float(os.getenv("E2E_SSE_TIMEOUT", "60"))
    pipeline_timeout: float = float(os.getenv("E2E_PIPELINE_TIMEOUT", "300"))
    poll_interval: float = float(os.getenv("E2E_POLL_INTERVAL", "5"))

    verify_tls: bool = field(default_factory=lambda: _b("E2E_VERIFY_TLS", True))

    run_id: str = os.getenv("E2E_RUN_ID", uuid4().hex[:12])

    @property
    def has_oidc_client(self) -> bool:
        return bool(self.keycloak_client_id and self.keycloak_client_secret)

    @property
    def has_oidc_password(self) -> bool:
        return bool(self.keycloak_username and self.keycloak_password)

    @property
    def can_auth(self) -> bool:
        return self.has_oidc_client or self.has_oidc_password

    @property
    def can_kafka(self) -> bool:
        return bool(self.kafka_bootstrap and self.schema_registry_url)


settings = Settings()
