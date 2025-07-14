"""
예외 클래스 정의 모듈

스크래핑 시스템에서 사용되는 커스텀 예외들을 정의합니다.
"""

from typing import Optional


class ScrapingSystemException(Exception):
    """스크래핑 시스템 기본 예외 클래스"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        """
        예외 초기화
        
        Args:
            message: 오류 메시지
            error_code: 오류 코드 (선택사항)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ScriptNotFoundException(ScrapingSystemException):
    """스크립트를 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(self, script_name: str, version: Optional[str] = None):
        """
        스크립트 찾기 실패 예외 초기화
        
        Args:
            script_name: 스크립트 이름
            version: 스크립트 버전
        """
        version_info = f" (버전: {version})" if version else ""
        message = f"스크립트를 찾을 수 없습니다: {script_name}{version_info}"
        super().__init__(message, "SCRIPT_NOT_FOUND")
        self.script_name = script_name
        self.version = version


class ScriptExecutionException(ScrapingSystemException):
    """스크립트 실행 중 발생하는 예외"""
    
    def __init__(self, script_name: str, error_message: str):
        """
        스크립트 실행 예외 초기화
        
        Args:
            script_name: 스크립트 이름
            error_message: 오류 메시지
        """
        message = f"스크립트 실행 실패: {script_name} - {error_message}"
        super().__init__(message, "SCRIPT_EXECUTION_ERROR")
        self.script_name = script_name
        self.error_message = error_message


class ScriptValidationException(ScrapingSystemException):
    """스크립트 유효성 검증 실패 시 발생하는 예외"""
    
    def __init__(self, script_name: str, validation_errors: list):
        """
        스크립트 검증 예외 초기화
        
        Args:
            script_name: 스크립트 이름
            validation_errors: 검증 오류 목록
        """
        error_list = ", ".join(validation_errors)
        message = f"스크립트 유효성 검증 실패: {script_name} - {error_list}"
        super().__init__(message, "SCRIPT_VALIDATION_ERROR")
        self.script_name = script_name
        self.validation_errors = validation_errors


class QueueConnectionException(ScrapingSystemException):
    """큐 연결 오류 시 발생하는 예외"""
    
    def __init__(self, connection_info: str):
        """
        큐 연결 예외 초기화
        
        Args:
            connection_info: 연결 정보
        """
        message = f"큐 연결 실패: {connection_info}"
        super().__init__(message, "QUEUE_CONNECTION_ERROR")
        self.connection_info = connection_info


class WorkerTimeoutException(ScrapingSystemException):
    """워커 타임아웃 시 발생하는 예외"""
    
    def __init__(self, worker_id: str, timeout_seconds: int):
        """
        워커 타임아웃 예외 초기화
        
        Args:
            worker_id: 워커 ID
            timeout_seconds: 타임아웃 시간(초)
        """
        message = f"워커 타임아웃: {worker_id} ({timeout_seconds}초)"
        super().__init__(message, "WORKER_TIMEOUT")
        self.worker_id = worker_id
        self.timeout_seconds = timeout_seconds


class ConfigurationException(ScrapingSystemException):
    """설정 오류 시 발생하는 예외"""
    
    def __init__(self, config_key: str, error_detail: str):
        """
        설정 예외 초기화
        
        Args:
            config_key: 설정 키
            error_detail: 오류 상세 정보
        """
        message = f"설정 오류: {config_key} - {error_detail}"
        super().__init__(message, "CONFIGURATION_ERROR")
        self.config_key = config_key
        self.error_detail = error_detail


class ScriptRepositoryException(ScrapingSystemException):
    """스크립트 저장소 관련 예외"""
    
    def __init__(self, repository_type: str, error_detail: str):
        """
        스크립트 저장소 예외 초기화
        
        Args:
            repository_type: 저장소 타입
            error_detail: 오류 상세 정보
        """
        message = f"스크립트 저장소 오류 ({repository_type}): {error_detail}"
        super().__init__(message, "SCRIPT_REPOSITORY_ERROR")
        self.repository_type = repository_type
        self.error_detail = error_detail 