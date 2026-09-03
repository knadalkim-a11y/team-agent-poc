# 버전 및 실행 환경

기준일: 2026-09-03

## 확인된 환경

| 항목 | 값 | 상태 |
|---|---|---|
| OS | Windows, Docker 미사용 | 확인 |
| Hermes Agent | 0.19.0 (v2026.7.20) | 설치 확인 |
| Hermes 설치 방식 | uv tool / pip | 확인 |
| Hermes Python | 3.12.10 | 확인 |
| OpenAI SDK | 2.24.0 | 확인 |
| uv | 0.12.7 | 확인 |
| Hermes profile | default | 확인 |
| Hermes model | <INTERNAL_MODEL_PATH> | 실제 값 비공개 |
| Hermes gateway | stopped | 현재 미기동 |

## Open WebUI POC 고정값

| 항목 | 값 | 상태 |
|---|---|---|
| Open WebUI | 0.11.3 | /health 200, UI 접속·관리자 계정 생성 확인 |
| Python | 3.11 | 목표 런타임 |
| 주소 | http://127.0.0.1:8080 | /health HTTP 200 |
| DATA_DIR | %LOCALAPPDATA%\EES-Agent-POC\open-webui\data | 사용 여부 미검증 |
| Hermes API | http://127.0.0.1:8642/v1 | 미기동 |
| 외부 다운로드 프록시 | <CORPORATE_PROXY_URL> | 실제 값 비공개 |

GitHub·PyPI·Hugging Face 프록시 연결 시험은 모두 HTTP 200이었습니다. 이는 다운로드 경로 확인 결과이며 Open WebUI 설치·기동 성공을 의미하지 않습니다.

## 계획된 전환

| 항목 | 계획 | 상태 |
|---|---|---|
| Hermes API smoke test | 0.19.0으로 localhost에서만 확인 | 대기 |
| Hermes 공식 설치본 | 팀 POC 전에 최신 검증 버전으로 전환 | 미적용 |
| 서버 배포 | 로컬 Gate 통과 후 신규 설치 | 미적용 |

## 갱신 규칙

- 버전 변경은 날짜와 재검증 결과와 함께 기록합니다.
- API Key, 실제 사내 주소·모델 경로·프록시는 저장하지 않습니다.
- POC 중에는 정상 동작 중인 Hermes default Profile을 직접 변경하지 않습니다.
- 버전을 변경하면 evals/scenarios.md의 핵심 시나리오를 다시 실행합니다.
