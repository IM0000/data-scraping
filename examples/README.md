# 예제 모음

이 디렉토리는 Gateway-Worker 스크래핑 시스템의 사용 예제를 제공합니다.

## 구조

```
examples/
├── README.md              # 이 파일
├── basic_structure.py     # 기본 코딩 패턴
├── test_pattern.py        # 테스트 패턴
└── models/
    └── basic_usage.py     # 핵심 모델 사용 예제
```

## 사용법

### 핵심 모델 사용 예제

```bash
# 기본 사용 예제 실행
python examples/models/basic_usage.py
```

이 예제는 다음 기능들을 보여줍니다:

1. **설정 시스템**: 환경 변수 로드 및 유효성 검증
2. **로깅 시스템**: 한국어 로깅 메시지 출력
3. **데이터 모델**: 요청/응답 모델 생성 및 사용
4. **유틸리티**: ID 생성, 해시 계산 등
5. **예외 처리**: 커스텀 예외 사용

### 코딩 패턴

`basic_structure.py`는 프로젝트의 표준 코딩 스타일을 보여줍니다:

- 한국어 docstring과 주석
- 타입 힌트 사용
- 로깅 패턴
- 예외 처리 패턴

### 테스트 패턴

`test_pattern.py`는 테스트 작성 패턴을 보여줍니다:

- pytest 사용법
- 모킹 패턴
- 픽스처 사용
- 예외 테스트

## 개발 가이드라인

### 새 예제 추가

1. 적절한 하위 디렉토리에 파일 생성
2. 한국어 docstring과 주석 사용
3. 실행 가능한 예제 제공
4. README.md 업데이트

### 파일 명명 규칙

- `basic_*.py`: 기본 사용법 예제
- `advanced_*.py`: 고급 사용법 예제
- `integration_*.py`: 통합 시나리오 예제

### 코드 품질

- PEP 8 준수
- 타입 힌트 필수
- 한국어 문서화
- 예외 처리 포함

## 참고 자료

- [INITIAL.md](../INITIAL.md): 전체 시스템 요구사항
- [PRPs/](../PRPs/): 상세 구현 계획
- [src/](../src/): 소스 코드
- [tests/](../tests/): 테스트 코드
