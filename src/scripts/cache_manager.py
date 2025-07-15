"""
스크립트 캐시 관리 모듈

스크립트의 로컬 캐싱과 버전 관리를 담당합니다.
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..utils.helpers import calculate_file_hash
from ..utils.logging import get_logger
from .metadata import MetadataParser, ScriptMetadata
from .repository import RepositoryBase

logger = get_logger(__name__)


class CacheManager:
    """스크립트 캐시 관리자"""

    def __init__(self, settings, repository: RepositoryBase):
        """
        캐시 매니저 초기화

        Args:
            settings: 시스템 설정
            repository: 저장소 인스턴스
        """
        self.settings = settings
        self.repository = repository
        self.logger = logger
        self.cache_dir = Path(settings.script_cache_dir)
        self.metadata_parser = MetadataParser(settings)

        # 캐시 디렉토리 생성
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, script_name: str, version: str) -> Path:
        """캐시 경로 생성"""
        return self.cache_dir / script_name / version

    def _get_metadata_path(self, script_name: str, version: str) -> Path:
        """메타데이터 파일 경로 생성"""
        return self._get_cache_path(script_name, version) / "metadata.json"

    async def get_script(self, script_name: str, version: Optional[str] = None) -> tuple[Path, ScriptMetadata]:
        """
        스크립트 가져오기 (캐시 우선)

        Args:
            script_name: 스크립트 이름
            version: 버전 (None이면 최신 버전)

        Returns:
            (스크립트 경로, 메타데이터) 튜플

        Raises:
            ValueError: 스크립트 버전을 찾을 수 없을 때
            Exception: 스크립트 다운로드 실패 시
        """
        # 버전이 지정되지 않으면 최신 버전 사용
        if not version:
            version = await self.repository.get_latest_version(script_name)
            if not version:
                raise ValueError(f"스크립트 버전을 찾을 수 없습니다: {script_name}")

        cache_path = self._get_cache_path(script_name, version)
        metadata_path = self._get_metadata_path(script_name, version)

        # 캐시 확인
        if await self._is_cache_valid(script_name, version):
            self.logger.info(f"캐시에서 스크립트 로드: {script_name} v{version}")
            metadata = self.metadata_parser.parse_metadata_file(metadata_path)
            return cache_path, metadata

        # 캐시가 없거나 만료된 경우 다운로드
        self.logger.info(f"스크립트 다운로드 시작: {script_name} v{version}")

        try:
            # 저장소에서 다운로드
            temp_path = await self.repository.download_script(script_name, version)

            # 캐시 디렉토리로 복사
            cache_path.mkdir(parents=True, exist_ok=True)

            if temp_path.is_file():
                # 단일 파일인 경우
                shutil.copy2(temp_path, cache_path / temp_path.name)
            else:
                # 디렉토리인 경우 - 기존 캐시 삭제 후 복사
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                shutil.copytree(temp_path, cache_path)

            # 메타데이터 파싱
            if not metadata_path.exists():
                # 메타데이터 파일이 없으면 기본 메타데이터 생성
                self._create_default_metadata(script_name, version, metadata_path)

            metadata = self.metadata_parser.parse_metadata_file(metadata_path)

            # 캐시 정보 저장
            await self._save_cache_info(script_name, version, metadata)

            # 임시 파일 정리
            if temp_path.exists():
                if temp_path.is_file():
                    temp_path.unlink()
                else:
                    shutil.rmtree(temp_path)

            self.logger.info(f"스크립트 캐시 완료: {script_name} v{version}")
            return cache_path, metadata

        except Exception as e:
            self.logger.error(f"스크립트 캐시 오류: {e}")
            raise Exception(f"스크립트 캐시 오류: {e}") from e

    async def _is_cache_valid(self, script_name: str, version: str) -> bool:
        """캐시 유효성 검사"""
        cache_path = self._get_cache_path(script_name, version)
        metadata_path = self._get_metadata_path(script_name, version)
        cache_info_path = cache_path / ".cache_info"

        # 필수 파일 존재 확인
        if not all([cache_path.exists(), metadata_path.exists(), cache_info_path.exists()]):
            return False

        try:
            # 캐시 정보 로드
            with open(cache_info_path, encoding='utf-8') as f:
                cache_info = json.load(f)

            # 캐시 시간 검사 (설정에서 지정된 시간, 기본 24시간)
            cache_max_age = getattr(self.settings, 'script_cache_max_age', 24)
            cached_at = datetime.fromisoformat(cache_info['cached_at'])
            if datetime.now() - cached_at > timedelta(hours=cache_max_age):
                self.logger.debug(f"캐시 만료: {script_name} v{version}")
                return False

            # 파일 무결성 검사
            entry_point = cache_info.get('entry_point', 'main.py')
            entry_file = cache_path / entry_point

            if entry_file.exists():
                current_hash = calculate_file_hash(str(entry_file))
                stored_hash = cache_info.get('file_hash')
                if current_hash != stored_hash:
                    self.logger.warning(f"파일 무결성 검사 실패: {script_name} v{version}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"캐시 유효성 검사 오류: {e}")
            return False

    async def _save_cache_info(self, script_name: str, version: str, metadata: ScriptMetadata) -> None:
        """캐시 정보 저장"""
        cache_path = self._get_cache_path(script_name, version)
        cache_info_path = cache_path / ".cache_info"

        # 엔트리 포인트 파일 해시 계산
        entry_file = cache_path / metadata.entry_point
        file_hash = calculate_file_hash(str(entry_file)) if entry_file.exists() else None

        cache_info = {
            'script_name': script_name,
            'version': version,
            'cached_at': datetime.now().isoformat(),
            'entry_point': metadata.entry_point,
            'file_hash': file_hash,
            'repository_type': type(self.repository).__name__,
            'metadata': {
                'name': metadata.name,
                'description': metadata.description,
                'author': metadata.author,
                'dependencies': metadata.dependencies,
                'timeout': metadata.timeout
            }
        }

        with open(cache_info_path, 'w', encoding='utf-8') as f:
            json.dump(cache_info, f, indent=2, ensure_ascii=False)

    def _create_default_metadata(self, script_name: str, version: str, metadata_path: Path) -> None:
        """기본 메타데이터 생성"""
        default_metadata = self.metadata_parser.create_sample_metadata(script_name)
        default_metadata['version'] = version

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(default_metadata, f, indent=2, ensure_ascii=False)

    async def cleanup_old_cache(self, max_age_hours: int = 168) -> None:  # 7일
        """
        오래된 캐시 정리

        Args:
            max_age_hours: 최대 보관 시간 (시간 단위)
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0

        for script_dir in self.cache_dir.iterdir():
            if script_dir.is_dir():
                for version_dir in script_dir.iterdir():
                    if version_dir.is_dir():
                        cache_info_path = version_dir / ".cache_info"

                        if cache_info_path.exists():
                            try:
                                with open(cache_info_path, encoding='utf-8') as f:
                                    cache_info = json.load(f)

                                cached_at = datetime.fromisoformat(cache_info['cached_at'])
                                if cached_at < cutoff_time:
                                    shutil.rmtree(version_dir)
                                    cleaned_count += 1
                                    self.logger.info(f"오래된 캐시 정리: {script_dir.name} v{version_dir.name}")

                            except Exception as e:
                                self.logger.error(f"캐시 정리 오류: {e}")
                        else:
                            # 캐시 정보가 없는 디렉토리도 정리
                            try:
                                shutil.rmtree(version_dir)
                                cleaned_count += 1
                                self.logger.info(f"캐시 정보 없는 디렉토리 정리: {script_dir.name} v{version_dir.name}")
                            except Exception as e:
                                self.logger.error(f"디렉토리 정리 오류: {e}")

        if cleaned_count > 0:
            self.logger.info(f"캐시 정리 완료: {cleaned_count}개 항목 삭제")

    async def get_cached_scripts(self) -> list[dict]:
        """
        캐시된 스크립트 목록 조회

        Returns:
            캐시된 스크립트 정보 목록
        """
        cached_scripts = []

        for script_dir in self.cache_dir.iterdir():
            if script_dir.is_dir():
                for version_dir in script_dir.iterdir():
                    if version_dir.is_dir():
                        cache_info_path = version_dir / ".cache_info"

                        if cache_info_path.exists():
                            try:
                                with open(cache_info_path, encoding='utf-8') as f:
                                    cache_info = json.load(f)

                                # 디렉토리 크기 계산
                                total_size = sum(
                                    f.stat().st_size
                                    for f in version_dir.rglob('*')
                                    if f.is_file()
                                )

                                cached_scripts.append({
                                    'script_name': cache_info['script_name'],
                                    'version': cache_info['version'],
                                    'cached_at': cache_info['cached_at'],
                                    'size': total_size,
                                    'repository_type': cache_info.get('repository_type', 'unknown'),
                                    'metadata': cache_info.get('metadata', {})
                                })

                            except Exception as e:
                                self.logger.error(f"캐시 정보 읽기 오류: {e}")

        # 캐시된 시간 순으로 정렬 (최신 순)
        cached_scripts.sort(key=lambda x: x['cached_at'], reverse=True)
        return cached_scripts

    async def invalidate_cache(self, script_name: str, version: Optional[str] = None) -> None:
        """
        캐시 무효화

        Args:
            script_name: 스크립트 이름
            version: 특정 버전 (None이면 모든 버전)
        """
        if version:
            # 특정 버전만 삭제
            cache_path = self._get_cache_path(script_name, version)
            if cache_path.exists():
                shutil.rmtree(cache_path)
                self.logger.info(f"캐시 무효화: {script_name} v{version}")
        else:
            # 모든 버전 삭제
            script_cache_dir = self.cache_dir / script_name
            if script_cache_dir.exists():
                shutil.rmtree(script_cache_dir)
                self.logger.info(f"전체 캐시 무효화: {script_name}")

    async def get_cache_stats(self) -> dict:
        """
        캐시 통계 정보 조회

        Returns:
            캐시 통계 딕셔너리
        """
        total_size = 0
        script_count = 0
        version_count = 0

        for script_dir in self.cache_dir.iterdir():
            if script_dir.is_dir():
                script_count += 1
                for version_dir in script_dir.iterdir():
                    if version_dir.is_dir():
                        version_count += 1
                        # 디렉토리 크기 계산
                        dir_size = sum(
                            f.stat().st_size
                            for f in version_dir.rglob('*')
                            if f.is_file()
                        )
                        total_size += dir_size

        return {
            'total_size_bytes': total_size,
            'script_count': script_count,
            'version_count': version_count,
            'cache_directory': str(self.cache_dir)
        }
