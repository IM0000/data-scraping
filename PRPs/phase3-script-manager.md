# PRP-3: Script Manager

## Goal

Implement a comprehensive script management system that handles downloading, caching, version control, and metadata management for scraping scripts from external repositories. The system should support automatic updates, version comparison, and efficient caching strategies.

## Why

- **Dynamic execution**: Enables running scripts without hardcoding them into the system
- **Version control**: Supports script updates and rollbacks with semantic versioning
- **Performance**: Reduces script download time through intelligent caching
- **Reliability**: Ensures script availability even when repository is temporarily unavailable
- **Metadata management**: Tracks script dependencies, requirements, and configurations

## What

Build a script management system that includes:

- External repository integration (Git, HTTP, S3)
- Version-controlled caching with conditional downloads
- Script metadata parsing and validation
- Dependency resolution and requirements management
- Script integrity verification with checksums
- Automatic cleanup of old script versions

### Success Criteria

- [ ] Scripts can be downloaded from external repositories
- [ ] Version comparison works correctly (semantic versioning)
- [ ] Caching reduces redundant downloads
- [ ] Script metadata is properly parsed and validated
- [ ] Dependencies are resolved automatically
- [ ] Script integrity is verified before execution
- [ ] All validation gates pass

## All Needed Context

### Documentation & References

```yaml
# External Repository Integration
- url: https://gitpython.readthedocs.io/en/stable/
  why: Git repository operations for script downloading

- url: https://requests.readthedocs.io/en/latest/
  why: HTTP downloads for script repositories

- url: https://docs.python.org/3/library/urllib.html
  why: URL handling and parsing

- url: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
  why: AWS S3 integration for script storage

- url: https://semver.org/
  why: Semantic versioning for script versions

# File and Path Management
- url: https://docs.python.org/3/library/pathlib.html
  why: Path operations for script caching

- url: https://docs.python.org/3/library/hashlib.html
  why: Script integrity verification

# Dependencies
- file: PRPs/phase1-core-models.md
  why: Uses core data models and configuration system

- file: examples/basic_structure.py
  why: Follow existing coding patterns and class structure

- file: examples/test_pattern.py
  why: Test patterns for validation gates
```

### Current Codebase Structure (After Phase 1-2)

```
src/
├── models/
│   ├── base.py              # Core data models
│   └── enums.py             # Task status enums
├── config/
│   └── settings.py          # Configuration
├── utils/
│   ├── logging.py           # Logging system
│   └── helpers.py           # Common utilities
├── exceptions.py            # Exception classes
├── queue/                   # Message queue system
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
└── scripts/                 # NEW: Script management system
    ├── __init__.py
    ├── repository.py        # Repository integrations
    ├── cache_manager.py     # Caching and version control
    ├── metadata.py          # Script metadata handling
    └── downloader.py        # Script download orchestrator
```

### Key Requirements from INITIAL.md

- External repository for site-specific and task-specific scraping scripts
- Version-controlled caching and automatic updates
- Script metadata (dependencies, requirements)
- Support for HTTP scraping, captcha handling, and browser automation
- Child process isolation for security

## Implementation Blueprint

### Task 1: Script Metadata Model

```python
# scripts/metadata.py
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import json
import hashlib
from src.utils.logging import setup_logging

@dataclass
class ScriptMetadata:
    """스크립트 메타데이터 모델"""
    name: str
    version: str
    description: str
    author: str
    created_at: datetime
    updated_at: datetime

    # 의존성 정보
    python_version: str = ">=3.8"
    dependencies: List[str] = None
    system_requirements: List[str] = None

    # 실행 정보
    entry_point: str = "main.py"
    timeout: int = 300
    memory_limit: str = "512MB"

    # 추가 설정
    parameters: Dict[str, Any] = None
    tags: List[str] = None

    def __post_init__(self):
        """초기화 후 기본값 설정"""
        if self.dependencies is None:
            self.dependencies = []
        if self.system_requirements is None:
            self.system_requirements = []
        if self.parameters is None:
            self.parameters = {}
        if self.tags is None:
            self.tags = []

class MetadataParser:
    """스크립트 메타데이터 파서"""

    def __init__(self, settings):
        """
        메타데이터 파서 초기화

        Args:
            settings: 시스템 설정 객체
        """
        self.settings = settings
        self.logger = setup_logging(settings)

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
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata_dict = json.load(f)

            # 필수 필드 검증
            required_fields = ['name', 'version', 'description', 'author']
            for field in required_fields:
                if field not in metadata_dict:
                    raise ValueError(f"필수 필드 누락: {field}")

            # 날짜 파싱
            created_at = datetime.fromisoformat(metadata_dict.get('created_at', datetime.now().isoformat()))
            updated_at = datetime.fromisoformat(metadata_dict.get('updated_at', datetime.now().isoformat()))

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
            raise ValueError(f"메타데이터 JSON 파싱 오류: {e}")
        except Exception as e:
            raise ValueError(f"메타데이터 파싱 오류: {e}")

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
```

### Task 2: Repository Integration

```python
# scripts/repository.py
import asyncio
import aiohttp
import git
from typing import Optional, Dict, List
from pathlib import Path
from urllib.parse import urlparse
from src.utils.logging import setup_logging
from src.exceptions import ScriptNotFoundException

class RepositoryBase:
    """저장소 기본 클래스"""

    def __init__(self, settings):
        """저장소 기본 초기화"""
        self.settings = settings
        self.logger = setup_logging(settings)

    async def download_script(self, script_name: str, version: str = None) -> Path:
        """스크립트 다운로드 (추상 메서드)"""
        raise NotImplementedError("하위 클래스에서 구현해야 합니다")

    async def get_available_versions(self, script_name: str) -> List[str]:
        """사용 가능한 버전 목록 (추상 메서드)"""
        raise NotImplementedError("하위 클래스에서 구현해야 합니다")

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """최신 버전 조회 (추상 메서드)"""
        raise NotImplementedError("하위 클래스에서 구현해야 합니다")

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
                self.repo.remotes.origin.pull()
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
            self.local_repo_path.mkdir(parents=True, exist_ok=True)
            self.repo = git.Repo.clone_from(
                self.repository_url,
                self.local_repo_path,
                depth=1  # 얕은 복제로 성능 향상
            )
            self.logger.info(f"저장소 복제 완료: {self.repository_url}")
        except Exception as e:
            self.logger.error(f"저장소 복제 실패: {e}")
            raise ScriptNotFoundException(f"저장소 복제 실패: {e}")

    async def download_script(self, script_name: str, version: str = None) -> Path:
        """Git에서 스크립트 다운로드"""
        await self.clone_or_update_repo()

        script_path = self.local_repo_path / script_name
        if not script_path.exists():
            raise ScriptNotFoundException(f"스크립트를 찾을 수 없습니다: {script_name}")

        # 버전 체크아웃 (태그 기준)
        if version and self.repo:
            try:
                self.repo.git.checkout(f"v{version}")
                self.logger.info(f"버전 체크아웃: {version}")
            except Exception as e:
                self.logger.warning(f"버전 체크아웃 실패: {e}, 기본 브랜치 사용")

        return script_path

    async def get_available_versions(self, script_name: str) -> List[str]:
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

            return sorted(versions, reverse=True)
        except Exception as e:
            self.logger.error(f"버전 목록 조회 실패: {e}")
            return []

    async def get_latest_version(self, script_name: str) -> Optional[str]:
        """최신 버전 조회"""
        versions = await self.get_available_versions(script_name)
        return versions[0] if versions else None

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

    async def download_script(self, script_name: str, version: str = None) -> Path:
        """HTTP에서 스크립트 다운로드"""
        session = await self._get_session()

        # 버전 지정이 없으면 최신 버전 사용
        if not version:
            version = await self.get_latest_version(script_name)

        # 스크립트 URL 구성
        script_url = f"{self.base_url}/{script_name}/{version}"

        try:
            async with session.get(script_url) as response:
                if response.status == 200:
                    # 로컬 캐시 디렉토리 생성
                    cache_dir = Path(self.settings.script_cache_dir) / script_name / version
                    cache_dir.mkdir(parents=True, exist_ok=True)

                    # 압축 파일 다운로드 및 추출
                    content = await response.read()

                    # 간단한 경우: 단일 파일 다운로드
                    script_file = cache_dir / "main.py"
                    with open(script_file, 'wb') as f:
                        f.write(content)

                    self.logger.info(f"HTTP 스크립트 다운로드 완료: {script_name} v{version}")
                    return cache_dir
                else:
                    raise ScriptNotFoundException(f"스크립트 다운로드 실패: HTTP {response.status}")

        except Exception as e:
            self.logger.error(f"HTTP 스크립트 다운로드 오류: {e}")
            raise ScriptNotFoundException(f"HTTP 스크립트 다운로드 오류: {e}")

    async def get_available_versions(self, script_name: str) -> List[str]:
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
        versions = await self.get_available_versions(script_name)
        return versions[0] if versions else None

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
            raise ImportError("boto3 라이브러리가 필요합니다: pip install boto3")
        except Exception as e:
            self.logger.error(f"S3 초기화 실패: {e}")
            raise

    async def download_script(self, script_name: str, version: str = None) -> Path:
        """S3에서 스크립트 다운로드"""
        if not version:
            version = await self.get_latest_version(script_name)

        # S3 키 구성
        script_key = f"{self.prefix}{script_name}/{version}/"

        try:
            # 로컬 캐시 디렉토리 생성
            cache_dir = Path(self.settings.script_cache_dir) / script_name / version
            cache_dir.mkdir(parents=True, exist_ok=True)

            # S3에서 스크립트 파일들 나열
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=script_key
            )

            if 'Contents' not in response:
                raise ScriptNotFoundException(f"S3에서 스크립트를 찾을 수 없습니다: {script_name} v{version}")

            # 각 파일 다운로드
            for obj in response['Contents']:
                file_key = obj['Key']
                # 상대 경로 추출 (prefix 제거)
                relative_path = file_key[len(script_key):]

                if relative_path:  # 빈 경로 제외
                    local_file_path = cache_dir / relative_path
                    local_file_path.parent.mkdir(parents=True, exist_ok=True)

                    # 파일 다운로드
                    self.s3_client.download_file(
                        self.bucket_name,
                        file_key,
                        str(local_file_path)
                    )

            self.logger.info(f"S3 스크립트 다운로드 완료: {script_name} v{version}")
            return cache_dir

        except Exception as e:
            self.logger.error(f"S3 스크립트 다운로드 오류: {e}")
            raise ScriptNotFoundException(f"S3 스크립트 다운로드 오류: {e}")

    async def get_available_versions(self, script_name: str) -> List[str]:
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
```

### Task 3: Cache Manager

```python
# scripts/cache_manager.py
import asyncio
import json
import shutil
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime, timedelta
from src.scripts.metadata import ScriptMetadata, MetadataParser
from src.scripts.repository import RepositoryBase
from src.utils.logging import setup_logging
from src.utils.helpers import calculate_file_hash

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
        self.logger = setup_logging(settings)
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

    async def get_script(self, script_name: str, version: str = None) -> tuple[Path, ScriptMetadata]:
        """
        스크립트 가져오기 (캐시 우선)

        Args:
            script_name: 스크립트 이름
            version: 버전 (None이면 최신 버전)

        Returns:
            (스크립트 경로, 메타데이터) 튜플
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
            # 임시 디렉토리에 다운로드
            temp_path = await self.repository.download_script(script_name, version)

            # 캐시 디렉토리로 복사
            cache_path.mkdir(parents=True, exist_ok=True)

            if temp_path.is_file():
                # 단일 파일인 경우
                shutil.copy2(temp_path, cache_path / temp_path.name)
            else:
                # 디렉토리인 경우
                shutil.copytree(temp_path, cache_path, dirs_exist_ok=True)

            # 메타데이터 파싱
            metadata = self.metadata_parser.parse_metadata_file(metadata_path)

            # 캐시 정보 저장
            await self._save_cache_info(script_name, version, metadata)

            self.logger.info(f"스크립트 캐시 완료: {script_name} v{version}")
            return cache_path, metadata

        except Exception as e:
            self.logger.error(f"스크립트 캐시 오류: {e}")
            raise

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
            with open(cache_info_path, 'r') as f:
                cache_info = json.load(f)

            # 캐시 시간 검사 (24시간)
            cached_at = datetime.fromisoformat(cache_info['cached_at'])
            if datetime.now() - cached_at > timedelta(hours=24):
                return False

            # 파일 무결성 검사
            entry_point = cache_info.get('entry_point', 'main.py')
            entry_file = cache_path / entry_point

            if entry_file.exists():
                current_hash = calculate_file_hash(str(entry_file))
                return current_hash == cache_info.get('file_hash')

            return False

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
            'repository_type': type(self.repository).__name__
        }

        with open(cache_info_path, 'w') as f:
            json.dump(cache_info, f, indent=2)

    async def cleanup_old_cache(self, max_age_hours: int = 168) -> None:  # 7일
        """오래된 캐시 정리"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        for script_dir in self.cache_dir.iterdir():
            if script_dir.is_dir():
                for version_dir in script_dir.iterdir():
                    if version_dir.is_dir():
                        cache_info_path = version_dir / ".cache_info"

                        if cache_info_path.exists():
                            try:
                                with open(cache_info_path, 'r') as f:
                                    cache_info = json.load(f)

                                cached_at = datetime.fromisoformat(cache_info['cached_at'])
                                if cached_at < cutoff_time:
                                    shutil.rmtree(version_dir)
                                    self.logger.info(f"오래된 캐시 정리: {script_dir.name} v{version_dir.name}")

                            except Exception as e:
                                self.logger.error(f"캐시 정리 오류: {e}")

    async def get_cached_scripts(self) -> List[Dict]:
        """캐시된 스크립트 목록"""
        cached_scripts = []

        for script_dir in self.cache_dir.iterdir():
            if script_dir.is_dir():
                for version_dir in script_dir.iterdir():
                    if version_dir.is_dir():
                        cache_info_path = version_dir / ".cache_info"

                        if cache_info_path.exists():
                            try:
                                with open(cache_info_path, 'r') as f:
                                    cache_info = json.load(f)

                                cached_scripts.append({
                                    'script_name': cache_info['script_name'],
                                    'version': cache_info['version'],
                                    'cached_at': cache_info['cached_at'],
                                    'size': sum(f.stat().st_size for f in version_dir.rglob('*') if f.is_file())
                                })

                            except Exception as e:
                                self.logger.error(f"캐시 정보 읽기 오류: {e}")

        return cached_scripts
```

## Integration Points

### Environment Variables (.env) - Updated

```bash
# Script Repository Configuration
SCRIPT_REPOSITORY_TYPE=git  # git, http, s3
SCRIPT_REPOSITORY_URL=https://github.com/your-org/scraping-scripts  # For git/http
SCRIPT_CACHE_DIR=./cache/scripts
SCRIPT_CACHE_MAX_AGE=168  # hours

# S3 Configuration (when SCRIPT_REPOSITORY_TYPE=s3)
S3_BUCKET_NAME=your-scraping-scripts-bucket
S3_REGION=ap-northeast-2
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_PREFIX=scripts/

# Script Execution
SCRIPT_TIMEOUT=300
SCRIPT_MEMORY_LIMIT=512MB

# Existing from previous phases...
```

### Project Structure - Updated

```
src/
├── models/
│   ├── base.py              # From Phase 1
│   └── enums.py             # From Phase 1
├── config/
│   └── settings.py          # Updated with script settings
├── utils/
│   ├── logging.py           # From Phase 1
│   └── helpers.py           # From Phase 1 (updated with file hash)
├── exceptions.py            # From Phase 1 (updated with script exceptions)
├── queue/                   # From Phase 2
│   ├── redis_queue.py
│   ├── task_manager.py
│   └── worker_monitor.py
└── scripts/                 # NEW
    ├── __init__.py
    ├── metadata.py          # Script metadata model and parser
    ├── repository.py        # Repository integrations (Git, HTTP)
    ├── cache_manager.py     # Caching and version control
    └── downloader.py        # Main orchestrator
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Type checking and linting
uv run mypy src/scripts/
uv run ruff check src/scripts/ --fix

# Expected: No errors. All async functions properly typed.
```

### Level 2: Unit Tests

```python
# tests/test_scripts.py
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from src.scripts.metadata import ScriptMetadata, MetadataParser
from src.scripts.cache_manager import CacheManager
from src.scripts.repository import GitRepository, HttpRepository
from src.config.settings import Settings

class TestScriptMetadata:
    """스크립트 메타데이터 테스트"""

    def test_metadata_creation(self):
        """메타데이터 생성 테스트"""
        metadata = ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert metadata.name == "test_scraper"
        assert metadata.version == "1.0.0"
        assert metadata.dependencies == []
        assert metadata.timeout == 300

class TestMetadataParser:
    """메타데이터 파서 테스트"""

    @pytest.fixture
    def parser(self):
        """파서 픽스처"""
        settings = Settings()
        return MetadataParser(settings)

    @pytest.fixture
    def temp_metadata_file(self):
        """임시 메타데이터 파일"""
        metadata = {
            "name": "test_scraper",
            "version": "1.0.0",
            "description": "테스트 스크래퍼",
            "author": "Test Author",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "dependencies": ["requests", "beautifulsoup4"],
            "entry_point": "main.py"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(metadata, f)
            return Path(f.name)

    def test_parse_metadata_file(self, parser, temp_metadata_file):
        """메타데이터 파일 파싱 테스트"""
        metadata = parser.parse_metadata_file(temp_metadata_file)

        assert metadata.name == "test_scraper"
        assert metadata.version == "1.0.0"
        assert "requests" in metadata.dependencies
        assert metadata.entry_point == "main.py"

        # 파일 정리
        temp_metadata_file.unlink()

    def test_validate_metadata(self, parser):
        """메타데이터 유효성 검증 테스트"""
        valid_metadata = ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert parser.validate_metadata(valid_metadata) is True

        # 잘못된 버전 형식
        invalid_metadata = ScriptMetadata(
            name="test_scraper",
            version="invalid",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert parser.validate_metadata(invalid_metadata) is False

class TestCacheManager:
    """캐시 매니저 테스트"""

    @pytest.fixture
    async def cache_manager(self):
        """캐시 매니저 픽스처"""
        settings = Settings()
        settings.script_cache_dir = tempfile.mkdtemp()

        repository = AsyncMock()
        repository.get_latest_version.return_value = "1.0.0"
        repository.download_script.return_value = Path("test_script.py")

        return CacheManager(settings, repository)

    @pytest.mark.asyncio
    async def test_cache_path_generation(self, cache_manager):
        """캐시 경로 생성 테스트"""
        cache_path = cache_manager._get_cache_path("test_scraper", "1.0.0")

        expected_path = Path(cache_manager.cache_dir) / "test_scraper" / "1.0.0"
        assert cache_path == expected_path
```

```bash
# Run script tests
uv run pytest tests/test_scripts.py -v

# Run with Git integration test (requires Git repository)
uv run pytest tests/test_scripts_integration.py -v
```

### Level 3: Integration Test

```python
# tests/test_scripts_integration.py
@pytest.mark.asyncio
async def test_full_script_workflow():
    """전체 스크립트 워크플로우 테스트"""
    settings = Settings()

    # Git 저장소 설정 (테스트용)
    git_repo = GitRepository(settings, "https://github.com/test/scripts.git")
    cache_manager = CacheManager(settings, git_repo)

    # 스크립트 가져오기
    script_path, metadata = await cache_manager.get_script("example_scraper", "1.0.0")

    # 검증
    assert script_path.exists()
    assert metadata.name == "example_scraper"
    assert metadata.version == "1.0.0"

    # 캐시 확인
    cached_scripts = await cache_manager.get_cached_scripts()
    assert len(cached_scripts) > 0
    assert cached_scripts[0]['script_name'] == "example_scraper"
```

## Final Validation Checklist

- [ ] Scripts can be downloaded from external repositories
- [ ] Version comparison and caching work correctly
- [ ] Metadata is properly parsed and validated
- [ ] Cache cleanup functions correctly
- [ ] All unit tests pass: `uv run pytest tests/test_scripts.py -v`
- [ ] Integration tests pass: `uv run pytest tests/test_scripts_integration.py -v`
- [ ] No type errors: `uv run mypy src/scripts/`
- [ ] No linting errors: `uv run ruff check src/scripts/`
- [ ] File integrity verification works
- [ ] Korean logging messages are properly formatted

## Anti-Patterns to Avoid

- ❌ Don't download scripts synchronously - use async operations
- ❌ Don't store scripts without version control
- ❌ Don't ignore script metadata - validate before execution
- ❌ Don't cache scripts indefinitely - implement cleanup
- ❌ Don't skip file integrity checks - verify checksums
- ❌ Don't hardcode repository URLs - use configuration
