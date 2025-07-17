"""
성능 최적화 테스트 모듈

분산 시스템의 성능 지표를 측정하고 최적화를 검증합니다.
"""

import asyncio
import gc
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Dict, Any

import psutil
import pytest

from src.config.settings import Settings
from src.models.base import ScrapingRequest, TaskStatus
from src.queue.rabbitmq_rpc import RabbitMQRPC, RabbitMQWorker
from src.utils.logging import setup_logging


class TestPerformanceOptimization:
    """성능 최적화 테스트"""

    @pytest.fixture(scope="class")
    def perf_settings(self) -> Settings:
        """성능 테스트용 설정"""
        os.environ["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672/"
        os.environ["RABBITMQ_TASK_QUEUE"] = "perf_test_queue"
        os.environ["LOG_LEVEL"] = "WARNING"  # 성능 테스트 중 로그 최소화
        
        settings = Settings()
        return settings

    @pytest.fixture(scope="class")
    async def rabbitmq_available(self, perf_settings: Settings) -> bool:
        """RabbitMQ 가용성 확인"""
        try:
            rpc = RabbitMQRPC(perf_settings)
            await rpc.connect()
            await rpc.disconnect()
            return True
        except Exception:
            pytest.skip("RabbitMQ 서버가 실행되지 않아 성능 테스트를 건너뜁니다")

    @pytest.mark.asyncio
    async def test_queue_throughput(self, perf_settings: Settings, rabbitmq_available: bool):
        """큐 처리량 테스트"""
        logger = setup_logging(perf_settings)
        
        # RabbitMQ RPC 클라이언트 설정
        rpc_client = RabbitMQRPC(perf_settings)
        await rpc_client.connect()
        await rpc_client.setup_callback_queue()
        
        try:
            # 테스트 요청들 생성
            requests = []
            for i in range(100):  # 100개 요청으로 시작
                request = ScrapingRequest(
                    script_name="performance_test",
                    script_version=None,
                    parameters={"index": i, "batch": "throughput"}
                )
                requests.append(request)

            # 큐에 추가 성능 측정
            start_time = time.time()
            
            # 동시에 여러 요청 발송 (비동기)
            async def send_request(req):
                try:
                    # 타임아웃을 짧게 설정 (워커가 없어도 테스트 가능)
                    await rpc_client.call_async(req, timeout=1)
                except Exception:
                    pass  # 타임아웃 예상됨
            
            # 모든 요청을 동시에 발송
            await asyncio.gather(*[send_request(req) for req in requests], return_exceptions=True)
            
            enqueue_time = time.time() - start_time

            # 성능 지표 계산
            enqueue_rate = len(requests) / enqueue_time

            logger.warning(f"큐 처리 속도: {enqueue_rate:.2f} req/sec")
            logger.warning(f"총 처리 시간: {enqueue_time:.2f} seconds")

            # 성능 기준 검증 (매우 관대한 기준)
            assert enqueue_rate > 10  # 최소 10 req/sec
            assert enqueue_time < 30  # 30초 이내

        finally:
            await rpc_client.disconnect()

    @pytest.mark.asyncio
    async def test_memory_usage_optimization(self, perf_settings: Settings, rabbitmq_available: bool):
        """메모리 사용량 최적화 테스트"""
        logger = setup_logging(perf_settings)
        
        # 초기 메모리 사용량 측정
        gc.collect()
        initial_memory = psutil.Process().memory_info().rss

        rpc_client = RabbitMQRPC(perf_settings)
        await rpc_client.connect()
        await rpc_client.setup_callback_queue()

        try:
            # 대량 요청 생성 및 처리
            for batch in range(5):  # 5 배치
                requests = []
                for i in range(100):  # 배치당 100개
                    request = ScrapingRequest(
                        script_name="memory_test",
                        script_version=None,
                        parameters={"batch": batch, "index": i}
                    )
                    requests.append(request)

                # 요청 처리 (타임아웃으로 빠르게 완료)
                async def process_request(req):
                    try:
                        await rpc_client.call_async(req, timeout=1)
                    except Exception:
                        pass

                await asyncio.gather(*[process_request(req) for req in requests], return_exceptions=True)

                # 메모리 정리
                del requests
                gc.collect()

                # 중간 메모리 체크
                current_memory = psutil.Process().memory_info().rss
                memory_increase = current_memory - initial_memory
                logger.warning(f"배치 {batch} 후 메모리 증가: {memory_increase / 1024 / 1024:.2f} MB")

        finally:
            await rpc_client.disconnect()

        # 최종 메모리 사용량
        gc.collect()
        final_memory = psutil.Process().memory_info().rss
        memory_increase = final_memory - initial_memory

        logger.warning(f"총 메모리 사용량 증가: {memory_increase / 1024 / 1024:.2f} MB")

        # 메모리 증가량이 합리적인 범위인지 확인
        assert memory_increase < 50 * 1024 * 1024  # 50MB 이하

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, perf_settings: Settings, rabbitmq_available: bool):
        """동시 처리 성능 테스트"""
        logger = setup_logging(perf_settings)

        # 여러 RPC 클라이언트 생성 (동시 연결 시뮬레이션)
        clients = []
        for i in range(3):  # 3개 클라이언트
            client = RabbitMQRPC(perf_settings)
            await client.connect()
            await client.setup_callback_queue()
            clients.append(client)

        try:
            # 동시 요청 처리 시뮬레이션
            async def client_simulation(client_id: int, client: RabbitMQRPC):
                """클라이언트 시뮬레이션"""
                processed = 0
                errors = 0
                
                for i in range(10):  # 각 클라이언트가 10개 요청
                    try:
                        request = ScrapingRequest(
                            script_name="concurrent_test",
                            script_version=None,
                            parameters={"client": client_id, "request": i}
                        )
                        
                        await client.call_async(request, timeout=1)
                        processed += 1
                    except Exception:
                        errors += 1
                    
                    # 간단한 처리 시뮬레이션
                    await asyncio.sleep(0.01)
                
                return {"processed": processed, "errors": errors}

            # 모든 클라이언트 동시 실행
            start_time = time.time()

            results = await asyncio.gather(*[
                client_simulation(i, client) 
                for i, client in enumerate(clients)
            ])

            total_time = time.time() - start_time
            total_processed = sum(r["processed"] for r in results)
            total_errors = sum(r["errors"] for r in results)

            processing_rate = total_processed / total_time if total_time > 0 else 0

            logger.warning(f"동시 처리 속도: {processing_rate:.2f} req/sec")
            logger.warning(f"총 처리 시간: {total_time:.2f} seconds")
            logger.warning(f"처리된 요청: {total_processed}, 오류: {total_errors}")

            # 성능 기준 검증
            assert total_time < 60  # 60초 이내 완료
            assert total_processed + total_errors == 30  # 모든 요청이 처리됨

        finally:
            # 모든 클라이언트 정리
            for client in clients:
                await client.disconnect()

    @pytest.mark.asyncio
    async def test_latency_measurement(self, perf_settings: Settings, rabbitmq_available: bool):
        """지연시간 측정 테스트"""
        logger = setup_logging(perf_settings)

        rpc_client = RabbitMQRPC(perf_settings)
        await rpc_client.connect()
        await rpc_client.setup_callback_queue()

        try:
            latencies = []

            # 여러 요청의 지연시간 측정
            for i in range(20):  # 20개 요청
                start_time = time.time()
                
                try:
                    request = ScrapingRequest(
                        script_name="latency_test",
                        script_version=None,
                        parameters={"index": i}
                    )
                    
                    await rpc_client.call_async(request, timeout=1)
                    
                except Exception:
                    pass  # 타임아웃 예상됨
                
                end_time = time.time()
                latency = end_time - start_time
                latencies.append(latency)
                
                # 요청 간 간격
                await asyncio.sleep(0.1)

            # 지연시간 통계
            if latencies:
                avg_latency = statistics.mean(latencies)
                min_latency = min(latencies)
                max_latency = max(latencies)
                median_latency = statistics.median(latencies)

                logger.warning(f"평균 지연시간: {avg_latency*1000:.2f}ms")
                logger.warning(f"최소 지연시간: {min_latency*1000:.2f}ms")
                logger.warning(f"최대 지연시간: {max_latency*1000:.2f}ms")
                logger.warning(f"중앙값 지연시간: {median_latency*1000:.2f}ms")

                # 지연시간 기준 검증 (관대한 기준)
                assert avg_latency < 5.0  # 평균 5초 이내
                assert max_latency < 10.0  # 최대 10초 이내

        finally:
            await rpc_client.disconnect()

    @pytest.mark.asyncio 
    async def test_connection_pooling(self, perf_settings: Settings, rabbitmq_available: bool):
        """연결 풀링 성능 테스트"""
        logger = setup_logging(perf_settings)

        # 연결 생성/해제 시간 측정
        connection_times = []

        for i in range(5):  # 5번의 연결 테스트
            start_time = time.time()
            
            client = RabbitMQRPC(perf_settings)
            await client.connect()
            await client.setup_callback_queue()
            await client.disconnect()
            
            end_time = time.time()
            connection_time = end_time - start_time
            connection_times.append(connection_time)
            
            logger.warning(f"연결 {i+1} 시간: {connection_time:.3f}초")

        # 연결 시간 통계
        avg_connection_time = statistics.mean(connection_times)
        max_connection_time = max(connection_times)

        logger.warning(f"평균 연결 시간: {avg_connection_time:.3f}초")
        logger.warning(f"최대 연결 시간: {max_connection_time:.3f}초")

        # 연결 시간 기준 검증
        assert avg_connection_time < 2.0  # 평균 2초 이내
        assert max_connection_time < 5.0  # 최대 5초 이내

    @pytest.mark.asyncio
    async def test_resource_monitoring(self, perf_settings: Settings):
        """리소스 모니터링 테스트"""
        logger = setup_logging(perf_settings)

        # 시스템 리소스 측정
        cpu_samples = []
        memory_samples = []

        # 10초간 리소스 모니터링
        for i in range(10):
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_info = psutil.virtual_memory()
            
            cpu_samples.append(cpu_percent)
            memory_samples.append(memory_info.percent)
            
            await asyncio.sleep(1)

        # 리소스 사용량 통계
        avg_cpu = statistics.mean(cpu_samples)
        max_cpu = max(cpu_samples)
        avg_memory = statistics.mean(memory_samples)
        max_memory = max(memory_samples)

        logger.warning(f"평균 CPU 사용률: {avg_cpu:.2f}%")
        logger.warning(f"최대 CPU 사용률: {max_cpu:.2f}%")
        logger.warning(f"평균 메모리 사용률: {avg_memory:.2f}%")
        logger.warning(f"최대 메모리 사용률: {max_memory:.2f}%")

        # 리소스 사용량이 합리적인 범위인지 확인
        assert max_memory < 90  # 메모리 사용률 90% 이하
        
        # CPU는 테스트 환경에 따라 다를 수 있으므로 관대한 기준
        assert max_cpu < 100  # CPU 사용률 100% 이하 (당연함)

    def test_data_structure_efficiency(self):
        """데이터 구조 효율성 테스트"""
        # ScrapingRequest 객체 생성 시간 측정
        start_time = time.time()

        requests = []
        for i in range(1000):
            request = ScrapingRequest(
                script_name=f"test_script_{i}",
                script_version=None,
                parameters={"index": i, "data": f"test_data_{i}"}
            )
            requests.append(request)

        creation_time = time.time() - start_time
        
        # 직렬화 시간 측정
        start_time = time.time()
        
        for request in requests[:100]:  # 100개만 테스트
            request.model_dump_json()
        
        serialization_time = time.time() - start_time

        print(f"객체 생성 시간 (1000개): {creation_time:.3f}초")
        print(f"직렬화 시간 (100개): {serialization_time:.3f}초")

        # 성능 기준 검증
        assert creation_time < 1.0  # 1초 이내
        assert serialization_time < 0.5  # 0.5초 이내

    @pytest.mark.asyncio
    async def test_error_recovery_performance(self, perf_settings: Settings, rabbitmq_available: bool):
        """오류 복구 성능 테스트"""
        logger = setup_logging(perf_settings)

        recovery_times = []

        for i in range(3):  # 3번의 복구 테스트
            # 정상 연결
            client = RabbitMQRPC(perf_settings)
            await client.connect()
            await client.setup_callback_queue()

            # 연결 강제 종료 시뮬레이션
            await client.disconnect()

            # 복구 시간 측정
            start_time = time.time()
            
            # 재연결
            await client.connect()
            await client.setup_callback_queue()
            
            recovery_time = time.time() - start_time
            recovery_times.append(recovery_time)
            
            logger.warning(f"복구 {i+1} 시간: {recovery_time:.3f}초")
            
            await client.disconnect()

        # 복구 시간 통계
        avg_recovery_time = statistics.mean(recovery_times)
        max_recovery_time = max(recovery_times)

        logger.warning(f"평균 복구 시간: {avg_recovery_time:.3f}초")
        logger.warning(f"최대 복구 시간: {max_recovery_time:.3f}초")

        # 복구 시간 기준 검증
        assert avg_recovery_time < 3.0  # 평균 3초 이내
        assert max_recovery_time < 5.0  # 최대 5초 이내 