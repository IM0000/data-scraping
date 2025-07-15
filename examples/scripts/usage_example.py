#!/usr/bin/env python3
"""
스크립트 관리 시스템 사용 예제

이 파일은 Phase 3에서 구현된 스크립트 관리 시스템의 사용법을 보여줍니다.
"""

import asyncio
import tempfile
from pathlib import Path

from src.scripts import ScriptDownloader, get_script, list_available_versions, cleanup_old_cache
from src.config.settings import Settings


async def basic_usage_example():
    """기본 사용법 예제"""
    print("=== 스크립트 관리 시스템 기본 사용법 ===")
    
    # 설정 생성 (테스트용)
    settings = Settings()
    settings.script_cache_dir = tempfile.mkdtemp()
    from src.models.enums import ScriptRepositoryType
    settings.script_repository_type = ScriptRepositoryType.GIT
    settings.script_repository_url = "https://github.com/example/scripts.git"
    
    # 스크립트 다운로더 생성
    async with ScriptDownloader(settings) as downloader:
        # 사용 가능한 버전 목록 조회
        print("\n1. 버전 목록 조회")
        versions = await downloader.get_available_versions("example_scraper")
        print(f"사용 가능한 버전: {versions}")
        
        # 최신 버전 조회
        latest = await downloader.get_latest_version("example_scraper")
        print(f"최신 버전: {latest}")
        
        # 캐시 통계 확인
        print("\n2. 캐시 통계")
        stats = await downloader.get_cache_stats()
        print(f"캐시 디렉토리: {stats['cache_directory']}")
        print(f"스크립트 수: {stats['script_count']}")
        print(f"버전 수: {stats['version_count']}")
        
        # 캐시된 스크립트 목록
        print("\n3. 캐시된 스크립트")
        cached = await downloader.list_cached_scripts()
        for script in cached:
            print(f"- {script['script_name']} v{script['version']} ({script['size']} bytes)")


async def convenience_functions_example():
    """편의 함수 사용 예제"""
    print("\n=== 편의 함수 사용 예제 ===")
    
    try:
        # 편의 함수로 스크립트 가져오기
        script_path, metadata = await get_script("example_scraper", "1.0.0")
        print(f"스크립트 경로: {script_path}")
        print(f"스크립트 이름: {metadata.name}")
        print(f"엔트리 포인트: {metadata.entry_point}")
        
        # 편의 함수로 버전 목록 조회
        versions = await list_available_versions("example_scraper")
        print(f"사용 가능한 버전: {versions}")
        
        # 오래된 캐시 정리
        await cleanup_old_cache(24)  # 24시간 이상 된 캐시 정리
        print("캐시 정리 완료")
        
    except Exception as e:
        print(f"편의 함수 사용 중 오류: {e}")


async def cache_management_example():
    """캐시 관리 예제"""
    print("\n=== 캐시 관리 예제 ===")
    
    settings = Settings()
    settings.script_cache_dir = tempfile.mkdtemp()
    
    async with ScriptDownloader(settings) as downloader:
        # 스크립트 유효성 검증
        print("\n1. 스크립트 유효성 검증")
        is_valid = await downloader.validate_script("example_scraper", "1.0.0")
        print(f"스크립트 유효성: {is_valid}")
        
        # 스크립트 정보 조회
        print("\n2. 스크립트 정보 조회")
        info = await downloader.get_script_info("example_scraper", "1.0.0")
        if info:
            print(f"스크립트: {info['name']} v{info['version']}")
            print(f"설명: {info['description']}")
            print(f"작성자: {info['author']}")
            print(f"의존성: {info['dependencies']}")
        
        # 캐시 무효화
        print("\n3. 캐시 무효화")
        await downloader.invalidate_cache("example_scraper", "1.0.0")
        print("특정 버전 캐시 무효화 완료")
        
        await downloader.invalidate_cache("example_scraper")
        print("전체 버전 캐시 무효화 완료")
        
        # 캐시 정리
        print("\n4. 캐시 정리")
        await downloader.cleanup_cache(1)  # 1시간 이상 된 캐시 정리
        print("캐시 정리 완료")


def sync_wrapper():
    """동기 함수에서 비동기 함수 호출을 위한 래퍼"""
    print("스크립트 관리 시스템 예제 시작")
    
    try:
        # 비동기 함수들 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 기본 사용법
        loop.run_until_complete(basic_usage_example())
        
        # 편의 함수 사용
        loop.run_until_complete(convenience_functions_example())
        
        # 캐시 관리
        loop.run_until_complete(cache_management_example())
        
    except Exception as e:
        print(f"예제 실행 중 오류 발생: {e}")
    finally:
        loop.close()
        print("\n예제 실행 완료")


if __name__ == "__main__":
    sync_wrapper() 