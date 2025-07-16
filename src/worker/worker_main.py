"""
워커 메인 모듈

스크래핑 워커의 메인 클래스로 전체 시스템을 통합 관리합니다.
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional, Any, Dict, Union

from ..config.settings import get_settings
from ..models.base import ScrapingRequest, ScrapingResponse
from ..models.enums import TaskStatus, ScriptRepositoryType
from ..queue.rabbitmq_rpc import RabbitMQWorker
from ..queue.task_manager import TaskManager
from ..queue.worker_monitor import WorkerMonitor
from ..scripts.cache_manager import CacheManager
from ..scripts.repository import GitRepository, HttpRepository, S3Repository, RepositoryBase
from ..utils.helpers import generate_worker_id
from ..utils.logging import get_logger
from .script_executor import ScriptExecutor

logger = get_logger(__name__)


class ScrapingWorker:
    """스크래핑 워커 메인 클래스"""

    def __init__(self, worker_id: Optional[str] = None):
        """
        워커 초기화

        Args:
            worker_id: 워커 ID (None이면 자동 생성)
        """
        self.settings = get_settings()
        self.worker_id = worker_id or generate_worker_id()
        self.logger = logger
        self.is_running = False
        self.is_shutdown = False

        # 컴포넌트 초기화
        self.rabbitmq_worker: Optional[RabbitMQWorker] = None
        self.task_manager: Optional[TaskManager] = None
        self.worker_monitor: Optional[WorkerMonitor] = None
        self.script_executor: Optional[ScriptExecutor] = None

        # 시그널 핸들러 설정
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.logger.info(f"워커 초기화 완료: {self.worker_id}")

    async def initialize(self) -> None:
        """워커 컴포넌트 초기화"""
        try:
            self.logger.info(f"워커 컴포넌트 초기화 시작: {self.worker_id}")

            # 저장소 초기화
            repository = self._create_repository()

            # 캐시 매니저 초기화
            cache_manager = CacheManager(self.settings, repository)

            # 스크립트 실행기 초기화
            self.script_executor = ScriptExecutor(self.settings, cache_manager)

            # RabbitMQ 워커 연결
            self.rabbitmq_worker = RabbitMQWorker(
                self.settings,
                self._handle_task
            )
            await self.rabbitmq_worker.connect()

            # 작업 매니저 초기화
            self.task_manager = TaskManager(self.settings)
            await self.task_manager.connect()

            # 워커 모니터 초기화
            self.worker_monitor = WorkerMonitor(self.settings)
            await self.worker_monitor.connect()

            # 워커 상태 발행
            await self.worker_monitor.register_worker(
                self.worker_id,
                {
                    "status": "active",
                    "max_concurrent_tasks": self.settings.max_concurrent_tasks,
                    "current_tasks": 0
                }
            )

            self.logger.info(f"워커 초기화 완료: {self.worker_id}")

        except Exception as e:
            self.logger.error(f"워커 초기화 실패: {e}")
            raise

    def _create_repository(self):
        """저장소 인스턴스 생성"""
        if self.settings.script_repository_type == ScriptRepositoryType.GIT:
            if not self.settings.script_repository_url:
                raise ValueError("Git 저장소 사용 시 SCRIPT_REPOSITORY_URL이 필요합니다")
            return GitRepository(self.settings, self.settings.script_repository_url)
        elif self.settings.script_repository_type == ScriptRepositoryType.HTTP:
            if not self.settings.script_repository_url:
                raise ValueError("HTTP 저장소 사용 시 SCRIPT_REPOSITORY_URL이 필요합니다")
            return HttpRepository(self.settings, self.settings.script_repository_url)
        elif self.settings.script_repository_type == ScriptRepositoryType.S3:
            return S3Repository(self.settings)
        else:
            raise ValueError(f"지원하지 않는 저장소 타입: {self.settings.script_repository_type}")

    async def start(self):
        """워커 시작"""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info(f"워커 시작: {self.worker_id}")

        try:
            # 하트비트 작업 시작
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 정리 작업 시작
            cleanup_task = asyncio.create_task(self._cleanup_loop())

            # RabbitMQ 소비 시작  
            if not self.rabbitmq_worker:
                raise RuntimeError("RabbitMQ 워커가 초기화되지 않았습니다")
            consume_task = asyncio.create_task(self.rabbitmq_worker.start_consuming())

            # 메인 워커 루프
            main_task = asyncio.create_task(self._main_worker_loop())

            # 모든 작업 완료 대기
            await asyncio.gather(
                heartbeat_task,
                cleanup_task,
                consume_task,
                main_task,
                return_exceptions=True
            )

        except Exception as e:
            self.logger.error(f"워커 실행 오류: {e}")
            raise
        finally:
            await self.cleanup()

    async def _handle_task(self, request: ScrapingRequest) -> ScrapingResponse:
        """RabbitMQ 작업 처리 핸들러"""
        try:
            self.logger.info(f"작업 처리 시작: {request.request_id}")

            # 워커가 바쁜 상태인지 확인
            if not self.script_executor or self.script_executor.is_busy():
                return ScrapingResponse(
                    request_id=request.request_id,
                    status=TaskStatus.FAILED,
                    error="워커가 최대 용량에 도달했습니다",
                    completed_at=datetime.now()
                )

            # 작업 시작 알림
            await self._update_worker_task_count(1)

            # 작업 실행
            response = await self.script_executor.execute_scraping_request(request)

            # 작업 완료 이벤트 발행
            if self.task_manager:
                await self.task_manager.publish_task_completion(response)

            self.logger.info(f"작업 처리 완료: {request.request_id}")
            return response

        except Exception as e:
            self.logger.error(f"작업 처리 오류: {e}")
            # 오류 응답 반환
            return ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error=str(e),
                completed_at=datetime.now()
            )
        finally:
            # 작업 완료 후 카운트 감소
            await self._update_worker_task_count(-1)

    async def _main_worker_loop(self):
        """메인 워커 루프 (상태 모니터링)"""
        while self.is_running and not self.is_shutdown:
            try:
                # 워커 상태 점검
                if self.script_executor:
                    stats = await self.script_executor.get_execution_statistics()
                    self.logger.debug(f"워커 상태: {stats}")

                # RabbitMQ 연결 상태 확인
                if self.rabbitmq_worker and not self.rabbitmq_worker.is_connected():
                    self.logger.warning("RabbitMQ 연결 끊어짐, 재연결 시도...")
                    await self.rabbitmq_worker.reconnect()

                await asyncio.sleep(30)  # 30초마다 상태 점검

            except Exception as e:
                self.logger.error(f"워커 루프 오류: {e}")
                await asyncio.sleep(5)

    async def _heartbeat_loop(self):
        """하트비트 루프"""
        while self.is_running and not self.is_shutdown:
            try:
                # 워커 상태 정보 수집
                heartbeat_data = {
                    "status": "active",
                    "current_tasks": (
                        self.script_executor.process_manager.get_active_process_count() 
                        if self.script_executor and self.script_executor.process_manager 
                        else 0
                    ),
                    "max_tasks": self.settings.max_concurrent_tasks,
                    "last_heartbeat": datetime.now().isoformat()
                }

                if self.worker_monitor:
                    await self.worker_monitor.send_heartbeat(self.worker_id, heartbeat_data)

                await asyncio.sleep(self.settings.worker_heartbeat_interval)

            except Exception as e:
                self.logger.error(f"하트비트 오류: {e}")
                await asyncio.sleep(self.settings.worker_heartbeat_interval)

    async def _cleanup_loop(self):
        """정리 루프"""
        while self.is_running and not self.is_shutdown:
            try:
                # 스크립트 캐시 정리
                if self.script_executor:
                    await self.script_executor.cache_manager.cleanup_old_cache()

                # 비활성 워커 정리
                if self.worker_monitor:
                    await self.worker_monitor.cleanup_inactive_workers()

                await asyncio.sleep(self.settings.worker_cleanup_interval)

            except Exception as e:
                self.logger.error(f"정리 작업 오류: {e}")
                await asyncio.sleep(3600)  # 오류 시 1시간 대기

    async def _update_worker_task_count(self, delta: int):
        """워커 작업 수 업데이트"""
        try:
            # 현재 작업 수 계산
            current_tasks = 0
            if self.script_executor and self.script_executor.process_manager:
                current_tasks = self.script_executor.process_manager.get_active_process_count()

            # 워커 상태 업데이트
            status_data = {
                "status": "active",
                "current_tasks": current_tasks,
                "max_tasks": self.settings.max_concurrent_tasks
            }

            if self.worker_monitor:
                await self.worker_monitor.update_worker_status(self.worker_id, status_data)

        except Exception as e:
            self.logger.error(f"워커 상태 업데이트 오류: {e}")

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
        max_wait_time = 30
        wait_time = 0

        while wait_time < max_wait_time:
            if self.script_executor and self.script_executor.process_manager:
                active_count = self.script_executor.process_manager.get_active_process_count()
                if active_count == 0:
                    break

                self.logger.info(f"진행 중인 작업 대기 중: {active_count}개")

            await asyncio.sleep(1)
            wait_time += 1

        await self.cleanup()
        self.logger.info(f"워커 정지 완료: {self.worker_id}")

    async def cleanup(self):
        """리소스 정리"""
        try:
            # 워커 상태를 비활성으로 변경
            if self.worker_monitor:
                await self.worker_monitor.update_worker_status(
                    self.worker_id,
                    {"status": "inactive"}
                )

            # 스크립트 실행기 정리
            if self.script_executor:
                await self.script_executor.cleanup()

            # RabbitMQ 연결 종료
            if self.rabbitmq_worker:
                await self.rabbitmq_worker.disconnect()

            # 작업 매니저 정리
            if self.task_manager:
                await self.task_manager.disconnect()

            # 워커 모니터 정리
            if self.worker_monitor:
                await self.worker_monitor.disconnect()

            self.logger.info(f"워커 정리 완료: {self.worker_id}")

        except Exception as e:
            self.logger.error(f"워커 정리 오류: {e}")

    async def get_status(self) -> dict:
        """워커 상태 반환"""
        try:
            stats = await self.script_executor.get_execution_statistics() if self.script_executor else {}

            return {
                "worker_id": self.worker_id,
                "is_running": self.is_running,
                "is_shutdown": self.is_shutdown,
                "rabbitmq_connected": self.rabbitmq_worker.is_connected() if self.rabbitmq_worker else False,
                "execution_stats": stats
            }

        except Exception as e:
            self.logger.error(f"상태 조회 오류: {e}")
            return {
                "worker_id": self.worker_id,
                "is_running": self.is_running,
                "is_shutdown": self.is_shutdown,
                "error": str(e)
            }


async def main():
    """워커 메인 함수"""
    worker = ScrapingWorker()

    try:
        await worker.initialize()
        await worker.start()
    except KeyboardInterrupt:
        logger.info("워커 종료 요청")
    except Exception as e:
        logger.error(f"워커 실행 오류: {e}")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main()) 