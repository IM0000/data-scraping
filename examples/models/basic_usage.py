#!/usr/bin/env python3
"""
핵심 모델 사용 예제

이 파일은 스크래핑 시스템의 핵심 모델들을 사용하는 방법을 보여줍니다.
"""

from datetime import datetime
from src.models.base import ScrapingRequest, ScrapingResponse, ScriptInfo, WorkerInfo
from src.models.enums import TaskStatus, ScriptRepositoryType
from src.config.settings import get_settings
from src.utils.logging import setup_logging
from src.utils.helpers import generate_task_id, calculate_string_hash


def main():
    """기본 사용 예제 실행"""
    print("=== 핵심 모델 사용 예제 ===\n")
    
    # 1. 설정 로드
    print("1. 설정 시스템 초기화")
    settings = get_settings()
    print(f"   Redis 호스트: {settings.redis_host}")
    print(f"   스크립트 저장소: {settings.script_repository_type.value}")
    
    # 2. 로깅 시스템 초기화
    print("\n2. 로깅 시스템 초기화")
    logger = setup_logging(settings)
    logger.info("시스템 초기화 완료")
    
    # 3. 스크래핑 요청 생성
    print("\n3. 스크래핑 요청 생성")
    request = ScrapingRequest(
        script_name="example_scraper",
        script_version="1.0.0",
        parameters={
            "url": "https://example.com",
            "selector": ".content",
            "max_pages": 10
        },
        timeout=300
    )
    
    print(f"   요청 ID: {request.request_id}")
    print(f"   스크립트: {request.script_name} v{request.script_version}")
    print(f"   매개변수: {request.parameters}")
    logger.info(f"스크래핑 요청 생성: {request.script_name}")
    
    # 4. 작업 ID 생성
    print("\n4. 작업 ID 생성")
    task_id = generate_task_id()
    print(f"   작업 ID: {task_id}")
    
    # 5. 스크립트 정보 생성
    print("\n5. 스크립트 정보 생성")
    script_content = """
def scrape_data(url, selector, max_pages=5):
    # 실제 스크래핑 로직
    return {"data": "scraped content"}
"""
    script_hash = calculate_string_hash(script_content)
    
    script_info = ScriptInfo(
        name="example_scraper",
        version="1.0.0",
        file_path="/cache/scripts/example_scraper.py",
        file_hash=script_hash,
        modified_at=datetime.now(),
        cached_at=datetime.now()
    )
    
    print(f"   스크립트: {script_info.name}")
    print(f"   해시: {script_info.file_hash[:16]}...")
    print(f"   경로: {script_info.file_path}")
    
    # 6. 워커 정보 생성
    print("\n6. 워커 정보 생성")
    worker_info = WorkerInfo(
        worker_id="worker-001",
        status="active",
        current_tasks=1,
        max_tasks=4
    )
    
    print(f"   워커 ID: {worker_info.worker_id}")
    print(f"   상태: {worker_info.status}")
    print(f"   작업 수: {worker_info.current_tasks}/{worker_info.max_tasks}")
    
    # 7. 성공 응답 생성
    print("\n7. 성공 응답 생성")
    response = ScrapingResponse(
        request_id=request.request_id,
        status=TaskStatus.COMPLETED,
        data={
            "title": "Example Page",
            "content": "This is example content",
            "links": ["https://example.com/page1", "https://example.com/page2"],
            "scraped_at": datetime.now().isoformat()
        },
        execution_time=25.5,
        completed_at=datetime.now(),
        error=None
    )
    
    print(f"   응답 ID: {response.request_id}")
    print(f"   상태: {response.status.value}")
    print(f"   실행 시간: {response.execution_time}초")
    print(f"   데이터 항목: {len(response.data) if response.data else 0}")
    logger.info(f"스크래핑 완료: {response.execution_time}초")
    
    # 8. 오류 응답 생성 예제
    print("\n8. 오류 응답 생성 예제")
    error_response = ScrapingResponse(
        request_id=request.request_id,
        status=TaskStatus.FAILED,
        error="대상 웹사이트에 접근할 수 없습니다",
        execution_time=5.0,
        completed_at=datetime.now(),
        data=None
    )
    
    print(f"   오류 상태: {error_response.status.value}")
    print(f"   오류 메시지: {error_response.error}")
    logger.error(f"스크래핑 실패: {error_response.error}")
    
    # 9. 열거형 사용 예제
    print("\n9. 열거형 사용 예제")
    print("   작업 상태:")
    for status in TaskStatus:
        print(f"     - {status.value}")
    
    print("   저장소 타입:")
    for repo_type in ScriptRepositoryType:
        print(f"     - {repo_type.value}")
    
    print("\n=== 예제 완료 ===")


if __name__ == "__main__":
    main() 