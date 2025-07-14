"""
공통 유틸리티 함수 모듈

스크래핑 시스템에서 공통으로 사용되는 헬퍼 함수들을 제공합니다.
"""

import asyncio
import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from ..utils.logging import get_logger

logger = get_logger(__name__)


def generate_task_id() -> str:
    """
    고유한 작업 ID 생성
    
    Returns:
        str: 고유한 작업 ID
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = str(uuid.uuid4())[:8]
    return f"task_{timestamp}_{random_str}"


def generate_worker_id() -> str:
    """
    고유한 워커 ID 생성
    
    Returns:
        str: 고유한 워커 ID
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = str(uuid.uuid4())[:8]
    return f"worker_{timestamp}_{random_str}"


def calculate_file_hash(file_path: Union[str, Path]) -> str:
    """
    파일의 SHA-256 해시 계산
    
    Args:
        file_path: 파일 경로
        
    Returns:
        str: SHA-256 해시값
        
    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때
        PermissionError: 파일 읽기 권한이 없을 때
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
    
    if not file_path.is_file():
        raise ValueError(f"디렉토리입니다: {file_path}")
    
    hasher = hashlib.sha256()
    
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
    except PermissionError:
        raise PermissionError(f"파일 읽기 권한이 없습니다: {file_path}")
    
    return hasher.hexdigest()


def calculate_string_hash(content: str) -> str:
    """
    문자열의 SHA-256 해시 계산
    
    Args:
        content: 해시를 계산할 문자열
        
    Returns:
        str: SHA-256 해시값
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    지수 백오프를 사용한 재시도 함수
    
    Args:
        func: 재시도할 함수
        max_retries: 최대 재시도 횟수
        initial_delay: 초기 지연 시간 (초)
        backoff_factor: 백오프 배수
        max_delay: 최대 지연 시간 (초)
        exceptions: 재시도할 예외 타입들
        
    Returns:
        Any: 함수 실행 결과
        
    Raises:
        Exception: 모든 재시도 실패 시 마지막 예외
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func()
            else:
                return func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"재시도 {max_retries}회 모두 실패: {e}")
                raise
            
            # 지수 백오프 계산
            delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
            logger.warning(f"재시도 {attempt + 1}/{max_retries} 실패, {delay:.1f}초 후 재시도: {e}")
            await asyncio.sleep(delay)
    
    # 이 코드는 도달하지 않지만 타입 체커를 위해 추가
    if last_exception:
        raise last_exception
    else:
        raise Exception("알 수 없는 오류")


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    파일명을 안전하게 정리
    
    Args:
        filename: 원본 파일명
        max_length: 최대 길이
        
    Returns:
        str: 정리된 파일명
    """
    # 위험한 문자 제거
    dangerous_chars = '<>:"/\\|?*'
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # 공백 및 특수 문자 정리
    filename = filename.strip()
    filename = filename.replace(' ', '_')
    
    # 길이 제한
    if len(filename) > max_length:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        if ext:
            max_name_length = max_length - len(ext) - 1
            filename = f"{name[:max_name_length]}.{ext}"
        else:
            filename = filename[:max_length]
    
    return filename


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    디렉토리 존재 확인 및 생성
    
    Args:
        path: 디렉토리 경로
        
    Returns:
        Path: 디렉토리 경로 객체
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_file_size(size_bytes: int) -> str:
    """
    파일 크기를 사람이 읽기 쉬운 형태로 변환
    
    Args:
        size_bytes: 바이트 단위 크기
        
    Returns:
        str: 형식화된 크기 문자열
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size_value = float(size_bytes)
    
    while size_value >= 1024 and i < len(size_names) - 1:
        size_value = size_value / 1024
        i += 1
    
    return f"{size_value:.1f} {size_names[i]}"


def format_duration(seconds: float) -> str:
    """
    지속 시간을 사람이 읽기 쉬운 형태로 변환
    
    Args:
        seconds: 초 단위 시간
        
    Returns:
        str: 형식화된 시간 문자열
    """
    if seconds < 60:
        return f"{seconds:.1f}초"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{int(minutes)}분 {seconds:.1f}초"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{int(hours)}시간 {int(minutes)}분 {seconds:.1f}초"


def validate_url(url: str) -> bool:
    """
    URL 유효성 검증
    
    Args:
        url: 검증할 URL
        
    Returns:
        bool: 유효한 URL인지 여부
    """
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    문자열을 지정된 길이로 자르기
    
    Args:
        text: 자를 문자열
        max_length: 최대 길이
        suffix: 자른 부분에 추가할 접미사
        
    Returns:
        str: 자른 문자열
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix 