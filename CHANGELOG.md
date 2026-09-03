# Changelog

설치·연동 완료 여부는 실제 검증 후에만 기록합니다.

## Unreleased

### Planned

- Open WebUI 0.11.3 정상 모드 재시작과 계정 유지 확인
- Open WebUI에서 사내 vLLM 직접 연결 검증
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
- 사내 vLLM의 direct/proxy 비교 결과, 직접 경로는 403 HTML 차단 응답이고 프록시 경로는 HTTP 200이었습니다.
- 이 POC의 확정 경로는 사내 프록시 경유이며 NO_PROXY는 loopback 주소만 유지합니다.

### Current limitations

- Open WebUI 핵심 기동은 검증됐으나 정상 모드 재시작과 계정 유지 확인은 아직 진행 전입니다.
- Open WebUI → 사내 vLLM 연결은 아직 검증되지 않았습니다.
- Hermes gateway/API는 현재 실행 중이 아닙니다.
- 개인화와 사용자 인식형 외부 Memory는 MVP 범위에서 제외합니다.
- Docker sandbox가 없으므로 초기 Hermes Tool은 비활성화합니다.
