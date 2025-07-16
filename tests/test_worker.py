"""
워커 시스템 테스트 모듈

ProcessManager, ScriptExecutor, ScrapingWorker의 단위 테스트를 제공합니다.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.settings import Settings
from src.models.base import ScrapingRequest, ScrapingResponse
from src.models.enums import TaskStatus
from src.scripts.metadata import ScriptMetadata
from src.worker.process_manager import ProcessManager
from src.worker.script_executor import ScriptExecutor
from src.worker.worker_main import ScrapingWorker


class TestProcessManager:
    """프로세스 매니저 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정"""
        return Settings(
            process_timeout=30,
            process_memory_limit="128MB",
            process_cpu_limit=60,
            process_file_limit=512
        )

    @pytest.fixture
    def process_manager(self, settings):
        """프로세스 매니저 픽스처"""
        return ProcessManager(settings)

    @pytest.fixture
    def temp_script(self):
        """임시 테스트 스크립트 생성"""
        script_content = '''#!/usr/bin/env python3
import json
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parameters', type=str, required=True)
    args = parser.parse_args()

    parameters = json.loads(args.parameters)

    # 간단한 테스트 결과
    result = {
        "status": "success",
        "data": parameters,
        "message": "테스트 스크립트 실행 완료"
    }

    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir)
            script_file = script_path / "main.py"

            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)

            yield script_path

    @pytest.mark.asyncio
    async def test_execute_script_success(self, process_manager, temp_script):
        """스크립트 성공 실행 테스트"""
        parameters = {"test_key": "test_value", "url": "https://example.com"}

        return_code, stdout, stderr = await process_manager.execute_script(
            script_path=temp_script,
            entry_point="main.py",
            parameters=parameters,
            timeout=30,
            memory_limit="128MB"
        )

        assert return_code == 0
        assert "test_value" in stdout
        assert "success" in stdout
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_execute_script_timeout(self, process_manager, temp_script):
        """스크립트 타임아웃 테스트"""
        # 무한 루프 스크립트 생성
        timeout_script_content = '''#!/usr/bin/env python3
import time
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parameters', type=str, required=True)
    args = parser.parse_args()
    
    # 무한 루프
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
'''
        
        timeout_script = temp_script / "timeout.py"
        with open(timeout_script, 'w', encoding='utf-8') as f:
            f.write(timeout_script_content)

        with pytest.raises(Exception) as exc_info:
            await process_manager.execute_script(
                script_path=temp_script,
                entry_point="timeout.py",
                parameters={},
                timeout=2  # 2초 타임아웃
            )

        assert "타임아웃" in str(exc_info.value)

    def test_parse_memory_limit(self, process_manager):
        """메모리 제한 파싱 테스트"""
        assert process_manager._parse_memory_limit("512MB") == 512 * 1024 * 1024
        assert process_manager._parse_memory_limit("1GB") == 1024 * 1024 * 1024
        assert process_manager._parse_memory_limit("1024KB") == 1024 * 1024
        assert process_manager._parse_memory_limit("1024") == 1024

    def test_get_active_process_count(self, process_manager):
        """활성 프로세스 수 확인 테스트"""
        assert process_manager.get_active_process_count() == 0

    @pytest.mark.asyncio
    async def test_cleanup_all_processes(self, process_manager):
        """프로세스 정리 테스트"""
        # 정리 함수가 예외 없이 실행되는지 확인
        await process_manager.cleanup_all_processes()
        assert process_manager.get_active_process_count() == 0


class TestScriptExecutor:
    """스크립트 실행기 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정"""
        from src.models.enums import ScriptRepositoryType
        return Settings(
            process_timeout=30,
            process_memory_limit="128MB",
            max_concurrent_tasks=1,
            script_repository_type=ScriptRepositoryType.GIT,
            script_repository_url="https://github.com/test/scripts.git",
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            rabbitmq_task_queue="test_queue"
        )

    @pytest.fixture
    def mock_cache_manager(self):
        """Mock 캐시 매니저"""
        cache_manager = AsyncMock()
        cache_manager.cache_dir = Path("/tmp/test_cache")
        
        # metadata_parser mock
        cache_manager.metadata_parser = MagicMock()
        cache_manager.metadata_parser.validate_metadata.return_value = True
        
        return cache_manager

    @pytest.fixture
    def script_executor(self, settings, mock_cache_manager):
        """스크립트 실행기 픽스처"""
        return ScriptExecutor(settings, mock_cache_manager)

    @pytest.fixture
    def test_metadata(self):
        """테스트용 메타데이터"""
        from datetime import datetime
        return ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            entry_point="main.py",
            description="테스트 스크래퍼",
            author="test_author",
            dependencies=[],
            memory_limit="128MB",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    @pytest.fixture
    def test_script_path(self):
        """테스트 스크립트 경로"""
        script_content = '''#!/usr/bin/env python3
import json
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parameters', type=str, required=True)
    args = parser.parse_args()

    parameters = json.loads(args.parameters)

    result = {
        "status": "success", 
        "data": {"scraped_data": parameters.get("url", "default")},
        "count": 1
    }

    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir)
            script_file = script_path / "main.py"

            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)

            yield script_path

    @pytest.mark.asyncio
    async def test_execute_scraping_request_success(
        self, script_executor, mock_cache_manager, test_metadata, test_script_path
    ):
        """스크래핑 요청 성공 실행 테스트"""
        # Mock 설정
        mock_cache_manager.get_script.return_value = (test_script_path, test_metadata)

        request = ScrapingRequest(
            script_name="test_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"},
            timeout=30
        )

        response = await script_executor.execute_scraping_request(request)

        assert response.status == TaskStatus.COMPLETED
        assert response.data is not None
        assert response.data["status"] == "success"
        assert response.error is None
        assert response.execution_time > 0

    @pytest.mark.asyncio
    async def test_execute_scraping_request_script_not_found(
        self, script_executor, mock_cache_manager, test_metadata
    ):
        """스크립트 파일이 없는 경우 테스트"""
        # 존재하지 않는 경로 설정
        mock_cache_manager.get_script.return_value = (Path("/nonexistent"), test_metadata)

        request = ScrapingRequest(
            script_name="nonexistent_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"}
        )

        response = await script_executor.execute_scraping_request(request)

        assert response.status == TaskStatus.FAILED
        assert response.error is not None
        assert "스크립트 실행" in response.error and "실패" in response.error

    @pytest.mark.asyncio
    async def test_validate_script_execution_success(
        self, script_executor, test_metadata, test_script_path
    ):
        """스크립트 실행 검증 성공 테스트"""
        is_valid = await script_executor.validate_script_execution(test_script_path, test_metadata)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_script_execution_missing_file(
        self, script_executor, test_metadata
    ):
        """스크립트 파일 없음 검증 테스트"""
        nonexistent_path = Path("/nonexistent")
        is_valid = await script_executor.validate_script_execution(nonexistent_path, test_metadata)
        assert is_valid is False

    def test_parse_script_output_json(self, script_executor):
        """스크립트 출력 JSON 파싱 테스트"""
        json_output = '{"status": "success", "data": {"url": "https://example.com"}}'
        result = script_executor._parse_script_output(json_output)
        
        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"

    def test_parse_script_output_text(self, script_executor):
        """스크립트 출력 텍스트 파싱 테스트"""
        text_output = "스크래핑 완료\n결과: 성공"
        result = script_executor._parse_script_output(text_output)
        
        assert "output" in result
        assert result["output"] == text_output

    def test_extract_error_message(self, script_executor):
        """에러 메시지 추출 테스트"""
        stderr = """Traceback (most recent call last):
  File "test.py", line 10, in <module>
    raise ValueError("테스트 에러")
ValueError: 테스트 에러"""

        error_msg = script_executor._extract_error_message(stderr, 1)
        assert "테스트 에러" in error_msg

    @pytest.mark.asyncio
    async def test_get_execution_statistics(self, script_executor):
        """실행 통계 조회 테스트"""
        stats = await script_executor.get_execution_statistics()
        
        assert "active_processes" in stats
        assert "cache_directory" in stats
        assert "settings" in stats
        assert stats["active_processes"] == 0

    def test_is_busy(self, script_executor):
        """바쁜 상태 확인 테스트"""
        # 초기 상태는 바쁘지 않음
        assert script_executor.is_busy() is False

    @pytest.mark.asyncio
    async def test_cleanup(self, script_executor):
        """리소스 정리 테스트"""
        # 정리 함수가 예외 없이 실행되는지 확인
        await script_executor.cleanup()


class TestScrapingWorker:
    """스크래핑 워커 테스트"""

    @pytest.fixture
    def settings(self):
        """테스트용 설정"""
        from src.models.enums import ScriptRepositoryType
        return Settings(
            script_repository_type=ScriptRepositoryType.GIT,
            script_repository_url="https://github.com/test/scripts.git",
            max_concurrent_tasks=1,
            worker_heartbeat_interval=10,
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            rabbitmq_task_queue="test_queue"
        )

    @pytest.fixture
    def worker(self):
        """워커 픽스처"""
        from src.models.enums import ScriptRepositoryType
        from unittest.mock import patch
        
        # 테스트용 설정 Mock
        test_settings = Settings(
            script_repository_type=ScriptRepositoryType.GIT,
            script_repository_url="https://github.com/test/scripts.git",
            max_concurrent_tasks=1,
            worker_heartbeat_interval=10,
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            rabbitmq_task_queue="test_queue"
        )
        
        with patch('src.worker.worker_main.get_settings', return_value=test_settings):
            return ScrapingWorker("test-worker")

    def test_worker_initialization(self, worker):
        """워커 초기화 테스트"""
        assert worker.worker_id == "test-worker"
        assert worker.is_running is False
        assert worker.is_shutdown is False

    def test_signal_handler(self, worker):
        """시그널 핸들러 테스트"""
        worker._signal_handler(2, None)  # SIGINT

        assert worker.is_shutdown is True
        assert worker.is_running is False

    @pytest.mark.asyncio
    async def test_handle_task_success(self, worker):
        """작업 처리 성공 테스트"""
        # Mock script executor
        worker.script_executor = MagicMock()
        worker.script_executor.is_busy.return_value = False
        worker.script_executor.execute_scraping_request = AsyncMock(return_value=ScrapingResponse(
            request_id="test-123",
            status=TaskStatus.COMPLETED,
            data={"result": "success"}
        ))

        # Mock task manager
        worker.task_manager = AsyncMock()

        request = ScrapingRequest(
            request_id="test-123",
            script_name="test_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"}
        )

        response = await worker._handle_task(request)

        assert response.status == TaskStatus.COMPLETED
        assert response.request_id == "test-123"

    @pytest.mark.asyncio
    async def test_handle_task_worker_busy(self, worker):
        """워커 바쁜 상태에서 작업 처리 테스트"""
        # Mock script executor - 바쁜 상태
        worker.script_executor = MagicMock()
        worker.script_executor.is_busy.return_value = True

        request = ScrapingRequest(
            request_id="test-123",
            script_name="test_scraper",
            script_version="1.0.0",
            parameters={"url": "https://example.com"}
        )

        response = await worker._handle_task(request)

        assert response.status == TaskStatus.FAILED
        assert "최대 용량" in response.error

    @pytest.mark.asyncio
    async def test_get_status(self, worker):
        """워커 상태 조회 테스트"""
        # Mock script executor
        worker.script_executor = AsyncMock()
        worker.script_executor.get_execution_statistics.return_value = {
            "active_processes": 0
        }

        # Mock rabbitmq worker
        worker.rabbitmq_worker = MagicMock()
        worker.rabbitmq_worker.is_connected.return_value = True

        status = await worker.get_status()

        assert status["worker_id"] == "test-worker"
        assert status["is_running"] is False
        assert status["rabbitmq_connected"] is True

    @pytest.mark.asyncio
    async def test_cleanup(self, worker):
        """워커 정리 테스트"""
        # Mock 컴포넌트들
        worker.script_executor = AsyncMock()
        worker.rabbitmq_worker = AsyncMock()
        worker.task_manager = AsyncMock()
        worker.worker_monitor = AsyncMock()

        # 정리 함수가 예외 없이 실행되는지 확인
        await worker.cleanup()

        # 각 컴포넌트의 정리 메서드가 호출되었는지 확인
        worker.script_executor.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_worker_integration():
    """워커 통합 테스트 (간단 버전)"""
    from src.models.enums import ScriptRepositoryType
    from unittest.mock import patch
    
    # 테스트용 설정 Mock
    test_settings = Settings(
        script_repository_type=ScriptRepositoryType.GIT,
        script_repository_url="https://github.com/test/scripts.git",
        max_concurrent_tasks=1,
        worker_heartbeat_interval=10,
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        rabbitmq_task_queue="test_queue"
    )
    
    with patch('src.worker.worker_main.get_settings', return_value=test_settings):
        worker = ScrapingWorker("integration-test-worker")

        # 기본 상태 확인
        assert worker.worker_id == "integration-test-worker"
        assert worker.is_running is False

        # 상태 조회 (초기화 전)
        status = await worker.get_status()
        assert status["worker_id"] == "integration-test-worker"
        assert "error" not in status or status.get("error") is None 