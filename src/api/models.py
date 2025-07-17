"""
API 요청/응답 모델 모듈

FastAPI용 Pydantic 모델들을 정의합니다.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from ..models.base import TaskStatus


class ScrapingRequestAPI(BaseModel):
    """API 스크래핑 요청 모델"""
    
    script_name: str = Field(
        ...,
        description="실행할 스크립트 이름",
        min_length=1,
        max_length=100
    )
    script_version: Optional[str] = Field(
        None,
        description="스크립트 버전 (기본값: 최신)",
        max_length=50
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="스크립트 매개변수"
    )
    timeout: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="타임아웃 (초)"
    )

    @field_validator('script_name')
    @classmethod
    def validate_script_name(cls, v: str) -> str:
        """스크립트 이름 유효성 검사"""
        if not v or not v.strip():
            raise ValueError('스크립트 이름은 필수입니다')

        # 허용되는 문자만 포함 (알파벳, 숫자, _, -, .)
        if not re.match(r'^[a-zA-Z0-9_.-]+$', v):
            raise ValueError('스크립트 이름은 알파벳, 숫자, _, -, . 만 포함할 수 있습니다')

        return v.strip()

    @field_validator('parameters')
    @classmethod
    def validate_parameters(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """매개변수 유효성 검사"""
        if not isinstance(v, dict):
            raise ValueError('매개변수는 딕셔너리 형태여야 합니다')

        # 매개변수 키 검증
        for key in v.keys():
            if not isinstance(key, str):
                raise ValueError('매개변수 키는 문자열이어야 합니다')
            if not key.strip():
                raise ValueError('매개변수 키는 빈 문자열일 수 없습니다')

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


class HealthCheckResponse(BaseModel):
    """헬스 체크 응답 모델"""
    
    status: str = Field(..., description="서비스 상태")
    timestamp: datetime = Field(..., description="체크 시간")
    components: Dict[str, str] = Field(..., description="컴포넌트 상태")
    version: str = Field(..., description="API 버전")


class WebSocketMessage(BaseModel):
    """웹소켓 메시지 모델"""
    
    type: str = Field(..., description="메시지 타입")
    request_id: Optional[str] = Field(default=None, description="요청 ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="메시지 데이터")
    timestamp: datetime = Field(default_factory=datetime.now, description="메시지 시간")


class ErrorResponse(BaseModel):
    """오류 응답 모델"""
    
    error: str = Field(..., description="오류 메시지")
    detail: Optional[str] = Field(default=None, description="상세 오류 정보")
    code: Optional[str] = Field(default=None, description="오류 코드")
    timestamp: datetime = Field(default_factory=datetime.now, description="오류 발생 시간")


class AuthTokenRequest(BaseModel):
    """인증 토큰 요청 모델"""
    
    client_id: str = Field(
        ...,
        description="클라이언트 ID",
        min_length=1,
        max_length=50
    )
    client_secret: Optional[str] = Field(
        None,
        description="클라이언트 시크릿",
        max_length=100
    )

    @field_validator('client_id')
    @classmethod
    def validate_client_id(cls, v: str) -> str:
        """클라이언트 ID 유효성 검사"""
        if not v or not v.strip():
            raise ValueError('클라이언트 ID는 필수입니다')
        
        # 허용되는 문자만 포함
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('클라이언트 ID는 알파벳, 숫자, _, - 만 포함할 수 있습니다')
        
        return v.strip()


class AuthTokenResponse(BaseModel):
    """인증 토큰 응답 모델"""
    
    access_token: str = Field(..., description="액세스 토큰")
    token_type: str = Field(default="bearer", description="토큰 타입")
    expires_in: int = Field(..., description="만료 시간 (초)")
    client_id: str = Field(..., description="클라이언트 ID")


class TaskListResponse(BaseModel):
    """작업 목록 응답 모델"""
    
    tasks: List[ScrapingResponseAPI] = Field(..., description="작업 목록")
    total: int = Field(..., description="전체 작업 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")


class WorkerStatusResponse(BaseModel):
    """워커 상태 응답 모델"""
    
    worker_id: str = Field(..., description="워커 ID")
    status: str = Field(..., description="워커 상태")
    current_tasks: int = Field(..., description="현재 작업 수")
    max_tasks: int = Field(..., description="최대 작업 수")
    last_heartbeat: datetime = Field(..., description="마지막 하트비트")
    uptime: float = Field(..., description="워커 업타임 (초)") 