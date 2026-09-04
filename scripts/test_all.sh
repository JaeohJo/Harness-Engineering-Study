#!/usr/bin/env bash
# ==============================================================================
# Antigravity 하네스 전체 테스트 실행 스크립트
#
# 사용법:
#   ./scripts/test_all.sh [추가 pytest 옵션]
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# 가상환경 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}        Antigravity 하네스 단위/통합 테스트 실행       ${NC}"
echo -e "${BLUE}======================================================${NC}"

# pytest 실행 (인자가 전달되면 전달받은 옵션 적용)
pytest -v tests/ "$@"
