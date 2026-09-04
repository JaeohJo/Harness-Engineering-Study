# Antigravity CLI 하네스 엔지니어링 프레임워크 (`agy-harness`)

Antigravity CLI(`agy`)를 대상으로 하는 프로덕션 레벨의 확장 가능한 **하네스 엔지니어링(Harness Engineering)** 프레임워크입니다.

본 시스템은 Antigravity AI 에이전트를 자동화된 **실행(Execution), 샌드박싱(Sandboxing), 보안 가드레일(Guardrails), 정밀 평가(Evaluation), 관측성(Telemetry)** 파이프라인으로 감싸 체계적인 벤치마크 평가, CI/CD 회귀 테스트 및 자율 작업 검증을 지원합니다.

---

## 📑 시스템 아키텍처 개요

```
                                  +-----------------------+
                                  |    태스크 / 데이터셋    |
                                  | (SWE-bench / 커스텀)  |
                                  +-----------+-----------+
                                              |
                                              v
+------------------------+        +-----------+-----------+
|    생명주기 가드레일   | <----> |   워크스페이스 샌드박스 |
| (.agents/hooks.json)   |        | (Git Worktree / Temp) |
+------------------------+        +-----------+-----------+
                                              |
                                              v
                                  +-----------+-----------+
                                  |   헤드리스 실행기     |
                                  | (agy --print stream)  |
                                  +-----------+-----------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
        +------------+------------+                       +------------+------------+
        |     평가 및 정답 검증   |                       |    텔레메트리 및 관측성   |
        | (Diff / AST / Test Pass)|                       | (Transcripts / 메트릭)  |
        +------------+------------+                       +------------+------------+
                     |                                                 |
                     +------------------------+------------------------+
                                              |
                                              v
                                  +-----------+-----------+
                                  |     벤치마크 리포트   |
                                  |  (Markdown 및 JSON)   |
                                  +-----------------------+
```

---

## 🚀 핵심 기능 및 특징

1. **헤드리스 CLI 스트리밍 실행기 (`harness.runner.CliRunner`)**
   - `agy --print --output-format stream-json` 기반의 비대화형 자동화 구동
   - 표준 출력(stdout)을 라인 단위로 읽어 모델의 생각(`thought`), 도구 호출(`tool_call`), 텍스트 응답(`delta`), 완료(`done`) 이벤트를 실시간 디시리얼라이즈
   - 타임아웃 발생 시 독립 프로세스 그룹(`os.setsid`)을 통해 `SIGTERM` ➔ `SIGKILL` 단계별 클린 강제 종료

2. **격리된 워크스페이스 샌드박싱 (`harness.environment.GitWorktreeEnvironment`)**
   - 태스크마다 임시 브랜치와 독립된 Git Worktree(`git worktree add`)를 자동 프로비저닝하여 호스트 저장소 오염 방지
   - 신규 생성된 파일(untracked)을 포함한 전체 수정 내역(`git diff HEAD`) 정밀 추출
   - 완료 후 자동 롤백 및 임시 브랜치/워크트리 원자적 정리

3. **실시간 생명주기 가드레일 (`harness.guardrails.HookManager`)**
   - Antigravity 표준 규격에 맞춰 `.agents/hooks.json` 및 파이썬 보안 인터셉터 스크립트 동적 주입
   - `PreToolUse` 훅을 통해 파괴적 명령어(`rm -rf /`, 포크밤, 디스크 포맷, 리버스 셸, `.git` 훼손 등) 사전 차단
   - 프롬프트 컨텍스트에 자동 주입되는 엔지니어링 가이드라인(`GEMINI.md`) 적용

4. **다단계 평가 및 검증 엔진 (`harness.evaluator.TestEvaluator` & `DiffEvaluator`)**
   - 테스트 실행 전 수정된 파이썬 파일의 AST 구문 트리(`ast.parse`) 검사로 SyntaxError 사전 감지
   - 검증용 골든 테스트 패치(`test_patch`)를 안전하게 적용하고 지정된 테스트 명령어(pytest 등) 실행
   - 태스크 해결 결과를 `PASS`, `FAIL`, `ERROR`, `TIMEOUT` 상태로 명확하게 분류

5. **심층 텔레메트리 및 관측성 (`harness.telemetry.TranscriptParser`)**
   - Antigravity Brain의 세션 로그(`transcript.jsonl`)를 자동 탐색하여 파싱
   - 추론 토큰량(Thinking Tokens) 추정치, 대화 턴 수, 도구별 호출 횟수 및 에러율 집계
   - 종합 벤치마크 결과 보고서(Markdown 및 JSON) 자동 생성

---

## 🛠 설치 방법

```bash
# 저장소 클론 후 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate

# 개발용 의존성 패키지와 함께 편집 가능(editable) 모드로 설치
pip install -e ".[dev]"
```

또는 제공되는 셋업 스크립트를 통해 한 번에 구성할 수 있습니다:
```bash
./scripts/setup.sh
```

---

## 💻 실행 셸 스크립트 (`scripts/`)

프로젝트 루트의 `scripts/` 폴더에 즉시 실행 가능한 셸 스크립트가 제공됩니다:

| 스크립트 | 설명 | 사용 예시 |
| :--- | :--- | :--- |
| **`scripts/setup.sh`** | 가상환경 구성, 패키지 설치, agy CLI 감지 및 초기 파일 생성 | `./scripts/setup.sh` |
| **`scripts/run_task.sh`** | 단일 태스크 실행 및 평가 | `./scripts/run_task.sh sample_tasks.json gemini-1.5-pro high` |
| **`scripts/run_benchmark.sh`** | 데이터셋 벤치마크 일괄 평가 및 보고서 생성 | `./scripts/run_benchmark.sh sample_tasks.json reports/ gemini-1.5-pro high` |
| **`scripts/test_all.sh`** | 20개 전체 단위/통합 테스트 스위트 실행 | `./scripts/test_all.sh` |

---

## 💻 CLI 명령어 직접 사용

### 1. 환경 초기화
기본 설정 파일(`harness.yaml`) 및 샘플 태스크(`sample_tasks.json`) 생성:
```bash
agy-harness init
```

### 2. 단일 태스크 실행
```bash
agy-harness run --task sample_tasks.json --model gemini-1.5-pro --effort high
```

### 3. 벤치마크 일괄 평가
```bash
agy-harness benchmark --dataset sample_tasks.json --output reports/
```

---

## ⚙️ 설정 파일 안내 (`harness.yaml`)

```yaml
output_dir: reports                 # 평가 보고서 저장 폴더
runner:
  model: null                       # 대상 LLM 모델 (예: gemini-1.5-pro)
  effort: high                      # 추론 노력 수준 (low | medium | high)
  mode: accept-edits                # 에이전트 실행 모드 (accept-edits | plan)
  dangerously_skip_permissions: true # 비대화형 자동화를 위해 도구 승인 프롬프트 건너뛰기
  sandbox: false                    # 터미널 명령어 제한 샌드박스 활성화 여부
  timeout_seconds: 300.0            # 태스크 최대 실행 제한 시간(초)
  agy_bin_path: agy                 # CLI 바이너리 실행 경로
  extra_flags: []                   # 추가 전달할 CLI 플래그 목록
cleanup_worktree: true              # 실행 완료 후 임시 Git Worktree 자동 삭제 여부
enable_guardrails: true             # .agents/hooks.json 보안 가드레일 자동 주입 여부
concurrency: 1                      # 동시 실행 태스크 수
```

---

## 🧪 테스트 실행

```bash
pytest tests/
# 또는 스크립트 실행
./scripts/test_all.sh
```
