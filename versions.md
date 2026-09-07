# 버전 및 환경 기준

문서 갱신일: 2026-09-07. 설치 기준 확인일은 2026-09-03이며 모델 운용 기준은 아래 사용자 보고를 따릅니다. 이 문서는 버전·경로·실행 전제를 관리합니다. 진행 상태·다음 작업은 [STATUS](docs/STATUS.md), 성공 여부는 [평가표](evals/scenarios.md)에서 확인합니다.

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

## 사내 모델 운용 기준

2026-09-06 사용자 설명 기준입니다. 제품의 공개 성능·출시 여부를 조사한 기록이나 실제 사내 서빙 설정을 검사한 결과는 아닙니다.

| 구분 | 기준 |
|---|---|
| 현재 주 모델 | 사내 GLM 5.2 |
| 후속 후보 | GLM 5.3으로 교체 가능; 이후에도 모델 변경을 전제로 함 |
| 실제 API 모델 ID·주소·옵션 | 승인된 실행 환경의 설정에서 관리; 모델 제품명으로 값을 추측하지 않음 |
| 성능 판단 | 현재 사내 모델·서빙 경로에서 측정한 기능별 결과를 사용; 새 버전의 성능 향상을 가정하지 않음 |

- Tool의 업무 로직·입력 검증·UI 템플릿에 모델 이름을 하드코딩하지 않습니다. 모델 선택과 연결 설정을 바꾼 뒤 해당 환경의 호환성을 확인하며, 교체를 위한 별도 서버·라우터는 미리 만들지 않습니다.
- 현재 모델이 안정적으로 처리하는 범위를 기준으로 작은 Tool 입력 스키마, 짧고 명확한 설명, 제한된 조회 단계를 우선합니다. 복잡한 다중 Agent 계획·긴 자동 재시도는 실제 필요와 호출 품질이 확인될 때 검토합니다.
- 반복 업무 Rich UI는 검증된 템플릿을 쓰고 모델은 허용된 화면·조회 조건을 선택하게 합니다. 매번 HTML·JavaScript를 새로 생성하는 능력을 MVP의 전제로 두지 않습니다. 기본 되묻기의 호출도 확인하고 사용할 수 없으면 일반 대화로 필요한 조건을 묻습니다.
- 모델 또는 주요 서빙 옵션을 바꾸면 기존 [평가표](evals/scenarios.md)의 같은 대표 질문으로 답의 정확성, Skill·Tool 선택, 인자, 호출 횟수와 응답 시간을 비교합니다. 비교에는 당시 모델·옵션의 비식별 표기와 Agent Pack 원본 커밋을 함께 기록합니다.
- 연결된 기능의 대표 일반 대화·조회 인자/근거·정보 부족/실패·금지 요청을 작은 묶음으로 비교합니다. 정책(P02~P10)과 Confluence(C04·C07·C08)의 영향받는 조건을 [검증 시점](evals/scenarios.md#validation-timing)에 맞춰 선택하며 전체 문답·20회 호출을 무조건 반복하지 않습니다. 모델만 바뀌고 인증·저장 경로가 그대로라면 PAT 암호화·DB 보존 시험을 자동 초기화하지 않습니다. Tool mock 통과나 개발에 사용한 외부 모델의 응답을 사내 모델 성능 증거로 대신하지 않습니다.

## Confluence 확인 환경

- 사내 표시 버전은 **9.2.21**이라는 사용자 보고를 받았습니다. [9.2 공식 릴리스 안내](https://confluence.atlassian.com/doc/confluence-9-2-release-notes-1456345480.html)는 Data Center 라이선스 전용임을 명시하므로, 보고된 버전을 기준으로 Data Center 연동 경로를 선택합니다. 사내 설치·라이선스를 직접 검사한 결과는 아닙니다.
- 준비한 Tool의 인증·API 기준은 [Confluence 설치 안내](docs/04-confluence-read-tool.md)를 따릅니다. 버전 확인을 현재 Tool의 실제 인증·조회·사용자 격리 검증 완료로 해석하지 않습니다.

## Jira 확인 환경

- Jira Tool **v0.1.1 / a6b6f2e** 적용과 기본 대시보드 흐름 정상 확인을 2026-09-07 사용자에게 보고받았습니다. 사내 등록 코드·checkout SHA의 직접 대조는 미실행입니다. 인증·API·설정 스키마는 v0.1.0과 동일합니다. [적용 범위](evals/scenarios.md#jira-dashboard-acceptance), [사외 변경 검증](evals/jira-offline.md#dashboard-design)
- 2026-09-07 사용자 보고: Jira **8.5.12**, build **805012**, sha1 **156decd**. 개인 토큰을 이미 다른 호출에 사용 중이며 시스템은 프로젝트로 구분하는 것으로 설명함. 실제 프로젝트 키는 사내 허용목록으로 관리하며 저장소에는 넣지 않음.
- Server/Data Center 라이선스 구분·토큰 발급 구현은 미확인. [공식 내장 PAT](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html)는 Jira 8.14 이상이므로 현재 사용 중인 토큰을 내장 PAT로 단정하지 않음. [8.5.12 REST API](https://docs.atlassian.com/software/jira/docs/api/REST/8.5.12/)를 기준으로 기본 비활성 Bearer 읽기 Tool을 준비함.
- 2026-09-07 후속 사용자 보고: `check-jira-auth.ps1 -AllowHttp` 안내 후 `HTTPStatus=200`, `BearerAuthenticated=True`. 해당 PC에서 HTTP Bearer 계정 확인 성공으로 판정함. [확인 범위와 앞선 차단](evals/scenarios.md#jira-bearer-check)을 보존함.
- 후속 보고로 WebUI 등록·관리자 설정·Assistant 연결·가짜 개인 PAT 마스킹과 DB 저장 검사 통과, 실제 토큰 입력 후 대시보드 정상 표시를 확인함. 이후 v0.1.1의 전체 표시·대표 건수 대조·화면 조작 확인은 위 적용 기록을 따르며 계정 격리는 미확인입니다. [저장·첫 화면 증거](evals/scenarios.md#jira-first-dashboard), [판정](evals/scenarios.md#jira-live)을 따르며 이미 끝난 인증·등록·저장 확인은 반복하지 않음.

## GitHub 확인 환경

- 2026-09-07 사용자 보고: **GitHub Enterprise Server 3.17.15**, 개인 PAT를 이미 발급받아 보유함. PAT 종류·권한·사내 기본 주소/프로토콜·허용 저장소·API 실행 성공은 아직 미확인임.
- 후보 Tool **v0.1.0**, Open WebUI **0.11.3**, [GHES 3.17 PR REST API](https://docs.github.com/en/enterprise-server@3.17/rest/pulls/pulls), API 버전 헤더 **2022-11-28**을 기준으로 준비함. GitHub.com용 구현으로 대체하거나 현재 서버 버전을 자동 변경하지 않음.
- 새 개인 필드 저장은 기존 검사기의 `--github`로 확인하며 동일 플랫폼의 기존 DB/키·재시작 증거는 재사용함. 실제 Tool/Prompt 등록·저장 검사·목록/본문 조회는 미실행. [가이드](docs/06-github-read-tool.md), [사외 검증](evals/github-offline.md), [실환경 판정](evals/scenarios.md#github-live)

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

Confluence Tool 시험은 Python 표준 라이브러리와 Pydantic 2를 사용합니다. 저장 암호화 검사와 그 합성 시험에는 `cryptography`도 필요합니다. 재현용 독립 환경의 버전 예시는 Pydantic 2.13.4·cryptography 46.0.0이며, Open WebUI 자체의 의존 버전을 이 값으로 강제하지 않습니다. 실제 실행한 OS·Python·라이브러리 버전은 [날짜별 시험 증거](evals/confluence-offline.md)에 기록합니다.

## 변경 규칙

- 버전 변경은 별도 작업으로 검토하고 관련 시험을 다시 실행합니다.
- 설치 옵션의 기준은 `scripts/start-openwebui.ps1`입니다. 버전 변경 시 이 문서의 환경 기준도 맞춥니다.
- 확인하지 않은 플랫폼·버전을 설치 완료로 표시하지 않습니다.
- API Key·실제 사내 주소·PAT·DB·키 파일은 버전 기록에 포함하지 않습니다.
