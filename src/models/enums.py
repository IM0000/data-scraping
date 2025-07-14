"""
열거형 정의 모듈

스크래핑 시스템에서 사용되는 상수 값들을 열거형으로 정의합니다.
"""

from enum import Enum


class TaskStatus(Enum):
    """작업 상태 열거형"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ScriptRepositoryType(Enum):
    """스크립트 저장소 타입 열거형"""
    GIT = "git"
    HTTP = "http"
    S3 = "s3" 