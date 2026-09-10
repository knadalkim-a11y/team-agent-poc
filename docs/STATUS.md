# 현재 작업 상태

갱신일: 2026-09-10

계획·다음 작업·적용 원본을 관리합니다. 시험 판정은 [평가표](../evals/scenarios.md), 환경은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 목표와 이번 작업

- 목표: [여섯 가지 프로젝트 목표](../README.md#프로젝트-목표)에 따라 쉬운 Chat UI·문서 시스템·관리자 공통 정책·관리자 워크플로·레거시 연동·레거시 간접 UI를 제공함. 범용 Assistant·팀원 Prompt/Skill 공유를 유지하고 Open WebUI Native와 Git Agent Pack을 우선 활용함.
- 현재 위치: **단순 래퍼와 EES 이름·로고의 사내 적용 작업 단위를 완료함.** 2026-09-09 사용자 보고로 Apply -Resume/Start 성공에 이어 이름·로고 변경, 기존 대화 유지, 평소 Jira·Confluence·GitHub 조회 정상을 확인함. 이후 실시간 가동·장기 안정성·rename/SSL 원인 해소까지 확인한 것은 아님. [적용·사용 흐름 근거](../evals/scenarios.md#ees-wrapper-manual-resume).
- 이번 작업: **복구 안내 뒤 사용자 화면의 EES Portal 이름 표시를 확인함.** 2026-09-10 사용자가 이름 변경을 확인했다고 보고함. 개별 Apply -Resume/Start/ApplyDemo 출력·실제 적용 SHA·패널 v0.1.3 반영은 별도 미확인으로 유지함. promote 접근 거부의 원인 해소나 장기 안정성까지 확인한 것은 아님. [실패·후속 확인](../evals/scenarios.md#ees-portal-upgrade-apply-failure).
- 다음 작업 하나: **새 EES 대화에서 협업 패널 가독성과 조립 2라인 예시질문을 확인한다.** Portal 표시 확인 뒤 복구 블록을 다시 실행하지 않음. 전문가 회신을 먼저 읽고 상세 질문·근거를 펼칠 수 있는지와 현실적인 시작 질문 표시를 짧게 확인하며, 새 적용이나 재시작은 그 결과에 따라 필요한 경우만 안내함. [화면·질문 확인](03-openwebui-native-agent.md#demo-assets-deployment).
- 공유 DB 전제와 후속: 여러 시스템이 하나의 물리 DB와 일부 공통 데이터를 사용하나 각 담당자는 자기 시스템 지식에 집중되어 있음. [관계 발견 설계](03-openwebui-native-agent.md#shared-db-relations)는 운영 데이터 연결을 준비할 때 사용하며 현재 시연 범위에서 제외함. 시스템 간 실제 의미·접근 권한·스키마는 아직 조사하지 않음.
- 배포 확인: 패널 v0.1.3 [PR #24](https://github.com/knadalkim-a11y/team-agent-poc/pull/24)를 main `a6f108796d818510c44a6c0d6408823bdb8b6611`에 반영했고 PR/main Windows/Linux CI·Agent Pack 생성을 완료함. Portal 프로그램 입력은 같아 기존 `0336cb8311789cd3f70785f1bd170cd2bd9148ce` 산출물을 재사용할 수 있음을 확인함. 사내 Upgrade의 apply 실패 뒤 수동 복구를 안내했고, 후속 사용자 보고로 Portal 이름 표시를 확인함. 개별 운영 명령 결과와 v0.1.3 자산 실적용은 미확인. 사용자 전달 wrapper는 `a6f108798d81`로 원격 SHA 접두사와 한 글자 차이가 있어 전체 사내 checkout 대조 없이 동일 SHA로 확정하지 않음. [실패 기록](../evals/scenarios.md#ees-portal-upgrade-apply-failure).
- 설비 조회 관리 합의: 여러 업무에서 쓰는 공통 기능이므로 운영용 설계에서는 독립 Tool로 등록·관리하는 방향을 유지함. 사용자는 이번 시연에 한해 적용이 간단한 기존 단일 등록 항목을 유지하기로 함. 현재는 같은 Tool 안의 함수 분리이며 별도 등록 완료가 아님. 후속 요청의 설비 조회 패널도 같은 등록 항목에서 제공하며 새 적용 성공 보고로 간주하지 않음.
- 첫 화면 제안: 기본 영어 문구를 대체할 천안 설비·헝가리 설비·AI WO 초안·직접 선택의 네 질문을 준비하고, v0.1.2의 Tool·WO 지침·제안 갱신 안내를 수행했다는 사용자 보고를 받음. 첫 조회 시연 중 대화 이동 후 패널 소실을 보고했으며 제안 네 개의 실제 등록 원문·각 클릭 결과를 직접 대조한 것은 아님. 이번 수정은 제안 JSON을 바꾸지 않음. [적용 안내](03-openwebui-native-agent.md#first-use-entry).
- 완료한 이전 단위: 초기 Rich UI 제거·일반 문장/표/원문 링크 전환의 구현·검증·main 반영에 이어 **제거 작업과 변경 프롬프트의 WebUI 반영 완료를 사용자 보고로 확인함.** 개별 Tool 등록 내용·적용 SHA·새 조회/원문 결과의 직접 대조는 미확인으로 유지하며 저장 절차를 반복 안내하지 않음. [적용 보고](../evals/scenarios.md#plain-output-applied-report), [변경·검증](../evals/scenarios.md#prototype-rich-ui-removal).
- 후속 UI 방향: **준비된 업무 화면을 상황에 맞게 활용하고 같은 폼에서 직접 입력과 AI 작성·수정을 함께 지원함.** 사용자가 확인한 검색 계층은 SHOP → LINE → PROCESS이며, 시연 피드백을 받은 뒤 운영용 화면을 구체화함. 실제 WO 발행은 사용자의 최종 버튼과 서버 검증을 거치는 [설계 기준](03-openwebui-native-agent.md#legacy-ui-design)을 유지하며 현재는 샘플 시연만 제공함.
- 관리자 공지 후속 요구: 첫 시작의 영어 `새로운 기능 EES Assistant`·v0.11.3 릴리스 노트는 향후 관리자 팀 공지 용도로 활용하고자 함. UI 설계 방향 기록에 팝업 수정·공지 구현은 포함하지 않음.

아래는 **중단한 후보 환경 방식의 구현·진단 이력**이며 현재 재실행 목록이 아닙니다. [manage_ees.py](../scripts/manage_ees.py)·[ees_deploy_process.py](../scripts/ees_deploy_process.py)와 [전환 시험](../tests/test_manage_ees.py)·[프로세스 시험](../tests/test_ees_deploy_process.py)은 보존합니다. 기존 도구의 Rollback을 새 직접 적용 방식의 원복 기능으로 간주하지 않습니다. 마지막 실패와 원인 미확정 상태를 유지하며 관리 방식 변경을 배포 성공으로 기록하지 않습니다.

진단 보완 코드 원본은 `1ac1c33cf50cb3135f63c7ed8ac5ccaf22cdab30`이며 [Windows/Linux CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34184761238) 성공을 확인했습니다. PR #7의 main 병합과 사내 `c5f1690...` Update/Status 실행은 사용자 보고로 확인했으며 전체 SHA·등록 내용 직접 대조는 미실행입니다. 프로그램 후보 ZIP 원본 및 EES 전환 성공 여부와 구분합니다.

CA 옵션 운영 코드 원본은 `6a2638be157c125dd12ad70c95de075cbe77d1ce`, main 병합은 `d9cb7cd87d0c93dec6485407b280aa04b505e4a3`입니다. [PR의 Windows/Linux CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34190121123)는 성공했습니다. Update/옵션을 포함한 명령 안내 뒤 위 배포 실패를 보고받았으며, 실제 명령·checkout SHA·후보 환경 원문은 직접 대조하지 않았습니다. 이 SHA를 프로그램 Deploy의 Commit으로 사용하지 않습니다.

Diagnose 운영 코드 원본은 `70e7b9f268029bbc161f03b5f364130d2cd24239`, [PR #9](https://github.com/knadalkim-a11y/team-agent-poc/pull/9) 병합은 `36974ce45ff46a1e7fc830c2325873f14546f8e5`입니다. [Windows/Linux CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34201413944)는 성공했습니다. 이후 수신한 v2 사내 결과는 아래 기록으로 이어집니다. 프로그램 후보의 Deploy Commit과 구분합니다.

Diagnose v2 운영 코드 원본은 `2cb6b55f8ff2dc38ecd8a2ca39d30a7e6951d876`이며 [PR #10](https://github.com/knadalkim-a11y/team-agent-poc/pull/10)의 [Windows/Linux CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34281735662)는 성공했습니다. main 병합은 `50c2a1f7bcaa80b6ee64252bd74bbece30fb098d`입니다. 사내 v2 실행 결과를 수신했으며 전체 checkout SHA 직접 대조·추가 Deploy는 미실행입니다. 기존 준비 프로그램 `4a8779bbf3ee078abe8c94ff75b59fa3bb7aad50`과 DB·키·CA 선택·대기 한도를 유지하며, 프로그램 ZIP을 다시 준비하지 않습니다.

ProbeImports 시간 기준 수정 원본은 `25e4af3972d3b46a232c24216741aececa96502b`이며 [PR #14](https://github.com/knadalkim-a11y/team-agent-poc/pull/14)의 [Windows/Linux Python 3.11 CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34288461465)는 성공했습니다. main 병합은 `4656464b76e94222378872b76d56d3e87adedc76`입니다. 앞선 PR #11~13 근거는 [기본 검사](../evals/scenarios.md#ees-import-probe)·[전달 보완](../evals/scenarios.md#ees-typed-handoff)·[프로필 수정](../evals/scenarios.md#ees-import-followup)에 보존합니다. 수정 후 안내에 따른 새 I1/T1 사용자 보고를 수신했으며, 전체 사내 checkout SHA·후보 세부 지연 원인·실제 EES 전환 성공은 미확인입니다. 기존 프로그램 ZIP의 Deploy Commit은 계속 `4a8779bbf3ee078abe8c94ff75b59fa3bb7aad50`입니다.

<a id="resume-branch"></a>

## 최신 main에서 재개

**다음 개발은 원격 최신 main을 기준으로 시작합니다.** PR #5 → #4 → #3 → #2의 [통합 커밋 3184b78](https://github.com/knadalkim-a11y/team-agent-poc/commit/3184b78ccb3d4d8a4977055693cb6d58728caa01)과 이후 [PR #6의 프로그램 원본 4a8779b](../evals/scenarios.md#ees-program-deployment)는 과거 병합/배포물 이력입니다. 이를 최신 개발 head로 고정하지 않으며 재개 시 원격 main을 확인합니다.

재개 시 최신 main 커밋의 AGENTS·이 문서를 읽고 그때 관련 열린 PR이 있는지만 확인합니다. 관련 후속 수정은 기존 PR에서 마무리하며 새 PR을 미병합 PR 위에 계속 쌓지 않습니다. 이전 PR별 원본·병합 결과는 [통합 기록](../evals/scenarios.md#pr-stack-review)에 보존합니다. 아래 사내 수동 적용 원본은 Git 최신 main과 구분합니다.

**2026-09-09 구현 시작 기준:** 원격 main `99ab68064a70a88da4b988d349dd1c45e30e7022`, tree `482e8853f71d60799a6dfc80294bf7b6ff6a775e`, 당시 관련 열린 PR 0개를 확인했습니다. 같은 tree의 로컬 비교 스냅샷에서 구현한 `feat/simple-webui-wrapper`를 [PR #15](https://github.com/knadalkim-a11y/team-agent-poc/pull/15)에 게시했습니다. 실행 코드 원본 `aa005f0edad338357438d70b9933a2bdb58c5b50`의 Windows/Linux CI와 독립 검토는 완료했으며 [PR #15 병합 b65e7fb](https://github.com/knadalkim-a11y/team-agent-poc/commit/b65e7fbbee612a8e34f7fd4136ca5cdc919fd082)을 확인했습니다. 다음 작업에서 이 SHA를 최신 head로 고정하지 않고 그때의 main·관련 열린 PR을 확인합니다. 이전 새 대화 준비 근거는 [기존 기록](../evals/scenarios.md#ees-wrapper-resume)에 보존합니다.

- 이번 Rich UI 제거 시작 기준: 2026-09-09 원격 main `99a9ee`·관련 열린 PR 0개를 확인함. 다음 재개 때 이 SHA를 최신 head로 고정하지 않음.
- 읽을 범위: AGENTS·이 문서 → [협업 패널](03-openwebui-native-agent.md#cooperation-panel)·[이번 검증](../evals/scenarios.md#cross-system-demo-readability) → 해당 구현·검사. 이번 시작 기준 원격 main `0336cb8311789cd3f70785f1bd170cd2bd9148ce`·관련 열린 PR 0개. 기존 WO·공통 조회는 유지하며 완료한 수동 저장 절차와 중단한 후보 진단을 재실행 목록으로 읽지 않음.
- 완료한 단위: 초기 Rich UI 제거의 Git 구현·검증·main 반영에 이어, 제거 작업과 변경 프롬프트의 WebUI 반영 완료를 사용자 보고로 확인함. 실제 등록 코드·적용 SHA·새 조회의 상세 출력 검증과 구분하며, 기존 프로그램 적용·기동·인증 전수 검사를 반복하지 않음. [적용 보고](../evals/scenarios.md#plain-output-applied-report).
- 마지막 서버 증거: **2026-09-10 접속 불가 시 등록 프로세스는 생존했으나 해당 포트의 Listen은 없었고, Stop/Start/ApplyDemo 순차 안내 뒤 ApplyDemo 성공을 보고받음.** 당시 `ip=True listen=False http=000 curl=28`, 현재 프로세스 로그 `age_min=31.1 tail200=winerror_64`를 수신함. WinError 64의 원인 여부와 장애 발생 시각은 미확정이며 31.1분은 로그 마지막 수정 후 경과 시간임. 성공 시점의 WebUI API 접근·자산 적용은 확인됐으나 이번 Stop/Start 개별 출력·브라우저 채팅·장기 안정성은 별도 확인하지 않음. [이번 적용·장애 근거](../evals/scenarios.md#cross-system-demo-internal-apply), [이전 접속·기동 지연](../evals/scenarios.md#ees-start-health-followup).
- 사내 결과는 직접 타이핑 1~2줄만 가능하며 전체 출력·파일·화면 사진을 요청하지 않습니다. 명령 블록은 각각 2,500자 이내로 준비하고, 상세 결과는 사내에 저장합니다. [재개 준비 점검](../evals/scenarios.md#ees-wrapper-resume).

<a id="delivery-plan"></a>

## 실행 계획

| 목표 | 현재 근거와 남은 범위 | 다음 구현 단위 |
|---|---|---|
| 1. 쉬운 Chat UI | 대화·스트리밍·이름/로고와 초기 Rich UI 제거 작업 완료 보고. 실제 비개발자 사용성 전체는 미확인 | 합의한 목업 우선 방식으로 필요한 업무 화면을 하나씩 설계. 관리자 공지는 후속 요구 |
| 2. 문서 시스템 연동 | 평소 세 연동 조회 정상의 기존 보고와 Rich UI 제거·변경 프롬프트 WebUI 반영 완료 보고. 새 출력의 개별 검증은 별도 미확인 | 실제 업무에 필요한 조회·후속 해석 보완. 새 일반 답변·원문 확인은 다음 관련 사용/변경에 묶음 |
| 3. 관리자 공통 정책 | EES Assistant에 합성 공통 지침·정책 답변 Skill 저장 보고. 실제 사내 정책 적용은 미완료 | EES 전용 공통 원칙·상세 절차·권한/Tool 제한의 배치와 관리자 변경 반영을 정리 |
| 4. 관리자 워크플로 | 도구 자동 선택과 협업 패널 열림·전문가 질문/회신 표시를 사용자 보고로 확인. 글이 많다는 피드백에 v0.1.3 가독성·업무 질문 개선 | 새 표현을 적용해 읽기 편해졌는지 확인. 반증·EMS 단독·분석 정확성은 후속 |
| 5. 레거시 시스템 연동 | EMS/APC/FDC의 실제 업무 기능은 미연결 | 승인된 API 또는 Query Broker로 가치가 있는 읽기 기능 하나 연결. 기존 서비스 권한·업무 규칙 활용 |
| 6. 레거시 간접 UI | v0.1.3 기능 정상 보고와 이후 `panel_error` 이력 보존. v0.1.5 갱신 안내 후 패널 표시 성공을 사용자 보고로 확인. 최초 원인·장기 재발 여부는 미확정 | 시연 피드백 반영 → 운영용 목업 → 실제 EMS 구현. [목업](03-openwebui-native-agent.md#wo-mockup) |

**개발 순서:** 1·2의 이름·로고와 래퍼 사내 적용 완료 → 초기 Rich UI 제거·변경 프롬프트 WebUI 반영 완료 보고 → 3의 EES 전용 공통 정책 → 4의 대표 워크플로 하나 → 5·6의 레거시 업무 하나를 함께 연결. 새 UI는 해당 업무 수요를 정하고 목업·사용자 확인을 거쳐 하나씩 구현하며, 4번은 단순 절차 지침과 실행 코드로 보장할 단계를 구분함. [구현 수단 선택](03-openwebui-native-agent.md#managed-policy-workflow)과 [남은 권한·격리 조건](../evals/scenarios.md#validation-timing)을 따름.

2026-09-09 사용자의 명시 요청으로 **6의 WO 시연용 목업·피드백을 먼저 진행**합니다. 기존 대화창과 우측 패널에서 시연한 뒤 운영용 목업을 정하고 실제 EMS를 연결합니다. 공통 정책·대표 워크플로의 미완료 상태는 유지하며 권한 세분화·상세 운영 설계를 시연의 선행 조건으로 늘리지 않습니다.

2026-09-10에는 **4의 시스템 간 분석 시연 목표**를 추가로 정했습니다. EES가 여러 전문 Assistant의 근거를 연결하고 가설을 수정하는 흐름을 보여주며, 앞선 WO 시연·운영 연결 계획은 유지합니다. EMS/APC/FDC 합성 교차 분석은 첫 시연 제안이고 EGIS/EPT 등은 실제 역량·연결 범위를 확인해 추가합니다. 전체 시스템 연결이나 대형 오케스트레이션 기반을 선행 조건으로 두지 않습니다.

현재 첫 공용 파일럿에 준비한 업무 기반은 **범용 채팅 + Confluence·Jira·GitHub 읽기**입니다. 여기에 EES 공통 정책과 대표 워크플로를 적용하는 방향으로 확장합니다. 기존 Tool·Skill·모델 전체를 Public으로 바꿨다는 사용자 보고가 있으며, 개인 환경의 조회 성공과 이 설정 변경을 모든 연동의 일반 사용자 조회·격리 검증 완료로 간주하지 않습니다. GitHub·EMS/APC/FDC 전체 연동이나 Hermes 도입을 MVP 완료 조건으로 두지 않습니다. 파일럿에서 비개발자가 실제 업무 흐름을 완료하고 결과·오류·공유를 이해하는 것까지가 첫 배포의 목표입니다.

이 업무 목록은 현재 연결 기능이며 Assistant의 고정 역할이나 최종 기능 목록이 아닙니다. 범용 대화와 필요에 따른 기능 확장을 유지하고, 팀 시연용 소개·예시를 먼저 적용 준비한 뒤 실제로 자주 쓰이는 업무에 맞춰 다듬습니다. 안정화는 기능 전체를 동결하거나 평가표를 처음부터 반복하는 단계가 아닙니다.

기능별 업무 흐름을 구현·검증 단위로 유지합니다. 초기 Rich UI 제거와 변경 프롬프트 반영 완료 보고는 [적용 기록](../evals/scenarios.md#plain-output-applied-report)에 보존하고, 후속 기능의 필요한 구현·확인을 묶습니다. 제품 확인 → 작은 읽기 기능·필요한 답변 → GPT의 코드/합성 검사 → 사내의 짧은 확인 묶음 → 결과 반영 순서로 진행합니다. 단계별 실제 권한·배포 승인을 대신하는 계획은 아닙니다. 구체 등록/화면 경계는 [Native 가이드](03-openwebui-native-agent.md#rich-ui), 시험 시점은 [평가표](../evals/scenarios.md#validation-timing)에만 관리합니다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 교차 분석 시연 | v0.1.3 회신 중심 패널·가상 조립 2라인 시작 질문·기존 두 Tool에 화면 포함 | 2026-09-10 사용자 보고로 패널 열림과 전문가 카드의 질문·회신 표시 확인. 가독성 개선 요청. 실제 수치/회신 정확성·새 v0.1.3 사용성은 미확인 | [이번 개선](../evals/scenarios.md#cross-system-demo-readability), [패널 검증](../evals/scenarios.md#cross-system-demo-panel), [최초 적용](../evals/scenarios.md#cross-system-demo-internal-apply) | 패널 적용 안내 원본 `0336cb8311789cd3f70785f1bd170cd2bd9148ce`(v0.1.2), 실제 사내 SHA는 직접 대조하지 않음. 최초 확인 자산 `502344d55154`와 프로그램 `4a8779bbf3ee` 기록 보존 |
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| WO 시연 목업 | EES WO Demo v0.1.7: 패널 서비스 이름 EES Portal. v0.1.6 크기 조절 표시·기존 진단·복원·조회/WO 동작 유지 | 2026-09-09 v0.1.6 적용·크기 조절 정상 보고. 앞선 v0.1.5 패널 표시 성공과 최초 예외 원인 미확정은 보존. 실제 EMS 미연결 | [시연 검사·후속 보고](../evals/scenarios.md#wo-mockup), [기존 항목 갱신](03-openwebui-native-agent.md#wo-mockup) | 적용·정상 보고 직전 안내 원본 `ba396da8d1d0abcb4e17494e8d9b37c5add514fc`(v0.1.6); 사내 등록 바이트·전체 SHA 직접 대조 미실행. 이전 성공·실패 이력은 평가 기록에 보존. PR #19 main 병합 `cb3a922d870663abd7f5fd576ba23456575e49a2` 확인 |
| 팀 시연용 이름·소개·시작 질문 | 기존 모델 이름·소개·프로필 적용 안내, 목업 제안 JSON 4개·짧은 팀원 안내 | 2026-09-09 서비스 이름·로고 변경에 이어 목업 제안을 포함한 v0.1.2 갱신 수행 보고 수신. 모델 소개·팀원 전달·제안별 전체 클릭 결과는 미확인 | [목업 적용 보고](../evals/scenarios.md#wo-mockup), [서비스 이름·로고 확인](../evals/scenarios.md#ees-wrapper-manual-resume), [시연 준비](../evals/scenarios.md#team-demo-customization), [이전 준비](../evals/scenarios.md#team-first-use-preparation), [당시 보류](../evals/scenarios.md#onboarding-deferred) | 서비스 브랜딩은 아래 프로그램 원본. [제안 JSON](../agent-pack/ees-prompt-suggestions.json)의 안내 원본 `5a80ac6d`; 사내 등록 내용·SHA 직접 대조 미실행 |
| EES 프로그램·전달 도구 | EES Portal ees.2와 Upgrade의 CI 확인·래퍼/프로그램 일괄 갱신 준비. 기존 ees.1 Start/Restore와 수동 Apply 유지 | Apply/CheckOnly·직전 Restore·운영 연결·오류 보존·수동 승격 후 Resume 구현/Windows/Linux 실제 wheel CI/독립 검토/main 반영 완료(PR #15~17). 2026-09-09 수동 변경 뒤 Apply -Resume=ok/changed true/4a8779bbf3ee/complete/customized, Start=ok/같은 commit/complete/customized/running true와 이름·로고·기존 대화·세 연동 정상 보고. 이후 접속 불가·Start health_check 실패에 이어 기존 웹 주소 접속 성공 보고. 최초 프로세스 종료는 확인되지 않았으며 밤사이 접속 불가·기동 지연 원인은 미확정. 2026-09-10 복구 안내 뒤 사용자 화면의 EES Portal 이름 표시 확인. 개별 Resume/Start/ApplyDemo 결과·실제 적용 SHA·패널 v0.1.3은 별도 미확인 | [Upgrade 준비·검증](../evals/scenarios.md#ees-wrapper-upgrade), [사내 성공과 CI](../evals/scenarios.md#ees-wrapper-manual-resume), [현재 적용 안내](03-openwebui-native-agent.md#ees-wrapper-upgrade), [구현 검증](../evals/scenarios.md#ees-wrapper-implementation), [준비 성공](../evals/scenarios.md#ees-prepare-completed), [이전 복구](../evals/scenarios.md#ees-original-recovered), [이번 health 실패·복구](../evals/scenarios.md#ees-retransition-health-failure), [프로그램 CI](../evals/scenarios.md#ees-program-deployment) | 이전 확인 프로그램 원본 `4a8779bbf3ee078abe8c94ff75b59fa3bb7aad50`, 내부 ZIP `EES-demo-4a8779bbf3ee.zip`. 운영 코드의 [캐시 복구 추가 원본 15cd88b](https://github.com/knadalkim-a11y/team-agent-poc/commit/15cd88b5a99142c07c4d8cca4dcdd957354d48cb)와 구분. 사내 checkout 전체 SHA 직접 대조 미실행. Portal 표시 확인 시점의 실제 적용 SHA도 미확인 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 2026-09-07 두 지침 UI 저장 보고; 개정 후 P02 PASS, P03 창작 거절 부분 확인, P04~P10 미완료; 실행 시점은 평가표 | [P02~P10 재검증](../evals/scenarios.md#instruction-revision), [기존 지침 갱신](03-openwebui-native-agent.md#update-existing-instructions) | 전달·저장 안내 원본 [dfeb95f](https://github.com/knadalkim-a11y/team-agent-poc/commit/dfeb95fbf96cf6a2bb75a3ba75fac3bc92ed60fc); 등록 내용·사용자 추가 규칙·사내 checkout SHA 직접 대조는 미실행 |
| 조회 경로 보완 | Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | 부분 적용 당시 C04·P02 정상·임베딩 오류 재발 없음 보고; 이번 전체 Prompt에도 포함해 저장 안내 | [실환경 결과](../evals/scenarios.md#결과-기록), [당시 소스 검토](../evals/confluence-offline.md#knowledge-routing) | 부분 추가 안내 원본 [28f526a](https://github.com/knadalkim-a11y/team-agent-poc/blob/28f526a39162e54f126f577554f8c15fdd5940f1/agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로); 현재 전체 지침 안내 원본은 위 행. 부분 적용 당시 성공을 이번 개정 후 재평가로 간주하지 않음 |
| 일반 답변·후속 조회 지침 | 카드/화면 필터/질문 버튼 전제를 제거하고 일반 문장·표·원문 Markdown 링크로 답변. Confluence 본문·Jira/GitHub 실제 ID·페이지 범위는 유지 | 2026-09-07 전체 Prompt 저장·업데이트와 당시 GitHub/Jira 후속 흐름 정상 보고는 보존. 이후 변경된 프롬프트의 WebUI 반영 완료를 사용자 보고로 확인함. 실제 등록 내용·새 모델 출력은 직접 대조하지 않음 | [이번 변경](../evals/scenarios.md#prototype-rich-ui-removal), [이전 전체 지침 저장 보고](../evals/scenarios.md#rich-ui-prompt-saved) | [현재 Prompt 원본](../agent-pack/system-prompts/ees-integrated-assistant.md)과 실제 등록본의 직접 대조·적용 SHA는 미확인. 변경 프롬프트 반영 완료 보고와 별개로, 이전 전달·저장 안내 원본은 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md); 실제 등록 내용·사용자 추가 지침 직접 대조 미실행 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.6. JSON 검색·본문/오류 반환, HTML 카드·예제 제거. 검색 400과 비검색 오류·본문 텍스트 추출·개인 인증 유지 | 2026-09-09 EES 수정본에서 평소 Confluence 조회 정상 보고. 마지막 코드 저장 보고는 2026-09-07 v0.1.4이며 v0.1.6 일반 출력·검색 400 안내의 사내 반영은 미확인. 기존 연결·권한·확인한 비밀 비노출·쓰기 차단·PAT 교체 근거는 보존 | [이번 일반 출력 전환](../evals/scenarios.md#prototype-rich-ui-removal), [검색 오류 사외 검증](../evals/confluence-offline.md#search-error-guidance), [버튼 부재 보고](../evals/scenarios.md#body-query-buttons-observed), [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.3 사외 검증](../evals/confluence-offline.md#rich-ui-results), [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 마지막 v0.1.4 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/confluence-read/scripts/confluence_tool.py). 기존 Skill은 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md) 유지. 등록 코드·사내 checkout 직접 대조 미실행; 이전 v0.1.2 적용 근거는 실환경 기록에 보존 |
| 초기 Rich UI 참고 예제 | 합성 검색 결과 HTML을 사용자 요청에 따라 제거. 새 UI는 업무별 후속 설계 | 기존 대화에 남은 카드·사용자 데이터는 보존하며 예제를 새 배포 대상으로 두지 않음 | [이번 제거](../evals/scenarios.md#prototype-rich-ui-removal), [과거 사전 준비 검증](../evals/confluence-offline.md#status-history) | 해당 없음 |
| Jira 읽기 | Python Tool v0.1.6. JSON 집계·목록·본문/오류 반환. 차트·카드·필터·질문 버튼 제거, 함수·API·페이지 이동·개인 설정 유지 | 2026-09-09 EES 수정본에서 평소 Jira 조회 정상 보고. 마지막 코드 저장 보고는 2026-09-07 v0.1.5이며 v0.1.6 일반 출력의 사내 반영은 미확인. 이전 이슈 본문·원문/조회·저장 근거는 보존 | [이번 일반 출력 전환](../evals/scenarios.md#prototype-rich-ui-removal), [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [이슈 본문 흐름 확인](../evals/scenarios.md#jira-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.4 사외 검증](../evals/jira-offline.md#mvp-usability), [v0.1.3 사외 검증](../evals/jira-offline.md#followup-actions), [저장 보고](../evals/scenarios.md#followup-tools-saved), [v0.1.2 사외 검증](../evals/jira-offline.md#merge-review-fixes), [기존 v0.1.1 기본 흐름](../evals/scenarios.md#jira-dashboard-acceptance), [J01~J05](../evals/scenarios.md#jira-live) | 마지막 v0.1.5 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/jira-read/scripts/jira_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| GitHub PR 읽기 | Python Tool v0.1.4. JSON 목록·본문/오류 반환. 카드·다음 목록 질문 버튼 제거, API·페이지 이동·개인 설정 유지 | 2026-09-09 EES 수정본에서 평소 GitHub 조회 정상 보고. 마지막 코드 저장 보고는 2026-09-07 v0.1.3이며 v0.1.4 일반 출력의 사내 반영은 미확인. 이전 PR 본문·원문/조회·저장 근거는 보존 | [이번 일반 출력 전환](../evals/scenarios.md#prototype-rich-ui-removal), [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [새 카드 흐름 확인](../evals/scenarios.md#github-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [저장 보고](../evals/scenarios.md#followup-tools-saved), [기존 기본 흐름](../evals/scenarios.md#github-read-acceptance), [DB 저장 증거](../evals/scenarios.md#github-storage-check), [사외 검증](../evals/github-offline.md), [GH01~GH04](../evals/scenarios.md#github-live) | 마지막 v0.1.3 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/github-read/scripts/github_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |
| Windows 수락 오류 선택 기동 | [Selector 실행 파일](../scripts/serve_openwebui_windows.py)·읽기 전용 사전검사·복구 안내. 기존 SQLite·단일 worker 범위 | 선택 실행 파일 미적용. 기존 기동으로 `/health` true, 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구 보고; 수락 오류 재발 방지는 미확인 | [소스·합성 검사](../evals/scenarios.md#windows-accept-preparation); 실제 Windows 동작과 구분 | Git 준비본만 반영. 사내 적용 원본 없음; 기존 기동 스크립트·명령을 자동 교체하지 않음 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

과거 ees.1 프로그램 ZIP·설치본은 보존하되 이번 EES Portal 적용에는 ees.2가 포함된 새 ZIP을 사용합니다. Upgrade는 검증된 프로그램 artifact를 선택하며 성공 결과의 래퍼 커밋과 프로그램 커밋을 따로 표시합니다. 기존 설치본의 Start/Restore는 계속 지원하고 Agent Pack 전용 ZIP은 프로그램 ZIP을 대체하지 않습니다. **번들에 포함된 Prompt·Skill·Tool의 API 자동 동기화는 이번 범위에서 제외**하며 기존 UI 등록 항목을 계속 사용합니다.

## 남아 있는 검증과 제한

- 새로고침 뒤에만 답변이 보이던 현상과 origin 거부 보고 후, CORS 영구 저장·현재 창 적용 안내에 이어 **스트리밍이 되고 정상인 것 같다는 사용자 보고**를 받음([기록](../evals/scenarios.md#chat-live-update-observation)). 현재 일반 채팅의 실시간 표시 복구로 인정함. 정확한 허용 목록·User 저장 출력·오류 로그 소멸·PC 재부팅 뒤 유지·장기 안정성은 직접 대조하지 않았으며 Windows 수락 오류의 원인/재발 방지나 새 카드 성공으로 확대하지 않음.

- Windows 수락 오류 이후 접속 불가를 보고했으나 원래 PowerShell에서 Ctrl+C 후 기존 폴더·명령으로 재시작해 `/health` true를 확인했다고 보고함([증거](../evals/scenarios.md#windows-existing-restart)). 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구를 보고했지만 listener 종료 경로·수락 오류 근본 원인·재발 여부는 미확인. GitHub/Jira 후속 카드 흐름 정상 보고는 각각 별도 근거로 기록함. 당시 전달된 런타임 경로는 Python 3.11이었으며 이후 후보 준비 로그의 3.11.16 보고는 [환경 기준](../versions.md#open-webui-대상-환경)에 구분함. 원래 설치 전체·실제 Uvicorn 버전의 직접 대조는 미실행. 선택 실행 파일은 미적용이며 기존 성공 기록과 오류 기록을 보존함.

- GitHub의 [이전 카드·본문 흐름](../evals/scenarios.md#github-rich-ui-acceptance)과 2026-09-09 평소 조회 정상 보고는 해당 범위의 근거로 보존함. 변경 프롬프트 반영 완료 보고는 반영함. v0.1.4 등록 코드·새 조회 출력/원문의 개별 대조는 미확인. 기존 카드의 좁은 화면/키보드 조작은 제거 작업의 남은 게이트가 아니며, 실제 API 페이지 이동·오류/빈 결과·사용자 격리·비밀 보호의 미확인은 해당 사용/공개 시점에 확인함. 이미 확인한 인증·DB 저장을 반복하지 않으며 CI/리뷰·diff·일반 이슈·쓰기는 후속 수요로 유지함.

- Jira의 [이전 이슈 본문 흐름](../evals/scenarios.md#jira-rich-ui-acceptance)과 2026-09-09 평소 조회 정상 보고는 보존함. 변경 프롬프트 반영 완료 보고는 반영함. v0.1.6 등록 코드·새 조회 출력/원문의 개별 대조는 미확인. 초기 카드 디자인 튜닝·빈 필터 복구·좁은 화면/키보드 검사를 이번 제거 작업의 게이트로 유지하지 않음. 실제 조회 범위·페이지 이동·부분 실패·권한/계정 격리·비밀 보호의 미확인은 해당 사용/공개 시점에 확인하며, 이전 인증/DB 저장·재시작·전체 건수 대조를 반복하지 않음. 사외 브라우저 URL 정책 차단과 이전 기본 흐름은 당시 기록으로 유지함.
- 개정 지침은 UI 저장 보고가 있고 P02 PASS, P03 창작 거절 부분 확인 상태. 나머지는 평가표의 시점에 따라 기능 확인·공개 전 묶음·진단으로 수행하며 미확인을 PASS로 바꾸지 않음. POC-POL-001 v0.1은 합성 Knowledge이고 공통 정책 관리 원본 v0.2와 다름.
- Confluence의 이전 v0.1.4 코드 저장·본문 질문 버튼 부재·전체 Prompt 저장과 2026-09-09 평소 조회 정상 보고는 보존함. v0.1.6 일반 출력·검색 오류 안내의 사내 반영과 새 답변 확인은 미완료. 검색 범위/시각·실제 본문과 답변 근거·C07의 개별 HTTP 400/401/403/timeout·confluence-read Skill 실제 로딩은 일반적인 조회 정상 보고만으로 통과 처리하지 않음. 과거 임베딩 오류 재발 없음 보고는 의미 검색 자체 복구와 구분하며 운영 장애·토큰 폐기를 불필요하게 반복하지 않음.
- 기존 W/D/S/Confluence PASS는 해당 환경·구성·합성 자료와 사용자 보고 범위임. 현재 PC의 팀원 로그인 화면 접속은 확인했으며 전송 보호·I01~I05 사용자 격리·실제 비개발자 사용/공유는 미완료. 같은 저장 경로의 완료 증거는 재사용하며, 다른 서버로 옮길 때 그 환경의 저장/권한을 확인함.
- 초기 EES의 Memory·Chat History·위험 실행 기능 OFF는 유지하며 개인 전역 Memory ON과 구분함. 운영 DB 직접 연결·자격증명·범용 SQL·Shell·쓰기는 제공하지 않음. S06은 승인 DB 조회 중계 기능을 도입할 때만 실행함.
- 현재 GLM 5.2를 기준으로 작은 Tool 스키마·짧은 절차·일반 JSON 결과를 사용함. GLM 5.3 등 모델 교체 시 대표 대화·조회·실패/금지 요청을 비교하고, 영향 없는 저장·토큰 시험을 자동 반복하지 않음.
- 기존 Hermes 환경은 보존. 별도 Tool Server·Router·A2A·자동 동기화·개인화·WebUI 코어 수정·공통 UI 프레임워크는 실제 필요가 확인될 때 검토함. 팀원 작성물은 WebUI, 담당자가 채택한 공통 배포 자산은 Git이라는 [관리 경계](../README.md#원본과-배포본)를 유지함.

## 사내 전달과 유지할 환경

- 범용 Assistant에 필요한 기능을 늘리는 방향을 유지합니다. 화면·답변은 가독성과 유연성을 우선하고 **이모지를 사용하지 않습니다**. 초기 조회 결과 Rich UI 제거 작업과 변경 프롬프트의 WebUI 반영을 완료했다고 보고받았습니다. 이후 화면은 업무별로 하나씩 설계하며 관리자 공지·그룹 세분화·서비스화·서버 이전은 별도 후속 범위입니다.
- 사내 PC에서는 ChatGPT에 접근할 수 없어 외부 모바일로 코드·명령을 옮기거나 Git을 사용함. `%USERPROFILE%\team-agent-poc` 최초 clone은 성공 보고가 있으므로 반복하지 않음. GitHub.com HTTPS용 사용자 전역 Git 프록시 설정 안내 후 2026-09-08 사용자가 설정 완료를 보고함. 설정 원문은 미수집이며 이후 Update는 저장된 Git 설정을 사용해 `-GitProxy`를 생략할 수 있음. WebUI/Confluence의 네트워크 설정 변경이나 모든 사내 호스트의 프록시 필요 여부가 확인된 것으로 해석하지 않음.
- 2026-09-08 사용자 설명에 따라 **화이트리스트에 등록된 웹사이트만 접근 가능한 환경**을 전제로 함. 실제 허용 목록·차단 로그는 미수집이며 모델 파일·추가 다운로드 호스트·업데이트 확인까지 접근 가능하다고 가정하지 않음. 필요한 외부 호출과 기존 로컬 캐시 사용을 구분하고 승인되지 않은 우회·임의 허용 범위 확대는 하지 않음.
- 현재 Windows PC의 데이터·키·계정은 유지하며 프로그램 운영에는 등록된 `manage-ees.ps1` 경로를 사용함. 실제 Python·작업 위치·DATA_DIR·주소와 기동 로그/백업의 위치는 [기존 등록 설정](03-openwebui-native-agent.md#ees-local-state)을 따름. `start-openwebui.ps1`의 loopback·기본 폴더는 설치 예제이며, 이 예제로 현재 등록값을 덮어쓰거나 되돌리지 않음. 접속 허용 정책은 사내 관리 시스템을 따르고 서비스화·다른 서버/데이터 이전은 후속 범위임.
- 웹 프로젝트 지침은 2026-09-06 README의 짧은 저장소 참조 문구로 교체했다고 보고받음. 재입력을 요구하지 않으며 저장소 지침 변경이 웹 설정 자체를 수정한 것으로 기록하지 않음.

## 최근 점검

2026-09-10: 사용자 보고로 EES Portal 이름 표시를 확인하고 복구 실행 대기 상태를 화면 확인 단계로 갱신함. 개별 명령 성공·실제 적용 SHA·패널 v0.1.3·접근 거부 원인 해소는 미확인으로 유지함. 기존 복구 안내를 날짜가 있는 과거 절차로 표시해 반복 실행을 방지하고, 문서 구조·링크와 diff를 점검함. 실행 코드·설정·테스트·사내 환경은 변경하지 않음. [확인 범위](../evals/scenarios.md#ees-portal-upgrade-apply-failure).

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때 갱신합니다. 최근 점검은 이번 요약만 두고 날짜별 증거는 기존 evals에서 연결합니다. Git 게시·WebUI 적용·실환경 통과를 각각 구분합니다.
