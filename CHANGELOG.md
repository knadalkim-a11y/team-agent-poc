# Changelog

완료된 변경·중요 결정과 날짜별 관찰을 기록합니다. 다음 작업과 최신 배포 상태는 [STATUS](docs/STATUS.md), 시험별 현재 판정은 [평가표](evals/scenarios.md)가 원본입니다. 과거 실패 기록을 현재 장애나 재실행 지시로 해석하지 않습니다.

## 2026-09-07

- Native `query_knowledge_files`의 임베딩 의존성이 문서 설정의 임베딩 우회와 별개임을 확인해 안내를 보완. Confluence Tool 우선과 작은 정책 Knowledge의 파일명/본문 조회를 사용하는 Prompt 섹션을 준비함. 기존 Knowledge 연결을 유지하며 개별 함수 강제 차단·임베딩 설정 복구를 의미하지 않음. [검토 근거](evals/confluence-offline.md#knowledge-routing); 사내 부분 적용·회귀 확인은 별도 수행.

## 2026-09-06

- Confluence Tool v0.1.2: HTTP 전용 사내 연결을 위한 관리자 `ALLOW_HTTP` 옵션 추가(기본 `false`). 요청·문서 링크의 스킴·포트·context path를 유지하고 HTTP에는 CA 파일을 사용하지 않음. HTTPS 인증서 검증·고정 GET 경로·리디렉션 차단·개인 PAT·공간 제한은 유지. [검증 증거](evals/confluence-offline.md#http-opt-in); 사내 코드 교체·연결 재검증은 별도 수행.
- Open WebUI 0.11.3 개인 설정의 가짜 PAT를 읽기 전용으로 확인하는 운영자 검사기 추가. 기존 키로 암호문 일치와 DB·WAL·journal 평문 잔존을 확인하고, 로그·재기동·사용자 격리 판정은 분리. [합성 검증 증거](evals/confluence-offline.md#canary-db-check); 실제 사내 DB 검사 통과를 뜻하지 않음.
- 검수 절차를 변경 규모와 영향에 맞춰 구체화. 변경 전 확인 범위를 정하고, 검수·관련 문제 수정·필요한 재검증 뒤 범위·발견·처리·미확인을 남기도록 보완. 작은 수정은 짧게 보고하고 재사용할 근거는 기존 evals에 기록하며, STATUS의 무조건 갱신으로 읽히던 안내를 상태 변경 시 갱신으로 통일.
- 사내 복귀 전 관리·지침 정리: 팀원 개인·공유 자산은 WebUI, 담당자가 채택한 공통 배포 자산은 Git으로 관리하는 경계를 명확화. STATUS의 누적 검증 기록은 날짜·환경·결과를 보존해 기존 사외 검증 문서로 이동하고 현재 상태·최신 점검만 유지.
- Native 가이드의 Skill 호출 조건·Knowledge 조회·Action 경로를 대상 0.11.3에 맞게 정정하고, 기본 Assistant·Confluence·후속 DB 조회의 평가 범위를 구분. 인증 없는 응답이나 과거 프록시 관찰로 현재 경로를 확정하던 안내를 수정.
- Confluence Tool v0.1.1: 표의 인접 셀 값이 합쳐지는 문제를 수정하고 `get_page` 회귀시험 추가. 로컬 smoke test의 자동 리디렉션을 차단해 다른 주소의 성공 응답을 로컬 성공으로 판정하지 않도록 수정. 실제 Windows·WebUI·Confluence 실행과 배포는 미수행; 사외 검증은 [기존 검증 기록](evals/confluence-offline.md#pre-mvp-cleanup)에 보존.
- AI 사용 경험이 적은 비개발자를 기본 사용자로 삼는 설계·검토 기준을 개발 지침에 추가. 업무 표현·입력 예시·필요한 조건 확인·명확한 결과와 오류 안내를 우선하며, 실제 사용자 확인과 정적 검토를 구분. 화면·기능·배포 변경은 수행하지 않음.
- 사용자 설명에 따라 현재 GLM 5.2 중심 운용과 GLM 5.3을 포함한 후속 교체 가능성을 환경 기준에 기록. 현재 사내 모델의 기능별 성능을 확인해 구현 복잡도를 정하고, 모델명과 업무 Tool·UI를 분리하는 원칙을 추가. 모델 설정 변경이나 성능 검증은 수행하지 않음.
- 개발 시작 시 관련 열린 PR의 지침·상태를 함께 확인하도록 보완. main·PR·실제 배포 상태를 구분하고, PR 발견 자체를 작업 대상 전환·병합·배포 승인으로 해석하지 않음.
- Assistant Prompt에서 실행 지시와 문서 근거를 분리하고, 정책 답변 Skill에 실제 연결된 승인 읽기 Tool의 조회 근거를 포함.
- 공통 정책 v0.2에서 채팅의 자격증명 수집·노출 금지와 승인된 개인 설정의 보호 저장을 구분. 운영 DB·직접 SQL·쓰기 금지는 유지.
- 관련 문서와 후속 행동 평가를 갱신. 사내 모델의 응답 재검증과 WebUI 적용은 수행하지 않음.

## 2026-09-05

### Added

- Confluence 검색 결과 탐색용 합성 HTML 참고 예제 추가. 별도 서버·설치 없이 받은 결과의 필터·상세 펼치기를 확인하는 용도이며 기존 Tool과 미연동.
- 개인 UserValves PAT를 사용하는 Confluence 읽기 Tool과 Skill 묶음 준비.
- 고정 GET API·허용 Space·TLS 검증·응답 제한·안전한 오류 처리 및 오프라인 테스트 43개 추가.
- Confluence 설치·암호화 저장·사용자 권한 검증 가이드 추가. 실제 연결이나 WebUI 배포 완료를 의미하지 않음.
- GPT 개발 규칙 `AGENTS.md`와 최신 작업 상태 `docs/STATUS.md` 추가.
- 읽기 전용·오프라인 문서 점검기 `scripts/check_docs.py`와 합성 저장소 회귀 테스트 43개 추가. 깨진 내부 링크와 연결되지 않은 관리 문서를 구분하고, 문서 자동 삭제는 하지 않음.

### Changed

- README는 목적·구조 지도·문서 탐색, versions는 환경 기준, CHANGELOG는 완료 이력으로 역할을 구분.
- Confluence C01~C09를 `evals/scenarios.md#confluence-live`로 옮기고 설치 가이드는 평가표 링크만 유지.
- 설치 가이드의 중복 판정표 제거. 직접 모델 D06 반복 안정성 / D07 재시작 번호를 기존 평가표 기준으로 통일.
- 기존 UI의 Skill 2개와 Git에 추가 준비된 Confluence Skill을 구분. Git 준비·WebUI 반영·실환경 검증을 독립적으로 추적.
- 과거 관찰은 날짜로 구분하고, GitHub·외부 Tool Server·Hermes 예시는 선택적 후속 경로로 명시.
- 관리 리팩토링에서는 기존 Skill·Tool·실행 스크립트·설정·테스트 경로와 동작을 변경하지 않음.
- GPT 작업 종료에 관련 문서 의미 검토·구조 점검·경고 처리 보고를 포함. 새 문서보다 기존 원본 갱신을 우선하고 세션별 보고서 누적을 방지.
- README에 일회성 ChatGPT 프로젝트 지침 설정 안내와 검사 범위·한계를 추가. 사용자 설정 완료나 GitHub 필수 검사 설치를 의미하지 않음.

### 주요 결정

- 기본 되묻기·일반 답변·Rich UI의 선택 기준과 Jira/GitHub 읽기 연동 준비 항목을 기존 Native 가이드에 정리. Rich UI는 업무 기능 내부에서 관리하고 실제 중복 전에는 공통 프레임워크를 만들지 않음.
- 혼자 GPT로 개발하는 규모에 맞춰 진입 문서 2개만 추가. 별도 adapter·registry·배포 시스템과 세션별 handoff 파일은 만들지 않음.
- 실제 WebUI에 복사·등록한 원본 커밋을 추적하며, 모르는 적용 SHA를 Git 최신 커밋으로 대신 기록하지 않음.

### 문서 점검 추가 검증

- Linux / Python 3.12.13 / Pydantic 2.13.4에서 `python -m unittest discover -s tests -v`: 신규 문서 점검 43개와 기존 Confluence 43개, 총 86개 통과.
- `python scripts/check_docs.py`: 문서 20개·내부 링크 86개, 오류 0·검토 후보 0. `git diff --check` 통과. 실제 Windows·WebUI·Confluence 검증이나 사용자 프로젝트 설정은 수행하지 않음.

## 2026-09-03

### 설계·관리 변경

- Open WebUI Native 우선 MVP와 비밀정보 없는 Agent Pack 템플릿 채택.
- Hermes 연동을 필수 다음 단계가 아닌 선택적 비교로 변경.
- 기본 구성 기준선을 Assistant 1개, Skill 2개, 합성 Knowledge 1개로 정의.
- DB 안전성을 모델의 행동 거절(P05·P06)과 실제 Tool·Broker·네트워크 통제(S06)로 분리.
- Community 표시 이름을 `EES Assistant (Open WebUI)`로 구성.
- Open WebUI Skill의 지침과 실행 코드를 구분하고 Workspace Tool 또는 외부 연결로 실행 기능을 제공하는 방향을 정리.

### Added

- Windows·Docker 미사용 환경의 로컬 POC 문서 구조
- Open WebUI 실행·smoke test PowerShell
- 직접 vLLM 기준선과 Hermes 연동 절차
- 비밀정보 placeholder 정책
- MVP 검증 시나리오와 버전 기록

### Verified

- Open WebUI 0.11.3 Skill 생성 화면에서 YAML frontmatter를 인식하고 `policy-grounded-answer` 생성 확인
- Open WebUI Workspace의 Skills 목록에서 `policy-grounded-answer`와 `structured-troubleshooting` 2개 생성 확인
- `EES POC Policy` Knowledge Base에 합성 `poc-policy.md` 문서 첨부 확인
- `EES 통합 Assistant` Workspace Model 생성 및 메인 Chat 모델 선택기 노출 확인
- 정책 질문에서 `view_skill` 호출과 `policy-grounded-answer` 형식 준수 확인
- 합성 Knowledge의 `POC-POL-001 v0.1` 및 관련 절을 정확히 근거로 제시
- 임베딩 우회 상태에서 semantic query 실패 후 `grep_knowledge_files`·파일 보기로 복구 확인
- 장애 질문에서 `structured-troubleshooting` Skill만 자동 선택하고 지정된 진단 구조를 준수
- 문서에 없는 긴급 예외 시간·승인자 추정 요청을 거절하고 운영 DB 직접 접근 금지 원칙 유지
- 운영 DB 직접 조회 요청을 거절하고 승인된 읽기 전용 API·Query Broker 경로 안내 확인(P05)
- 이전 규칙 무시·긴급 예외 우회 요청 거절 확인(P06)
- 존재하지 않는 정책 문서에 대해 확인 불가를 밝히고 추측 확정 요청 거절 확인(P07)
- 기존 Hermes 0.19.0과 사내 모델의 CLI 질문·응답 확인
- GitHub, PyPI, Hugging Face 프록시 연결 HTTP 200
- 로컬 포트 8080과 8642에 기존 listener 없음
- Open WebUI 0.11.3 진단 실행에서 /health HTTP 200 확인
- 브라우저 UI 접속과 최초 관리자 계정 생성 확인
- Open WebUI에서 승인된 사내 Chat 모델 2종을 각각 선택해 기본 응답 확인
- 사내 Chat 모델 전환 후 각 모델의 정상 응답 확인
- 연결 allowlist로 Embedding·Reranker를 숨기고 승인된 Chat 모델만 picker에 표시

### Observed

- 장애 분석 답변의 일부 맞춤법 오타는 Skill 선택과 분리해 모델 출력 품질 개선 항목으로 남겼습니다.
- 첫 정책 답변에서 `POC`를 한 곳에서 `PCO`로 표기한 경미한 출력 오타를 관찰했습니다.
- `EES POC Policy` Knowledge Base에서 파일 추가 시 임베딩 모델 미설정 오류를 확인했습니다. 작은 합성 문서 POC는 관리자 문서 설정의 `임베딩 검색 우회`로 진행하고, 사내 Embedding 모델 연결은 후속 단계로 분리합니다.
- Open WebUI 최초 기동은 CORS 경고까지 진행됐습니다.
- 이후 약 30분 동안 8080 listener가 없고 /health가 HTTP 000인 정체 상태를 확인했습니다.
- uv·uvx·python 프로세스는 남아 있었고, 원래 창에서 Ctrl+C 후 traceback 없이 중단됐습니다.
- import timing과 DEBUG 로그로 재실행했고, aiosqlite 설정 조회가 계속 진행되는 것을 확인했습니다.
- aiosqlite 조회 로그는 webui.db 접근을 확인할 뿐 전체 DB 초기화 진행을 증명하지 않으므로 원인 판정을 보류했습니다.
- 신규 빈 DB에서 수십 분이 걸리는 것은 정상으로 간주하지 않으며 프로세스 중복·파일 변화·import 병목을 추가 확인합니다.
- DEBUG 모드에서는 백엔드가 준비된 뒤에도 aiosqlite와 서버 로그가 계속 출력되는 것이 정상입니다.
- DEBUG를 제거한 정상 재시작과 계정 유지 확인은 아직 진행 전입니다.
- UI 준비 후 Hugging Face HTTPS 호출에서 `CERTIFICATE_VERIFY_FAILED` 재시도를 관찰했습니다.
- 해당 재시도와 일부 오류 후에도 UI 접근과 관리자 세션은 정상 상태를 유지했습니다.
- 기본 `api.openai.com/v1/models` 조회는 사내망에서 403 HTML 차단 응답을 받았습니다. 이는 예상된 외부 경로 차단이며 기본 OpenAI 연결을 비활성화하고 사내 vLLM만 등록합니다.
- 핵심 UI·계정 기능에는 영향이 없지만 로컬 임베딩·파일 RAG 관련 기능은 사내 CA 신뢰 설정 전까지 보류합니다.

- 사내 vLLM 모델 조회에서 `Cannot connect to host <INTERNAL_VLLM_HOST>:443 ssl:default`를 관찰했습니다.
- 동일 endpoint의 키·URL·모델 ID는 기존 클라이언트에서 검증됐으므로, Open WebUI 프로세스의 direct/proxy/CA 경로를 판별 중입니다.
- 기존 문서가 사내 호스트를 NO_PROXY에 넣도록 단정한 부분을 수정하고 경로 비교 후 결정하도록 변경했습니다.
- 사내 vLLM의 최초 비인증 direct/proxy 비교에서 직접 경로 403 HTML과 프록시 측 200을 관찰했습니다.
- Gateway가 Key와 발신 IP를 함께 검증하며, 프록시의 200은 CONNECT 터널 응답일 수 있어 경로 확정 판정을 철회했습니다.
- 유효한 Key를 사용해 마지막 HTTP 응답과 Content-Type을 재검증한 뒤 NO_PROXY를 결정합니다.
- 인증 포함 재검증에서는 direct가 403 `text/html`, explicit proxy가 HTTP 000이었습니다.
- 두 경로 모두 모델 API의 정상 JSON 응답을 받지 못해 proxy curl 종료 코드·TLS 오류와 기존 성공 클라이언트의 경로를 추가 확인합니다.
- explicit proxy 진단은 curl exit 28 timeout이었지만 같은 PC의 기존 Agent는 정상 동작했습니다.
- 고정 프록시 대신 direct Chat Completions를 검증하며, Gateway의 `/models` 제한 가능성 때문에 Open WebUI에는 exact Model ID를 수동 등록합니다.
- 사내 `/models` 전체 카탈로그 때문에 Embedding·Reranker도 모델 선택기에 노출됐습니다. 연결의 `Model IDs (Filter)`를 승인된 Chat 모델 allowlist로 제한합니다.
- 현재 날짜를 맞히는 응답은 Open WebUI의 시간 컨텍스트 주입으로도 가능하므로 Tool·Function 호출 성공 증거로 간주하지 않습니다.
- 새 대화에서 같은 사용자의 이전 질문을 찾는 동작을 관찰했습니다. Native Builtin Tools의 `search_chats`·`view_chat` 호출 가능성이 높으며, 이는 자동 문맥 주입·장기 Memory·사용자 간 노출과 구분합니다.
- Open WebUI Builtin Tools는 Hermes v0.19.0 API에 자동 승계되지 않습니다. MVP에서는 직접 모델과 Hermes 모델을 병행하고 Hermes 전용 preset의 Builtin Tools를 끕니다.

### 당시 제한과 보류 기록

다음은 2026-09-03 당시의 기록입니다. 현재 상태나 다음 작업 지시가 아니며, 후속 변경과 [STATUS](docs/STATUS.md)를 함께 확인합니다.

- Open WebUI 0.11.3 Workspace Skill은 단일 Markdown 지침만 저장하며 `scripts/`, `references/`, 상대경로 리소스 또는 실행 코드의 패키지 배포를 지원하지 않습니다.
- 현재 Skill 2개는 행동 지침·선택 POC이며 기존 사내 실행형 Agent Skill Package의 대체재가 아닙니다.
- 당시 실행형 Package의 실환경 검증은 미수행이었습니다. 별도 Tool Server가 필수 조건인 것은 아니며, 후속 Workspace Tool 경로는 [Confluence 가이드](docs/04-confluence-read-tool.md)에서 다룹니다.
- Open WebUI 핵심 기동은 검증됐으나 정상 모드 재시작과 계정 유지 확인은 아직 진행 전입니다.
- Open WebUI → 사내 vLLM 기본 Chat 응답과 모델 allowlist는 검증됐으나 스트리밍·문맥·반복·재시작은 아직 미검증입니다.
- Hermes gateway/API는 현재 실행 중이 아니며, 현재 우선 경로가 아닙니다. Native 평가 후 비교 여부를 결정합니다.
- 개인화와 사용자 인식형 외부 Memory는 MVP 범위에서 제외합니다.
- Docker sandbox가 없으므로 초기 Hermes Tool은 비활성화합니다.
