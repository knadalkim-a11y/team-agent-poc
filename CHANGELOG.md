# Changelog

설치·연동 완료 여부는 실제 검증 후에만 기록합니다.

## Unreleased

### Planned

- Open WebUI 0.11.3 정상 모드 재시작과 계정 유지 확인
- Open WebUI 직접 연결의 스트리밍·문맥·반복·재시작 검증
- Hermes 0.19.0 localhost API 호환성 확인
- Hermes Memory 비활성화와 위험 Tool 차단 검증
- 2개 사용자 계정의 데이터 격리 검증
- 팀 POC 전 Hermes 공식 설치본 전환 검토
- 검증 완료 후 서버 신규 배포

## 2026-09-03

### Added

- Windows·Docker 미사용 환경의 로컬 POC 문서 구조
- Open WebUI 실행·smoke test PowerShell
- 직접 vLLM 기준선과 Hermes 연동 절차
- 비밀정보 placeholder 정책
- MVP 검증 시나리오와 버전 기록

### Verified

- 기존 Hermes 0.19.0과 사내 모델의 CLI 질문·응답 확인
- GitHub, PyPI, Hugging Face 프록시 연결 HTTP 200
- 로컬 포트 8080과 8642에 기존 listener 없음
- Open WebUI 0.11.3 진단 실행에서 /health HTTP 200 확인
- 브라우저 UI 접속과 최초 관리자 계정 생성 확인
- Open WebUI에서 승인된 사내 Chat 모델 2종을 각각 선택해 기본 응답 확인
- 사내 Chat 모델 전환 후 각 모델의 정상 응답 확인
- 연결 allowlist로 Embedding·Reranker를 숨기고 승인된 Chat 모델만 picker에 표시

### Observed

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

### Current limitations

- Open WebUI 핵심 기동은 검증됐으나 정상 모드 재시작과 계정 유지 확인은 아직 진행 전입니다.
- Open WebUI → 사내 vLLM 기본 Chat 응답과 모델 allowlist는 검증됐으나 스트리밍·문맥·반복·재시작은 아직 미검증입니다.
- Hermes gateway/API는 현재 실행 중이 아닙니다.
- 개인화와 사용자 인식형 외부 Memory는 MVP 범위에서 제외합니다.
- Docker sandbox가 없으므로 초기 Hermes Tool은 비활성화합니다.
