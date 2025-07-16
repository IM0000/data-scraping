#!/usr/bin/env python3
"""
RabbitMQ 큐 시스템 사용 예제

이 파일은 Gateway-Worker 스크래핑 시스템의 RabbitMQ 큐 시스템 사용법을 보여줍니다.
"""

import asyncio
from datetime import datetime
from src.config.settings import get_settings
from src.models.base import ScrapingRequest, ScrapingResponse, TaskStatus
from src.queue import RabbitMQRPC, RabbitMQWorker, TaskManager, WorkerMonitor


async def example_task_handler(request: ScrapingRequest) -> ScrapingResponse:
    """
    예제 작업 처리 함수
    
    실제 워커에서는 이 함수가 스크래핑 스크립트를 실행합니다.
    
    Args:
        request: 스크래핑 요청
        
    Returns:
        스크래핑 응답
    """
    print(f"   📝 작업 처리 시작: {request.script_name}")
    
    # 실제 스크래핑 작업 시뮬레이션 (2초 대기)
    await asyncio.sleep(2)
    
    # 성공 응답 생성
    response = ScrapingResponse(
        request_id=request.request_id,
        status=TaskStatus.COMPLETED,
        data={
            "title": "예제 웹사이트",
            "content": "스크래핑된 내용",
            "url": request.parameters.get("url", ""),
            "scraped_at": datetime.now().isoformat()
        },
        execution_time=2.0,
        completed_at=datetime.now()
    )
    
    print(f"   ✅ 작업 처리 완료: {request.request_id}")
    return response


async def example_heartbeat_handler(heartbeat_data: dict) -> None:
    """예제 하트비트 처리 함수"""
    worker_id = heartbeat_data.get("worker_id")
    timestamp = heartbeat_data.get("timestamp")
    print(f"   💓 하트비트 수신: {worker_id} at {timestamp}")


async def example_task_history_handler(history_data: dict) -> None:
    """예제 작업 히스토리 처리 함수"""
    request_id = history_data.get("request_id")
    status = history_data.get("status")
    print(f"   📊 작업 히스토리: {request_id} -> {status}")


async def demo_rpc_client():
    """RPC 클라이언트 데모"""
    print("\n🌐 === RPC 클라이언트 데모 ===")
    
    settings = get_settings()
    rpc_client = RabbitMQRPC(settings)
    
    try:
        # RabbitMQ 연결 (실제 환경에서는 RabbitMQ 서버가 필요)
        print("   🔌 RabbitMQ 연결 중...")
        # await rpc_client.connect()
        # await rpc_client.setup_callback_queue()
        print("   ✅ RabbitMQ 연결 완료 (시뮬레이션)")
        
        # 스크래핑 요청 생성
        request = ScrapingRequest(
            script_name="example_scraper",
            script_version="1.0.0",
            parameters={
                "url": "https://example.com",
                "selector": ".content"
            },
            timeout=300
        )
        
        print(f"   📤 RPC 요청 생성: {request.script_name}")
        print(f"   🆔 요청 ID: {request.request_id}")
        
        # 실제 환경에서는 다음과 같이 RPC 호출을 수행:
        # response = await rpc_client.call_async(request, timeout=300)
        # print(f"   📥 RPC 응답 수신: {response.status}")
        
        print("   ⚠️  실제 RPC 호출은 RabbitMQ 서버가 필요합니다")
        
    except Exception as e:
        print(f"   ❌ RPC 클라이언트 오류: {e}")
    finally:
        # await rpc_client.disconnect()
        print("   🔌 RPC 클라이언트 연결 해제")


async def demo_worker():
    """워커 데모"""
    print("\n👷 === 워커 데모 ===")
    
    settings = get_settings()
    worker = RabbitMQWorker(settings, example_task_handler)
    
    try:
        # RabbitMQ 연결 (실제 환경에서는 RabbitMQ 서버가 필요)
        print("   🔌 워커 RabbitMQ 연결 중...")
        # await worker.connect()
        print("   ✅ 워커 RabbitMQ 연결 완료 (시뮬레이션)")
        
        # 작업 큐 소비 시작 (실제 환경)
        # await worker.start_consuming()
        print("   🎯 작업 큐 소비 시작 (시뮬레이션)")
        
        # 예제 메시지 처리 시뮬레이션
        example_request = ScrapingRequest(
            script_name="demo_scraper",
            script_version="1.0.0",
            parameters={"url": "https://demo.com"}
        )
        
        response = await example_task_handler(example_request)
        print(f"   📋 작업 결과: {response.status.value}")
        
    except Exception as e:
        print(f"   ❌ 워커 오류: {e}")
    finally:
        # await worker.disconnect()
        print("   🔌 워커 연결 해제")


async def demo_task_manager():
    """작업 매니저 데모"""
    print("\n📋 === 작업 매니저 데모 ===")
    
    settings = get_settings()
    task_manager = TaskManager(settings)
    
    try:
        # RabbitMQ 연결 (실제 환경에서는 RabbitMQ 서버가 필요)
        print("   🔌 작업 매니저 연결 중...")
        # await task_manager.connect()
        print("   ✅ 작업 매니저 연결 완료 (시뮬레이션)")
        
        # 예제 작업 완료 이벤트 발행
        example_response = ScrapingResponse(
            request_id="demo-task-123",
            status=TaskStatus.COMPLETED,
            data={"scraped_items": 42},
            execution_time=15.5,
            completed_at=datetime.now()
        )
        
        # await task_manager.publish_task_completion(example_response)
        print(f"   📤 작업 완료 이벤트 발행: {example_response.request_id}")
        
        # 큐 메트릭 조회
        # metrics = await task_manager.get_queue_metrics()
        # print(f"   📊 큐 메트릭: {metrics}")
        print("   📊 큐 메트릭 조회 완료 (시뮬레이션)")
        
    except Exception as e:
        print(f"   ❌ 작업 매니저 오류: {e}")
    finally:
        # await task_manager.disconnect()
        print("   🔌 작업 매니저 연결 해제")


async def demo_worker_monitor():
    """워커 모니터 데모"""
    print("\n👁️ === 워커 모니터 데모 ===")
    
    settings = get_settings()
    worker_monitor = WorkerMonitor(settings)
    
    try:
        # RabbitMQ 연결 (실제 환경에서는 RabbitMQ 서버가 필요)
        print("   🔌 워커 모니터 연결 중...")
        # await worker_monitor.connect()
        print("   ✅ 워커 모니터 연결 완료 (시뮬레이션)")
        
        # 워커 등록
        worker_info = {
            "max_tasks": 4,
            "capabilities": ["scraping", "browser"],
            "version": "1.0.0"
        }
        
        # await worker_monitor.register_worker("demo-worker-001", worker_info)
        print("   📝 워커 등록: demo-worker-001")
        
        # 워커 상태 발행
        # await worker_monitor.publish_worker_status("demo-worker-001", "active")
        print("   📤 워커 상태 발행: active")
        
        # 하트비트 전송
        # await worker_monitor.send_heartbeat("demo-worker-001", {"cpu_usage": 23.5})
        print("   💓 하트비트 전송: demo-worker-001")
        
        # 워커 건강 상태 확인
        last_heartbeats = {
            "demo-worker-001": datetime.now(),
            "demo-worker-002": datetime.now()
        }
        
        unhealthy_workers = await worker_monitor.check_worker_health(last_heartbeats)
        print(f"   🏥 비정상 워커: {len(unhealthy_workers)}개")
        
    except Exception as e:
        print(f"   ❌ 워커 모니터 오류: {e}")
    finally:
        # await worker_monitor.disconnect()
        print("   🔌 워커 모니터 연결 해제")


async def main():
    """메인 함수 - RabbitMQ 큐 시스템 사용 예제 실행"""
    print("🚀 === RabbitMQ 큐 시스템 사용 예제 ===")
    print("⚠️  주의: 실제 RabbitMQ 서버 연결은 시뮬레이션됩니다")
    print("📖 완전한 기능을 위해서는 RabbitMQ 서버가 필요합니다\n")
    
    try:
        # 각 컴포넌트 데모 실행
        await demo_rpc_client()
        await demo_worker()
        await demo_task_manager()
        await demo_worker_monitor()
        
        print("\n✅ === 모든 데모 완료 ===")
        print("\n📚 추가 정보:")
        print("   - RabbitMQ 서버 설치: apt install rabbitmq-server")
        print("   - 환경 변수 설정: RABBITMQ_URL=amqp://localhost:5672/")
        print("   - 실제 구현에서는 모든 주석 처리된 코드를 활성화하세요")
        
    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main())) 