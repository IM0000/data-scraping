# PRP-2: Message Queue System

## Goal

Implement a Redis-based message queue system for distributed communication between the Gateway and Workers. The system should handle task queuing, worker health monitoring, and reliable message delivery with retry mechanisms.

## Why

- **Decoupling**: Separates Gateway and Worker components for better scalability
- **Reliability**: Ensures tasks are not lost even if workers are temporarily unavailable
- **Scalability**: Supports multiple worker instances and horizontal scaling
- **Monitoring**: Provides visibility into task status and worker health
- **Load balancing**: Distributes tasks efficiently across available workers

## What

Build a comprehensive message queue system that includes:

- Redis-based task queue with priority support
- Worker registration and health monitoring
- Task lifecycle management (pending, processing, completed, failed)
- Dead letter queue for failed tasks
- Rate limiting and backpressure handling
- Real-time status updates and metrics

### Success Criteria

- [ ] Tasks are queued and processed reliably
- [ ] Worker health monitoring works correctly
- [ ] Failed tasks are handled gracefully with retry logic
- [ ] System can handle multiple workers concurrently
- [ ] Real-time status updates are available
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# Redis and Message Queue
- url: https://redis.io/docs/manual/data-types/
  why: Understanding Redis data structures for queue implementation

- url: https://python-rq.org/
  why: Python Redis Queue patterns and best practices

- url: https://docs.celeryq.dev/en/stable/
  why: Distributed task queue architecture patterns

- url: https://docs.aioredis.io/en/stable/
  why: Async Redis client for Python

# Dependencies
- file: PRPs/phase1-core-models.md
  why: Uses core data models and configuration system

- file: examples/basic_structure.py
  why: Follow existing coding patterns and class structure

- file: examples/test_pattern.py
  why: Test patterns for validation gates
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
    ├── redis_queue.py       # Redis queue implementation
    ├── task_manager.py      # Task lifecycle management
    └── worker_monitor.py    # Worker health monitoring
```

### Key Requirements from INITIAL.md

- Redis as message broker for high performance
- Synchronous response delivery with timeout handling
- Comprehensive logging in Korean
- Retry mechanisms with exponential backoff
- Worker health and queue status monitoring

## Implementation Blueprint

### Task 1: Redis Queue Implementation

```python
# queue/redis_queue.py
import asyncio
import json
import redis.asyncio as redis
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings
from src.utils.logging import setup_logging
from src.exceptions import QueueConnectionException

class RedisQueue:
    """Redis 기반 작업 큐 클래스"""

    def __init__(self, settings: Settings):
        """
        Redis 큐 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.redis_client: Optional[redis.Redis] = None
        self.logger = setup_logging(settings)

        # 큐 이름 정의
        self.task_queue = "scraping:tasks:pending"
        self.processing_queue = "scraping:tasks:processing"
        self.completed_queue = "scraping:tasks:completed"
        self.failed_queue = "scraping:tasks:failed"

    async def connect(self) -> None:
        """Redis 연결 초기화"""
        try:
            self.redis_client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                decode_responses=True
            )
            # 연결 테스트
            await self.redis_client.ping()
            self.logger.info(f"Redis 연결 성공: {self.settings.redis_host}:{self.settings.redis_port}")
        except Exception as e:
            self.logger.error(f"Redis 연결 실패: {e}")
            raise QueueConnectionException(f"Redis 연결 실패: {e}")

    async def enqueue_task(self, request: ScrapingRequest) -> None:
        """작업을 큐에 추가"""
        if not self.redis_client:
            raise QueueConnectionException("Redis 클라이언트가 초기화되지 않았습니다")

        task_data = {
            "request_id": request.request_id,
            "script_name": request.script_name,
            "script_version": request.script_version,
            "parameters": request.parameters,
            "timeout": request.timeout,
            "created_at": request.created_at.isoformat(),
            "status": TaskStatus.PENDING.value
        }

        await self.redis_client.lpush(self.task_queue, json.dumps(task_data))
        self.logger.info(f"작업 큐 추가: {request.request_id}")

    async def dequeue_task(self, worker_id: str) -> Optional[ScrapingRequest]:
        """큐에서 작업 가져오기 (블로킹)"""
        if not self.redis_client:
            raise QueueConnectionException("Redis 클라이언트가 초기화되지 않았습니다")

        # 블로킹 pop으로 작업 가져오기
        result = await self.redis_client.brpop(self.task_queue, timeout=10)

        if result:
            queue_name, task_json = result
            task_data = json.loads(task_json)

            # 처리 중 큐로 이동
            task_data["status"] = TaskStatus.RUNNING.value
            task_data["worker_id"] = worker_id
            task_data["started_at"] = datetime.now().isoformat()

            await self.redis_client.hset(
                self.processing_queue,
                task_data["request_id"],
                json.dumps(task_data)
            )

            self.logger.info(f"작업 할당: {task_data['request_id']} -> {worker_id}")

            return ScrapingRequest(
                script_name=task_data["script_name"],
                script_version=task_data["script_version"],
                parameters=task_data["parameters"],
                timeout=task_data["timeout"],
                request_id=task_data["request_id"],
                created_at=datetime.fromisoformat(task_data["created_at"])
            )

        return None
```

### Task 2: Task Manager

```python
# queue/task_manager.py
import asyncio
import json
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.queue.redis_queue import RedisQueue
from src.utils.logging import setup_logging

class TaskManager:
    """작업 생명주기 관리 클래스"""

    def __init__(self, redis_queue: RedisQueue):
        """
        작업 매니저 초기화

        Args:
            redis_queue: Redis 큐 인스턴스
        """
        self.redis_queue = redis_queue
        self.logger = setup_logging(redis_queue.settings)
        self.cleanup_interval = 300  # 5분마다 정리

    async def complete_task(self, response: ScrapingResponse) -> None:
        """작업 완료 처리"""
        if not self.redis_queue.redis_client:
            return

        # 처리 중에서 제거
        await self.redis_queue.redis_client.hdel(
            self.redis_queue.processing_queue,
            response.request_id
        )

        # 완료 큐에 추가
        completion_data = {
            "request_id": response.request_id,
            "status": response.status.value,
            "data": response.data,
            "error": response.error,
            "execution_time": response.execution_time,
            "completed_at": response.completed_at.isoformat() if response.completed_at else None
        }

        if response.status == TaskStatus.COMPLETED:
            await self.redis_queue.redis_client.hset(
                self.redis_queue.completed_queue,
                response.request_id,
                json.dumps(completion_data)
            )
            self.logger.info(f"작업 완료: {response.request_id}")
        else:
            await self.redis_queue.redis_client.hset(
                self.redis_queue.failed_queue,
                response.request_id,
                json.dumps(completion_data)
            )
            self.logger.error(f"작업 실패: {response.request_id} - {response.error}")

    async def get_task_status(self, request_id: str) -> Optional[TaskStatus]:
        """작업 상태 조회"""
        if not self.redis_queue.redis_client:
            return None

        # 각 큐에서 작업 상태 확인
        queues = [
            (self.redis_queue.task_queue, TaskStatus.PENDING),
            (self.redis_queue.processing_queue, TaskStatus.RUNNING),
            (self.redis_queue.completed_queue, TaskStatus.COMPLETED),
            (self.redis_queue.failed_queue, TaskStatus.FAILED)
        ]

        for queue_name, status in queues:
            if queue_name == self.redis_queue.task_queue:
                # 리스트 큐에서 검색
                tasks = await self.redis_queue.redis_client.lrange(queue_name, 0, -1)
                for task_json in tasks:
                    task_data = json.loads(task_json)
                    if task_data["request_id"] == request_id:
                        return status
            else:
                # 해시 큐에서 검색
                exists = await self.redis_queue.redis_client.hexists(queue_name, request_id)
                if exists:
                    return status

        return None

    async def cleanup_old_tasks(self) -> None:
        """오래된 작업 정리"""
        if not self.redis_queue.redis_client:
            return

        cutoff_time = datetime.now() - timedelta(hours=24)

        # 완료된 작업 정리
        for queue_name in [self.redis_queue.completed_queue, self.redis_queue.failed_queue]:
            task_ids = await self.redis_queue.redis_client.hkeys(queue_name)

            for task_id in task_ids:
                task_json = await self.redis_queue.redis_client.hget(queue_name, task_id)
                if task_json:
                    task_data = json.loads(task_json)
                    completed_at = datetime.fromisoformat(task_data["completed_at"])

                    if completed_at < cutoff_time:
                        await self.redis_queue.redis_client.hdel(queue_name, task_id)
                        self.logger.info(f"오래된 작업 정리: {task_id}")

    async def start_cleanup_worker(self) -> None:
        """정리 작업 워커 시작"""
        while True:
            try:
                await self.cleanup_old_tasks()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                self.logger.error(f"정리 작업 오류: {e}")
                await asyncio.sleep(60)  # 오류 시 1분 대기
```

### Task 3: Worker Monitor

```python
# queue/worker_monitor.py
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from src.queue.redis_queue import RedisQueue
from src.utils.logging import setup_logging

class WorkerMonitor:
    """워커 상태 모니터링 클래스"""

    def __init__(self, redis_queue: RedisQueue):
        """
        워커 모니터 초기화

        Args:
            redis_queue: Redis 큐 인스턴스
        """
        self.redis_queue = redis_queue
        self.logger = setup_logging(redis_queue.settings)
        self.workers_key = "scraping:workers"
        self.heartbeat_timeout = 60  # 1분

    async def register_worker(self, worker_id: str) -> None:
        """워커 등록"""
        if not self.redis_queue.redis_client:
            return

        worker_data = {
            "worker_id": worker_id,
            "registered_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "status": "active",
            "tasks_processed": 0
        }

        await self.redis_queue.redis_client.hset(
            self.workers_key,
            worker_id,
            json.dumps(worker_data)
        )

        self.logger.info(f"워커 등록: {worker_id}")

    async def update_heartbeat(self, worker_id: str) -> None:
        """워커 하트비트 업데이트"""
        if not self.redis_queue.redis_client:
            return

        worker_json = await self.redis_queue.redis_client.hget(self.workers_key, worker_id)
        if worker_json:
            worker_data = json.loads(worker_json)
            worker_data["last_heartbeat"] = datetime.now().isoformat()

            await self.redis_queue.redis_client.hset(
                self.workers_key,
                worker_id,
                json.dumps(worker_data)
            )

    async def increment_task_counter(self, worker_id: str) -> None:
        """워커 처리 작업 수 증가"""
        if not self.redis_queue.redis_client:
            return

        worker_json = await self.redis_queue.redis_client.hget(self.workers_key, worker_id)
        if worker_json:
            worker_data = json.loads(worker_json)
            worker_data["tasks_processed"] += 1

            await self.redis_queue.redis_client.hset(
                self.workers_key,
                worker_id,
                json.dumps(worker_data)
            )

    async def get_active_workers(self) -> List[Dict]:
        """활성 워커 목록 조회"""
        if not self.redis_queue.redis_client:
            return []

        workers = []
        worker_ids = await self.redis_queue.redis_client.hkeys(self.workers_key)

        for worker_id in worker_ids:
            worker_json = await self.redis_queue.redis_client.hget(self.workers_key, worker_id)
            if worker_json:
                worker_data = json.loads(worker_json)
                last_heartbeat = datetime.fromisoformat(worker_data["last_heartbeat"])

                # 하트비트 타임아웃 확인
                if datetime.now() - last_heartbeat < timedelta(seconds=self.heartbeat_timeout):
                    worker_data["status"] = "active"
                    workers.append(worker_data)
                else:
                    worker_data["status"] = "inactive"
                    workers.append(worker_data)

        return workers

    async def cleanup_inactive_workers(self) -> None:
        """비활성 워커 정리"""
        if not self.redis_queue.redis_client:
            return

        worker_ids = await self.redis_queue.redis_client.hkeys(self.workers_key)

        for worker_id in worker_ids:
            worker_json = await self.redis_queue.redis_client.hget(self.workers_key, worker_id)
            if worker_json:
                worker_data = json.loads(worker_json)
                last_heartbeat = datetime.fromisoformat(worker_data["last_heartbeat"])

                # 5분 이상 비활성 워커 제거
                if datetime.now() - last_heartbeat > timedelta(minutes=5):
                    await self.redis_queue.redis_client.hdel(self.workers_key, worker_id)
                    self.logger.info(f"비활성 워커 제거: {worker_id}")
```

## Integration Points

### Environment Variables (.env) - Updated

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Optional

# Queue Configuration
TASK_QUEUE_TIMEOUT=10
WORKER_HEARTBEAT_INTERVAL=30
CLEANUP_INTERVAL=300

# Existing from Phase 1...
```

### Project Structure - Updated

```
src/
├── models/
│   ├── base.py              # From Phase 1
│   └── enums.py             # From Phase 1
├── config/
│   └── settings.py          # Updated with queue settings
├── utils/
│   ├── logging.py           # From Phase 1
│   └── helpers.py           # From Phase 1
├── exceptions.py            # From Phase 1
└── queue/                   # NEW
    ├── __init__.py
    ├── redis_queue.py       # Redis queue implementation
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
from unittest.mock import AsyncMock, patch
from src.queue.redis_queue import RedisQueue
from src.queue.task_manager import TaskManager
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.config.settings import Settings

class TestRedisQueue:
    """Redis 큐 테스트"""

    @pytest.fixture
    async def redis_queue(self):
        """Redis 큐 픽스처"""
        settings = Settings()
        queue = RedisQueue(settings)

        # Mock Redis client
        queue.redis_client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_enqueue_task(self, redis_queue):
        """작업 큐 추가 테스트"""
        request = ScrapingRequest(
            script_name="test_scraper",
            parameters={"url": "https://example.com"}
        )

        await redis_queue.enqueue_task(request)

        # Redis lpush 호출 확인
        redis_queue.redis_client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_task(self, redis_queue):
        """작업 큐 가져오기 테스트"""
        # Mock Redis brpop response
        task_data = {
            "request_id": "test-123",
            "script_name": "test_scraper",
            "script_version": None,
            "parameters": {"url": "https://example.com"},
            "timeout": 300,
            "created_at": "2024-01-01T00:00:00",
            "status": "pending"
        }
        redis_queue.redis_client.brpop.return_value = ("queue", json.dumps(task_data))

        result = await redis_queue.dequeue_task("worker-1")

        assert result is not None
        assert result.request_id == "test-123"
        assert result.script_name == "test_scraper"

class TestTaskManager:
    """작업 매니저 테스트"""

    @pytest.fixture
    async def task_manager(self):
        """작업 매니저 픽스처"""
        settings = Settings()
        redis_queue = RedisQueue(settings)
        redis_queue.redis_client = AsyncMock()

        return TaskManager(redis_queue)

    @pytest.mark.asyncio
    async def test_complete_task(self, task_manager):
        """작업 완료 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )

        await task_manager.complete_task(response)

        # Redis 작업 확인
        task_manager.redis_queue.redis_client.hdel.assert_called_once()
        task_manager.redis_queue.redis_client.hset.assert_called_once()
```

```bash
# Run queue tests
uv run pytest tests/test_queue.py -v

# Run with Redis integration test
docker run -d --name redis-test -p 6379:6379 redis:latest
uv run pytest tests/test_queue_integration.py -v
docker stop redis-test && docker rm redis-test
```

### Level 3: Integration Test

```python
# tests/test_queue_integration.py
import pytest
import asyncio
from src.queue.redis_queue import RedisQueue
from src.queue.task_manager import TaskManager
from src.queue.worker_monitor import WorkerMonitor
from src.models.base import ScrapingRequest, TaskStatus
from src.config.settings import Settings

@pytest.mark.asyncio
async def test_full_queue_workflow():
    """전체 큐 워크플로우 테스트"""
    settings = Settings()

    # 큐 시스템 초기화
    redis_queue = RedisQueue(settings)
    await redis_queue.connect()

    task_manager = TaskManager(redis_queue)
    worker_monitor = WorkerMonitor(redis_queue)

    # 워커 등록
    await worker_monitor.register_worker("test-worker-1")

    # 작업 생성 및 큐에 추가
    request = ScrapingRequest(
        script_name="test_scraper",
        parameters={"url": "https://example.com"}
    )
    await redis_queue.enqueue_task(request)

    # 작업 상태 확인
    status = await task_manager.get_task_status(request.request_id)
    assert status == TaskStatus.PENDING

    # 워커에서 작업 가져오기
    dequeued_task = await redis_queue.dequeue_task("test-worker-1")
    assert dequeued_task.request_id == request.request_id

    # 처리 중 상태 확인
    status = await task_manager.get_task_status(request.request_id)
    assert status == TaskStatus.RUNNING

    # 활성 워커 확인
    active_workers = await worker_monitor.get_active_workers()
    assert len(active_workers) == 1
    assert active_workers[0]["worker_id"] == "test-worker-1"
```

## Final Validation Checklist

- [ ] Redis connection established successfully
- [ ] Tasks can be enqueued and dequeued reliably
- [ ] Worker registration and monitoring works
- [ ] Task lifecycle management functions correctly
- [ ] Failed tasks are handled gracefully
- [ ] All unit tests pass: `uv run pytest tests/test_queue.py -v`
- [ ] Integration tests pass: `uv run pytest tests/test_queue_integration.py -v`
- [ ] No type errors: `uv run mypy src/queue/`
- [ ] No linting errors: `uv run ruff check src/queue/`
- [ ] Korean logging messages are properly formatted

## Anti-Patterns to Avoid

- ❌ Don't use synchronous Redis operations in async code
- ❌ Don't ignore Redis connection errors - handle gracefully
- ❌ Don't store large data in Redis keys - use references
- ❌ Don't forget to cleanup old tasks and inactive workers
- ❌ Don't block the event loop with long-running operations
- ❌ Don't use Redis as a database - it's for caching and queuing
