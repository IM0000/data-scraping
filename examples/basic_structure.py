#!/usr/bin/env python3
"""
기본 파일 구조 예제

이 파일은 프로젝트의 기본 코딩 스타일과 구조를 보여줍니다.
모든 새로운 Python 파일은 이 패턴을 따라야 합니다.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 상수 정의
DEFAULT_CONFIG_PATH = Path("config.json")
MAX_RETRY_COUNT = 3


class ExampleService:
    """
    예제 서비스 클래스
    
    이 클래스는 프로젝트의 표준 클래스 구조를 보여줍니다.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        서비스 초기화
        
        Args:
            config_path: 설정 파일 경로 (기본값: DEFAULT_CONFIG_PATH)
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config: Dict[str, Any] = {}
        self._is_initialized = False
        
        logger.info(f"ExampleService 초기화: {self.config_path}")
    
    def initialize(self) -> None:
        """
        서비스 초기화 수행
        
        Raises:
            FileNotFoundError: 설정 파일이 없을 때
            ValueError: 설정이 유효하지 않을 때
        """
        if self._is_initialized:
            logger.warning("서비스가 이미 초기화되었습니다")
            return
        
        try:
            self._load_config()
            self._validate_config()
            self._is_initialized = True
            logger.info("서비스 초기화 완료")
            
        except Exception as e:
            logger.error(f"서비스 초기화 실패: {e}")
            raise
    
    def process_data(self, data: str, options: Optional[Dict[str, Any]] = None) -> str:
        """
        데이터 처리 메서드
        
        Args:
            data: 처리할 데이터
            options: 처리 옵션 (선택사항)
            
        Returns:
            처리된 데이터
            
        Raises:
            ValueError: 데이터가 유효하지 않을 때
            RuntimeError: 서비스가 초기화되지 않았을 때
        """
        if not self._is_initialized:
            raise RuntimeError("서비스가 초기화되지 않았습니다")
        
        if not data or not isinstance(data, str):
            raise ValueError("유효한 문자열 데이터가 필요합니다")
        
        # 기본 옵션 설정
        options = options or {}
        prefix = options.get('prefix', '[처리됨]')
        
        # 데이터 처리 로직
        result = f"{prefix} {data.strip()}"
        
        logger.debug(f"데이터 처리 완료: {len(data)} -> {len(result)} 문자")
        return result
    
    def _load_config(self) -> None:
        """
        설정 파일 로드 (private 메서드)
        
        Reason: 설정 로드 로직을 분리하여 테스트와 유지보수 용이성 향상
        """
        if not self.config_path.exists():
            logger.warning(f"설정 파일이 없습니다: {self.config_path}")
            self.config = {"default": True}
            return
        
        # 실제 구현에서는 JSON 파일을 로드
        self.config = {"loaded": True, "path": str(self.config_path)}
    
    def _validate_config(self) -> None:
        """
        설정 유효성 검증 (private 메서드)
        
        Raises:
            ValueError: 설정이 유효하지 않을 때
        """
        if not isinstance(self.config, dict):
            raise ValueError("설정은 딕셔너리 형태여야 합니다")
        
        # 추가 검증 로직...
        logger.debug("설정 검증 완료")


def create_service(config_path: Optional[str] = None) -> ExampleService:
    """
    서비스 팩토리 함수
    
    Args:
        config_path: 설정 파일 경로
        
    Returns:
        초기화된 ExampleService 인스턴스
    """
    path = Path(config_path) if config_path else None
    service = ExampleService(path)
    service.initialize()
    return service


def main() -> int:
    """
    메인 함수 - 스크립트 실행 시 호출
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    try:
        # 서비스 생성 및 사용 예제
        service = create_service()
        
        # 데이터 처리 예제
        sample_data = "Hello, World!"
        result = service.process_data(sample_data, {"prefix": "[예제]"})
        
        print(f"입력: {sample_data}")
        print(f"출력: {result}")
        
    except Exception as e:
        logger.error(f"실행 중 오류 발생: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main()) 