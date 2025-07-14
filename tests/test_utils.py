"""
유틸리티 함수 테스트 모듈

공통 유틸리티 함수들을 테스트합니다.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from src.utils.helpers import (
    generate_task_id,
    generate_worker_id,
    calculate_file_hash,
    calculate_string_hash,
    retry_with_backoff,
    sanitize_filename,
    ensure_directory,
    format_file_size,
    format_duration,
    validate_url,
    truncate_string
)


class TestIdGeneration:
    """ID 생성 함수 테스트"""

    def test_generate_task_id(self):
        """작업 ID 생성 테스트"""
        task_id = generate_task_id()
        
        assert task_id.startswith("task_")
        assert len(task_id) > 10
        
        # 두 번 호출 시 다른 ID 생성
        task_id2 = generate_task_id()
        assert task_id != task_id2

    def test_generate_worker_id(self):
        """워커 ID 생성 테스트"""
        worker_id = generate_worker_id()
        
        assert worker_id.startswith("worker_")
        assert len(worker_id) > 10
        
        # 두 번 호출 시 다른 ID 생성
        worker_id2 = generate_worker_id()
        assert worker_id != worker_id2


class TestHashCalculation:
    """해시 계산 함수 테스트"""

    def test_calculate_string_hash(self):
        """문자열 해시 계산 테스트"""
        content = "Hello, World!"
        hash_value = calculate_string_hash(content)
        
        assert len(hash_value) == 64  # SHA-256 해시 길이
        assert hash_value.isalnum()  # 영숫자만 포함
        
        # 같은 내용은 같은 해시값 생성
        hash_value2 = calculate_string_hash(content)
        assert hash_value == hash_value2
        
        # 다른 내용은 다른 해시값 생성
        different_content = "Hello, Python!"
        different_hash = calculate_string_hash(different_content)
        assert hash_value != different_hash

    def test_calculate_file_hash(self):
        """파일 해시 계산 테스트"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("테스트 파일 내용")
            temp_file = Path(f.name)
        
        try:
            hash_value = calculate_file_hash(temp_file)
            
            assert len(hash_value) == 64
            assert hash_value.isalnum()
            
            # 같은 파일은 같은 해시값 생성
            hash_value2 = calculate_file_hash(temp_file)
            assert hash_value == hash_value2
            
        finally:
            temp_file.unlink()

    def test_calculate_file_hash_not_found(self):
        """존재하지 않는 파일 해시 계산 테스트"""
        with pytest.raises(FileNotFoundError):
            calculate_file_hash("/nonexistent/file.txt")

    def test_calculate_file_hash_directory(self):
        """디렉토리 해시 계산 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValueError):
                calculate_file_hash(temp_dir)


class TestRetryWithBackoff:
    """재시도 함수 테스트"""

    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """첫 번째 시도에서 성공하는 경우 테스트"""
        async def success_func():
            return "success"
        
        result = await retry_with_backoff(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """실패 후 성공하는 경우 테스트"""
        attempt_count = 0
        
        async def eventually_success_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("임시 오류")
            return "success"
        
        result = await retry_with_backoff(
            eventually_success_func, 
            max_retries=3,
            initial_delay=0.1
        )
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded(self):
        """최대 재시도 횟수 초과 테스트"""
        async def always_fail_func():
            raise ValueError("항상 실패")
        
        with pytest.raises(ValueError, match="항상 실패"):
            await retry_with_backoff(
                always_fail_func, 
                max_retries=2,
                initial_delay=0.1
            )

    @pytest.mark.asyncio
    async def test_retry_with_sync_function(self):
        """동기 함수 재시도 테스트"""
        def sync_success_func():
            return "sync_success"
        
        result = await retry_with_backoff(sync_success_func)
        assert result == "sync_success"


class TestFilenameUtils:
    """파일명 유틸리티 테스트"""

    def test_sanitize_filename(self):
        """파일명 정리 테스트"""
        # 위험한 문자 제거
        filename = "test<>file.txt"
        sanitized = sanitize_filename(filename)
        assert sanitized == "test__file.txt"
        
        # 공백 언더스코어로 변환
        filename = "test file name.txt"
        sanitized = sanitize_filename(filename)
        assert sanitized == "test_file_name.txt"
        
        # 길이 제한
        long_filename = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_filename, max_length=10)
        assert len(sanitized) <= 10
        assert sanitized.endswith(".txt")

    def test_ensure_directory(self):
        """디렉토리 생성 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test" / "nested" / "dir"
            
            result = ensure_directory(test_dir)
            
            assert result == test_dir
            assert test_dir.exists()
            assert test_dir.is_dir()


class TestFormatUtils:
    """포맷 유틸리티 테스트"""

    def test_format_file_size(self):
        """파일 크기 포맷팅 테스트"""
        assert format_file_size(0) == "0 B"
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1024 * 1024) == "1.0 MB"
        assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_file_size(1536) == "1.5 KB"

    def test_format_duration(self):
        """지속 시간 포맷팅 테스트"""
        assert format_duration(30.5) == "30.5초"
        assert format_duration(90) == "1분 30.0초"
        assert format_duration(3661) == "1시간 1분 1.0초"
        assert format_duration(3600) == "1시간 0분 0.0초"

    def test_validate_url(self):
        """URL 유효성 검증 테스트"""
        # 유효한 URL
        assert validate_url("https://example.com") is True
        assert validate_url("http://localhost:8080") is True
        assert validate_url("https://api.example.com/v1/data") is True
        
        # 유효하지 않은 URL
        assert validate_url("not-a-url") is False
        assert validate_url("ftp://example.com") is False
        assert validate_url("") is False

    def test_truncate_string(self):
        """문자열 자르기 테스트"""
        text = "이것은 매우 긴 텍스트입니다"
        
        # 길이 제한 없음
        result = truncate_string(text, 50)
        assert result == text
        
        # 길이 제한 있음
        result = truncate_string(text, 10)
        assert len(result) <= 10
        assert result.endswith("...")
        
        # 커스텀 접미사
        result = truncate_string(text, 10, suffix="…")
        assert result.endswith("…")


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    def test_file_processing_workflow(self):
        """파일 처리 워크플로우 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 디렉토리 생성
            work_dir = ensure_directory(Path(temp_dir) / "work")
            
            # 파일 생성
            filename = sanitize_filename("test file<>.txt")
            file_path = work_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("테스트 내용")
            
            # 파일 해시 계산
            file_hash = calculate_file_hash(file_path)
            
            # 파일 크기 포맷팅
            file_size = format_file_size(file_path.stat().st_size)
            
            assert file_path.exists()
            assert len(file_hash) == 64
            assert "B" in file_size

    def test_id_generation_uniqueness(self):
        """ID 생성 고유성 테스트"""
        task_ids = set()
        worker_ids = set()
        
        # 100개의 고유 ID 생성
        for _ in range(100):
            task_ids.add(generate_task_id())
            worker_ids.add(generate_worker_id())
        
        # 모든 ID가 고유한지 확인
        assert len(task_ids) == 100
        assert len(worker_ids) == 100 