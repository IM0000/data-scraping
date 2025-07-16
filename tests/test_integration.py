"""
통합 테스트 모듈

시스템 전체 구성 요소의 통합 테스트를 수행합니다.
"""

import tempfile
from pathlib import Path
import pytest

from src.models.base import ScrapingRequest, ScrapingResponse
from src.models.enums import TaskStatus
from src.config.settings import Settings, get_settings
from src.utils.logging import setup_logging
from src.utils.helpers import generate_task_id, calculate_string_hash
from src.exceptions import ScriptNotFoundException, ConfigurationException


class TestFullModelWorkflow:
    """전체 모델 워크플로우 테스트"""

    def test_request_response_workflow(self):
        """요청-응답 워크플로우 테스트"""
        # 스크래핑 요청 생성
        request = ScrapingRequest(
            script_name="test_scraper",
            parameters={"url": "https://example.com"},
            timeout=600,
            script_version=None
        )
        
        # 요청 데이터 검증
        assert request.script_name == "test_scraper"
        assert request.parameters["url"] == "https://example.com"
        assert request.timeout == 600
        assert request.request_id is not None
        
        # 성공 응답 생성
        response = ScrapingResponse(
            request_id=request.request_id,
            status=TaskStatus.COMPLETED,
            data={"scraped_data": "test_result", "items": ["item1", "item2"]},
            execution_time=10.5,
            error=None,
            completed_at=None
        )
        
        # 응답 데이터 검증
        assert response.request_id == request.request_id
        assert response.status == TaskStatus.COMPLETED
        assert response.data is not None
        assert response.data["scraped_data"] == "test_result"
        assert response.execution_time == 10.5
        assert response.error is None

    def test_error_workflow(self):
        """오류 워크플로우 테스트"""
        # 스크래핑 요청 생성
        request = ScrapingRequest(
            script_name="failing_scraper",
            parameters={"url": "https://invalid.com"},
            script_version=None
        )
        
        # 오류 응답 생성
        response = ScrapingResponse(
            request_id=request.request_id,
            status=TaskStatus.FAILED,
            error="스크립트 실행 중 오류 발생",
            execution_time=5.0,
            data=None,
            completed_at=None
        )
        
        # 응답 데이터 검증
        assert response.request_id == request.request_id
        assert response.status == TaskStatus.FAILED
        assert response.error == "스크립트 실행 중 오류 발생"
        assert response.data is None


class TestConfigurationIntegration:
    """설정 통합 테스트"""

    def test_settings_and_logging_integration(self, monkeypatch):
        """설정과 로깅 시스템 통합 테스트"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        # 환경 변수 설정
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("RABBITMQ_URL", "amqp://test:pass@test.rabbitmq.com:5672/")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            monkeypatch.setenv("SCRIPT_CACHE_DIR", temp_dir)
            monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://github.com/test/repo")
            
            # 설정 로드
            settings = Settings()
            assert settings.log_level == "DEBUG"
            assert settings.rabbitmq_url == "amqp://test:pass@test.rabbitmq.com:5672/"
            
            # 로깅 시스템 초기화
            logger = setup_logging(settings)
            assert logger.name == "scraping_system"
            
            # 로그 메시지 테스트
            logger.info("통합 테스트 로그 메시지")
            logger.debug("디버그 메시지")
            logger.error("오류 메시지")

    def test_settings_validation_integration_s3(self, monkeypatch):
        """설정 유효성 검증 통합 테스트 (S3)"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        # S3 설정 (필수 정보 누락)
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "s3")
        monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
        # S3_ACCESS_KEY 누락
        
        with pytest.raises(ConfigurationException, match="S3 저장소 사용 시 필요합니다"):
            Settings().validate_configuration()

    def test_settings_validation_integration_git(self, monkeypatch):
        """설정 유효성 검증 통합 테스트 (Git)"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        # Git 설정 (필수 정보 누락)
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "git")
        # SCRIPT_REPOSITORY_URL 누락
        
        with pytest.raises(ConfigurationException, match="git 저장소 사용 시 필요합니다"):
            Settings().validate_configuration()


class TestUtilityIntegration:
    """유틸리티 통합 테스트"""

    def test_id_generation_and_hashing(self):
        """ID 생성과 해싱 통합 테스트"""
        # 고유 ID 생성
        task_id = generate_task_id()
        
        # ID를 사용한 해시 계산
        hash_value = calculate_string_hash(task_id)
        
        assert len(task_id) > 10
        assert len(hash_value) == 64
        assert hash_value.isalnum()
        
        # 다른 ID는 다른 해시값 생성
        task_id2 = generate_task_id()
        hash_value2 = calculate_string_hash(task_id2)
        
        assert task_id != task_id2
        assert hash_value != hash_value2

    def test_file_handling_integration(self):
        """파일 처리 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            from src.utils.helpers import ensure_directory, sanitize_filename, calculate_file_hash
            
            # 안전한 디렉토리 생성
            work_dir = ensure_directory(Path(temp_dir) / "scripts")
            
            # 안전한 파일명 생성
            unsafe_filename = "test<script>file.py"
            safe_filename = sanitize_filename(unsafe_filename)
            
            # 파일 생성
            file_path = work_dir / safe_filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# 테스트 스크립트\nprint('Hello, World!')")
            
            # 파일 해시 계산
            file_hash = calculate_file_hash(file_path)
            
            assert file_path.exists()
            assert safe_filename == "test_script_file.py"
            assert len(file_hash) == 64


class TestExceptionHandling:
    """예외 처리 통합 테스트"""

    def test_exception_chain_handling(self):
        """예외 연쇄 처리 테스트"""
        # 스크립트 찾기 실패 시나리오
        try:
            raise ScriptNotFoundException("missing_script", "1.0.0")
        except ScriptNotFoundException as e:
            assert e.script_name == "missing_script"
            assert e.version == "1.0.0"
            assert e.error_code == "SCRIPT_NOT_FOUND"
            
            # 오류 정보를 응답에 포함
            response = ScrapingResponse(
                request_id="test-123",
                status=TaskStatus.FAILED,
                error=str(e),
                data=None,
                completed_at=None
            )
            
            assert response.status == TaskStatus.FAILED
            assert response.error is not None
            assert "missing_script" in response.error
            assert "1.0.0" in response.error

    def test_configuration_exception_handling(self, monkeypatch):
        """설정 예외 처리 테스트"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        # 잘못된 설정
        monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "git")
        # SCRIPT_REPOSITORY_URL 누락
        
        with pytest.raises(ConfigurationException) as exc_info:
            get_settings()
        
        assert "git 저장소 사용 시 필요합니다" in str(exc_info.value)


class TestCompleteSystemWorkflow:
    """완전한 시스템 워크플로우 테스트"""

    def test_end_to_end_success_scenario(self, monkeypatch):
        """종단 간 성공 시나리오 테스트"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 환경 설정
            monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "git")
            monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://github.com/test/repo.git")
            monkeypatch.setenv("SCRIPT_CACHE_DIR", temp_dir)
            monkeypatch.setenv("LOG_LEVEL", "INFO")
            
            # 1. 시스템 초기화
            settings = get_settings()
            logger = setup_logging(settings)
            
            # 2. 스크래핑 요청 생성
            request = ScrapingRequest(
                script_name="example_scraper",
                parameters={
                    "url": "https://example.com",
                    "timeout": 30
                },
                script_version=None
            )
            
            # 3. 로깅
            logger.info(f"스크래핑 요청 수신: {request.script_name}")
            logger.debug(f"요청 매개변수: {request.parameters}")
            
            # 4. 작업 처리 시뮬레이션
            task_id = generate_task_id()
            logger.info(f"작업 ID 생성: {task_id}")
            
            # 5. 성공 응답 생성
            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.COMPLETED,
                data={
                    "title": "Example Title",
                    "content": "Example content",
                    "scraped_at": "2024-01-01T00:00:00Z"
                },
                execution_time=25.5,
                error=None,
                completed_at=None
            )
            
            # 6. 결과 검증
            logger.info(f"스크래핑 완료: {response.request_id}")
            
            # 모든 단계가 성공적으로 완료되었는지 확인
            assert settings.script_repository_url == "https://github.com/test/repo.git"
            assert request.script_name == "example_scraper"
            assert response.status == TaskStatus.COMPLETED
            assert response.data is not None
            assert response.data["title"] == "Example Title"
            assert response.execution_time == 25.5
            assert len(task_id) > 10

    def test_end_to_end_failure_scenario(self, monkeypatch):
        """종단 간 실패 시나리오 테스트"""
        # 캐시 클리어
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 환경 설정
            monkeypatch.setenv("SCRIPT_REPOSITORY_TYPE", "http")
            monkeypatch.setenv("SCRIPT_REPOSITORY_URL", "https://api.example.com/scripts")
            monkeypatch.setenv("SCRIPT_CACHE_DIR", temp_dir)
            
            # 1. 시스템 초기화
            settings = get_settings()
            logger = setup_logging(settings)
            
            # 2. 스크래핑 요청 생성
            request = ScrapingRequest(
                script_name="nonexistent_scraper",
                parameters={"url": "https://example.com"},
                script_version=None
            )
            
            # 3. 스크립트 찾기 실패 시뮬레이션
            logger.error(f"스크립트 찾기 실패: {request.script_name}")
            
            # 4. 오류 응답 생성
            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error="스크립트를 찾을 수 없습니다: nonexistent_scraper",
                execution_time=1.0,
                data=None,
                completed_at=None
            )
            
            # 5. 결과 검증
            logger.error(f"스크래핑 실패: {response.error}")
            
            # 실패 시나리오가 올바르게 처리되었는지 확인
            assert response.status == TaskStatus.FAILED
            assert response.error is not None
            assert "스크립트를 찾을 수 없습니다" in response.error
            assert response.data is None
            assert response.execution_time == 1.0 