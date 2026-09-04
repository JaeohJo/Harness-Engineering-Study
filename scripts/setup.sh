#!/usr/bin/env bash
# ==============================================================================
# Antigravity 하네스 엔지니어링 개발 환경 설정 스크립트
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}     Antigravity 하네스 개발 환경 초기 설정을 시작합니다     ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. 파이썬 버전 확인
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[오류] python3가 설치되어 있지 않습니다.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✔ 감지된 Python 버전: ${PYTHON_VERSION}${NC}"

# 2. 가상환경(.venv) 생성 또는 확인
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}가상환경(.venv)을 생성합니다...${NC}"
    python3 -m venv .venv
    echo -e "${GREEN}✔ 가상환경 생성 완료${NC}"
else
    echo -e "${GREEN}✔ 기존 가상환경(.venv) 확인됨${NC}"
fi

# 3. 가상환경 활성화
source .venv/bin/activate

# 4. pip 업그레이드 및 패키지 설치
echo -e "${YELLOW}의존성 패키지 및 antigravity-harness를 설치합니다...${NC}"
pip install --upgrade pip
pip install -e ".[dev]"

# 5. agy CLI 설치 여부 확인
echo -e "${BLUE}Antigravity CLI (agy) 바이너리 설치 여부 확인 중...${NC}"
if command -v agy &> /dev/null; then
    echo -e "${GREEN}✔ agy CLI가 정상적으로 감지되었습니다: $(which agy)${NC}"
else
    echo -e "${YELLOW}[안내] agy CLI가 PATH에 등록되어 있지 않습니다.${NC}"
    echo -e "${YELLOW}실제 LLM 에이전트를 구동하려면 Antigravity CLI 설치가 필요합니다.${NC}"
fi

# 6. 기본 설정 및 샘플 데이터셋 초기화 (없을 경우)
if [ ! -f "harness.yaml" ] || [ ! -f "sample_tasks.json" ]; then
    echo -e "${YELLOW}기본 설정 및 샘플 데이터셋을 생성합니다...${NC}"
    agy-harness init
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}        하네스 환경 설정이 성공적으로 완료되었습니다!        ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "가상환경 활성화: ${BLUE}source .venv/bin/activate${NC}"
echo -e "테스트 실행:     ${BLUE}./scripts/test_all.sh${NC}"
echo -e "벤치마크 실행:   ${BLUE}./scripts/run_benchmark.sh${NC}\n"
