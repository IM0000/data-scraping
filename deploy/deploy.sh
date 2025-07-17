#!/bin/bash

# 스크래핑 시스템 배포 스크립트
# 사용법: ./deploy.sh [environment]

set -e

echo "=== Gateway-Worker 스크래핑 시스템 배포 시작 ==="

# 환경 변수 확인
ENVIRONMENT="${1:-development}"
PROJECT_NAME="data-scraping-project"
DOCKER_COMPOSE_CMD="docker-compose"

echo "배포 환경: $ENVIRONMENT"

# 환경별 설정 파일 선택
case $ENVIRONMENT in
    "development")
        COMPOSE_FILE="docker/docker-compose.yml"
        COMPOSE_OVERRIDE="docker/docker-compose.dev.yml"
        ;;
    "staging")
        COMPOSE_FILE="docker/docker-compose.yml"
        COMPOSE_OVERRIDE="docker/docker-compose.staging.yml"
        ;;
    "production")
        COMPOSE_FILE="docker/docker-compose.yml"
        COMPOSE_OVERRIDE="docker/docker-compose.prod.yml"
        ;;
    *)
        echo "오류: 지원되지 않는 환경입니다: $ENVIRONMENT"
        echo "사용 가능한 환경: development, staging, production"
        exit 1
        ;;
esac

# Docker Compose 파일 존재 확인
if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "오류: Docker Compose 파일을 찾을 수 없습니다: $COMPOSE_FILE"
    exit 1
fi

echo "Docker Compose 파일: $COMPOSE_FILE"

# Override 파일이 있으면 추가
COMPOSE_FILES="-f $COMPOSE_FILE"
if [[ -f "$COMPOSE_OVERRIDE" ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f $COMPOSE_OVERRIDE"
    echo "Override 파일: $COMPOSE_OVERRIDE"
fi

# 환경 변수 파일 확인
ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
    echo "환경 변수 파일 발견: $ENV_FILE"
    source "$ENV_FILE"
else
    echo "경고: .env 파일이 없습니다. 기본값을 사용합니다."
fi

# 필수 환경 변수 확인
echo "필수 환경 변수 확인 중..."
REQUIRED_VARS=(
    "RABBITMQ_URL"
    "JWT_SECRET_KEY"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var}" ]]; then
        echo "경고: $var 환경 변수가 설정되지 않았습니다"
    else
        echo "✓ $var 설정됨"
    fi
done

# Docker 및 Docker Compose 확인
echo "Docker 환경 확인 중..."
if ! command -v docker &> /dev/null; then
    echo "오류: Docker가 설치되지 않았습니다"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "경고: docker-compose를 찾을 수 없습니다. docker compose 명령을 사용합니다"
    DOCKER_COMPOSE_CMD="docker compose"
fi

echo "✓ Docker 환경 확인 완료"

# 기존 컨테이너 중지 (오류 무시)
echo "기존 컨테이너 중지 중..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES down --remove-orphans || true

# 오래된 이미지 정리 (선택사항)
if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "오래된 이미지 정리 중..."
    docker image prune -f || true
fi

# 이미지 빌드
echo "Docker 이미지 빌드 중..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES build --no-cache

# 컨테이너 시작
echo "컨테이너 시작 중..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES up -d

# 서비스 시작 대기
echo "서비스 시작 대기 중..."
sleep 10

# 헬스 체크 수행
echo "헬스 체크 수행 중..."

# API 서비스 헬스 체크
API_URL="${API_URL:-http://localhost:8000}"
HEALTH_CHECK_URL="$API_URL/health"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "API 헬스 체크: $HEALTH_CHECK_URL"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -f -s "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
        echo "✅ API 헬스 체크 성공 (시도 $i/$MAX_RETRIES)"
        break
    fi

    if [ $i -eq $MAX_RETRIES ]; then
        echo "❌ API 헬스 체크 실패: $MAX_RETRIES회 시도 후 타임아웃"
        echo "컨테이너 로그 확인:"
        $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs --tail=20 api
        exit 1
    fi

    echo "헬스 체크 시도 $i/$MAX_RETRIES... ($RETRY_INTERVAL초 후 재시도)"
    sleep $RETRY_INTERVAL
done

# RabbitMQ 관리 UI 확인
RABBITMQ_URL="${RABBITMQ_MANAGEMENT_URL:-http://localhost:15672}"
echo "RabbitMQ 관리 UI 확인: $RABBITMQ_URL"

if curl -f -s "$RABBITMQ_URL" > /dev/null 2>&1; then
    echo "✅ RabbitMQ 관리 UI 접근 가능"
else
    echo "⚠️  RabbitMQ 관리 UI 접근 불가 (정상적인 경우일 수 있음)"
fi

# 시스템 상태 확인
echo "시스템 상태 확인 중..."
if curl -s "$API_URL/status" | python3 -m json.tool > /dev/null 2>&1; then
    echo "✅ 시스템 상태 API 정상"
    curl -s "$API_URL/status" | python3 -m json.tool
else
    echo "⚠️  시스템 상태 API 응답 오류"
fi

# 메트릭 엔드포인트 확인
echo "메트릭 엔드포인트 확인 중..."
if curl -f -s "$API_URL/metrics" > /dev/null 2>&1; then
    echo "✅ Prometheus 메트릭 엔드포인트 정상"
else
    echo "⚠️  Prometheus 메트릭 엔드포인트 접근 불가"
fi

# 컨테이너 상태 확인
echo "컨테이너 상태 확인:"
$DOCKER_COMPOSE_CMD $COMPOSE_FILES ps

# 배포 완료 메시지
echo ""
echo "=== 배포 완료 ==="
echo "환경: $ENVIRONMENT"
echo "API 엔드포인트: $API_URL"
echo "API 문서: $API_URL/docs"
echo "RabbitMQ 관리 UI: $RABBITMQ_URL (admin/admin123)"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000 (admin/admin)"
echo ""
echo "로그 확인: $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs -f [service_name]"
echo "중지: $DOCKER_COMPOSE_CMD $COMPOSE_FILES down"
echo "스케일링: $DOCKER_COMPOSE_CMD $COMPOSE_FILES up --scale worker=5 -d"
echo ""
echo "배포가 성공적으로 완료되었습니다! 🎉" 