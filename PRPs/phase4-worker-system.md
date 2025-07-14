# PRP-4: Worker System

## Goal

Implement a robust worker system that retrieves tasks from RabbitMQ queue, downloads and executes scraping scripts in isolated child processes, and reports results back via RPC reply_to queues. The system should handle process isolation, resource management, error handling, and concurrent task execution to ensure worker stability.

## Why

- **Process isolation**: Ensures script execution doesn't affect the main worker process - critical for worker stability
- **Worker stability**: Prevents script failures (bugs, infinite loops, memory leaks) from crashing the entire worker
- **Resource management**: Controls CPU, memory, and execution time limits for each script
- **Scalability**: Supports multiple concurrent tasks and horizontal scaling
- **Reliability**: Handles script failures gracefully without affecting other tasks
- **Security**: Prevents malicious scripts from affecting the system
- **RPC communication**: Enables synchronous response delivery using correlation_id pattern

## What

Build a comprehensive worker system that includes:

- Task retrieval from RabbitMQ queue with RPC pattern support
- Script download and execution in sandboxed child processes for isolation
- Resource monitoring and limit enforcement per script execution
- Error handling and recovery mechanisms
- Result reporting via RabbitMQ reply_to queues with correlation_id
- Heartbeat monitoring and worker health checks
- Connection management and recovery for RabbitMQ

### Success Criteria

- [ ] Workers can retrieve tasks from RabbitMQ queue reliably
- [ ] Scripts execute in isolated child processes without affecting worker
- [ ] Resource limits are enforced correctly per script execution
- [ ] Failed scripts don't crash the worker process
- [ ] Results are reported back via reply_to queues with correct correlation_id
- [ ] Multiple workers can run concurrently
- [ ] RabbitMQ connection recovery works properly
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# Process Management
- url: https://docs.python.org/3/library/subprocess.html
  why: Child process execution and management for script isolation

- url: https://docs.python.org/3/library/multiprocessing.html
  why: Process pools and resource sharing

- url: https://docs.python.org/3/library/asyncio-subprocess.html
  why: Async subprocess management

# Resource Management
- url: https://docs.python.org/3/library/resource.html
  why: System resource monitoring and limits for child processes

- url: https://psutil.readthedocs.io/en/latest/
  why: Process and system monitoring

# RabbitMQ Integration
- url: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
  why: RPC pattern implementation for task processing

- url: https://pika.readthedocs.io/en/stable/
  why: RabbitMQ client for task consumption and result publishing

- url: https://aio-pika.readthedocs.io/en/latest/
  why: Async RabbitMQ client for high-performance task processing

# Dependencies
- file: PRPs/phase1-core-models.md
  why: Uses core data models and exceptions

- file: PRPs/phase2-message-queue.md
  why: RabbitMQ RPC integration and task management

- file: PRPs/phase3-script-manager.md
  why: Script downloading and caching

- file: examples/basic_structure.py
  why: Follow existing coding patterns

- file: examples/test_pattern.py
  why: Test patterns for validation gates
```

### Current Codebase Structure (After Phase 1-3)

```
src/
├── models/
│   ├── base.py              # Core data models
│   └── enums.py             # Task status enums
├── config/
│   └── settings.py          # Configuration
├── utils/
│   ├── logging.py           # Logging system
│   └── helpers.py           # Common utilities
├── exceptions.py            # Exception classes
├── queue/                   # Message queue system
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
├── scripts/                 # Script management
│   ├── metadata.py
│   ├── repository.py
│   ├── cache_manager.py
│   └── downloader.py
└── worker/                  # NEW: Worker system
    ├── __init__.py
    ├── process_manager.py   # Child process management
    ├── resource_monitor.py  # Resource monitoring
    ├── script_executor.py   # Script execution
    └── worker_main.py       # Main worker process
```

### Key Requirements from INITIAL.md

- Child process isolation for security
- Resource limits (CPU, memory, timeout)
- Comprehensive logging in Korean
- Support for HTTP scraping, captcha handling, browser automation
- Synchronous response delivery with timeout handling

## Implementation Blueprint

### Task 1: Process Manager

```python
# worker/process_manager.py
import asyncio
import subprocess
import signal
import psutil
import resource
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from src.utils.logging import setup_logging
from src.exceptions import ScriptExecutionException

class ProcessManager:
    """차일드 프로세스 관리자"""

    def __init__(self, settings):
        """
        프로세스 매니저 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.logger = setup_logging(settings)
        self.active_processes: Dict[str, subprocess.Popen] = {}

    async def execute_script(
        self,
        script_path: Path,
        entry_point: str,
        parameters: Dict[str, Any],
        timeout: int = 300,
        memory_limit: str = "512MB"
    ) -> Tuple[int, str, str]:
        """
        스크립트를 차일드 프로세스에서 실행

        Args:
            script_path: 스크립트 디렉토리 경로
            entry_point: 실행할 스크립트 파일명
            parameters: 스크립트 매개변수
            timeout: 실행 타임아웃 (초)
            memory_limit: 메모리 제한 (예: "512MB")

        Returns:
            (종료 코드, 표준 출력, 표준 에러) 튜플
        """
        script_file = script_path / entry_point

        if not script_file.exists():
            raise ScriptExecutionException(f"스크립트 파일을 찾을 수 없습니다: {script_file}")

        # 스크립트 실행 명령 구성
        cmd = [
            "python", str(script_file),
            "--parameters", json.dumps(parameters)
        ]

        # 환경 변수 설정
        env = os.environ.copy()
        env["PYTHONPATH"] = str(script_path)

        process_id = f"proc_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        try:
            # 프로세스 시작
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=script_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._set_process_limits,
                start_new_session=True  # 새 세션으로 시작하여 시그널 격리
            )

            self.active_processes[process_id] = process
            self.logger.info(f"스크립트 실행 시작: {script_file} (PID: {process.pid})")

            # 리소스 모니터링 시작
            monitor_task = asyncio.create_task(
                self._monitor_process_resources(process, memory_limit)
            )

            try:
                # 타임아웃과 함께 프로세스 실행
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                return_code = process.returncode

                # 모니터링 작업 정리
                monitor_task.cancel()

                # 결과 디코딩
                stdout_text = stdout.decode('utf-8') if stdout else ""
                stderr_text = stderr.decode('utf-8') if stderr else ""

                self.logger.info(f"스크립트 실행 완료: {script_file} (종료코드: {return_code})")

                return return_code, stdout_text, stderr_text

            except asyncio.TimeoutError:
                self.logger.error(f"스크립트 실행 타임아웃: {script_file}")
                await self._terminate_process(process)
                raise ScriptExecutionException(f"스크립트 실행 타임아웃: {timeout}초")

            except Exception as e:
                self.logger.error(f"스크립트 실행 오류: {e}")
                await self._terminate_process(process)
                raise ScriptExecutionException(f"스크립트 실행 오류: {e}")

        except Exception as e:
            self.logger.error(f"프로세스 생성 오류: {e}")
            raise ScriptExecutionException(f"프로세스 생성 오류: {e}")

        finally:
            # 프로세스 정리
            if process_id in self.active_processes:
                del self.active_processes[process_id]

    def _set_process_limits(self):
        """프로세스 리소스 제한 설정"""
        try:
            # CPU 시간 제한 (초)
            resource.setrlimit(resource.RLIMIT_CPU, (300, 300))

            # 메모리 제한 (바이트)
            memory_bytes = self._parse_memory_limit("512MB")
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

            # 파일 디스크립터 제한
            resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))

            # 프로세스 우선순위 설정 (낮은 우선순위)
            os.nice(10)

        except Exception as e:
            # 리소스 제한 설정 실패는 로그만 남기고 계속 진행
            pass

    def _parse_memory_limit(self, memory_limit: str) -> int:
        """메모리 제한 문자열을 바이트로 변환"""
        memory_limit = memory_limit.upper()

        if memory_limit.endswith('KB'):
            return int(memory_limit[:-2]) * 1024
        elif memory_limit.endswith('MB'):
            return int(memory_limit[:-2]) * 1024 * 1024
        elif memory_limit.endswith('GB'):
            return int(memory_limit[:-2]) * 1024 * 1024 * 1024
        else:
            return int(memory_limit)

    async def _monitor_process_resources(self, process: subprocess.Popen, memory_limit: str):
        """프로세스 리소스 모니터링"""
        memory_bytes = self._parse_memory_limit(memory_limit)

        while process.returncode is None:
            try:
                # psutil을 사용한 프로세스 모니터링
                ps_process = psutil.Process(process.pid)

                # 메모리 사용량 확인
                memory_info = ps_process.memory_info()
                if memory_info.rss > memory_bytes:
                    self.logger.warning(f"메모리 제한 초과: {memory_info.rss / 1024 / 1024:.2f}MB")
                    await self._terminate_process(process)
                    break

                # CPU 사용량 확인
                cpu_percent = ps_process.cpu_percent(interval=1)
                if cpu_percent > 90:  # 90% 이상 CPU 사용
                    self.logger.warning(f"높은 CPU 사용률: {cpu_percent}%")

                await asyncio.sleep(1)  # 1초마다 모니터링

            except psutil.NoSuchProcess:
                # 프로세스가 종료됨
                break
            except Exception as e:
                self.logger.error(f"프로세스 모니터링 오류: {e}")
                break

    async def _terminate_process(self, process: subprocess.Popen):
        """프로세스 강제 종료"""
        if process.returncode is None:
            try:
                # 프로세스 그룹 전체 종료
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)

                # 5초 대기 후 SIGKILL
                await asyncio.sleep(5)
                if process.returncode is None:
                    os.killpg(pgid, signal.SIGKILL)

            except Exception as e:
                self.logger.error(f"프로세스 종료 오류: {e}")

    async def cleanup_all_processes(self):
        """모든 활성 프로세스 정리"""
        for process_id, process in self.active_processes.items():
            try:
                await self._terminate_process(process)
                self.logger.info(f"프로세스 정리 완료: {process_id}")
            except Exception as e:
                self.logger.error(f"프로세스 정리 오류: {e}")

        self.active_processes.clear()
```

### Task 2: Script Executor

```python
# worker/script_executor.py
import asyncio
import json
import traceback
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.scripts.metadata import ScriptMetadata
from src.scripts.cache_manager import CacheManager
from src.worker.process_manager import ProcessManager
from src.utils.logging import setup_logging
from src.exceptions import ScriptExecutionException

class ScriptExecutor:
    """스크립트 실행기"""

    def __init__(self, settings, cache_manager: CacheManager):
        """
        스크립트 실행기 초기화

        Args:
            settings: 시스템 설정
            cache_manager: 캐시 매니저
        """
        self.settings = settings
        self.cache_manager = cache_manager
        self.process_manager = ProcessManager(settings)
        self.logger = setup_logging(settings)

    async def execute_scraping_request(self, request: ScrapingRequest) -> ScrapingResponse:
        """
        스크래핑 요청 실행

        Args:
            request: 스크래핑 요청

        Returns:
            스크래핑 응답
        """
        start_time = datetime.now()

        try:
            self.logger.info(f"스크래핑 요청 처리 시작: {request.request_id}")

            # 스크립트 다운로드 및 캐시
            script_path, metadata = await self.cache_manager.get_script(
                request.script_name,
                request.script_version
            )

            self.logger.info(f"스크립트 준비 완료: {script_path}")

            # 스크립트 실행
            return_code, stdout, stderr = await self.process_manager.execute_script(
                script_path=script_path,
                entry_point=metadata.entry_point,
                parameters=request.parameters,
                timeout=request.timeout,
                memory_limit=metadata.memory_limit
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            # 실행 결과 분석
            if return_code == 0:
                # 성공적인 실행
                try:
                    # stdout에서 JSON 결과 파싱
                    result_data = json.loads(stdout) if stdout.strip() else {}

                    response = ScrapingResponse(
                        request_id=request.request_id,
                        status=TaskStatus.COMPLETED,
                        data=result_data,
                        execution_time=execution_time,
                        completed_at=datetime.now()
                    )

                    self.logger.info(f"스크래핑 요청 성공: {request.request_id}")
                    return response

                except json.JSONDecodeError as e:
                    # JSON 파싱 실패
                    self.logger.error(f"결과 파싱 실패: {e}")

                    response = ScrapingResponse(
                        request_id=request.request_id,
                        status=TaskStatus.FAILED,
                        error=f"결과 파싱 실패: {e}",
                        execution_time=execution_time,
                        completed_at=datetime.now()
                    )

                    return response
            else:
                # 실행 실패
                error_message = stderr if stderr else f"스크립트 실행 실패 (종료코드: {return_code})"

                response = ScrapingResponse(
                    request_id=request.request_id,
                    status=TaskStatus.FAILED,
                    error=error_message,
                    execution_time=execution_time,
                    completed_at=datetime.now()
                )

                self.logger.error(f"스크립트 실행 실패: {request.request_id} - {error_message}")
                return response

        except ScriptExecutionException as e:
            # 스크립트 실행 관련 예외
            execution_time = (datetime.now() - start_time).total_seconds()

            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
                completed_at=datetime.now()
            )

            self.logger.error(f"스크립트 실행 예외: {request.request_id} - {e}")
            return response

        except Exception as e:
            # 예기치 않은 오류
            execution_time = (datetime.now() - start_time).total_seconds()
            error_trace = traceback.format_exc()

            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error=f"예기치 않은 오류: {str(e)}",
                execution_time=execution_time,
                completed_at=datetime.now()
            )

            self.logger.error(f"예기치 않은 오류: {request.request_id} - {error_trace}")
            return response

    async def validate_script_execution(self, script_path: Path, metadata: ScriptMetadata) -> bool:
        """
        스크립트 실행 가능성 검증

        Args:
            script_path: 스크립트 경로
            metadata: 스크립트 메타데이터

        Returns:
            실행 가능 여부
        """
        try:
            # 엔트리 포인트 파일 존재 확인
            entry_file = script_path / metadata.entry_point
            if not entry_file.exists():
                self.logger.error(f"엔트리 포인트 파일 없음: {entry_file}")
                return False

            # 기본 구문 검사
            with open(entry_file, 'r', encoding='utf-8') as f:
                script_content = f.read()

            # 기본적인 Python 구문 검사
            compile(script_content, str(entry_file), 'exec')

            # 메타데이터 검증
            if not self.cache_manager.metadata_parser.validate_metadata(metadata):
                self.logger.error(f"메타데이터 검증 실패: {metadata.name}")
                return False

            return True

        except SyntaxError as e:
            self.logger.error(f"스크립트 구문 오류: {e}")
            return False
        except Exception as e:
            self.logger.error(f"스크립트 검증 오류: {e}")
            return False

    async def cleanup(self):
        """리소스 정리"""
        await self.process_manager.cleanup_all_processes()
```

### Task 3: Main Worker Process

```python
# worker/worker_main.py
import asyncio
import signal
import sys
from typing import Optional
from datetime import datetime
from src.config.settings import Settings
from src.queue.redis_queue import RedisQueue
from src.queue.task_manager import TaskManager
from src.queue.worker_monitor import WorkerMonitor
from src.scripts.cache_manager import CacheManager
from src.scripts.repository import GitRepository, HttpRepository, S3Repository
from src.worker.script_executor import ScriptExecutor
from src.utils.logging import setup_logging
from src.utils.helpers import generate_task_id

class ScrapingWorker:
    """스크래핑 워커 메인 클래스"""

    def __init__(self, worker_id: Optional[str] = None):
        """
        워커 초기화

        Args:
            worker_id: 워커 ID (None이면 자동 생성)
        """
        self.settings = Settings()
        self.worker_id = worker_id or f"worker_{generate_task_id()}"
        self.logger = setup_logging(self.settings)
        self.is_running = False
        self.is_shutdown = False

        # 컴포넌트 초기화
        self.redis_queue = None
        self.task_manager = None
        self.worker_monitor = None
        self.script_executor = None

        # 시그널 핸들러 설정
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.logger.info(f"워커 초기화 완료: {self.worker_id}")

    async def initialize(self):
        """워커 컴포넌트 초기화"""
        try:
            # Redis 큐 연결
            self.redis_queue = RedisQueue(self.settings)
            await self.redis_queue.connect()

            # 작업 매니저 초기화
            self.task_manager = TaskManager(self.redis_queue)

            # 워커 모니터 초기화
            self.worker_monitor = WorkerMonitor(self.redis_queue)

            # 저장소 초기화
            if self.settings.script_repository_type == "git":
                repository = GitRepository(self.settings, self.settings.script_repository_url)
            elif self.settings.script_repository_type == "http":
                repository = HttpRepository(self.settings, self.settings.script_repository_url)
            elif self.settings.script_repository_type == "s3":
                repository = S3Repository(self.settings)
            else:
                raise ValueError(f"지원하지 않는 저장소 타입: {self.settings.script_repository_type}")

            # 캐시 매니저 초기화
            cache_manager = CacheManager(self.settings, repository)

            # 스크립트 실행기 초기화
            self.script_executor = ScriptExecutor(self.settings, cache_manager)

            # 워커 등록
            await self.worker_monitor.register_worker(self.worker_id)

            self.logger.info(f"워커 초기화 완료: {self.worker_id}")

        except Exception as e:
            self.logger.error(f"워커 초기화 실패: {e}")
            raise

    async def start(self):
        """워커 시작"""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info(f"워커 시작: {self.worker_id}")

        try:
            # 하트비트 작업 시작
            heartbeat_task = asyncio.create_task(self._heartbeat_worker())

            # 메인 작업 루프 시작
            main_task = asyncio.create_task(self._main_worker_loop())

            # 정리 작업 시작
            cleanup_task = asyncio.create_task(self._cleanup_worker())

            # 모든 작업 완료 대기
            await asyncio.gather(heartbeat_task, main_task, cleanup_task)

        except Exception as e:
            self.logger.error(f"워커 실행 오류: {e}")
            raise
        finally:
            await self.cleanup()

    async def _main_worker_loop(self):
        """메인 워커 루프"""
        while self.is_running and not self.is_shutdown:
            try:
                # 큐에서 작업 가져오기
                task = await self.redis_queue.dequeue_task(self.worker_id)

                if task:
                    self.logger.info(f"작업 처리 시작: {task.request_id}")

                    # 작업 실행
                    response = await self.script_executor.execute_scraping_request(task)

                    # 결과 보고
                    await self.task_manager.complete_task(response)

                    # 워커 통계 업데이트
                    await self.worker_monitor.increment_task_counter(self.worker_id)

                    self.logger.info(f"작업 처리 완료: {task.request_id}")
                else:
                    # 작업이 없으면 잠시 대기
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"작업 처리 오류: {e}")
                await asyncio.sleep(5)  # 오류 시 5초 대기

    async def _heartbeat_worker(self):
        """하트비트 워커"""
        while self.is_running and not self.is_shutdown:
            try:
                await self.worker_monitor.update_heartbeat(self.worker_id)
                await asyncio.sleep(30)  # 30초마다 하트비트
            except Exception as e:
                self.logger.error(f"하트비트 오류: {e}")
                await asyncio.sleep(30)

    async def _cleanup_worker(self):
        """정리 워커"""
        while self.is_running and not self.is_shutdown:
            try:
                # 스크립트 캐시 정리
                await self.script_executor.cache_manager.cleanup_old_cache()

                # 24시간마다 정리
                await asyncio.sleep(86400)
            except Exception as e:
                self.logger.error(f"정리 작업 오류: {e}")
                await asyncio.sleep(3600)  # 오류 시 1시간 대기

    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        self.logger.info(f"종료 시그널 수신: {signum}")
        self.is_shutdown = True
        self.is_running = False

    async def stop(self):
        """워커 정지"""
        self.logger.info(f"워커 정지 시작: {self.worker_id}")
        self.is_running = False

        # 진행 중인 작업 완료 대기 (최대 30초)
        await asyncio.sleep(30)

        await self.cleanup()
        self.logger.info(f"워커 정지 완료: {self.worker_id}")

    async def cleanup(self):
        """리소스 정리"""
        try:
            if self.script_executor:
                await self.script_executor.cleanup()

            if self.worker_monitor:
                await self.worker_monitor.cleanup_inactive_workers()

            self.logger.info(f"워커 정리 완료: {self.worker_id}")

        except Exception as e:
            self.logger.error(f"워커 정리 오류: {e}")

async def main():
    """워커 메인 함수"""
    worker = ScrapingWorker()

    try:
        await worker.initialize()
        await worker.start()
    except KeyboardInterrupt:
        print("워커 종료 요청")
    except Exception as e:
        print(f"워커 실행 오류: {e}")
    finally:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Integration Points

### Environment Variables (.env) - Updated

```bash
# Worker Configuration
WORKER_ID=worker-001  # Optional, auto-generated if not set
MAX_WORKERS=4
WORKER_TIMEOUT=300
WORKER_HEARTBEAT_INTERVAL=30
WORKER_CLEANUP_INTERVAL=86400

# Process Limits
PROCESS_MEMORY_LIMIT=512MB
PROCESS_CPU_LIMIT=300  # seconds
PROCESS_FILE_LIMIT=1024

# Existing from previous phases...
```

### Project Structure - Updated

```
src/
├── models/
│   ├── base.py              # From Phase 1
│   └── enums.py             # From Phase 1
├── config/
│   └── settings.py          # Updated with worker settings
├── utils/
│   ├── logging.py           # From Phase 1
│   └── helpers.py           # From Phase 1
├── exceptions.py            # From Phase 1 (updated with worker exceptions)
├── queue/                   # From Phase 2
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
├── scripts/                 # From Phase 3
│   ├── metadata.py
│   ├── repository.py
│   ├── cache_manager.py
│   └── downloader.py
└── worker/                  # NEW
    ├── __init__.py
    ├── process_manager.py   # Child process management
    ├── script_executor.py   # Script execution orchestrator
    └── worker_main.py       # Main worker process
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Type checking and linting
uv run mypy src/worker/
uv run ruff check src/worker/ --fix

# Expected: No errors. All async functions properly typed.
```

### Level 2: Unit Tests

```python
# tests/test_worker.py
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from src.worker.process_manager import ProcessManager
from src.worker.script_executor import ScriptExecutor
from src.worker.worker_main import ScrapingWorker
from src.models.base import ScrapingRequest, TaskStatus
from src.config.settings import Settings

class TestProcessManager:
    """프로세스 매니저 테스트"""

    @pytest.fixture
    def process_manager(self):
        """프로세스 매니저 픽스처"""
        settings = Settings()
        return ProcessManager(settings)

    @pytest.fixture
    def temp_script(self):
        """임시 스크립트 생성"""
        script_content = '''
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
        parameters = {"test_key": "test_value"}

        return_code, stdout, stderr = await process_manager.execute_script(
            script_path=temp_script,
            entry_point="main.py",
            parameters=parameters,
            timeout=30
        )

        assert return_code == 0
        assert "test_value" in stdout
        assert stderr == ""

    def test_parse_memory_limit(self, process_manager):
        """메모리 제한 파싱 테스트"""
        assert process_manager._parse_memory_limit("512MB") == 512 * 1024 * 1024
        assert process_manager._parse_memory_limit("1GB") == 1024 * 1024 * 1024
        assert process_manager._parse_memory_limit("1024") == 1024

class TestScriptExecutor:
    """스크립트 실행기 테스트"""

    @pytest.fixture
    async def script_executor(self):
        """스크립트 실행기 픽스처"""
        settings = Settings()
        cache_manager = AsyncMock()

        return ScriptExecutor(settings, cache_manager)

    @pytest.mark.asyncio
    async def test_execute_scraping_request(self, script_executor):
        """스크래핑 요청 실행 테스트"""
        # Mock 설정
        script_executor.cache_manager.get_script.return_value = (
            Path("/tmp/test_script"),
            MagicMock(entry_point="main.py", memory_limit="512MB")
        )

        script_executor.process_manager.execute_script.return_value = (
            0,  # return_code
            '{"status": "success", "data": {"url": "https://example.com"}}',  # stdout
            ""  # stderr
        )

        request = ScrapingRequest(
            script_name="test_scraper",
            parameters={"url": "https://example.com"}
        )

        response = await script_executor.execute_scraping_request(request)

        assert response.status == TaskStatus.COMPLETED
        assert response.data["status"] == "success"
        assert response.error is None

class TestScrapingWorker:
    """스크래핑 워커 테스트"""

    @pytest.fixture
    def worker(self):
        """워커 픽스처"""
        return ScrapingWorker("test-worker")

    def test_worker_initialization(self, worker):
        """워커 초기화 테스트"""
        assert worker.worker_id == "test-worker"
        assert worker.is_running is False
        assert worker.is_shutdown is False

    @pytest.mark.asyncio
    async def test_signal_handler(self, worker):
        """시그널 핸들러 테스트"""
        worker._signal_handler(2, None)  # SIGINT

        assert worker.is_shutdown is True
        assert worker.is_running is False
```

```bash
# Run worker tests
uv run pytest tests/test_worker.py -v

# Run integration tests
uv run pytest tests/test_worker_integration.py -v
```

### Level 3: Integration Test

```python
# tests/test_worker_integration.py
@pytest.mark.asyncio
async def test_full_worker_integration():
    """전체 워커 통합 테스트"""
    # Redis 연결 설정
    settings = Settings()

    # 워커 초기화
    worker = ScrapingWorker("integration-test-worker")
    await worker.initialize()

    # 테스트 작업 생성
    request = ScrapingRequest(
        script_name="example_scraper",
        parameters={"url": "https://httpbin.org/json"}
    )

    # 작업 큐에 추가
    await worker.redis_queue.enqueue_task(request)

    # 워커 실행 (제한 시간)
    worker_task = asyncio.create_task(worker.start())

    # 5초 후 워커 정지
    await asyncio.sleep(5)
    await worker.stop()

    # 작업 결과 확인
    status = await worker.task_manager.get_task_status(request.request_id)
    assert status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
```

## Final Validation Checklist

- [ ] Workers can retrieve tasks from RabbitMQ queue reliably
- [ ] Scripts execute in isolated child processes without affecting worker
- [ ] Resource limits are enforced correctly per script execution
- [ ] Failed scripts don't crash the worker process
- [ ] Results are reported back via reply_to queues with correct correlation_id
- [ ] Multiple workers can run concurrently
- [ ] RabbitMQ connection recovery works properly
- [ ] All unit tests pass: `uv run pytest tests/test_worker.py -v`
- [ ] Integration tests pass: `uv run pytest tests/test_worker_integration.py -v`
- [ ] No type errors: `uv run mypy src/worker/`
- [ ] No linting errors: `uv run ruff check src/worker/`
- [ ] Korean logging messages are properly formatted
- [ ] Process cleanup works correctly on shutdown

## Anti-Patterns to Avoid

- ❌ Don't run scripts in the main worker process - use child processes
- ❌ Don't ignore resource limits - enforce memory and CPU constraints
- ❌ Don't let failed scripts crash the worker - handle exceptions gracefully
- ❌ Don't forget to cleanup processes on shutdown
- ❌ Don't skip heartbeat monitoring - maintain worker health status
- ❌ Don't use blocking operations in async worker loops
