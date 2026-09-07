# 현재 작업 상태

갱신일: 2026-09-07

계획·다음 작업·적용 원본을 관리합니다. 시험 판정은 [평가표](../evals/scenarios.md), 환경은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 목표와 이번 작업

- 목표: 비개발자가 범용 채팅·사내 자료 조회·팀원 Prompt/Skill 공유를 쉽게 사용하는 플랫폼. 현재는 Open WebUI Native와 Git Agent Pack을 사용하고 원본 WebUI는 수정하지 않음.
- 현재 위치: 사용자가 기능 안정화 전에 현재 업무로 소개·예시를 고정하는 것은 이르다고 지적함. **첫 화면·온보딩 적용은 보류**하고 범용 Assistant에 필요한 기능을 추가하는 방향을 유지함. 기존 Skill·Tool·모델 Public 설정 보고와 그룹 운영 후속 결정은 그대로임.
- 이번 작업: 새 대화에서 이어갈 작업 브랜치·결정·다음 범위를 정리함. [첫 화면 초안 보류](../evals/scenarios.md#onboarding-deferred)를 유지하고 이번 세션에서 새 기능 안정화 작업이나 사내 UI 변경을 시작하지 않음. 과거 증거와 미확인 조건은 유지함.
- 다음 작업 하나: **기존 연동의 자연어 요청 → 기능 선택 → 후속 조회·오류 안내 흐름에서 보완할 부분을 검토한다.** 현재 코드·준비 지침·확인된 배포 상태의 차이와 실제 불편을 기준으로 한 건씩 보완함. 미확인을 오류로 단정하거나 완료한 인증/저장/조회·20회 안정성 검사를 다시 시작하지 않음. 첫 화면 적용·그룹 재설정은 선행조건이 아님.

<a id="resume-branch"></a>

## 새 대화에서 이어갈 브랜치

2026-09-07 세션 정리 시 `main`은 `9dcdbf60a98124506140b0dca315d50223cfa0ed`이며 아래 PR들은 열려 있는 draft·미병합 상태입니다. **현재 이어갈 대상은 [PR #4](https://github.com/knadalkim-a11y/team-agent-poc/pull/4)의 최신 head**, 브랜치는 `codex/windows-local-pilot-20260907`입니다. main만 읽고 Jira 구현부터 다시 시작하지 않습니다.

| PR | 내용 | 기준 브랜치 |
|---|---|---|
| [#2](https://github.com/knadalkim-a11y/team-agent-poc/pull/2) | Jira 읽기·대시보드와 확인 기록 | main |
| [#3](https://github.com/knadalkim-a11y/team-agent-poc/pull/3) | GitHub PR 읽기와 확인 기록 | PR #2의 브랜치 |
| [#4](https://github.com/knadalkim-a11y/team-agent-poc/pull/4) | 현재 PC 팀 사용·공유 설정·온보딩 보류·현재 계획 | PR #3의 브랜치 |

재개할 때 원격 main·관련 PR 상태를 다시 확인하고 PR #4 최신 `AGENTS.md`와 이 문서를 읽은 뒤 해당 기능 파일만 봅니다. 이후 병합됐다면 실제 반영 상태에 맞춰 기준을 갱신합니다. Git의 준비 원본과 아래 표의 사내 수동 적용 원본을 혼동하지 않습니다. 새 대화용 별도 인계 문서나 프로젝트 지침 재입력은 필요하지 않습니다.

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

한 번에 구현할 업무 흐름은 하나로 유지합니다. 제품 확인 → 작은 읽기 기능·필요한 화면 → GPT의 코드/합성 검사 → 사내의 짧은 확인 묶음 → 결과 반영 순서로 진행합니다. 단계별 실제 권한·배포 승인을 대신하는 계획은 아닙니다. 구체 등록/화면 경계는 [Native 가이드](03-openwebui-native-agent.md#rich-ui), 시험 시점은 [평가표](../evals/scenarios.md#validation-timing)에만 관리합니다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| 첫 사용 안내 — 보류 | 소개·질문 JSON 4개·팀원 안내 참고 초안 | 사용자 결정으로 UI 적용·팀원 배포 보류. 적용 성공 보고 없음 | [준비 기록](../evals/scenarios.md#team-first-use-preparation), [보류 결정](../evals/scenarios.md#onboarding-deferred) | PR #4의 [초안](../agent-pack/ees-prompt-suggestions.json); 배포 원본 SHA 미확인 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 2026-09-07 두 지침 UI 저장 보고; 개정 후 P02 PASS, P03 창작 거절 부분 확인, P04~P10 미완료; 실행 시점은 평가표 | [P02~P10 재검증](../evals/scenarios.md#instruction-revision), [기존 지침 갱신](03-openwebui-native-agent.md#update-existing-instructions) | 전달·저장 안내 원본 [dfeb95f](https://github.com/knadalkim-a11y/team-agent-poc/commit/dfeb95fbf96cf6a2bb75a3ba75fac3bc92ed60fc); 등록 내용·사용자 추가 규칙·사내 checkout SHA 직접 대조는 미실행 |
| 조회 경로 보완 | Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | 부분 적용 당시 C04·P02 정상·임베딩 오류 재발 없음 보고; 이번 전체 Prompt에도 포함해 저장 안내 | [실환경 결과](../evals/scenarios.md#결과-기록), [당시 소스 검토](../evals/confluence-offline.md#knowledge-routing) | 부분 추가 안내 원본 [28f526a](https://github.com/knadalkim-a11y/team-agent-poc/blob/28f526a39162e54f126f577554f8c15fdd5940f1/agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로); 현재 전체 지침 안내 원본은 위 행. 부분 적용 당시 성공을 이번 개정 후 재평가로 간주하지 않음 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.2; HTTP 명시적 허용 | 2026-09-07 연결·조회·문서 권한·확인한 출력의 PAT 비노출·시험한 구성의 쓰기 차단·PAT 폐기와 교체 후 복구 확인 보고. 오류 처리 등 공용 사용 전체 검증은 미완료 | [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 새 Tool 안내 원본 [910ad765](https://github.com/knadalkim-a11y/team-agent-poc/blob/910ad765a777df1caf30a565a197097f8afbf8b0/agent-pack/skills/confluence-read/scripts/confluence_tool.py), 기존 Skill 안내 원본 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md). C06에서 등록 코드가 전달한 원본과 같다는 사용자 확인; GPT의 등록 코드·사내 checkout SHA 직접 대조는 미실행 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | [사전 준비 검증](../evals/confluence-offline.md#status-history); 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| Jira 읽기·Rich UI | 기본 비활성 Python Tool v0.1.1, 코드 안의 개편 화면, 기존 Prompt의 조건부 Jira 안내. 추가 Skill 없음 | 2026-09-07 v0.1.1 적용·전체 시스템 표시·대표 시스템 건수 대조·화면 조작 정상 보고. Jira Prompt 절의 별도 UI 반영은 미안내 | [사외 변경 검증](../evals/jira-offline.md#dashboard-design), [실환경 보고](../evals/scenarios.md#jira-dashboard-acceptance), [J01~J05](../evals/scenarios.md#jira-live) | 적용 안내 원본 [a6b6f2e의 Tool](https://github.com/knadalkim-a11y/team-agent-poc/blob/a6b6f2e911525519e8cc56be92d889caa1ab8845/agent-pack/skills/jira-read/scripts/jira_tool.py). 사용자 보고 기준이며 사내 등록 코드·checkout 직접 대조는 미실행. 이전 ce982de5 등록과 d24b47d 저장 검사 증거는 [첫 화면 기록](../evals/scenarios.md#jira-first-dashboard)에 보존 |
| GitHub PR 읽기 | 기본 비활성 Python Tool v0.1.0, 조건부 Prompt·기존 채팅 표, --github 개인 필드 검사 | 2026-09-07 새 개인 필드 DB 범위 PASS 후 목록·PR 한 건 본문 요약·원문 링크 정상 보고. Prompt 절 UI 저장은 별도 미확인 | [기본 흐름 확인](../evals/scenarios.md#github-read-acceptance), [저장 증거](../evals/scenarios.md#github-storage-check), [사외 검증](../evals/github-offline.md), [GH01~GH04](../evals/scenarios.md#github-live) | 안내 원본 [4b058996의 Tool](https://github.com/knadalkim-a11y/team-agent-poc/blob/4b058996d1e3f360ee670da553e2f9bc7a9046a1/agent-pack/skills/github-read/scripts/github_tool.py) 및 [검사기](https://github.com/knadalkim-a11y/team-agent-poc/blob/4b058996d1e3f360ee670da553e2f9bc7a9046a1/scripts/check_confluence_canary.py). 사용자 보고 기준이며 등록 코드·checkout 직접 대조는 미실행. Jira PR #2 기반 별도 GitHub PR #3, main 미병합 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

## 남아 있는 검증과 제한

- GitHub의 새 개인 필드 DB 저장과 목록·PR 한 건 본문·원문 기본 흐름은 사용자 보고 범위에서 확인함. 전체 목록 정확성/페이지 처리·사용자 격리·마스킹 화면의 별도 관찰·Prompt 절 UI 저장은 미확인. PAT 종류/전체 권한은 확인하지 않았고 실제 사내 주소·저장소 식별자·업무 내용은 기록하지 않음. CI/리뷰·diff·일반 이슈·쓰기·추가 Rich UI는 후속 수요로 남김.

- Jira는 개인 환경의 기본 조회·화면 흐름을 사용자 보고로 확인함. 개별 상세 API/본문 정확성·대표 권한 차단·계정 격리·실제 출력 비밀 비노출·부분 실패와 모델 근거 대조는 평가표의 관련 시점에 남김. 전체 시스템의 모든 건수를 대조한 것으로 확대하지 않음. 완료한 인증·DB 저장·재시작·화면 흐름을 반복하지 않음.
- 개정 지침은 UI 저장 보고가 있고 P02 PASS, P03 창작 거절 부분 확인 상태. 나머지는 평가표의 시점에 따라 기능 확인·공개 전 묶음·진단으로 수행하며 미확인을 PASS로 바꾸지 않음. POC-POL-001 v0.1은 합성 Knowledge이고 공통 정책 관리 원본 v0.2와 다름.
- Confluence C07의 개별 HTTP 401·403·timeout 분기, confluence-read Skill의 실제 로딩은 미확인. 과거 임베딩 검색 오류는 조회 경로 보완 후 재발 없음 보고가 있으나 의미 검색 자체를 복구한 것은 아님. 운영 장애나 토큰 폐기를 불필요하게 반복하지 않음.
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

[새 대화 재개 기준 정리](../evals/scenarios.md#session-continuation): 원격 main과 열린 PR #2/#3/#4의 상태·기준 브랜치를 확인하고 현재 재개 대상을 명시함. 보류 결정·실환경 보고 범위·완료한 검증 재사용을 유지하고 문서·링크·diff만 확인함. 코드·JSON·기존 시험·사내 설정 변경이나 PR 병합은 수행하지 않음.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때 갱신합니다. 최근 점검은 이번 요약만 두고 날짜별 증거는 기존 evals에서 연결합니다. Git 게시·WebUI 적용·실환경 통과를 각각 구분합니다.
