# PRP-5: Gateway API

## Goal

Implement a FastAPI-based REST API gateway that receives scraping requests via HTTP, validates input, forwards tasks to RabbitMQ using RPC pattern, and returns results synchronously with correlation_id matching and timeout handling. The API should support authentication, rate limiting, and real-time status monitoring.

## Why

- **HTTP Interface**: Provides standard REST API access for clients
- **Synchronous responses**: Clients get immediate results using RabbitMQ RPC pattern without polling
- **Input validation**: Ensures request data integrity before processing
- **Rate limiting**: Prevents system overload from excessive requests
- **Authentication**: Secures API access with token-based authentication
- **Monitoring**: Real-time visibility into system status and performance
- **RPC communication**: Enables synchronous request-response pattern with correlation_id

## What

Build a comprehensive API gateway that includes:

- FastAPI REST endpoints for scraping requests
- Request validation and parameter sanitization
- RabbitMQ RPC integration with correlation_id and reply_to queues
- Synchronous response handling with timeout management
- Real-time WebSocket connections for status updates
- Authentication middleware with API keys
- Rate limiting and request throttling
- Health checks and system monitoring endpoints

### Success Criteria

- [ ] API accepts and validates scraping requests
- [ ] Tasks are sent to RabbitMQ with correlation_id and reply_to queue
- [ ] Results are received synchronously via RPC pattern with timeout
- [ ] WebSocket connections provide real-time updates
- [ ] Authentication and rate limiting work correctly
- [ ] Health checks report system status accurately
- [ ] API documentation is auto-generated and complete
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# FastAPI Framework
- url: https://fastapi.tiangolo.com/
  why: Main API framework documentation

- url: https://fastapi.tiangolo.com/tutorial/security/
  why: Authentication and security patterns

- url: https://fastapi.tiangolo.com/advanced/websockets/
  why: WebSocket implementation for real-time updates

- url: https://fastapi.tiangolo.com/async/
  why: Async/await patterns for RabbitMQ RPC integration

# RabbitMQ Integration
- url: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
  why: RPC pattern implementation for synchronous responses

- url: https://aio-pika.readthedocs.io/en/latest/
  why: Async RabbitMQ client for FastAPI integration

# Additional Libraries
- url: https://slowapi.readthedocs.io/
  why: Rate limiting for FastAPI

- url: https://docs.pydantic.dev/
  why: Request/response validation models

# Dependencies
- file: PRPs/phase1-core-models.md
  why: Uses core data models and configuration

- file: PRPs/phase2-message-queue.md
  why: RabbitMQ RPC integration for task management

- file: examples/basic_structure.py
  why: Follow existing coding patterns
```

### Current Codebase Structure (After Phase 1-4)

```
src/
├── models/
│   ├── base.py              # Core data models
│   └── enums.py             # Task status enums
├── config/
│   └── settings.py          # Configuration
├── utils/
│   ├── logging.py           # Logging system
│   └── helpers.py           # Common utilities
├── exceptions.py            # Exception classes
├── queue/                   # Message queue system
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
├── scripts/                 # Script management
│   ├── metadata.py
│   ├── repository.py
│   ├── cache_manager.py
│   └── downloader.py
├── worker/                  # Worker system
│   ├── process_manager.py
│   ├── script_executor.py
│   └── worker_main.py
└── api/                     # NEW: API Gateway
    ├── __init__.py
    ├── models.py            # API request/response models
    ├── auth.py              # Authentication middleware
    ├── rate_limit.py        # Rate limiting
    ├── endpoints/
    │   ├── __init__.py
    │   ├── scraping.py      # Scraping endpoints
    │   ├── status.py        # Status and monitoring
    │   └── websocket.py     # WebSocket handlers
    └── main.py              # FastAPI application
```

### Key Requirements from INITIAL.md

- FastAPI for gateway REST API
- Synchronous response delivery with timeout handling
- Authentication with API key or token-based access control
- Rate limiting per-site and per-client
- Real-time status updates and monitoring

## Implementation Blueprint

### Task 1: API Models

```python
# api/models.py
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List
from datetime import datetime
from src.models.base import TaskStatus

class ScrapingRequestAPI(BaseModel):
    """API 스크래핑 요청 모델"""
    script_name: str = Field(..., description="실행할 스크립트 이름")
    script_version: Optional[str] = Field(None, description="스크립트 버전 (기본값: 최신)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="스크립트 매개변수")
    timeout: int = Field(default=300, ge=1, le=3600, description="타임아웃 (초)")

    @validator('script_name')
    def validate_script_name(cls, v):
        """스크립트 이름 유효성 검사"""
        if not v or not v.strip():
            raise ValueError('스크립트 이름은 필수입니다')

        # 허용되는 문자만 포함
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('스크립트 이름은 알파벳, 숫자, _, - 만 포함할 수 있습니다')

        return v.strip()

    @validator('parameters')
    def validate_parameters(cls, v):
        """매개변수 유효성 검사"""
        if not isinstance(v, dict):
            raise ValueError('매개변수는 딕셔너리 형태여야 합니다')

        # 매개변수 키 검증
        for key in v.keys():
            if not isinstance(key, str):
                raise ValueError('매개변수 키는 문자열이어야 합니다')

        return v

class ScrapingResponseAPI(BaseModel):
    """API 스크래핑 응답 모델"""
    request_id: str = Field(..., description="요청 고유 ID")
    status: TaskStatus = Field(..., description="작업 상태")
    data: Optional[Dict[str, Any]] = Field(None, description="스크래핑 결과 데이터")
    error: Optional[str] = Field(None, description="오류 메시지")
    execution_time: float = Field(..., description="실행 시간 (초)")
    created_at: datetime = Field(..., description="요청 생성 시간")
    completed_at: Optional[datetime] = Field(None, description="완료 시간")

class SystemStatusResponse(BaseModel):
    """시스템 상태 응답 모델"""
    status: str = Field(..., description="시스템 상태")
    queue_length: int = Field(..., description="대기 중인 작업 수")
    active_workers: int = Field(..., description="활성 워커 수")
    completed_tasks: int = Field(..., description="완료된 작업 수")
    failed_tasks: int = Field(..., description="실패한 작업 수")
    uptime: float = Field(..., description="시스템 업타임 (초)")
    memory_usage: float = Field(..., description="메모리 사용률 (%)")
    cpu_usage: float = Field(..., description="CPU 사용률 (%)")

class WebSocketMessage(BaseModel):
    """웹소켓 메시지 모델"""
    type: str = Field(..., description="메시지 타입")
    request_id: Optional[str] = Field(None, description="요청 ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="메시지 데이터")
    timestamp: datetime = Field(default_factory=datetime.now, description="메시지 시간")

class ErrorResponse(BaseModel):
    """오류 응답 모델"""
    error: str = Field(..., description="오류 메시지")
    detail: Optional[str] = Field(None, description="상세 오류 정보")
    code: Optional[str] = Field(None, description="오류 코드")
    timestamp: datetime = Field(default_factory=datetime.now, description="오류 발생 시간")
```

### Task 2: Authentication

```python
# api/auth.py
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import jwt
from datetime import datetime, timedelta
from src.config.settings import Settings
from src.utils.logging import setup_logging

security = HTTPBearer()

class AuthManager:
    """인증 관리자"""

    def __init__(self, settings: Settings):
        """인증 관리자 초기화"""
        self.settings = settings
        self.logger = setup_logging(settings)
        self.secret_key = settings.jwt_secret_key
        self.algorithm = "HS256"

    def create_access_token(self, client_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """
        액세스 토큰 생성

        Args:
            client_id: 클라이언트 ID
            expires_delta: 만료 시간 (기본값: 24시간)

        Returns:
            JWT 토큰
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=24)

        to_encode = {
            "client_id": client_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> dict:
        """
        토큰 검증

        Args:
            token: JWT 토큰

        Returns:
            토큰 페이로드

        Raises:
            HTTPException: 토큰이 유효하지 않을 때
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # 토큰 타입 확인
            if payload.get("type") != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="잘못된 토큰 타입",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            client_id = payload.get("client_id")
            if not client_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="토큰에 클라이언트 ID가 없습니다",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰이 만료되었습니다",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰을 검증할 수 없습니다",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_current_client(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
        """
        현재 클라이언트 정보 가져오기

        Args:
            credentials: HTTP 인증 정보

        Returns:
            클라이언트 ID
        """
        payload = self.verify_token(credentials.credentials)
        client_id = payload.get("client_id")

        self.logger.info(f"인증된 클라이언트: {client_id}")
        return client_id

# 전역 인증 관리자
auth_manager = AuthManager(Settings())

# 의존성 함수
def get_current_client(client_id: str = Depends(auth_manager.get_current_client)) -> str:
    """현재 클라이언트 의존성"""
    return client_id
```

### Task 3: Main API Application

```python
# api/main.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
from src.config.settings import Settings
from src.queue.redis_queue import RedisQueue
from src.queue.task_manager import TaskManager
from src.queue.worker_monitor import WorkerMonitor
from src.models.base import ScrapingRequest
from src.api.models import ScrapingRequestAPI, ScrapingResponseAPI, SystemStatusResponse
from src.api.auth import get_current_client
from src.utils.logging import setup_logging

# 전역 변수
settings = Settings()
logger = setup_logging(settings)
redis_queue = None
task_manager = None
worker_monitor = None
app_start_time = datetime.now()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    global redis_queue, task_manager, worker_monitor

    # 시작 시 초기화
    logger.info("API 서버 시작")

    try:
        # Redis 큐 연결
        redis_queue = RedisQueue(settings)
        await redis_queue.connect()

        # 컴포넌트 초기화
        task_manager = TaskManager(redis_queue)
        worker_monitor = WorkerMonitor(redis_queue)

        logger.info("API 서버 초기화 완료")

        yield

    except Exception as e:
        logger.error(f"API 서버 초기화 실패: {e}")
        raise
    finally:
        # 종료 시 정리
        logger.info("API 서버 종료")

# FastAPI 앱 생성
app = FastAPI(
    title="스크래핑 시스템 API",
    description="분산 웹 스크래핑 시스템 REST API",
    version="1.0.0",
    lifespan=lifespan
)

# 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.get("/", tags=["Root"])
async def root():
    """루트 엔드포인트"""
    return {
        "message": "스크래핑 시스템 API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/scrape", response_model=ScrapingResponseAPI, tags=["Scraping"])
async def submit_scraping_request(
    request: ScrapingRequestAPI,
    background_tasks: BackgroundTasks,
    client_id: str = Depends(get_current_client)
):
    """
    스크래핑 요청 제출

    Args:
        request: 스크래핑 요청 데이터
        background_tasks: 백그라운드 작업
        client_id: 클라이언트 ID

    Returns:
        스크래핑 응답
    """
    try:
        logger.info(f"스크래핑 요청 수신: {request.script_name} (클라이언트: {client_id})")

        # 내부 요청 모델로 변환
        internal_request = ScrapingRequest(
            script_name=request.script_name,
            script_version=request.script_version,
            parameters=request.parameters,
            timeout=request.timeout
        )

        # 큐에 작업 추가
        await redis_queue.enqueue_task(internal_request)

        # 동기적 응답 대기 (타임아웃 포함)
        response = await wait_for_task_completion(
            internal_request.request_id,
            timeout=request.timeout + 30  # 추가 30초 여유
        )

        logger.info(f"스크래핑 요청 완료: {internal_request.request_id}")

        return ScrapingResponseAPI(
            request_id=response.request_id,
            status=response.status,
            data=response.data,
            error=response.error,
            execution_time=response.execution_time,
            created_at=internal_request.created_at,
            completed_at=response.completed_at
        )

    except Exception as e:
        logger.error(f"스크래핑 요청 처리 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"스크래핑 요청 처리 중 오류가 발생했습니다: {str(e)}"
        )

async def wait_for_task_completion(request_id: str, timeout: int = 300):
    """
    작업 완료 대기

    Args:
        request_id: 요청 ID
        timeout: 대기 타임아웃 (초)

    Returns:
        완료된 작업 응답
    """
    start_time = datetime.now()

    while (datetime.now() - start_time).total_seconds() < timeout:
        # 작업 상태 확인
        status = await task_manager.get_task_status(request_id)

        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            # 완료된 작업 결과 가져오기
            if status == TaskStatus.COMPLETED:
                result = await redis_queue.redis_client.hget(
                    redis_queue.completed_queue, request_id
                )
            else:
                result = await redis_queue.redis_client.hget(
                    redis_queue.failed_queue, request_id
                )

            if result:
                import json
                result_data = json.loads(result)

                from src.models.base import ScrapingResponse
                return ScrapingResponse(
                    request_id=result_data["request_id"],
                    status=TaskStatus(result_data["status"]),
                    data=result_data.get("data"),
                    error=result_data.get("error"),
                    execution_time=result_data["execution_time"],
                    completed_at=datetime.fromisoformat(result_data["completed_at"]) if result_data.get("completed_at") else None
                )

        # 1초 대기
        await asyncio.sleep(1)

    # 타임아웃 발생
    raise HTTPException(
        status_code=408,
        detail=f"작업이 {timeout}초 내에 완료되지 않았습니다"
    )

@app.get("/status", response_model=SystemStatusResponse, tags=["Monitoring"])
async def get_system_status():
    """시스템 상태 조회"""
    try:
        # 큐 길이 조회
        queue_length = await redis_queue.redis_client.llen(redis_queue.task_queue)

        # 활성 워커 수
        active_workers = await worker_monitor.get_active_workers()

        # 완료/실패 작업 수
        completed_count = await redis_queue.redis_client.hlen(redis_queue.completed_queue)
        failed_count = await redis_queue.redis_client.hlen(redis_queue.failed_queue)

        # 시스템 리소스 (psutil 사용)
        import psutil
        memory_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=1)

        # 업타임 계산
        uptime = (datetime.now() - app_start_time).total_seconds()

        return SystemStatusResponse(
            status="healthy",
            queue_length=queue_length,
            active_workers=len(active_workers),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            uptime=uptime,
            memory_usage=memory_percent,
            cpu_usage=cpu_percent
        )

    except Exception as e:
        logger.error(f"시스템 상태 조회 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"시스템 상태를 조회할 수 없습니다: {str(e)}"
        )

@app.get("/health", tags=["Health"])
async def health_check():
    """헬스 체크"""
    try:
        # Redis 연결 확인
        await redis_queue.redis_client.ping()

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "redis": "connected",
                "queue": "operational"
            }
        }

    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"시스템이 정상적으로 동작하지 않습니다: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
```

## Integration Points

### Environment Variables (.env) - Updated

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# Authentication
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRES_HOURS=24

# CORS
CORS_ORIGINS=["http://localhost:3000", "https://your-frontend.com"]

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60  # seconds

# Existing from previous phases...
```

### Project Structure - Updated

```
src/
├── models/
│   ├── base.py              # From Phase 1
│   └── enums.py             # From Phase 1
├── config/
│   └── settings.py          # Updated with API settings
├── utils/
│   ├── logging.py           # From Phase 1
│   └── helpers.py           # From Phase 1
├── exceptions.py            # From Phase 1
├── queue/                   # From Phase 2
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
├── scripts/                 # From Phase 3
│   ├── metadata.py
│   ├── repository.py
│   ├── cache_manager.py
│   └── downloader.py
├── worker/                  # From Phase 4
│   ├── process_manager.py
│   ├── script_executor.py
│   └── worker_main.py
└── api/                     # NEW
    ├── __init__.py
    ├── models.py            # API request/response models
    ├── auth.py              # Authentication middleware
    ├── main.py              # FastAPI application
    └── endpoints/           # Additional endpoints
        ├── __init__.py
        ├── websocket.py     # WebSocket handlers
        └── monitoring.py    # Additional monitoring endpoints
```

## Final Validation Checklist

- [ ] API accepts and validates scraping requests
- [ ] Tasks are queued and results returned synchronously
- [ ] Authentication works with JWT tokens
- [ ] Health checks report system status accurately
- [ ] API documentation is auto-generated: http://localhost:8000/docs
- [ ] All unit tests pass: `uv run pytest tests/test_api.py -v`
- [ ] Integration tests pass: `uv run pytest tests/test_api_integration.py -v`
- [ ] No type errors: `uv run mypy src/api/`
- [ ] No linting errors: `uv run ruff check src/api/`
- [ ] Korean error messages in responses
- [ ] CORS and middleware configured correctly

## Anti-Patterns to Avoid

- ❌ Don't use synchronous database operations in async endpoints
- ❌ Don't skip input validation - validate all request data
- ❌ Don't expose internal errors to clients - use generic error messages
- ❌ Don't ignore authentication - secure all endpoints
- ❌ Don't forget timeout handling - implement proper timeouts
- ❌ Don't skip logging - log all important events
