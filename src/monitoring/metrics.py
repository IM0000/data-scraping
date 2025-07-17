"""
Prometheus 메트릭 모듈

시스템 성능 및 상태 메트릭을 수집하고 노출합니다.
"""

import platform
import sys
import time
from functools import wraps
from typing import Any, Dict, Optional

import psutil
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info

from ..utils.logging import get_logger

# 메트릭 레지스트리
REGISTRY = CollectorRegistry()

# 로거
logger = get_logger(__name__)

# 요청 관련 메트릭
REQUEST_COUNT = Counter(
    'scraping_requests_total',
    '총 스크래핑 요청 수',
    ['script_name', 'status', 'client_id'],
    registry=REGISTRY
)

REQUEST_DURATION = Histogram(
    'scraping_request_duration_seconds',
    '스크래핑 요청 처리 시간 (초)',
    ['script_name'],
    registry=REGISTRY
)

# 큐 관련 메트릭
QUEUE_LENGTH = Gauge(
    'scraping_queue_length',
    '현재 스크래핑 큐 길이',
    ['queue_name'],
    registry=REGISTRY
)

QUEUE_PROCESSING_RATE = Gauge(
    'scraping_queue_processing_rate',
    '큐 처리 속도 (req/sec)',
    ['queue_name'],
    registry=REGISTRY
)

# 워커 관련 메트릭
ACTIVE_WORKERS = Gauge(
    'scraping_active_workers',
    '활성 워커 수',
    registry=REGISTRY
)

WORKER_HEARTBEAT = Counter(
    'scraping_worker_heartbeats_total',
    '워커 하트비트 총 수',
    ['worker_id'],
    registry=REGISTRY
)

WORKER_TASKS_PROCESSED = Counter(
    'scraping_worker_tasks_processed_total',
    '워커별 처리된 작업 수',
    ['worker_id', 'status'],
    registry=REGISTRY
)

# 시스템 리소스 메트릭
SYSTEM_MEMORY = Gauge(
    'system_memory_usage_percent',
    '시스템 메모리 사용률 (%)',
    registry=REGISTRY
)

SYSTEM_CPU = Gauge(
    'system_cpu_usage_percent',
    '시스템 CPU 사용률 (%)',
    registry=REGISTRY
)

SYSTEM_DISK_USAGE = Gauge(
    'system_disk_usage_percent',
    '시스템 디스크 사용률 (%)',
    ['mount_point'],
    registry=REGISTRY
)

# RabbitMQ 관련 메트릭
RABBITMQ_CONNECTIONS = Gauge(
    'rabbitmq_connections_active',
    '활성 RabbitMQ 연결 수',
    registry=REGISTRY
)

RABBITMQ_MESSAGES_PUBLISHED = Counter(
    'rabbitmq_messages_published_total',
    '발행된 RabbitMQ 메시지 수',
    ['exchange', 'routing_key'],
    registry=REGISTRY
)

RABBITMQ_MESSAGES_CONSUMED = Counter(
    'rabbitmq_messages_consumed_total',
    '소비된 RabbitMQ 메시지 수',
    ['queue_name'],
    registry=REGISTRY
)

# 오류 관련 메트릭
ERROR_COUNT = Counter(
    'scraping_errors_total',
    '스크래핑 오류 총 수',
    ['error_type', 'component'],
    registry=REGISTRY
)

# 시스템 정보
SYSTEM_INFO = Info(
    'scraping_system_info',
    '스크래핑 시스템 정보',
    registry=REGISTRY
)

# 시스템 정보 설정
SYSTEM_INFO.info({
    'version': '1.0.0',
    'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    'platform': platform.system()
})


def track_request_metrics(script_name: str, client_id: Optional[str] = None):
    """
    요청 메트릭 추적 데코레이터
    
    Args:
        script_name: 스크립트 이름
        client_id: 클라이언트 ID (선택사항)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            client = client_id or 'unknown'

            try:
                result = await func(*args, **kwargs)

                # 성공 메트릭 기록
                REQUEST_COUNT.labels(
                    script_name=script_name,
                    status='success',
                    client_id=client
                ).inc()

                logger.debug(f"성공 메트릭 기록: {script_name} (클라이언트: {client})")
                return result

            except Exception as e:
                # 실패 메트릭 기록
                REQUEST_COUNT.labels(
                    script_name=script_name,
                    status='error',
                    client_id=client
                ).inc()

                # 오류 메트릭 기록
                error_type = type(e).__name__
                ERROR_COUNT.labels(
                    error_type=error_type,
                    component='api'
                ).inc()

                logger.warning(f"실패 메트릭 기록: {script_name} - {error_type}")
                raise

            finally:
                # 실행 시간 기록
                duration = time.time() - start_time
                REQUEST_DURATION.labels(script_name=script_name).observe(duration)

        return wrapper
    return decorator


async def update_system_metrics():
    """시스템 메트릭 업데이트"""
    try:
        # 메모리 사용률
        memory_info = psutil.virtual_memory()
        SYSTEM_MEMORY.set(memory_info.percent)

        # CPU 사용률 (1초 간격으로 측정)
        cpu_percent = psutil.cpu_percent(interval=1)
        SYSTEM_CPU.set(cpu_percent)

        # 디스크 사용률
        try:
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            SYSTEM_DISK_USAGE.labels(mount_point='/').set(disk_percent)
        except Exception as e:
            logger.warning(f"디스크 사용률 측정 실패: {e}")

        logger.debug(f"시스템 메트릭 업데이트: CPU {cpu_percent:.1f}%, 메모리 {memory_info.percent:.1f}%")

    except Exception as e:
        logger.error(f"시스템 메트릭 업데이트 오류: {e}")
        ERROR_COUNT.labels(
            error_type=type(e).__name__,
            component='monitoring'
        ).inc()


def update_queue_metrics(queue_name: str, queue_length: int):
    """
    큐 메트릭 업데이트
    
    Args:
        queue_name: 큐 이름
        queue_length: 큐 길이
    """
    QUEUE_LENGTH.labels(queue_name=queue_name).set(queue_length)
    logger.debug(f"큐 메트릭 업데이트: {queue_name} = {queue_length}")


def update_worker_metrics(worker_count: int):
    """
    워커 메트릭 업데이트
    
    Args:
        worker_count: 활성 워커 수
    """
    ACTIVE_WORKERS.set(worker_count)
    logger.debug(f"워커 메트릭 업데이트: {worker_count}개")


def record_worker_heartbeat(worker_id: str):
    """
    워커 하트비트 기록
    
    Args:
        worker_id: 워커 ID
    """
    WORKER_HEARTBEAT.labels(worker_id=worker_id).inc()
    logger.debug(f"워커 하트비트 기록: {worker_id}")


def record_worker_task(worker_id: str, status: str):
    """
    워커 작업 처리 기록
    
    Args:
        worker_id: 워커 ID  
        status: 작업 상태 (completed, failed, etc.)
    """
    WORKER_TASKS_PROCESSED.labels(worker_id=worker_id, status=status).inc()
    logger.debug(f"워커 작업 기록: {worker_id} - {status}")


def record_rabbitmq_message_published(exchange: str, routing_key: str):
    """
    RabbitMQ 메시지 발행 기록
    
    Args:
        exchange: Exchange 이름
        routing_key: 라우팅 키
    """
    RABBITMQ_MESSAGES_PUBLISHED.labels(
        exchange=exchange,
        routing_key=routing_key
    ).inc()
    logger.debug(f"RabbitMQ 메시지 발행: {exchange}/{routing_key}")


def record_rabbitmq_message_consumed(queue_name: str):
    """
    RabbitMQ 메시지 소비 기록
    
    Args:
        queue_name: 큐 이름
    """
    RABBITMQ_MESSAGES_CONSUMED.labels(queue_name=queue_name).inc()
    logger.debug(f"RabbitMQ 메시지 소비: {queue_name}")


def update_rabbitmq_connections(connection_count: int):
    """
    RabbitMQ 연결 수 업데이트
    
    Args:
        connection_count: 연결 수
    """
    RABBITMQ_CONNECTIONS.set(connection_count)
    logger.debug(f"RabbitMQ 연결 수 업데이트: {connection_count}")


def record_error(error_type: str, component: str):
    """
    오류 발생 기록
    
    Args:
        error_type: 오류 타입
        component: 오류가 발생한 컴포넌트
    """
    ERROR_COUNT.labels(error_type=error_type, component=component).inc()
    logger.warning(f"오류 기록: {component} - {error_type}")


def get_metrics_summary() -> dict[str, Any]:
    """
    메트릭 요약 정보 반환
    
    Returns:
        메트릭 요약 딕셔너리
    """
    try:
        # 현재 시스템 상태
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent()

        return {
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_info.percent,
                "memory_available_gb": memory_info.available / (1024**3)
            },
            "registry_collectors": len(REGISTRY._collector_to_names),
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"메트릭 요약 생성 오류: {e}")
        return {"error": str(e), "timestamp": time.time()}
