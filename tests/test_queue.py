"""
RabbitMQ 큐 시스템 테스트

RabbitMQ RPC, TaskManager, WorkerMonitor 클래스들의 단위 테스트를 제공합니다.
"""

import pytest
import pytest_asyncio
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
from typing import Dict, Any

from src.queue.rabbitmq_rpc import RabbitMQRPC, RabbitMQWorker
from src.queue.task_manager import TaskManager
from src.queue.worker_monitor import WorkerMonitor
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings
from src.exceptions import QueueConnectionException


class TestRabbitMQRPC:
    """RabbitMQ RPC 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정 픽스처"""
        return Settings(
            rabbitmq_url="amqp://test:test@localhost:5672/",
            rabbitmq_task_queue="test_scraping_tasks",
            log_level="DEBUG"
        )

    @pytest_asyncio.fixture
    async def rabbitmq_rpc(self, settings):
        """RabbitMQ RPC 픽스처"""
        rpc = RabbitMQRPC(settings)

        # Mock RabbitMQ components
        rpc.connection = AsyncMock()
        rpc.channel = AsyncMock()
        rpc.callback_queue = AsyncMock()
        rpc.callback_queue.name = "test-callback-queue"
        rpc.reply_queue_name = "test-callback-queue"
        return rpc

    @pytest.fixture
    def scraping_request(self):
        """테스트용 스크래핑 요청 픽스처"""
        return ScrapingRequest(
            script_name="test_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"},
            timeout=300
        )

    @pytest.mark.asyncio
    async def test_connect_success(self, settings):
        """RabbitMQ 연결 성공 테스트"""
        rpc = RabbitMQRPC(settings)

        with patch('aio_pika.connect_robust', new_callable=AsyncMock) as mock_connect:
            mock_connection = AsyncMock()
            mock_channel = AsyncMock()
            mock_connect.return_value = mock_connection
            mock_connection.channel.return_value = mock_channel

            await rpc.connect()

            assert rpc.connection == mock_connection
            assert rpc.channel == mock_channel
            mock_channel.set_qos.assert_called_once_with(prefetch_count=1)
            mock_channel.declare_queue.assert_called_once_with(
                settings.rabbitmq_task_queue,
                durable=True
            )

    @pytest.mark.asyncio
    async def test_connect_failure(self, settings):
        """RabbitMQ 연결 실패 테스트"""
        rpc = RabbitMQRPC(settings)

        with patch('aio_pika.connect_robust', side_effect=Exception("연결 실패")):
            with pytest.raises(QueueConnectionException):
                await rpc.connect()

    @pytest.mark.asyncio
    async def test_setup_callback_queue(self, rabbitmq_rpc):
        """콜백 큐 설정 테스트"""
        await rabbitmq_rpc.setup_callback_queue()

        rabbitmq_rpc.channel.declare_queue.assert_called_once_with(
            exclusive=True,
            auto_delete=True
        )
        rabbitmq_rpc.callback_queue.consume.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_async_success(self, rabbitmq_rpc, scraping_request):
        """RPC 비동기 호출 성공 테스트"""
        # Mock future for correlation_id
        correlation_id = "test-correlation-id"
        response = ScrapingResponse(
            request_id=scraping_request.request_id,
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

        with patch('uuid.uuid4', return_value=Mock(__str__=lambda: correlation_id)):
            with patch.object(asyncio, 'wait_for', return_value=response):
                result = await rabbitmq_rpc.call_async(scraping_request)

        assert result.request_id == scraping_request.request_id
        assert result.status == TaskStatus.COMPLETED
        rabbitmq_rpc.channel.default_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_async_timeout(self, rabbitmq_rpc, scraping_request):
        """RPC 비동기 호출 타임아웃 테스트"""
        correlation_id = "test-correlation-id"

        with patch('uuid.uuid4', return_value=Mock(__str__=lambda: correlation_id)):
            with patch.object(asyncio, 'wait_for', side_effect=asyncio.TimeoutError):
                with pytest.raises(TimeoutError):
                    await rabbitmq_rpc.call_async(scraping_request, timeout=5)

    @pytest.mark.asyncio
    async def test_on_response(self, rabbitmq_rpc):
        """응답 메시지 처리 테스트"""
        correlation_id = "test-correlation-id"
        future = asyncio.Future()
        rabbitmq_rpc.futures[correlation_id] = future

        # Mock 응답 메시지
        mock_message = AsyncMock()
        mock_message.correlation_id = correlation_id
        mock_message.body.decode.return_value = json.dumps({
            "request_id": "test-123",
            "status": "completed",
            "data": {"result": "success"},
            "error": None,
            "execution_time": 1.5,
            "completed_at": "2024-01-01T00:00:00"
        })

        await rabbitmq_rpc._on_response(mock_message)

        assert future.done()
        result = future.result()
        assert result.request_id == "test-123"
        assert result.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_disconnect(self, rabbitmq_rpc):
        """연결 해제 테스트"""
        rabbitmq_rpc.connection.is_closed = False

        await rabbitmq_rpc.disconnect()

        rabbitmq_rpc.connection.close.assert_called_once()


class TestRabbitMQWorker:
    """RabbitMQ 워커 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정 픽스처"""
        return Settings(
            rabbitmq_url="amqp://test:test@localhost:5672/",
            rabbitmq_task_queue="test_scraping_tasks"
        )

    @pytest_asyncio.fixture
    async def mock_task_handler(self):
        """모의 작업 처리 함수 픽스처"""
        async def handler(request: ScrapingRequest) -> ScrapingResponse:
            return ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.COMPLETED,
                data={"result": "success"}
            )
        return handler

    @pytest_asyncio.fixture
    async def rabbitmq_worker(self, settings, mock_task_handler):
        """RabbitMQ 워커 픽스처"""
        worker = RabbitMQWorker(settings, mock_task_handler)

        # Mock RabbitMQ components
        worker.connection = AsyncMock()
        worker.channel = AsyncMock()
        return worker

    @pytest.mark.asyncio
    async def test_worker_connect_success(self, settings, mock_task_handler):
        """워커 RabbitMQ 연결 성공 테스트"""
        worker = RabbitMQWorker(settings, mock_task_handler)

        with patch('aio_pika.connect_robust', new_callable=AsyncMock) as mock_connect:
            mock_connection = AsyncMock()
            mock_channel = AsyncMock()
            mock_connect.return_value = mock_connection
            mock_connection.channel.return_value = mock_channel

            await worker.connect()

            assert worker.connection == mock_connection
            assert worker.channel == mock_channel

    @pytest.mark.asyncio
    async def test_start_consuming(self, rabbitmq_worker):
        """작업 큐 소비 시작 테스트"""
        mock_queue = AsyncMock()
        rabbitmq_worker.channel.declare_queue.return_value = mock_queue

        await rabbitmq_worker.start_consuming()

        rabbitmq_worker.channel.declare_queue.assert_called_once_with(
            rabbitmq_worker.settings.rabbitmq_task_queue,
            durable=True
        )
        mock_queue.consume.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_success(self, rabbitmq_worker):
        """메시지 처리 성공 테스트"""
        # Mock 메시지
        mock_message = AsyncMock()
        mock_message.reply_to = "test-reply-queue"
        mock_message.correlation_id = "test-correlation-id"
        mock_message.body.decode.return_value = json.dumps({
            "request_id": "test-123",
            "script_name": "test_scraper",
            "script_version": "1.0.0",
            "parameters": {"url": "https://example.com"},
            "timeout": 300,
            "created_at": datetime.now().isoformat()
        })

        # Mock message.process() context manager
        mock_message.process.return_value.__aenter__ = AsyncMock()
        mock_message.process.return_value.__aexit__ = AsyncMock()

        await rabbitmq_worker._process_message(mock_message)

        # 응답 발송 확인
        rabbitmq_worker.channel.default_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response(self, rabbitmq_worker):
        """응답 발송 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

        await rabbitmq_worker._send_response(response, "test-reply-queue", "test-correlation-id")

        rabbitmq_worker.channel.default_exchange.publish.assert_called_once()


class TestTaskManager:
    """작업 매니저 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정 픽스처"""
        return Settings(
            rabbitmq_url="amqp://test:test@localhost:5672/",
            rabbitmq_task_queue="test_scraping_tasks"
        )

    @pytest_asyncio.fixture
    async def task_manager(self, settings):
        """작업 매니저 픽스처"""
        manager = TaskManager(settings)

        # Mock RabbitMQ components
        manager.connection = AsyncMock()
        manager.channel = AsyncMock()
        manager.task_history_exchange_obj = AsyncMock()
        manager.worker_status_exchange_obj = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_connect_success(self, settings):
        """작업 매니저 연결 성공 테스트"""
        manager = TaskManager(settings)

        with patch('aio_pika.connect_robust', new_callable=AsyncMock) as mock_connect:
            mock_connection = AsyncMock()
            mock_channel = AsyncMock()
            mock_task_exchange = AsyncMock()
            mock_worker_exchange = AsyncMock()
            
            mock_connect.return_value = mock_connection
            mock_connection.channel.return_value = mock_channel
            mock_channel.declare_exchange.side_effect = [mock_task_exchange, mock_worker_exchange]

            await manager.connect()

            assert manager.connection == mock_connection
            assert manager.channel == mock_channel
            assert manager.task_history_exchange_obj == mock_task_exchange
            assert manager.worker_status_exchange_obj == mock_worker_exchange
            # Exchange 선언 확인
            assert mock_channel.declare_exchange.call_count == 2

    @pytest.mark.asyncio
    async def test_publish_task_completion_success(self, task_manager):
        """작업 완료 이벤트 발행 테스트 (성공)"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

        await task_manager.publish_task_completion(response)

        # Exchange에 메시지 발행 확인
        task_manager.task_history_exchange_obj.publish.assert_called_once()
        
        # 호출 인자 확인
        call_args = task_manager.task_history_exchange_obj.publish.call_args
        assert call_args[1]["routing_key"] == "task.completed"

    @pytest.mark.asyncio
    async def test_publish_task_completion_failed(self, task_manager):
        """작업 완료 이벤트 발행 테스트 (실패)"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.FAILED,
            error="스크래핑 실패"
        )

        await task_manager.publish_task_completion(response)

        # Exchange에 메시지 발행 확인
        task_manager.task_history_exchange_obj.publish.assert_called_once()
        
        # 호출 인자 확인
        call_args = task_manager.task_history_exchange_obj.publish.call_args
        assert call_args[1]["routing_key"] == "task.failed"

    @pytest.mark.asyncio
    async def test_publish_task_started(self, task_manager):
        """작업 시작 이벤트 발행 테스트"""
        request = ScrapingRequest(
            script_name="test_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"}
        )

        await task_manager.publish_task_started(request)

        # Exchange에 메시지 발행 확인
        task_manager.task_history_exchange_obj.publish.assert_called_once()
        
        # 호출 인자 확인
        call_args = task_manager.task_history_exchange_obj.publish.call_args
        assert call_args[1]["routing_key"] == "task.started"

    @pytest.mark.asyncio
    async def test_publish_task_progress(self, task_manager):
        """작업 진행 이벤트 발행 테스트"""
        await task_manager.publish_task_progress(
            "test-123", 
            {"completed": 50, "total": 100}
        )

        # Exchange에 메시지 발행 확인
        task_manager.task_history_exchange_obj.publish.assert_called_once()
        
        # 호출 인자 확인
        call_args = task_manager.task_history_exchange_obj.publish.call_args
        assert call_args[1]["routing_key"] == "task.progress"

    @pytest.mark.asyncio
    async def test_get_queue_metrics(self, task_manager):
        """큐 메트릭 조회 테스트"""
        task_manager.connection.is_closed = False

        metrics = await task_manager.get_queue_metrics()

        assert "task_queue" in metrics
        assert "connection_status" in metrics
        assert metrics["connection_status"] == "connected"


class TestWorkerMonitor:
    """워커 모니터 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정 픽스처"""
        return Settings(
            rabbitmq_url="amqp://test:test@localhost:5672/"
        )

    @pytest_asyncio.fixture
    async def worker_monitor(self, settings):
        """워커 모니터 픽스처"""
        monitor = WorkerMonitor(settings)

        # Mock RabbitMQ components
        monitor.connection = AsyncMock()
        monitor.channel = AsyncMock()
        monitor.worker_status_exchange_obj = AsyncMock()
        return monitor

    @pytest.mark.asyncio
    async def test_connect_success(self, settings):
        """워커 모니터 연결 성공 테스트"""
        monitor = WorkerMonitor(settings)

        with patch('aio_pika.connect_robust', new_callable=AsyncMock) as mock_connect:
            mock_connection = AsyncMock()
            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            
            mock_connect.return_value = mock_connection
            mock_connection.channel.return_value = mock_channel
            mock_channel.declare_exchange.return_value = mock_exchange

            await monitor.connect()

            assert monitor.connection == mock_connection
            assert monitor.channel == mock_channel
            assert monitor.worker_status_exchange_obj == mock_exchange

    @pytest.mark.asyncio
    async def test_publish_worker_status(self, worker_monitor):
        """워커 상태 발행 테스트"""
        await worker_monitor.publish_worker_status(
            "test-worker-1", 
            "active", 
            {"current_tasks": 2}
        )

        # Exchange에 메시지 발행 확인
        worker_monitor.worker_status_exchange_obj.publish.assert_called_once()
        
        # 호출 인자 확인
        call_args = worker_monitor.worker_status_exchange_obj.publish.call_args
        assert call_args[1]["routing_key"] == "worker.active"

    @pytest.mark.asyncio
    async def test_send_heartbeat(self, worker_monitor):
        """하트비트 전송 테스트"""
        await worker_monitor.send_heartbeat(
            "test-worker-1", 
            {"cpu_usage": 45.2}
        )

        # 기본 Exchange에 메시지 발행 확인 (하트비트는 큐로 직접 전송)
        worker_monitor.channel.default_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_worker(self, worker_monitor):
        """워커 등록 테스트"""
        worker_info = {
            "max_tasks": 4,
            "capabilities": ["scraping", "browser"]
        }

        await worker_monitor.register_worker("test-worker-1", worker_info)

        # 기본 Exchange에 메시지 발행 확인 (등록은 큐로 직접 전송)
        worker_monitor.channel.default_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_worker_health(self, worker_monitor):
        """워커 상태 확인 테스트"""
        from datetime import timedelta
        
        last_heartbeats = {
            "worker-1": datetime.now() - timedelta(seconds=30),  # 정상
            "worker-2": datetime.now() - timedelta(seconds=120), # 타임아웃
        }

        unhealthy_workers = await worker_monitor.check_worker_health(last_heartbeats)

        assert "worker-2" in unhealthy_workers
        assert "worker-1" not in unhealthy_workers

    @pytest.mark.asyncio
    async def test_get_worker_metrics(self, worker_monitor):
        """워커 메트릭 조회 테스트"""
        worker_monitor.connection.is_closed = False

        metrics = await worker_monitor.get_worker_metrics()

        assert "heartbeat_queue" in metrics
        assert "worker_status_exchange" in metrics
        assert "connection_status" in metrics
        assert metrics["connection_status"] == "connected" 