"""
설정 관리 모듈

환경 변수를 통한 시스템 설정을 관리합니다.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from ..exceptions import ConfigurationException
from ..models.enums import ScriptRepositoryType


class Settings(BaseSettings):
    """시스템 설정 관리 클래스"""
    
    # RabbitMQ 설정
    rabbitmq_url: str = Field(
        default="amqp://localhost:5672/",
        description="RabbitMQ 연결 URL"
    )
    rabbitmq_task_queue: str = Field(
        default="scraping_tasks",
        description="작업 큐 이름"
    )
    rabbitmq_result_timeout: int = Field(
        default=300,
        description="결과 대기 타임아웃 (초)"
    )
    
    # 스크립트 저장소 설정
    script_repository_type: ScriptRepositoryType = Field(
        default=ScriptRepositoryType.GIT,
        description="스크립트 저장소 타입"
    )
    script_repository_url: Optional[str] = Field(
        default="https://github.com/example/scraping-scripts",
        description="스크립트 저장소 URL (Git/HTTP용)"
    )
    script_cache_dir: str = Field(
        default="./cache/scripts",
        description="스크립트 캐시 디렉토리"
    )
    
    # S3 설정 (script_repository_type이 S3일 때 사용)
    s3_bucket_name: Optional[str] = Field(
        default=None,
        description="S3 버킷 이름"
    )
    s3_region: str = Field(
        default="ap-northeast-2",
        description="S3 리전"
    )
    s3_access_key: Optional[str] = Field(
        default=None,
        description="S3 액세스 키"
    )
    s3_secret_key: Optional[str] = Field(
        default=None,
        description="S3 시크릿 키"
    )
    s3_prefix: str = Field(
        default="scripts/",
        description="S3 객체 접두사"
    )
    
    # 워커 설정
    worker_timeout: int = Field(
        default=300,
        description="워커 타임아웃 (초)"
    )
    max_workers: int = Field(
        default=4,
        description="최대 워커 수"
    )
    max_concurrent_tasks: int = Field(
        default=1,
        description="워커당 최대 동시 작업 수"
    )
    worker_heartbeat_interval: int = Field(
        default=30,
        description="워커 하트비트 간격 (초)"
    )
    worker_cleanup_interval: int = Field(
        default=86400,
        description="워커 정리 작업 간격 (초)"
    )
    
    # 프로세스 리소스 제한 설정
    process_memory_limit: str = Field(
        default="512MB",
        description="프로세스별 메모리 제한"
    )
    process_cpu_limit: int = Field(
        default=300,
        description="프로세스별 CPU 시간 제한 (초)"
    )
    process_file_limit: int = Field(
        default=1024,
        description="프로세스별 파일 디스크립터 제한"
    )
    process_timeout: int = Field(
        default=300,
        description="프로세스 실행 타임아웃 (초)"
    )
    
    # 로깅 설정
    log_level: str = Field(
        default="INFO",
        description="로그 레벨"
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="로그 포맷"
    )
    log_file: Optional[str] = Field(
        default=None,
        description="로그 파일 경로"
    )
    
    # API 설정
    api_host: str = Field(
        default="0.0.0.0",
        description="API 서버 호스트"
    )
    api_port: int = Field(
        default=8000,
        description="API 서버 포트"
    )
    api_timeout: int = Field(
        default=30,
        description="API 요청 타임아웃 (초)"
    )
    api_reload: bool = Field(
        default=True,
        description="API 서버 자동 재로드 (개발용)"
    )
    
    # JWT 인증 설정
    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="JWT 서명용 비밀 키"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT 알고리즘"
    )
    jwt_expires_hours: int = Field(
        default=24,
        description="JWT 토큰 만료 시간 (시간)"
    )
    
    # CORS 설정
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS 허용 오리진 목록"
    )
    cors_credentials: bool = Field(
        default=True,
        description="CORS 자격 증명 허용"
    )
    
    # 레이트 리미팅 설정
    rate_limit_requests: int = Field(
        default=100,
        description="레이트 리밋 요청 수"
    )
    rate_limit_window: int = Field(
        default=60,
        description="레이트 리밋 윈도우 (초)"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 환경 변수 이름을 대문자로 변환
        case_sensitive = False
        
    def validate_configuration(self) -> None:
        """설정 유효성 검증"""
        # S3 설정 검증
        if self.script_repository_type == ScriptRepositoryType.S3:
            if not self.s3_bucket_name:
                raise ConfigurationException(
                    "S3_BUCKET_NAME", "S3 저장소 사용 시 필요합니다"
                )
            if not self.s3_access_key or not self.s3_secret_key:
                raise ConfigurationException(
                    "S3_ACCESS_KEY/S3_SECRET_KEY", "S3 저장소 사용 시 필요합니다"
                )
        
        # Git/HTTP 설정 검증
        if self.script_repository_type in [ScriptRepositoryType.GIT, ScriptRepositoryType.HTTP]:
            if not self.script_repository_url:
                raise ConfigurationException(
                    "SCRIPT_REPOSITORY_URL",
                    f"{self.script_repository_type.value} 저장소 사용 시 필요합니다"
                )
        
        # 캐시 디렉토리 생성
        os.makedirs(self.script_cache_dir, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """
    설정 인스턴스를 반환합니다 (싱글톤 패턴)
    
    Returns:
        Settings: 설정 인스턴스
    """
    settings = Settings()
    settings.validate_configuration()
    return settings 