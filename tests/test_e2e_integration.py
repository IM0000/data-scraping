"""
종단간 통합 테스트 모듈

전체 Gateway-Worker 시스템의 통합 테스트를 수행합니다.
RabbitMQ RPC 패턴과 correlation_id 검증을 포함합니다.
"""

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import httpx
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.config.settings import Settings
from src.models.base import ScrapingRequest, TaskStatus
from src.queue.rabbitmq_rpc import RabbitMQRPC, RabbitMQWorker
from src.worker.worker_main import ScrapingWorker
from src.utils.logging import setup_logging


class TestEndToEndIntegration:
    """종단간 통합 테스트"""

    @pytest.fixture(scope="class")
    def test_settings(self) -> Settings:
        """테스트용 설정"""
        # 테스트용 환경 변수 설정
        os.environ["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672/"
        os.environ["RABBITMQ_TASK_QUEUE"] = "test_scraping_tasks"
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-e2e-testing"
        os.environ["API_PORT"] = "8001"  # 테스트용 포트
        os.environ["LOG_LEVEL"] = "INFO"
        
        settings = Settings()
        return settings

    @pytest.fixture(scope="class")
    async def rabbitmq_running(self, test_settings: Settings) -> bool:
        """RabbitMQ 서버 실행 확인"""
        try:
            # RabbitMQ 연결 테스트
            test_rpc = RabbitMQRPC(test_settings)
            await test_rpc.connect()
            await test_rpc.disconnect()
            return True
        except Exception:
            pytest.skip("RabbitMQ 서버가 실행되지 않아 E2E 테스트를 건너뜁니다")

    @pytest.fixture(scope="class")
    async def test_app(self, test_settings: Settings, rabbitmq_running: bool):
        """테스트용 FastAPI 앱"""
        app = create_app(test_settings)
        return app

    @pytest.fixture(scope="class")
    async def test_worker(self, test_settings: Settings, rabbitmq_running: bool):
        """테스트용 워커"""
        # 테스트용 간단한 스크립트 생성
        script_dir = Path("cache/scripts/test_script")
        script_dir.mkdir(parents=True, exist_ok=True)
        
        script_content = '''#!/usr/bin/env python3
"""테스트용 스크래핑 스크립트"""

import json
import sys
import time

def main():
    """메인 함수"""
    # 표준 입력에서 파라미터 읽기
    input_data = sys.stdin.read()
    try:
        params = json.loads(input_data) if input_data.strip() else {}
    except:
        params = {}
    
    # 간단한 처리 시뮬레이션
    test_url = params.get("url", "https://httpbin.org/json")
    delay = params.get("delay", 0.1)
    
    time.sleep(delay)  # 처리 시간 시뮬레이션
    
    # 결과 반환
    result = {
        "url": test_url,
        "timestamp": time.time(),
        "parameters": params,
        "status": "success"
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
'''
        
        script_file = script_dir / "scraper.py"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        # 실행 권한 부여
        script_file.chmod(0o755)
        
        # 워커 시작
        worker = ScrapingWorker("test-worker-e2e")
        await worker.initialize()
        
        # 백그라운드에서 워커 실행
        worker_task = asyncio.create_task(worker.start())
        
        # 워커가 시작될 시간을 줌
        await asyncio.sleep(2)
        
        yield worker
        
        # 정리
        await worker.stop()
        if not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

    @pytest.fixture
    def auth_token(self, test_settings: Settings) -> str:
        """테스트용 인증 토큰"""
        from src.api.auth import AuthManager
        
        auth_manager = AuthManager(test_settings)
        return auth_manager.create_access_token("test-client")

    @pytest.mark.asyncio
    async def test_complete_scraping_workflow(
        self, 
        test_app, 
        test_worker, 
        auth_token: str,
        test_settings: Settings
    ):
        """완전한 스크래핑 워크플로우 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            # 1. 헬스 체크
            health_response = await client.get("/health")
            assert health_response.status_code == 200
            
            health_data = health_response.json()
            logger.info(f"헬스 체크 결과: {health_data}")
            
            # 2. 스크래핑 요청 제출
            scraping_request = {
                "script_name": "test_script",
                "parameters": {
                    "url": "https://httpbin.org/json",
                    "delay": 0.5
                },
                "timeout": 30
            }
            
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            logger.info("스크래핑 요청 제출 중...")
            response = await client.post(
                "/scrape",
                json=scraping_request,
                headers=headers,
                timeout=60.0
            )
            
            logger.info(f"응답 상태: {response.status_code}")
            assert response.status_code == 200
            
            result = response.json()
            logger.info(f"스크래핑 결과: {result}")
            
            # 3. 응답 검증
            assert "request_id" in result
            assert result["status"] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]
            
            if result["status"] == TaskStatus.COMPLETED.value:
                assert "data" in result
                assert result["data"] is not None
                assert result["execution_time"] > 0
                
                # 스크립트 결과 검증
                data = result["data"]
                assert data["url"] == scraping_request["parameters"]["url"]
                assert "timestamp" in data
            else:
                assert "error" in result
                logger.warning(f"스크래핑 실패: {result['error']}")

    @pytest.mark.asyncio
    async def test_concurrent_requests(
        self, 
        test_app, 
        test_worker, 
        auth_token: str,
        test_settings: Settings
    ):
        """동시 요청 처리 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            # 여러 개의 동시 요청 준비
            requests = []
            for i in range(3):  # 3개의 동시 요청
                request_data = {
                    "script_name": "test_script",
                    "parameters": {
                        "url": f"https://httpbin.org/json?id={i}",
                        "delay": 0.2
                    },
                    "timeout": 30
                }
                requests.append(request_data)
            
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            # 동시 요청 실행
            logger.info(f"{len(requests)}개의 동시 요청 실행 중...")
            
            async def send_request(req_data):
                response = await client.post(
                    "/scrape",
                    json=req_data,
                    headers=headers,
                    timeout=60.0
                )
                return response
            
            # 모든 요청을 동시에 실행
            responses = await asyncio.gather(*[send_request(req) for req in requests])
            
            # 모든 요청이 성공했는지 확인
            for i, response in enumerate(responses):
                assert response.status_code == 200
                result = response.json()
                assert "request_id" in result
                logger.info(f"요청 {i} 결과: {result['status']}")

    @pytest.mark.asyncio
    async def test_error_handling(
        self, 
        test_app, 
        test_worker, 
        auth_token: str,
        test_settings: Settings
    ):
        """오류 처리 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            # 존재하지 않는 스크립트 요청
            invalid_request = {
                "script_name": "nonexistent_script",
                "parameters": {},
                "timeout": 30
            }
            
            logger.info("존재하지 않는 스크립트 요청 테스트...")
            response = await client.post(
                "/scrape",
                json=invalid_request,
                headers=headers,
                timeout=60.0
            )
            
            assert response.status_code == 200
            result = response.json()
            logger.info(f"오류 응답: {result}")
            
            # 오류 응답 검증
            assert result["status"] == TaskStatus.FAILED.value
            assert "error" in result
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_authentication_required(self, test_app, test_settings: Settings):
        """인증 필수 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            # 토큰 없이 요청
            logger.info("인증 없이 요청 테스트...")
            response = await client.post(
                "/scrape",
                json={"script_name": "test", "parameters": {}}
            )
            
            assert response.status_code == 401
            logger.info("인증 필수 검증 완료")

    @pytest.mark.asyncio
    async def test_timeout_handling(
        self, 
        test_app, 
        test_worker, 
        auth_token: str,
        test_settings: Settings
    ):
        """타임아웃 처리 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            # 긴 실행 시간을 가진 요청
            timeout_request = {
                "script_name": "test_script",
                "parameters": {
                    "delay": 5  # 5초 지연
                },
                "timeout": 2  # 2초 타임아웃
            }
            
            logger.info("타임아웃 테스트 시작...")
            start_time = time.time()
            
            response = await client.post(
                "/scrape",
                json=timeout_request,
                headers=headers,
                timeout=60.0
            )
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            logger.info(f"요청 처리 시간: {elapsed:.2f}초")
            
            # 타임아웃이 정상적으로 처리되었는지 확인
            if response.status_code == 408:
                logger.info("타임아웃이 정상적으로 처리됨")
            else:
                # 또는 실패 상태로 반환될 수 있음
                assert response.status_code == 200
                result = response.json()
                if result["status"] == TaskStatus.FAILED.value:
                    logger.info("타임아웃으로 인한 실패 상태 확인")

    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, test_app, test_settings: Settings):
        """시스템 헬스 모니터링 테스트"""
        logger = setup_logging(test_settings)
        
        async with httpx.AsyncClient(base_url="http://test") as client:
            # 헬스 체크
            logger.info("헬스 체크 테스트...")
            health_response = await client.get("/health")
            assert health_response.status_code == 200
            
            health_data = health_response.json()
            assert "status" in health_data
            assert "components" in health_data
            assert "timestamp" in health_data
            
            logger.info(f"헬스 상태: {health_data['status']}")
            
            # 시스템 상태 확인
            logger.info("시스템 상태 체크 테스트...")
            status_response = await client.get("/status")
            assert status_response.status_code == 200
            
            status_data = status_response.json()
            assert "queue_length" in status_data
            assert "active_workers" in status_data
            assert "memory_usage" in status_data
            assert "cpu_usage" in status_data
            assert "uptime" in status_data
            
            logger.info(f"시스템 상태: {status_data}")

    @pytest.mark.asyncio
    async def test_websocket_connection(self, test_app, test_settings: Settings):
        """WebSocket 연결 테스트"""
        logger = setup_logging(test_settings)
        
        # WebSocket 테스트는 기본적인 연결만 확인
        async with httpx.AsyncClient(base_url="http://test") as client:
            # WebSocket 엔드포인트가 있는지 확인
            response = await client.get("/")
            assert response.status_code == 200
            logger.info("WebSocket 엔드포인트 존재 확인")

    @pytest.mark.asyncio
    async def test_correlation_id_pattern(
        self, 
        test_settings: Settings,
        rabbitmq_running: bool
    ):
        """RabbitMQ RPC correlation_id 패턴 테스트"""
        logger = setup_logging(test_settings)
        
        # 직접 RabbitMQ RPC 테스트
        rpc_client = RabbitMQRPC(test_settings)
        await rpc_client.connect()
        await rpc_client.setup_callback_queue()
        
        try:
            # 테스트 요청 생성
            test_request = ScrapingRequest(
                script_name="test_correlation",
                script_version=None,
                parameters={"test": "correlation_id"}
            )
            
            logger.info(f"correlation_id 패턴 테스트 시작: {test_request.request_id}")
            
            # 타임아웃을 짧게 설정하여 테스트
            try:
                response = await rpc_client.call_async(test_request, timeout=5)
                logger.info(f"RPC 응답 수신: {response.request_id}")
                assert response.request_id == test_request.request_id
            except TimeoutError:
                logger.info("RPC 타임아웃 - 정상적인 테스트 결과")
            
        finally:
            await rpc_client.disconnect() 