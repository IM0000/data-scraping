"""
프로세스 관리 모듈

차일드 프로세스의 실행, 모니터링, 리소스 제한을 관리합니다.
"""

import asyncio
import json
import os
import resource
import signal
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import psutil

from ..exceptions import ProcessExecutionException, ResourceLimitException
from ..utils.logging import get_logger

logger = get_logger(__name__)


class ProcessManager:
    """차일드 프로세스 관리자"""

    def __init__(self, settings):
        """
        프로세스 매니저 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.logger = logger
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def execute_script(
        self,
        script_path: Path,
        entry_point: str,
        parameters: Dict[str, Any],
        timeout: Optional[int] = None,
        memory_limit: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        스크립트를 차일드 프로세스에서 실행

        Args:
            script_path: 스크립트 디렉토리 경로
            entry_point: 실행할 스크립트 파일명
            parameters: 스크립트 매개변수
            timeout: 실행 타임아웃 (초, None이면 설정값 사용)
            memory_limit: 메모리 제한 (예: "512MB", None이면 설정값 사용)

        Returns:
            (종료 코드, 표준 출력, 표준 에러) 튜플

        Raises:
            ProcessExecutionException: 프로세스 실행 오류
            ResourceLimitException: 리소스 제한 초과
        """
        script_file = script_path / entry_point
        timeout = timeout or self.settings.process_timeout
        memory_limit = memory_limit or self.settings.process_memory_limit

        if not script_file.exists():
            raise ProcessExecutionException(f"스크립트 파일을 찾을 수 없습니다: {script_file}")

        # 스크립트 실행 명령 구성
        cmd = [
            "python", str(script_file),
            "--parameters", json.dumps(parameters, ensure_ascii=False)
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
                preexec_fn=lambda: self._set_process_limits(memory_limit),
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

                return_code = process.returncode or 0

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
                raise ProcessExecutionException(f"스크립트 실행 타임아웃: {timeout}초")

            except Exception as e:
                self.logger.error(f"스크립트 실행 오류: {e}")
                await self._terminate_process(process)
                raise ProcessExecutionException(f"스크립트 실행 오류: {e}")

        except Exception as e:
            self.logger.error(f"프로세스 생성 오류: {e}")
            raise ProcessExecutionException(f"프로세스 생성 오류: {e}")

        finally:
            # 프로세스 정리
            if process_id in self.active_processes:
                del self.active_processes[process_id]

    def _set_process_limits(self, memory_limit: str):
        """프로세스 리소스 제한 설정"""
        try:
            # CPU 시간 제한 (초)
            resource.setrlimit(resource.RLIMIT_CPU, (
                self.settings.process_cpu_limit,
                self.settings.process_cpu_limit
            ))

            # 메모리 제한 (바이트)
            memory_bytes = self._parse_memory_limit(memory_limit)
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

            # 파일 디스크립터 제한
            resource.setrlimit(resource.RLIMIT_NOFILE, (
                self.settings.process_file_limit,
                self.settings.process_file_limit
            ))

            # 프로세스 우선순위 설정 (낮은 우선순위)
            os.nice(10)

        except Exception as e:
            # 리소스 제한 설정 실패는 로그만 남기고 계속 진행
            self.logger.warning(f"리소스 제한 설정 실패: {e}")

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

    async def _monitor_process_resources(self, process: asyncio.subprocess.Process, memory_limit: str):
        """프로세스 리소스 모니터링"""
        memory_bytes = self._parse_memory_limit(memory_limit)

        while process.returncode is None:
            try:
                # psutil을 사용한 프로세스 모니터링
                ps_process = psutil.Process(process.pid)

                # 메모리 사용량 확인
                memory_info = ps_process.memory_info()
                if memory_info.rss > memory_bytes:
                    self.logger.warning(
                        f"메모리 제한 초과: {memory_info.rss / 1024 / 1024:.2f}MB > "
                        f"{memory_bytes / 1024 / 1024:.2f}MB"
                    )
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

    async def _terminate_process(self, process: asyncio.subprocess.Process):
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

    def get_active_process_count(self) -> int:
        """활성 프로세스 수 반환"""
        return len(self.active_processes) 