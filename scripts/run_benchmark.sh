#!/usr/bin/env bash
# ==============================================================================
# Antigravity 하네스 벤치마크 일괄 평가 실행 스크립트
#
# 사용법:
#   ./scripts/run_benchmark.sh [데이터셋.json|jsonl] [결과저장폴더] [모델명] [추론수준]
# 예시:
#   ./scripts/run_benchmark.sh sample_tasks.json reports/
#   ./scripts/run_benchmark.sh datasets/swe_bench.jsonl reports/experiment_1 gemini-1.5-pro high
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DATASET_FILE="${1:-sample_tasks.json}"
OUTPUT_DIR="${2:-reports}"
MODEL_NAME="${3:-}"
EFFORT="${4:-}"

# 가상환경 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

if [ ! -f "${DATASET_FILE}" ]; then
    echo -e "${RED}[오류] 데이터셋 파일을 찾을 수 없습니다: ${DATASET_FILE}${NC}"
    echo -e "사용법: $0 [데이터셋.json|jsonl] [결과저장폴더] [모델명] [추론수준]"
    exit 1
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}             Antigravity 벤치마크 평가 시작            ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "데이터셋:    ${GREEN}${DATASET_FILE}${NC}"
echo -e "보고서 폴더: ${GREEN}${OUTPUT_DIR}${NC}"

CMD_ARGS=("benchmark" "--dataset" "${DATASET_FILE}" "--output" "${OUTPUT_DIR}")

if [ -n "${MODEL_NAME}" ]; then
    echo -e "지정 모델:   ${GREEN}${MODEL_NAME}${NC}"
    CMD_ARGS+=("--model" "${MODEL_NAME}")
fi

if [ -n "${EFFORT}" ]; then
    echo -e "추론 수준:   ${GREEN}${EFFORT}${NC}"
    CMD_ARGS+=("--effort" "${EFFORT}")
fi

echo -e "------------------------------------------------------\n"

# 하네스 CLI 벤치마크 실행
agy-harness "${CMD_ARGS[@]}"

echo -e "\n${GREEN}평가 완료! 생성된 리포트:${NC}"
echo -e "- 마크다운 보고서: ${BLUE}${OUTPUT_DIR}/benchmark_report.md${NC}"
echo -e "- JSON 데이터:     ${BLUE}${OUTPUT_DIR}/benchmark_report.json${NC}\n"
