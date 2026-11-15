"""Avro producer for the usage-ETL event-first smoke.

The usage-service is an event-driven ETL (Kafka -> ingest -> aggregate ->
pgvector); it has no synchronous write endpoint. To smoke it end-to-end we
produce one synthetic ``UsageChargeCreated`` event (the exact Avro contract
billing emits onto ``billing.usage-charge.created``) stamped with a unique
``metric`` for this run, then poll the usage read API until the aggregate
appears.

Security:
  * ``PLAINTEXT``  -> local docker-compose Kafka.
  * ``MSK_IAM``    -> staging MSK (SASL_SSL / OAUTHBEARER) using the Job's
    IAM role via ``aws-msk-iam-sasl-signer``.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

from .config import Settings

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "usage_charge_created.avsc"


def _oauth_cb(settings: Settings):
    """MSK IAM OAUTHBEARER token callback (librdkafka contract)."""
    from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

    def cb(_config: str):
        token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(settings.aws_region)
        return token, time.time() + expiry_ms / 1000.0

    return cb


def _producer_config(settings: Settings) -> dict:
    conf: dict = {"bootstrap.servers": settings.kafka_bootstrap}
    if settings.kafka_security == "MSK_IAM":
        conf.update(
            {
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "OAUTHBEARER",
                "oauth_cb": _oauth_cb(settings),
            }
        )
    return conf


def _avro_serializer(settings: Settings) -> AvroSerializer:
    sr = SchemaRegistryClient({"url": settings.schema_registry_url})
    schema_str = SCHEMA_PATH.read_text()
    # auto-register the subject if absent (matches billing's Confluent serializer
    # default), so the ETL smoke works even before billing has produced.
    return AvroSerializer(sr, schema_str, conf={"auto.register.schemas": True})


def produce_usage_charge(settings: Settings, *, metric: str, quantity: int = 7) -> dict:
    """Produce one UsageChargeCreated event; return the payload for assertions."""
    invoice_id = str(uuid4())
    payload = {
        "usageChargeId": str(uuid4()),
        "invoiceId": invoice_id,
        "metric": metric,
        "quantity": quantity,
        "unitPrice": Decimal("0.10"),
        "totalPrice": Decimal("0.10") * quantity,
        "createdAt": int(time.time() * 1000),
    }

    serializer = _avro_serializer(settings)
    producer = Producer(_producer_config(settings))
    ctx = SerializationContext(settings.kafka_topic, MessageField.VALUE)

    delivery: dict = {}

    def _on_delivery(err, msg):
        delivery["err"] = err
        delivery["partition"] = None if err else msg.partition()

    producer.produce(
        topic=settings.kafka_topic,
        key=invoice_id,
        value=serializer(payload, ctx),
        on_delivery=_on_delivery,
    )
    producer.flush(settings.http_timeout)

    if delivery.get("err") is not None:
        raise RuntimeError(f"Kafka delivery failed: {delivery['err']}")

    return payload


if __name__ == "__main__":  # manual smoke: python -m saas_e2e.kafka_producer
    print(json.dumps({"schema": str(SCHEMA_PATH)}, indent=2))
