# EES Workflow · Team Agent POC

EES 팀의 비개발자 팀원이 브라우저에서 **대화와 업무 화면만으로** 사내 문서를 찾고, 관리자가 정한 절차대로 업무를 진행하도록 돕는 사내 AI 업무 플랫폼 PoC입니다. [Open WebUI](https://github.com/open-webui/open-webui) 0.11.3 위에 업무 절차의 작성·게시·실행·판정 계층을 얹었고, 인증·대화·첨부·모델 연결은 Open WebUI의 것을 그대로 씁니다.

- **팀원**은 왼쪽에서 공장·시스템과 업무를 고르고, 가운데에서 단계별 작업을 실행·판정하며, 오른쪽 대화에서 묻습니다.
- **관리자·시스템 담당자**는 업무 절차(단계 › 작업)를 작성해 게시하고, 서비스 API 명세를 등록해 작업에 연결합니다.
- **AI**는 대화에서 업무 상태를 읽고 입력 칸을 채워 제안하며 다음 할 일을 안내합니다. 확정과 저장·게시는 사람이 합니다.

![업무 절차 작성 화면: 단계 안의 두 작업에 등록한 서비스 API가 연결되어 있다](evals/artifacts/api-tools-20261113/api-v11-task-mapped.png)

![워크스페이스의 도구 화면: 서비스별로 묶인 API 명세 목록](evals/artifacts/api-tools-20261113/api-v11-tools-list.png)

위 두 장은 개발 환경에서 시험 계정과 합성 데이터로 찍은 제품 화면입니다. 같은 상태의 설계 화면과 측정값은 [제품 비교 기록](evals/artifacts/api-tools-20261113/README.md)에 있습니다.

이 문서의 앞부분은 처음 보는 사람을 위한 소개이고, [프로젝트 설계 읽기](#project-design)부터는 개발·운영 참고입니다.

## 프로젝트 목표

여러 시스템에 있는 문서 조회와 관리자가 정한 업무 절차를 한 화면의 대화와 업무 흐름으로 모으는 것이 목표입니다.

| 목표 | 사용자에게 제공할 가치 |
|---|---|
| 1. 쉬운 Chat UI | 비개발자가 브라우저에서 자연어로 질문하고 대화 맥락을 이어갈 수 있음 |
| 2. 문서 시스템 연동 | 문서 검색·본문 조회·근거 확인을 대화 안에서 수행함 |
| 3. 관리자 공통 정책 | EES Assistant 사용 시 담당자가 관리하는 공통 원칙을 적용받음 |
| 4. 관리자 워크플로 | 업무별 처리 단계·분기·확인 절차와 필요한 도구/모델 선택을 관리자가 정해 적용함 |
| 5. 레거시 시스템 연동 | EMS/APC/FDC 등의 승인된 업무 기능을 연결해 실제 데이터를 활용함 |
| 6. 레거시의 간접 UI | 연결된 기능을 조건 입력·결과 선택·필터·비교 등 대화와 업무 화면으로 쉽게 사용함 |

공통 정책의 적용 범위는 **EES Assistant를 사용하는 대화**이며 개인 모델·개인 Assistant로 확대하지 않습니다. 워크플로는 관리자가 정하는 업무 절차라는 목표이고, Hook·동적 워크플로·오케스트레이션은 필요에 따라 선택할 구현 수단입니다. 현재 Native 호출 루프나 공유 Skill만으로 관리자가 실행 순서를 제어하는 워크플로가 완성됐다고 보지 않습니다.

목표 번호는 제품의 구성 요소이며 구현 순서는 [현재 계획](docs/STATUS.md#delivery-plan)에서 관리합니다. 레거시 연결은 작은 읽기 기능부터 시작하고 해당 업무의 간접 UI를 함께 완성합니다. 필요한 기능 화면과 시각 디자인 튜닝·첫 화면/온보딩은 구분합니다. 정책·워크플로의 배치와 확장 판단은 [Native 가이드](docs/03-openwebui-native-agent.md#managed-policy-workflow)를 따릅니다.

## 어떻게 동작하나

### 전체 구성과 화면의 역할

아래는 같은 Open WebUI 안의 논리적 책임과 외부 연결입니다. 별도 서버를 추가하는 배포 설계가 아닙니다. 외부 연결의 실제 사용 가능 여부는 설치·권한·개인 설정과 해당 기능의 검증 상태를 따릅니다.

```mermaid
flowchart TD
  UI["EES 화면: 탐색·업무·대화"]
  Native["Open WebUI Native: 인증·대화·모델·자산"]
  Work["업무 서비스: 검증·저장·실행·판정"]
  DB["업무 SQLite: 초안·게시본·회차·기록"]
  Model["사내 모델"]
  Api["등록한 서비스 API: 주소·인증은 서버 설정"]
  Tool["Native 도구와 실행자의 개인 설정"]
  Source["Confluence·Jira·GitHub"]
  UI -->|"대화·계정·자산 관리"| Native
  UI -->|"인증된 업무 명령"| Work
  Native -->|"조회·제안용 업무 도구"| Work
  Native -->|"대화"| Model
  Work -->|"업무 상태 보존"| DB
  Work -->|"작업 실행 때 호출"| Api
  Work -->|"실행 때 현재 권한 확인"| Tool
  Native -->|"허용된 대화 도구 호출"| Tool
  Tool -->|"승인된 조회"| Source
```

| 사용자 화면 | 역할 | 바꿀 때 함께 확인할 것 |
|---|---|---|
| 왼쪽 탐색 | 업무/워크스페이스 전환, 작업 위치와 대상 선택 | 선택 권한·범위, 이동 뒤 목적지, 미저장 내용 |
| 가운데 업무·작성 화면 | 구조화된 입력·결과·저장·게시·실행·확정. AI에게 초안을 맡기는 요청 기능은 두지 않고 AI가 채운 값은 구분해 표시 | 저장 전/후, 실행 권한, 회차와 게시 버전, 완료 기준 |
| 오른쪽 대화 | 설명·질문·근거. AI가 사용자의 요청으로 업무 기능과 상호작용(상태 읽기·칸 채우기·다음 할 일 안내) | 개인 대화·첨부 보존, 현재 참고와 메시지 당시 참고, AI가 채운 값의 반영 여부 |

**AI의 역할(2026-10-26 사용자 결정):** 이 제품에는 업무 패널에서 ‘AI에게 초안을 맡기는 기능’이 따로 없습니다. AI는 두 가지로 쓰입니다. 하나는 오른쪽 대화에서 사용자의 요청을 받아 제품 기능과 상호작용하는 것으로, 업무 상태를 읽고 업무 패널의 입력·판정·보고 칸을 사람 확인 전 값으로 채우며 다음 할 일을 안내합니다. 다른 하나는 절차 안의 AI(LLM)로 처리하는 작업으로, 회차와 예약 실행이 다른 작업처럼 실행합니다. 어느 쪽이든 AI가 채운 값은 구분해 보이고, 사람 확인이 필요한 결과의 확정과 저장·게시는 사람이 합니다. 현재 구현된 대화 도구는 조회·입력 제안·화면 안내입니다. 수행 방법 ‘AI 초안’과 결과 형태 ‘AI 초안 검토’는 두 번째 방식의 현재 이름이며, 실행 방식은 유지하고 이름과 화면만 [화면이 바뀌는 기능의 개발 순서](AGENTS.md#design-mock-first)로 바꿉니다.

일부 자산 관리는 Native 화면을 사용합니다. EES 화면 틀과 Native 관리 화면의 전환 범위는 [메뉴 안내](docs/03-openwebui-native-agent.md#menu-integration-20261006)가 원본입니다. Figma의 목표 화면과 현재 구현의 예외를 구분합니다.

### 핵심 데이터와 변경 영향

| 대상 | 관계와 책임 | 변경 영향의 확인점 |
|---|---|---|
| 초안 | 작성자가 고치는 워크플로우 정의. 저장과 게시는 다른 행동 | 저장한 변경이 어느 게시본·회차부터 쓰이는지 |
| 게시본 | 검사와 게시로 확정된 불변 버전 | 새 게시가 이미 열린 회차의 기준을 임의로 바꾸지 않는지 |
| 회차·진행 건 | 게시 버전, 대상과 실행 범위를 가진 업무 진행 단위 | 개인 화면 선택·대화와 공동 업무 상태를 혼동하지 않는지 |
| 실행 시도·사람 판정 | 회차의 작업 실행·결과·확정 근거와 당시 기록 | 재실행 결과와 이전 근거, 현재 권한, 확정 전/후 조건 |
| 공용 도구·스킬·참고 문서 | 여러 작업이나 도우미가 참조하는 재사용 자산 | 쓰는 곳, 버전·입력/결과 호환, 저장 뒤 반영 시점·추가 조치 |
| Native 개인 자료 | 사용자 계정·대화·첨부·개인 설정·PAT | 업무 공유와 별개인 접근 권한·보존. 프로그램 갱신으로 재등록·초기화하지 않음 |

저장·게시·회차 시작·실행·결과 확정은 각각 다른 경계입니다. 도구·스킬·문서의 변경 반영 시점은 서로 같다고 가정하지 않고 해당 기능 계약을 확인합니다. 기능을 삭제·교체·병합할 때는 직접 참조하는 작업·게시본·열린 회차·기록을 확인하며, 새 규칙은 해당 기능의 원본에 한 번만 정합니다.

## 설계에서 지킨 것

- **확정은 사람이 합니다.** 대화의 AI는 조회·제안·안내만 하고, AI가 채운 값은 구분해 보입니다. 저장·게시·실행·확정은 인증된 사용자 명령을 서버가 검증합니다.
- **상태의 경계를 나눕니다.** 초안, 게시본, 회차, 실행 시도, 사람 판정을 따로 저장합니다. 게시본은 바뀌지 않는 버전이고 회차는 자신의 게시 버전을 기준으로 진행합니다.
- **연결을 좁게 엽니다.** 운영 DB 직접 연결과 범용 SQL·Shell 도구를 두지 않습니다. 서비스 주소와 인증값은 API 명세가 아니라 서버 설정에 두고, 설정에 없거나 허용되지 않은 호출은 거절합니다. [서비스 연결 조건](docs/specs/shared-tools.md#api-tools-v11)
- **없는 것을 있는 것처럼 답하지 않습니다.** 실제 연결이 없는 요청은 차단하고 성공 응답을 합성하지 않으며, 예시 데이터와 실제 실행 결과를 구별합니다.
- **프로그램과 사용자 자료를 분리합니다.** 프로그램 갱신·복원은 계정·대화·첨부·개인 설정·키를 바꾸지 않습니다. [원본과 배포본](#원본과-배포본)
- **화면 변경을 검토할 수 있게 둡니다.** Open WebUI 화면은 고정한 소스 커밋에 대한 [패치](frontend/patches/)로 바꾸고 CI에서 빌드해 해시를 검사합니다. 사내에는 CI가 만든 ZIP만 전달합니다. [유지보수 기준](docs/03-openwebui-native-agent.md#ees-wrapper-maintenance)

자세한 범위는 아래 [범위와 안전 경계](#범위와-안전-경계)에 있습니다.

## 개발 방식

구현은 AI 코딩 에이전트(ChatGPT·Codex·Claude)가 맡고, 요구사항·구현할 판 지정·병합·사내 적용은 사람이 결정합니다. 에이전트가 대화 기억 대신 저장소를 읽고 이어서 일하도록 규칙과 기록의 위치를 정해 두었습니다.

- **규칙은 한 곳에 둡니다.** 작업 범위, 검증, 종료 절차는 [AGENTS.md](AGENTS.md)가 원본이고 현재 상태는 [STATUS](docs/STATUS.md)가 원본입니다.
- **화면은 목업부터 만듭니다.** 눌러 볼 수 있는 HTML 목업과 Figma 시안을 먼저 확인하고, 사람이 구현할 판을 지정하면 제품을 그 판과 같은 창 크기·상태에서 대조합니다. [개발 순서](AGENTS.md#design-mock-first)
- **실패를 지우지 않습니다.** 최초 실패, 재시도 이유, 원인 판단과 조치를 [평가 기록](evals/scenarios.md#evidence-index)에 남기고, 개발 환경의 자동 검증과 사내 실제 확인을 구분합니다.
- **CI가 제품을 빌드해 검사합니다.** 고정 소스를 빌드해 실제 브라우저로 화면을 검사하고, Linux와 Windows에서 설치와 이전 버전 복원을 검사합니다. [EES delivery](.github/workflows/ees-delivery.yml)

## 현재 단계

기존 Windows PC 한 대에서 팀원이 브라우저로 접속하는 소규모 파일럿을 전제로 개발하고 있습니다. 기능별 구현·CI 검증·사내 적용·사용자 확인은 서로 다른 결과로 기록하며, 최신 판정은 [STATUS](docs/STATUS.md)에서 확인합니다. 이 README에는 진행 상태를 복제하지 않습니다.

---

<a id="project-design"></a>

## 프로젝트 설계 읽기

이 README를 프로젝트 설계의 진입점으로 사용합니다. 처음 참여한 사람과 개발 AI는 [목표](#프로젝트-목표) → [전체 구조와 데이터 관계](#어떻게-동작하나) → [문서 역할](#design-sources)을 읽고, 이후에는 바꾸는 기능의 원본만 따라갑니다. 코드 경로는 아래 [코드 책임 표](#코드와-배포-원본-찾기)에서 찾으며 전체 API·DB 테이블·시험 목록을 여기에 복제하지 않습니다. 대상 범위는 EES 팀과 EES 관리 시스템입니다.

<a id="design-sources"></a>

<a id="figma-active-pages"></a>

[Figma 기능 지도](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1288-2)에서 현재 설계를 찾습니다. 네 기능 페이지의 링크는 해당 페이지 헤더를 가리킵니다. 페이지 맨 위에는 머리말과 세부 기능별 구역만 있으므로, 머리말의 ‘구역 색인’에서 필요한 구역을 골라 그 안의 화면만 읽습니다.

| 활성 기능 페이지 | 확인할 화면 |
|---|---|
| [공통 · 화면 틀](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1284-3047) | 왼쪽 탐색, 가운데 업무, 오른쪽 대화, 채팅 접기·확대와 작은 화면 배치 |
| [업무 · 운영](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1284-3107) | 업무 선택, 진행 단계, 작업 결과와 판정. 셋업·장애대응 사례와 공통 운영 기준을 함께 찾습니다. |
| [워크 · 업무 절차](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1285-1830) | 절차 목록, 단계·작업 작성, 게시와 변경 기록 |
| [워크 · 도구](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1285-1842) | 도구 정의, 연결, 시험과 사용 |

[00 설계 관리](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=897-760)에서 관리 규칙을, [70 작업실](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=897-761)에서 검토 중인 시안을 찾습니다. [91 보관](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1722-1395)에는 [이전 92 작업실 보드](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2207-28518)가 있습니다.

구현 기준은 사용자가 지정한 [업무 중심 화면 1판](docs/mockups/ees-work/TASK.md#work-centered-20261106)입니다. 이전 설계는 [운영31·작성12 비교 기록](docs/mockups/ees-work/TASK.md#operations31-authoring12-parity-20261030), [업무 공통 기준](docs/mockups/ees-work/TASK.md#workflow-stage-common-standard), [워크스페이스 메뉴 2판](docs/mockups/ees-work/TASK.md#workspace-assets-prompts-20261106)에서 당시 판의 화면과 함께 확인할 수 있습니다.

### 설계 문서의 역할과 찾는 순서

| 필요한 답 | 관리 원본 | 읽고 고치는 범위 |
|---|---|---|
| 무엇을 만들고 각 부분은 어떻게 연결되는가 | 이 README의 목표·실행 구조·코드 책임 표 | 기능 간 책임이나 데이터·권한 경계가 바뀔 때 갱신 |
| 어떤 화면과 문구를 보여 주는가 | [Figma 기능 지도](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1288-2) → [네 기능 페이지의 헤더](#figma-active-pages) → 해당 화면·명세 카드 | 화면 배치·문구·상태·이동. 현재 기능마다 화면 한 벌을 유지하고 헤더에 판 번호를 기록합니다. |
| 어떤 조건에서 저장·실행·완료되는가 | 대상 브랜치의 기능 명세가 있으면 그 명세, 없으면 [TASK의 해당 기능 계약](docs/mockups/ees-work/TASK.md) | 입력·권한·상태 변화·저장/반영·완료 조건. 화면 카드에는 규칙 ID와 기능별 표시 차이만 연결 |
| 어디까지 구현·검증·사내 적용됐는가 | [STATUS](docs/STATUS.md)와 거기서 연결한 PR·Checks·[평가 기록](evals/v4-ui-20260930.md) | 구현할 판 지정·코드 구현·CI 검증·사내 확인을 구분 |
| 개발 AI는 어떻게 작업하는가 | [AGENTS.md](AGENTS.md), Claude Code 진입은 [CLAUDE.md](CLAUDE.md) | 같은 지침 원본을 사용하며 기능별 상세 문서는 필요할 때 읽음 |

**워크스페이스 → 도구**에서 서비스 API의 이름, 용도, 주소, 입력과 응답을 등록합니다. **업무 절차 → 단계 → 작업**에서 등록한 API를 선택해 사용할 값을 연결합니다. Confluence 문서 조회는 기본 가이드에서 바로 시작할 수 있습니다. [API 명세 관리](docs/specs/shared-tools.md#api-tools-v11) · [가이드 실행 및 서비스 연결](docs/specs/shared-tools.md#confluence-starter) · [워크 · 도구 화면](docs/mockups/ees-work/api-tools-20261113/README.md)

설계 관리의 이번 정리 범위와 Figma 후속 대상은 [작은 개선 계획](docs/mockups/ees-work/TASK.md#design-maintenance-20261016)에 모았습니다.

## 어디부터 읽나

- **개발을 이어갈 AI**: [AGENTS.md](AGENTS.md) → [현재 상태](docs/STATUS.md) → 해당 기능 파일과 테스트.
- **설치·운영할 사람**: [환경 기준](versions.md)을 읽고, 최초 설치는 [설치·기동](docs/01-openwebui-install.md), 기존 EES 환경의 업데이트는 [래퍼 운영](docs/03-openwebui-native-agent.md#ees-wrapper-maintenance)에서 시작합니다.
- **팀원**: [EES Workflow 시작 안내](docs/07-team-quickstart.md) — 팀 시연용 준비본. 실제 전달 상태는 STATUS에서 확인.
- **업무와 대화 화면**은 왼쪽에서 공장·시스템과 업무를 선택하고, 가운데에서 업무 진행·작성을 하며 오른쪽에서 대화합니다. 작은 화면에서는 채팅을 업무 위에 열 수 있습니다. [화면 기준과 제품 구현 계약](docs/mockups/ees-work/TASK.md#work-centered-20261106)
- **준비·배포·검증 여부 확인**: [STATUS](docs/STATUS.md)의 요약과 연결된 [평가표](evals/scenarios.md)를 확인합니다.

<details>
<summary>이전 계약과 당시 근거 찾기</summary>

아래는 지난 기능 계약과 적용 이력으로 가는 색인입니다. 현재 화면 기준은 위 [Figma 기능 페이지](#figma-active-pages)와 업무 중심 화면 1판입니다.

- **1단계 적용 이력·첫 실제 업무**: [소스 프런트엔드 적용·실패 대응](docs/03-openwebui-native-agent.md#source-frontend-apply-20261013) → [도구 등록·게시·팀원 완료](docs/07-team-quickstart.md#first-work-20261012). GitHub 토큰이 없으면 [브라우저 ZIP 적용](docs/03-openwebui-native-agent.md#source-frontend-local-zip-20261013)을 처음부터 사용합니다.
- **권한별 메뉴와 Open WebUI 왕복**: [메뉴 사용 안내](docs/03-openwebui-native-agent.md#menu-integration-20261006) · [C18 PR 1 구현 계약](docs/mockups/ees-work/TASK.md#merge-ui-20261011). EES 작성 권한과 원래 Open WebUI 권한을 구분하며 작성 중인 내용을 같은 로그인 세션에서 보존합니다.
- **시스템 담당자 작성·게시**: [v1.1 권한/보존 계약](docs/mockups/ees-work/TASK.md#system-authoring-20260924) → [가입·첫 이용·P 작성 안내](docs/07-team-quickstart.md#system-authoring-20260924) · [관리자 운영/복원/세션 경계](docs/03-openwebui-native-agent.md#system-authoring-20260924) · [SA/NU·사내 OP 평가](evals/scenarios.md#system-authoring-20260924). Native 개인 계정/그룹을 사용하고 담당 시스템의 선택 P만 저장·검사·게시합니다. 기존 업무 이용/실행/개인 자료 권한은 별도이며 A안 화면을 재사용합니다.
- **공통 Native 도구·P/T 자동 실행**: [09-25 계약·두 예제](docs/mockups/ees-work/TASK.md#shared-native-runtime-20260925) → [승인·운영·복원 경계](docs/03-openwebui-native-agent.md#shared-native-runtime-20260925) · [사용 안내](docs/07-team-quickstart.md#shared-native-runtime-20260925) · [TR-01~24 근거](evals/scenarios.md#shared-native-runtime-20260925). 기존 등록본·ACL·개인 설정으로 실행하며 채팅과 패널이 같은 영속 서비스를 사용합니다. 기존 모의 진행과 새 실행 계약을 구분하고 Windows 셋업 자동화는 후속으로 유지합니다.
- **이전 EES Work 4차 UI 구현 근거**: [v1.1 구현 범위·재사용](docs/mockups/ees-work/TASK.md#v4-ui-20260930) → [V4-01~15·실제 검증 경계](evals/v4-ui-20260930.md). 왼쪽은 공장/시스템 작업 공간과 업무 탐색, 중앙은 목록·입력/실행/결과와 상세 정보, 오른쪽은 실제 Native EES Assistant였습니다. [09-28 C안](docs/mockups/ees-work/TASK.md#c-design-phase1-20260928), [09-23 A안](docs/mockups/ees-work/TASK.md#a-design-20260923), [09-22 진행/기록](docs/mockups/ees-work/TASK.md#right-panel-20260922), [업무 패널·대화 계약](docs/mockups/ees-work/TASK.md#work-panel-chat-design-20260916)은 당시 기능/검사 근거로 보존합니다. 장기 [공동 진행과 개인 대화 분리](docs/mockups/ees-work/TASK.md#ees-work-shared-target)는 현재 사용자별 진행 건과 별개입니다.

</details>

## 저장소 지도

| 경로 | 책임 |
|---|---|
| [AGENTS.md](AGENTS.md) | 이 프로젝트를 개발하는 AI의 작업 규칙 |
| [docs/STATUS.md](docs/STATUS.md) | 현재 목표·다음 작업·미해결·Git 준비와 WebUI 적용 상태 |
| [agent-pack/](agent-pack/README.md) | 서비스 Assistant에 배포할 Prompt·정책·Skill·합성 Knowledge 원본 |
| [agent-pack/skills/confluence-read/](agent-pack/skills/confluence-read/) | 기능 단위 묶음: 지침과 실행 코드를 함께 관리 |
| [scripts/](scripts/) | 개발·운영자의 시작·점검·배포물 생성 스크립트 |
| [frontend/](frontend/) | 고정 Open WebUI 0.11.3 소스 manifest·순서가 있는 Svelte 패치; CI에서 빌드하고 사내에는 ZIP 전달 |
| [branding/ees/](branding/ees/) | EES 이름·아이콘 배포 자산; [빌드·배포 안내](docs/03-openwebui-native-agent.md#release-delivery) |
| [config/](config/) | 비밀값 없는 설정 예제 |
| [tests/](tests/) | 자동 실행하는 검증 코드 |
| [.github/workflows/](.github/workflows/ees-delivery.yml) | 빌드·설치·복원·브라우저 검사를 실행하는 CI |
| [evals/](evals/) | 합격 기준·실환경 판정·날짜별 검증 증거 |
| [docs/](docs/) | 설치·연동·장애 대응 방법 |
| [docs/specs/](docs/specs/shared-tools.md) | 기능별 명세(시범): 입력 조건·상태 변화·권한·저장/반영 시점·완료 기준. 화면 배치·문구는 Figma 명세 카드 |
| [versions.md](versions.md) | 의존 버전·환경 기준 |
| [CHANGELOG.md](CHANGELOG.md) | 완료된 변경과 과거 관찰·결정 |

폴더 상세는 `rg --files`로 확인합니다. 파일 목록을 별도 문서에 계속 복사하지 않습니다. 기능에 필요한 참고자료가 생기면 해당 Skill 아래에 `references/`를 추가하되 빈 디렉터리는 미리 만들지 않습니다.

## 코드와 관리 원본

**공식 Open WebUI 패키지와 우리 프로젝트 래퍼** 두 구성으로 관리하며, 이 저장소는 사내 설정·Agent Pack과 Open WebUI 수정사항·빌드/적용 절차를 관리합니다. 기존 Python·호환 의존성을 재사용하고 데이터·키는 프로그램 변경과 분리합니다. [단순 유지보수 기준](docs/03-openwebui-native-agent.md#ees-wrapper-maintenance)과 실제 구현·적용 상태는 [STATUS](docs/STATUS.md)를 따릅니다.

### 코드와 배포 원본 찾기

Native 대화와 업무 서비스는 같은 Open WebUI 프로세스에 있다. 업무 SQLite는 초안·불변 게시본·진행 건·실행 시도·사람 판정·예약·외부 요청을 구분한다. 사용자 화면 상태와 개인 대화는 공동 업무 상태와 분리한다. AI는 조회·제안·안내만 하고 저장·게시·실행·확정은 인증된 사용자 명령이 검증한다. 실제 EES 연결이 없는 요청은 명시적으로 차단하며 성공 응답을 합성하지 않는다.

- `AGENTS.md`는 개발 지침이며, `agent-pack/`의 공통 코드·실제 읽기 도구는 배포 원본이다.
- `skills`/`demo`라는 폴더 이름은 삭제 범위가 아니다. 기존 공통 서버 경로를 유지한다.
- 기본 업무 콘텐츠는 [Confluence 문서 확인 가이드](docs/specs/shared-tools.md#confluence-starter) 절차 한 개와 읽기 API 두 개다. Native의 Skill·Python Tool·모델 연결은 별도로 관리한다.
- Git 반영·프로그램 Restore·사용자 자산 삭제/복구·실제 사내 검증은 각각 별도 결과다.

AI 개발을 위한 다음 내부 정리는 [제한적 리팩토링 설계](docs/mockups/ees-work/TASK.md#refactoring-design)의 파일별 책임·공개 연결·자료 보존·검증 기준을 따른다. 설계와 실제 구현/배포 상태는 구분한다.

업무 서버 변경은 아래 책임에서 시작합니다. 설치 후 공개 진입점은 계속 `open_webui.ees_workflow`이며, 기능 설명·수락 조건은 위 설계, 현재 구현·배포 상태는 STATUS가 관리합니다.

| 변경할 책임 | 원본 |
|---|---|
| 공개 인증 API·이전 기록 조회 | [ees_workflow.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow.py) |
| 새 절차·게시 버전·진행 건·설정·판정·공유/개인 상태 | [ees_workflow_workspace.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_workspace.py) |
| 새 절차의 합성 예시·단계/작업 구조 | [workflow_procedure_examples.json](agent-pack/skills/ees-work-demo/scripts/workflow_procedure_examples.json), [작성 안내](docs/03-openwebui-native-agent.md#procedure-examples-20261006) |
| 예약·실행 시도·도구 검토·서버 확인·EES 요청 추적 | [ees_workflow_operations.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_operations.py) |
| 시스템 담당 인가·P별 초안/게시·legacy 보존·감사 | [ees_workflow_authoring.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_authoring.py) |
| 정의 읽기·참조/입력/게시 검증 | [ees_workflow_definition.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_definition.py) |
| 진행률·선행 대기·표시 상태 계산 | [ees_workflow_view.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_view.py) |
| 영속 계획·실행·호출·중단/재개·worker | [ees_workflow_execution.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_execution.py) |
| 서비스 API 명세 저장·버전, 작업의 입력·결과 연결, HTTP 호출, OpenAPI 읽기 | [ees_workflow_api_catalog.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_api_catalog.py), [ees_workflow_api_binding.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_api_binding.py), [ees_workflow_api_http.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_api_http.py), [ees_workflow_api_openapi.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_api_openapi.py), [명세](docs/specs/shared-tools.md#api-tools-v11) |
| 기본 Confluence 가이드의 API 명세 | [workflow_confluence_guide.json](agent-pack/skills/ees-work-demo/scripts/workflow_confluence_guide.json), [가이드 규칙](docs/specs/shared-tools.md#confluence-starter) |
| 공용 도구 확인·그룹·버전·현재 사용 가능 상태 | [ees_workflow_shared_tools.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_shared_tools.py) |
| 기존 Native 등록본 승인·현재 권한·개인 설정·호출 | [ees_workflow_native.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_native.py) |
| 코드 도구의 초안·시험·사용 버전·격리 호출. 작성·승인 제공은 [종료](docs/specs/shared-tools.md#api-tools-v11) | `agent-pack/skills/ees-work-demo/scripts/`의 `ees_workflow_tool_*.py` |
| 입력/결과 연결·완료 검증. 두 재사용 예제는 삭제되어 당시 원본으로 연결 | [ees_workflow_contract.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_contract.py), [ees_workflow_examples.py](https://github.com/knadalkim-a11y/team-agent-poc/blob/b41e23917273e1d2d0ead1ddadfea75b2dda1e32/agent-pack/skills/ees-work-demo/scripts/ees_workflow_examples.py) |
| 제한된 근거 정리와 Native 모델 호출 | [ees_workflow_model.py](agent-pack/skills/ees-work-demo/scripts/ees_workflow_model.py) |
| 공통 실행 정책 | [workflow_policy.json](agent-pack/skills/ees-work-demo/scripts/workflow_policy.json) |
| 참고 업무 절차·공장 예시(삭제됨, 당시 원본) | [workflow_seed.json](https://github.com/knadalkim-a11y/team-agent-poc/blob/b41e23917273e1d2d0ead1ddadfea75b2dda1e32/agent-pack/skills/ees-work-demo/scripts/workflow_seed.json) |

정책과 예시의 분리는 현재 저장된 게시본·초안·진행 건을 재작성하지 않습니다. AI Tool의 [workflow_tool.py](agent-pack/skills/ees-work-demo/scripts/workflow_tool.py)와 UI는 같은 공개 서비스와 권한 판정을 사용합니다.

업무 화면의 바깥 틀·탐색·Native 대화 연결은 [고정 소스 패치](frontend/patches/0001-ees-native-hooks.patch)의 Svelte 구성에서 시작합니다. 아래 `src/lib/...` 경로는 이 저장소의 별도 디렉터리가 아니라 패치가 고정 upstream 소스에 만드는 경로입니다. 기존 세 JS 소스는 명시적으로 제공된 패널·오버레이 host 안의 업무 제어·표시·편집을 담당하며 `assemble_work_launcher`에서 배포 JS로 조립됩니다.

| 변경할 책임 | 원본 |
|---|---|
| 화면 틀·Native 경로/대화·패널 크기/초점 | [소스 패치](frontend/patches/0001-ees-native-hooks.patch)의 `src/lib/components/ees/EesShell.svelte` |
| 왼쪽 탐색·범위 드롭다운 | 같은 패치의 `EesNavigation.svelte` · `EesScopeSelect.svelte` |
| Svelte 공유 상태·현재 로그인 세션의 API 요청 | 같은 패치의 `src/lib/components/ees/state.ts` · `src/lib/apis/ees-work.ts` |
| 작업 지침·참고 문서의 목록과 내용(표, 두 열 배치, 쓰는 곳, 접근 표시) | 같은 패치의 `src/lib/components/workspace/Skills.svelte` · `Knowledge.svelte` · `Skills/SkillEditor.svelte` · `Knowledge/KnowledgeBase.svelte`, 함께 쓰는 `ees/EesAssetUsage.svelte` · `ees/EesAccessTag.svelte` · `ees/assets.ts`. 시험은 [test_ees_source_shell_native.py](tests/test_ees_source_shell_native.py) |
| 서버 요청·대화 연결·개인 초안·응답 순서 | [ees-work-launcher.js](branding/ees/ui/ees-work-launcher.js) |
| 공장 선택·단계별 진행·업무 패널·조건 탐색/복귀·읽기 전용 수행 상세·크기 | [ees-work-view.js](branding/ees/ui/ees-work-view.js) |
| 시스템/P별 절차 편집·미저장 초안·권한 상태·Native 셸 복원 | [ees-work-designer.js](branding/ees/ui/ees-work-designer.js) |
| 고정 소스 프런트엔드 빌드·검증 | [build_ees_frontend.py](scripts/build_ees_frontend.py) |
| 소스 조립·wheel 파일 목록·해시 | [build_ees_webui.py](scripts/build_ees_webui.py) |
| 사내 확인용 디자인 목업(제품 CSS·아이콘·글꼴로 만든 단일 HTML, 테마 시험 글꼴은 선택) | [build_design_mock.py](scripts/build_design_mock.py), 원본 `docs/mockups/ees-work/design-mock-src/`, [개발 순서](AGENTS.md#design-mock-first) |
| Figma 설계 파일 고정 점검(읽기 전용, Figma 도구 use_figma로 실행) | [figma_check.js](scripts/figma_check.js), 시험 [test_figma_check.cjs](tests/test_figma_check.cjs), [규칙](AGENTS.md#design-mock-first) |

factory는 배포 JS 내부에만 존재하고 기존 runtime UI/Tool 연결을 유지합니다. ees.11의 P별 작성 프로토콜·추가 메타데이터와 기존 전체 초안 호환은 [별도 계약](docs/mockups/ees-work/TASK.md#system-authoring-20260924)을 따릅니다. 화면 분리와 이전 프로그램 복원 검증의 실제 범위는 [R2/R3 기록](evals/scenarios.md#work-ui-refactor-20260915)을 따릅니다.

시험은 바꾸는 책임에서 시작합니다. 아래는 대표 진입점이며 전체 시험 목록과 통과 판정을 복제하지 않습니다. 실제 실행 명령·묶음은 [기존 CI](.github/workflows/ees-delivery.yml), 합격 기준·이력은 [평가표](evals/scenarios.md)에서 확인합니다.

| 변경 범위 | 먼저 확인할 기존 시험 |
|---|---|
| 공통 화면 틀·탐색·반응형 | [소스 셸 Native](tests/test_ees_source_shell_native.py), [Figma 배치 Native](tests/test_ees_work_figma_layout_native.py), [Native 복귀 선택](tests/test_ees_native_return_selection.cjs) |
| 서비스 API 명세·작업 연결·호출 | [API 명세](tests/test_ees_api_catalog.py), [작업 연결](tests/test_ees_api_binding.py), [HTTP 호출](tests/test_ees_api_http.py), [API 명세 Native](tests/test_ees_api_catalog_native.py) |
| 공용 도구 조건·저장·실행 결과 | [공용 도구 Native](tests/test_ees_shared_tools_native.py), [workspace](tests/test_ees_work_workspace.py), [결과 계약](tests/test_ees_workflow_contract.py), [실행 UI](tests/test_ees_work_figma_runtime_ui.cjs) |

### 원본과 배포본

팀원이 만든 개인·공유 프롬프트·Skill·Tool은 허용된 생성·공유·수정 권한 안에서 WebUI에서 관리합니다. 공유할 때마다 담당자의 채택이나 Git 반영을 거칠 필요는 없습니다. 담당자가 팀 공통 배포 대상으로 채택한 항목만 검토한 버전을 Git에 보관하고, 이후에는 Git에서 변경을 관리해 해당 배포 절차로 반영합니다. 교차 분석 시연에 `ApplyDemo`를 쓰던 절차는 과거 기록입니다. 현재 ApplyDemo 재등록은 중지됐으며, 기존 사용자 자산의 변경은 승인된 해당 관리 절차를 따릅니다. 개발 환경에 없는 사용자 자산도 계속 보존하며, 프로그램 내부 리팩토링을 자산 ID 변경·재등록·초기화와 결합하지 않습니다.

사용자 작성물은 WebUI 실행 데이터와 함께 승인된 내부 백업으로 보존하는 운영 방침이며, 모든 작성물을 Git에 수집하지 않습니다. 이는 실제 사용자 권한 설정·공유 시험·백업이 완료됐다는 뜻이 아니며 자동 동기화도 구성하지 않았습니다. 실제 적용 상태는 [STATUS](docs/STATUS.md)에서 확인합니다.

| 대상 | 관리 원본 | WebUI 반영·보존 위치 |
|---|---|---|
| 모델 연결/허용 목록 | Native 관리자·사용자 설정 | 기반 모델 연결 유지; 전문 데모 preset을 기본 생성하지 않음 |
| 업무 공통 정책 | `agent-pack/policies/` | 검토 후 Prompt·Tool 구성에 반영; 자동 적용 아님 |
| 업무 Skill·지침 | Native Workspace Skills | 담당자가 명시적으로 관리; 사전 콘텐츠 등록 없음 |
| Git 관리 공통 실행 코드 | 해당 Skill의 `scripts/` | 지정 Workspace Tools에 해당 배포 절차로 반영 |
| 폐기 콘텐츠 관리 범위 | `agent-pack/ees-demo.json` | 빈 등록 목록과 역사 ID; ApplyDemo 중지, 별도 정리 미리보기/백업/승인 |
| EES Workflow 업무 절차·진행 건 | 업무 절차는 관리자/담당자의 업무 절차 작성기, 진행 건은 기존 사용자 업무 화면 | 기존 DATA_DIR의 `ees-work.sqlite3`; 대화·버전·현장별 실행 결과 보존. [관리·실행 경계](docs/03-openwebui-native-agent.md#ees-work-demo) |
| 검증용 합성 콘텐츠 | `tests/fixtures/` | 시험용; 제품에 자동 등록하지 않음 |
| 팀원 개인·공유 프롬프트·Skill·Tool·모델 | 승인된 실행 환경의 WebUI | 등록 ID·내용·연결·권한·개인 설정 보존; 내부 백업 대상 |
| 실제 PAT·DB·대화 | 승인된 실행 환경 | Git에 저장하지 않음 |

## 설치·검증 안내

| 할 일 | 안내 |
|---|---|
| Open WebUI 설치·시작 | [01-openwebui-install](docs/01-openwebui-install.md) |
| 기존 Windows PC로 팀 파일럿 시작 | [접속·계정·공유 범위 준비](docs/01-openwebui-install.md#local-pc-pilot) |
| 사내 Chat 모델 연결 | [02-vllm-direct-test](docs/02-vllm-direct-test.md) |
| 기본 Assistant 구성 | [03-openwebui-native-agent](docs/03-openwebui-native-agent.md) |
| 초기 Rich UI 제거·일반 답변으로 전환 | [기존 Tool·Prompt 갱신](docs/03-openwebui-native-agent.md#plain-output-update) |
| 수정·배포·원복 방식 | [배포 단위와 운영 명령](docs/03-openwebui-native-agent.md#release-delivery) |
| 사내 명령 한 번으로 프로그램·래퍼 업데이트 | [Upgrade 최초 준비·실행·실패 시 확인](docs/03-openwebui-native-agent.md#ees-wrapper-upgrade) |
| 업데이트·패치 반복 실패의 원인과 조치 확인 | [확인한 원인·보존 로그의 해석 범위](docs/03-openwebui-native-agent.md#ees-update-failure-causes), [날짜별 실패·수정·사내 결과](evals/scenarios.md#ees-update-failure-causes) |
| 승인된 Upgrade 종료 실패 복구 | [대상 식별·보관 ZIP 재사용](docs/03-openwebui-native-agent.md#ees-stop-recovery) |
| 과거 교차 분석 시연·일괄 등록 이력(현재 중지) | [ApplyDemo 당시 절차](docs/03-openwebui-native-agent.md#demo-assets-deployment). 현재 적용 지시로 사용하지 않음 |
| 기존 AI 대화에서 업무 탐색·실행·절차 관리 | [EES Workflow 적용·사용](docs/03-openwebui-native-agent.md#ees-work-demo) |
| 팀 시연용 첫 화면 적용 준비 | [소개 문구·예시 질문 초안](docs/03-openwebui-native-agent.md#first-use-entry) |
| Confluence Skill·Tool 등록 | [04-confluence-read-tool](docs/04-confluence-read-tool.md) |
| Jira 읽기·프로젝트별 현황 | [05-jira-read-tool](docs/05-jira-read-tool.md) |
| GitHub Enterprise PR 읽기 | [06-github-read-tool](docs/06-github-read-tool.md) |
| 오류 원인 분리 | [troubleshooting](docs/troubleshooting.md) |
| 합격 기준·실환경 기록 | [evals/scenarios](evals/scenarios.md) |
| Confluence 사외 시험 증거 | [evals/confluence-offline](evals/confluence-offline.md) |
| Jira 사외 시험 증거 | [evals/jira-offline](evals/jira-offline.md) |
| GitHub 사외 시험 증거 | [evals/github-offline](evals/github-offline.md) |
| 필요 시 Hermes 비교 | [03-hermes-integration](docs/03-hermes-integration.md) |

<a id="gpt-프로젝트-최초-설정"></a>

## 개발 AI 최초 설정

ChatGPT·Claude의 웹 대화에서 개발할 때는 아래 시작 지침을 프로젝트 지침 또는 작업 요청에 연결합니다. 파일이 존재한다는 이유만으로 웹 대화가 자동으로 읽었다고 가정하지 않습니다. 현재 상태는 대화 기억이 아니라 저장소에서 확인합니다.

<details>
<summary>설정 절차와 지침 문구</summary>

1. ChatGPT 또는 Claude에서 이 개발 작업을 이어갈 프로젝트를 만들거나 기존 프로젝트를 엽니다. 예: `EES Assistant POC`.
2. 해당 프로젝트의 **지침 / Instructions**에 아래 내용을 저장합니다. 메뉴 이름은 사용하는 앱에 따라 다를 수 있습니다.
3. 그 프로젝트 안에서 개발 대화를 시작하고, GitHub 연결이 `knadalkim-a11y/team-agent-poc`에 접근 가능한지 확인합니다. PAT를 지침이나 채팅에 넣지 않습니다.

```text
이 프로젝트의 개발 원본은 GitHub knadalkim-a11y/team-agent-poc이다.
개발 작업 시작 시 요청 대상 브랜치(미지정 시 main)의 최신 커밋을 확인하고,
그 커밋의 AGENTS.md와 docs/STATUS.md를 읽어 작업 범위·검증·문서 관리·종료 규칙을 따른다.
그다음 README.md의 project-design·design-sources에서 해당 기능의 명세·Figma·코드·시험만 찾아 읽는다.
작업 전에 읽은 커밋과 설계 근거를 짧게 밝히고, 동작 변경은 같은 PR에서 해당 명세를 갱신한다.
읽지 못한 문서를 기억으로 대신하지 않고, 기존 사용자 변경을 보존한다.
저장소 접근이나 검사 실행이 불가능하면 추정해서 완료 처리하지 말고 제한을 알린다.
```

Claude Code에서는 루트 [CLAUDE.md](CLAUDE.md)가 `AGENTS.md`를 가져오도록 연결합니다. 규칙 본문은 AGENTS 한 곳에서 관리하고 README·STATUS·TASK 전체를 자동으로 가져오지 않습니다. 실제 로드 여부는 설치 환경의 `/context`로 확인하며, 조직 설정에 의한 제한은 그대로 따릅니다. [공식 설명](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools).

관련 열린 PR을 확인하는 세부 시작 규칙은 [AGENTS.md](AGENTS.md#1-세션-시작)에서 관리합니다. 위 지침을 이미 저장했다면 같은 문구를 다시 입력할 필요는 없습니다. 변경된 규칙이 요청 대상 브랜치에 반영되면 해당 파일을 읽을 때 적용하며, 미병합 PR을 이어갈 때는 PR 번호나 브랜치를 지정하면 됩니다.

프로젝트 지침은 그 프로젝트의 대화에 공유되지만, 연결하지 않은 저장소 접근을 새로 부여하지는 않습니다. 설정 후 새 프로젝트 대화에서 한 번만 읽은 커밋·현재 다음 작업을 확인하면 연결 여부를 점검할 수 있습니다. 사용자가 이 설정을 저장했는지는 별도 확인 전까지 완료로 기록하지 않습니다. [OpenAI 프로젝트 안내](https://learn.chatgpt.com/docs/projects)

로컬 저장소 폴더에서 실행하는 Codex의 `AGENTS.md` 자동 탐색과, GitHub 연결만 사용하는 대화는 구분합니다. 이 저장소에 파일이 있다는 사실만으로 모든 대화가 자동으로 읽는다고 가정하지 않습니다. [OpenAI AGENTS 안내](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

</details>

## 문서가 쌓이지 않게 유지하는 방법

개발 AI가 [AGENTS.md](AGENTS.md)의 종료 절차에 따라 관련 문서를 갱신하고, [문서 점검기](scripts/check_docs.py)를 실행합니다. AI가 검사를 실행할 수 있는 작업 환경에서는 사용자가 매번 별도로 정리를 요청하거나 사내 PC에서 실행할 필요는 없습니다. 직접 확인하려면 저장소 루트에서 실행합니다.

```powershell
python scripts/check_docs.py
# 다른 저장소 경로나 JSON 출력이 필요한 경우
python scripts/check_docs.py --root . --json
```

<details>
<summary>점검 항목과 한계</summary>

| 구분 | 점검 내용과 처리 |
|---|---|
| 오류 | 존재하지 않는 내부 링크·Markdown 앵커·명시적 참조 정의, 저장소 밖 경로, 읽기 실패 등을 수정 |
| 검토 후보 | README·AGENTS·SKILL 진입점에서 링크로 도달하지 못하는 루트·docs·evals 문서; 유지 또는 연결 보완 여부 검토 |
| GPT 검토 | 이번 기능 변경과 설명의 일치, 중복 원본, 더 이상 맞지 않는 절차를 관련 문서에서 확인 |
| 보존 | 과거 검증 증거와 실행용 Skill·참고자료를 참조 수나 날짜만으로 삭제하지 않음 |

- 점검기는 읽기 전용·오프라인이며 파일 수정·삭제·보고서 파일 생성을 하지 않습니다. 오류는 종료 코드 `1`, 경고만 있거나 정상이면 `0`, 잘못된 CLI 인자는 `2`입니다.
- Python 표준 라이브러리만 필요합니다. 일반 인라인·참조 링크, ATX/setext 제목·HTML id를 검사하지만 전체 CommonMark 렌더러는 아닙니다. 코드 블록·주석·외부 URL은 검사하지 않으며, 여러 줄에 걸친 링크·깊게 들여쓴 목록·복잡하거나 미완성인 문법은 수동 확인 대상입니다.
- `.git`·가상환경·`node_modules`·`data`·`runtime`·`logs` 등 코드의 `IGNORED_DIRS`에 정한 폴더와 심볼릭 링크·경로가 재지정되는 항목을 스캔하지 않습니다. `.gitignore` 규칙을 해석하는 방식은 아니며, 개별 문서는 1 MiB까지 읽습니다. 크기는 Windows 체크아웃처럼 줄바꿈을 CRLF로 셌을 때로 봅니다.
- 링크가 살아 있어도 내용이 오래됐을 수 있고, 링크가 없어도 필요한 문서일 수 있습니다. 점검 통과는 문서 전체가 최신이라는 보장이 아닙니다.
- 현재는 GPT 종료 규칙과 검사 명령까지 제공합니다. 모든 커밋을 차단하는 필수 CI나 자동 삭제·정기 실행은 구성하지 않았습니다.

</details>

지난 정리 작업은 [2026-09-11 문서·브랜치 정리 기록](evals/scenarios.md#repository-maintenance-20260911)에 있습니다.

## 범위와 안전 경계

기존 Windows PC의 Docker 없는 Open WebUI를 유지하고, 팀원이 브라우저로 접속하는 소규모 파일럿부터 진행합니다. 별도 서버 이전은 가용성·사용량 등 운영 필요가 확인될 때 검토합니다. 정확한 버전은 [환경 기준](versions.md), 접속·공유 절차는 [기존 PC 파일럿 안내](docs/01-openwebui-install.md#local-pc-pilot), 현재 상태는 [STATUS](docs/STATUS.md)에서 확인합니다. 별도 Tool Server·Router·A2A·자동 동기화는 실제 필요가 확인되고 범위가 승인된 뒤에만 추가합니다.

- 운영 DB 직접 연결, DB 자격증명, 범용 SQL·Shell·쓰기 도구는 이 POC에 제공하지 않습니다.
- 승인된 읽기 전용 API 또는 Query Broker를 연결할 때에도 도구·권한·네트워크 수준의 검증이 필요합니다.
- 실제 사내 주소·PAT·API Key·개인정보·사용자 DB·대화·키 파일은 Git에 올리지 않습니다. 설정 예제는 placeholder만 사용합니다.
- 기존 PC의 DB·키·계정·버전을 유지하며, 파일럿에 필요한 접속 범위와 일반 사용자 권한을 설정합니다. 개인 환경의 저장 검사 결과가 팀원의 접속 경로·전송 보호·사용자 격리를 대신하지는 않습니다. 추후 다른 서버로 사용자 데이터를 옮기는 작업은 별도 범위로 정합니다.
- 모델 선택기의 숨김은 UI 정리입니다. 리소스 권한과 사용자 격리는 별도로 검증합니다.
