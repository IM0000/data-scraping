"""
WebSocket 엔드포인트 모듈

실시간 상태 업데이트를 위한 WebSocket 연결을 제공합니다.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set, Optional

from fastapi import WebSocket, WebSocketDisconnect, Depends
from fastapi.routing import APIRouter

from ...config.settings import Settings, get_settings
from ...utils.logging import setup_logging
from ..models import WebSocketMessage
from ..auth import get_optional_current_client

# WebSocket 라우터
websocket_router = APIRouter()

# 활성 연결 관리
class ConnectionManager:
    """WebSocket 연결 관리자"""
    
    def __init__(self):
        """연결 관리자 초기화"""
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_connections: Dict[str, Set[str]] = {}
        
    async def connect(self, websocket: WebSocket, connection_id: str, client_id: Optional[str] = None):
        """
        WebSocket 연결 수락
        
        Args:
            websocket: WebSocket 연결
            connection_id: 연결 고유 ID
            client_id: 클라이언트 ID (선택사항)
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        if client_id:
            if client_id not in self.client_connections:
                self.client_connections[client_id] = set()
            self.client_connections[client_id].add(connection_id)
    
    def disconnect(self, connection_id: str, client_id: Optional[str] = None):
        """
        WebSocket 연결 해제
        
        Args:
            connection_id: 연결 고유 ID
            client_id: 클라이언트 ID (선택사항)
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            
        if client_id and client_id in self.client_connections:
            self.client_connections[client_id].discard(connection_id)
            if not self.client_connections[client_id]:
                del self.client_connections[client_id]
    
    async def send_personal_message(self, message: str, connection_id: str):
        """
        특정 연결에 메시지 전송
        
        Args:
            message: 전송할 메시지
            connection_id: 연결 ID
        """
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_text(message)
            except Exception:
                # 연결이 끊어진 경우 제거
                self.disconnect(connection_id)
    
    async def send_client_message(self, message: str, client_id: str):
        """
        특정 클라이언트의 모든 연결에 메시지 전송
        
        Args:
            message: 전송할 메시지
            client_id: 클라이언트 ID
        """
        if client_id in self.client_connections:
            disconnected_connections = []
            for connection_id in self.client_connections[client_id]:
                if connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]
                    try:
                        await websocket.send_text(message)
                    except Exception:
                        disconnected_connections.append(connection_id)
            
            # 끊어진 연결들 정리
            for connection_id in disconnected_connections:
                self.disconnect(connection_id, client_id)
    
    async def broadcast(self, message: str):
        """
        모든 연결에 메시지 브로드캐스트
        
        Args:
            message: 전송할 메시지
        """
        disconnected_connections = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected_connections.append(connection_id)
        
        # 끊어진 연결들 정리
        for connection_id in disconnected_connections:
            self.disconnect(connection_id)
    
    def get_connection_count(self) -> int:
        """활성 연결 수 반환"""
        return len(self.active_connections)
    
    def get_client_connection_count(self, client_id: str) -> int:
        """특정 클라이언트의 연결 수 반환"""
        if client_id in self.client_connections:
            return len(self.client_connections[client_id])
        return 0


# 전역 연결 관리자
manager = ConnectionManager()


@websocket_router.websocket("/ws/{connection_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    connection_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    WebSocket 엔드포인트
    
    Args:
        websocket: WebSocket 연결
        connection_id: 연결 고유 ID
        settings: 시스템 설정
    """
    logger = setup_logging(settings)
    client_id = None
    
    try:
        # 연결 수락
        await manager.connect(websocket, connection_id, client_id)
        logger.info(f"WebSocket 연결 수락: {connection_id}")
        
        # 환영 메시지 전송
        welcome_message = WebSocketMessage(
            type="welcome",
            data={
                "connection_id": connection_id,
                "server_time": datetime.now().isoformat(),
                "message": "WebSocket 연결이 성공했습니다"
            }
        )
        await manager.send_personal_message(welcome_message.model_dump_json(), connection_id)
        
        # 메시지 수신 루프
        while True:
            try:
                # 클라이언트로부터 메시지 수신
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                    message_type = message_data.get("type", "unknown")
                    
                    logger.debug(f"WebSocket 메시지 수신: {connection_id}, 타입: {message_type}")
                    
                    # 메시지 타입별 처리
                    if message_type == "ping":
                        # 핑-퐁 메시지
                        pong_message = WebSocketMessage(
                            type="pong",
                            data={"timestamp": datetime.now().isoformat()}
                        )
                        await manager.send_personal_message(pong_message.model_dump_json(), connection_id)
                    
                    elif message_type == "subscribe":
                        # 특정 이벤트 구독
                        event_type = message_data.get("event_type")
                        logger.info(f"구독 요청: {connection_id}, 이벤트: {event_type}")
                        
                        response_message = WebSocketMessage(
                            type="subscription_confirmed",
                            data={
                                "event_type": event_type,
                                "status": "subscribed"
                            }
                        )
                        await manager.send_personal_message(response_message.model_dump_json(), connection_id)
                    
                    elif message_type == "get_status":
                        # 현재 상태 요청
                        status_message = WebSocketMessage(
                            type="status_update",
                            data={
                                "connections": manager.get_connection_count(),
                                "server_time": datetime.now().isoformat(),
                                "status": "healthy"
                            }
                        )
                        await manager.send_personal_message(status_message.model_dump_json(), connection_id)
                    
                    else:
                        # 알 수 없는 메시지 타입
                        error_message = WebSocketMessage(
                            type="error",
                            data={
                                "message": f"알 수 없는 메시지 타입: {message_type}",
                                "received_message": message_data
                            }
                        )
                        await manager.send_personal_message(error_message.model_dump_json(), connection_id)
                
                except json.JSONDecodeError:
                    # JSON 파싱 오류
                    error_message = WebSocketMessage(
                        type="error",
                        data={"message": "잘못된 JSON 형식입니다"}
                    )
                    await manager.send_personal_message(error_message.model_dump_json(), connection_id)
                
            except WebSocketDisconnect:
                # 클라이언트가 연결을 끊음
                break
            except Exception as e:
                logger.error(f"WebSocket 메시지 처리 오류: {connection_id}, {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket 연결 오류: {connection_id}, {e}")
    
    finally:
        # 연결 정리
        manager.disconnect(connection_id, client_id)
        logger.info(f"WebSocket 연결 해제: {connection_id}")


async def broadcast_system_status(status_data: dict):
    """
    시스템 상태 브로드캐스트
    
    Args:
        status_data: 상태 데이터
    """
    message = WebSocketMessage(
        type="system_status",
        data=status_data
    )
    await manager.broadcast(message.model_dump_json())


async def broadcast_task_update(request_id: str, status: str, data: Optional[dict] = None):
    """
    작업 상태 업데이트 브로드캐스트
    
    Args:
        request_id: 요청 ID
        status: 작업 상태
        data: 추가 데이터
    """
    message = WebSocketMessage(
        type="task_update",
        request_id=request_id,
        data={
            "status": status,
            "timestamp": datetime.now().isoformat(),
            **(data or {})
        }
    )
    await manager.broadcast(message.model_dump_json())


async def send_client_notification(client_id: str, notification_type: str, data: dict):
    """
    특정 클라이언트에게 알림 전송
    
    Args:
        client_id: 클라이언트 ID
        notification_type: 알림 타입
        data: 알림 데이터
    """
    message = WebSocketMessage(
        type="notification",
        data={
            "notification_type": notification_type,
            "timestamp": datetime.now().isoformat(),
            **data
        }
    )
    await manager.send_client_message(message.model_dump_json(), client_id) 