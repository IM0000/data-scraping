"""
메트릭 엔드포인트 모듈

Prometheus 메트릭을 HTTP 엔드포인트로 노출합니다.
"""

import asyncio
from typing import Dict, Any

from fastapi import APIRouter, Response, BackgroundTasks, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ...config.settings import Settings, get_settings
from ...monitoring.metrics import (
    REGISTRY,
    update_system_metrics,
    get_metrics_summary
)
from ...utils.logging import setup_logging

# 메트릭 라우터
metrics_router = APIRouter()


@metrics_router.get("/metrics", tags=["Monitoring"])
async def get_prometheus_metrics(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings)
):
    """
    Prometheus 메트릭 노출
    
    Args:
        background_tasks: 백그라운드 작업
        settings: 시스템 설정

    Returns:
        Prometheus 형식의 메트릭
    """
    logger = setup_logging(settings)
    
    try:
        # 백그라운드에서 시스템 메트릭 업데이트
        background_tasks.add_task(update_system_metrics)
        
        # Prometheus 메트릭 생성
        metrics_data = generate_latest(REGISTRY)
        
        logger.debug("Prometheus 메트릭 생성 완료")
        
        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )
        
    except Exception as e:
        logger.error(f"메트릭 생성 오류: {e}")
        return Response(
            content=f"# 메트릭 생성 오류: {e}\n",
            media_type=CONTENT_TYPE_LATEST,
            status_code=500
        )


@metrics_router.get("/metrics/summary", tags=["Monitoring"])
async def get_metrics_summary_endpoint(
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """
    메트릭 요약 정보
    
    Args:
        settings: 시스템 설정

    Returns:
        메트릭 요약 딕셔너리
    """
    logger = setup_logging(settings)
    
    try:
        summary = get_metrics_summary()
        logger.debug("메트릭 요약 생성 완료")
        return summary
        
    except Exception as e:
        logger.error(f"메트릭 요약 생성 오류: {e}")
        return {"error": str(e)}


@metrics_router.post("/metrics/update", tags=["Monitoring"])
async def force_metrics_update(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings)
) -> Dict[str, str]:
    """
    메트릭 강제 업데이트
    
    Args:
        background_tasks: 백그라운드 작업
        settings: 시스템 설정

    Returns:
        업데이트 상태
    """
    logger = setup_logging(settings)
    
    try:
        # 백그라운드에서 메트릭 업데이트
        background_tasks.add_task(update_system_metrics)
        
        logger.info("메트릭 강제 업데이트 요청됨")
        
        return {
            "status": "success",
            "message": "메트릭 업데이트가 백그라운드에서 실행됩니다"
        }
        
    except Exception as e:
        logger.error(f"메트릭 업데이트 요청 오류: {e}")
        return {
            "status": "error",
            "message": str(e)
        } 