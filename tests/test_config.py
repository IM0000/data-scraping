"""
설정 관리 테스트 모듈

시스템 설정 관리 기능을 테스트합니다.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.config.settings import Settings, get_settings
from src.models.enums import ScriptRepositoryType
from src.exceptions import ConfigurationException


class TestSettings:
    """설정 클래스 테스트"""

    def test_default_settings(self):
        """기본 설정 테스트"""
        settings = Settings()
        
        assert settings.rabbitmq_url == "amqp://localhost:5672/"
        assert settings.rabbitmq_task_queue == "scraping_tasks"
        assert settings.rabbitmq_result_timeout == 300
        
        assert settings.script_repository_type == ScriptRepositoryType.GIT
        assert settings.script_repository_url is None
        assert settings.script_cache_dir == "./cache/scripts"
        
        assert settings.worker_timeout == 300
        assert settings.max_workers == 4
        assert settings.max_concurrent_tasks == 1

    def test_settings_from_env(self, monkeypatch):
        """환경 변수로부터 설정 로드 테스트"""
        # 환경 변수 설정
        monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@rabbitmq.example.com:5672/")
        monkeypatch.setenv("RABBITMQ_TASK_QUEUE", "custom_tasks")
        monkeypatch.setenv("RABBITMQ_RESULT_TIMEOUT", "600")
        
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://api.example.com/scripts")
        monkeypatch.setenv("SCRIPT_CACHE_DIR", "/tmp/cache/scripts")
        
        monkeypatch.setenv("S3_BUCKET_NAME", "my-scripts-bucket")
        monkeypatch.setenv("S3_REGION", "us-west-2")
        monkeypatch.setenv("S3_ACCESS_KEY", "access123")
        monkeypatch.setenv("S3_SECRET_KEY", "secret456")
        monkeypatch.setenv("S3_PREFIX", "custom/scripts/")
        
        monkeypatch.setenv("WORKER_TIMEOUT", "600")
        monkeypatch.setenv("MAX_WORKERS", "8")
        monkeypatch.setenv("MAX_CONCURRENT_TASKS", "2")
        
        settings = Settings()
        
        # RabbitMQ 설정 확인
        assert settings.rabbitmq_url == "amqp://user:pass@rabbitmq.example.com:5672/"
        assert settings.rabbitmq_task_queue == "custom_tasks"
        assert settings.rabbitmq_result_timeout == 600
        
        # 스크립트 저장소 설정 확인
        assert settings.script_repository_type == ScriptRepositoryType.S3
        assert settings.script_repository_url == "https://api.example.com/scripts"
        assert settings.script_cache_dir == "/tmp/cache/scripts"
        
        # S3 설정 확인
        assert settings.s3_bucket_name == "my-scripts-bucket"
        assert settings.s3_region == "us-west-2"
        assert settings.s3_access_key == "access123"
        assert settings.s3_secret_key == "secret456"
        assert settings.s3_prefix == "custom/scripts/"
        
        # 워커 설정 확인
        assert settings.worker_timeout == 600
        assert settings.max_workers == 8
        assert settings.max_concurrent_tasks == 2

    def test_s3_validation_success(self, monkeypatch):
        """S3 설정 유효성 검증 성공 테스트"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        monkeypatch.setenv("S3_BUCKET_NAME", "my-bucket")
        monkeypatch.setenv("S3_ACCESS_KEY", "access123")
        monkeypatch.setenv("S3_SECRET_KEY", "secret456")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            monkeypatch.setenv("SCRIPT_CACHE_DIR", tmp_dir)
            
            settings = Settings()
            settings.validate_configuration()  # 예외 발생하지 않아야 함

    def test_s3_validation_missing_bucket(self, monkeypatch):
        """S3 설정 유효성 검증 실패 테스트 - 버킷명 누락"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        monkeypatch.setenv("S3_ACCESS_KEY", "access123")
        monkeypatch.setenv("S3_SECRET_KEY", "secret456")
        
        settings = Settings()
        with pytest.raises(ConfigurationException, match="S3_BUCKET_NAME"):
            settings.validate_configuration()

    def test_s3_validation_missing_credentials(self, monkeypatch):
        """S3 설정 유효성 검증 실패 테스트 - 자격증명 누락"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        monkeypatch.setenv("S3_BUCKET_NAME", "my-bucket")
        
        settings = Settings()
        with pytest.raises(ConfigurationException, match="S3_ACCESS_KEY"):
            settings.validate_configuration()

    def test_git_validation_success(self, monkeypatch):
        """Git 설정 유효성 검증 성공 테스트"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "git")
        monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://github.com/user/repo.git")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            monkeypatch.setenv("SCRIPT_CACHE_DIR", tmp_dir)
            
            settings = Settings()
            settings.validate_configuration()  # 예외 발생하지 않아야 함

    def test_git_validation_missing_url(self, monkeypatch):
        """Git 설정 유효성 검증 실패 테스트 - URL 누락"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "git")
        
        settings = Settings()
        with pytest.raises(ConfigurationException, match="SCRIPT_REPOSITORY_URL"):
            settings.validate_configuration()

    def test_http_validation_success(self, monkeypatch):
        """HTTP 설정 유효성 검증 성공 테스트"""
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "http")
        monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://api.example.com/scripts")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            monkeypatch.setenv("SCRIPT_CACHE_DIR", tmp_dir)
            
            settings = Settings()
            settings.validate_configuration()  # 예외 발생하지 않아야 함

    def test_cache_directory_creation(self, monkeypatch):
        """캐시 디렉토리 생성 테스트"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "new_cache_dir"
            monkeypatch.setenv("SCRIPT_CACHE_DIR", str(cache_dir))
            monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://github.com/test/repo.git")
            
            settings = Settings()
            settings.validate_configuration()
            
            assert cache_dir.exists()
            assert cache_dir.is_dir()


class TestGetSettings:
    """설정 팩토리 함수 테스트"""

    def test_get_settings_singleton(self, monkeypatch):
        """설정 싱글톤 패턴 테스트"""
        # 캐시 클리어
        get_settings.cache_clear()
        
        # 필요한 환경 변수 설정
        monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://github.com/test/repo.git")
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2

    def test_get_settings_validation(self, monkeypatch):
        """설정 팩토리 유효성 검증 테스트"""
        # 캐시 클리어
        get_settings.cache_clear()
        
        # 유효하지 않은 설정
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        # S3 필수 설정 누락
        
        with pytest.raises(ConfigurationException):
            get_settings() 