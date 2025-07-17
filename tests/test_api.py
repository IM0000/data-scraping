"""
API 모듈 테스트

Gateway API의 엔드포인트들을 테스트합니다.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.auth import AuthManager
from src.api.models import (
    ScrapingRequestAPI, 
    AuthTokenRequest,
    SystemStatusResponse
)
from src.config.settings import Settings
from src.models.base import ScrapingResponse, TaskStatus


class TestAPIAuth:
    """API 인증 테스트"""
    
    def test_토큰_생성_성공(self):
        """JWT 토큰 생성 성공 테스트"""
        settings = Settings()
        auth_manager = AuthManager(settings)
        
        client_id = "test_client"
        token = auth_manager.create_access_token(client_id)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_토큰_검증_성공(self):
        """JWT 토큰 검증 성공 테스트"""
        settings = Settings()
        auth_manager = AuthManager(settings)
        
        client_id = "test_client"
        token = auth_manager.create_access_token(client_id)
        
        payload = auth_manager.verify_token(token)
        
        assert payload["client_id"] == client_id
        assert payload["type"] == "access"
    
    def test_만료된_토큰_검증_실패(self):
        """만료된 토큰 검증 실패 테스트"""
        settings = Settings()
        auth_manager = AuthManager(settings)
        
        client_id = "test_client"
        # 이미 만료된 토큰 생성 (음수 시간)
        expired_token = auth_manager.create_access_token(
            client_id, 
            expires_delta=timedelta(seconds=-1)
        )
        
        # 검증 시 HTTPException 발생해야 함
        with pytest.raises(Exception):
            auth_manager.verify_token(expired_token)
    
    def test_클라이언트_자격증명_검증(self):
        """클라이언트 자격 증명 검증 테스트"""
        settings = Settings()
        auth_manager = AuthManager(settings)
        
        # 유효한 클라이언트 ID
        assert auth_manager.validate_client_credentials("valid_client") is True
        
        # 빈 클라이언트 ID
        assert auth_manager.validate_client_credentials("") is False
        
        # 너무 긴 클라이언트 ID
        long_client_id = "a" * 100
        assert auth_manager.validate_client_credentials(long_client_id) is False


class TestAPIModels:
    """API 모델 테스트"""
    
    def test_스크래핑_요청_모델_검증(self):
        """스크래핑 요청 모델 검증 테스트"""
        # 유효한 요청
        valid_request = ScrapingRequestAPI(
            script_name="test_script",
            script_version="1.0.0",
            parameters={"url": "https://example.com"},
            timeout=300
        )
        
        assert valid_request.script_name == "test_script"
        assert valid_request.parameters["url"] == "https://example.com"
        assert valid_request.timeout == 300
    
    def test_스크래핑_요청_유효성_검증_실패(self):
        """스크래핑 요청 유효성 검증 실패 테스트"""
        # 빈 스크립트 이름
        with pytest.raises(ValueError):
            ScrapingRequestAPI(
                script_name="",
                script_version="1.0.0",
                parameters={}
            )
        
        # 잘못된 문자가 포함된 스크립트 이름
        with pytest.raises(ValueError):
            ScrapingRequestAPI(
                script_name="invalid/script",
                script_version="1.0.0",
                parameters={}
            )
        
        # 타임아웃이 범위를 벗어남
        with pytest.raises(ValueError):
            ScrapingRequestAPI(
                script_name="test_script",
                script_version="1.0.0",
                parameters={},
                timeout=0  # 최소 1초
            )
    
    def test_인증_토큰_요청_모델(self):
        """인증 토큰 요청 모델 테스트"""
        # 유효한 요청
        valid_request = AuthTokenRequest(client_id="test_client", client_secret="test_secret")
        assert valid_request.client_id == "test_client"
        
        # 빈 클라이언트 ID
        with pytest.raises(ValueError):
            AuthTokenRequest(client_id="", client_secret="test_secret")


class TestAPIEndpoints:
    """API 엔드포인트 테스트"""
    
    @pytest.fixture
    def client(self):
        """테스트 클라이언트 생성"""
        # 테스트용 설정
        test_settings = Settings(
            jwt_secret_key="test-secret-key",
            rabbitmq_url="amqp://test:test@localhost:5672/"
        )
        
        app = create_app(test_settings)
        return TestClient(app)
    
    @pytest.fixture
    def auth_token(self, client):
        """테스트용 인증 토큰 생성"""
        # 토큰 발급 요청
        response = client.post(
            "/auth/token",
            json={"client_id": "test_client"}
        )
        
        if response.status_code == 200:
            return response.json()["access_token"]
        return None
    
    def test_루트_엔드포인트(self, client):
        """루트 엔드포인트 테스트"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "스크래핑 시스템 API"
        assert data["version"] == "1.0.0"
        assert data["status"] == "running"
    
    def test_토큰_발급_엔드포인트(self, client):
        """토큰 발급 엔드포인트 테스트"""
        response = client.post(
            "/auth/token",
            json={"client_id": "test_client"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["client_id"] == "test_client"
    
    def test_토큰_발급_실패(self, client):
        """토큰 발급 실패 테스트"""
        # 빈 클라이언트 ID
        response = client.post(
            "/auth/token",
            json={"client_id": ""}
        )
        
        assert response.status_code == 422  # 유효성 검증 실패
    
    @patch('src.api.main.rabbitmq_rpc')
    def test_스크래핑_요청_성공(self, mock_rabbitmq, client, auth_token):
        """스크래핑 요청 성공 테스트"""
        if not auth_token:
            pytest.skip("인증 토큰 생성 실패")
        
        # Mock RabbitMQ RPC 응답
        mock_response = ScrapingResponse(
            request_id="test-request-id",
            status=TaskStatus.COMPLETED,
            data={"result": "success"},
            execution_time=1.5,
            completed_at=datetime.now()
        )
        mock_rabbitmq.call_async = AsyncMock(return_value=mock_response)
        
        # 스크래핑 요청
        response = client.post(
            "/scrape",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "script_name": "test_script",
                "parameters": {"url": "https://example.com"},
                "timeout": 300
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["data"]["result"] == "success"
    
    def test_스크래핑_요청_인증_실패(self, client):
        """스크래핑 요청 인증 실패 테스트"""
        # 인증 헤더 없이 요청
        response = client.post(
            "/scrape",
            json={
                "script_name": "test_script",
                "parameters": {},
                "timeout": 300
            }
        )
        
        assert response.status_code == 403  # 인증 실패
    
    def test_시스템_상태_조회(self, client):
        """시스템 상태 조회 테스트"""
        response = client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "queue_length" in data
        assert "active_workers" in data
        assert "uptime" in data
    
    def test_헬스_체크(self, client):
        """헬스 체크 테스트"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert "version" in data


class TestAPIWebSocket:
    """WebSocket API 테스트"""
    
    @pytest.fixture
    def client(self):
        """테스트 클라이언트 생성"""
        test_settings = Settings()
        app = create_app(test_settings)
        return TestClient(app)
    
    def test_웹소켓_연결(self, client):
        """WebSocket 연결 테스트"""
        with client.websocket_connect("/ws/test-connection") as websocket:
            # 환영 메시지 수신
            data = websocket.receive_json()
            
            assert data["type"] == "welcome"
            assert data["data"]["connection_id"] == "test-connection"
            assert "WebSocket 연결이 성공했습니다" in data["data"]["message"]
    
    def test_웹소켓_핑퐁(self, client):
        """WebSocket 핑-퐁 테스트"""
        with client.websocket_connect("/ws/test-connection") as websocket:
            # 환영 메시지 수신
            welcome = websocket.receive_json()
            assert welcome["type"] == "welcome"
            
            # 핑 메시지 전송
            websocket.send_json({"type": "ping"})
            
            # 퐁 메시지 수신
            pong = websocket.receive_json()
            assert pong["type"] == "pong"
            assert "timestamp" in pong["data"]
    
    def test_웹소켓_상태_조회(self, client):
        """WebSocket 상태 조회 테스트"""
        with client.websocket_connect("/ws/test-connection") as websocket:
            # 환영 메시지 수신
            welcome = websocket.receive_json()
            
            # 상태 조회 요청
            websocket.send_json({"type": "get_status"})
            
            # 상태 응답 수신
            status = websocket.receive_json()
            assert status["type"] == "status_update"
            assert "connections" in status["data"]
            assert "server_time" in status["data"]
    
    def test_웹소켓_잘못된_메시지(self, client):
        """WebSocket 잘못된 메시지 테스트"""
        with client.websocket_connect("/ws/test-connection") as websocket:
            # 환영 메시지 수신
            welcome = websocket.receive_json()
            
            # 잘못된 JSON 전송
            websocket.send_text("invalid json")
            
            # 오류 메시지 수신
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert "JSON" in error["data"]["message"]


class TestAPIIntegration:
    """API 통합 테스트"""
    
    @pytest.fixture
    def client(self):
        """테스트 클라이언트 생성"""
        test_settings = Settings(
            jwt_secret_key="integration-test-key"
        )
        app = create_app(test_settings)
        return TestClient(app)
    
    def test_전체_워크플로우(self, client):
        """전체 API 워크플로우 테스트"""
        # 1. 토큰 발급
        token_response = client.post(
            "/auth/token",
            json={"client_id": "integration_test_client"}
        )
        assert token_response.status_code == 200
        token = token_response.json()["access_token"]
        
        # 2. 시스템 상태 확인
        status_response = client.get("/status")
        assert status_response.status_code == 200
        
        # 3. 헬스 체크
        health_response = client.get("/health")
        assert health_response.status_code == 200
        
        # 4. WebSocket 연결 테스트
        with client.websocket_connect("/ws/integration-test") as websocket:
            welcome = websocket.receive_json()
            assert welcome["type"] == "welcome"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 