"""
로깅 시스템 모듈

한국어 로깅을 지원하는 통합 로깅 시스템을 제공합니다.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from ..config.settings import Settings


class KoreanFormatter(logging.Formatter):
    """한국어 로그 메시지를 위한 커스텀 포맷터"""
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        """
        포맷터 초기화
        
        Args:
            fmt: 로그 메시지 형식
            datefmt: 날짜 형식
        """
        super().__init__(fmt, datefmt)
    
    def format(self, record: logging.LogRecord) -> str:
        """
        로그 레코드를 한국어 형식으로 포맷팅
        
        Args:
            record: 로그 레코드
            
        Returns:
            str: 포맷된 로그 메시지
        """
        # 로그 레벨을 한국어로 변환
        level_mapping = {
            'DEBUG': '디버그',
            'INFO': '정보',
            'WARNING': '경고',
            'ERROR': '오류',
            'CRITICAL': '치명적'
        }
        
        original_levelname = record.levelname
        record.levelname = level_mapping.get(original_levelname, original_levelname)
        
        # 기본 포맷팅 수행
        formatted = super().format(record)
        
        # 원래 레벨명 복원
        record.levelname = original_levelname
        
        return formatted


def setup_logging(settings: Settings) -> logging.Logger:
    """
    한국어 로깅 시스템 설정
    
    Args:
        settings: 시스템 설정 객체
        
    Returns:
        logging.Logger: 설정된 로거 객체
    """
    logger = logging.getLogger("scraping_system")
    logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # 기존 핸들러 제거 (중복 방지)
    logger.handlers.clear()
    
    # 한국어 포맷터 생성
    formatter = KoreanFormatter(
        fmt=settings.log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러 설정 (로그 파일 지정된 경우)
    if settings.log_file:
        log_file_path = Path(settings.log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 로테이팅 파일 핸들러 (10MB, 5개 백업)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 프로파게이션 비활성화 (중복 출력 방지)
    logger.propagate = False
    
    logger.info("로깅 시스템이 초기화되었습니다")
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    특정 이름의 로거를 반환합니다
    
    Args:
        name: 로거 이름
        
    Returns:
        logging.Logger: 로거 객체
    """
    return logging.getLogger(f"scraping_system.{name}")


class LoggerMixin:
    """로깅 기능을 제공하는 믹스인 클래스"""
    
    @property
    def logger(self) -> logging.Logger:
        """
        클래스별 로거 반환
        
        Returns:
            logging.Logger: 클래스별 로거
        """
        return get_logger(self.__class__.__name__)
    
    def log_info(self, message: str, *args, **kwargs) -> None:
        """정보 로그 출력"""
        self.logger.info(message, *args, **kwargs)
    
    def log_error(self, message: str, *args, **kwargs) -> None:
        """오류 로그 출력"""
        self.logger.error(message, *args, **kwargs)
    
    def log_warning(self, message: str, *args, **kwargs) -> None:
        """경고 로그 출력"""
        self.logger.warning(message, *args, **kwargs)
    
    def log_debug(self, message: str, *args, **kwargs) -> None:
        """디버그 로그 출력"""
        self.logger.debug(message, *args, **kwargs) 