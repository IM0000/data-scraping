"""
스크립트 메타데이터 관리 모듈

스크립트의 메타데이터 모델과 파싱 기능을 제공합니다.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ScriptMetadata:
    """스크립트 메타데이터 모델"""

    # 기본 정보
    name: str
    version: str
    description: str
    author: str
    created_at: datetime
    updated_at: datetime

    # 의존성 정보
    python_version: str = ">=3.8"
    dependencies: list[str] = field(default_factory=list)
    system_requirements: list[str] = field(default_factory=list)

    # 실행 정보
    entry_point: str = "main.py"
    timeout: int = 300
    memory_limit: str = "512MB"

    # 추가 설정
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class MetadataParser:
    """스크립트 메타데이터 파서"""

    def __init__(self, settings=None):
        """
        메타데이터 파서 초기화

        Args:
            settings: 시스템 설정 객체 (선택사항)
        """
        self.settings = settings
        self.logger = logger

    def parse_metadata_file(self, metadata_path: Path) -> ScriptMetadata:
        """
        메타데이터 파일 파싱

        Args:
            metadata_path: 메타데이터 파일 경로

        Returns:
            파싱된 메타데이터 객체

        Raises:
            FileNotFoundError: 메타데이터 파일이 없을 때
            ValueError: 메타데이터 형식이 잘못되었을 때
        """
        if not metadata_path.exists():
            raise FileNotFoundError(f"메타데이터 파일을 찾을 수 없습니다: {metadata_path}")

        try:
            with open(metadata_path, encoding='utf-8') as f:
                metadata_dict = json.load(f)

            # 필수 필드 검증
            required_fields = ['name', 'version', 'description', 'author']
            for field in required_fields:
                if field not in metadata_dict:
                    raise ValueError(f"필수 필드 누락: {field}")

            # 날짜 파싱
            created_at = self._parse_datetime(
                metadata_dict.get('created_at', datetime.now().isoformat())
            )
            updated_at = self._parse_datetime(
                metadata_dict.get('updated_at', datetime.now().isoformat())
            )

            return ScriptMetadata(
                name=metadata_dict['name'],
                version=metadata_dict['version'],
                description=metadata_dict['description'],
                author=metadata_dict['author'],
                created_at=created_at,
                updated_at=updated_at,
                python_version=metadata_dict.get('python_version', '>=3.8'),
                dependencies=metadata_dict.get('dependencies', []),
                system_requirements=metadata_dict.get('system_requirements', []),
                entry_point=metadata_dict.get('entry_point', 'main.py'),
                timeout=metadata_dict.get('timeout', 300),
                memory_limit=metadata_dict.get('memory_limit', '512MB'),
                parameters=metadata_dict.get('parameters', {}),
                tags=metadata_dict.get('tags', [])
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"메타데이터 JSON 파싱 오류: {e}") from e
        except Exception as e:
            raise ValueError(f"메타데이터 파싱 오류: {e}") from e

    def validate_metadata(self, metadata: ScriptMetadata) -> bool:
        """
        메타데이터 유효성 검증

        Args:
            metadata: 검증할 메타데이터

        Returns:
            유효성 검증 결과
        """
        try:
            # 버전 형식 검증 (semantic versioning)
            version_parts = metadata.version.split('.')
            if len(version_parts) != 3:
                self.logger.error(f"잘못된 버전 형식: {metadata.version}")
                return False

            for part in version_parts:
                int(part)  # 숫자 검증

            # 엔트리 포인트 검증
            if not metadata.entry_point.endswith('.py'):
                self.logger.error(f"잘못된 엔트리 포인트: {metadata.entry_point}")
                return False

            # 타임아웃 검증
            if metadata.timeout <= 0:
                self.logger.error(f"잘못된 타임아웃: {metadata.timeout}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"메타데이터 검증 오류: {e}")
            return False

    def _parse_datetime(self, datetime_str: str) -> datetime:
        """
        ISO 형식 날짜 문자열을 datetime 객체로 변환

        Args:
            datetime_str: ISO 형식 날짜 문자열

        Returns:
            datetime 객체
        """
        try:
            return datetime.fromisoformat(datetime_str)
        except ValueError:
            # 기본 형식으로 재시도
            return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")

    def create_sample_metadata(self, script_name: str) -> dict[str, Any]:
        """
        샘플 메타데이터 생성

        Args:
            script_name: 스크립트 이름

        Returns:
            샘플 메타데이터 딕셔너리
        """
        now = datetime.now()
        return {
            "name": script_name,
            "version": "1.0.0",
            "description": f"{script_name} 스크래핑 스크립트",
            "author": "Development Team",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "python_version": ">=3.8",
            "dependencies": [
                "requests>=2.25.0",
                "beautifulsoup4>=4.9.0"
            ],
            "system_requirements": [],
            "entry_point": "main.py",
            "timeout": 300,
            "memory_limit": "512MB",
            "parameters": {
                "url": {
                    "type": "string",
                    "required": True,
                    "description": "스크래핑할 URL"
                },
                "timeout": {
                    "type": "integer",
                    "required": False,
                    "default": 30,
                    "description": "요청 타임아웃 (초)"
                }
            },
            "tags": ["web-scraping", "http"]
        }
