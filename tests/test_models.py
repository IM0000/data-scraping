"""
모델 테스트 모듈

스크래핑 시스템의 핵심 데이터 모델들을 테스트합니다.
"""

import pytest
from datetime import datetime
from uuid import UUID

from src.models.base import ScrapingRequest, ScrapingResponse, ScriptInfo, WorkerInfo
from src.models.enums import TaskStatus, ScriptRepositoryType


class TestScrapingRequest:
    """스크래핑 요청 모델 테스트"""

    def test_request_creation(self):
        """요청 생성 테스트"""
        request = ScrapingRequest(
            script_name="example_scraper",
            parameters={"url": "https://example.com"},
            script_version=None
        )
        
        assert request.script_name == "example_scraper"
        assert request.parameters["url"] == "https://example.com"
        assert request.timeout == 300  # 기본값
        assert request.script_version is None  # 기본값
        assert request.request_id is not None
        assert isinstance(request.created_at, datetime)
        
        # UUID 형식 확인
        UUID(request.request_id)  # 유효한 UUID면 예외 발생하지 않음

    def test_request_with_version(self):
        """버전 지정 요청 테스트"""
        request = ScrapingRequest(
            script_name="example_scraper",
            script_version="1.0.0"
        )
        assert request.script_version == "1.0.0"

    def test_request_with_custom_timeout(self):
        """커스텀 타임아웃 요청 테스트"""
        request = ScrapingRequest(
            script_name="example_scraper",
            timeout=600,
            script_version=None
        )
        assert request.timeout == 600

    def test_request_validation(self):
        """요청 유효성 검증 테스트"""
        # 빈 스크립트 이름
        with pytest.raises(ValueError):
            ScrapingRequest(script_name="", script_version=None)
        
        # 너무 긴 스크립트 이름
        with pytest.raises(ValueError):
            ScrapingRequest(script_name="a" * 101, script_version=None)
        
        # 잘못된 타임아웃 값
        with pytest.raises(ValueError):
            ScrapingRequest(script_name="test", timeout=0, script_version=None)
        
        with pytest.raises(ValueError):
            ScrapingRequest(script_name="test", timeout=3601, script_version=None)


class TestScrapingResponse:
    """스크래핑 응답 모델 테스트"""

    def test_successful_response(self):
        """성공 응답 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"},
            error=None,
            completed_at=None
        )
        
        assert response.request_id == "test-123"
        assert response.status == TaskStatus.COMPLETED
        assert response.data is not None
        assert response.data["result"] == "success"
        assert response.error is None
        assert response.execution_time == 0.0

    def test_error_response(self):
        """오류 응답 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.FAILED,
            error="스크립트 실행 실패",
            data=None,
            completed_at=None
        )
        
        assert response.status == TaskStatus.FAILED
        assert response.error == "스크립트 실행 실패"
        assert response.data is None

    def test_response_with_execution_time(self):
        """실행 시간 포함 응답 테스트"""
        response = ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data=None,
            error=None,
            execution_time=15.5,
            completed_at=None
        )
        assert response.execution_time == 15.5

    def test_response_validation(self):
        """응답 유효성 검증 테스트"""
        # 음수 실행 시간
        with pytest.raises(ValueError):
            ScrapingResponse(
                request_id="test-123",
                status=TaskStatus.COMPLETED,
                data=None,
                error=None,
                execution_time=-1.0,
                completed_at=None
            )


class TestScriptInfo:
    """스크립트 정보 모델 테스트"""

    def test_script_info_creation(self):
        """스크립트 정보 생성 테스트"""
        now = datetime.now()
        script_info = ScriptInfo(
            name="test_script",
            version="1.0.0",
            file_path="/path/to/script.py",
            file_hash="abc123",
            modified_at=now,
            cached_at=None
        )
        
        assert script_info.name == "test_script"
        assert script_info.version == "1.0.0"
        assert script_info.file_path == "/path/to/script.py"
        assert script_info.file_hash == "abc123"
        assert script_info.modified_at == now
        assert script_info.cached_at is None

    def test_script_info_with_cache(self):
        """캐시 시간 포함 스크립트 정보 테스트"""
        now = datetime.now()
        script_info = ScriptInfo(
            name="test_script",
            version="1.0.0",
            file_path="/path/to/script.py",
            file_hash="abc123",
            modified_at=now,
            cached_at=now
        )
        assert script_info.cached_at == now


class TestWorkerInfo:
    """워커 정보 모델 테스트"""

    def test_worker_info_creation(self):
        """워커 정보 생성 테스트"""
        worker_info = WorkerInfo(
            worker_id="worker-123",
            status="active"
        )
        
        assert worker_info.worker_id == "worker-123"
        assert worker_info.status == "active"
        assert worker_info.current_tasks == 0
        assert worker_info.max_tasks == 1
        assert isinstance(worker_info.last_heartbeat, datetime)

    def test_worker_info_with_tasks(self):
        """작업 정보 포함 워커 정보 테스트"""
        worker_info = WorkerInfo(
            worker_id="worker-123",
            status="active",
            current_tasks=2,
            max_tasks=4
        )
        
        assert worker_info.current_tasks == 2
        assert worker_info.max_tasks == 4

    def test_worker_info_validation(self):
        """워커 정보 유효성 검증 테스트"""
        # 음수 작업 수
        with pytest.raises(ValueError):
            WorkerInfo(
                worker_id="worker-123",
                status="active",
                current_tasks=-1
            )
        
        # 잘못된 최대 작업 수
        with pytest.raises(ValueError):
            WorkerInfo(
                worker_id="worker-123",
                status="active",
                max_tasks=0
            )


class TestEnums:
    """열거형 테스트"""

    def test_task_status_enum(self):
        """작업 상태 열거형 테스트"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.TIMEOUT.value == "timeout"

    def test_script_repository_type_enum(self):
        """스크립트 저장소 타입 열거형 테스트"""
        assert ScriptRepositoryType.GIT.value == "git"
        assert ScriptRepositoryType.HTTP.value == "http"
        assert ScriptRepositoryType.S3.value == "s3" 