# 현재 작업 상태

갱신일: 2026-09-07

계획·다음 작업·적용 원본을 관리합니다. 시험 판정은 [평가표](../evals/scenarios.md), 환경은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 목표와 이번 작업

- 목표: 비개발자가 범용 채팅·사내 자료 조회·팀원 Prompt/Skill 공유를 쉽게 사용하는 플랫폼. 현재는 Open WebUI Native와 Git Agent Pack을 사용하고 원본 WebUI는 수정하지 않음.
- 현재 위치: 기존 연동의 후속 조회 흐름을 보완하는 단계. **첫 화면·온보딩 적용은 보류**하고 범용 Assistant 방향을 유지함. 기존 Skill·Tool·모델 Public 설정 보고와 그룹 운영 후속 결정은 그대로임. 사용자가 Rich UI 디자인이 아직 어설프다고 평가해 시각 디자인 튜닝은 기능 흐름을 마무리한 뒤 한 번에 진행하기로 함. 업무를 막는 조작·가독성 오류는 발견 시 보완함.
- 이번 작업: **유지보수를 고려해 GitHub v0.1.2 PR 목록·본문 카드와 Confluence v0.1.3 검색·본문·근거 카드를 준비함.** 기존 조회 결과를 재사용하고 본문 접기·수동 질문 초안·오류/빈 결과 구분을 적용함. UI 템플릿은 모델 근거에서 분리하고 중복 표 출력 지침을 정리했으며 추가 API·모델 호출·프런트 의존성·서버는 없음. Jira v0.1.4 준비본도 유지함. 사용자는 기존 폴더·기존 명령으로 재시작한 뒤 `/health`에 true가 표시된다고 보고함. 당시에는 서버 응답 회복만 확인했고 오류 원인·재발 여부·모델/새 카드 동작은 미확인으로 남김. 이후 준비본의 Jira v0.1.4·GitHub v0.1.2·Confluence v0.1.3 도구 3개 저장 완료를 보고함. 이어 같은 원본의 전체 System Prompt를 2,500자 이내 3블록으로 전달했고 저장 및 업데이트 완료를 보고함. 이후 새 대화의 짧은 질문도 멈춰 보이며 새로고침 뒤에는 답변이 나타난다는 보고가 있어 실시간 표시 문제를 진단함. origin 거부 확인과 CORS 영구 저장 안내 뒤 스트리밍이 되고 정상인 것 같다는 보고를 받아 현재 일반 채팅의 표시 복구를 인정함. 이후 GitHub 목록 카드·본문 질문 입력·수동 전송 뒤 본문/원문이 정상이라는 사용자 보고를 받음. 이어 Jira 이슈 본문 질문 입력·수동 전송 뒤 본문/원문도 정상 확인 보고를 받음. Confluence 새 카드 흐름은 확인 대기이며 앞선 저장 보고는 당시 버전의 증거로 보존함.
- 다음 작업 하나: **Confluence v0.1.3 검색 카드 → 문서 한 건의 본문 조회 질문 입력 → 수동 전송 → 본문 요약·원문 흐름을 확인한다.** [GitHub 카드](../evals/scenarios.md#github-rich-ui-acceptance)와 [Jira 이슈 본문](../evals/scenarios.md#jira-rich-ui-acceptance)은 사용자 보고 범위에서 정상 확인함. 기존 등록·개인 설정·전체 Prompt로 [Confluence 카드 흐름](04-confluence-read-tool.md#rich-ui-results)을 이어감. 일반 채팅·GitHub/Jira 완료 흐름·health·인증/저장/20회 검사는 반복하지 않음. Rich UI 디자인 튜닝과 첫 화면·온보딩·Selector 적용은 현재 작업에 포함하지 않음.

<a id="resume-branch"></a>

## 최신 main에서 재개

**다음 개발은 원격 최신 main을 기준으로 시작합니다.** PR #5 → #4 → #3 → #2 순서로 통합했고, main 통합 병합 커밋은 [3184b78](https://github.com/knadalkim-a11y/team-agent-poc/commit/3184b78ccb3d4d8a4977055693cb6d58728caa01)입니다. 현재 상태와 재개 기준도 main에서 관리합니다. 이전 PR 브랜치를 최신 작업 대상으로 고정하지 않습니다.

재개 시 최신 main 커밋의 AGENTS·이 문서를 읽고 그때 관련 열린 PR이 있는지만 확인합니다. 관련 후속 수정은 기존 PR에서 마무리하며 새 PR을 미병합 PR 위에 계속 쌓지 않습니다. 이전 PR별 원본·병합 결과는 [통합 기록](../evals/scenarios.md#pr-stack-review)에 보존합니다. 아래 사내 수동 적용 원본은 Git 최신 main과 구분합니다.

<a id="delivery-plan"></a>

## 실행 계획

| 순서 | 작업 묶음 | 완료 판단·진행 조건 |
|---|---|---|
| 1. 기반 활용 | 기존 범용 채팅·Confluence 검색/본문/근거 링크 사용 | 확인한 W·D·Confluence 증거를 재사용하되 환경·변경 영향이 다른 범위는 구분. 세부 정책 문답 전체 완료를 다음 기능의 선행조건으로 두지 않음 |
| 2. Jira + 첫 Rich UI | 프로젝트별 전체/미완료 비교 → 받은 최근 목록의 필터·펼치기 → 원문 | [v0.1.1 기본 흐름 확인 보고](../evals/scenarios.md#jira-dashboard-acceptance). 전체 시스템 표시·대표 시스템 건수 대조·화면 조작 확인. 개별 상세 API·권한/공개 전 조건은 평가표에 남기며 다음 기능 개발의 전수 선행조건으로 두지 않음 |
| 3. GitHub 읽기 | GHES 3.17.15 개인 PAT로 허용 저장소 한 곳의 PR 목록 → 본문 → 원문 | [기본 흐름 확인 완료](../evals/scenarios.md#github-read-acceptance) — 개인 환경의 목록·PR 한 건 본문 요약·원문 일치 보고. 계정/공개 전 조건은 별도이며 완료한 흐름을 반복하지 않음 |
| 4. 기능 안정화·소규모 사용 — 현재 | 기존 연동의 실제 요청 처리·후속 조회·실패 안내에서 드러난 문제를 보완 | 완료한 기능 검증을 재사용하고 영향받는 조건만 확인. [남은 권한·격리 조건](../evals/scenarios.md#validation-timing)은 실제 확인 범위만 판정. 첫 화면·온보딩 구성은 기능과 사용 범위가 안정된 뒤 검토 |
| 5. 수요 기반 확장 | EMS/APC/FDC의 승인 API가 있는 업무 하나, 필요한 역할별 기능·Rich UI | 업무 가치와 접근 경계를 먼저 정하고 작은 읽기 기능부터 추가. 쓰기·자동화·다중 Agent는 별도 필요가 확인될 때 검토 |

첫 공용 파일럿의 기본 업무 범위는 **범용 채팅 + Confluence + 준비된 Jira/첫 Rich UI**입니다. GitHub는 개인 환경의 기본 흐름을 확인한 추가 업무이며, 현재는 기존 Tool·Skill·모델 전체를 Public으로 바꿨다는 사용자 보고가 있습니다. 이 설정 변경을 GitHub를 포함한 모든 연동의 일반 사용자 조회·격리 검증 완료로 간주하지 않습니다. GitHub·EMS/APC/FDC 전체 연동이나 Hermes 도입을 MVP 완료 조건으로 두지 않습니다. 파일럿에서 비개발자가 실제 업무 흐름을 완료하고 결과·오류·공유를 이해하는 것까지가 첫 배포의 목표입니다.

이 업무 목록은 현재 연결 기능이며 Assistant의 고정 역할이나 최종 기능 목록이 아닙니다. 범용 대화와 필요에 따른 기능 확장을 유지하고, 소개·예시·온보딩은 실제로 자주 쓰이는 업무가 드러난 뒤 다듬습니다. 안정화는 기능 전체를 동결하거나 평가표를 처음부터 반복하는 단계가 아닙니다.

기능별 업무 흐름을 구현·검증 단위로 유지하며, 사용자가 승인한 기존 연동의 카드 보완은 함께 준비해 사내 반영을 묶습니다. 제품 확인 → 작은 읽기 기능·필요한 화면 → GPT의 코드/합성 검사 → 사내의 짧은 확인 묶음 → 결과 반영 순서로 진행합니다. 단계별 실제 권한·배포 승인을 대신하는 계획은 아닙니다. 구체 등록/화면 경계는 [Native 가이드](03-openwebui-native-agent.md#rich-ui), 시험 시점은 [평가표](../evals/scenarios.md#validation-timing)에만 관리합니다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| 첫 사용 안내 — 보류 | 소개·질문 JSON 4개·팀원 안내 참고 초안 | 사용자 결정으로 UI 적용·팀원 배포 보류. 적용 성공 보고 없음 | [준비 기록](../evals/scenarios.md#team-first-use-preparation), [보류 결정](../evals/scenarios.md#onboarding-deferred) | 보관한 [초안](../agent-pack/ees-prompt-suggestions.json); 배포 원본 SHA 미확인 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 2026-09-07 두 지침 UI 저장 보고; 개정 후 P02 PASS, P03 창작 거절 부분 확인, P04~P10 미완료; 실행 시점은 평가표 | [P02~P10 재검증](../evals/scenarios.md#instruction-revision), [기존 지침 갱신](03-openwebui-native-agent.md#update-existing-instructions) | 전달·저장 안내 원본 [dfeb95f](https://github.com/knadalkim-a11y/team-agent-poc/commit/dfeb95fbf96cf6a2bb75a3ba75fac3bc92ed60fc); 등록 내용·사용자 추가 규칙·사내 checkout SHA 직접 대조는 미실행 |
| 조회 경로 보완 | Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | 부분 적용 당시 C04·P02 정상·임베딩 오류 재발 없음 보고; 이번 전체 Prompt에도 포함해 저장 안내 | [실환경 결과](../evals/scenarios.md#결과-기록), [당시 소스 검토](../evals/confluence-offline.md#knowledge-routing) | 부분 추가 안내 원본 [28f526a](https://github.com/knadalkim-a11y/team-agent-poc/blob/28f526a39162e54f126f577554f8c15fdd5940f1/agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로); 현재 전체 지침 안내 원본은 위 행. 부분 적용 당시 성공을 이번 개정 후 재평가로 간주하지 않음 |
| 카드·후속 조회 지침 | 카드/답변 중복 억제, Confluence 본문 조회, Jira/GitHub의 실제 ID·후속 범위 지침 | 2026-09-07 전체 System Prompt 3블록 전달 후 저장 및 업데이트 완료 보고. 일반 채팅 스트리밍과 GitHub/Jira 본문 후속 흐름 정상 보고; Confluence 새 흐름은 미확인 | [전체 지침 저장 보고](../evals/scenarios.md#rich-ui-prompt-saved) | [7c8a65b의 전체 Prompt](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md); 실제 등록 내용·사용자 추가 지침 직접 대조는 미실행 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.3; 기존 HTTP 허용 유지, 검색/본문/근거 카드·정확한 검색 범위·질문 초안 추가 | 2026-09-07 v0.1.3 코드 저장 완료 보고; 전체 Prompt 저장 보고가 있으며 새 카드 동작은 미확인. 앞선 v0.1.2의 연결·조회·문서 권한·확인한 출력의 PAT 비노출·시험한 구성의 쓰기 차단·PAT 폐기와 교체 후 복구 확인 보고. 오류 처리 등 공용 사용 전체 검증은 미완료 | [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.3 사외 검증](../evals/confluence-offline.md#rich-ui-results), [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 코드 안내 원본 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/skills/confluence-read/scripts/confluence_tool.py). 기존 Skill은 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md) 유지. 등록 코드·사내 checkout 직접 대조 미실행; 이전 v0.1.2 적용 근거는 실환경 기록에 보존 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | [사전 준비 검증](../evals/confluence-offline.md#status-history); 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| Jira 읽기·Rich UI | Python Tool v0.1.4·Jira 후속 조회 지침. 입력 초안 버튼에 원문·빈 필터 복구·오류 설명 연결 보완; HTTP·개인 설정은 기존과 같음 | 2026-09-07 v0.1.4 코드 저장 완료 보고. 전체 Prompt 저장 뒤 이슈의 본문 질문 입력·수동 전송·본문 요약/원문 정상 보고. 디자인 완성도 개선은 후속으로 둠. 앞선 v0.1.2 코드·당시 Jira 절 저장 보고를 보존 | [이슈 본문 흐름 확인](../evals/scenarios.md#jira-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [v0.1.4 사외 검증](../evals/jira-offline.md#mvp-usability), [v0.1.3 사외 검증](../evals/jira-offline.md#followup-actions), [저장 보고](../evals/scenarios.md#followup-tools-saved), [v0.1.2 사외 검증](../evals/jira-offline.md#merge-review-fixes), [기존 v0.1.1 기본 흐름](../evals/scenarios.md#jira-dashboard-acceptance), [J01~J05](../evals/scenarios.md#jira-live) | 코드 안내 원본 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/skills/jira-read/scripts/jira_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| GitHub PR 읽기 | Python Tool v0.1.2·GitHub/공통 카드 지침. PR 목록/본문/오류 카드·정확한 번호/다음 페이지 질문 초안 추가; 개인 설정·조회 경로는 기존과 같음 | 2026-09-07 v0.1.2 코드 저장 완료 보고. 전체 Prompt 저장 뒤 목록 카드·본문 질문 입력·수동 전송·본문/원문 정상 보고. 앞선 v0.1.1 코드·당시 GitHub 절 저장 보고를 보존 | [새 카드 흐름 확인](../evals/scenarios.md#github-rich-ui-acceptance), [도구 3개 저장 보고](../evals/scenarios.md#rich-ui-tools-saved), [저장 보고](../evals/scenarios.md#followup-tools-saved), [기존 기본 흐름](../evals/scenarios.md#github-read-acceptance), [DB 저장 증거](../evals/scenarios.md#github-storage-check), [사외 검증](../evals/github-offline.md), [GH01~GH04](../evals/scenarios.md#github-live) | 코드 안내 원본 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/skills/github-read/scripts/github_tool.py). 전체 Prompt 안내 원본도 [7c8a65b](https://github.com/knadalkim-a11y/team-agent-poc/blob/7c8a65b0e2eed6d22109b8770e97b9e6908ad68a/agent-pack/system-prompts/ees-integrated-assistant.md). 등록 코드·사내 checkout 직접 대조 미실행; 앞선 적용 근거는 위 기존 기록에 보존 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |
| Windows 수락 오류 선택 기동 | [Selector 실행 파일](../scripts/serve_openwebui_windows.py)·읽기 전용 사전검사·복구 안내. 기존 SQLite·단일 worker 범위 | 선택 실행 파일 미적용. 기존 기동으로 `/health` true, 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구 보고; 수락 오류 재발 방지는 미확인 | [소스·합성 검사](../evals/scenarios.md#windows-accept-preparation); 실제 Windows 동작과 구분 | Git 준비본만 반영. 사내 적용 원본 없음; 기존 기동 스크립트·명령을 자동 교체하지 않음 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

## 남아 있는 검증과 제한

- 새로고침 뒤에만 답변이 보이던 현상과 origin 거부 보고 후, CORS 영구 저장·현재 창 적용 안내에 이어 **스트리밍이 되고 정상인 것 같다는 사용자 보고**를 받음([기록](../evals/scenarios.md#chat-live-update-observation)). 현재 일반 채팅의 실시간 표시 복구로 인정함. 정확한 허용 목록·User 저장 출력·오류 로그 소멸·PC 재부팅 뒤 유지·장기 안정성은 직접 대조하지 않았으며 Windows 수락 오류의 원인/재발 방지나 새 카드 성공으로 확대하지 않음.

- Windows 수락 오류 이후 접속 불가를 보고했으나 원래 PowerShell에서 Ctrl+C 후 기존 폴더·명령으로 재시작해 `/health` true를 확인했다고 보고함([증거](../evals/scenarios.md#windows-existing-restart)). 이후 CORS 안내 뒤 일반 채팅 스트리밍 복구를 보고했지만 listener 종료 경로·수락 오류 근본 원인·재발 여부는 미확인. GitHub/Jira 후속 카드 흐름 정상 보고는 각각 별도 근거로 기록함. 전달된 런타임 경로는 Python 3.11이며 패치 버전·실제 Uvicorn 버전은 미대조. 선택 실행 파일은 미적용이며 기존 성공 기록과 오류 기록을 보존함.

- GitHub v0.1.2의 목록 카드·PR 한 건의 본문 질문 입력·수동 전송 뒤 본문 요약/원문 일치는 [사용자 보고로 확인](../evals/scenarios.md#github-rich-ui-acceptance)함. 실제 코드/화면·호출 이력의 직접 대조는 없으며 다음 페이지·본문 뒤 목록 이어가기·오류/빈 결과·전체 목록 정확성·사용자 격리·마스킹·좁은 화면/키보드 조작은 이번 보고에 포함되지 않음. 확인한 흐름·인증·DB 저장은 반복하지 않고 남은 조건은 해당 사용/공개 시점에 확인함. CI/리뷰·diff·일반 이슈·쓰기는 후속 수요로 유지함.

- Jira v0.1.4 코드·전체 Prompt 저장 뒤 이슈 한 건의 본문 질문 입력·수동 전송·본문 요약/원문 일치를 [사용자 보고로 확인](../evals/scenarios.md#jira-rich-ui-acceptance)함. 선택 시스템 새 조회·다음 페이지·빈 필터 복구·부분 실패 안내·대표 권한 차단·계정 격리·전체 출력 비밀 비노출·좁은 화면/키보드는 이번 보고에 포함되지 않음. 사외 브라우저의 기존 URL 정책 차단 기록과 이전 v0.1.1 기본 흐름은 보존함. 디자인은 아직 어설프다는 사용자 의견을 반영해 후속 튜닝으로 두며 완료한 이슈 흐름·인증/DB 저장·재시작·전체 건수 대조를 반복하지 않음.
- 개정 지침은 UI 저장 보고가 있고 P02 PASS, P03 창작 거절 부분 확인 상태. 나머지는 평가표의 시점에 따라 기능 확인·공개 전 묶음·진단으로 수행하며 미확인을 PASS로 바꾸지 않음. POC-POL-001 v0.1은 합성 Knowledge이고 공통 정책 관리 원본 v0.2와 다름.
- Confluence v0.1.3 코드와 전체 Prompt는 저장 완료 보고가 있으며 카드/검색 범위/시각/질문 초안의 실제 표시·모델 근거 일치는 미확인. C07의 개별 HTTP 401·403·timeout 분기, confluence-read Skill의 실제 로딩은 미확인. 과거 임베딩 검색 오류는 조회 경로 보완 후 재발 없음 보고가 있으나 의미 검색 자체를 복구한 것은 아님. 운영 장애나 토큰 폐기를 불필요하게 반복하지 않음.
- 기존 W/D/S/Confluence PASS는 해당 환경·구성·합성 자료와 사용자 보고 범위임. 현재 PC의 팀원 로그인 화면 접속은 확인했으며 전송 보호·I01~I05 사용자 격리·실제 비개발자 사용/공유는 미완료. 같은 저장 경로의 완료 증거는 재사용하며, 다른 서버로 옮길 때 그 환경의 저장/권한을 확인함.
- 초기 EES의 Memory·Chat History·위험 실행 기능 OFF는 유지하며 개인 전역 Memory ON과 구분함. 운영 DB 직접 연결·자격증명·범용 SQL·Shell·쓰기는 제공하지 않음. S06은 승인 DB 조회 중계 기능을 도입할 때만 실행함.
- 현재 GLM 5.2를 기준으로 작은 Tool 스키마·짧은 절차·고정 UI 템플릿을 사용함. GLM 5.3 등 모델 교체 시 대표 대화·조회·실패/금지 요청을 비교하고, 영향 없는 저장·토큰 시험을 자동 반복하지 않음.
- 기존 Hermes 환경은 보존. 별도 Tool Server·Router·A2A·자동 동기화·개인화·WebUI 코어 수정·공통 UI 프레임워크는 실제 필요가 확인될 때 검토함. 팀원 작성물은 WebUI, 담당자가 채택한 공통 배포 자산은 Git이라는 [관리 경계](../README.md#원본과-배포본)를 유지함.

## 사내 전달과 유지할 환경

- 범용 Assistant에 필요한 기능을 늘리는 방향을 유지합니다. 화면·답변은 사용자 친화적인 가독성과 유연성을 우선하고 **이모지를 사용하지 않습니다**. 소개·예시·온보딩 초안 적용, 그룹 세분화, 서비스화·서버 이전은 현재 선행 작업으로 되돌리지 않습니다.
- 사내 PC에서는 ChatGPT에 접근할 수 없어 외부 모바일로 코드·명령을 옮기거나 Git을 사용함. `%USERPROFILE%\team-agent-poc` 최초 clone은 성공 보고가 있으므로 반복하지 않음. 새 PowerShell에서는 사내 `$gitProxy` 값을 다시 설정하고 `git -c "http.proxy=$gitProxy" ...`를 사용함. 영구 프록시나 WebUI/Confluence 네트워크 설정은 임의 변경하지 않음.
- 현재 Windows PC의 데이터·키·계정·명령 복사 실행을 유지함. 기존 `start-openwebui.ps1`는 loopback 기준이며 이번 파일럿 때문에 자동 변경하지 않음. 앱 수신 주소는 기존 실행 환경에서 조정하고 접속 허용 정책은 사내 관리 시스템을 따름. 서비스화·다른 서버 이전·데이터 이전은 후속 필요가 생길 때 범위를 정함.
- 웹 프로젝트 지침은 2026-09-06 README의 짧은 저장소 참조 문구로 교체했다고 보고받음. 재입력을 요구하지 않으며 저장소 지침 변경이 웹 설정 자체를 수정한 것으로 기록하지 않음.

## 최근 점검

[Jira 이슈 본문 흐름 정상 보고와 디자인 튜닝 후속 결정](../evals/scenarios.md#jira-rich-ui-acceptance)을 기록하고 다음 작업을 Confluence 검색→본문 흐름으로 전환함. 질문 입력·본문 요약·원문 정상 보고를 인정하되 페이지/오류/계정 격리·디자인 만족도는 별도로 구분함. 상태·평가·Jira 안내와 결정 이력만 갱신하고 문서·diff를 검사함. 앱 코드·CSS·설정·사내 서버 변경과 독립 검토·완료 검사 반복은 수행하지 않음.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때 갱신합니다. 최근 점검은 이번 요약만 두고 날짜별 증거는 기존 evals에서 연결합니다. Git 게시·WebUI 적용·실환경 통과를 각각 구분합니다.
