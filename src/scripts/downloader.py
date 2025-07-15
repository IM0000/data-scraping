"""
스크립트 다운로더 오케스트레이터 모듈

스크립트 관리의 모든 기능을 통합하는 메인 인터페이스를 제공합니다.
"""

from typing import Optional

from ..config.settings import Settings
from ..models.enums import ScriptRepositoryType
from ..utils.logging import get_logger
from .cache_manager import CacheManager
from .metadata import MetadataParser, ScriptMetadata
from .repository import GitRepository, HttpRepository, RepositoryBase, S3Repository

logger = get_logger(__name__)


class ScriptDownloader:
    """스크립트 다운로더 오케스트레이터"""

    def __init__(self, settings: Optional[Settings] = None):
        """
        스크립트 다운로더 초기화

        Args:
            settings: 시스템 설정 (None이면 기본 설정 사용)
        """
        if settings is None:
            from ..config.settings import get_settings
            settings = get_settings()

        self.settings = settings
        self.logger = logger

        # 저장소 초기화
        self.repository = self._create_repository()

        # 캐시 매니저 초기화
        self.cache_manager = CacheManager(settings, self.repository)

        # 메타데이터 파서 초기화
        self.metadata_parser = MetadataParser(settings)

        self.logger.info(f"스크립트 다운로더 초기화 완료: {settings.script_repository_type.value}")

    def _create_repository(self) -> RepositoryBase:
        """설정에 따른 저장소 인스턴스 생성"""
        repo_type = self.settings.script_repository_type

        if repo_type == ScriptRepositoryType.GIT:
            if not self.settings.script_repository_url:
                raise ValueError("Git 저장소 사용 시 SCRIPT_REPOSITORY_URL이 필요합니다")
            return GitRepository(self.settings, self.settings.script_repository_url)

        elif repo_type == ScriptRepositoryType.HTTP:
            if not self.settings.script_repository_url:
                raise ValueError("HTTP 저장소 사용 시 SCRIPT_REPOSITORY_URL이 필요합니다")
            return HttpRepository(self.settings, self.settings.script_repository_url)

        elif repo_type == ScriptRepositoryType.S3:
            return S3Repository(self.settings)

        else:
            raise ValueError(f"지원하지 않는 저장소 타입: {repo_type}")

    async def get_script(self, script_name: str, version: Optional[str] = None, force_download: bool = False) -> tuple[str, ScriptMetadata]:
        """
        스크립트 가져오기

        Args:
            script_name: 스크립트 이름
            version: 스크립트 버전 (None이면 최신 버전)
            force_download: 강제 다운로드 여부 (캐시 무시)

        Returns:
            (스크립트 경로, 메타데이터) 튜플

        Raises:
            ValueError: 스크립트를 찾을 수 없을 때
            Exception: 다운로드 실패 시
        """
        self.logger.info(f"스크립트 요청: {script_name} v{version or 'latest'}")

        try:
            # 강제 다운로드인 경우 캐시 무효화
            if force_download:
                await self.cache_manager.invalidate_cache(script_name, version)

            # 캐시 매니저를 통해 스크립트 가져오기
            script_path, metadata = await self.cache_manager.get_script(script_name, version)

            # 메타데이터 유효성 검증
            if not self.metadata_parser.validate_metadata(metadata):
                self.logger.warning(f"메타데이터 유효성 검증 실패: {script_name} v{metadata.version}")

            self.logger.info(f"스크립트 반환: {script_name} v{metadata.version} -> {script_path}")
            return str(script_path), metadata

        except Exception as e:
            self.logger.error(f"스크립트 가져오기 실패: {script_name} - {e}")
            raise Exception(f"스크립트 가져오기 실패: {script_name} - {e}") from e

    async def get_available_versions(self, script_name: str) -> list[str]:
        """
        사용 가능한 스크립트 버전 목록 조회

        Args:
            script_name: 스크립트 이름

        Returns:
            버전 목록
        """
        try:
            versions = await self.repository.get_available_versions(script_name)
            self.logger.debug(f"사용 가능한 버전: {script_name} -> {versions}")
            return versions
        except Exception as e:
            self.logger.error(f"버전 목록 조회 실패: {script_name} - {e}")
            return []

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """
        최신 버전 조회

        Args:
            script_name: 스크립트 이름

        Returns:
            최신 버전 (없으면 None)
        """
        try:
            latest = await self.repository.get_latest_version(script_name)
            self.logger.debug(f"최신 버전: {script_name} -> {latest}")
            return latest
        except Exception as e:
            self.logger.error(f"최신 버전 조회 실패: {script_name} - {e}")
            return None

    async def list_cached_scripts(self) -> list[dict]:
        """
        캐시된 스크립트 목록 조회

        Returns:
            캐시된 스크립트 정보 목록
        """
        try:
            cached_scripts = await self.cache_manager.get_cached_scripts()
            self.logger.debug(f"캐시된 스크립트 {len(cached_scripts)}개 조회 완료")
            return cached_scripts
        except Exception as e:
            self.logger.error(f"캐시된 스크립트 목록 조회 실패: {e}")
            return []

    async def cleanup_cache(self, max_age_hours: int = 168) -> None:
        """
        오래된 캐시 정리

        Args:
            max_age_hours: 최대 보관 시간 (시간 단위, 기본 7일)
        """
        try:
            await self.cache_manager.cleanup_old_cache(max_age_hours)
            self.logger.info(f"캐시 정리 완료: {max_age_hours}시간 이상 된 항목 삭제")
        except Exception as e:
            self.logger.error(f"캐시 정리 실패: {e}")

    async def invalidate_cache(self, script_name: str, version: Optional[str] = None) -> None:
        """
        스크립트 캐시 무효화

        Args:
            script_name: 스크립트 이름
            version: 특정 버전 (None이면 모든 버전)
        """
        try:
            await self.cache_manager.invalidate_cache(script_name, version)
            version_info = f" v{version}" if version else " (모든 버전)"
            self.logger.info(f"캐시 무효화 완료: {script_name}{version_info}")
        except Exception as e:
            self.logger.error(f"캐시 무효화 실패: {script_name} - {e}")

    async def get_cache_stats(self) -> dict:
        """
        캐시 통계 정보 조회

        Returns:
            캐시 통계 딕셔너리
        """
        try:
            stats = await self.cache_manager.get_cache_stats()
            # 추가 정보 포함
            stats.update({
                'repository_type': self.settings.script_repository_type.value,
                'repository_url': self.settings.script_repository_url,
                'cache_max_age_hours': getattr(self.settings, 'script_cache_max_age', 24)
            })
            return stats
        except Exception as e:
            self.logger.error(f"캐시 통계 조회 실패: {e}")
            return {}

    async def validate_script(self, script_name: str, version: Optional[str] = None) -> bool:
        """
        스크립트 유효성 검증

        Args:
            script_name: 스크립트 이름
            version: 스크립트 버전

        Returns:
            유효성 검증 결과
        """
        try:
            script_path, metadata = await self.cache_manager.get_script(script_name, version)

            # 메타데이터 유효성 검증
            if not self.metadata_parser.validate_metadata(metadata):
                return False

            # 엔트리 포인트 파일 존재 확인
            entry_file = script_path / metadata.entry_point
            if not entry_file.exists():
                self.logger.error(f"엔트리 포인트 파일 없음: {entry_file}")
                return False

            self.logger.info(f"스크립트 유효성 검증 성공: {script_name} v{metadata.version}")
            return True

        except Exception as e:
            self.logger.error(f"스크립트 유효성 검증 실패: {script_name} - {e}")
            return False

    async def get_script_info(self, script_name: str, version: Optional[str] = None) -> Optional[dict]:
        """
        스크립트 정보 조회 (다운로드 없이 메타데이터만)

        Args:
            script_name: 스크립트 이름
            version: 스크립트 버전

        Returns:
            스크립트 정보 딕셔너리 (없으면 None)
        """
        try:
            script_path, metadata = await self.cache_manager.get_script(script_name, version)

            return {
                'name': metadata.name,
                'version': metadata.version,
                'description': metadata.description,
                'author': metadata.author,
                'created_at': metadata.created_at.isoformat(),
                'updated_at': metadata.updated_at.isoformat(),
                'python_version': metadata.python_version,
                'dependencies': metadata.dependencies,
                'system_requirements': metadata.system_requirements,
                'entry_point': metadata.entry_point,
                'timeout': metadata.timeout,
                'memory_limit': metadata.memory_limit,
                'parameters': metadata.parameters,
                'tags': metadata.tags,
                'cached_path': str(script_path)
            }

        except Exception as e:
            self.logger.error(f"스크립트 정보 조회 실패: {script_name} - {e}")
            return None

    async def close(self) -> None:
        """리소스 정리"""
        try:
            # HTTP 저장소인 경우 세션 정리
            if isinstance(self.repository, HttpRepository):
                await self.repository.close()

            self.logger.info("스크립트 다운로더 리소스 정리 완료")
        except Exception as e:
            self.logger.error(f"리소스 정리 실패: {e}")

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.close()


# 편의 함수들
async def get_script(script_name: str, version: Optional[str] = None, settings: Optional[Settings] = None) -> tuple[str, ScriptMetadata]:
    """
    편의 함수: 스크립트 가져오기

    Args:
        script_name: 스크립트 이름
        version: 스크립트 버전
        settings: 시스템 설정

    Returns:
        (스크립트 경로, 메타데이터) 튜플
    """
    async with ScriptDownloader(settings) as downloader:
        return await downloader.get_script(script_name, version)


async def list_available_versions(script_name: str, settings: Optional[Settings] = None) -> list[str]:
    """
    편의 함수: 사용 가능한 버전 목록 조회

    Args:
        script_name: 스크립트 이름
        settings: 시스템 설정

    Returns:
        버전 목록
    """
    async with ScriptDownloader(settings) as downloader:
        return await downloader.get_available_versions(script_name)


async def cleanup_old_cache(max_age_hours: int = 168, settings: Optional[Settings] = None) -> None:
    """
    편의 함수: 오래된 캐시 정리

    Args:
        max_age_hours: 최대 보관 시간 (시간 단위)
        settings: 시스템 설정
    """
    async with ScriptDownloader(settings) as downloader:
        await downloader.cleanup_cache(max_age_hours)
