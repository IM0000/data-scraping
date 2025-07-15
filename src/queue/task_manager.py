"""
작업 생명주기 관리 모듈

RabbitMQ를 통한 작업 상태 추적 및 이벤트 발행을 담당합니다.
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
from ..models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from ..utils.logging import setup_logging


class TaskManager:
    """RabbitMQ 기반 작업 생명주기 관리 클래스"""

    def __init__(self, settings: Settings):
        """
        작업 매니저 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.task_history_exchange_obj: Optional[AbstractExchange] = None
        self.worker_status_exchange_obj: Optional[AbstractExchange] = None
        self.logger = setup_logging(settings)

        # Exchange 이름 정의
        self.task_history_exchange = "scraping.task.history"
        self.worker_status_exchange = "scraping.worker.status"

    async def connect(self) -> None:
        """RabbitMQ 연결 초기화"""
        try:
            self.connection = await connect_robust(
                self.settings.rabbitmq_url,
                client_properties={"connection_name": "task-manager"}
            )
            self.channel = await self.connection.channel()

            # Exchange 선언 및 객체 저장
            self.task_history_exchange_obj = await self.channel.declare_exchange(
                self.task_history_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            self.worker_status_exchange_obj = await self.channel.declare_exchange(
                self.worker_status_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            self.logger.info(f"작업 매니저 RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"작업 매니저 RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"작업 매니저 RabbitMQ 연결 실패: {e}") from e

    async def publish_task_started(self, request: ScrapingRequest) -> None:
        """작업 시작 이벤트 발행"""
        if not self.task_history_exchange_obj:
            return

        task_data = {
            "request_id": request.request_id,
            "script_name": request.script_name,
            "script_version": request.script_version,
            "parameters": request.parameters,
            "timeout": request.timeout,
            "created_at": request.created_at.isoformat(),
            "status": "started",
            "timestamp": datetime.now().isoformat()
        }

        routing_key = "task.started"

        message = Message(
            json.dumps(task_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.task_history_exchange_obj.publish(
            message,
            routing_key=routing_key
        )

        self.logger.info(f"작업 시작 이벤트 발행: {request.request_id}")

    async def publish_task_completion(self, response: ScrapingResponse) -> None:
        """작업 완료 이벤트 발행"""
        if not self.task_history_exchange_obj:
            return

        completion_data = {
            "request_id": response.request_id,
            "status": response.status.value,
            "data": response.data,
            "error": response.error,
            "execution_time": response.execution_time,
            "completed_at": response.completed_at.isoformat() if response.completed_at else None,
            "timestamp": datetime.now().isoformat()
        }

        routing_key = f"task.{response.status.value.lower()}"

        message = Message(
            json.dumps(completion_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.task_history_exchange_obj.publish(
            message,
            routing_key=routing_key
        )

        if response.status == TaskStatus.COMPLETED:
            self.logger.info(f"작업 완료 이벤트 발행: {response.request_id}")
        else:
            self.logger.error(f"작업 실패 이벤트 발행: {response.request_id} - {response.error}")

    async def publish_task_progress(self, request_id: str, progress: dict[str, Any]) -> None:
        """작업 진행 상황 이벤트 발행"""
        if not self.task_history_exchange_obj:
            return

        progress_data = {
            "request_id": request_id,
            "progress": progress,
            "timestamp": datetime.now().isoformat()
        }

        routing_key = "task.progress"

        message = Message(
            json.dumps(progress_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT  # 진행 상황은 영속성 불필요
        )

        await self.task_history_exchange_obj.publish(
            message,
            routing_key=routing_key
        )

        self.logger.debug(f"작업 진행 이벤트 발행: {request_id}")

    async def get_queue_metrics(self) -> dict[str, Any]:
        """RabbitMQ 큐 메트릭 조회"""
        if not self.connection:
            return {}

        try:
            # 기본적인 연결 상태 메트릭
            return {
                "task_queue": self.settings.rabbitmq_task_queue,
                "task_history_exchange": self.task_history_exchange,
                "worker_status_exchange": self.worker_status_exchange,
                "connection_status": "connected" if not self.connection.is_closed else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"큐 메트릭 조회 오류: {e}")
            return {}

    async def setup_task_history_consumer(self, history_handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """작업 히스토리 소비자 설정"""
        if not self.channel:
            return

        # 작업 히스토리 큐 선언
        history_queue = await self.channel.declare_queue(
            "scraping.task.history.consumer",
            durable=True
        )

        # Exchange와 큐 바인딩
        await history_queue.bind(
            self.task_history_exchange,
            routing_key="task.*"
        )

        async def process_history(message: Any) -> None:
            async with message.process():
                try:
                    history_data = json.loads(message.body.decode())
                    await history_handler(history_data)
                except Exception as e:
                    self.logger.error(f"작업 히스토리 처리 오류: {e}")

        await history_queue.consume(process_history)
        self.logger.info("작업 히스토리 소비자 시작됨")

    async def get_task_statistics(self, time_range_hours: int = 24) -> dict[str, Any]:
        """작업 통계 조회"""
        # 실제 구현에서는 데이터베이스나 캐시에서 통계를 조회
        # 여기서는 기본적인 구조만 제공
        return {
            "time_range_hours": time_range_hours,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "average_execution_time": 0.0,
            "timestamp": datetime.now().isoformat()
        }

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("작업 매니저 RabbitMQ 연결 해제 완료")
