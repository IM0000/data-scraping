"""
FastAPI 메인 애플리케이션

Gateway-Worker 스크래핑 시스템의 REST API를 제공합니다.
"""

import asyncio
import psutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from ..config.settings import Settings, get_settings
from ..queue.rabbitmq_rpc import RabbitMQRPC
from ..queue.task_manager import TaskManager
from ..queue.worker_monitor import WorkerMonitor
from ..models.base import ScrapingRequest, TaskStatus
from ..utils.logging import setup_logging
from .models import (
    ScrapingRequestAPI, 
    ScrapingResponseAPI, 
    SystemStatusResponse,
    HealthCheckResponse,
    AuthTokenRequest,
    AuthTokenResponse,
    ErrorResponse
)
from .auth import get_current_client, get_optional_current_client, get_auth_manager, AuthManager
from .endpoints.websocket import websocket_router
from .endpoints.metrics import metrics_router

# 전역 변수
rabbitmq_rpc: Optional[RabbitMQRPC] = None
task_manager: Optional[TaskManager] = None
worker_monitor: Optional[WorkerMonitor] = None
app_start_time = datetime.now()

# 레이트 리미터 설정
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    global rabbitmq_rpc, task_manager, worker_monitor
    
    settings = get_settings()
    logger = setup_logging(settings)

    # 시작 시 초기화
    logger.info("API 서버 시작")

    try:
        # RabbitMQ RPC 연결 (선택적)
        try:
            rabbitmq_rpc = RabbitMQRPC(settings)
            await rabbitmq_rpc.connect()
            await rabbitmq_rpc.setup_callback_queue()
            logger.info("RabbitMQ 연결 성공")
        except Exception as e:
            logger.warning(f"RabbitMQ 연결 실패, 계속 진행합니다: {e}")
            rabbitmq_rpc = None

        # 컴포넌트 초기화 (선택적)
        try:
            task_manager = TaskManager(settings)
            await task_manager.connect()
            logger.info("TaskManager 연결 성공")
        except Exception as e:
            logger.warning(f"TaskManager 연결 실패, 계속 진행합니다: {e}")
            task_manager = None

        try:
            worker_monitor = WorkerMonitor(settings)
            await worker_monitor.connect()
            logger.info("WorkerMonitor 연결 성공")
        except Exception as e:
            logger.warning(f"WorkerMonitor 연결 실패, 계속 진행합니다: {e}")
            worker_monitor = None

        logger.info("API 서버 초기화 완료")

        yield

    except Exception as e:
        logger.error(f"API 서버 초기화 실패: {e}")
        logger.warning("일부 서비스가 사용할 수 없지만 API는 제한적으로 동작합니다")
    finally:
        # 종료 시 정리
        logger.info("API 서버 종료")
        
        if rabbitmq_rpc:
            await rabbitmq_rpc.disconnect()
        if task_manager:
            await task_manager.disconnect()
        if worker_monitor:
            await worker_monitor.disconnect()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """FastAPI 애플리케이션 생성"""
    if settings is None:
        settings = get_settings()

    # FastAPI 앱 생성
    app = FastAPI(
        title="스크래핑 시스템 API",
        description="분산 웹 스크래핑 시스템 REST API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 레이트 리미터 설정
    app.state.limiter = limiter
    
    # 레이트 리밋 예외 핸들러
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc: RateLimitExceeded):
        """레이트 리밋 초과 핸들러"""
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="요청 한도를 초과했습니다",
                detail=f"허용된 요청 수를 초과했습니다: {exc.detail}",
                code="RATE_LIMIT_EXCEEDED"
            ).model_dump()
        )

    # CORS 미들웨어
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip 압축 미들웨어
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # WebSocket 라우터 추가
    app.include_router(websocket_router)
    
    # 메트릭 라우터 추가
    app.include_router(metrics_router)

    return app


# FastAPI 앱 인스턴스
app = create_app()


@app.get("/", tags=["Root"])
async def root():
    """루트 엔드포인트"""
    return {
        "message": "스크래핑 시스템 API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "docs_url": "/docs"
    }


@app.post("/auth/token", response_model=AuthTokenResponse, tags=["Authentication"])
# @limiter.limit("10/minute")  # 임시 비활성화
async def create_access_token(
    request: AuthTokenRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
    settings: Settings = Depends(get_settings)
):
    """
    액세스 토큰 생성

    Args:
        request: 토큰 요청 정보
        auth_manager: 인증 관리자
        settings: 시스템 설정

    Returns:
        JWT 액세스 토큰
    """
    # 클라이언트 자격 증명 검증
    if not auth_manager.validate_client_credentials(request.client_id, request.client_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="클라이언트 자격 증명이 유효하지 않습니다"
        )

    # 토큰 생성
    try:
        access_token = auth_manager.create_access_token(request.client_id)
        expires_in = settings.jwt_expires_hours * 3600  # 초 단위 변환

        return AuthTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            client_id=request.client_id
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"토큰 생성 실패: {str(e)}"
        )


@app.post("/scrape", response_model=ScrapingResponseAPI, tags=["Scraping"])
# @limiter.limit("30/minute")  # 임시 비활성화
async def submit_scraping_request(
    request: ScrapingRequestAPI,
    background_tasks: BackgroundTasks,
    client_id: str = Depends(get_current_client),
    settings: Settings = Depends(get_settings)
):
    """
    스크래핑 요청 제출

    Args:
        request: 스크래핑 요청 데이터
        background_tasks: 백그라운드 작업
        client_id: 클라이언트 ID
        settings: 시스템 설정

    Returns:
        스크래핑 응답
    """
    logger = setup_logging(settings)
    
    try:
        logger.info(f"스크래핑 요청 수신: {request.script_name} (클라이언트: {client_id})")

        # 내부 요청 모델로 변환
        internal_request = ScrapingRequest(
            script_name=request.script_name,
            script_version=request.script_version,
            parameters=request.parameters,
            timeout=request.timeout
        )

        # RabbitMQ RPC를 통한 동기적 처리
        if not rabbitmq_rpc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="스크래핑 서비스가 현재 사용할 수 없습니다. RabbitMQ 연결이 필요합니다."
            )

        # RPC 호출로 동기적 응답 대기
        response = await rabbitmq_rpc.call_async(
            internal_request, 
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

    except TimeoutError:
        logger.error(f"스크래핑 요청 타임아웃: {request.script_name}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"요청이 {request.timeout}초 내에 완료되지 않았습니다"
        )
    except Exception as e:
        logger.error(f"스크래핑 요청 처리 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스크래핑 요청 처리 중 오류가 발생했습니다: {str(e)}"
        )


@app.get("/status", response_model=SystemStatusResponse, tags=["Monitoring"])
async def get_system_status(
    client_id: str = Depends(get_optional_current_client),
    settings: Settings = Depends(get_settings)
):
    """
    시스템 상태 조회
    
    Args:
        client_id: 클라이언트 ID (선택사항)
        settings: 시스템 설정

    Returns:
        시스템 상태 정보
    """
    try:
        # 큐 길이 조회 (task_manager를 통해)
        queue_length = 0
        # TODO: task_manager.get_queue_length() 메서드 구현 필요

        # 활성 워커 수
        active_workers = 0
        # TODO: worker_monitor.get_active_workers() 메서드 구현 필요

        # 완료/실패 작업 수 (task_manager를 통해)
        completed_count = 0
        failed_count = 0
        # TODO: task_manager.get_task_statistics() 메서드 구현 필요

        # 시스템 리소스
        memory_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=1)

        # 업타임 계산
        uptime = (datetime.now() - app_start_time).total_seconds()

        return SystemStatusResponse(
            status="healthy",
            queue_length=queue_length,
            active_workers=active_workers,
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            uptime=uptime,
            memory_usage=memory_percent,
            cpu_usage=cpu_percent
        )

    except Exception as e:
        logger = setup_logging(settings)
        logger.error(f"시스템 상태 조회 오류: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"시스템 상태를 조회할 수 없습니다: {str(e)}"
        )


@app.get("/health", response_model=HealthCheckResponse, tags=["Health"])
async def health_check(settings: Settings = Depends(get_settings)):
    """
    헬스 체크

    Args:
        settings: 시스템 설정

    Returns:
        서비스 상태 정보
    """
    logger = setup_logging(settings)
    
    try:
        components = {}

        # RabbitMQ 연결 확인
        if rabbitmq_rpc and rabbitmq_rpc.connection and not rabbitmq_rpc.connection.is_closed:
            components["rabbitmq"] = "connected"
        else:
            components["rabbitmq"] = "disconnected"

        # Task Manager 확인
        if task_manager:
            components["task_manager"] = "operational"
        else:
            components["task_manager"] = "unavailable"

        # Worker Monitor 확인
        if worker_monitor:
            components["worker_monitor"] = "operational"
        else:
            components["worker_monitor"] = "unavailable"

        # 전체 상태 결정
        overall_status = "healthy" if all(
            status in ["connected", "operational"] 
            for status in components.values()
        ) else "degraded"

        return HealthCheckResponse(
            status=overall_status,
            timestamp=datetime.now(),
            components=components,
            version="1.0.0"
        )

    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"시스템이 정상적으로 동작하지 않습니다: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTP 예외 핸들러"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            code=str(exc.status_code)
        ).model_dump()
    )


@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    """내부 서버 오류 핸들러"""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="내부 서버 오류가 발생했습니다",
            code="INTERNAL_SERVER_ERROR"
        ).model_dump()
    )


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level="info"
    ) 