# 버전 및 환경 기준

기준 확인일: 2026-09-03. 이 문서는 버전·경로·실행 전제만 관리합니다. 진행 상태·다음 작업은 [STATUS](docs/STATUS.md), 성공 여부는 [평가표](evals/scenarios.md)에서 확인합니다.

## Open WebUI 대상 환경

| 항목 | 기준 | 용도 |
|---|---|---|
| OS | Windows | 개인 PC POC; Docker 사용하지 않음 |
| Open WebUI | 0.11.3 | 실행 스크립트의 고정 버전 |
| Python | 3.11 | Open WebUI 목표 런타임 |
| uv | 0.12.7 | 사용자 보고 설치 버전 |
| 접속 주소 | http://127.0.0.1:8080 | 외부에 공개하지 않는 loopback |
| 작업 디렉터리 | %LOCALAPPDATA%\EES-Agent-POC\open-webui | 기존 키를 유지하도록 동일 위치 사용 |
| DATA_DIR | 위 작업 디렉터리의 data 폴더 | 계정·대화 등 실행 데이터; Git 제외 |
| 표시 이름 | EES Assistant (Open WebUI) | Community 구성의 표시값 |
| 모델·프록시 | 승인된 사내 값; 저장소에는 placeholder | 실제 주소·키·모델 경로는 Git에 저장하지 않음 |

데이터 위치나 설치 스크립트가 실제 환경에 적용됐다는 증거를 이 표에서 대신하지 않습니다.

## 보존 중인 Hermes 환경

| 항목 | 확인된 설치 기준 |
|---|---|
| Hermes Agent | 0.19.0 (v2026.7.20) |
| 설치 방식 | uv tool / pip |
| Python | 3.12.10 |
| OpenAI SDK | 2.24.0 |
| 기존 Profile | default |
| 추후 API 비교 주소 예시 | http://127.0.0.1:8642/v1 |

기존 설치는 별도 환경입니다. 이 표는 API 기동이나 WebUI 연동을 의미하지 않으며, 프로젝트 문서 정리를 이유로 재설치·업그레이드하지 않습니다.

## 독립 자동 시험 환경

Confluence Tool 시험은 Python 표준 라이브러리와 Pydantic 2를 사용합니다. 재현용 독립 환경의 Pydantic 버전 예시는 2.13.4이며, Open WebUI 자체의 의존 버전을 이 값으로 강제하지 않습니다. 실제 실행한 OS·Python·라이브러리 버전은 [날짜별 시험 증거](evals/confluence-offline.md)에 기록합니다.

## 변경 규칙

- 버전 변경은 별도 작업으로 검토하고 관련 시험을 다시 실행합니다.
- 설치 옵션의 기준은 `scripts/start-openwebui.ps1`입니다. 버전 변경 시 이 문서의 환경 기준도 맞춥니다.
- 확인하지 않은 플랫폼·버전을 설치 완료로 표시하지 않습니다.
- API Key·실제 사내 주소·PAT·DB·키 파일은 버전 기록에 포함하지 않습니다.
