"""
기본 데이터 모델 모듈

스크래핑 시스템의 핵심 데이터 구조들을 정의합니다.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .enums import TaskStatus


class ScrapingRequest(BaseModel):
    """스크래핑 요청 데이터 모델"""
    
    script_name: str = Field(
        ...,
        description="실행할 스크립트 이름",
        min_length=1,
        max_length=100
    )
    script_version: Optional[str] = Field(
        None,
        description="스크립트 버전 (지정하지 않으면 최신 버전 사용)",
        max_length=50
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="스크립트 실행 매개변수"
    )
    timeout: int = Field(
        default=300,
        description="실행 타임아웃 (초)",
        ge=1,
        le=3600
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="요청 고유 식별자"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="요청 생성 시간"
    )


class ScrapingResponse(BaseModel):
    """스크래핑 응답 데이터 모델"""
    
    request_id: str = Field(
        ...,
        description="요청 고유 식별자"
    )
    status: TaskStatus = Field(
        ...,
        description="작업 상태"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="스크래핑 결과 데이터"
    )
    error: Optional[str] = Field(
        default=None,
        description="오류 메시지"
    )
    execution_time: float = Field(
        default=0.0,
        description="실행 시간 (초)",
        ge=0
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="완료 시간"
    )


class ScriptInfo(BaseModel):
    """스크립트 정보 데이터 모델"""
    
    name: str = Field(
        ...,
        description="스크립트 이름",
        min_length=1,
        max_length=100
    )
    version: str = Field(
        ...,
        description="스크립트 버전",
        max_length=50
    )
    file_path: str = Field(
        ...,
        description="스크립트 파일 경로"
    )
    file_hash: str = Field(
        ...,
        description="파일 해시값 (SHA-256)"
    )
    modified_at: datetime = Field(
        ...,
        description="수정 시간"
    )
    cached_at: Optional[datetime] = Field(
        None,
        description="캐시 시간"
    )


class WorkerInfo(BaseModel):
    """워커 정보 데이터 모델"""
    
    worker_id: str = Field(
        ...,
        description="워커 고유 식별자"
    )
    status: str = Field(
        ...,
        description="워커 상태"
    )
    current_tasks: int = Field(
        default=0,
        description="현재 처리 중인 작업 수",
        ge=0
    )
    max_tasks: int = Field(
        default=1,
        description="최대 처리 가능한 작업 수",
        ge=1
    )
    last_heartbeat: datetime = Field(
        default_factory=datetime.now,
        description="마지막 하트비트 시간"
    ) 