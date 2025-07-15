"""
스크립트 저장소 통합 모듈

Git, HTTP, S3 저장소에서 스크립트를 다운로드하는 기능을 제공합니다.
"""

import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import aiohttp
import git

from ..exceptions import ScriptNotFoundException, ScriptRepositoryException
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RepositoryBase(ABC):
    """저장소 기본 추상 클래스"""

    def __init__(self, settings):
        """저장소 기본 초기화"""
        self.settings = settings
        self.logger = logger

    @abstractmethod
    async def download_script(self, script_name: str, version: Optional[str] = None) -> Path:
        """
        스크립트 다운로드 (추상 메서드)

        Args:
            script_name: 스크립트 이름
            version: 버전 (선택사항)

        Returns:
            다운로드된 스크립트 경로
        """
        pass

    @abstractmethod
    async def get_available_versions(self, script_name: str) -> list[str]:
        """
        사용 가능한 버전 목록 (추상 메서드)

        Args:
            script_name: 스크립트 이름

        Returns:
            버전 목록
        """
        pass

    @abstractmethod
    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """
        최신 버전 조회 (추상 메서드)

        Args:
            script_name: 스크립트 이름

        Returns:
            최신 버전 (없으면 None)
        """
        pass


class GitRepository(RepositoryBase):
    """Git 저장소 클래스"""

    def __init__(self, settings, repository_url: str):
        """
        Git 저장소 초기화

        Args:
            settings: 시스템 설정
            repository_url: Git 저장소 URL
        """
        super().__init__(settings)
        self.repository_url = repository_url
        self.local_repo_path = Path(settings.script_cache_dir) / "git_repo"
        self.repo = None

    async def clone_or_update_repo(self) -> None:
        """저장소 복제 또는 업데이트"""
        if self.local_repo_path.exists():
            # 기존 저장소 업데이트
            try:
                self.repo = git.Repo(self.local_repo_path)
                origin = self.repo.remotes.origin
                origin.pull()
                self.logger.info(f"저장소 업데이트 완료: {self.repository_url}")
            except Exception as e:
                self.logger.error(f"저장소 업데이트 실패: {e}")
                # 업데이트 실패 시 재복제
                await self._clone_fresh()
        else:
            # 새로운 저장소 복제
            await self._clone_fresh()

    async def _clone_fresh(self) -> None:
        """새로운 저장소 복제"""
        try:
            # 기존 디렉토리가 있으면 삭제
            if self.local_repo_path.exists():
                shutil.rmtree(self.local_repo_path)

            self.local_repo_path.mkdir(parents=True, exist_ok=True)
            self.repo = git.Repo.clone_from(
                self.repository_url,
                self.local_repo_path,
                depth=1  # 얕은 복제로 성능 향상
            )
            self.logger.info(f"저장소 복제 완료: {self.repository_url}")
        except Exception as e:
            self.logger.error(f"저장소 복제 실패: {e}")
            raise ScriptRepositoryException("git", f"저장소 복제 실패: {e}") from e

    async def download_script(self, script_name: str, version: Optional[str] = None) -> Path:
        """Git에서 스크립트 다운로드"""
        await self.clone_or_update_repo()

        script_path = self.local_repo_path / script_name
        if not script_path.exists():
            raise ScriptNotFoundException(script_name, version)

        # 버전 체크아웃 (태그 기준)
        if version and self.repo:
            try:
                self.repo.git.checkout(f"v{version}")
                self.logger.info(f"버전 체크아웃: v{version}")
            except Exception as e:
                self.logger.warning(f"버전 체크아웃 실패: {e}, 기본 브랜치 사용")

        # 임시 디렉토리에 복사
        temp_dir = Path(tempfile.mkdtemp())
        dest_path = temp_dir / script_name

        if script_path.is_file():
            # 단일 파일인 경우
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script_path, dest_path)
        else:
            # 디렉토리인 경우
            shutil.copytree(script_path, dest_path)

        return dest_path

    async def get_available_versions(self, script_name: str) -> list[str]:
        """Git 태그 기준 사용 가능한 버전 목록"""
        await self.clone_or_update_repo()

        if not self.repo:
            return []

        try:
            tags = self.repo.tags
            versions = []
            for tag in tags:
                tag_name = str(tag)
                if tag_name.startswith('v'):
                    versions.append(tag_name[1:])  # v 제거

            # 의미론적 버전 정렬 (내림차순)
            return sorted(versions, reverse=True, key=self._version_key)
        except Exception as e:
            self.logger.error(f"버전 목록 조회 실패: {e}")
            return []

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """최신 버전 조회"""
        versions = await self.get_available_versions(script_name)
        return versions[0] if versions else None

    def _version_key(self, version: str) -> tuple:
        """버전 정렬을 위한 키 생성"""
        try:
            parts = [int(part) for part in version.split('.')]
            return tuple(parts)
        except ValueError:
            return (0, 0, 0)


class HttpRepository(RepositoryBase):
    """HTTP 저장소 클래스"""

    def __init__(self, settings, base_url: str):
        """
        HTTP 저장소 초기화

        Args:
            settings: 시스템 설정
            base_url: HTTP 기본 URL
        """
        super().__init__(settings)
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP 세션 생성"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    'User-Agent': 'Scraping-System/1.0'
                }
            )
        return self.session

    async def download_script(self, script_name: str, version: Optional[str] = None) -> Path:
        """HTTP에서 스크립트 다운로드"""
        session = await self._get_session()

        # 버전 지정이 없으면 최신 버전 사용
        if not version:
            version = await self.get_latest_version(script_name)
            if not version:
                raise ScriptNotFoundException(script_name)

        # 스크립트 다운로드 URL 구성
        download_url = f"{self.base_url}/api/scripts/{script_name}/{version}/download"

        try:
            async with session.get(download_url) as response:
                if response.status == 200:
                    # 임시 디렉토리 생성
                    temp_dir = Path(tempfile.mkdtemp())
                    script_dir = temp_dir / script_name
                    script_dir.mkdir(parents=True, exist_ok=True)

                    # Content-Type 확인하여 처리 방식 결정
                    content_type = response.headers.get('content-type', '')

                    if 'application/zip' in content_type:
                        # ZIP 파일로 다운로드된 경우
                        zip_content = await response.read()
                        await self._extract_zip(zip_content, script_dir)
                    else:
                        # 단일 파일로 다운로드된 경우
                        content = await response.read()
                        script_file = script_dir / "main.py"
                        with open(script_file, 'wb') as f:
                            f.write(content)

                    self.logger.info(f"HTTP 스크립트 다운로드 완료: {script_name} v{version}")
                    return script_dir
                else:
                    raise ScriptNotFoundException(script_name, version)

        except Exception as e:
            self.logger.error(f"HTTP 스크립트 다운로드 오류: {e}")
            raise ScriptRepositoryException("http", f"스크립트 다운로드 오류: {e}") from e

    async def get_available_versions(self, script_name: str) -> list[str]:
        """HTTP API를 통한 사용 가능한 버전 목록"""
        session = await self._get_session()

        try:
            versions_url = f"{self.base_url}/api/scripts/{script_name}/versions"
            async with session.get(versions_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('versions', [])
                else:
                    self.logger.error(f"버전 목록 조회 실패: HTTP {response.status}")
                    return []

        except Exception as e:
            self.logger.error(f"버전 목록 조회 오류: {e}")
            return []

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """최신 버전 조회"""
        session = await self._get_session()

        try:
            latest_url = f"{self.base_url}/api/scripts/{script_name}/latest"
            async with session.get(latest_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('version')
                else:
                    # 버전 목록에서 첫 번째 항목을 최신으로 간주
                    versions = await self.get_available_versions(script_name)
                    return versions[0] if versions else None

        except Exception as e:
            self.logger.error(f"최신 버전 조회 오류: {e}")
            return None

    async def _extract_zip(self, zip_content: bytes, extract_path: Path) -> None:
        """ZIP 콘텐츠 추출"""
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
            zip_file.extractall(extract_path)

    async def close(self) -> None:
        """세션 정리"""
        if self.session:
            await self.session.close()


class S3Repository(RepositoryBase):
    """S3 저장소 클래스"""

    def __init__(self, settings):
        """
        S3 저장소 초기화

        Args:
            settings: 시스템 설정
        """
        super().__init__(settings)

        try:
            import boto3
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region
            )
            self.bucket_name = settings.s3_bucket_name
            self.prefix = settings.s3_prefix

            self.logger.info(f"S3 저장소 초기화 완료: {self.bucket_name}")

        except ImportError:
            raise ScriptRepositoryException("s3", "boto3 라이브러리가 필요합니다: uv add boto3")
        except Exception as e:
            self.logger.error(f"S3 초기화 실패: {e}")
            raise ScriptRepositoryException("s3", f"S3 초기화 실패: {e}") from e

    async def download_script(self, script_name: str, version: Optional[str] = None) -> Path:
        """S3에서 스크립트 다운로드"""
        if not version:
            version = await self.get_latest_version(script_name)
            if not version:
                raise ScriptNotFoundException(script_name)

        # S3 키 구성
        script_key = f"{self.prefix}{script_name}/{version}/"

        try:
            # 임시 디렉토리 생성
            temp_dir = Path(tempfile.mkdtemp())
            script_dir = temp_dir / script_name
            script_dir.mkdir(parents=True, exist_ok=True)

            # S3에서 스크립트 파일들 나열
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=script_key
            )

            if 'Contents' not in response:
                raise ScriptNotFoundException(script_name, version)

            # 각 파일 다운로드
            for obj in response['Contents']:
                file_key = obj['Key']
                # 상대 경로 추출 (prefix 제거)
                relative_path = file_key[len(script_key):]

                if relative_path:  # 빈 경로 제외
                    local_file_path = script_dir / relative_path
                    local_file_path.parent.mkdir(parents=True, exist_ok=True)

                    # 파일 다운로드
                    self.s3_client.download_file(
                        self.bucket_name,
                        file_key,
                        str(local_file_path)
                    )

            self.logger.info(f"S3 스크립트 다운로드 완료: {script_name} v{version}")
            return script_dir

        except Exception as e:
            self.logger.error(f"S3 스크립트 다운로드 오류: {e}")
            raise ScriptRepositoryException("s3", f"스크립트 다운로드 오류: {e}") from e

    async def get_available_versions(self, script_name: str) -> list[str]:
        """S3에서 사용 가능한 버전 목록 조회"""
        try:
            script_prefix = f"{self.prefix}{script_name}/"

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=script_prefix,
                Delimiter='/'
            )

            versions = []
            for prefix_info in response.get('CommonPrefixes', []):
                # 버전 디렉토리 이름 추출
                version_path = prefix_info['Prefix']
                version = version_path[len(script_prefix):].rstrip('/')
                if version:
                    versions.append(version)

            # 의미론적 버전 정렬 (내림차순)
            return sorted(versions, reverse=True)

        except Exception as e:
            self.logger.error(f"S3 버전 목록 조회 오류: {e}")
            return []

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """최신 버전 조회"""
        versions = await self.get_available_versions(script_name)
        return versions[0] if versions else None
