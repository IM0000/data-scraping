"""
JWT 기반 인증 모듈

API 액세스를 위한 JWT 토큰 기반 인증을 제공합니다.
"""

try:
    import jwt
except ImportError:
    raise ImportError("PyJWT 패키지가 필요합니다. 'uv add pyjwt' 명령으로 설치하세요")

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config.settings import Settings, get_settings
from ..exceptions import AuthenticationException
from ..utils.logging import setup_logging

# HTTP Bearer 토큰 스키마
security = HTTPBearer()


class AuthManager:
    """JWT 인증 관리자"""

    def __init__(self, settings: Settings):
        """
        인증 관리자 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.logger = setup_logging(settings)
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm

    def create_access_token(
        self, 
        client_id: str, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        액세스 토큰 생성

        Args:
            client_id: 클라이언트 ID
            expires_delta: 만료 시간 (기본값: 설정에서 가져옴)

        Returns:
            JWT 토큰 문자열

        Raises:
            AuthenticationException: 토큰 생성 실패 시
        """
        try:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(hours=self.settings.jwt_expires_hours)

            # JWT 페이로드 구성
            to_encode = {
                "client_id": client_id,
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "access"
            }

            # JWT 토큰 생성
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            self.logger.info(f"액세스 토큰 생성: {client_id}")
            return encoded_jwt

        except Exception as e:
            self.logger.error(f"토큰 생성 실패: {client_id}, {e}")
            raise AuthenticationException(f"토큰 생성 실패: {e}") from e

    def verify_token(self, token: str) -> dict:
        """
        토큰 검증

        Args:
            token: JWT 토큰

        Returns:
            토큰 페이로드

        Raises:
            HTTPException: 토큰이 유효하지 않을 때
        """
        try:
            # JWT 토큰 디코딩
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # 토큰 타입 확인
            if payload.get("type") != "access":
                self.logger.warning(f"잘못된 토큰 타입: {payload.get('type')}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="잘못된 토큰 타입입니다",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # 클라이언트 ID 확인
            client_id = payload.get("client_id")
            if not client_id:
                self.logger.warning("토큰에 클라이언트 ID가 없습니다")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="토큰에 클라이언트 ID가 없습니다",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return payload

        except jwt.ExpiredSignatureError:
            self.logger.warning("만료된 토큰으로 접근 시도")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰이 만료되었습니다",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as e:
            self.logger.warning(f"JWT 검증 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰을 검증할 수 없습니다",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def validate_client_credentials(self, client_id: str, client_secret: Optional[str] = None) -> bool:
        """
        클라이언트 자격 증명 검증

        현재는 단순히 클라이언트 ID가 있으면 허용하지만,
        실제 환경에서는 데이터베이스나 외부 서비스와 연동하여 검증해야 합니다.

        Args:
            client_id: 클라이언트 ID
            client_secret: 클라이언트 시크릿 (선택사항)

        Returns:
            검증 결과
        """
        # TODO: 실제 클라이언트 검증 로직 구현
        # 현재는 기본적인 검증만 수행
        if not client_id or not client_id.strip():
            self.logger.warning("빈 클라이언트 ID로 인증 시도")
            return False

        # 클라이언트 ID 길이 제한
        if len(client_id) > 50:
            self.logger.warning(f"너무 긴 클라이언트 ID: {len(client_id)}")
            return False

        self.logger.info(f"클라이언트 자격 증명 검증 성공: {client_id}")
        return True


# 전역 인증 관리자 인스턴스
def get_auth_manager(settings: Settings = Depends(get_settings)) -> AuthManager:
    """인증 관리자 의존성 함수"""
    return AuthManager(settings)


# 의존성 함수들
def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings)
) -> str:
    """
    현재 클라이언트 의존성 함수

    Args:
        credentials: HTTP 인증 정보
        settings: 시스템 설정

    Returns:
        클라이언트 ID
    """
    auth_manager = AuthManager(settings)
    payload = auth_manager.verify_token(credentials.credentials)
    client_id = payload.get("client_id")
    
    if not client_id:
        # 이 코드는 실행되지 않아야 하지만 타입 안전성을 위해 추가
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 클라이언트 ID가 없습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return client_id


def get_optional_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    settings: Settings = Depends(get_settings)
) -> Optional[str]:
    """
    선택적 클라이언트 인증 의존성 함수
    
    인증이 선택적인 엔드포인트에서 사용합니다.

    Args:
        credentials: HTTP 인증 정보 (선택사항)
        settings: 시스템 설정

    Returns:
        클라이언트 ID (인증되지 않은 경우 None)
    """
    if not credentials:
        return None
    
    try:
        auth_manager = AuthManager(settings)
        payload = auth_manager.verify_token(credentials.credentials)
        return payload.get("client_id")
    except HTTPException:
        # 인증 실패해도 예외를 발생시키지 않음
        return None 