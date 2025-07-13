#!/usr/bin/env python3
"""
테스트 패턴 예제

이 파일은 프로젝트의 표준 테스트 작성 패턴을 보여줍니다.
실제 프로젝트에서는 pytest를 설치하고 사용하세요.

설치 방법:
pip install pytest pytest-mock

실행 방법:
pytest tests/
"""

from unittest.mock import Mock, patch
from pathlib import Path
from typing import Any, Dict

# 실제 프로젝트에서는 다음과 같이 import 합니다:
# import pytest
# from your_module import YourClass, your_function


class TestExample:
    """
    테스트 클래스 예제
    
    테스트 클래스는 테스트 대상 클래스와 같은 이름에 Test 접두사를 붙입니다.
    """
    
    def setup_method(self):
        """
        각 테스트 메서드 실행 전 호출되는 설정 메서드
        
        Reason: 각 테스트가 독립적으로 실행되도록 초기 상태를 설정
        """
        self.test_data = "test_value"
        self.mock_object = Mock()
    
    def teardown_method(self):
        """
        각 테스트 메서드 실행 후 호출되는 정리 메서드
        """
        # 테스트 후 정리 작업
        pass
    
    def test_basic_functionality(self):
        """
        기본 기능 테스트
        
        테스트 이름은 test_로 시작하고 테스트 내용을 명확히 설명합니다.
        """
        # Given (준비)
        input_value = "test input"
        expected_output = "expected output"
        
        # When (실행)
        # actual_output = your_function(input_value)
        actual_output = f"processed: {input_value}"
        
        # Then (검증)
        assert actual_output == "processed: test input"
        assert len(actual_output) > 0
    
    def test_with_mock(self):
        """
        모킹을 사용한 테스트 예제
        """
        # Given
        mock_service = Mock()
        mock_service.process.return_value = "mocked result"
        
        # When
        result = mock_service.process("test")
        
        # Then
        assert result == "mocked result"
        mock_service.process.assert_called_once_with("test")
    
    def test_exception_handling(self):
        """
        예외 처리 테스트
        """
        # Given
        invalid_input = None
        
        # When & Then
        try:
            if invalid_input is None:
                raise ValueError("입력값이 None입니다")
            assert False, "예외가 발생해야 합니다"
        except ValueError as e:
            assert str(e) == "입력값이 None입니다"
    
    @patch('pathlib.Path.exists')
    def test_with_patch_decorator(self, mock_exists):
        """
        패치 데코레이터를 사용한 테스트
        
        Args:
            mock_exists: Path.exists 메서드의 모킹 객체
        """
        # Given
        mock_exists.return_value = True
        test_path = Path("test_file.txt")
        
        # When
        exists = test_path.exists()
        
        # Then
        assert exists is True
        mock_exists.assert_called_once()


def test_standalone_function():
    """
    독립적인 함수 테스트
    """
    # Given
    test_value = 42
    
    # When
    result = test_value * 2
    
    # Then
    assert result == 84


class TestParameterizedExample:
    """
    매개변수화된 테스트 예제
    
    실제 프로젝트에서는 pytest.mark.parametrize를 사용합니다.
    """
    
    def test_multiple_inputs(self):
        """
        여러 입력값에 대한 테스트
        """
        test_cases = [
            ("input1", "expected1"),
            ("input2", "expected2"),
            ("input3", "expected3"),
        ]
        
        for input_val, expected in test_cases:
            # When
            result = f"processed_{input_val}"
            expected_result = f"processed_{expected.replace('expected', 'input')}"
            
            # Then
            assert result == expected_result


class TestFixtureExample:
    """
    픽스처 사용 예제
    """
    
    def get_test_config(self) -> Dict[str, Any]:
        """
        테스트용 설정 픽스처 (실제로는 @pytest.fixture 사용)
        
        Returns:
            테스트용 설정 딕셔너리
        """
        return {
            "test_mode": True,
            "debug": True,
            "timeout": 30
        }
    
    def test_with_fixture(self):
        """
        픽스처를 사용한 테스트
        """
        # Given
        config = self.get_test_config()
        
        # When
        test_mode = config.get("test_mode")
        
        # Then
        assert test_mode is True
        assert config["debug"] is True


class TestEdgeCases:
    """
    엣지 케이스 테스트 모음
    """
    
    def test_empty_input(self):
        """
        빈 입력값 테스트
        """
        # Given
        empty_string = ""
        
        # When
        result = len(empty_string)
        
        # Then
        assert result == 0
    
    def test_none_input(self):
        """
        None 입력값 테스트
        """
        # Given
        none_value = None
        
        # When & Then
        assert none_value is None
        assert not none_value
    
    def test_large_input(self):
        """
        큰 입력값 테스트
        """
        # Given
        large_list = list(range(10000))
        
        # When
        result = len(large_list)
        
        # Then
        assert result == 10000
        assert large_list[0] == 0
        assert large_list[-1] == 9999


# 테스트 실행 시 사용할 수 있는 헬퍼 함수들
def assert_valid_string(value: str) -> None:
    """
    유효한 문자열인지 확인하는 헬퍼 함수
    
    Args:
        value: 확인할 문자열
    """
    assert isinstance(value, str)
    assert len(value) > 0
    assert value.strip() == value  # 앞뒤 공백 없음


def create_test_data() -> Dict[str, Any]:
    """
    테스트 데이터 생성 헬퍼 함수
    
    Returns:
        테스트용 데이터 딕셔너리
    """
    return {
        "string_value": "test string",
        "number_value": 42,
        "boolean_value": True,
        "list_value": [1, 2, 3],
        "dict_value": {"key": "value"}
    }


def run_basic_tests():
    """
    기본 테스트 실행 함수 (pytest 없이 실행 가능)
    """
    print("기본 테스트 실행 중...")
    
    # 기본 테스트 실행
    test_instance = TestExample()
    test_instance.setup_method()
    test_instance.test_basic_functionality()
    test_instance.teardown_method()
    
    # 독립 함수 테스트
    test_standalone_function()
    
    print("모든 테스트 통과!")


if __name__ == "__main__":
    run_basic_tests() 