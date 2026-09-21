# 버전 및 환경 기준

문서 갱신일: 2026-09-17. 설치 기준 확인일은 2026-09-03이며 이후 런타임·모델 관찰은 아래 날짜별 사용자 보고를 따릅니다. 이 문서는 버전·경로·실행 전제를 관리합니다. 진행 상태·다음 작업은 [STATUS](docs/STATUS.md), 성공 여부는 [평가표](evals/scenarios.md)에서 확인합니다.

## Open WebUI 대상 환경

| 항목 | 기준 | 용도 |
|---|---|---|
| OS | Windows | 기존 개인 PC에서 소규모 팀 파일럿; Docker 사용하지 않음 |
| Open WebUI | 0.11.3 | 실행 스크립트의 고정 버전 |
| Python | 3.11 | 지원 기준. 2026-09-08 후보 준비 로그의 3.11.16 사용자 보고는 아래에 구분 |
| uv | 0.12.7 | 사용자 보고 설치 버전 |
| 로컬 접속 예제 | http://127.0.0.1:8080 | 신규 설치 예제. 현재 서버는 등록한 기존 LAN IP·포트 사용 |
| 작업 디렉터리 예제 | %LOCALAPPDATA%\EES-Agent-POC\open-webui | 신규 설치 예제. 기존 서버는 등록된 cwd 유지 |
| DATA_DIR 예제 | 위 예제 작업 디렉터리의 data 폴더 | 신규 설치 예제. 기존 서버는 등록된 data_dir 유지; Git 제외 |
| 표시 이름 | 새 기본값과 ees.7/ees.8 브랜딩: EES Work (공식본은 Open WebUI 접미사). 이전 ees.2/ees.3/ees.4/ees.5/ees.6: EES Portal | 별도로 지정한 서비스 이름과 기존 Assistant 모델 이름·ID는 유지. 실제 적용 원본은 [STATUS](docs/STATUS.md), ees.4의 대화 폭·조절 표시 정상 보고는 [화면 확인 기록](evals/scenarios.md#ees-stop-recovery)에서 관리 |
| 모델·프록시 | 승인된 사내 값; 저장소에는 placeholder | 실제 주소·키·모델 경로는 Git에 저장하지 않음 |

이 표의 예제 경로를 이미 등록한 서버에 다시 적용하지 않습니다. 실제 Python·작업 위치·DATA_DIR·수신 주소는 사내 등록 설정이 원본이며 값을 추측하거나 재등록하지 않습니다. [기존 등록과 기록 위치](docs/03-openwebui-native-agent.md#ees-local-state)를 따릅니다.

2026-09-08 [antlr4 준비 실패 로그](evals/scenarios.md#ees-antlr-runtime-observation)에서 당시 후보 venv의 Python **3.11.16**을 사용자 보고로 확인했습니다. 원래 설치 전체·실제 Uvicorn 버전을 직접 대조한 기록은 아니며 3.11 지원 기준과 구분합니다. 이는 중단한 후보 환경 방식의 관찰로, 현재 실행 환경을 새로 만들라는 지침이 아닙니다.

현재 프로그램 운영은 Windows의 등록된 Python 3.11·Open WebUI 0.11.3·로컬 SQLite/Chroma 구성을 대상으로 합니다. [단순 래퍼 방식](docs/03-openwebui-native-agent.md#ees-wrapper-maintenance)은 기존 Python·호환 의존성을 재사용하며 프로그램 파일만 관리합니다. uv 0.12.7로 별도 환경과 전체 의존성을 준비하던 이전 절차는 중단했습니다. Windows/Linux CI의 합성 검증과 사내 실제 적용 결과는 구분합니다.

새 브랜딩 배포물은 **0.11.3+ees.10**이며 기반 프로그램·의존성 요구는 0.11.3을 유지합니다. 원본 wheel SHA-256은 `8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547`로 고정합니다. [빌드·전달 방식](docs/03-openwebui-native-agent.md#release-delivery)을 따르며 사내 설치 버전은 STATUS의 실제 적용 기록으로 구분합니다. ees.1~ees.10의 시작·직전 Restore를 지원하며 새 Apply에는 ees.10 프로그램 ZIP을 사용합니다. 새 정적 자산은 `/_ees10/`에 넣어 ees.9 브라우저 캐시와 분리하고, 공장/시스템 선택·직계 펼침·글꼴·기존 대화 동작을 유지합니다.

09-21 통합 UX 베타도 프로그램 `0.11.3+ees.10`·Agent Pack `0.2.12`를 유지합니다. 같은 버전의 변경을 구분하는 원본은 **정확한 커밋·wheel/ZIP SHA-256·내용 해시가 붙은 Work 자산 URL**입니다. ApplyDemo는 버전명만 비교하지 않고 관리 내용/기록을 대조해 바뀐 Workflow Tool만 갱신합니다. 이번 파생 진행 집계는 저장 형식을 추가하지 않으며 기존 snapshot/이력과 직전 프로그램 Restore 경계를 유지합니다. [새 검증·미지원·실환경 경계](evals/scenarios.md#integrated-work-beta-20260921), [베타 적용 준비](docs/03-openwebui-native-agent.md#ees-integrated-beta-20260921).

ees.9는 [조건부 자산 적용](docs/03-openwebui-native-agent.md#conditional-assets)을 추가합니다. 단일 프로세스·등록 DATA_DIR의 로컬 SQLite에서 ApplyDemo와 native 저장 경로를 함께 보호하며 DB 형식·키·사용자 자료는 바꾸지 않습니다. Agent Pack v0.2.10은 지정 전문가 Tool의 ees.9 버전 호환을 추가하고 기존 ID를 유지합니다. 새 ApplyDemo는 보호 API가 없는 이전 프로그램에서 쓰기 전에 중단하므로 처음에는 Update → Upgrade → ApplyDemo 순서입니다. 프로그램 Restore는 사용자 자산을 되돌리지 않으며 구프로그램에서는 새 ApplyDemo가 다시 중단합니다. 기본 적용은 병합·CI·프로그램 산출물 확인 뒤 수행합니다. 2026년 9월에는 [고정 원본 시험 적용](docs/03-openwebui-native-agent.md#ees-wrapper-trial)의 `Upgrade -TrialCommit`으로 ZIP 준비·백업·프로그램/지정 자산 적용을 연결하며 데이터 Backup·프로그램 Restore를 구분합니다. 기존 ZIP Apply도 지원합니다. 실제 적용 상태는 [STATUS](docs/STATUS.md)를 따릅니다.

ees.9에서 추가한 [R1 업무 서버·정책 분리](evals/scenarios.md#workflow-refactor-20260915)를 유지합니다. 형제 Python 모듈 두 개와 공통 정책 JSON을 프로그램에 함께 넣고 공개 모듈·완성 예시 정의를 유지합니다. ees.6~ees.8 백업에는 새 파일을 요구하지 않으며 ees.9 백업은 당시 분리 모듈과 자산 보호 파일을 계속 검증합니다. R1 자체의 Agent Pack 버전은 v0.2.10이었습니다.

ees.9의 [R2 화면 분리](evals/scenarios.md#work-ui-refactor-20260915) 방식대로 소스 세 개를 런처 한 개로 조립합니다. 당시 R2는 정적 파일 경로·JS 공개 연결·Agent Pack v0.2.10을 유지했고 자산 재등록이나 데이터 이관을 요구하지 않았습니다. R3의 고정 wheel 기반 ees.8 갱신·새 자료 저장·Restore 검증은 당시 근거이며 ees.10 시험의 대체가 아닙니다. 시험 통과 범위와 원격/사내 미확인은 같은 기록에서 구분합니다.

ees.9/v0.2.10의 [메인 채팅 업무 탐색·계획](docs/mockups/ees-work/TASK.md#chat-workflow-entry-20260915)은 Workflow Tool 0.2.1과 관리 Prompt로 읽기 전용 절차 상세 및 기존 실행의 고정된 지침을 제공했습니다. ees.10/Agent Pack **v0.2.11**은 [P/T/J 패널과 대화의 공통 업무 설계](docs/mockups/ees-work/TASK.md#work-panel-chat-design-20260916)를 적용합니다. 서버의 선택 업무 조회와 최초 저장·실행 계약, Workflow Tool **0.3.0**의 대상·요청 식별자, P/T/J 표시와 Workspace 디자인을 함께 갱신하므로 프로그램과 지정 관리 자산을 같은 원본으로 적용해야 합니다. 전문가 Tool에는 ees.10 지원만 추가하며 기존 Tool·모델 ID, 개인 모델 선택·연결·비관리 자산은 유지합니다.

ees.10의 `ees-work.sqlite3`에는 첫 저장·실행의 중복 요청을 구분하는 `action_requests` 테이블을 추가합니다. 기존 정의·진행 건·결과·이력 테이블과 그 자료를 삭제하거나 재작성하지 않습니다. 이전 프로그램은 추가 테이블을 사용하지 않고 기존 진행 자료를 계속 읽고 변경할 수 있지만 새 첫 쓰기 중복 방지·선택 대상 계약을 제공하지 않습니다. 프로그램 Restore는 DB나 Agent Pack을 되돌리지 않습니다. 따라서 ees.9로 Restore한 뒤 새 Workflow Tool 0.3.0의 업무 선택·실행은 프로그램 갱신 필요로 중단하며, 구프로그램의 기존 화면과 저장 자료를 사용하는 범위만 호환 대상으로 봅니다. 실제 새 저장 자료의 구프로그램 재사용 검증 및 플랫폼별 미실행 범위는 [이번 평가 기록](evals/scenarios.md#work-panel-chat-implementation-20260917)에 따릅니다. 새 원본은 [09-17 고정 원본 시험 적용](docs/03-openwebui-native-agent.md#ees-work-panel-trial-20260917)으로 프로그램과 지정 자산을 함께 반영하며 마지막 확인된 사내 ees.9 설치와 구분합니다.

[EES Work 업무 트리](docs/03-openwebui-native-agent.md#ees-work-demo)와 기존 중앙 AI 대화·업무 패널·절차 편집은 그대로 연결됩니다. 업무 정의·사용자별 진행 건은 기존 DATA_DIR의 `ees-work.sqlite3`에 저장하며 DB/AP 점검은 모의 실행입니다. 아래 Selector 실행 파일은 공식 0.11.3만 허용하고 현재 미적용이므로 EES 전환에 함께 사용하지 않습니다.

Windows 접속 수락 오류용 [선택 실행 파일](scripts/serve_openwebui_windows.py)은 위 WebUI·Python 버전과 공식 고정 의존성 **Uvicorn 0.51.0**, 기존 SQLite·단일 worker에 한정합니다. 별도 설치·업그레이드를 수행하지 않으며 실제 사내 의존성 버전은 아직 미대조입니다. 사전검사에서 다르면 기존 환경을 보존한 채 검토합니다. [Selector 제한·적용 조건](docs/troubleshooting.md#windows-accept-winerror64).

2026-09-07 사용자는 현재 사용 중인 Windows PC를 팀 파일럿 호스트로 선택했습니다. 기존 작업 디렉터리·DB·키·버전·수동 기동 방식을 유지하며 재설치나 데이터 이전을 전제로 하지 않습니다. 사내 연결 프로필 **Public**, 우선 IP·포트 직접 접속을 사용하며 **방화벽은 사내 관리 시스템을 따른다**는 사용자 설명을 반영했습니다. 초기 주소는 `http://<PC_LAN_IPV4>:8080`이며 후속으로 [팀원 로그인 화면 접속 확인](evals/scenarios.md#assistant-resource-access-followup)을 보고받았습니다. 실제 수신 설정·관리 시스템의 정책·일반 계정 조회/격리는 직접 대조하지 않았습니다. HTTP 전송 암호화는 미적용이고 HTTPS 주소·인증서 보유 여부는 별도 미확인입니다. [관리 경로 기록](evals/scenarios.md#managed-firewall-access), [기존 PC 파일럿 안내](docs/01-openwebui-install.md#local-pc-pilot)를 따르며 전용 서버 이전은 후속 운영 필요에 따라 검토합니다.

## 사내 모델 운용 기준

2026-09-15 사용자는 사내 모델이 GLM 5.3으로 변경됐고 UI의 관련 설정을 직접 반영했다고 보고했습니다. 이는 사용자 보고 기준이며 실제 사내 서빙 설정을 직접 검사하거나 새 모델의 업무별 성능을 비교 검증한 결과는 아닙니다. 과거 GLM 5.2의 확인 기록은 당시 모델의 증거로 보존합니다.

| 구분 | 기준 |
|---|---|
| 현재 주 모델 | 사내 GLM 5.3 — 2026-09-15 사용자 UI 반영 완료 보고 |
| 모델 교체 | 이후에도 모델 변경을 전제로 하며 UI의 실제 연결값을 보존 |
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

- 2026-09-07 사용자 보고: **GitHub Enterprise Server 3.17.15**, 개인 PAT를 이미 발급받아 보유함. 후속으로 허용 저장소를 정확한 `owner/repo`로 보완한 뒤 [열린 PR 목록 정상 조회](evals/scenarios.md#github-first-list)를 보고함. 조회 전 계정 확인 경로를 근거로 해당 개인 환경의 인증·목록 조회 성공으로 판정함. PAT 종류·전체 권한·사내 기본 주소/프로토콜은 미확인이며 실제 주소·허용 저장소 값은 사내 설정에서만 관리함.
- 최초 준비·적용 안내본은 GitHub Tool **v0.1.0**이며 현재 Git 준비본과 WebUI 저장 보고의 버전·원본은 [STATUS](docs/STATUS.md)를 따릅니다. Open WebUI **0.11.3**, [GHES 3.17 PR REST API](https://docs.github.com/en/enterprise-server@3.17/rest/pulls/pulls), API 버전 헤더 **2022-11-28**을 유지합니다. GitHub.com용 구현으로 대체하거나 현재 서버 버전을 자동 변경하지 않음.
- 2026-09-07 [4b058996](https://github.com/knadalkim-a11y/team-agent-poc/commit/4b058996d1e3f360ee670da553e2f9bc7a9046a1)의 Tool 등록·검사 안내 후 `--github` 출력 사용자 보고로 새 개인 PAT 필드의 **DB 범위 PASS**를 확인함. 사내 등록 코드·checkout SHA 직접 대조는 미실행. [저장 증거](evals/scenarios.md#github-storage-check)를 보존하고 동일 플랫폼의 기존 DB/키·재시작 증거를 재사용하며 관련 변경 없는 저장 검사는 반복하지 않음.
- 후속 사용자 보고로 선택한 한 PR의 본문 요약·원문 링크 대조까지 [기본 읽기 흐름 확인](evals/scenarios.md#github-read-acceptance)을 완료함. 이후 GitHub Tool·Prompt 절 UI 저장은 [사용자 보고](evals/scenarios.md#followup-tools-saved)로 확인했으며 새 버전의 후속 조회·전체 목록 정확성·페이지 처리·마스킹 화면의 별도 관찰·사용자 격리는 미확인. 완료한 개인 환경의 목록·본문·인증·저장 검사는 관련 변경 없이 반복하지 않으며, 다음 환경·범위 선정은 [소규모 공용 파일럿 계획](docs/STATUS.md#delivery-plan)을 따름. [가이드](docs/06-github-read-tool.md), [사외 검증](evals/github-offline.md), [실환경 판정](evals/scenarios.md#github-live)

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

Work 개발 검증은 먼저 기존 시험 환경의 실행 가능 여부와 필요한 의존성을 확인합니다. 기존 환경을 재사용할 수 없고 준비가 승인된 경우 저장소의 `.venv` 한 곳을 사용하며, 기능·PR마다 별도 환경을 늘리지 않습니다. 확인된 환경은 이후 검사에서도 그대로 사용하며, 같은 요청에서 이미 허용한 준비를 다시 승인받거나 매번 재설치하지 않습니다. 기준은 Python 3.11이며 고정 의존성의 관리 원본은 [EES delivery workflow](.github/workflows/ees-delivery.yml)의 `Install fixed test dependencies` 단계입니다. 이 목록을 별도 요구사항 파일에 복제하거나 시험 때문에 운영 Open WebUI의 의존 버전을 변경하지 않습니다.

- Node는 기존 실행 파일을 재사용합니다.
- 공식 Open WebUI wheel은 앱으로 설치하지 않고 `dist/upstream`의 고정 원본 자료와 `dist/branding`의 현재 소스 시험용 묶음으로 사용합니다. 빌더의 원본 해시 검증을 유지합니다.
- Chrome은 기존 실행 파일을 우선 사용합니다. 없고 준비가 승인된 경우에만 시험용 실행 파일 하나를 `dist/tools`에 준비합니다. 이번 Work 환경에서는 공식 `chrome-headless-shell` 153.0.8010.52를 사용하며, `EES_TEST_CHROME`은 `dist/tools/headless-shell-153.0.8010.52/chrome-headless-shell-linux64/chrome-headless-shell`의 절대 경로로 지정합니다. 이 실행 환경과 full Chrome 실행 결과는 구분합니다. 이 시험 자료는 새 제품 프레임워크·상시 서버·회사 PC 실행 환경이 아닙니다.

이 기준은 임의 설치·삭제 승인이 아닙니다. 이전 환경과 checkout은 용도·로컬 변경을 확인하지 않고 지우지 않습니다. 의존성 누락으로 실행되지 않은 시험은 환경 준비 실패로 기록하고 제품 결함으로 단정하지 않습니다. 기존 PASS·SKIP을 이번 실행 결과로 재사용하지 않으며, 실제 OS·Python·라이브러리 버전과 명령·결과·미실행 범위는 [해당 평가 기록](evals/scenarios.md#evidence-index)에 남깁니다.

## 변경 규칙

- 버전 변경은 별도 작업으로 검토하고 관련 시험을 다시 실행합니다.
- 설치 옵션의 기준은 `scripts/start-openwebui.ps1`입니다. 버전 변경 시 이 문서의 환경 기준도 맞춥니다.
- 확인하지 않은 플랫폼·버전을 설치 완료로 표시하지 않습니다.
- API Key·실제 사내 주소·PAT·DB·키 파일은 버전 기록에 포함하지 않습니다.
