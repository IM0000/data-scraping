#!/usr/bin/env python3
"""
워커 시스템 사용 예제

ScrapingWorker의 초기화, 시작, 정지 과정을 보여주는 예제입니다.
"""

import asyncio
import logging
import signal
from typing import Optional

from src.worker.worker_main import ScrapingWorker
from src.config.settings import get_settings


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WorkerManager:
    """워커 관리자 클래스"""

    def __init__(self, worker_count: int = 1):
        """
        워커 매니저 초기화

        Args:
            worker_count: 실행할 워커 수
        """
        self.worker_count = worker_count
        self.workers: list[ScrapingWorker] = []
        self.is_running = False

    async def start_workers(self):
        """워커들 시작"""
        logger.info(f"{self.worker_count}개의 워커를 시작합니다...")

        try:
            # 워커들 생성 및 초기화
            for i in range(self.worker_count):
                worker = ScrapingWorker(f"worker-{i+1}")
                await worker.initialize()
                self.workers.append(worker)

            # 워커들 동시 시작
            worker_tasks = [
                asyncio.create_task(worker.start())
                for worker in self.workers
            ]

            self.is_running = True
            logger.info("모든 워커가 시작되었습니다")

            # 모든 워커 완료 대기
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"워커 시작 오류: {e}")
            await self.stop_workers()

    async def stop_workers(self):
        """워커들 정지"""
        if not self.workers:
            return

        logger.info("워커들을 정지합니다...")

        # 모든 워커 정지
        stop_tasks = [
            asyncio.create_task(worker.stop())
            for worker in self.workers
        ]

        await asyncio.gather(*stop_tasks, return_exceptions=True)

        self.workers.clear()
        self.is_running = False
        logger.info("모든 워커가 정지되었습니다")

    async def get_worker_status(self) -> list:
        """모든 워커의 상태 반환"""
        if not self.workers:
            return []

        status_tasks = [
            worker.get_status()
            for worker in self.workers
        ]

        return await asyncio.gather(*status_tasks, return_exceptions=True)


async def single_worker_example():
    """단일 워커 사용 예제"""
    logger.info("=== 단일 워커 예제 시작 ===")

    # 워커 생성 및 초기화
    worker = ScrapingWorker("example-worker")

    try:
        # 워커 초기화
        await worker.initialize()
        logger.info("워커 초기화 완료")

        # 워커 상태 확인
        status = await worker.get_status()
        logger.info(f"워커 상태: {status}")

        # 워커 시작 (백그라운드에서 실행)
        worker_task = asyncio.create_task(worker.start())

        # 10초 대기
        logger.info("10초 동안 실행...")
        await asyncio.sleep(10)

        # 워커 정지
        await worker.stop()

        # 작업 완료 대기
        worker_task.cancel()

        logger.info("단일 워커 예제 완료")

    except Exception as e:
        logger.error(f"단일 워커 예제 오류: {e}")
        await worker.stop()


async def multiple_worker_example():
    """다중 워커 사용 예제"""
    logger.info("=== 다중 워커 예제 시작 ===")

    # 워커 매니저 생성
    manager = WorkerManager(worker_count=3)

    try:
        # 워커들 시작 (백그라운드)
        manager_task = asyncio.create_task(manager.start_workers())

        # 15초 대기
        logger.info("15초 동안 실행...")
        await asyncio.sleep(15)

        # 워커 상태 확인
        statuses = await manager.get_worker_status()
        for i, status in enumerate(statuses):
            logger.info(f"워커 {i+1} 상태: {status}")

        # 워커들 정지
        await manager.stop_workers()

        # 매니저 작업 취소
        manager_task.cancel()

        logger.info("다중 워커 예제 완료")

    except Exception as e:
        logger.error(f"다중 워커 예제 오류: {e}")
        await manager.stop_workers()


async def worker_with_monitoring_example():
    """모니터링이 포함된 워커 예제"""
    logger.info("=== 모니터링 워커 예제 시작 ===")

    worker = ScrapingWorker("monitoring-worker")

    try:
        await worker.initialize()

        # 백그라운드에서 워커 실행
        worker_task = asyncio.create_task(worker.start())

        # 30초 동안 5초마다 상태 모니터링
        for i in range(6):
            await asyncio.sleep(5)

            status = await worker.get_status()
            logger.info(f"모니터링 {i+1}/6: {status}")

            # 실행 통계 확인 (script_executor가 있을 때만)
            if worker.script_executor:
                stats = await worker.script_executor.get_execution_statistics()
                logger.info(f"실행 통계: {stats}")

        # 워커 정지
        await worker.stop()
        worker_task.cancel()

        logger.info("모니터링 워커 예제 완료")

    except Exception as e:
        logger.error(f"모니터링 워커 예제 오류: {e}")
        await worker.stop()


async def graceful_shutdown_example():
    """우아한 종료 예제"""
    logger.info("=== 우아한 종료 예제 시작 ===")

    manager = WorkerManager(worker_count=2)
    shutdown_requested = False

    def signal_handler():
        nonlocal shutdown_requested
        logger.info("종료 시그널 수신")
        shutdown_requested = True

    # 시그널 핸들러 등록
    loop = asyncio.get_event_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, signal_handler)

    try:
        # 워커들 시작
        manager_task = asyncio.create_task(manager.start_workers())

        # 종료 요청까지 대기
        while not shutdown_requested:
            await asyncio.sleep(1)

            # 워커 상태 확인
            if manager.is_running:
                statuses = await manager.get_worker_status()
                active_workers = sum(1 for status in statuses if status.get("is_running", False))
                logger.info(f"활성 워커 수: {active_workers}")

        logger.info("우아한 종료 시작...")

        # 워커들 정지
        await manager.stop_workers()
        manager_task.cancel()

        logger.info("우아한 종료 완료")

    except Exception as e:
        logger.error(f"우아한 종료 예제 오류: {e}")
        await manager.stop_workers()


async def main():
    """메인 함수"""
    logger.info("워커 시스템 예제를 시작합니다")

    # 설정 확인
    settings = get_settings()
    logger.info(f"RabbitMQ URL: {settings.rabbitmq_url}")
    logger.info(f"스크립트 저장소: {settings.script_repository_type}")

    try:
        # 예제 실행
        await single_worker_example()
        await asyncio.sleep(2)

        await multiple_worker_example()
        await asyncio.sleep(2)

        await worker_with_monitoring_example()
        await asyncio.sleep(2)

        # 우아한 종료 예제는 시그널이 필요하므로 주석 처리
        # await graceful_shutdown_example()

        logger.info("모든 예제가 완료되었습니다")

    except KeyboardInterrupt:
        logger.info("사용자 중단 요청")
    except Exception as e:
        logger.error(f"예제 실행 오류: {e}")


if __name__ == "__main__":
    # 이벤트 루프 실행
    asyncio.run(main()) 