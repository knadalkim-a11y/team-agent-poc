# Changelog

설치·연동 완료 여부는 실제 검증 후에만 기록합니다.

## Unreleased

### Planned

- Open WebUI 0.11.3 기동 확인
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

### Observed

- Open WebUI 최초 기동은 CORS 경고까지 진행됐습니다.
- 이후 약 30분 동안 8080 listener가 없고 /health가 HTTP 000인 정체 상태를 확인했습니다.
- uv·uvx·python 프로세스는 남아 있었고, 원래 창에서 Ctrl+C 후 traceback 없이 중단됐습니다.
- import timing과 DEBUG 로그로 재실행했고, aiosqlite 설정 조회가 계속 진행되는 것을 확인했습니다.
- aiosqlite 조회 로그는 webui.db 접근을 확인할 뿐 전체 DB 초기화 진행을 증명하지 않으므로 원인 판정을 보류했습니다.
- 신규 빈 DB에서 수십 분이 걸리는 것은 정상으로 간주하지 않으며 프로세스 중복·파일 변화·import 병목을 추가 확인합니다.
- DEBUG 모드에서는 백엔드가 준비된 뒤에도 aiosqlite와 서버 로그가 계속 출력되는 것이 정상입니다.
- 브라우저 화면과 최초 계정 생성은 아직 확인 전입니다.

### Current limitations

- Open WebUI 기동은 아직 검증되지 않았습니다.
- Open WebUI → 사내 vLLM 연결은 아직 검증되지 않았습니다.
- Hermes gateway/API는 현재 실행 중이 아닙니다.
- 개인화와 사용자 인식형 외부 Memory는 MVP 범위에서 제외합니다.
- Docker sandbox가 없으므로 초기 Hermes Tool은 비활성화합니다.
