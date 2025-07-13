sequenceDiagram
participant C as Client
participant G as Gateway
participant MQ as Message Queue
participant W as Worker
participant SS as Script Storage
participant CP as Child Process
participant Cache as Script Cache

    Note over C,Cache: 클라이언트 스크래핑 요청 처리 플로우

    C->>G: HTTP POST /scrape<br/>{script_name, version, parameters}

    G->>G: 요청 검증 및 전처리
    G->>MQ: 스크래핑 태스크 생성<br/>{task_id, script_info, params}

    Note over G: 동기 응답 대기 시작<br/>(timeout 설정)

    MQ->>W: 태스크 할당
    W->>W: 태스크 수신 및 처리 시작

    W->>Cache: 스크립트 캐시 확인<br/>(version 비교)

    alt 캐시 미스 또는 버전 불일치
        W->>SS: 스크립트 다운로드 요청<br/>{script_name, version}
        SS->>W: 스크립트 파일 반환
        W->>Cache: 스크립트 캐시 업데이트
    else 캐시 히트
        Cache->>W: 캐시된 스크립트 반환
    end

    W->>CP: 자식 프로세스 생성<br/>스크립트 실행 시작

    Note over CP: 스크립트 실행<br/>(HTTP 요청, 브라우저 자동화,<br/>captcha 처리 등)

    alt 스크립트 실행 성공
        CP->>W: 스크래핑 결과 반환<br/>{status: success, data}
        W->>G: 태스크 완료 결과 전송<br/>{task_id, result}
        G->>C: HTTP 200 OK<br/>{success: true, data}
    else 스크립트 실행 실패
        CP->>W: 에러 정보 반환<br/>{status: error, message}
        W->>G: 태스크 실패 결과 전송<br/>{task_id, error}
        G->>C: HTTP 500 Error<br/>{success: false, error}
    else 타임아웃 발생
        Note over G: 설정된 타임아웃 시간 초과
        G->>C: HTTP 408 Timeout<br/>{success: false, error: "timeout"}
        Note over W,CP: 백그라운드에서 계속 실행<br/>(결과는 무시됨)
    end

    Note over C,Cache: 요청 완료
