"""
워커 상태 모니터링 모듈

RabbitMQ를 통한 워커 상태 추적 및 하트비트 관리를 담당합니다.
"""

import json
from collections.abc import Awaitable
from datetime import datetime
from typing import Any, Callable, Optional

import aio_pika
from aio_pika import Message, connect_robust
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange

from ..config.settings import Settings
from ..exceptions import QueueConnectionException
from ..utils.logging import setup_logging


class WorkerMonitor:
    """RabbitMQ 기반 워커 상태 모니터링 클래스"""

    def __init__(self, settings: Settings):
        """
        워커 모니터 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.worker_status_exchange_obj: Optional[AbstractExchange] = None
        self.logger = setup_logging(settings)
        self.heartbeat_timeout = 60  # 1분

        # Exchange와 큐 이름 정의
        self.worker_status_exchange = "scraping.worker.status"
        self.heartbeat_queue = "scraping.worker.heartbeat"
        self.worker_registry_queue = "scraping.worker.registry"

    async def connect(self) -> None:
        """RabbitMQ 연결 초기화"""
        try:
            self.connection = await connect_robust(
                self.settings.rabbitmq_url,
                client_properties={"connection_name": "worker-monitor"}
            )
            self.channel = await self.connection.channel()

            # Exchange 선언 및 객체 저장
            self.worker_status_exchange_obj = await self.channel.declare_exchange(
                self.worker_status_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # 하트비트 큐 선언
            await self.channel.declare_queue(
                self.heartbeat_queue,
                durable=True
            )

            # 워커 등록 큐 선언
            await self.channel.declare_queue(
                self.worker_registry_queue,
                durable=True
            )

            self.logger.info(f"워커 모니터 RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"워커 모니터 RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"워커 모니터 RabbitMQ 연결 실패: {e}") from e

    async def publish_worker_status(self, worker_id: str, status: str, metadata: Optional[dict] = None) -> None:
        """워커 상태 발행"""
        if not self.worker_status_exchange_obj:
            return

        worker_data = {
            "worker_id": worker_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        routing_key = f"worker.{status}"

        message = Message(
            json.dumps(worker_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.worker_status_exchange_obj.publish(
            message,
            routing_key=routing_key
        )

        self.logger.info(f"워커 상태 발행: {worker_id} -> {status}")

    async def register_worker(self, worker_id: str, worker_info: dict[str, Any]) -> None:
        """워커 등록"""
        if not self.channel:
            return

        registration_data = {
            "worker_id": worker_id,
            "action": "register",
            "worker_info": worker_info,
            "timestamp": datetime.now().isoformat()
        }

        message = Message(
            json.dumps(registration_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.worker_registry_queue
        )

        self.logger.info(f"워커 등록: {worker_id}")

    async def unregister_worker(self, worker_id: str) -> None:
        """워커 등록 해제"""
        if not self.channel:
            return

        unregistration_data = {
            "worker_id": worker_id,
            "action": "unregister",
            "timestamp": datetime.now().isoformat()
        }

        message = Message(
            json.dumps(unregistration_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.worker_registry_queue
        )

        self.logger.info(f"워커 등록 해제: {worker_id}")

    async def send_heartbeat(self, worker_id: str, stats: Optional[dict] = None) -> None:
        """워커 하트비트 전송"""
        if not self.channel:
            return

        heartbeat_data = {
            "worker_id": worker_id,
            "timestamp": datetime.now().isoformat(),
            "stats": stats or {}
        }

        message = Message(
            json.dumps(heartbeat_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT  # 하트비트는 영속성 불필요
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.heartbeat_queue
        )

        self.logger.debug(f"하트비트 전송: {worker_id}")

    async def start_heartbeat_consumer(self, heartbeat_handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """하트비트 소비자 시작"""
        if not self.channel:
            return

        queue = await self.channel.declare_queue(
            self.heartbeat_queue,
            durable=True
        )

        async def process_heartbeat(message: Any) -> None:
            async with message.process():
                try:
                    heartbeat_data = json.loads(message.body.decode())
                    await heartbeat_handler(heartbeat_data)
                except Exception as e:
                    self.logger.error(f"하트비트 처리 오류: {e}")

        await queue.consume(process_heartbeat)
        self.logger.info("하트비트 소비자 시작됨")

    async def start_worker_registry_consumer(self, registry_handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """워커 등록 소비자 시작"""
        if not self.channel:
            return

        queue = await self.channel.declare_queue(
            self.worker_registry_queue,
            durable=True
        )

        async def process_registry(message: Any) -> None:
            async with message.process():
                try:
                    registry_data = json.loads(message.body.decode())
                    await registry_handler(registry_data)
                except Exception as e:
                    self.logger.error(f"워커 등록 처리 오류: {e}")

        await queue.consume(process_registry)
        self.logger.info("워커 등록 소비자 시작됨")

    async def start_worker_status_consumer(self, status_handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """워커 상태 소비자 시작"""
        if not self.channel:
            return

        # 워커 상태 큐 선언
        status_queue = await self.channel.declare_queue(
            "scraping.worker.status.consumer",
            durable=True
        )

        # Exchange와 큐 바인딩
        await status_queue.bind(
            self.worker_status_exchange,
            routing_key="worker.*"
        )

        async def process_status(message: Any) -> None:
            async with message.process():
                try:
                    status_data = json.loads(message.body.decode())
                    await status_handler(status_data)
                except Exception as e:
                    self.logger.error(f"워커 상태 처리 오류: {e}")

        await status_queue.consume(process_status)
        self.logger.info("워커 상태 소비자 시작됨")

    async def get_worker_metrics(self) -> dict[str, Any]:
        """워커 메트릭 조회"""
        if not self.connection:
            return {}

        try:
            # 기본적인 메트릭 정보
            return {
                "heartbeat_queue": self.heartbeat_queue,
                "worker_status_exchange": self.worker_status_exchange,
                "worker_registry_queue": self.worker_registry_queue,
                "connection_status": "connected" if not self.connection.is_closed else "disconnected",
                "heartbeat_timeout": self.heartbeat_timeout,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"워커 메트릭 조회 오류: {e}")
            return {}

    async def check_worker_health(self, last_heartbeats: dict[str, datetime]) -> list[str]:
        """워커 상태 확인 및 비정상 워커 목록 반환"""
        unhealthy_workers = []
        current_time = datetime.now()

        for worker_id, last_heartbeat in last_heartbeats.items():
            if (current_time - last_heartbeat).total_seconds() > self.heartbeat_timeout:
                unhealthy_workers.append(worker_id)
                self.logger.warning(f"워커 하트비트 타임아웃: {worker_id}")

        return unhealthy_workers

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("워커 모니터 RabbitMQ 연결 해제 완료")
