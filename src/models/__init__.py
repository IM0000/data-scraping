"""
데이터 모델 패키지

스크래핑 시스템의 핵심 데이터 모델들을 정의합니다.
"""

from .base import ScrapingRequest, ScrapingResponse
from .enums import TaskStatus, ScriptRepositoryType

__all__ = [
    "ScrapingRequest",
    "ScrapingResponse", 
    "TaskStatus",
    "ScriptRepositoryType",
] 