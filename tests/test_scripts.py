"""
스크립트 관리 시스템 테스트

PRP Phase 3의 검증 요구사항에 따른 테스트를 수행합니다.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.settings import Settings
from src.scripts.cache_manager import CacheManager
from src.scripts.downloader import ScriptDownloader
from src.scripts.metadata import MetadataParser, ScriptMetadata
from src.scripts.repository import GitRepository, HttpRepository


class TestScriptMetadata:
    """스크립트 메타데이터 테스트"""
    
    def test_metadata_creation(self):
        """메타데이터 생성 테스트"""
        now = datetime.now()
        metadata = ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=now,
            updated_at=now
        )
        
        assert metadata.name == "test_scraper"
        assert metadata.version == "1.0.0"
        assert metadata.dependencies == []
        assert metadata.timeout == 300
        assert metadata.entry_point == "main.py"
        assert metadata.python_version == ">=3.8"
    
    def test_metadata_with_custom_values(self):
        """커스텀 값을 가진 메타데이터 테스트"""
        now = datetime.now()
        metadata = ScriptMetadata(
            name="custom_scraper",
            version="2.1.0",
            description="커스텀 스크래퍼",
            author="Custom Author",
            created_at=now,
            updated_at=now,
            dependencies=["requests", "beautifulsoup4"],
            timeout=600,
            entry_point="scraper.py"
        )
        
        assert len(metadata.dependencies) == 2
        assert "requests" in metadata.dependencies
        assert metadata.timeout == 600
        assert metadata.entry_point == "scraper.py"


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
            "entry_point": "main.py",
            "timeout": 300
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(metadata, f, ensure_ascii=False)
            return Path(f.name)
    
    def test_parse_metadata_file(self, parser, temp_metadata_file):
        """메타데이터 파일 파싱 테스트"""
        try:
            metadata = parser.parse_metadata_file(temp_metadata_file)
            
            assert metadata.name == "test_scraper"
            assert metadata.version == "1.0.0"
            assert "requests" in metadata.dependencies
            assert metadata.entry_point == "main.py"
            assert metadata.timeout == 300
        finally:
            # 파일 정리
            temp_metadata_file.unlink()
    
    def test_parse_metadata_file_not_found(self, parser):
        """존재하지 않는 메타데이터 파일 테스트"""
        non_existent_file = Path("/non/existent/file.json")
        
        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse_metadata_file(non_existent_file)
        
        assert "메타데이터 파일을 찾을 수 없습니다" in str(exc_info.value)
    
    def test_validate_metadata_valid(self, parser):
        """유효한 메타데이터 검증 테스트"""
        now = datetime.now()
        valid_metadata = ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=now,
            updated_at=now
        )
        
        assert parser.validate_metadata(valid_metadata) is True
    
    def test_validate_metadata_invalid_version(self, parser):
        """잘못된 버전 형식 메타데이터 검증 테스트"""
        now = datetime.now()
        invalid_metadata = ScriptMetadata(
            name="test_scraper",
            version="invalid",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=now,
            updated_at=now
        )
        
        assert parser.validate_metadata(invalid_metadata) is False
    
    def test_validate_metadata_invalid_entry_point(self, parser):
        """잘못된 엔트리 포인트 메타데이터 검증 테스트"""
        now = datetime.now()
        invalid_metadata = ScriptMetadata(
            name="test_scraper",
            version="1.0.0",
            description="테스트 스크래퍼",
            author="Test Author",
            created_at=now,
            updated_at=now,
            entry_point="main.txt"  # 잘못된 확장자
        )
        
        assert parser.validate_metadata(invalid_metadata) is False
    
    def test_create_sample_metadata(self, parser):
        """샘플 메타데이터 생성 테스트"""
        sample = parser.create_sample_metadata("example_scraper")
        
        assert sample["name"] == "example_scraper"
        assert sample["version"] == "1.0.0"
        assert "dependencies" in sample
        assert "parameters" in sample
        assert sample["entry_point"] == "main.py"


class TestCacheManager:
    """캐시 매니저 테스트"""
    
    @pytest.fixture
    def mock_settings(self):
        """모킹된 설정"""
        settings = MagicMock()
        settings.script_cache_dir = tempfile.mkdtemp()
        return settings
    
    @pytest.fixture
    def mock_repository(self):
        """모킹된 저장소"""
        repository = AsyncMock()
        repository.get_latest_version.return_value = "1.0.0"
        
        # 임시 스크립트 파일 생성
        temp_dir = Path(tempfile.mkdtemp())
        script_file = temp_dir / "main.py"
        script_file.write_text("print('Hello, World!')")
        
        # 메타데이터 파일 생성
        metadata_file = temp_dir / "metadata.json"
        metadata_content = {
            "name": "test_scraper",
            "version": "1.0.0",
            "description": "테스트 스크래퍼",
            "author": "Test Author",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "entry_point": "main.py"
        }
        metadata_file.write_text(json.dumps(metadata_content, ensure_ascii=False))
        
        repository.download_script.return_value = temp_dir
        return repository
    
    @pytest.fixture
    def cache_manager(self, mock_settings, mock_repository):
        """캐시 매니저 픽스처"""
        return CacheManager(mock_settings, mock_repository)
    
    def test_cache_path_generation(self, cache_manager):
        """캐시 경로 생성 테스트"""
        cache_path = cache_manager._get_cache_path("test_scraper", "1.0.0")
        
        expected_path = Path(cache_manager.cache_dir) / "test_scraper" / "1.0.0"
        assert cache_path == expected_path
    
    def test_metadata_path_generation(self, cache_manager):
        """메타데이터 경로 생성 테스트"""
        metadata_path = cache_manager._get_metadata_path("test_scraper", "1.0.0")
        
        expected_path = Path(cache_manager.cache_dir) / "test_scraper" / "1.0.0" / "metadata.json"
        assert metadata_path == expected_path
    
    @pytest.mark.asyncio
    async def test_get_script_cache_miss(self, cache_manager, mock_repository):
        """캐시 미스 시 스크립트 가져오기 테스트"""
        script_path, metadata = await cache_manager.get_script("test_scraper", "1.0.0")
        
        assert script_path.exists()
        assert metadata.name == "test_scraper"
        assert metadata.version == "1.0.0"
        
        # 저장소에서 다운로드가 호출되었는지 확인
        mock_repository.download_script.assert_called_once_with("test_scraper", "1.0.0")
    
    @pytest.mark.asyncio
    async def test_get_script_latest_version(self, cache_manager, mock_repository):
        """최신 버전 스크립트 가져오기 테스트"""
        script_path, metadata = await cache_manager.get_script("test_scraper")
        
        assert script_path.exists()
        assert metadata.version == "1.0.0"
        
        # 최신 버전 조회가 호출되었는지 확인
        mock_repository.get_latest_version.assert_called_once_with("test_scraper")
    
    @pytest.mark.asyncio
    async def test_get_cached_scripts_empty(self, cache_manager):
        """빈 캐시 목록 테스트"""
        cached_scripts = await cache_manager.get_cached_scripts()
        assert cached_scripts == []
    
    @pytest.mark.asyncio
    async def test_cache_cleanup(self, cache_manager):
        """캐시 정리 테스트"""
        # 캐시 정리는 오래된 항목이 없으면 아무것도 하지 않음
        await cache_manager.cleanup_old_cache(1)  # 1시간
        
        # 오류가 발생하지 않으면 성공
        assert True
    
    @pytest.mark.asyncio
    async def test_cache_stats_empty(self, cache_manager):
        """빈 캐시 통계 테스트"""
        stats = await cache_manager.get_cache_stats()
        
        assert stats['total_size_bytes'] == 0
        assert stats['script_count'] == 0
        assert stats['version_count'] == 0
        assert 'cache_directory' in stats


class TestScriptDownloader:
    """스크립트 다운로더 테스트"""
    
    @pytest.fixture
    def mock_settings(self):
        """모킹된 설정"""
        settings = MagicMock()
        settings.script_repository_type.value = "git"
        settings.script_repository_url = "https://github.com/test/repo.git"
        settings.script_cache_dir = tempfile.mkdtemp()
        return settings
    
    @patch('src.scripts.downloader.GitRepository')
    def test_downloader_initialization_git(self, mock_git_repo, mock_settings):
        """Git 저장소로 다운로더 초기화 테스트"""
        from src.models.enums import ScriptRepositoryType
        mock_settings.script_repository_type = ScriptRepositoryType.GIT
        
        downloader = ScriptDownloader(mock_settings)
        
        assert downloader.settings == mock_settings
        mock_git_repo.assert_called_once_with(mock_settings, mock_settings.script_repository_url)
    
    @patch('src.scripts.downloader.HttpRepository')
    def test_downloader_initialization_http(self, mock_http_repo, mock_settings):
        """HTTP 저장소로 다운로더 초기화 테스트"""
        from src.models.enums import ScriptRepositoryType
        mock_settings.script_repository_type = ScriptRepositoryType.HTTP
        
        downloader = ScriptDownloader(mock_settings)
        
        assert downloader.settings == mock_settings
        mock_http_repo.assert_called_once_with(mock_settings, mock_settings.script_repository_url)
    
    def test_downloader_invalid_repository_type(self, mock_settings):
        """지원하지 않는 저장소 타입 테스트"""
        mock_settings.script_repository_type = "invalid"
        
        with pytest.raises(ValueError) as exc_info:
            ScriptDownloader(mock_settings)
        
        assert "지원하지 않는 저장소 타입" in str(exc_info.value)


class TestRepositoryIntegration:
    """저장소 통합 테스트 (모킹된 환경)"""
    
    @pytest.fixture
    def mock_settings(self):
        """모킹된 설정"""
        settings = MagicMock()
        settings.script_cache_dir = tempfile.mkdtemp()
        return settings
    
    @patch('git.Repo')
    def test_git_repository_initialization(self, mock_repo, mock_settings):
        """Git 저장소 초기화 테스트"""
        repository_url = "https://github.com/test/repo.git"
        git_repo = GitRepository(mock_settings, repository_url)
        
        assert git_repo.repository_url == repository_url
        assert git_repo.settings == mock_settings
    
    @patch('aiohttp.ClientSession')
    def test_http_repository_initialization(self, mock_session, mock_settings):
        """HTTP 저장소 초기화 테스트"""
        base_url = "https://api.example.com"
        http_repo = HttpRepository(mock_settings, base_url)
        
        assert http_repo.base_url == base_url
        assert http_repo.settings == mock_settings
        assert http_repo.session is None  # 아직 세션이 생성되지 않음


# 편의 함수 테스트
class TestConvenienceFunctions:
    """편의 함수 테스트"""
    
    @patch('src.scripts.downloader.ScriptDownloader')
    @pytest.mark.asyncio
    async def test_get_script_function(self, mock_downloader_class):
        """get_script 편의 함수 테스트"""
        from src.scripts.downloader import get_script
        
        # 모킹된 다운로더 인스턴스 설정
        mock_downloader = AsyncMock()
        mock_downloader.get_script.return_value = ("/path/to/script", MagicMock())
        mock_downloader_class.return_value.__aenter__.return_value = mock_downloader
        
        # 함수 호출
        result = await get_script("test_script", "1.0.0")
        
        # 검증
        assert result is not None
        mock_downloader.get_script.assert_called_once_with("test_script", "1.0.0")
    
    @patch('src.scripts.downloader.ScriptDownloader')
    @pytest.mark.asyncio
    async def test_list_available_versions_function(self, mock_downloader_class):
        """list_available_versions 편의 함수 테스트"""
        from src.scripts.downloader import list_available_versions
        
        # 모킹된 다운로더 인스턴스 설정
        mock_downloader = AsyncMock()
        mock_downloader.get_available_versions.return_value = ["1.0.0", "1.1.0"]
        mock_downloader_class.return_value.__aenter__.return_value = mock_downloader
        
        # 함수 호출
        versions = await list_available_versions("test_script")
        
        # 검증
        assert versions == ["1.0.0", "1.1.0"]
        mock_downloader.get_available_versions.assert_called_once_with("test_script")


# 통합 테스트
class TestIntegration:
    """전체 시스템 통합 테스트"""
    
    @pytest.fixture
    def integration_settings(self):
        """통합 테스트용 설정"""
        settings = Settings()
        settings.script_cache_dir = tempfile.mkdtemp()
        return settings
    
    @pytest.mark.asyncio
    async def test_full_workflow_mock(self, integration_settings):
        """모킹된 환경에서 전체 워크플로우 테스트"""
        # 실제 저장소 대신 모킹된 저장소 사용
        mock_repository = AsyncMock()
        mock_repository.get_latest_version.return_value = "1.0.0"
        
        # 임시 스크립트 디렉토리 생성
        temp_dir = Path(tempfile.mkdtemp())
        script_file = temp_dir / "main.py"
        script_file.write_text("print('Hello from script!')")
        
        metadata_file = temp_dir / "metadata.json"
        metadata_content = {
            "name": "test_script",
            "version": "1.0.0",
            "description": "테스트 스크립트",
            "author": "Test Team",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "entry_point": "main.py"
        }
        metadata_file.write_text(json.dumps(metadata_content, ensure_ascii=False))
        
        mock_repository.download_script.return_value = temp_dir
        
        # 캐시 매니저 생성
        cache_manager = CacheManager(integration_settings, mock_repository)
        
        try:
            # 스크립트 가져오기
            script_path, metadata = await cache_manager.get_script("test_script")
            
            # 검증
            assert script_path.exists()
            assert metadata.name == "test_script"
            assert metadata.version == "1.0.0"
            
            # 엔트리 포인트 파일 존재 확인
            entry_file = script_path / metadata.entry_point
            assert entry_file.exists()
            
            # 캐시 통계 확인
            stats = await cache_manager.get_cache_stats()
            assert stats['script_count'] >= 1
            assert stats['version_count'] >= 1
            
        finally:
            # 임시 파일 정리
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if Path(integration_settings.script_cache_dir).exists():
                shutil.rmtree(integration_settings.script_cache_dir) 