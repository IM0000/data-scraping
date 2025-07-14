# PRP-1: Core Models & Shared Components

## Goal

Create the foundational data models, shared utilities, and configuration management system for the Gateway-Worker Scraping System. This includes defining all core data structures, exception handling, logging system, and common utilities that will be used across all other components.

## Why

- **Foundation for all components**: All other phases depend on these core models
- **Type safety**: Ensures consistent data structures across the distributed system
- **Error handling**: Provides standardized exception handling patterns
- **Logging consistency**: Establishes unified logging in Korean across all components
- **Configuration management**: Centralizes system configuration and environment variables including RabbitMQ settings

## What

Build the core foundation that includes:

- Data models for requests, responses, tasks, and scripts
- Shared utilities and helper functions
- Configuration management with environment variables (including RabbitMQ settings)
- Exception handling classes
- Logging system with Korean messages
- Common constants and enums

### Success Criteria

- [ ] All data models defined with proper type hints
- [ ] Configuration system loads from environment variables including RabbitMQ settings
- [ ] Logging system outputs Korean messages consistently
- [ ] Exception handling covers all error scenarios
- [ ] Unit tests achieve 100% coverage
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# Core Python Libraries
- url: https://docs.python.org/3/library/typing.html
  why: Type hints for data models and function signatures

- url: https://docs.python.org/3/library/dataclasses.html
  why: Data class patterns for model definitions

- url: https://pydantic-docs.helpmanual.io/
  why: Data validation and serialization patterns

- url: https://docs.python.org/3/library/logging.html
  why: Structured logging implementation in Korean

- url: https://python-dotenv.readthedocs.io/en/latest/
  why: Environment variable management

# RabbitMQ Configuration
- url: https://pika.readthedocs.io/en/stable/
  why: RabbitMQ connection configuration patterns

- url: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
  why: RPC pattern configuration requirements
```

### Current Codebase Structure

```
data-scraping-project/
├── examples/
│   ├── basic_structure.py      # Coding patterns
│   ├── test_pattern.py         # Test patterns
│   └── README.md              # Documentation patterns
├── PRPs/
│   └── templates/
└── INITIAL.md                 # Requirements
```

### Key Requirements from INITIAL.md

- Language: Python with Korean comments and docstrings
- Architecture: Distributed gateway-worker pattern
- Message queue communication between components
- Script storage with version control
- Child process isolation for security
- Synchronous response delivery with timeout handling

## Implementation Blueprint

### Task 1: Core Data Models

```python
# models/base.py
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class TaskStatus(Enum):
    """작업 상태 열거형"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class ScrapingRequest:
    """스크래핑 요청 데이터 모델"""
    script_name: str
    script_version: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = 300
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)

@dataclass
class ScrapingResponse:
    """스크래핑 응답 데이터 모델"""
    request_id: str
    status: TaskStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    completed_at: Optional[datetime] = None
```

### Task 2: Exception Handling

```python
# exceptions.py
class ScrapingSystemException(Exception):
    """스크래핑 시스템 기본 예외 클래스"""
    pass

class ScriptNotFoundException(ScrapingSystemException):
    """스크립트를 찾을 수 없을 때 발생하는 예외"""
    pass

class ScriptExecutionException(ScrapingSystemException):
    """스크립트 실행 중 발생하는 예외"""
    pass

class QueueConnectionException(ScrapingSystemException):
    """큐 연결 오류 시 발생하는 예외"""
    pass
```

### Task 3: Configuration Management

```python
# config/settings.py
from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """시스템 설정 관리 클래스"""
    # Redis 설정
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # 스크립트 저장소 설정
    script_repository_type: str = "git"  # git, http, s3
    script_repository_url: Optional[str] = None  # For git/http
    script_cache_dir: str = "./cache/scripts"

    # S3 설정 (script_repository_type이 s3일 때 사용)
    s3_bucket_name: Optional[str] = None
    s3_region: str = "ap-northeast-2"
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_prefix: str = "scripts/"

    # 워커 설정
    worker_timeout: int = 300
    max_workers: int = 4

    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Task 4: Logging System

```python
# utils/logging.py
import logging
from typing import Optional
from config.settings import Settings

def setup_logging(settings: Settings) -> logging.Logger:
    """
    한국어 로깅 시스템 설정

    Args:
        settings: 시스템 설정 객체

    Returns:
        설정된 로거 객체
    """
    logger = logging.getLogger("scraping_system")
    logger.setLevel(getattr(logging, settings.log_level))

    # 한국어 로그 메시지 포맷터
    formatter = logging.Formatter(
        fmt=settings.log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
```

### Task 5: Common Utilities

```python
# utils/helpers.py
import asyncio
import hashlib
from typing import Any, Dict, Optional
from datetime import datetime

def generate_task_id() -> str:
    """고유한 작업 ID 생성"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = str(uuid.uuid4())[:8]
    return f"task_{timestamp}_{random_str}"

def calculate_file_hash(file_path: str) -> str:
    """파일의 SHA-256 해시 계산"""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

async def retry_with_backoff(
    func: callable,
    max_retries: int = 3,
    initial_delay: float = 1.0
) -> Any:
    """지수 백오프를 사용한 재시도 데코레이터"""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = initial_delay * (2 ** attempt)
            await asyncio.sleep(delay)
```

## Integration Points

### Project Structure

```
src/
├── models/
│   ├── __init__.py
│   ├── base.py              # Core data models
│   └── enums.py             # Enumerations
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration management
├── utils/
│   ├── __init__.py
│   ├── logging.py           # Logging system
│   └── helpers.py           # Common utilities
├── exceptions.py            # Exception classes
└── __init__.py
```

### Environment Variables (.env)

```
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Script Repository Configuration
SCRIPT_REPOSITORY_TYPE=git  # git, http, s3
SCRIPT_REPOSITORY_URL=https://github.com/your-org/scraping-scripts  # For git/http
SCRIPT_CACHE_DIR=./cache/scripts

# S3 Configuration (when SCRIPT_REPOSITORY_TYPE=s3)
S3_BUCKET_NAME=your-scraping-scripts-bucket
S3_REGION=ap-northeast-2
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_PREFIX=scripts/

# Worker Configuration
WORKER_TIMEOUT=300
MAX_WORKERS=4

# Logging
LOG_LEVEL=INFO
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Type checking and linting
uv run mypy src/
uv run ruff check src/ --fix

# Expected: No errors. All type hints properly defined.
```

### Level 2: Unit Tests

```python
# tests/test_models.py
import pytest
from datetime import datetime
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.exceptions import ScriptNotFoundException

class TestScrapingRequest:
    """스크래핑 요청 모델 테스트"""

    def test_request_creation(self):
        """요청 생성 테스트"""
        request = ScrapingRequest(
            script_name="example_scraper",
            parameters={"url": "https://example.com"}
        )
        assert request.script_name == "example_scraper"
        assert request.parameters["url"] == "https://example.com"
        assert request.timeout == 300  # 기본값
        assert request.request_id is not None

    def test_request_with_version(self):
        """버전 지정 요청 테스트"""
        request = ScrapingRequest(
            script_name="example_scraper",
            script_version="1.0.0"
        )
        assert request.script_version == "1.0.0"

class TestScrapingResponse:
    """스크래핑 응답 모델 테스트"""

    def test_successful_response(self):
        """성공 응답 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        )
        assert response.status == TaskStatus.COMPLETED
        assert response.data["result"] == "success"
        assert response.error is None

    def test_error_response(self):
        """오류 응답 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.FAILED,
            error="스크립트 실행 실패"
        )
        assert response.status == TaskStatus.FAILED
        assert response.error == "스크립트 실행 실패"
        assert response.data is None

# tests/test_config.py
def test_settings_from_env():
    """환경 변수로부터 설정 로드 테스트"""
    from src.config.settings import Settings

    settings = Settings()
    assert settings.redis_host == "localhost"
    assert settings.redis_port == 6379
    assert settings.worker_timeout == 300
```

```bash
# Run unit tests
uv run pytest tests/test_models.py -v
uv run pytest tests/test_config.py -v
uv run pytest tests/test_utils.py -v

# Expected: All tests pass with 100% coverage
```

### Level 3: Integration Test

```python
# tests/test_integration.py
def test_full_model_workflow():
    """전체 모델 워크플로우 테스트"""
    from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
    from src.config.settings import Settings
    from src.utils.logging import setup_logging

    # 설정 로드
    settings = Settings()
    logger = setup_logging(settings)

    # 요청 생성
    request = ScrapingRequest(
        script_name="test_scraper",
        parameters={"url": "https://example.com"}
    )

    # 응답 생성
    response = ScrapingResponse(
        request_id=request.request_id,
        status=TaskStatus.COMPLETED,
        data={"scraped_data": "test"}
    )

    # 로깅 테스트
    logger.info(f"요청 처리 완료: {request.request_id}")

    assert response.request_id == request.request_id
    assert response.status == TaskStatus.COMPLETED
```

## Final Validation Checklist

- [ ] All data models properly defined with type hints
- [ ] Configuration system loads from .env file
- [ ] Logging system outputs Korean messages
- [ ] Exception classes cover all error scenarios
- [ ] Unit tests achieve 100% coverage: `uv run pytest tests/ --cov=src/`
- [ ] No type errors: `uv run mypy src/`
- [ ] No linting errors: `uv run ruff check src/`
- [ ] Integration test passes
- [ ] Documentation in Korean added to examples/

## Anti-Patterns to Avoid

- ❌ Don't use generic Exception - create specific exception classes
- ❌ Don't hardcode configuration values - use environment variables
- ❌ Don't write English comments - use Korean consistently
- ❌ Don't skip type hints - every function needs proper typing
- ❌ Don't ignore validation - all input data must be validated
- ❌ Don't use print() for logging - use the logging system
