"""
스크립트 실행기 모듈

스크래핑 스크립트의 실행을 오케스트레이션하고 결과를 처리합니다.
"""

import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from ..models.base import ScrapingRequest, ScrapingResponse
from ..models.enums import TaskStatus
from ..scripts.metadata import ScriptMetadata
from ..scripts.cache_manager import CacheManager
from ..exceptions import ScriptExecutionException, ProcessExecutionException
from ..utils.logging import get_logger
from .process_manager import ProcessManager

logger = get_logger(__name__)


class ScriptExecutor:
    """스크립트 실행기"""

    def __init__(self, settings, cache_manager: CacheManager):
        """
        스크립트 실행기 초기화

        Args:
            settings: 시스템 설정
            cache_manager: 캐시 매니저
        """
        self.settings = settings
        self.cache_manager = cache_manager
        self.process_manager = ProcessManager(settings)
        self.logger = logger

    async def execute_scraping_request(self, request: ScrapingRequest) -> ScrapingResponse:
        """
        스크래핑 요청 실행

        Args:
            request: 스크래핑 요청

        Returns:
            스크래핑 응답
        """
        start_time = datetime.now()

        try:
            self.logger.info(f"스크래핑 요청 처리 시작: {request.request_id}")

            # 스크립트 다운로드 및 캐시
            script_path, metadata = await self.cache_manager.get_script(
                request.script_name,
                request.script_version
            )

            self.logger.info(f"스크립트 준비 완료: {script_path}")

            # 스크립트 실행 전 검증
            if not await self.validate_script_execution(script_path, metadata):
                raise ScriptExecutionException(
                    request.script_name,
                    f"스크립트 실행 검증 실패: {request.script_name}"
                )

            # 스크립트 실행
            return_code, stdout, stderr = await self.process_manager.execute_script(
                script_path=script_path,
                entry_point=metadata.entry_point,
                parameters=request.parameters,
                timeout=request.timeout,
                memory_limit=getattr(metadata, 'memory_limit', None)
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            # 실행 결과 분석
            if return_code == 0:
                # 성공적인 실행
                try:
                    # stdout에서 JSON 결과 파싱
                    result_data = self._parse_script_output(stdout)

                    response = ScrapingResponse(
                        request_id=request.request_id,
                        status=TaskStatus.COMPLETED,
                        data=result_data,
                        execution_time=execution_time,
                        completed_at=datetime.now()
                    )

                    self.logger.info(f"스크래핑 요청 성공: {request.request_id}")
                    return response

                except (json.JSONDecodeError, ValueError) as e:
                    # JSON 파싱 실패
                    self.logger.error(f"결과 파싱 실패: {e}")

                    response = ScrapingResponse(
                        request_id=request.request_id,
                        status=TaskStatus.FAILED,
                        error=f"결과 파싱 실패: {e}",
                        execution_time=execution_time,
                        completed_at=datetime.now()
                    )

                    return response
            else:
                # 실행 실패
                error_message = self._extract_error_message(stderr, return_code)

                response = ScrapingResponse(
                    request_id=request.request_id,
                    status=TaskStatus.FAILED,
                    error=error_message,
                    execution_time=execution_time,
                    completed_at=datetime.now()
                )

                self.logger.error(f"스크립트 실행 실패: {request.request_id} - {error_message}")
                return response

        except (ScriptExecutionException, ProcessExecutionException) as e:
            # 스크립트 실행 관련 예외
            execution_time = (datetime.now() - start_time).total_seconds()

            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
                completed_at=datetime.now()
            )

            self.logger.error(f"스크립트 실행 예외: {request.request_id} - {e}")
            return response

        except Exception as e:
            # 예기치 않은 오류
            execution_time = (datetime.now() - start_time).total_seconds()
            error_trace = traceback.format_exc()

            response = ScrapingResponse(
                request_id=request.request_id,
                status=TaskStatus.FAILED,
                error=f"예기치 않은 오류: {str(e)}",
                execution_time=execution_time,
                completed_at=datetime.now()
            )

            self.logger.error(f"예기치 않은 오류: {request.request_id} - {error_trace}")
            return response

    async def validate_script_execution(self, script_path: Path, metadata: ScriptMetadata) -> bool:
        """
        스크립트 실행 가능성 검증

        Args:
            script_path: 스크립트 경로
            metadata: 스크립트 메타데이터

        Returns:
            실행 가능 여부
        """
        try:
            # 엔트리 포인트 파일 존재 확인
            entry_file = script_path / metadata.entry_point
            if not entry_file.exists():
                self.logger.error(f"엔트리 포인트 파일 없음: {entry_file}")
                return False

            # 기본 구문 검사
            with open(entry_file, 'r', encoding='utf-8') as f:
                script_content = f.read()

            # 기본적인 Python 구문 검사
            try:
                compile(script_content, str(entry_file), 'exec')
            except SyntaxError as e:
                self.logger.error(f"스크립트 구문 오류: {e}")
                return False

            # 메타데이터 검증
            if not self.cache_manager.metadata_parser.validate_metadata(metadata):
                self.logger.error(f"메타데이터 검증 실패: {metadata.name}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"스크립트 검증 오류: {e}")
            return False

    def _parse_script_output(self, stdout: str) -> Dict[str, Any]:
        """
        스크립트 출력 결과 파싱

        Args:
            stdout: 표준 출력

        Returns:
            파싱된 결과 데이터

        Raises:
            ValueError: 파싱 실패
        """
        if not stdout.strip():
            return {}

        try:
            # JSON 결과 파싱 시도
            result_data = json.loads(stdout)
            
            # 기본 구조 검증
            if isinstance(result_data, dict):
                return result_data
            else:
                # JSON이 dict가 아닌 경우 wrapper로 감싸기
                return {"result": result_data}

        except json.JSONDecodeError:
            # JSON이 아닌 경우 텍스트로 처리
            lines = stdout.strip().split('\n')
            
            # 마지막 줄이 JSON인지 확인
            for line in reversed(lines):
                if line.strip():
                    try:
                        result_data = json.loads(line)
                        if isinstance(result_data, dict):
                            return result_data
                        else:
                            return {"result": result_data}
                    except json.JSONDecodeError:
                        continue
            
            # JSON을 찾지 못한 경우 텍스트로 반환
            return {"output": stdout.strip()}

    def _extract_error_message(self, stderr: str, return_code: int) -> str:
        """
        에러 메시지 추출

        Args:
            stderr: 표준 에러
            return_code: 프로세스 종료 코드

        Returns:
            정제된 에러 메시지
        """
        if stderr and stderr.strip():
            # stderr에서 중요한 에러 메시지 추출
            lines = stderr.strip().split('\n')
            
            # 마지막 Traceback에서 실제 에러 찾기
            error_lines = []
            in_traceback = False
            
            for line in lines:
                if line.startswith('Traceback'):
                    in_traceback = True
                    error_lines = [line]
                elif in_traceback:
                    error_lines.append(line)
            
            if error_lines:
                # 마지막 에러 라인 (실제 예외)
                last_line = error_lines[-1].strip()
                if last_line:
                    return last_line
            
            # Traceback이 없으면 stderr 전체 또는 마지막 라인
            return lines[-1].strip() if lines else stderr.strip()
        
        return f"스크립트 실행 실패 (종료코드: {return_code})"

    async def get_execution_statistics(self) -> Dict[str, Any]:
        """
        실행 통계 정보 반환

        Returns:
            실행 통계 딕셔너리
        """
        return {
            "active_processes": self.process_manager.get_active_process_count(),
            "cache_directory": str(self.cache_manager.cache_dir),
            "settings": {
                "process_timeout": self.settings.process_timeout,
                "process_memory_limit": self.settings.process_memory_limit,
                "max_concurrent_tasks": self.settings.max_concurrent_tasks
            }
        }

    async def cleanup(self):
        """리소스 정리"""
        try:
            await self.process_manager.cleanup_all_processes()
            self.logger.info("스크립트 실행기 정리 완료")
        except Exception as e:
            self.logger.error(f"스크립트 실행기 정리 오류: {e}")

    def is_busy(self) -> bool:
        """
        실행기가 바쁜 상태인지 확인

        Returns:
            바쁜 상태 여부
        """
        active_count = self.process_manager.get_active_process_count()
        return active_count >= self.settings.max_concurrent_tasks 