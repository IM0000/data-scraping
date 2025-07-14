# PRP-2: RabbitMQ RPC Communication System

## Goal

Implement a RabbitMQ-based RPC communication system for distributed communication between the Gateway and Workers. The system should handle synchronous request-response patterns using correlation_id and reply_to queues, with robust error handling and timeout mechanisms.

## Why

- **Synchronous communication**: Enables gateway to wait for worker responses synchronously
- **Decoupling**: Separates Gateway and Worker components for better scalability
- **Reliability**: RabbitMQ provides guaranteed message delivery and persistence
- **Scalability**: Supports multiple worker instances and horizontal scaling
- **Monitoring**: Provides visibility into task status and worker health
- **Load balancing**: Distributes tasks efficiently across available workers using RabbitMQ's built-in load balancing

## What

Build a comprehensive RabbitMQ RPC system that includes:

- RabbitMQ-based RPC pattern with correlation_id and reply_to queues
- Task queue management for worker task distribution
- Worker health monitoring and registration
- Timeout handling for synchronous responses
- Error handling and retry mechanisms
- Connection pooling and recovery
- Real-time status updates and metrics

### Success Criteria

- [ ] RPC pattern works correctly with correlation_id matching
- [ ] Gateway can send tasks and receive responses synchronously
- [ ] Worker health monitoring works correctly
- [ ] Failed tasks are handled gracefully with retry logic
- [ ] System can handle multiple workers concurrently
- [ ] Timeout handling works for long-running tasks
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# RabbitMQ and RPC Pattern
- url: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
  why: Official RabbitMQ RPC tutorial with correlation_id pattern

- url: https://pika.readthedocs.io/en/stable/
  why: Python RabbitMQ client library documentation

- url: https://aio-pika.readthedocs.io/en/latest/
  why: Async RabbitMQ client for high-performance applications

- url: https://www.rabbitmq.com/confirms.html
  why: Message acknowledgment and reliability patterns

# Connection Management
- url: https://www.rabbitmq.com/connection-blocked.html
  why: Connection management and recovery patterns

- url: https://www.rabbitmq.com/heartbeats.html
  why: Health monitoring and connection keepalive

# Error Handling
- url: https://www.rabbitmq.com/dlx.html
  why: Dead letter exchange for failed message handling
```

### Current Codebase Structure (After Phase 1)

```
src/
├── models/
│   ├── base.py              # Core data models (from Phase 1)
│   └── enums.py             # Task status enums
├── config/
│   └── settings.py          # Configuration (from Phase 1)
├── utils/
│   ├── logging.py           # Logging system (from Phase 1)
│   └── helpers.py           # Common utilities (from Phase 1)
├── exceptions.py            # Exception classes (from Phase 1)
└── queue/                   # NEW: Message queue system
    ├── __init__.py
    ├── rabbitmq_rpc.py      # RabbitMQ RPC implementation
    ├── task_manager.py      # Task lifecycle management
    └── worker_monitor.py    # Worker health monitoring
```

### Key Requirements from INITIAL.md

- RabbitMQ as message broker for robust RPC-style communication
- Synchronous response delivery with timeout handling using correlation_id pattern
- Comprehensive logging in Korean
- Retry mechanisms with exponential backoff
- Worker health and queue status monitoring

## Implementation Blueprint

### Task 1: RabbitMQ RPC Implementation

```python
# queue/rabbitmq_rpc.py
import asyncio
import json
import uuid
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import aio_pika
from aio_pika import Message, DeliveryMode, connect_robust
from aio_pika.abc import AbstractIncomingMessage, AbstractConnection, AbstractChannel, AbstractQueue
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings
from src.utils.logging import setup_logging
from src.exceptions import QueueConnectionException

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
        self.futures: Dict[str, asyncio.Future] = {}
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
```

### Task 2: Task Manager

```python
# queue/task_manager.py
import asyncio
import json
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import aio_pika
from aio_pika import connect_robust, Message
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractQueue
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings
from src.utils.logging import setup_logging
from src.exceptions import QueueConnectionException

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
        self.logger = setup_logging(settings)

        # 큐 이름 정의
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

            # Exchange 선언
            await self.channel.declare_exchange(
                self.task_history_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            await self.channel.declare_exchange(
                self.worker_status_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            self.logger.info(f"작업 매니저 RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"작업 매니저 RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"작업 매니저 RabbitMQ 연결 실패: {e}")

    async def publish_task_completion(self, response: ScrapingResponse) -> None:
        """작업 완료 이벤트 발행"""
        if not self.channel:
            return

        completion_data = {
            "request_id": response.request_id,
            "status": response.status.value,
            "data": response.data,
            "error": response.error,
            "execution_time": response.execution_time,
            "completed_at": response.completed_at.isoformat() if response.completed_at else None
        }

        routing_key = f"task.{response.status.value.lower()}"

        message = Message(
            json.dumps(completion_data).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.task_history_exchange + "." + routing_key
        )

        if response.status == TaskStatus.COMPLETED:
            self.logger.info(f"작업 완료 이벤트 발행: {response.request_id}")
        else:
            self.logger.error(f"작업 실패 이벤트 발행: {response.request_id} - {response.error}")

    async def get_queue_metrics(self) -> Dict[str, Any]:
        """RabbitMQ 큐 메트릭 조회"""
        if not self.connection:
            return {}

        try:
            # Management API를 통한 큐 통계 조회 (선택사항)
            # 여기서는 간단한 버전으로 구현
            return {
                "task_queue": self.settings.rabbitmq_task_queue,
                "connection_status": "connected" if not self.connection.is_closed else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"큐 메트릭 조회 오류: {e}")
            return {}

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("작업 매니저 RabbitMQ 연결 해제 완료")
```

### Task 3: Worker Monitor

```python
# queue/worker_monitor.py
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import aio_pika
from aio_pika import connect_robust, Message
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractQueue
from src.config.settings import Settings
from src.utils.logging import setup_logging
from src.exceptions import QueueConnectionException

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
        self.logger = setup_logging(settings)
        self.heartbeat_timeout = 60  # 1분

        # Exchange와 큐 이름 정의
        self.worker_status_exchange = "scraping.worker.status"
        self.heartbeat_queue = "scraping.worker.heartbeat"

    async def connect(self) -> None:
        """RabbitMQ 연결 초기화"""
        try:
            self.connection = await connect_robust(
                self.settings.rabbitmq_url,
                client_properties={"connection_name": "worker-monitor"}
            )
            self.channel = await self.connection.channel()

            # Exchange 선언
            await self.channel.declare_exchange(
                self.worker_status_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # 하트비트 큐 선언
            await self.channel.declare_queue(
                self.heartbeat_queue,
                durable=True
            )

            self.logger.info(f"워커 모니터 RabbitMQ 연결 성공: {self.settings.rabbitmq_url}")
        except Exception as e:
            self.logger.error(f"워커 모니터 RabbitMQ 연결 실패: {e}")
            raise QueueConnectionException(f"워커 모니터 RabbitMQ 연결 실패: {e}")

    async def publish_worker_status(self, worker_id: str, status: str, metadata: Dict = None) -> None:
        """워커 상태 발행"""
        if not self.channel:
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

        await self.channel.default_exchange.publish(
            message,
            routing_key=self.worker_status_exchange + "." + routing_key
        )

        self.logger.info(f"워커 상태 발행: {worker_id} -> {status}")

    async def send_heartbeat(self, worker_id: str, stats: Dict = None) -> None:
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

    async def start_heartbeat_consumer(self, heartbeat_handler: callable) -> None:
        """하트비트 소비자 시작"""
        if not self.channel:
            return

        queue = await self.channel.declare_queue(
            self.heartbeat_queue,
            durable=True
        )

        async def process_heartbeat(message):
            async with message.process():
                try:
                    heartbeat_data = json.loads(message.body.decode())
                    await heartbeat_handler(heartbeat_data)
                except Exception as e:
                    self.logger.error(f"하트비트 처리 오류: {e}")

        await queue.consume(process_heartbeat)
        self.logger.info("하트비트 소비자 시작됨")

    async def get_worker_metrics(self) -> Dict[str, Any]:
        """워커 메트릭 조회"""
        if not self.connection:
            return {}

        try:
            # RabbitMQ Management API를 통한 워커 통계 조회
            # 여기서는 기본적인 메트릭만 제공
            return {
                "heartbeat_queue": self.heartbeat_queue,
                "worker_status_exchange": self.worker_status_exchange,
                "connection_status": "connected" if not self.connection.is_closed else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"워커 메트릭 조회 오류: {e}")
            return {}

    async def disconnect(self) -> None:
        """연결 해제"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("워커 모니터 RabbitMQ 연결 해제 완료")
```

## Integration Points

### Environment Variables (.env) - Updated

```bash
# RabbitMQ Configuration
RABBITMQ_URL=amqp://user:password@localhost:5672/
RABBITMQ_TASK_QUEUE=scraping_tasks
RABBITMQ_RESULT_TIMEOUT=300  # seconds

# Queue Configuration
WORKER_HEARTBEAT_INTERVAL=30
TASK_TIMEOUT=300
RPC_TIMEOUT=300

# Existing from Phase 1...
```

### Project Structure - Updated

```
src/
├── models/
│   ├── base.py              # From Phase 1
│   └── enums.py             # From Phase 1
├── config/
│   └── settings.py          # Updated with RabbitMQ settings
├── utils/
│   ├── logging.py           # From Phase 1
│   └── helpers.py           # From Phase 1
├── exceptions.py            # From Phase 1
└── queue/                   # NEW
    ├── __init__.py
    ├── rabbitmq_rpc.py      # RabbitMQ RPC implementation
    ├── task_manager.py      # Task lifecycle management
    └── worker_monitor.py    # Worker health monitoring
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Type checking and linting
uv run mypy src/queue/
uv run ruff check src/queue/ --fix

# Expected: No errors. All async functions properly typed.
```

### Level 2: Unit Tests

```python
# tests/test_queue.py
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch
from src.queue.rabbitmq_rpc import RabbitMQRPC, RabbitMQWorker
from src.queue.task_manager import TaskManager
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings

class TestRabbitMQRPC:
    """RabbitMQ RPC 테스트"""

    @pytest.fixture
    async def rabbitmq_rpc(self):
        """RabbitMQ RPC 픽스처"""
        settings = Settings()
        rpc = RabbitMQRPC(settings)

        # Mock RabbitMQ components
        rpc.connection = AsyncMock()
        rpc.channel = AsyncMock()
        rpc.callback_queue = AsyncMock()
        rpc.callback_queue.name = "test-callback-queue"
        return rpc

    @pytest.mark.asyncio
    async def test_call_async(self, rabbitmq_rpc):
        """RPC 비동기 호출 테스트"""
        request = ScrapingRequest(
            script_name="test_scraper",
            parameters={"url": "https://example.com"}
        )

        # Mock future for correlation_id
        future = asyncio.Future()
        response = ScrapingResponse(
            request_id=request.request_id,
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )
        future.set_result(response)

        with patch.object(asyncio, 'wait_for', return_value=response):
            result = await rabbitmq_rpc.call_async(request)

        assert result.request_id == request.request_id
        assert result.status == TaskStatus.COMPLETED

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

class TestTaskManager:
    """작업 매니저 테스트"""

    @pytest.fixture
    async def task_manager(self):
        """작업 매니저 픽스처"""
        settings = Settings()
        manager = TaskManager(settings)

        # Mock RabbitMQ components
        manager.connection = AsyncMock()
        manager.channel = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_publish_task_completion(self, task_manager):
        """작업 완료 이벤트 발행 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

        await task_manager.publish_task_completion(response)

        # RabbitMQ 메시지 발행 확인
        task_manager.channel.default_exchange.publish.assert_called_once()
```

```bash
# Run queue tests
uv run pytest tests/test_queue.py -v

# Run with RabbitMQ integration test
docker run -d --name rabbitmq-test -p 5672:5672 -p 15672:15672 rabbitmq:3-management
uv run pytest tests/test_queue_integration.py -v
docker stop rabbitmq-test && docker rm rabbitmq-test
```

### Level 3: Integration Test

```python
# tests/test_queue_integration.py
import pytest
import asyncio
from src.queue.rabbitmq_rpc import RabbitMQRPC, RabbitMQWorker
from src.queue.task_manager import TaskManager
from src.queue.worker_monitor import WorkerMonitor
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings

@pytest.mark.asyncio
async def test_full_rpc_workflow():
    """전체 RabbitMQ RPC 워크플로우 테스트"""
    settings = Settings()

    # RPC 시스템 초기화
    rpc_client = RabbitMQRPC(settings)
    await rpc_client.connect()
    await rpc_client.setup_callback_queue()

    task_manager = TaskManager(settings)
    await task_manager.connect()

    worker_monitor = WorkerMonitor(settings)
    await worker_monitor.connect()

    # 워커 상태 발행
    await worker_monitor.publish_worker_status("test-worker-1", "active")

    # 작업 생성 및 RPC 호출 (타임아웃 테스트)
    request = ScrapingRequest(
        script_name="test_scraper",
        parameters={"url": "https://example.com"}
    )

    # 실제 워커가 없으므로 타임아웃 발생 예상
    with pytest.raises(TimeoutError):
        await rpc_client.call_async(request, timeout=5)

    # 시스템 정리
    await rpc_client.disconnect()
    await task_manager.disconnect()
    await worker_monitor.disconnect()

@pytest.mark.asyncio
async def test_worker_integration():
    """워커 통합 테스트"""
    settings = Settings()

    async def mock_task_handler(request: ScrapingRequest) -> ScrapingResponse:
        """모의 작업 처리 함수"""
        return ScrapingResponse(
            request_id=request.request_id,
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

    # 워커 초기화
    worker = RabbitMQWorker(settings, mock_task_handler)
    await worker.connect()

    # 워커는 백그라운드에서 실행되므로 간단한 연결 테스트만 수행
    assert worker.connection is not None
    assert worker.channel is not None

    await worker.disconnect()
```

## Final Validation Checklist

- [ ] RabbitMQ connection established successfully
- [ ] RPC pattern works correctly with correlation_id matching
- [ ] Worker can consume messages and send responses reliably
- [ ] Task lifecycle management functions correctly
- [ ] Failed tasks are handled gracefully with retry logic
- [ ] System can handle multiple workers concurrently
- [ ] Timeout handling works for long-running tasks
- [ ] All unit tests pass: `uv run pytest tests/test_queue.py -v`
- [ ] Integration tests pass: `uv run pytest tests/test_queue_integration.py -v`
- [ ] No type errors: `uv run mypy src/queue/`
- [ ] No linting errors: `uv run ruff check src/queue/`
- [ ] Korean logging messages are properly formatted

## Anti-Patterns to Avoid

- ❌ Don't use synchronous RabbitMQ operations in async code
- ❌ Don't ignore RabbitMQ connection errors - handle gracefully with reconnection
- ❌ Don't store large data in message payloads - use references or external storage
- ❌ Don't forget to acknowledge messages properly to prevent message loss
- ❌ Don't block the event loop with long-running operations
- ❌ Don't create too many channels - reuse connections and channels efficiently
- ❌ Don't ignore correlation_id matching - it's critical for RPC pattern reliability
