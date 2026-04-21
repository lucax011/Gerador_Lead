import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage

logger = logging.getLogger(__name__)

DEAD_LETTER_EXCHANGE = "lead.dlx"
DEAD_LETTER_QUEUE = "lead.rejected"


class RabbitMQPublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(
            self._url,
            reconnect_interval=5,
        )
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            "leads",
            ExchangeType.TOPIC,
            durable=True,
        )
        # Ensure dead-letter infrastructure exists
        dlx = await self._channel.declare_exchange(DEAD_LETTER_EXCHANGE, ExchangeType.FANOUT, durable=True)
        dlq = await self._channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dlq.bind(dlx)
        logger.info("RabbitMQPublisher connected")

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if self._exchange is None:
            raise RuntimeError("Publisher not connected. Call connect() first.")
        body = json.dumps(payload, default=str).encode()
        message = Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)
        logger.debug("Published event", extra={"routing_key": routing_key, "payload_size": len(body)})

    async def publish_to_dead_letter(self, payload: dict[str, Any], reason: str) -> None:
        payload["rejection_reason"] = reason
        await self.publish(DEAD_LETTER_QUEUE, payload)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()


class RabbitMQConsumer:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(
            self._url,
            reconnect_interval=5,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # Declare shared exchange
        await self._channel.declare_exchange("leads", ExchangeType.TOPIC, durable=True)

        # Ensure dead-letter infrastructure exists
        dlx = await self._channel.declare_exchange(DEAD_LETTER_EXCHANGE, ExchangeType.FANOUT, durable=True)
        dlq = await self._channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dlq.bind(dlx)
        logger.info("RabbitMQConsumer connected")

    async def consume(
        self,
        queue_name: str,
        routing_key: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if self._channel is None:
            raise RuntimeError("Consumer not connected. Call connect() first.")

        exchange = await self._channel.get_exchange("leads")
        queue = await self._channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-message-ttl": 86_400_000,  # 24h TTL on failed messages
            },
        )
        await queue.bind(exchange, routing_key=routing_key)

        async def _on_message(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                try:
                    payload = json.loads(message.body)
                    logger.info("Received message", extra={"routing_key": routing_key, "queue": queue_name})
                    await handler(payload)
                except Exception:
                    logger.exception("Error processing message — routing to dead-letter")
                    raise

        await queue.consume(_on_message)
        logger.info("Consuming queue", extra={"queue": queue_name, "routing_key": routing_key})

        # Keep running until cancelled
        await asyncio.Future()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
