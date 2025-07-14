"""
RabbitMQ RPC 통신 모듈

Gateway-Worker 간 RPC 패턴을 사용한 비동기 통신을 제공합니다.
correlation_id와 reply_to 큐를 사용하여 동기적 응답을 지원합니다.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Callable, Optional, Any

from aio_pika import DeliveryMode, Message, connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractIncomingMessage,
    AbstractQueue,
)

from ..config.settings import Settings
from ..exceptions import QueueConnectionException
from ..models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from ..utils.logging import setup_logging


class RabbitMQRPC:
    """RabbitMQ 기반 RPC 통신 클래스"""

    def __init__(self, settings: Settings):
        """
        RabbitMQ RPC 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.callback_queue: Optional[AbstractQueue] = None
        self.futures: dict[str, asyncio.Future[Any]] = {}
        self.logger = setup_logging(settings)

        # 큐 이름 정의
        self.task_queue_name = settings.rabbitmq_task_queue
        self.reply_queue_name = None  # 동적 생성

    async def connect(self) -> None:
        """RabbitMQ 연결 초기화"""
        try:
            self.connection = await connect_robust(
                self.settings.rabbitmq_url,
                client_properties={"connection_name": "gateway-rpc-client"}
            )
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)

            # 작업 큐 선언 (워커가 소비할 큐)
            await self.channel.declare_queue(
                self.task_queue_name,
                durable=True
            )

            self.logger.info(f"RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"RabbitMQ 연결 실패: {e}")

    async def setup_callback_queue(self) -> None:
        """응답 수신용 콜백 큐 설정"""
        if not self.channel:
            raise QueueConnectionException("RabbitMQ 채널이 초기화되지 않았습니다")

        # 익스클루시브 큐 생성 (클라이언트별 고유)
        self.callback_queue = await self.channel.declare_queue(
            exclusive=True,
            auto_delete=True
        )
        self.reply_queue_name = self.callback_queue.name

        # 콜백 메시지 소비 시작
        await self.callback_queue.consume(
            self._on_response,
            no_ack=True
        )

        self.logger.info(f"콜백 큐 설정 완료: {self.reply_queue_name}")

    async def _on_response(self, message: AbstractIncomingMessage) -> None:
        """응답 메시지 처리"""
        correlation_id = message.correlation_id

        if correlation_id in self.futures:
            future = self.futures.pop(correlation_id)
            if not future.done():
                try:
                    response_data = json.loads(message.body.decode())
                    response = ScrapingResponse(**response_data)
                    future.set_result(response)
                    self.logger.info(f"응답 수신 완료: {correlation_id}")
                except Exception as e:
                    future.set_exception(e)
                    self.logger.error(f"응답 처리 오류: {correlation_id}, {e}")

    async def call_async(self, request: ScrapingRequest, timeout: int = 300) -> ScrapingResponse:
        """비동기 RPC 호출"""
        if not self.channel or not self.callback_queue:
            raise QueueConnectionException("RabbitMQ가 초기화되지 않았습니다")

        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()
        self.futures[correlation_id] = future

        # 요청 메시지 생성
        request_data = {
            "request_id": request.request_id,
            "script_name": request.script_name,
            "script_version": request.script_version,
            "parameters": request.parameters,
            "timeout": request.timeout,
            "created_at": request.created_at.isoformat()
        }

        message = Message(
            json.dumps(request_data).encode(),
            correlation_id=correlation_id,
            reply_to=self.reply_queue_name,
            delivery_mode=DeliveryMode.PERSISTENT
        )

        # 메시지 발송
        await self.channel.default_exchange.publish(
            message,
            routing_key=self.task_queue_name
        )

        self.logger.info(f"RPC 요청 발송: {correlation_id} -> {request.script_name}")

        try:
            # 응답 대기 (타임아웃 포함)
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            # 타임아웃 시 future 정리
            self.futures.pop(correlation_id, None)
            self.logger.error(f"RPC 요청 타임아웃: {correlation_id}")
            raise TimeoutError(f"RPC 요청 타임아웃: {correlation_id}")
        except Exception as e:
            self.futures.pop(correlation_id, None)
            self.logger.error(f"RPC 요청 오류: {correlation_id}, {e}")
            raise

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("RabbitMQ 연결 해제 완료")


class RabbitMQWorker:
    """워커용 RabbitMQ 클라이언트"""

    def __init__(self, settings: Settings, task_handler: Callable):
        """
        RabbitMQ 워커 초기화

        Args:
            settings: 시스템 설정 객체
            task_handler: 작업 처리 함수
        """
        self.settings = settings
        self.task_handler = task_handler
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.logger = setup_logging(settings)

    async def connect(self) -> None:
        """RabbitMQ 연결 초기화"""
        try:
            self.connection = await connect_robust(
                self.settings.rabbitmq_url,
                client_properties={"connection_name": "worker-client"}
            )
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)

            self.logger.info(f"워커 RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"워커 RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"워커 RabbitMQ 연결 실패: {e}")

    async def start_consuming(self) -> None:
        """작업 큐 소비 시작"""
        if not self.channel:
            raise QueueConnectionException("RabbitMQ 채널이 초기화되지 않았습니다")

        # 작업 큐 선언
        queue = await self.channel.declare_queue(
            self.settings.rabbitmq_task_queue,
            durable=True
        )

        # 메시지 소비 시작
        await queue.consume(self._process_message)
        self.logger.info(f"작업 큐 소비 시작: {self.settings.rabbitmq_task_queue}")

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        """작업 메시지 처리"""
        async with message.process():
            try:
                # 요청 데이터 파싱
                request_data = json.loads(message.body.decode())
                # datetime 문자열을 객체로 변환
                if "created_at" in request_data:
                    request_data["created_at"] = datetime.fromisoformat(request_data["created_at"])
                request = ScrapingRequest(**request_data)

                self.logger.info(f"작업 처리 시작: {request.request_id}")

                # 작업 처리
                response = await self.task_handler(request)

                # 응답 발송
                if message.reply_to and message.correlation_id:
                    await self._send_response(response, message.reply_to, message.correlation_id)

                self.logger.info(f"작업 처리 완료: {request.request_id}")

            except Exception as e:
                self.logger.error(f"작업 처리 오류: {e}")

                # 오류 응답 발송
                if message.reply_to and message.correlation_id:
                    error_response = ScrapingResponse(
                        request_id=request_data.get("request_id", "unknown"),
                        status=TaskStatus.FAILED,
                        error=str(e)
                    )
                    await self._send_response(error_response, message.reply_to, message.correlation_id)

    async def _send_response(self, response: ScrapingResponse, reply_to: str, correlation_id: str) -> None:
        """응답 메시지 발송"""
        if not self.channel:
            return

        response_data = {
            "request_id": response.request_id,
            "status": response.status.value,
            "data": response.data,
            "error": response.error,
            "execution_time": response.execution_time,
            "completed_at": response.completed_at.isoformat() if response.completed_at else None
        }

        message = Message(
            json.dumps(response_data).encode(),
            correlation_id=correlation_id
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=reply_to
        )

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("워커 RabbitMQ 연결 해제 완료")
