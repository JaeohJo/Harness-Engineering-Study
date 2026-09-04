#!/usr/bin/env bash
# ==============================================================================
# Antigravity 하네스 단일 태스크 실행 스크립트
#
# 사용법:
#   ./scripts/run_task.sh [태스크파일.json] [모델명] [추론수준:low|medium|high]
# 예시:
#   ./scripts/run_task.sh sample_tasks.json
#   ./scripts/run_task.sh sample_tasks.json gemini-1.5-pro high
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

TASK_FILE="${1:-sample_tasks.json}"
MODEL_NAME="${2:-}"
EFFORT="${3:-}"

# 가상환경 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

if [ ! -f "${TASK_FILE}" ]; then
    echo -e "${RED}[오류] 태스크 파일을 찾을 수 없습니다: ${TASK_FILE}${NC}"
    echo -e "사용법: $0 [태스크파일.json] [모델명] [추론수준:low|medium|high]"
    exit 1
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}               단일 태스크 하네스 실행                ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "태스크 파일: ${GREEN}${TASK_FILE}${NC}"

CMD_ARGS=("run" "--task" "${TASK_FILE}")

if [ -n "${MODEL_NAME}" ]; then
    echo -e "지정 모델:   ${GREEN}${MODEL_NAME}${NC}"
    CMD_ARGS+=("--model" "${MODEL_NAME}")
fi

if [ -n "${EFFORT}" ]; then
    echo -e "추론 수준:   ${GREEN}${EFFORT}${NC}"
    CMD_ARGS+=("--effort" "${EFFORT}")
fi

echo -e "------------------------------------------------------\n"

# 하네스 CLI 실행
agy-harness "${CMD_ARGS[@]}"
