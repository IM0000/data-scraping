"""
예외 클래스 테스트 모듈

스크래핑 시스템의 커스텀 예외들을 테스트합니다.
"""

import pytest

from src.exceptions import (
    ScrapingSystemException,
    ScriptNotFoundException,
    ScriptExecutionException,
    ScriptValidationException,
    QueueConnectionException,
    WorkerTimeoutException,
    ConfigurationException,
    ScriptRepositoryException
)


class TestScrapingSystemException:
    """기본 예외 클래스 테스트"""

    def test_basic_exception(self):
        """기본 예외 생성 테스트"""
        exc = ScrapingSystemException("테스트 오류")
        
        assert str(exc) == "테스트 오류"
        assert exc.message == "테스트 오류"
        assert exc.error_code is None

    def test_exception_with_error_code(self):
        """오류 코드 포함 예외 테스트"""
        exc = ScrapingSystemException("테스트 오류", "TEST_ERROR")
        
        assert str(exc) == "테스트 오류"
        assert exc.message == "테스트 오류"
        assert exc.error_code == "TEST_ERROR"

    def test_exception_inheritance(self):
        """예외 상속 테스트"""
        exc = ScrapingSystemException("테스트 오류")
        
        assert isinstance(exc, Exception)
        assert isinstance(exc, ScrapingSystemException)


class TestScriptNotFoundException:
    """스크립트 찾기 실패 예외 테스트"""

    def test_script_not_found_without_version(self):
        """버전 없는 스크립트 찾기 실패 테스트"""
        exc = ScriptNotFoundException("test_script")
        
        assert "스크립트를 찾을 수 없습니다: test_script" in str(exc)
        assert exc.script_name == "test_script"
        assert exc.version is None
        assert exc.error_code == "SCRIPT_NOT_FOUND"

    def test_script_not_found_with_version(self):
        """버전 포함 스크립트 찾기 실패 테스트"""
        exc = ScriptNotFoundException("test_script", "1.0.0")
        
        assert "스크립트를 찾을 수 없습니다: test_script (버전: 1.0.0)" in str(exc)
        assert exc.script_name == "test_script"
        assert exc.version == "1.0.0"
        assert exc.error_code == "SCRIPT_NOT_FOUND"

    def test_inheritance(self):
        """상속 관계 테스트"""
        exc = ScriptNotFoundException("test_script")
        
        assert isinstance(exc, ScrapingSystemException)
        assert isinstance(exc, Exception)


class TestScriptExecutionException:
    """스크립트 실행 예외 테스트"""

    def test_script_execution_exception(self):
        """스크립트 실행 예외 테스트"""
        exc = ScriptExecutionException("test_script", "파이썬 문법 오류")
        
        assert "스크립트 실행 실패: test_script - 파이썬 문법 오류" in str(exc)
        assert exc.script_name == "test_script"
        assert exc.error_message == "파이썬 문법 오류"
        assert exc.error_code == "SCRIPT_EXECUTION_ERROR"


class TestScriptValidationException:
    """스크립트 유효성 검증 예외 테스트"""

    def test_script_validation_exception(self):
        """스크립트 유효성 검증 예외 테스트"""
        validation_errors = ["필수 함수 누락", "잘못된 인수 타입"]
        exc = ScriptValidationException("test_script", validation_errors)
        
        assert "스크립트 유효성 검증 실패: test_script - 필수 함수 누락, 잘못된 인수 타입" in str(exc)
        assert exc.script_name == "test_script"
        assert exc.validation_errors == validation_errors
        assert exc.error_code == "SCRIPT_VALIDATION_ERROR"

    def test_single_validation_error(self):
        """단일 유효성 검증 오류 테스트"""
        validation_errors = ["필수 함수 누락"]
        exc = ScriptValidationException("test_script", validation_errors)
        
        assert "스크립트 유효성 검증 실패: test_script - 필수 함수 누락" in str(exc)
        assert exc.validation_errors == validation_errors


class TestQueueConnectionException:
    """큐 연결 예외 테스트"""

    def test_queue_connection_exception(self):
        """큐 연결 예외 테스트"""
        exc = QueueConnectionException("amqp://localhost:5672/")
        
        assert "큐 연결 실패: amqp://localhost:5672/" in str(exc)
        assert exc.connection_info == "amqp://localhost:5672/"
        assert exc.error_code == "QUEUE_CONNECTION_ERROR"


class TestWorkerTimeoutException:
    """워커 타임아웃 예외 테스트"""

    def test_worker_timeout_exception(self):
        """워커 타임아웃 예외 테스트"""
        exc = WorkerTimeoutException("worker-123", 300)
        
        assert "워커 타임아웃: worker-123 (300초)" in str(exc)
        assert exc.worker_id == "worker-123"
        assert exc.timeout_seconds == 300
        assert exc.error_code == "WORKER_TIMEOUT"


class TestConfigurationException:
    """설정 예외 테스트"""

    def test_configuration_exception(self):
        """설정 예외 테스트"""
        exc = ConfigurationException("rabbitmq_url", "잘못된 RabbitMQ URL 형식")
        
        assert "설정 오류: rabbitmq_url - 잘못된 RabbitMQ URL 형식" in str(exc)
        assert exc.config_key == "rabbitmq_url"
        assert exc.error_detail == "잘못된 RabbitMQ URL 형식"
        assert exc.error_code == "CONFIGURATION_ERROR"


class TestScriptRepositoryException:
    """스크립트 저장소 예외 테스트"""

    def test_script_repository_exception(self):
        """스크립트 저장소 예외 테스트"""
        exc = ScriptRepositoryException("s3", "버킷에 접근할 수 없음")
        
        assert "스크립트 저장소 오류 (s3): 버킷에 접근할 수 없음" in str(exc)
        assert exc.repository_type == "s3"
        assert exc.error_detail == "버킷에 접근할 수 없음"
        assert exc.error_code == "SCRIPT_REPOSITORY_ERROR"


class TestExceptionChaining:
    """예외 연쇄 테스트"""

    def test_exception_raising(self):
        """예외 발생 테스트"""
        with pytest.raises(ScriptNotFoundException) as exc_info:
            raise ScriptNotFoundException("missing_script")
        
        assert exc_info.value.script_name == "missing_script"

    def test_exception_catching(self):
        """예외 포착 테스트"""
        try:
            raise ScriptExecutionException("error_script", "런타임 오류")
        except ScrapingSystemException as e:
            assert e.error_code == "SCRIPT_EXECUTION_ERROR"
            assert isinstance(e, ScriptExecutionException)
        except Exception:
            pytest.fail("ScrapingSystemException으로 포착되어야 함")

    def test_multiple_exception_types(self):
        """여러 예외 타입 테스트"""
        exceptions = [
            ScriptNotFoundException("test"),
            ScriptExecutionException("test", "error"),
            QueueConnectionException("amqp://test"),
            WorkerTimeoutException("worker-1", 300),
            ConfigurationException("key", "detail"),
            ScriptRepositoryException("git", "clone failed")
        ]
        
        for exc in exceptions:
            assert isinstance(exc, ScrapingSystemException)
            assert isinstance(exc, Exception)
            assert exc.error_code is not None
            assert exc.message is not None 