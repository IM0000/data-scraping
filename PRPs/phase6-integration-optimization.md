# PRP-6: Integration & Optimization

## Goal

Integrate all system components into a complete distributed scraping system with comprehensive testing, performance optimization, monitoring, and production-ready deployment configurations. This phase focuses on system-wide integration, end-to-end testing of RabbitMQ RPC patterns, and operational excellence.

## Why

- **System integration**: Ensures all components work together seamlessly with RabbitMQ RPC communication
- **Performance optimization**: Maximizes throughput and minimizes latency in distributed environment
- **Monitoring & observability**: Provides visibility into system health and RabbitMQ queue performance
- **Production readiness**: Prepares the system for real-world deployment with proper scaling
- **Operational excellence**: Establishes best practices for maintenance and scaling of distributed systems

## What

Build a complete production-ready system that includes:

- End-to-end integration testing across all components with RabbitMQ RPC pattern validation
- Performance benchmarking and optimization for distributed communication
- Comprehensive monitoring and alerting for RabbitMQ queues and worker health
- Docker containerization and orchestration with RabbitMQ clustering
- CI/CD pipeline configuration
- Production deployment documentation
- System scaling and load balancing

### Success Criteria

- [ ] All components integrate successfully with RabbitMQ RPC communication
- [ ] End-to-end tests pass consistently including correlation_id validation
- [ ] Performance benchmarks meet requirements for distributed workloads
- [ ] Monitoring dashboards track RabbitMQ queue metrics and worker status
- [ ] Docker containers build and run correctly with RabbitMQ clustering
- [ ] Documentation is complete and accurate for distributed deployment
- [ ] System can handle production workloads with proper scaling

## All Needed Context

### Documentation & References

```yaml
# Integration Testing
- url: https://docs.pytest.org/en/stable/
  why: Comprehensive testing framework

- url: https://docs.docker.com/
  why: Containerization for deployment

- url: https://kubernetes.io/docs/
  why: Container orchestration (optional)

# RabbitMQ Monitoring
- url: https://www.rabbitmq.com/monitoring.html
  why: RabbitMQ monitoring and metrics collection

- url: https://www.rabbitmq.com/management.html
  why: RabbitMQ management plugin for monitoring

- url: https://www.rabbitmq.com/clustering.html
  why: RabbitMQ clustering for high availability

# Monitoring & Observability
- url: https://prometheus.io/docs/
  why: Metrics collection and alerting

- url: https://grafana.com/docs/
  why: Monitoring dashboards

- url: https://docs.python.org/3/library/logging.html
  why: Structured logging

# Performance
- url: https://locust.io/
  why: Load testing framework

- url: https://docs.python.org/3/library/asyncio.html
  why: Async performance optimization

# Dependencies
- file: PRPs/phase1-core-models.md
  why: Core system foundation

- file: PRPs/phase2-message-queue.md
  why: RabbitMQ RPC system integration

- file: PRPs/phase3-script-manager.md
  why: Script management integration

- file: PRPs/phase4-worker-system.md
  why: Worker system integration

- file: PRPs/phase5-gateway-api.md
  why: API gateway integration
```

### Current Codebase Structure (Complete System)

```
data-scraping-project/
├── src/
│   ├── models/              # Phase 1: Core models
│   ├── config/              # Phase 1: Configuration
│   ├── utils/               # Phase 1: Utilities
│   ├── exceptions.py        # Phase 1: Exceptions
│   ├── queue/               # Phase 2: Message queue
│   ├── scripts/             # Phase 3: Script management
│   ├── worker/              # Phase 4: Worker system
│   └── api/                 # Phase 5: API gateway
├── tests/                   # Comprehensive test suite
├── docker/                  # Docker configurations
├── deploy/                  # Deployment scripts
├── monitoring/              # Monitoring configurations
├── docs/                    # Documentation
└── scripts/                 # Management scripts
```

## Implementation Blueprint

### Task 1: End-to-End Integration Tests

```python
# tests/test_e2e_integration.py
import pytest
import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime, timedelta
from src.config.settings import Settings
from src.queue.redis_queue import RedisQueue
from src.worker.worker_main import ScrapingWorker
from src.api.main import app
from src.api.auth import auth_manager

class TestEndToEndIntegration:
    """종단간 통합 테스트"""

    @pytest.fixture
    async def system_setup(self):
        """전체 시스템 설정"""
        settings = Settings()

        # 테스트용 Redis 설정
        settings.redis_db = 1  # 테스트용 DB

        # Redis 큐 초기화
        redis_queue = RedisQueue(settings)
        await redis_queue.connect()

        # 워커 시작
        worker = ScrapingWorker("test-worker-e2e")
        await worker.initialize()

        # 워커 백그라운드 실행
        worker_task = asyncio.create_task(worker.start())

        # API 서버 시작 (테스트용)
        from fastapi.testclient import TestClient
        api_client = TestClient(app)

        # 테스트 클라이언트 토큰 생성
        token = auth_manager.create_access_token("test-client")

        yield {
            "redis_queue": redis_queue,
            "worker": worker,
            "api_client": api_client,
            "token": token,
            "settings": settings
        }

        # 정리
        await worker.stop()
        worker_task.cancel()

    @pytest.mark.asyncio
    async def test_complete_scraping_workflow(self, system_setup):
        """완전한 스크래핑 워크플로우 테스트"""
        api_client = system_setup["api_client"]
        token = system_setup["token"]

        # 1. 스크래핑 요청 제출
        scraping_request = {
            "script_name": "example_scraper",
            "parameters": {
                "url": "https://httpbin.org/json",
                "method": "GET"
            },
            "timeout": 60
        }

        response = api_client.post(
            "/scrape",
            json=scraping_request,
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        result = response.json()

        # 2. 응답 검증
        assert "request_id" in result
        assert result["status"] in ["completed", "failed"]

        if result["status"] == "completed":
            assert "data" in result
            assert result["data"] is not None
            assert result["execution_time"] > 0

        # 3. 시스템 상태 확인
        status_response = api_client.get("/status")
        assert status_response.status_code == 200

        status_data = status_response.json()
        assert status_data["status"] == "healthy"
        assert status_data["active_workers"] >= 1

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, system_setup):
        """동시 요청 처리 테스트"""
        api_client = system_setup["api_client"]
        token = system_setup["token"]

        # 여러 개의 동시 요청
        requests = []
        for i in range(5):
            request_data = {
                "script_name": "example_scraper",
                "parameters": {"url": f"https://httpbin.org/json?id={i}"},
                "timeout": 30
            }
            requests.append(request_data)

        # 동시 요청 실행
        responses = []
        for req in requests:
            response = api_client.post(
                "/scrape",
                json=req,
                headers={"Authorization": f"Bearer {token}"}
            )
            responses.append(response)

        # 모든 요청이 성공했는지 확인
        for response in responses:
            assert response.status_code == 200
            result = response.json()
            assert "request_id" in result

    @pytest.mark.asyncio
    async def test_error_handling(self, system_setup):
        """오류 처리 테스트"""
        api_client = system_setup["api_client"]
        token = system_setup["token"]

        # 존재하지 않는 스크립트 요청
        invalid_request = {
            "script_name": "nonexistent_script",
            "parameters": {},
            "timeout": 30
        }

        response = api_client.post(
            "/scrape",
            json=invalid_request,
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "failed"
        assert "error" in result
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_authentication_required(self, system_setup):
        """인증 필수 테스트"""
        api_client = system_setup["api_client"]

        # 토큰 없이 요청
        response = api_client.post(
            "/scrape",
            json={"script_name": "test", "parameters": {}}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, system_setup):
        """시스템 헬스 모니터링 테스트"""
        api_client = system_setup["api_client"]

        # 헬스 체크
        health_response = api_client.get("/health")
        assert health_response.status_code == 200

        health_data = health_response.json()
        assert health_data["status"] == "healthy"
        assert "components" in health_data
        assert health_data["components"]["redis"] == "connected"

        # 시스템 상태 확인
        status_response = api_client.get("/status")
        assert status_response.status_code == 200

        status_data = status_response.json()
        assert "queue_length" in status_data
        assert "active_workers" in status_data
        assert "memory_usage" in status_data
        assert "cpu_usage" in status_data
```

### Task 2: Performance Optimization

```python
# tests/test_performance.py
import pytest
import asyncio
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from src.config.settings import Settings
from src.queue.redis_queue import RedisQueue
from src.models.base import ScrapingRequest

class TestPerformanceOptimization:
    """성능 최적화 테스트"""

    @pytest.fixture
    async def performance_setup(self):
        """성능 테스트 설정"""
        settings = Settings()
        settings.redis_db = 2  # 성능 테스트용 DB

        redis_queue = RedisQueue(settings)
        await redis_queue.connect()

        yield {"redis_queue": redis_queue, "settings": settings}

        # 정리
        await redis_queue.redis_client.flushdb()

    @pytest.mark.asyncio
    async def test_queue_throughput(self, performance_setup):
        """큐 처리량 테스트"""
        redis_queue = performance_setup["redis_queue"]

        # 테스트 요청들 생성
        requests = []
        for i in range(1000):
            request = ScrapingRequest(
                script_name="performance_test",
                parameters={"index": i}
            )
            requests.append(request)

        # 큐에 추가 성능 측정
        start_time = time.time()

        for request in requests:
            await redis_queue.enqueue_task(request)

        enqueue_time = time.time() - start_time

        # 큐에서 제거 성능 측정
        start_time = time.time()

        dequeued_count = 0
        while dequeued_count < 1000:
            task = await redis_queue.dequeue_task("perf-worker")
            if task:
                dequeued_count += 1

        dequeue_time = time.time() - start_time

        # 성능 지표 계산
        enqueue_rate = len(requests) / enqueue_time
        dequeue_rate = dequeued_count / dequeue_time

        print(f"큐 추가 속도: {enqueue_rate:.2f} req/sec")
        print(f"큐 제거 속도: {dequeue_rate:.2f} req/sec")

        # 성능 기준 검증
        assert enqueue_rate > 100  # 최소 100 req/sec
        assert dequeue_rate > 100  # 최소 100 req/sec

    @pytest.mark.asyncio
    async def test_memory_usage_optimization(self, performance_setup):
        """메모리 사용량 최적화 테스트"""
        import psutil
        import gc

        redis_queue = performance_setup["redis_queue"]

        # 초기 메모리 사용량
        gc.collect()
        initial_memory = psutil.Process().memory_info().rss

        # 대량 요청 생성 및 처리
        for batch in range(10):
            requests = []
            for i in range(1000):
                request = ScrapingRequest(
                    script_name="memory_test",
                    parameters={"batch": batch, "index": i}
                )
                requests.append(request)

            # 큐에 추가
            for request in requests:
                await redis_queue.enqueue_task(request)

            # 큐에서 제거
            for _ in range(1000):
                await redis_queue.dequeue_task("memory-worker")

            # 메모리 정리
            del requests
            gc.collect()

        # 최종 메모리 사용량
        final_memory = psutil.Process().memory_info().rss
        memory_increase = final_memory - initial_memory

        print(f"메모리 사용량 증가: {memory_increase / 1024 / 1024:.2f} MB")

        # 메모리 증가량이 합리적인 범위인지 확인
        assert memory_increase < 100 * 1024 * 1024  # 100MB 이하

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, performance_setup):
        """동시 처리 성능 테스트"""
        redis_queue = performance_setup["redis_queue"]

        # 테스트 요청들 생성
        requests = []
        for i in range(500):
            request = ScrapingRequest(
                script_name="concurrent_test",
                parameters={"index": i}
            )
            requests.append(request)

        # 모든 요청을 큐에 추가
        for request in requests:
            await redis_queue.enqueue_task(request)

        # 동시 워커 시뮬레이션
        async def worker_simulation(worker_id: str):
            """워커 시뮬레이션"""
            processed = 0
            while processed < 100:  # 각 워커가 100개 처리
                task = await redis_queue.dequeue_task(worker_id)
                if task:
                    processed += 1
                    # 간단한 처리 시뮬레이션
                    await asyncio.sleep(0.01)
                else:
                    await asyncio.sleep(0.1)
            return processed

        # 5개 워커 동시 실행
        start_time = time.time()

        workers = []
        for i in range(5):
            worker_task = asyncio.create_task(worker_simulation(f"worker-{i}"))
            workers.append(worker_task)

        results = await asyncio.gather(*workers)

        total_time = time.time() - start_time
        total_processed = sum(results)

        processing_rate = total_processed / total_time

        print(f"동시 처리 속도: {processing_rate:.2f} req/sec")
        print(f"총 처리 시간: {total_time:.2f} seconds")

        # 성능 기준 검증
        assert processing_rate > 50  # 최소 50 req/sec
        assert total_processed == 500  # 모든 요청이 처리되었는지 확인
```

### Task 3: Docker Configuration

**Dependency Management Strategy:**

- **Project Dependencies**: Use `pyproject.toml` + `uv` (Core system dependencies for Gateway, Worker, etc.)
- **Script Dependencies**: Use `requirements.txt` (Dynamic dependencies for individual scraping scripts)

Each scraping script can include its own `requirements.txt` in its directory. The worker's child process will install these dependencies in an isolated virtual environment before script execution.

**Script Directory Structure Example:**

```
scripts/
├── example_scraper/
│   ├── scraper.py
│   └── requirements.txt  # 이 스크립트만의 의존성
├── advanced_scraper/
│   ├── scraper.py
│   └── requirements.txt  # 다른 의존성 조합
└── simple_scraper/
    └── scraper.py        # requirements.txt 없음 (기본 의존성만 사용)
```

```dockerfile
# docker/Dockerfile.api
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install --no-cache-dir uv

# 프로젝트 의존성 파일 복사 (Docker 레이어 캐시 활용)
COPY pyproject.toml uv.lock* ./

# uv를 사용하여 프로젝트 의존성 설치
RUN uv pip sync --system

# 애플리케이션 코드 복사
COPY src/ src/
COPY .env .env

# 포트 노출
EXPOSE 8000

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 애플리케이션 실행
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# docker/Dockerfile.worker
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install --no-cache-dir uv

# 프로젝트 의존성 파일 복사 (Docker 레이어 캐시 활용)
COPY pyproject.toml uv.lock* ./

# uv를 사용하여 프로젝트 의존성 설치
RUN uv pip sync --system

# 애플리케이션 코드 복사
COPY src/ src/
COPY .env .env

# 스크립트 캐시 디렉터리 생성
RUN mkdir -p /app/cache/scripts

# 워커 실행
CMD ["python", "-m", "src.worker.worker_main"]
```

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - '5672:5672'
      - '15672:15672'
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    environment:
      - RABBITMQ_DEFAULT_USER=admin
      - RABBITMQ_DEFAULT_PASS=admin123

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.api
    ports:
      - '8000:8000'
    depends_on:
      - rabbitmq
    environment:
      - RABBITMQ_URL=amqp://admin:admin123@rabbitmq:5672/
      - RABBITMQ_TASK_QUEUE=scraping_tasks
      - SCRIPT_REPOSITORY_TYPE=${SCRIPT_REPOSITORY_TYPE:-git}
      - SCRIPT_REPOSITORY_URL=${SCRIPT_REPOSITORY_URL}
      - S3_BUCKET_NAME=${S3_BUCKET_NAME}
      - S3_REGION=${S3_REGION}
      - S3_ACCESS_KEY=${S3_ACCESS_KEY}
      - S3_SECRET_KEY=${S3_SECRET_KEY}
      - S3_PREFIX=${S3_PREFIX:-scripts/}
    volumes:
      - ../logs:/app/logs
    restart: unless-stopped

  worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.worker
    depends_on:
      - rabbitmq
    environment:
      - RABBITMQ_URL=amqp://admin:admin123@rabbitmq:5672/
      - RABBITMQ_TASK_QUEUE=scraping_tasks
      - SCRIPT_REPOSITORY_TYPE=${SCRIPT_REPOSITORY_TYPE:-git}
      - SCRIPT_REPOSITORY_URL=${SCRIPT_REPOSITORY_URL}
      - S3_BUCKET_NAME=${S3_BUCKET_NAME}
      - S3_REGION=${S3_REGION}
      - S3_ACCESS_KEY=${S3_ACCESS_KEY}
      - S3_SECRET_KEY=${S3_SECRET_KEY}
      - S3_PREFIX=${S3_PREFIX:-scripts/}
    volumes:
      - ../logs:/app/logs
      - script_cache:/app/cache
    restart: unless-stopped
    scale: 3

  prometheus:
    image: prom/prometheus:latest
    ports:
      - '9090:9090'
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

  grafana:
    image: grafana/grafana:latest
    ports:
      - '3000:3000'
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/var/lib/grafana/dashboards
      - ./grafana/provisioning:/etc/grafana/provisioning

volumes:
  rabbitmq_data:
  script_cache:
  prometheus_data:
  grafana_data:
```

### Task 4: Monitoring Configuration

```python
# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from typing import Dict, Any
import time
from functools import wraps

# 메트릭 레지스트리
REGISTRY = CollectorRegistry()

# 메트릭 정의
REQUEST_COUNT = Counter(
    'scraping_requests_total',
    'Total number of scraping requests',
    ['script_name', 'status', 'client_id'],
    registry=REGISTRY
)

REQUEST_DURATION = Histogram(
    'scraping_request_duration_seconds',
    'Duration of scraping requests',
    ['script_name'],
    registry=REGISTRY
)

QUEUE_LENGTH = Gauge(
    'scraping_queue_length',
    'Current length of the scraping queue',
    registry=REGISTRY
)

ACTIVE_WORKERS = Gauge(
    'scraping_active_workers',
    'Number of active workers',
    registry=REGISTRY
)

SYSTEM_MEMORY = Gauge(
    'system_memory_usage_percent',
    'System memory usage percentage',
    registry=REGISTRY
)

SYSTEM_CPU = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=REGISTRY
)

def track_request_metrics(script_name: str, client_id: str = None):
    """요청 메트릭 추적 데코레이터"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)

                # 성공 메트릭 기록
                REQUEST_COUNT.labels(
                    script_name=script_name,
                    status='success',
                    client_id=client_id or 'unknown'
                ).inc()

                return result

            except Exception as e:
                # 실패 메트릭 기록
                REQUEST_COUNT.labels(
                    script_name=script_name,
                    status='error',
                    client_id=client_id or 'unknown'
                ).inc()

                raise

            finally:
                # 실행 시간 기록
                duration = time.time() - start_time
                REQUEST_DURATION.labels(script_name=script_name).observe(duration)

        return wrapper
    return decorator

async def update_system_metrics():
    """시스템 메트릭 업데이트"""
    import psutil

    # 메모리 사용률
    memory_percent = psutil.virtual_memory().percent
    SYSTEM_MEMORY.set(memory_percent)

    # CPU 사용률
    cpu_percent = psutil.cpu_percent(interval=1)
    SYSTEM_CPU.set(cpu_percent)
```

### Task 5: Deployment Scripts

```bash
#!/bin/bash
# deploy/deploy.sh

set -e

echo "=== 스크래핑 시스템 배포 시작 ==="

# 환경 변수 확인
if [[ -z "$ENVIRONMENT" ]]; then
    echo "오류: ENVIRONMENT 변수가 설정되지 않았습니다"
    exit 1
fi

# 배포 환경별 설정
case $ENVIRONMENT in
    "development")
        COMPOSE_FILE="docker-compose.dev.yml"
        ;;
    "staging")
        COMPOSE_FILE="docker-compose.staging.yml"
        ;;
    "production")
        COMPOSE_FILE="docker-compose.prod.yml"
        ;;
    *)
        echo "오류: 지원되지 않는 환경입니다: $ENVIRONMENT"
        exit 1
        ;;
esac

echo "배포 환경: $ENVIRONMENT"
echo "Docker Compose 파일: $COMPOSE_FILE"

# 기존 컨테이너 중지
echo "기존 컨테이너 중지 중..."
docker-compose -f $COMPOSE_FILE down

# 최신 이미지 빌드
echo "Docker 이미지 빌드 중..."
docker-compose -f $COMPOSE_FILE build

# 컨테이너 시작
echo "컨테이너 시작 중..."
docker-compose -f $COMPOSE_FILE up -d

# 헬스 체크
echo "헬스 체크 수행 중..."
sleep 10

API_URL="http://localhost:8000"
HEALTH_CHECK_URL="$API_URL/health"

# 최대 30초 동안 헬스 체크
for i in {1..30}; do
    if curl -f $HEALTH_CHECK_URL > /dev/null 2>&1; then
        echo "✅ 헬스 체크 성공"
        break
    fi

    if [ $i -eq 30 ]; then
        echo "❌ 헬스 체크 실패: 30초 타임아웃"
        exit 1
    fi

    echo "헬스 체크 시도 $i/30..."
    sleep 1
done

# 시스템 상태 확인
echo "시스템 상태 확인 중..."
curl -s "$API_URL/status" | jq '.'

echo "=== 배포 완료 ==="
```

## Final Validation Checklist

### Dependency Management Validation

- [ ] Project dependencies are properly defined in `pyproject.toml`: `uv tree`
- [ ] Development dependencies are installed correctly: `uv sync --dev`
- [ ] Lock file is up to date: `uv lock --check`

### System Integration Validation

- [ ] All components integrate successfully with RabbitMQ RPC communication
- [ ] End-to-end tests pass consistently including correlation_id validation: `uv run pytest tests/test_e2e_integration.py -v`
- [ ] Performance benchmarks meet requirements for distributed workloads: `uv run pytest tests/test_performance.py -v`
- [ ] Docker containers build and run correctly with RabbitMQ clustering: `docker-compose up -d`

### Repository Integration Validation

- [ ] Git repository integration works correctly (if configured)
- [ ] HTTP repository integration works correctly (if configured)
- [ ] S3 repository integration works correctly (if configured)
- [ ] boto3 dependency is installed for S3 support: `uv add boto3`

### Monitoring and Documentation Validation

- [ ] Monitoring dashboards are functional: http://localhost:3000
- [ ] API documentation is complete: http://localhost:8000/docs
- [ ] All unit tests pass: `uv run pytest tests/ -v`
- [ ] No type errors across all modules: `uv run mypy src/`
- [ ] No linting errors: `uv run ruff check src/`
- [ ] System can handle production workloads with proper scaling (load testing)
- [ ] Documentation is complete and accurate for distributed deployment

### Script Dependency Management Validation

- [ ] Per-script `requirements.txt` files are processed correctly
- [ ] Worker installs dependencies in isolated environment before script execution
- [ ] Script dependency conflicts do not affect the system

## Anti-Patterns to Avoid

### Dependency Management Related

- ❌ Don't mix package managers - use `uv` for project dependencies, not `pip` or `poetry`
- ❌ Don't put script-specific dependencies in `pyproject.toml` - use per-script `requirements.txt`
- ❌ Don't skip dependency locking - always commit `uv.lock` file
- ❌ Don't install system packages in Docker without cleanup - use multi-stage builds

### System Integration Related

- ❌ Don't skip integration testing - test all component interactions
- ❌ Don't ignore performance bottlenecks - profile and optimize
- ❌ Don't deploy without monitoring - implement comprehensive observability
- ❌ Don't hardcode configuration - use environment variables
- ❌ Don't skip documentation - maintain up-to-date docs
- ❌ Don't ignore security - implement proper authentication and authorization
- ❌ Don't forget backup and recovery procedures
