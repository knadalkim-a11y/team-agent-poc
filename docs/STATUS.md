# 현재 작업 상태

갱신일: 2026-09-08

계획·다음 작업·적용 원본을 관리합니다. 시험 판정은 [평가표](../evals/scenarios.md), 환경은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 목표와 이번 작업

- 목표: [여섯 가지 프로젝트 목표](../README.md#프로젝트-목표)에 따라 쉬운 Chat UI·문서 시스템·관리자 공통 정책·관리자 워크플로·레거시 연동·레거시 간접 UI를 제공함. 범용 Assistant·팀원 Prompt/Skill 공유를 유지하고 Open WebUI Native와 Git Agent Pack을 우선 활용함.
- 현재 위치: 사용자가 여섯 목표의 본격 구현 전에 **팀원 시연용 커스터마이징과 수정·배포 방식 준비**를 우선 요청함. 이전 첫 화면/소개·예시·짧은 안내 보류는 이 범위에서 해제하고, 조회 결과 Rich UI 전체 디자인 튜닝은 후속으로 유지함. EES 전용 공통 정책·관리자 워크플로·레거시 목표는 유지함.
- 이번 작업: **사내 Update 뒤 `head=c5f1690...`, idle·original·관리 프로세스 생존을 사용자 보고로 확인함.** 전달한 Status 순서의 current_commit·last_failure는 null, rollback_available은 false임. 축약 SHA 접두어가 안내 원본과 일치하며 사내 전체 checkout/설정 직접 대조는 미실행. [갱신·상태 확인 보고](../evals/scenarios.md#ees-retransition-ready). 진단 운영 코드 갱신은 사용자 보고 범위로 인정하고 EES 프로그램 전환·최초 실패 원인 확정은 아직 미완료임. [재개 절차](03-openwebui-native-agent.md#ees-resume-prepared-release), [준비 후보](../evals/scenarios.md#ees-prepare-completed).
- 다음 작업 하나: **준비된 프로그램 원본 `4a8779bbf3ee078abe8c94ff75b59fa3bb7aad50`으로 Deploy 한 번의 결과와 최소 화면 확인을 받는다.** 같은 운영 창에서 `-HealthTimeout 600`을 전달하며 기본값/등록 환경은 유지함. 기존 관리 경로가 종료·백업·기동을 담당하고 재다운로드·Prepare·Init·별도 수동 Stop은 붙이지 않음. 실패 시 재실행 전에 Operation stopped/Diagnostics로 실제 실패와 복구 상태를 확인함. 이 명령의 사내 실행 결과는 아직 없음.

진단 코드는 [manage_ees.py](../scripts/manage_ees.py)·[ees_deploy_process.py](../scripts/ees_deploy_process.py), 관련 시험은 [전환 시험](../tests/test_manage_ees.py)·[프로세스 시험](../tests/test_ees_deploy_process.py)입니다. [진단 필드와 해석](03-openwebui-native-agent.md#ees-deployment-diagnostics)을 따르며, 마지막 실패 기록은 이후 성공과 구분해 보존합니다. 새 진단은 과거 실패 원인을 복원하거나 사내 적용을 대신하지 않습니다.

진단 보완 코드 원본은 `1ac1c33cf50cb3135f63c7ed8ac5ccaf22cdab30`이며 [Windows/Linux CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34184761238) 성공을 확인했습니다. PR #7의 main 병합과 사내 `c5f1690...` Update/Status 실행은 사용자 보고로 확인했으며 전체 SHA·등록 내용 직접 대조는 미실행입니다. 프로그램 후보 ZIP 원본 및 EES 전환 성공 여부와 구분합니다.

<a id="resume-branch"></a>

## 최신 main에서 재개

**다음 개발은 원격 최신 main을 기준으로 시작합니다.** PR #5 → #4 → #3 → #2의 [통합 커밋 3184b78](https://github.com/knadalkim-a11y/team-agent-poc/commit/3184b78ccb3d4d8a4977055693cb6d58728caa01)과 이후 [PR #6의 프로그램 원본 4a8779b](../evals/scenarios.md#ees-program-deployment)는 과거 병합/배포물 이력입니다. 이를 최신 개발 head로 고정하지 않으며 재개 시 원격 main을 확인합니다.

재개 시 최신 main 커밋의 AGENTS·이 문서를 읽고 그때 관련 열린 PR이 있는지만 확인합니다. 관련 후속 수정은 기존 PR에서 마무리하며 새 PR을 미병합 PR 위에 계속 쌓지 않습니다. 이전 PR별 원본·병합 결과는 [통합 기록](../evals/scenarios.md#pr-stack-review)에 보존합니다. 아래 사내 수동 적용 원본은 Git 최신 main과 구분합니다.

<a id="delivery-plan"></a>

## 실행 계획

| 목표 | 현재 근거와 남은 범위 | 다음 구현 단위 |
|---|---|---|
| 1. 쉬운 Chat UI | 대화·스트리밍 기본 사용 확인. 비개발자의 도움 없는 실제 사용 전체는 미확인 | 팀 시연용 이름·소개·빠른 제안·짧은 안내와 배포 단위를 먼저 준비. 조회 카드 전체 디자인 튜닝은 후속 |
| 2. 문서 시스템 연동 | Confluence 검색·본문의 기존 확인과 GitHub PR·Jira 이슈 읽기 흐름을 재사용. 새 Confluence 자연어 본문/원문 흐름은 미확인 | 실제 업무에서 필요한 조회·후속 해석을 보완하며 완료한 흐름을 반복하지 않음 |
| 3. 관리자 공통 정책 | EES Assistant에 합성 공통 지침·정책 답변 Skill 저장 보고. 실제 사내 정책 적용은 미완료 | EES 전용 공통 원칙·상세 절차·권한/Tool 제한의 배치와 관리자 변경 반영을 정리 |
| 4. 관리자 워크플로 | Skill의 절차 지침과 Native 호출 기능은 사용 중. 관리자가 단계·분기·검사를 제어하는 업무 워크플로는 설계 전 | 기존 문서/조회 기능으로 대표 업무 하나를 정하고 입력·단계·분기·완료 조건을 정의. 필요한 제어 수준에 맞춰 구현 수단 선택 |
| 5. 레거시 시스템 연동 | EMS/APC/FDC의 실제 업무 기능은 미연결 | 승인된 API 또는 Query Broker로 가치가 있는 읽기 기능 하나 연결. 기존 서비스 권한·업무 규칙 활용 |
| 6. 레거시 간접 UI | 기존 조회 카드 경험은 있지만 레거시 업무에 연결된 간접 UI는 미구현 | 5번의 같은 업무에 필요한 조건 입력·결과 선택·필터·비교를 묶어 사용 흐름 완성 |

**개발 순서:** 1·2의 기존 기반으로 팀 시연용 커스터마이징·배포 방식 준비 → 3의 EES 전용 공통 정책 → 4의 대표 워크플로 하나 → 5·6의 레거시 업무 하나를 함께 연결. 4번은 단순 절차 지침과 실행 코드로 보장할 단계를 구분하며, 복잡한 오케스트레이터부터 도입하지 않음. [구현 수단 선택](03-openwebui-native-agent.md#managed-policy-workflow)과 [남은 권한·격리 조건](../evals/scenarios.md#validation-timing)을 따름.

현재 첫 공용 파일럿에 준비한 업무 기반은 **범용 채팅 + Confluence + Jira/첫 Rich UI**입니다. 여기에 EES 공통 정책과 대표 워크플로를 적용하는 방향으로 확장합니다. GitHub는 개인 환경의 기본 흐름을 확인한 추가 업무이며, 현재는 기존 Tool·Skill·모델 전체를 Public으로 바꿨다는 사용자 보고가 있습니다. 이 설정 변경을 GitHub를 포함한 모든 연동의 일반 사용자 조회·격리 검증 완료로 간주하지 않습니다. GitHub·EMS/APC/FDC 전체 연동이나 Hermes 도입을 MVP 완료 조건으로 두지 않습니다. 파일럿에서 비개발자가 실제 업무 흐름을 완료하고 결과·오류·공유를 이해하는 것까지가 첫 배포의 목표입니다.

이 업무 목록은 현재 연결 기능이며 Assistant의 고정 역할이나 최종 기능 목록이 아닙니다. 범용 대화와 필요에 따른 기능 확장을 유지하고, 팀 시연용 소개·예시를 먼저 적용 준비한 뒤 실제로 자주 쓰이는 업무에 맞춰 다듬습니다. 안정화는 기능 전체를 동결하거나 평가표를 처음부터 반복하는 단계가 아닙니다.

기능별 업무 흐름을 구현·검증 단위로 유지하며, 사용자가 승인한 기존 연동의 카드 보완은 함께 준비해 사내 반영을 묶습니다. 제품 확인 → 작은 읽기 기능·필요한 화면 → GPT의 코드/합성 검사 → 사내의 짧은 확인 묶음 → 결과 반영 순서로 진행합니다. 단계별 실제 권한·배포 승인을 대신하는 계획은 아닙니다. 구체 등록/화면 경계는 [Native 가이드](03-openwebui-native-agent.md#rich-ui), 시험 시점은 [평가표](../evals/scenarios.md#validation-timing)에만 관리합니다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| 팀 시연용 이름·소개·시작 질문 | 기존 모델 이름·소개·프로필 적용 안내, 제안 JSON 4개·짧은 팀원 안내 | 사용자 요청으로 준비 재개. 실제 UI 저장·로고 교체·팀원 전달은 미확인 | [시연 준비](../evals/scenarios.md#team-demo-customization), [이전 준비](../evals/scenarios.md#team-first-use-preparation), [당시 보류](../evals/scenarios.md#onboarding-deferred) | 현재 [제안 JSON](../agent-pack/ees-prompt-suggestions.json); 사내 적용 원본 없음 |
| EES 프로그램·전달 도구 | 이름·아이콘 wheel/ZIP/Actions와 Windows 배포 명령; 기동 대기·첫 antlr4 캐시 복구 명령 | 후보 prepared=true·server_changed=false·0.11.3+ees.1 보고 후 첫 Deploy/자동 복구 실패. 최종 기존 Start·UI 접속 정상 보고로 original 복구. EES 전환 미완료·최초 실패 원인 미확정 | [운영 명령](03-openwebui-native-agent.md#기존-windows-서버에-적용), [준비 성공](../evals/scenarios.md#ees-prepare-completed), [최종 복구](../evals/scenarios.md#ees-original-recovered), [프로그램 CI](../evals/scenarios.md#ees-program-deployment) | 프로그램 원본 `4a8779bbf3ee078abe8c94ff75b59fa3bb7aad50`, 내부 ZIP `EES-demo-4a8779bbf3ee.zip`. 운영 코드의 [캐시 복구 추가 원본 15cd88b](https://github.com/knadalkim-a11y/team-agent-poc/commit/15cd88b5a99142c07c4d8cca4dcdd957354d48cb)와 구분. 사내 checkout 전체 SHA 직접 대조 미실행 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 2026-09-07 두 지침 UI 저장 보고; 개정 후 P02 PASS, P03 창작 거절 부분 확인, P04~P10 미완료; 실행 시점은 평가표 | [P02~P10 재검증](../evals/scenarios.md#instruction-revision), [기존 지침 갱신](03-openwebui-native-agent.md#update-existing-instructions) | 전달·저장 안내 원본 [dfeb95f](https://github.com/knadalkim-a11y/team-agent-poc/commit/dfeb95fbf96cf6a2bb75a3ba75fac3bc92ed60fc); 등록 내용·사용자 추가 규칙·사내 checkout SHA 직접 대조는 미실행 |
| 조회 경로 보완 | Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | 부분 적용 당시 C04·P02 정상·임베딩 오류 재발 없음 보고; 이번 전체 Prompt에도 포함해 저장 안내 | [실환경 결과](../evals/scenarios.md#결과-기록), [당시 소스 검토](../evals/confluence-offline.md#knowledge-routing) | 부분 추가 안내 원본 [28f526a](https://github.com/knadalkim-a11y/team-agent-poc/blob/28f526a39162e54f126f577554f8c15fdd5940f1/agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로); 현재 전체 지침 안내 원본은 위 행. 부분 적용 당시 성공을 이번 개정 후 재평가로 간주하지 않음 |
| 카드·후속 조회 지침 | 카드/답변 중복 억제, Confluence 본문 조회, Jira/GitHub의 실제 ID·후속 범위 지침 | 2026-09-07 전체 System Prompt 3블록 전달 후 저장 및 업데이트 완료 보고. 일반 채팅 스트리밍과 GitHub/Jira 이전 본문 후속 흐름 정상 보고; 이번 버튼 제거에는 같은 전체 Prompt 유지, Confluence 새 흐름은 미확인 | [전체 지침 저장 보고](../evals/scenarios.md#rich-ui-prompt-saved) | [7c8a65b의 전체 Prompt](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md); 실제 등록 내용·사용자 추가 지침 직접 대조는 미실행 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.5; 검색 400의 검색어 변경 안내·비검색 400 구분. 기존 카드·본문 질문 버튼 제거 유지 | 2026-09-07 v0.1.4 코드 저장 및 이후 본문 질문 버튼 부재 보고; 자연어 본문/원문 흐름은 미확인. v0.1.5 오류 안내는 미적용. 전체 Prompt 저장 보고 유지. 앞선 v0.1.2의 연결·조회·문서 권한·확인한 출력의 PAT 비노출·시험한 구성의 쓰기 차단·PAT 폐기와 교체 후 복구 확인 보고. 오류 처리 등 공용 사용 전체 검증은 미완료 | [검색 오류 사외 검증](../evals/confluence-offline.md#search-error-guidance), [버튼 부재 보고](../evals/scenarios.md#body-query-buttons-observed), [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.3 사외 검증](../evals/confluence-offline.md#rich-ui-results), [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 이번 v0.1.4 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/confluence-read/scripts/confluence_tool.py). 기존 Skill은 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md) 유지. 등록 코드·사내 checkout 직접 대조 미실행; 이전 v0.1.2 적용 근거는 실환경 기록에 보존 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | [사전 준비 검증](../evals/confluence-offline.md#status-history); 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| Jira 읽기·Rich UI | Python Tool v0.1.5. 이슈별 본문 질문 버튼 제거, 원문·필터·시스템/다음 목록 질문 유지; HTTP·개인 설정은 기존과 같음 | 2026-09-07 v0.1.5 코드 교체·저장 완료 보고; 새 출력은 미확인. 2026-09-07 이전 v0.1.4 코드 저장 완료 보고. 전체 Prompt 저장 뒤 이슈의 본문 질문 입력·수동 전송·본문 요약/원문 정상 보고. 디자인 완성도 개선은 후속으로 둠. 앞선 v0.1.2 코드·당시 Jira 절 저장 보고를 보존 | [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [이슈 본문 흐름 확인](../evals/scenarios.md#jira-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.4 사외 검증](../evals/jira-offline.md#mvp-usability), [v0.1.3 사외 검증](../evals/jira-offline.md#followup-actions), [저장 보고](../evals/scenarios.md#followup-tools-saved), [v0.1.2 사외 검증](../evals/jira-offline.md#merge-review-fixes), [기존 v0.1.1 기본 흐름](../evals/scenarios.md#jira-dashboard-acceptance), [J01~J05](../evals/scenarios.md#jira-live) | 이번 v0.1.5 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/jira-read/scripts/jira_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| GitHub PR 읽기 | Python Tool v0.1.3. PR별 본문 질문 버튼 제거, 목록/본문/오류 카드와 다음 목록 질문 유지; 개인 설정·조회 경로는 기존과 같음 | 2026-09-07 v0.1.3 코드 교체·저장 완료 보고; 새 출력은 미확인. 2026-09-07 이전 v0.1.2 코드 저장 완료 보고. 전체 Prompt 저장 뒤 목록 카드·본문 질문 입력·수동 전송·본문/원문 정상 보고. 앞선 v0.1.1 코드·당시 GitHub 절 저장 보고를 보존 | [버튼 제거본 저장 보고](../evals/scenarios.md#body-query-buttons-saved), [버튼 제거 검수](../evals/scenarios.md#body-query-buttons-removed), [새 카드 흐름 확인](../evals/scenarios.md#github-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [저장 보고](../evals/scenarios.md#followup-tools-saved), [기존 기본 흐름](../evals/scenarios.md#github-read-acceptance), [DB 저장 증거](../evals/scenarios.md#github-storage-check), [사외 검증](../evals/github-offline.md), [GH01~GH04](../evals/scenarios.md#github-live) | 이번 v0.1.3 저장 안내 원본 [a778e5d](https://github.com/knadalkim-a11y/team-agent-poc/blob/a778e5d41d9213c58dc997a6acdd5603c4df1251/agent-pack/skills/github-read/scripts/github_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |
| Windows 수락 오류 선택 기동 | [Selector 실행 파일](../scripts/serve_openwebui_windows.py)·읽기 전용 사전검사·복구 안내. 기존 SQLite·단일 worker 범위 | 선택 실행 파일 미적용. 기존 기동으로 `/health` true, 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구 보고; 수락 오류 재발 방지는 미확인 | [소스·합성 검사](../evals/scenarios.md#windows-accept-preparation); 실제 Windows 동작과 구분 | Git 준비본만 반영. 사내 적용 원본 없음; 기존 기동 스크립트·명령을 자동 교체하지 않음 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

프로그램 후보는 이미 준비한 위 ZIP을 유지하며 현재 장애 정리를 이유로 다시 다운로드·Prepare하지 않습니다. 운영 스크립트는 최신 main에서 개발하되, `15cd88b`의 CI 산출물은 Agent Pack 전용이므로 프로그램 ZIP을 대체하지 않습니다. **번들에 포함된 Prompt·Skill·Tool의 API 자동 동기화는 미구현**이며 기존 UI 등록 항목을 계속 사용합니다.

## 남아 있는 검증과 제한

- 새로고침 뒤에만 답변이 보이던 현상과 origin 거부 보고 후, CORS 영구 저장·현재 창 적용 안내에 이어 **스트리밍이 되고 정상인 것 같다는 사용자 보고**를 받음([기록](../evals/scenarios.md#chat-live-update-observation)). 현재 일반 채팅의 실시간 표시 복구로 인정함. 정확한 허용 목록·User 저장 출력·오류 로그 소멸·PC 재부팅 뒤 유지·장기 안정성은 직접 대조하지 않았으며 Windows 수락 오류의 원인/재발 방지나 새 카드 성공으로 확대하지 않음.

- Windows 수락 오류 이후 접속 불가를 보고했으나 원래 PowerShell에서 Ctrl+C 후 기존 폴더·명령으로 재시작해 `/health` true를 확인했다고 보고함([증거](../evals/scenarios.md#windows-existing-restart)). 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구를 보고했지만 listener 종료 경로·수락 오류 근본 원인·재발 여부는 미확인. GitHub/Jira 후속 카드 흐름 정상 보고는 각각 별도 근거로 기록함. 당시 전달된 런타임 경로는 Python 3.11이었으며 이후 후보 준비 로그의 3.11.16 보고는 [환경 기준](../versions.md#open-webui-대상-환경)에 구분함. 원래 설치 전체·실제 Uvicorn 버전의 직접 대조는 미실행. 선택 실행 파일은 미적용이며 기존 성공 기록과 오류 기록을 보존함.

- GitHub v0.1.2의 목록 카드·PR 한 건의 본문 질문 입력·수동 전송 뒤 본문 요약/원문 일치는 [사용자 보고로 확인](../evals/scenarios.md#github-rich-ui-acceptance)함. 실제 코드/화면·호출 이력의 직접 대조는 없으며 다음 페이지·본문 뒤 목록 이어가기·오류/빈 결과·전체 목록 정확성·사용자 격리·마스킹·좁은 화면/키보드 조작은 이번 보고에 포함되지 않음. 확인한 흐름·인증·DB 저장은 반복하지 않고 남은 조건은 해당 사용/공개 시점에 확인함. CI/리뷰·diff·일반 이슈·쓰기는 후속 수요로 유지함. 이번 v0.1.3 버튼 제거본의 코드 저장은 사용자 보고로 확인했으며 새 출력은 미확인.

- Jira v0.1.4 코드·전체 Prompt 저장 뒤 이슈 한 건의 본문 질문 입력·수동 전송·본문 요약/원문 일치를 [사용자 보고로 확인](../evals/scenarios.md#jira-rich-ui-acceptance)함. 선택 시스템 새 조회·다음 페이지·빈 필터 복구·부분 실패 안내·대표 권한 차단·계정 격리·전체 출력 비밀 비노출·좁은 화면/키보드는 이번 보고에 포함되지 않음. 사외 브라우저의 기존 URL 정책 차단 기록과 이전 v0.1.1 기본 흐름은 보존함. 디자인은 아직 어설프다는 사용자 의견을 반영해 후속 튜닝으로 두며 완료한 이슈 흐름·인증/DB 저장·재시작·전체 건수 대조를 반복하지 않음. 이번 v0.1.5 버튼 제거본의 코드 저장은 사용자 보고로 확인했으며 새 출력은 미확인.
- 개정 지침은 UI 저장 보고가 있고 P02 PASS, P03 창작 거절 부분 확인 상태. 나머지는 평가표의 시점에 따라 기능 확인·공개 전 묶음·진단으로 수행하며 미확인을 PASS로 바꾸지 않음. POC-POL-001 v0.1은 합성 Knowledge이고 공통 정책 관리 원본 v0.2와 다름.
- Confluence v0.1.4 코드 저장·본문 질문 버튼 부재와 기존 전체 Prompt 저장은 사용자 보고로 확인함. 검색 범위/시각·자연어 본문 조회와 모델 근거 일치는 미확인. v0.1.5 검색 오류 안내는 사외 준비만 완료했으며 사내 반영·실제 HTTP 400 응답은 미확인. C07의 개별 HTTP 401·403·timeout 분기, confluence-read Skill의 실제 로딩은 미확인. 과거 임베딩 검색 오류는 조회 경로 보완 후 재발 없음 보고가 있으나 의미 검색 자체를 복구한 것은 아님. 운영 장애나 토큰 폐기를 불필요하게 반복하지 않음.
- 기존 W/D/S/Confluence PASS는 해당 환경·구성·합성 자료와 사용자 보고 범위임. 현재 PC의 팀원 로그인 화면 접속은 확인했으며 전송 보호·I01~I05 사용자 격리·실제 비개발자 사용/공유는 미완료. 같은 저장 경로의 완료 증거는 재사용하며, 다른 서버로 옮길 때 그 환경의 저장/권한을 확인함.
- 초기 EES의 Memory·Chat History·위험 실행 기능 OFF는 유지하며 개인 전역 Memory ON과 구분함. 운영 DB 직접 연결·자격증명·범용 SQL·Shell·쓰기는 제공하지 않음. S06은 승인 DB 조회 중계 기능을 도입할 때만 실행함.
- 현재 GLM 5.2를 기준으로 작은 Tool 스키마·짧은 절차·고정 UI 템플릿을 사용함. GLM 5.3 등 모델 교체 시 대표 대화·조회·실패/금지 요청을 비교하고, 영향 없는 저장·토큰 시험을 자동 반복하지 않음.
- 기존 Hermes 환경은 보존. 별도 Tool Server·Router·A2A·자동 동기화·개인화·WebUI 코어 수정·공통 UI 프레임워크는 실제 필요가 확인될 때 검토함. 팀원 작성물은 WebUI, 담당자가 채택한 공통 배포 자산은 Git이라는 [관리 경계](../README.md#원본과-배포본)를 유지함.

## 사내 전달과 유지할 환경

- 범용 Assistant에 필요한 기능을 늘리는 방향을 유지합니다. 화면·답변은 사용자 친화적인 가독성과 유연성을 우선하고 **이모지를 사용하지 않습니다**. 소개·예시·짧은 시작 안내는 팀 시연용으로 준비합니다. 그룹 세분화·서비스화·서버 이전과 조회 카드 전체 재디자인은 이번 준비에 포함하지 않습니다.
- 사내 PC에서는 ChatGPT에 접근할 수 없어 외부 모바일로 코드·명령을 옮기거나 Git을 사용함. `%USERPROFILE%\team-agent-poc` 최초 clone은 성공 보고가 있으므로 반복하지 않음. 새 PowerShell에서는 사내 `$gitProxy` 값을 다시 설정하고 `git -c "http.proxy=$gitProxy" ...`를 사용함. 영구 프록시나 WebUI/Confluence 네트워크 설정은 임의 변경하지 않음.
- 현재 Windows PC의 데이터·키·계정은 유지하며 프로그램 운영에는 등록된 `manage-ees.ps1` 경로를 사용함. 실제 Python·작업 위치·DATA_DIR·주소와 기동 로그/백업의 위치는 [기존 등록 설정](03-openwebui-native-agent.md#ees-local-state)을 따름. `start-openwebui.ps1`의 loopback·기본 폴더는 설치 예제이며, 이 예제로 현재 등록값을 덮어쓰거나 되돌리지 않음. 접속 허용 정책은 사내 관리 시스템을 따르고 서비스화·다른 서버/데이터 이전은 후속 범위임.
- 웹 프로젝트 지침은 2026-09-06 README의 짧은 저장소 참조 문구로 교체했다고 보고받음. 재입력을 요구하지 않으며 저장소 지침 변경이 웹 설정 자체를 수정한 것으로 기록하지 않음.

## 최근 점검

최신 main `c5f1690`·열린 PR 없음·로컬 무변경을 확인하고 같은 커밋의 지침/상태가 직전 안내 원본과 동일함을 대조함. 사용자 보고의 여섯 상태값을 실제 Status 필드 순서에 매핑하고, 이후 Deploy가 기존 후보를 검증한 뒤 관리 프로세스 종료/백업/기동을 수행함을 확인함. [결과·다음 명령 근거](../evals/scenarios.md#ees-retransition-ready). STATUS·기존 평가 기록만 갱신하며 코드 시험/CI·독립 검토·사내 health/데이터/연동 검증은 반복하지 않음.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때 갱신합니다. 최근 점검은 이번 요약만 두고 날짜별 증거는 기존 evals에서 연결합니다. Git 게시·WebUI 적용·실환경 통과를 각각 구분합니다.
