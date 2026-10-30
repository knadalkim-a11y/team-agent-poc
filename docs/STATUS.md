# 현재 작업 상태

## 2026-10-30 · PR #110 병합 요청 · 새 터미널 실행 정책 중단

- **현재:** 사용자가 배포 문서 [PR #110](https://github.com/knadalkim-a11y/team-agent-poc/pull/110)의 병합도 요청했다. 문서·실패 기록을 보완하고 최종 CI 확인 후 병합한다. 제품 코드는 바꾸지 않는다.
- **현장 보고:** 재부팅 뒤 새 PowerShell 창에서 첫 `Status`가 `UnauthorizedAccess`로 차단됐다. 이번 시도의 Update·Upgrade·Stop·프로그램 교체는 미실행이며 Restore는 불필요하다. 현재 실행 정책 값·재시도·새 프로그램 적용 성공은 아직 미확인이고, 마지막 성공 보고는42f5ae5다. [원인 판단과 재발 방지](../evals/v4-ui-20260930.md#powershell-preflight-20261030).
- **다음 하나:** PR #110 병합 뒤 정확한 새 main에서 프로그램 포함 CI/ZIP을 검증하고 새 고정 적용 블록을 같은 PR 본문에 제공한다. 기존6b1c256 블록은 병합 전 이력으로 보존하며 재실행하지 않는다. [새 터미널 준비](03-openwebui-native-agent.md#ees-new-powershell-window)를 현재 배포 안내에 연결했다.

> 아래는 앞선 배포 준비·구현 당시 기록이다. Draft 유지·다음 작업 문구와 CI 성공은 각 당시 상태이며, 이번 병합이나 사내 적용 성공을 뜻하지 않는다.

## 2026-10-30 · PR #109 병합 · 운영32/작성12 사내 적용 준비

- **병합:** 사용자의 “병합하고, 사내배포 스크립트까지 복붙가능하게 제공해줘” 요청에 따라 [PR #109](https://github.com/knadalkim-a11y/team-agent-poc/pull/109)를08:50 KST에 main `6b1c256ef44691ffec53cdcd7b65db329e11c4e1`으로 병합했다. 최종 head `3c5ba1d`의 [CI407](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40973385124)은39성공/PR 출하1정상생략이며 미해결 리뷰0이었다. 병합 main과 검증 head의 tree `63bec1690b08c9eb3c6a39196ba95f89fee4d19c`는 같다.
- **배포 준비:** [main CI408](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40975832132)은 첫 실행40/40 성공했다. 새 프로그램 ZIP의 실제 바이트·clean 원본·32포함 파일·wheel RECORD·프런트엔드139입력/5,582출력을 strict 검증하고 [복사 실행·복구 블록](03-openwebui-native-agent.md#main-6b1c256-apply-prep-20261030)을 준비했다. 마지막 사내 보고 `42f5ae502b57be68aefa5d141f09259c8f6e9ee9`에서 기존 Update→Upgrade/명시적 Restore를 사용한다. 기존 관리 스크립트·업무 Python·Work/Confluence 도구 원본은 이 구간에서 바뀌지 않았으며 자료 이관·재등록·의존성 설치는 추가하지 않는다.
- **다음 하나·현장:** 검증된 main ZIP과 복사 실행 블록으로 적용한 결과1줄·읽기 전용 화면/기존 자료 확인1줄을 받는다. 배포 기록 문서는 별도 Draft로 두어 적용 대상 main6b1c256을 유지한다. 이 준비를 사내 적용 성공으로 표시하지 않는다. 아래 Draft·미병합 문구는 작업 당시 이력이다.

## 2026-10-30 · 사유의 파란 바깥선 제거 · PR #109 후속

- **현재:** 사용자 요청에 따라 같은 [PR #109](https://github.com/knadalkim-a11y/team-agent-poc/pull/109)에서 사유의 파란 바깥선을 제거하고 키보드 초점을 회색 안쪽선으로 바꿨다. Figma 운영32와 비교 HTML에도 반영했다. 작성12·현재 검색 목록·B1 제외 결정은 유지한다. [범위](mockups/ees-work/TASK.md#reason-border-20261030).
- **확인:** 정상 source6 빌드·strict 검증, 실제 Native 사유2/2·12포커스 상태·복사4회·읽기 전용 입력 차단2회와 별도 central-chat/helper18단계가 통과했다. Figma 고정 점검 오류0/기존 작성 페이지 크기 경고1을 확인한 뒤 C132를 남겼다. [원본·검증 경계](../evals/v4-ui-20260930.md#reason-border-20261030).
- **첫 CI와 후속:** 이전 head `ed77695`의 [CI406](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40970728929)은 별도 central-chat 시험이 옛 시작 버튼을 바로 클릭해 실패했다. 기존 개요→단계→시작 helper를 호출하도록 시험1줄만 보완했고 동일 source6 실제 gate를 통과했다. 최초 실패는 보존하며 로컬 성공을 새 head 전체 CI 성공으로 대신하지 않는다.
- **다음 하나·적용:** [PR #109 최종 검사](https://github.com/knadalkim-a11y/team-agent-poc/pull/109/checks)와 검토를 확인한다. Draft·미병합이며 사내 배포는 하지 않았다. 마지막 사용자 보고 적용 원본 `42f5ae502b57`은 그대로다.

> 아래는 앞선 구현 당시 기록이며 source5 검증을 source6 전체 재검증으로 해석하지 않는다.

## 2026-10-30 · 운영31·업무절차12 구현·로컬 검증 완료

- **사용자 요청·현재:** #104·#107·#108은 main `6ac4c1062a6c83d2d1429d0120cc5179d5dc508d`에 병합됐다. 두 페이지를 다시 비교한 뒤 받은 구현 요청에 따라 `feat/operations31-authoring12-parity-20261030`에서 [범위·완료 조건](mockups/ees-work/TASK.md#operations31-authoring12-parity-20261030)의 제품 보정과 로컬 검증을 마쳤다. 새 변경은 아직 main에 병합되지 않았다.
- **수정 대상:** 운영31의 개요와 실행 전 단계 조회·판정 사유/근거 배치, 작성12의 도구 미연결/확인 필요 상태를 기존 기능에 연결한다. 비교 HTML8의 B1은 이전 참고 화면이라는 사용자 정정을 반영하며 현재 코드의 목록은 유지한다.
- **검증:** Node404개와 source5 실제 Native6개·시각 단언을 통과했다. 바로 전 source4의 영향 경로는21개 첫 통과와 탐색 보완 후1개 재검증 통과이며, Complete Native22단계도 통과했다. source5는 그 뒤 CSS1파일만 보완했으며 두 빌드의 검증 범위를 [최종 원본·해시·실측](../evals/artifacts/operations31-authoring12-parity-20261030/runtime/final-result.json)에서 구분한다. 실제 도구 설정 수·실패 상태·판정자와 시각을 보존하므로 전체 이미지 픽셀 동일성을 주장하지 않는다.
- **다음 하나:** [이 브랜치의 검토 PR](https://github.com/knadalkim-a11y/team-agent-poc/pulls?q=is%3Apr+head%3Afeat%2Foperations31-authoring12-parity-20261030)의 최종 CI와 병합 전 검토를 확인한다. 로컬 성공을 새 PR head CI나 사내 적용 성공으로 대신하지 않는다.
- **사내 적용:** 이번 구현은 새 사내 배포를 포함하지 않는다. 마지막 사용자 보고 적용 원본 `42f5ae502b57`과 당시 기록을 유지한다.

## 2026-10-30 · PR 통합과 두 Figma 페이지의 제품 UI 재검증

- **사용자 요청·현재:** 열린 PR을 병합한 뒤 Figma ‘업무 · 운영’과 ‘워크 · 업무 절차’가 현재 제품에 시각적으로 반영됐는지 다시 확인한다. [PR #108](https://github.com/knadalkim-a11y/team-agent-poc/pull/108)은 검증된 head `a5af7706708687a61acb6ec2fd0c65c6d34db026`에서 main `b8f6e16f551fb197ef41d799a962420e5dcf10f2`로 병합했다.
- **통합 범위:** 같은 [PR #107](https://github.com/knadalkim-a11y/team-agent-poc/pull/107)에 최신 main과 [PR #104](https://github.com/knadalkim-a11y/team-agent-poc/pull/104)의 사내 적용 기록을 merge로 통합한다. 양쪽 목업·구현·실패·적용 이력을 보존하고 새로운 제품 변경은 추가하지 않는다. 운영29판은 목업이며 병합만으로 제품 구현이 되지 않는다.
- **검증·다음 하나:** 통합 최종 head의 전체 CI와 실제 제품/Figma 대조를 진행한 뒤 병합을 마친다. 최종 CI·병합·시각 비교 결과는 [PR #107 본문과 검사](https://github.com/knadalkim-a11y/team-agent-poc/pull/107/checks)에서 확인한다. 이전 head 성공과 과거 일부 영역의 치수 일치를 두 페이지 전체 일치로 확대하지 않는다.
- **사내 적용:** 이번 통합의 사내 배포는 수행하지 않는다. 마지막 사용자 보고 `42f5ae502b57`의 적용·기동 성공과 사내 화면·자료 보존 미확인은 아래 원래 기록을 유지한다.

> 아래는 각 작업 당시 기록이다. Draft·미병합·다음 작업 문구는 위의 새 병합·재검증 요청 이전 상태로 구분하며 검증·실패 근거를 보존한다.

## 2026-10-29 · 워크.워크플로 Figma 12판 보정 · PR #108

- **현재 작업:** 실제 Figma와 PR 화면의 차이를 보여준 뒤 받은 “동일하게 변경 진행해줘” 요청에 따라, 같은 [PR #108](https://github.com/knadalkim-a11y/team-agent-poc/pull/108)에서 현재 Figma12판에 맞춰 제품 UI를 보정하고 로컬 검증을 마쳤다. 이번 보정의 시각 기준은 [Figma 워크·업무 절차](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1285-1830)이며 [범위·보존·완료 기준](mockups/ees-work/TASK.md#workspace-authoring12-ui-20261029)을 따른다. 기존 HTML12판과 이전 검증 근거는 그대로 보존한다.
- **출발점:** PR #108 head `c4b21685dac37a5278c52d5e118c389441fba127`, 같은 작업 브랜치 `feat/workspace-authoring12-ui-20261029`. main `96467cfc7298521eee3812e38237ebb719cd544e`는 이 head에 이미 통합됐으며 작성12판은 아직 main에 병합되지 않았다.
- **검증 상태:** 출발 head의 [CI400](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40799420294)과 이전 HTML 대조는 이번 Figma 보정의 통과 근거로 재사용하지 않는다. 이번 authoring Node264·Python8, runtime Node128, source frontend32 검사와 최종 소스 빌드 strict 검증을 통과했다. 최종 실제 Native 집중2시험과 같은 예시·네 탭 표본1시험도 통과했으며, 사람 상세12개 측정 영역의 위치·치수 차이는0px, 하단 버튼은0.5px 이내다. 네 탭의 가로 넘침은0이고 독립 육안 검수5개 화면에 겹침·잘림이 없었다. [실측·보존한 차이](../evals/artifacts/workspace-authoring12-ui-20261029/figma-parity/comparison.json)와 [검증 이력](../evals/v4-ui-20260930.md#workspace-authoring12-ui-20261029)을 남겼다. 전체 이미지 픽셀 일치를 뜻하지 않으며, 이번 head 전체 CI 결과는 [PR #108 검사](https://github.com/knadalkim-a11y/team-agent-poc/pull/108/checks)와 PR 본문에서 확인한다.
- **전체 CI 후속:** [CI401 Complete Native](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40859406117/job/123400889349)는 공용 central-chat helper가 작업 상세에서 없어진 목록 이동 행을 클릭해 실패했다. 공용 helper에도 ‘단계와 작업 → 목록’ 동선을 적용하고 기존 권한·저장 단언을 유지했으며, Native C44 저장·재개1시험과 helper 구문 검사를 통과했다. 제품 코드는 그대로다. 전체 central-chat 재검증과 새 head 전체 CI는 별도로 확인하며 첫 실패와 로컬 환경의 시작 실패를 평가 기록에 보존한다.
- **기능·자료 경계:** 기능 완성은 ‘워크.도구’ 설계 이후이며 새 도구 제작·backend·실행 엔진은 추가하지 않는다. 완료 조건의 기본 표시를39px로 맞추면서 textarea와 여러 줄 저장값을 유지하고, workflows 자료·숨긴 설정·기존 저장/게시 동작을 보존한다.
- **사내 적용:** 이번 변경은 미실행이다. 기존 main `42f5ae5` 적용·기동 성공 사용자 보고는 [PR #104](https://github.com/knadalkim-a11y/team-agent-poc/pull/104)의 원래 기록을 유지한다.
- **다음 하나:** 공용 시험 동선 수정의 전체 central-chat 재검증·새 head 전체 CI와 PR #108 검토를 확인한다. 병합은 사용자 별도 요청에 따르며 사내 적용은 미실행이다.

> 아래 절은 운영26판과 이전 구현 당시 기록이다. 작성12판의 현재 상태와 구분한다.

## 2026-10-28 · 워크플로우에서 단계·작업으로 바로 이동하는 목업29

- **현재 요청:** 사용자가 워크플로우→단계→작업 계층으로 탐색하고 기존 `업무.운영` 목업과 자연스럽게 이어지도록 요청했다. [29판 계약](mockups/ees-work/TASK.md#workflow-entry29-20261028)에 따라 업무 시작 진입 조건과 별도 진행 건 블록을 제거하고 개요의 단계행을 기존 작업 화면에 연결한다.
- **원본/범위:** 기존 [07 HTML](mockups/ees-work/design-mock-07-workflow-entry.html)·[편집 원본](mockups/ees-work/design-mock-src/07-workflow-entry.html), Figma 운영/공통과 [PR #107](https://github.com/knadalkim-a11y/team-agent-poc/pull/107)을 갱신한다. 조회만으로 결과를 만들지 않으며 기존 실행·판정은 합성 상태로 이어진다. 실제 서버 진행 건 생성·권한·저장 정책은 이번에 확정하지 않는다.
- **실제 적용:** 사내 마지막 보고는 `result=ok / stage=complete / running=true / commit=42f5ae502b57`이다. 새29판은 목업이며 제품 코드·API·저장·실행·사내 재배포는 변경하지 않는다. PR #106의 별도 Figma 관리 변경은 그대로다.
- **확인한 범위:** [고정29판5a7c3b0](https://github.com/knadalkim-a11y/team-agent-poc/blob/5a7c3b02e55b5b5dbe2af6e6812f6d85fe1533cf/docs/mockups/ees-work/design-mock-07-workflow-entry.html)의1920/480 폭·10장면·변경 경계81/81 PASS다. 좁은 화면에서 왼쪽 워크플로우 버튼이 오른쪽 패널에 가리던 결함을 고쳤고 실제 포인터 경로로 확인했다. 최초 실패·검증 경계는 [평가 기록](../evals/v4-ui-20260930.md#workflow-entry29-20261028)에 남겼다.
- **다음 하나:** 개요에서 ‘1차 점검’을 클릭해 기존 단계·작업 화면으로 이어지는 수정 목업을 검토한다.

> 아래28판은 업무 시작을 거쳐 단계로 들어가던 이전 설계·검증 기록이다.

## 2026-10-28 · 왼쪽 공장·시스템 선택 재사용 목업28

- **현재 요청:** 사용자가27판의 별도 공장 선택이 왼쪽 선택과 중복이라고 지적하고 목업 수정을 요청했다. [28판 계약](mockups/ees-work/TASK.md#workflow-entry28-20261028)에 따라 오른쪽 시작 폼을 제거하고 왼쪽 작업 위치로 시작한다. 공장 필수·미선택일 때만 왼쪽 목록으로 연결한다.
- **원본/반영 범위:** 기존 [07 HTML](mockups/ees-work/design-mock-07-workflow-entry.html)·[편집 원본](mockups/ees-work/design-mock-src/07-workflow-entry.html), Figma `업무.운영`/`업무.공통`과 [기존 PR #107](https://github.com/knadalkim-a11y/team-agent-poc/pull/107)을 갱신한다. 위치를 바꿔도 이전 진행 건의 대상은 유지한다. 이전27판 증빙은 보존한다.
- **실제 적용 상태:** 사내 프로그램의 마지막 사용자 보고는 `result=ok / stage=complete / running=true / commit=42f5ae502b57`이다. 새28판은 목업이며 제품 코드·서버·저장·실행·사내 재배포를 바꾸지 않는다. PR #106의 별도 Figma 관리 변경은 미병합 상태 그대로다.
- **확인한 범위:** [고정 목업5cd9f94](https://github.com/knadalkim-a11y/team-agent-poc/blob/5cd9f945def1b8911bec864cc8aca054c10b9afe/docs/mockups/ees-work/design-mock-07-workflow-entry.html)에서1920/480 폭·12장면·변경 경계63/63 PASS다. 중복 시작 때문에 비활성 버튼으로 초점이 사라지던 첫 관측을 보완했고, 외부/API 요청·브라우저 오류·가로 넘침은0이다. [검증과 경계](../evals/v4-ui-20260930.md#workflow-entry28-20261028).
- **다음 하나:** 수정 목업에서 왼쪽 선택→업무 시작→단계 진입을 확인하고 피드백을 받는다.

> 아래27판은 중복 공장 선택을 제거하기 전의 설계·검증 기록이다.

## 2026-10-28 · 진행0개 워크플로우 진입 목업27 설계

- **현재 요청:** 사용자는42f5ae5 적용·기동 성공 뒤 진행 중인 업무가 없어 새 단계 화면까지 들어가지 못한다고 보고했고, 빠진 첫 진입 흐름을 설계하라고 요청했다. [이번 계약](mockups/ees-work/TASK.md#workflow-entry27-20261028)에 따라 개요·조건부 시작 입력·단계 진입·기존 진행 업무 열기를 목업으로 연결한다.
- **최신 목업/구현 기준:** 새 설계는27판 [HTML](mockups/ees-work/design-mock-07-workflow-entry.html)·[편집 원본](mockups/ees-work/design-mock-src/07-workflow-entry.html)이다. 기존 단계26판의 디자인과 동작을 재사용하며 제품 코드·API·저장·실행은 변경하지 않는다. Figma 화면별 최신판 관리와 작업실 정리 [PR #106](https://github.com/knadalkim-a11y/team-agent-poc/pull/106)은 별도 미병합 변경으로 존중한다.
- **Figma 진입점:** `업무.운영` [시작 전 전체](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1762-456) · [시작과 단계 진입 상태](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1762-758), `업무.공통` [진입 표준](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1763-495). 기존26판과 새27판의 실제 적용 경계를 유지한다.
- **실제 적용 상태:** 사용자 보고 `result=ok / stage=complete / running=true / commit=42f5ae502b57`이다. 사내 적용·최초 화면 관측은 [PR #104](https://github.com/knadalkim-a11y/team-agent-poc/pull/104)에 기록했다. 새27판 제품 구현·배포, 실제 단계 표시·자료 보존은 확인하지 않았다. 적용 스크립트를 다시 실행하지 않는다.
- **확인한 범위:** 합성 목업을3개 화면 크기·24장면에서 검증해141/141 PASS, 가로 넘침·외부/API 요청·브라우저 오류0이다. 시작 더블클릭이 다음 단계 실행으로 전달되는 실제 결함을 보완하고 집중3/3 PASS했다. 초기 포커스·검사 가정 오류·수정 전 결과도 [평가 기록](../evals/v4-ui-20260930.md#workflow-entry27-20261028)에 보존했다. 실제 제품 적용이나 사내 사용자 확인 완료로 보지 않는다.
- **다음 하나:** 새 진입 목업의0개 상태에서 시작·단계까지 직접 눌러 보고 사용자 피드백을 받는다. 새 기능을 임의로 추가하거나 다음 워크스페이스 작성 목업으로 넘어가지 않는다.

> 아래는 이전 제품 구현·검증과 설계 당시 기록이다. 당시 대기/미확인 표현을 위 최신 상태와 구분한다.

## 2026-10-28 · 공통 단계26판 사내 적용 성공 보고·화면 진입 확인 중

- **현재 목표:** 기존 제품을 확정 목업과 시각적으로 맞춰 사내에서 확인한다. 사용자 지정 상단 표준화를 포함한 [26판 HTML](mockups/ees-work/design-mock-06-task-groups.html)·[구현 범위](mockups/ees-work/TASK.md#operations-stage26-product-20261028)를 [PR #105](https://github.com/knadalkim-a11y/team-agent-poc/pull/105)로 구현했고 main `42f5ae502b57be68aefa5d141f09259c8f6e9ee9`에 병합했다. HTML 제공·main 병합만으로 사내 제품 배포를 완료한 것으로 보지 않는다.
- **Figma 기준:** [26판 전체 화면](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1705-1020) · [집중4상태](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1705-1328) · [기록/기준](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1705-1851)과 공통 상단 적용 안내를 연결한다.25/20판의 당시 원본과 검증은 보존한다.
- **공통 상단:** 워크플로우 이름과 필요한 실제 구분 정보만 표시한다. 모든 업무에 ‘회차’를 강제하지 않으며 주기·예약 두 줄은 단계 화면에서 제거한다. 단계 제목·작업 수·실행 버튼·목록 배치는 유지한다.
- **제품 연결:** 실제 Job을 한 행으로 표시하고 기존 판정·실행 명령과 실제 도구/지침/입출력 기록을 연결한다. 실행 성공/실패를 승인/미승인으로 바꾸지 않는다. 다중 도구의 종합 판정·사유 자동 저장·첨부 연동은 새 기능으로 추가하지 않는다.
- **확인된 범위:** 최종 PR head `018e7cc42b8d13e93d3e2789b4cf26f33ebe9e59`의 [CI381](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40604943707)은 첫 실행40개 작업 중39성공·PR 출하1정상 생략이며 실패/취소0이다. Native8모듈85/85(신규2시험 포함)·PNG247장 디코더 검사, Complete Native20단계·중앙 대화17단계가 통과했다. 새 단계 자동 진입과 명시적 전체 개요의 기존 A5 자산 검사도 각각 통과했다. main과 검증한 PR/합성 merge의 tree `3e8213adf92e7171963b71804a32ac5d5a11e55c`가 같다. 앞선1920/480 폭의 목업11개 부품 대조·12상태 넘침0과 초기SKIP·CI380 최초 실패는 [평가 기록](../evals/v4-ui-20260930.md#operations-stage26-product-20261028)에 보존한다.
- **사내 설치 상태:** 사용자가 `result=ok / stage=complete / running=true / commit=42f5ae502b57`를 보고했다. 프로그램 적용·기동 성공 보고로 기록하며 이전924d919 보고와 적용 준비·실패 이력은 보존한다. 사내 PC·화면을 직접 확인한 결과가 아니며 이번 단계 화면의 실제 표시·기존 자료 보존은 아직 미확인이다. [문서 PR #104](https://github.com/knadalkim-a11y/team-agent-poc/pull/104).
- **현재 화면 관측:** 사용자는 `배포 산출물 점검` 선택 뒤 `새로 시작`·`대상 공장 시스템 전체`가 보인다고 했다. 코드상 진행 건을 선택하지 않은 수시 업무의 시작 화면이며 이번 변경은 그 뒤의 단계 화면이다. 시작 화면은924d919와42f5ae5에서 동일하다. 배포·캐시 오류로 확정하지 않으며 시작 화면 미변경과 진입 안내 누락을 구분한다. [읽기 전용 진입 안내](03-openwebui-native-agent.md#operations-stage26-readonly-entry-20261028)·[관측과 코드 근거](../evals/v4-ui-20260930.md#main-42f5ae5-intranet-report-20261028).
- **배포물 검증:** 같은 main의 [CI382](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40606766540)는 첫 실행40/40 성공했다. 새 프로그램 artifact12781047790의 실제 다운로드 크기155,277,967bytes·SHA256·내외 ZIP CRC·clean exact source_commit·32개 포함 파일·wheel/프런트엔드 원본을 기존 엄격 검증기로 확인했다. wheel SHA256은 실제 Native 시각 검증본과 같다. [메타·검증·블록 대조](../evals/artifacts/ci-delivery-20261016/main-42f5ae5-apply-prep.json).
- **다음 하나:** 기존 진행 건을 읽기 전용으로 열어 실제 단계 화면과 기존 자료를 확인한다. 이미 성공한 [적용 블록](03-openwebui-native-agent.md#main-42f5ae5-apply-prep-20261028)은 다시 실행하지 않는다. 확인만을 위해 새 진행 건·작업 실행·판정 변경을 만들지 않으며, 기존 진행 건이 없으면 그 사실만 남긴다. 문서 PR #104는 Draft·미병합으로 유지하고 워크스페이스의 운영 워크플로우 작성 목업은 이 확인 다음 순서다.

> 아래는25판 설계·보완 당시 기록이다. 당시 ‘제품 변경 없음’과 다음 작업 안내는 위의 새 구현·배포 요청으로 대체하며, 승인·실패·이전 검증 근거는 보존한다.

## 2026-10-28 · 운영 목업25판 확정·Figma 전체 화면 보완

- **사용자 확정:** 현재 운영의 ‘배포 산출물 점검 → 1차 점검’ 목업25판 디자인·모의 동작을 기준으로 확정했다. 이후 수정 가능성을 유지하며 [확정 범위와 원본](mockups/ees-work/TASK.md#work-operations-design)을 같은 [PR #105](https://github.com/knadalkim-a11y/team-agent-poc/pull/105)에 반영한다.
- **페이지 구분:** [업무 · 운영](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1284-3106) / [업무 · 공통](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1689-1061) / [업무 · 셋업](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1689-1062) / [업무 · 장애대응](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1689-1063). 셋업/장애대응은 기존 참고 설계 분류이며 새 목업 확정이 아니다.
- **현재 화면:** [25판 HTML](mockups/ees-work/design-mock-06-task-groups.html)·[원본](mockups/ees-work/design-mock-src/06-task-groups.html)·[Figma25판 전체 화면](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1700-933). 확정25판 원본과 동작은 그대로이며, 이번 보완은 Figma 표현 범위에 한정한다.
- **공통 기준과 미적용 사항:** [업무 공통 원칙](mockups/ees-work/TASK.md#workflow-stage-common-standard)은 합의된 방향이다. 실행 여부와 판정 주체 분리·상단 맥락·자료 역할 구분은 현재25판에 모두 적용되지 않았으며 후속 목업 검토로 남는다.
- **이전 기준:** [확정20판](mockups/ees-work/TASK.md#design-mock-approved20-20261027)은 이전 확정본으로 보존한다. 같은 화면의 현재 기준은25판이다. 기존 [25판 메뉴 검증](../evals/v4-ui-20260930.md#design-mock-verdict-menu-20261028)·[공통 원칙 검토](../evals/v4-ui-20260930.md#workflow-stage-common-standard-20261028)와 최초 실패/관측은 유지한다.
- **남은 계약:** 실제 Job/result.items 연결, 직접 판정 저장/최종 확정·권한, 도구 결과 조합·재실행 영향, 실제 도구/스킬 이력과 자료 연결/업로드는 후속 결정/구현 범위다. 첨부는 합성 예시다. 제품 UI·API·저장·엔진·병합·배포는 변경하지 않는다.
- **누락 정정:** 앞선 C103 반영은25판4패널 이동과 안내 확인에 한정됐고, 전체 화면·상세 자료는20판에 머물렀다. 사용자 지적 후 최신25 HTML에서21상태를 다시 캡처하고 현재 전체 화면과 도구 근거·실행 내역·기록/기준의 Figma 표현을 보완했다. 최신 화면을 앞에 배치하고 이전20은 PREVIOUS20으로 구분했다. 이전 완료 주장·실제 누락·최종 대응 범위는 [이번 검증](../evals/v4-ui-20260930.md#operations25-figma-sync-20261028)에 기록하며, [이전 확인](../evals/v4-ui-20260930.md#work-operations-approved25-20261028)을 삭제하지 않는다.
- **사내 적용 원본:** [미병합 문서 PR #104](https://github.com/knadalkim-a11y/team-agent-poc/pull/104)의 사용자 보고 `result=ok / stage=complete / running=true / commit=924d919333b8`에 따라 프로그램 적용 완료·실행 중으로 구분한다. 로그인·기존 자료·새 화면·도구 설정은 별도 미확인이다. #104의 상세 적용 기록은 이 브랜치에 복제하거나 덮어쓰지 않는다.
- **다음 하나:** 이번 운영25판 Figma 보완 뒤, 사용자가 지정한 워크스페이스의 운영 워크플로우 작성 화면을 목업부터 다룬다. 기존 워크-1 설계와 운영25판의 단계·작업·도구·입력·판정 기준을 연결하고 미정 기능 계약은 임의 구현하지 않는다.

> 아래 절은 이전 작업 당시 기록이다. #103 병합 대기·사내 적용 미실행 등의 당시 표현은 위 현재 상태와 구분하고, 과거 검증·실패 근거는 보존한다.

## 2026-10-26 · main924d919 사내 적용 완료 (사용자 보고)

- **현재 적용:** 사용자 회신 `result=ok / stage=complete / running=true / commit=924d919333b8`를 받았다. 확정 대상은 `924d919333b8804ece2cf5322e14adc681ad6457`이며 프로그램 적용 완료·실행 중으로 기록한다. 에이전트가 사내 PC나 화면에 직접 접근해 확인한 결과는 아니다. 적용 명령을 반복하지 않는다.
- **검증·보존:** 적용 대상 main의 CI#34540/40 성공과 ZIP 검증을 유지한다. 정정 블록 b5aed83의 [CI#347](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40316799429)는 첫 시도39성공/PR 출하1정상 생략이며 Native83/83·작성29/29·Windows2289자 PowerShell 구문 검사도 통과했다. 초기 설치 기준 불일치·임시 ZIP 이름 실패는 [평가 기록](../evals/v4-ui-20260930.md#main-924d919-apply-evidence-20261026)에 보존한다.
- **다음 하나:** 브라우저에서 로그인·기존 대화/업무/입력·단계⋯/작업 상세·Work 도구 상태를 확인하고 결과만 짧게 받는다. 화면·자료 보존·Confluence 관리자 설정/개인 연결은 아직 미확인이다. 문서 #104는 미병합이며 이번 갱신은 상태 기록뿐이다.

> 아래 사전 중단·미실행·결과 대기 문구는 이번 성공 보고 전 기록이다.

## 2026-10-26 · 사내 적용 사전 중단·설치 기준 정정

- **사용자 보고:** `EES before commit=1c1efff7abe… valid=true running=true`. 최초924d919 블록은 과거2a4b82a 보고를 예상해 Update·Stop·백업·Apply 전에 중단했다. Status는 읽기 전용이며 **924d919 적용은 미실행**, 보고 당시 기존 프로그램은 유효·실행 중이다.
- **정정·보호:** Git의 #101 병합 원본은 `1c1efff8abe19da3e6e8921859b52858fc6cacfb`이다. 사용자 타이핑7/8 차이를 확정하지 않고 [정정 블록](03-openwebui-native-agent.md#main-924d919-apply-prep-20261026)이 전체 SHA를 정확히 검사한다. 이미 받은 동일 ZIP은 크기/해시 재검증 뒤 재사용하며, 없을 때만 기존 다운로드를 진행한다. 1c1efff8→924d919 운영·Work 백엔드·저장·도구 코드는 동일하다.
- **다음 하나:** 정정 블록의 `result/stage/running/commit`1~2줄을 받는다. 다시 EES before면 출력의 commit 앞12자리만 확인하고 반복하지 않는다. Restore는 필요하지 않으며 문서 #104는 미병합으로 유지한다. [실패와 정정 근거](../evals/v4-ui-20260930.md#main-924d919-apply-evidence-20261026). 대상 main의 CI#345 성공과 문서 정정 head의 CI는 별개다.

> 아래 최초 준비와2a4b82a 기준·미실행 표기는 정정 전 기록이다. 실패와 당시 판단을 보존한다.

## 2026-10-26 · #103 병합 완료·main924d919 사내 적용 준비

- **병합·승인:** 사용자 “병합하고 해” 승인으로 #103을 **2026-10-26 17:45:45 KST**, main `924d919333b8804ece2cf5322e14adc681ad6457`에 merge commit으로 병합했다. 최신 PR head afc4697의 [CI40290888003/#344](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40290888003)는39성공/PR 출하1정상 생략이었다. rebase·force-push·main 직접 push는 하지 않았다.
- **main 검증:** [CI40294530820/#345](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40294530820) **첫 시도40/40 성공**, Native83/83·작성29/29·Complete Native·execution5/5·Windows 검증을 확인했다. 프로그램 ZIP 실제 크기·SHA256·내/외 CRC·기존 manifest/wheel 검사를 통과했다. [적용 근거](../evals/v4-ui-20260930.md#main-924d919-apply-evidence-20261026).
- **사내 적용:** 사용자 실행용 [2,500자 이내 한 블록](03-openwebui-native-agent.md#main-924d919-apply-prep-20261026)을 준비했다. 마지막 설치 보고2a4b82a의 정상/미완료·정확SHA와 목표ZIP·HEAD/origin/main 보호를 유지한다. 운영·Work/Confluence 도구·업무 백엔드/저장 형식은2a4b82a와 동일하며 도구 재등록/자료 이관은 하지 않는다. 실제 사내 PC 실행·적용은 아직 **미실행**이다.
- **다음 하나:** 사용자가 블록을 실행하고 기존 `result/stage/running/commit`1~2줄을 전달한다. 실패면 반복하지 않고 보존된 단계/상태로 판단한다. 새 문서 PR을 먼저 병합해 main을 바꾸지 않으며, 실제 적용 성공이나 도구 설정 완료는 사용자 결과를 받은 범위에서만 기록한다.

> 아래 #103 미병합·“병합은 사용자”와 과거 적용 대기는 이번 승인 전 기록이다. 현재 병합/적용 상태는 위 절을 따르며 모든 과거 기록을 보존한다.

## 2026-10-26 · PR #103에 #102 병합 main 통합

- **완료한 선행 조건:** 사용자 승인으로 [#102](https://github.com/knadalkim-a11y/team-agent-poc/pull/102)를 **2026-10-26 10:15:03 KST**, main `4d27de76fe4bbc4aad70ec009bb7d478d0bbe29f`에 merge commit으로 병합했다. 최종 head41c0a4b의 [CI40252075901/#341](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40252075901)는39성공/PR 출하1정상 생략, Native81/81·작성27/27·Windows Node probe와2454자 PowerShell 파싱을 통과했다. 첫 실패와 원인 미확정은 보존했다.
- **현재 통합:** [#103](https://github.com/knadalkim-a11y/team-agent-poc/pull/103)의 검증된0b885d3에 위 최신 main을 merge commit **`5634ca9cc9e953f5a91226e45e8985e32b863909`**으로 통합했다. 두 부모는0b885d3·4d27de7이며 rebase·force-push는 하지 않았다. STATUS 상단1곳의 충돌은 양쪽 기록을 모두 남기고 이 현재 상태를 앞에 두어 해결했다. CHANGELOG·가이드·evals·증거와 CI의 읽기 전용 PowerShell 파싱은 함께 보존한다. C66 제품/시험 소스는0b885d3 그대로이며 API·저장 형식·시험 단언·시간 제한은 바꾸지 않는다.
- **통합 head 전체 CI:** `5634ca9cc9e953f5a91226e45e8985e32b863909`의 [CI40253641052/#343](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40253641052)는 **첫 시도 성공·39작업 성공/PR 출하1정상 생략**이다. Native **83/83·작성29/29**, Complete Native·execution5/5, Ubuntu/Windows 최종 검사와 기존10초 launcher probe·2454자 PowerShell 파싱을 통과했다. 실제 Native 구성 PNG235장·Complete Native45장의 유효성을 확인했다. [병합 main CI40253294470/#342](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40253294470)도 **첫 시도40/40 성공**이며 Native81/81·작성27/27과 프로그램 ZIP 생성을 확인했다. PR 본문에도 동일한 head·번호·결과를 기록했다.
- **검증 구분:** 통합 전 #103의 [CI40242894489/#340](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40242894489)는39성공/1정상 생략·Native83/83·작성29/29다. 위 #343은 통합 head를 직접 검증한 결과이며 이전 성공으로 대신하지 않았다. [통합 기록](../evals/v4-ui-20260930.md#work-content-job-detail-c66-20261022). 이번 후속 변경은 이 STATUS의 결과 명시뿐이다. 선택 사항인 CSS 토큰 치환은 이미 끝난 통합 push에 추가하지 않아 제품·시험·기존 화면을 그대로 유지한다. 기록 보완 head의 최신 전체 CI는 [같은 PR 본문/Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/103/checks)에서 별도로 확인한다.
- **사내 적용:** **미실행**이다. 기존2a4b82a의 유효/실행 중 사용자 보고를 유지한다.1c1efff 블록은 당시 검토 기록이며 새 적용 때 목표·성공 CI 프로그램 ZIP·바이트/SHA256·설치 원본을 함께 확정한다. 보호 조건·PowerShell 실행문은 바꾸지 않는다.
- **다음 하나:** 통합 및 전체 CI 검증을 완료한 #103을 사용자가 검토·병합한다. #103은 Draft가 해제된 상태이며 에이전트는 #103 자체를 병합하지 않는다. main 직접 push·사내 실행·Figma/서버 API/사용자 자산 변경은 하지 않는다.

> 아래 #103 보완·#102 승인 및10-22 적용 준비 절은 통합 전의 기록이다. ‘#102 미병합’, ‘main1c1efff’, 당시 ‘다음 하나’는 위 현재 상태로 대체하며 최초 검증·실패 내용은 보존한다.

## 2026-10-26 · PR #103 C66 검토 보완 완료

- **현재 범위:** #101 병합 main `1c1efff8abe19da3e6e8921859b52858fc6cacfb`의 별도 `feat/work-content-job-detail-c66-20261022`, [PR #103](https://github.com/knadalkim-a11y/team-agent-poc/pull/103)에서 추가 설정 요약·도구 선택 줄의 검토 보완을 완료했다. [계약](mockups/ees-work/TASK.md#work-content-job-detail-c66-20261022) · [최초 실패·검증](../evals/v4-ui-20260930.md#work-content-job-detail-c66-20261022). 아래 #101 재검토 문구는 당시 기록이다.
- **이번 결과:** 제품·시험 head `62c9515d3e861f98445071bc29328ae1abd33c97`의 [CI40241391858/#339](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/40241391858)는 **39작업 성공/PR 배포 준비1정상 생략**, Native **83/83·작성29/29**다. 관련 Node519 PASS·작성/일정 Python30 PASS이며 기존 저장·D5·상수·키보드 보호를 유지했다. 실제 작업 상세26장 중 지정한6상태×두 폭과 완료 조건 하단14장을 Figma에 직접 대조했고 전체26관찰의 가로 넘침은0이다. [원본 결과·캡처·해시](../evals/artifacts/work-content-job-detail-c66-20261022/review-20261026-ci339-evidence.json). 기록을 포함한 최종 head의 전체 CI 번호와 결과는 [같은 PR 본문/Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/103/checks)를 원본으로 연결한다.
- **보완 내용:** 사람이 확인·AI 초안의 숨은 수행 안내/다시 읽기를 추가 설정 요약에서 제외했다. 작업 상세만 이름→조회/도구 확인 필요→알려진 버전→오른쪽 chevron으로 표시하고 미연결 이름·버전은 원본 회색을 쓴다. 기존 목록·선택·포커스·저장 동작은 유지한다. 새12개 중 최초10FAIL·수정 후12PASS, 새 Native 포커스 색 기대 오류와 실제 화면/토큰 대조 과정은 평가에 보존했다.
- **별도 적용 문서:** [PR #102](https://github.com/knadalkim-a11y/team-agent-poc/pull/102)는 아직 미병합이며 섞지 않았다. 적용 전 출력에서 확인된 기존 프로그램은 `2a4b82a5f482…`, valid/running=true이고 `1c1efff` 적용 성공은 아직 보고되지 않았다. 이번 C66 사내 실행·적용은 **미실행**이다.
- **앞선 제품 검증:** 제품 head `537cda97799dabcaa62e07324ce481f32587b170`의 [CI39759230676/#334](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39759230676)는 39작업 성공/PR 배포 준비1생략이다. Native 구성83/83·작성29/29, 관련 Node507 PASS이며 D5 취소/정리·상수 왕복/게시 검사·기존 자료·공장 초기화·메뉴/포커스를 통과했다. 480/1366 실제 단계32장·작업 상세26장과 Figma 대조, 하단 단추 가시성·넘침0을 [증거 색인](../evals/artifacts/work-content-job-detail-c66-20261022/ci334-evidence.json)에 보존했다. 최초 실패와 #330~333의 미도달 범위·수정 이유는 평가에 그대로 남겼다.
- **이전 기록 보존:** 기존 기록 head78bc879의 CI #335도39성공/1정상 생략이었다. #334/#335와 이번 #339를 구분하며, 앞선 실패·취소·미도달 범위를 성공 뒤에도 보존한다.
- **남은 경계:** 서버 오류에 구조화 인자 ID가 없어 게시 오류의 개별 입력 줄 연결은 후속이다. 기존 전체 오류 안내를 유지하며 문구 파싱/API·저장·검증기 변경은 없다. 실제 사내 도구/모델 연결·사용자 사용성 확인은 이번 합성 Native 검증에 포함하지 않는다.
- **다음 하나:** 사용자가 **#102를 먼저 병합 → #103에 최신 main 통합(양쪽 기록 보존) → 통합 head CI 확인** 후 #103을 검토·병합한다. #103은 Draft가 해제된 상태이며 현재 main은1c1efff다. main 직접 push·PR 병합·사내 적용·Figma/API/저장 형식 변경은 하지 않았다.

## 2026-10-26 · PR #102 병합 승인·검증

- **현재 범위:** 사용자가 #102 병합을 명시 승인했다. [문서 PR #102](https://github.com/knadalkim-a11y/team-agent-poc/pull/102)의 기존 head5f047c8·main1c1efff에서 최종 검증한다. 제품·서버 API·시험 단언·시간 제한은 변경하지 않는다. #103 병합·사내 실행/적용 승인은 포함하지 않는다.
- **확인한 실패:** 최신 [CI39738417918/#329](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39738417918)는 Windows 합성 Node launcher probe가 진입 표식 없이10초 제한에 걸린1건으로 실패했다. 이전 종료 시험67개와 정정 PowerShell 블록2454자 파싱은 통과했으므로 이전 종료 실패와 구분한다. 원인 미확정·원문·최초 실패를 [기존 평가](../evals/v4-ui-20260930.md#main-1c1efff-apply-evidence-20261022)에 보존한다.
- **적용 경계:** 기존1c1efff 블록은 당시 검토 기록이다. main이 진행되면 정확 SHA 보호로 중단하므로 다음 사내 적용에는 목표·CI ZIP·바이트/해시·설치 원본을 함께 다시 확정한다. 기존2a4b82a의 유효/실행 중 사용자 보고 이후 새 적용 성공은 없으며 사내 적용은 **미실행**이다. 아래10-22의 ‘다음 하나’는 당시 상태다.
- **다음 하나:** 기록을 포함한 새 head를 새 실행기에서1회 검증하고 전체 필수 CI 성공 뒤 #102를 merge commit으로 병합한다. 같은 Node 실패가 재발하면 자동 반복·제한 완화 없이 진단한다. 정확한 최종 head·CI·병합 결과는 같은 PR 본문/Checks를 원본으로 확인한다. 이후 앞서 정한 #103 최신 main 통합 순서를 따르되 #103 자체는 병합하지 않는다.

## 2026-10-22 · main 1c1efff 사내 적용 준비

- **현재 원본:** #101까지 main `1c1efff8abe19da3e6e8921859b52858fc6cacfb`에 병합됐다. main [CI 39694472521 / #326](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39694472521) 첫 시도 40개 작업 성공·native-compose 81 PASS와 프로그램 ZIP을 확인했다. 준비 착수 시 열린 PR은 0개였다. 아래 #101 재검토·병합 대기는 당시 상태다.
- **사내 적용·최초 시도:** 2026-10-22 사용자가 Claude 검토 후 실행했고 `EES before commit=2a4b82a5f482… valid=true running=true`로 중단됐다고 보고했다. 접두어는 #96 병합 main `2a4b82a5f482b6b1677b40cad171589c71bae13f`와 일치한다. 최초 준비의 d4f1806 기준이 실제보다 오래돼 Update·Stop·Apply **전**에 차단됐다. 1c1efff 적용·새 기동·설정 변경은 **미실행**이며 보고 당시 기존 프로그램은 유효·실행 중이다. 실제 PC 파일·DB를 직접 확인한 것은 아니다.
- **다음 하나:** [설치 기준을 실제 2a4b82a로 정정한 한 블록](03-openwebui-native-agent.md#main-1c1efff-apply-prep-20261022)을 사용하고 기존 `result/stage/running/commit` 1~2줄로 적용 결과를 받는다. 목표 ZIP·해시·정상/미완료 설치 검사·정확한 SHA 비교는 유지한다. 남은 main 변경은 #100·#101이며 운영/업무 Python 코드는 동일하다. [최초 중단과 근거](../evals/v4-ui-20260930.md#main-1c1efff-apply-evidence-20261022). 이 문서 PR 병합과 에이전트의 사내 실행·도구 변경은 하지 않는다.

## 2026-10-21 · PR #101 C61 동시 편집 안내

- **현재 범위:** 미병합 `ce099f2`에서 같은 PR의 안내 위치·시점·취소 단추 3건만 변경한다. revision과 버퍼/최신 초안 보존·쓰기 차단은 유지한다. [계약](mockups/ees-work/TASK.md#work-content-chat-proposals-20261020).
- **최초 검증:** 제품 수정 전 새 Node 17건 실패, 추가 경계를 원본 ce099f2로 확인한 22건 실패를 보존했다. 이름 오류로 쓰던 동시 편집 안내를 C61에 따라 즉시 폼 안내로 교체한다. 수정 후 관련 Node458 PASS·작성/일정 Python30 PASS·문서/diff를 통과했다. 실제 Native는 로컬 자료 부재로 SKIP이며 최종 CI에서 실행한다. [최초 실패·검증](../evals/v4-ui-20260930.md#work-content-chat-proposals-20261020).
- **다음 하나:** 관련 시험·문서/diff·최종 head CI(native-compose)와 480/1366 예시13·14 캡처를 확인하고 같은 PR에 Claude 재검토 댓글 하나를 남긴다. 병합·main 직접 push·사내 적용·Figma 변경은 하지 않는다. 아래 기록은 이전 단계의 상태다.

## 2026-10-21 · PR #101 검토 수정

- **현재 범위:** 같은 `feat/work-content-chat-proposals-20261020`의 `6b1944a`에서 사용자 수정 7건과 이름 안내를 반영한다. 위치 변경의 LCS 계산·묶음 목록, 제안 삭제의 기간 정리, A4a 입력 저장 전·되돌리기, 탭 왕복 보존, 메뉴 Escape·차단 안내·숨긴 순서 알림이다. [정정 계약](mockups/ees-work/TASK.md#work-content-chat-proposals-20261020).
- **검증:** 제품 수정 전에 새 Node 단언의 작성 9개·입력 13개 실패와 제안 기간 Python 통합 실패를 확인했다. 시험 준비 오류·문서 참조 오류와 이전 CI 실패도 [기존 평가](../evals/v4-ui-20260930.md#work-content-chat-proposals-20261020)에 보존한다. 최종 head의 실제 브라우저 포함 CI와 480·1366 화면 대조는 [PR #101](https://github.com/knadalkim-a11y/team-agent-poc/pull/101)의 본문/Checks에서 확정한다.
- **첫 실제 화면 확인:** `d91e619`의 CI 39541400685는 Native 구성 79 PASS / 기존 시험의 Python 지역 import 오류 1 ERROR였다. 새 예시 12·탭/되돌리기·차단 안내는 통과했다. 오류를 최소 수정하고 실제 480 캡처에서 드러난 A4a 막대의 단어 중간 줄바꿈·색상도 보완한다. 첫 실패·원본 화면 해시·새 단언 실패는 위 평가에 보존하며 후속 head 전체 CI를 다시 확인한다.
- **후속 자동 검토:** 설정 탭의 제안 비교 기준과 독립 설정 저장, 혼합 초안의 같은 종류 이동, 큰 제안의 반복 계산을 새 단언 6개 실패로 재현해 보완했다. Node 8모듈 471 PASS, 엄격한 인코딩의 일정·작성 Python 30 PASS다. 248개 작업의 비교 호출은 251회에서 화면 갱신당 1회로 줄였으며 실제 설정 탭 회귀와 최종 화면은 후속 head CI에서 확정한다.
- **마지막 표시·진입 검토:** 저장 성공 뒤 남은 반영 표시, 빈 단계의 추가 설정 진입, 혼합 초안의 순번과 수동 편집 뒤 배지 갱신을 새 단언 8개 실패로 재현해 수정했다. 관련 Node 8모듈 481 PASS이며 한글 조합·포커스·커서 보존을 포함한다. 실제 브라우저에 저장 뒤 재편집·저장 전 한 칸 편집·빈 단계 설정 왕복을 추가했다. 최초 실패와 앞선 CI 대체 이력은 기존 평가에 보존한다.
- **31c4e1f 검증·추가 경계:** 실제 CI 39545049473는 Native 구성 80 PASS / 새 설정 시험의 응답 경로 1 ERROR였다. 원시 서버 응답과 화면 정규화를 구분해 같은 저장·버전 단언을 유지한다. 이 실행의 480·1366 예시 12·A4a 및 Complete Native product는 대조했으며 원본 오류·해시는 기존 평가에 보존했다. 같은 값·연속 제안·요청 화면에 숨은 입력의 추가 검토 3건은 새 단언 10개와 반영 시점 재검 1개 실패 후 보완했다. 최종 관련 Node 493 PASS이며 최신 head 전체 CI로 확정한다.
- **최신 버전·표시 수명 보완:** ff12997의 추가 검토에서 열린 단계 폼의 구버전 적용과 직접 고친 칸의 기여 재등장을 재현했다. revision을 비교해 최신 저장본과 버퍼를 보존하고, 원격 삭제 뒤에도 버퍼 검토·취소를 제공한다. 수동 편집·외부 저장으로 끝난 기여는 제거한다. 이 실행에서 설정 탭 시험은 통과했고 새 요청 필드 순서 기대값 1건이 실패했다. 저장된 스키마의 정확한 순서로 정정하며 원본 실패와 새 단언은 기존 평가에 보존한다. 최종 관련 Node 505 PASS, 작성 Python 8 PASS이며 실제 화면은 최신 head CI로 확인한다.
- **다음 하나:** Codex 스레드 3건에는 수정 커밋 `0bd38de`를 답하고 해결 처리했다. 최신 head의 실제 브라우저 포함 CI·화면을 확인한 뒤 Claude 재검토 댓글 하나를 남긴다. 새 PR·병합·main 직접 push·사내 실행/적용·서버 API·Figma 변경은 하지 않는다. 아래 10-20 기록은 당시 상태다.

## 2026-10-20 · 업무 내용·단계와 작업 · 대화 제안 E1·E2

- **선행 완료:** 사용자 요청으로 [PR #100](https://github.com/knadalkim-a11y/team-agent-poc/pull/100)을 `3c343ce` 에 병합했다. 최종 head `2a3ddf5` 의 CI 39420778057 성공과 C60 실제 Native 증거를 확인했다. 이 main 에서 새 `feat/work-content-chat-proposals-20261020` 을 시작한다. 아래 C60 Draft·병합 대기는 당시 기록이다.
- **현재 범위:** 작성의 요약·구조를 업무 내용으로 합치고 단계 접힘·이름 먼저 추가·수정/삭제/왕복을 구현했다. 패널 AI 요청은 제거하고 대화에서 받은 정의·입력 제안의 검토/반영/버리기를 유지한다. 단계 삭제 시 기간 설정 잔류 결함을 함께 고쳤다. [계약](mockups/ees-work/TASK.md#work-content-chat-proposals-20261020) · [최초 실패·검증](../evals/v4-ui-20260930.md#work-content-chat-proposals-20261020).
- **최근 검증:** 관련 Node 439 PASS, 기간 삭제 뒤 실제 저장·주기 게시 검사 통과. CI 의 새 480 px / 1366 × 768 변형 시험과 38개 화면 관찰을 통과했고 경고 가시성·포커스·스크롤 복원을 확인했다. 실제 대화 제안·계정/업무/실행·전체 제품도 통과했다. 두 번째 CI 에서 드러난 좁은 화면의 기존 56 px 여유 단언과 CSS 아이콘 검토 목록 누락은 시험에 반영했다. 최초 실패·시각 보완·로컬 의존성 부재와 미실행을 평가에 보존한다.
- **PR·다음 하나:** [PR #101](https://github.com/knadalkim-a11y/team-agent-poc/pull/101)의 정확한 최종 head CI 와 최종 화면 판정은 PR 본문/Checks 를 원본으로 확인한다. 필수 검증을 통과한 새 PR 을 사용자가 검토·병합한다. #100 병합 main 의 [CI 39425795994](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39425795994)는 전체 성공이며 프로그램 산출물도 생성됐다. 사내 실행·적용, 서버 API 변경, 작업 상세 재설계, Figma 수정은 하지 않았다.

## 2026-10-20 · C3 겹친 패널 Escape 범위 · C60 정정

- **현재 범위:** 같은 Draft #100 의 `aa32500` 에서 C60 을 반영한다. 대화 Escape 가 겹친 패널을 닫고 포커스를 옮기던 문제를 패널 안 target 조건과 닫기 시작 시 바깥 포커스 보호로 수정했다. 기존 제외 조건·붙은 패널·움직임과 C54 를 유지한다. [현재 계약](mockups/ees-work/TASK.md#common-motion-c3-20261020).
- **검증:** 기존 시험은 패널 안 Escape 만 검사해 대화 경로를 놓쳤다. 새 단언은 수정 전 22 PASS / 2 FAIL, 수정 후 Svelte 24 PASS 이며 관련 Node 전체 59 PASS 이다. Native 회귀에 대화 Escape 의 document 버블 도달과 패널 Escape 의 미도달 증거를 추가했다. [최초 실패·환경·남은 검증](../evals/v4-ui-20260930.md#common-motion-c3-20261020). 정확한 최종 head CI 결과는 [PR #100](https://github.com/knadalkim-a11y/team-agent-poc/pull/100)에서 확인한다.
- **첫 CI:** `c0e7d81` 의 CI 39420123286 은 변경 전 공식 wheel 의 Chrome 시작 응답 시간 초과로 실패했다. C60 패치 빌드와 EES 실제 브라우저는 미진입이다. 기록만 더한 head 를 새 실행기에서 1회 재검하며 제품·시험·시간 제한은 유지한다. 원인 미확정과 첫 실패는 위 평가에 보존한다.
- **다음 하나:** 최종 head 의 실제 브라우저 포함 CI 를 확인한 뒤 같은 PR 에 댓글 1개로 Claude 재검토를 요청한다. Draft 유지·병합 없음·사내 실행/적용 미실행이다. E1·E2 는 착수하지 않는다. 아래 기록은 C54 당시의 상태와 이전 증거다.

## 2026-10-20 · C3 공통 움직임 · C54 정정

- **현재 원본/범위:** Draft #100 head `2bbbdd3`의 Claude 검토와 C54에 따라 겹친 업무 패널의 배경막만 제거한다. 패널16px/투명도·Escape·닫기·포커스와 붙은 패널, 확인 창·도움말 배경막은 유지한다. [C3 계약](mockups/ees-work/TASK.md#common-motion-c3-20261020).
- **검증:** 선행2bbbdd3의 CI39355663661은39작업 성공/PR 배포 준비1생략으로 성공했다. 당시 시험은 닫기 중 대화 클릭만 확인해 열린 패널의 차단을 놓쳤다. 이번에는1095px에서 열린 패널 옆 대화의 실제 클릭·입력과 초안 보존을 추가한다. 최초 구현·수정 전 재현과 후속 결과는 [기존 평가](../evals/v4-ui-20260930.md#common-motion-c3-20261020)에 보존하며 최종 head/CI는 [Draft #100](https://github.com/knadalkim-a11y/team-agent-poc/pull/100)에서 확정한다.
- **다음 하나:** 관련 Node·Native·문서·최종 CI 확인 후 같은 PR 댓글1개로 Claude 재검토 요청. Draft 유지, main 직접 push·병합·사내 실행/적용·Figma 수정·#77/#79는 하지 않는다.

## 2026-10-20 · #96 최신 main 통합·최종 병합 검증

- **완료한 선행 조건:** #95·#94에 이어 main 시험 신뢰성 보완 [#99](https://github.com/knadalkim-a11y/team-agent-poc/pull/99)를 main `b1cee7d1a678891caff7c332c9a7fd5595628ddd`로 병합했다. 이 main의 [push CI39345522634](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39345522634) 첫 시도40개 성공과 [Agent Pack ZIP12232065133](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39345522634/artifacts/12232065133), 1,200,576 bytes 확인 뒤 #96 통합을 시작했다. 시험·문서 변경인 #99의 산출물은 Agent Pack ZIP이며 새 프로그램 ZIP으로 표시하지 않는다. [#94 최초 실패·#99 보완 완료](../evals/v4-ui-20260930.md#main-native-reliability-20261020)는 보존한다.
- **현재 범위:** #96 head `9de04fb42120ca99dff7b17065b4d14faf47078b`에 위 main을 merge commit으로 통합 중이다. 양쪽 기록·시험과 main의 작성 머리 구조를 유지하며 #96의 `도구 · 공용`·시스템 이름 숨김을 결합한다. README는 [기능 명세](specs/shared-tools.md)를 현재 진입점으로 연결한다. 기존 ST-OPEN-3/4/5/6/8/9 결정 필요 항목은 다루지 않는다. [이번 통합·검증](../evals/v4-ui-20260930.md#pr96-merge-validation-20261020).
- **통합 검사:** 충돌0, Node224PASS·strict Python209PASS/77SKIP(고정 Native 자료 미준비). 추가 실행 모듈명 오기1ERROR는 평가에 보존하고 정확한 모듈의35PASS/2SKIP로 확인했다. 시험 ID 감사1550개/오류0·전체 diff 통과. 실제 Native/Windows를 포함한 최종 head CI와 병합 main CI/ZIP은 순차 확인한다.
- **다음 하나:** 충돌 해소·관련 시험·문서/diff·최종 head 전체 CI·PR 본문 검증을 마친 뒤 #96 Draft를 해제하고 merge commit으로 병합한다. 병합 main push CI 성공과 해당 배포 ZIP을 확인한다. 기존 head 성공을 이번 통합 검증으로 대신하지 않으며 새 실패는 원인 판단과 함께 보존한다.
- **보존/범위:** main 직접 push·rebase·force-push·브랜치 삭제·사내 실행/적용·Figma 수정·#77/#79 착수는 하지 않는다. Figma 카드의 ‘미병합’ 표기는 Claude가 정리한다. 아래는 당시의 중단·Draft·병합 대기·실제 적용 이력이며 현재 진행 상태는 이 절을 따른다.

## 2026-10-20 · #94 병합 main CI 실패·Native 시험 보완

- **완료한 선행 조건:** #95 merge main `471236a47939275d1cfeea637166642388b072f8`의 [push CI39338337583](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39338337583) 첫 시도 성공과 [프로그램 ZIP12228507651](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39338337583/artifacts/12228507651), 155,193,025 bytes 확인 후 #94를 통합했다. #94 최종 head `930d7c29ca1751fc1b71e89899ea70a81ba96443`의 [PR CI39340559323](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39340559323) 성공 뒤 main `7e71b615cb0c751781b731c55cd9a0439252a6a8`로 병합했다. [#95 최초 실패·검증](../evals/v4-ui-20260930.md#pr95-merge-reliability-20261020)과 [#94 통합·검증](../evals/v4-ui-20260930.md#pr94-merge-validation-20261020)은 보존한다.
- **현재·중단 조건:** #94 병합 main의 [push CI39342237471](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/39342237471)는 첫 시도 completed/failure다. native-compose2시험이 실패했고 배포 artifact0건으로 ZIP 조건을 충족하지 못했다. #96에는 main을 합치지 않았다. source-shell은 정상 목적지 프레임 직전 관측 경계를 닫았고, 일정 필드 시험은 다른 초기 절차를 클릭했다. 원인별 확신 범위·원본 증거·실행 환경은 [기존 평가 기록](../evals/v4-ui-20260930.md#main-native-reliability-20261020)에 남겼다.
- **다음 하나:** 사용자 승인6항에 따라 최신 main 기반 `test/main-native-readiness-20261020` 새 PR에서 두 시험의 준비·관측 경계만 보완한다. 제품 파일은 변경하지 않으며 관련 시험·문서/diff·최종 head 전체 CI·PR 본문 검증을 확인한다. 승인 조건으로 merge commit 병합 후 해당 main push CI 성공과 배포 ZIP을 확인해야 #96 통합을 재개한다. 로컬 구문 검사 통과와 Native 환경 부재 SKIP를 실제 브라우저 성공으로 세지 않는다.
- **보존/범위:** 세 PR과 보완 PR의 브랜치를 유지하고 main 직접 push·rebase·force-push·사내 실행/적용·Figma 수정·#77/#79 착수는 하지 않는다. 재실행 성공으로 첫 실패를 지우지 않으며, 기존 사내 적용 기록은 아래에 보존한다. 아래 Draft/병합 대기 문구는 각각 당시 상태다.

## 2026-10-19 · 8081 검증본 main 병합 검증

- **사용자 승인/범위:** 8081 실행본의 작성 UI·초기 절차·Windows 빌드 보완과 관련 시험/문서를 기존 `feat/figma-parity-20261017`에서 PR로 검증 후 병합한다. main `f7cfeee`는 변경 없으며 #94/#95/#96은 별도 미병합 범위다. 계정·비밀번호·DB·키·로컬 runtime 자료는 포함하지 않는다.
- **실행본 대응:** 최초 PR의 제품 원본은 8081 wheel `71623cd4…`의 frontend 입력 134개·업무 자산 16개와 일치했다. 병합 검사에서 Escape 취소의 Native 대화 포커스 간섭과 새 아이콘이 구버전 복원 목록에 섞인 문제를 추가 수정했다. 8080/8081 프로그램·데이터를 교체하거나 사내 배포하지 않는다.
- **검증 상태:** 최초 로컬 Node 212 PASS, backend/개인 개발/시험 분류 97 PASS, Windows Chrome 작성 흐름 4 PASS. 확장 검사와 첫 CI에서 옛 시작 화면/문구/편집 경로를 기대한 시험, 시험 prelude, 구버전 복원 목록 결함을 발견해 보완했다. 상세 실패·재검증은 [병합 검증 기록](../evals/v4-ui-20260930.md#merge-8081-20261019), 최종 원격 판정과 병합 여부는 [PR #98의 Checks와 병합 상태](https://github.com/knadalkim-a11y/team-agent-poc/pull/98)를 원본으로 확인한다. PR 생성만을 병합 완료로 판단하지 않는다.
- **다음 개발 하나:** C44 부분 변경 제안·되돌리기·영속 카드와 미저장 초안 참고 연결. 전체 Figma 동일·실제 모델/사내 연동 완료로 판단하지 않는다. 현재 개인 PC 실행 방법과 8080/8081 구분은 아래 10-17 기록을 유지한다.

## 2026-10-17 · C44 작성 흐름 누락 보완·별도 로컬 검증본

- **현재 범위:** `feat/figma-parity-20261017`, HEAD/main `f7cfeee`. 기존 dirty 요약·초기 절차·설치 변경 보존, 열린 #94/#95/#96 미병합. [대조표/기능 계약](mockups/ees-work/TASK.md#authoring-audit-20261017)에 현재 설계·옛 R8·미정 사항을 구분했다.
- **반영:** 항목별 설명·예시, 입력 정의/실행 값 구분, 작업 기준 판정/송부 필요 여부, 명시적 해당 없음과 검사 필요/오류 구분. 무슨 업무·언제 제자리 편집의 취소/적용/초안 저장 분리, 탭 왕복 버퍼·다른 미저장 내용 보존, 입력 dialog 고급 항목 접기/스타일, 목록 저장 시각·이어 작성 및 분류 수정 진입을 보완했다.
- **검증:** 관련 Node212PASS, workspace/routes80PASS, frontend/branding58PASS/3정상SKIP, Windows Chrome Native4PASS. 실제 모델·사내 연결·전체 Figma 반영 성공은 아니다. 최초 실패·화면·빌드 근거는 [평가 기록](../evals/v4-ui-20260930.md#authoring-audit-20261017).
- **실행본 구분:** 기존 개인 앱 `http://localhost:8080`은 교체하지 않았다. 새 검증용 wheel은 `D:/EES-Workflow-Dev-Builds/20261017-authoring-audit/branding`, SHA256 `71623cd44cb421407fb703d289034a171f3b0343a23eadf88baafe04657c41f6`이다. 별도 데이터/키의 `http://localhost:8081`에서 검증하며 사용자 `EES Workflow 셋업`을 복제·수정·삭제·게시하지 않는다.
- **실제 앱 확인:** 8081에서 실제 신규 계정 로그인·합성 셋업 절차 생성/분류/작업 작성/저장/검사 오류0을 확인했다. 합성 절차는 미게시 r2, JavaScript 오류0이다. 8080 사용자 절차5개 전후 상세가 동일하며 `runtime/authoring-preview/verification.json`에 결과를 보관한다. 실제 모델 호출과 사내 도구 연동은 하지 않았다.
- **이 PC에서 확인:** 저장소 루트에서 `.\.venv\Scripts\python.exe runtime/authoring-preview.py status` / `start` / `stop`. 검증 계정은 로컬 전용 `runtime/authoring-preview/test-account.json`, 로그와 실행 출처는 같은 폴더의 `logs`/`build.json`이다. 이 helper와 빌드/데이터는 ignored 로컬 검증 자료이며 배포 스크립트가 아니다. 수정 후에는 기존 소스 빌더로 새 산출물을 만들고 manifest를 대조해야 한다. 8080 새로고침만으로 새 소스가 적용되지는 않는다.
- **남은 작업 하나:** C44 부분 변경 제안·되돌리기·영속 최신 카드/패널 기록과 미저장 초안 참고의 계약 및 구현. 삭제/시스템 이동의 참조 보존 정책·월내 서수 반복도 별도 결정 필요. PR 병합·설치본 교체·사내 배포·#77/#79 착수 없음.

## 2026-10-17 · 절차 작성 화면 시각 대조·개인 PC 적용

- **기준/범위:** main `f7cfeee` 기반 `feat/figma-parity-20261017`의 미커밋 변경이다. Figma 요약·모델 미연결·이름 창을 조회하고 실제 1920×1080/1440×1080 화면을 대조했다. 이중 헤더, 패널 폭, 글꼴/본문/태그/간격/행 테두리와 모델 없는 편집의 인사 화면을 수정했다. Figma는 변경하지 않았다. [디자인 계약](mockups/ees-work/TASK.md#visual-authoring-20261017).
- **검증/실행:** UI 291 PASS, 소스/패키징 58 PASS·3 SKIP, 패키지 브라우저 6 PASS. `0.11.3+ees.14` wheel `3ec69225…`를 localhost:8080에 적용했다. 실제 관리자 화면의 요약·구조·목록·이름 창 취소, JS 오류 0, 기존 업무 5개와 키/진행 건 보존, 설치 파일 6,017개와 wheel 바이트 일치, 현재 프런트엔드 원본과 manifest 일치를 확인했다. [산출물·실패·측정 증거](../evals/v4-ui-20260930.md#visual-authoring-20261017).
- **미완료:** 전체 Figma와 시각적으로 동일한 상태가 아니다. Native 자산 전체 페이지·대화 툴바/입력창, 요약 제자리 편집·자동 질문, 변경 없는 저장 버튼 상태는 남았다. 실제 데이터/권한에 따른 내용 차이를 Figma 예시 데이터로 덮지 않는다. 모델·사내 연동·전체 CI는 미검증이다.
- **다음 개발 하나:** 요약 카드의 제자리 편집과 저장 전/후 동작 상태를 Figma에 맞추고 같은 화면 크기에서 검증한다. 사용자가 만든 `EES Workflow 셋업`은 대신 작성·게시하지 않는다.

## 2026-10-17 · 기본 절차를 일반 업무 절차로 정정·개인 PC 적용

- **기준:** 사용자가 병합한 #97을 받아 `feat/figma-parity-20261017`을 main `f7cfeee51a2b97aa61a1bbcd5b961232f6c3cd3e`로 fast-forward했다. #97은 설계 문서 변경이며 UI 구현 병합이 아니다. 기존 설치 변경·통합 전 stash·개인 데이터는 보존했다. #94/#95/#96의 미병합 변경은 가져오지 않았다.
- **범위:** 사용자 정정에 따라 별도 기본 제공 목록·보기 전용 흐름을 제거했다. 배포 산출물 점검·신규 공장 횡전개·일일 시스템 점검은 업무 절차의 일반 초안이며 직접 편집한다. 시스템 담당자의 최초 절차 진입 POST에서 한 번 등록하고 기존 이름·수정·삭제를 보존한다. Figma 목록·편집·복사·새 절차 배경·설명도 수정했다. [현재 계약과 Figma](mockups/ees-work/TASK.md#initial-procedures-20261017), [사용 안내](03-openwebui-native-agent.md#procedure-examples-20261006). 이전 전체 조사·첫 적용 증거는 [기존 대조표](mockups/ees-work/TASK.md#figma-parity-20261017)에 보존한다.
- **검증/실행:** UI 291·백엔드 69·HTTP 10·패키지 브라우저 4 PASS, 프런트엔드 소스 26 PASS/Windows symlink 1 SKIP. `0.11.3+ees.14` wheel(`2fe52157…`)로 localhost:8080을 재시작했다. 실제 관리자 로그인·일반 목록 4개(기존 1+초기 3)·편집·새로고침 중복 없음·기존 레코드/키 보존·브라우저 오류 0을 확인했다. 설치 파일 6,011개와 wheel 바이트, 현재 프런트엔드/백엔드 원본과 빌드를 대조했다. [실패·재검증·산출물 기록](../evals/v4-ui-20260930.md#initial-procedures-20261017).
- **미완료:** 전체 화면 일치나 전체 CI 통과 상태가 아니다. AI 도우미·스킬·참고 문서는 실제 화면이 전체 페이지로 열려 Figma의 가운데 대화/오른쪽 편집 구조와 다르다. C44 자동 질문·항목별 기록/되돌리기·패널 변경의 대화 기록, 목록 행의 메뉴, 요약 카드의 제자리 편집도 남았다. 옛 시작 안내를 전제로 한 전체 도움말 Native 시험도 현행 흐름으로 전환해야 한다. Figma에 화면이 없는 대화 기록·빠른 문장·공장/접근 범위는 기존 기능을 보존한다. 실제 모델·사내 연동은 미검증이다.
- **다음 개발 하나:** Native 자산 화면의 대화 보존과 오른쪽 편집 전환을 공통으로 구현한다. 사용자가 직접 만들 `EES Workflow 셋업`은 대신 생성하거나 게시하지 않는다. 전체 Figma 일치나 PR 병합 준비가 끝났다고 판단하지 않는다.

## 2026-10-17 · 개인 Windows 개발 환경 설치·실행

- **원본:** 최신 main `0f4c905ea6cb277b0704af32c40dd198fab3f959`와 [CI38858836722 성공](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38858836722)을 확인했다. #94 성능/권한, #95 CI, #96 공용 도구 후속, #97 설계 문서는 열린 Draft이며 가져오거나 병합하지 않았다. 별도 로컬 브랜치 `chore/windows-local-setup-20261017`의 미커밋 변경이다.
- **개인 PC:** 사용자 폴더 `source/repos/team-agent-poc`에 새 clone, Python3.11.13 `.venv`, 전용 Node22.16.0/npm10.9.2를 준비했다. 먼저 검증한 main CI wheel로 실행한 뒤 로컬 Windows 빌드·적용·재기동까지 확인했다. 현재 앱은 `0.11.3+ees.14`, main 기반에 Windows 빌드 보완이 있는 dirty 개발본이다. [설치·명령·저장 위치](01-openwebui-install.md#personal-windows-development).
- **검증:** 실제 Chrome의 새 관리자 가입/로그인, 업무/워크스페이스, 빈 절차 생성·단계 추가·초안 r2 저장/새로고침, 정상 Stop, 로컬 wheel 적용 후 재로그인·r2 보존, 공용 도구 목록 통과. 업무 API3개200·미인증401·연결 모델0·브라우저 오류0. 설치 파일6,011개와 wheel 바이트를 대조했다. [최초 실패·검사·해시·미확인](../evals/v4-ui-20260930.md#personal-windows-20261017).
- **경계:** localhost 전용, 새 개인 데이터/키/테스트 계정만 사용했다. 사내 설치·DB·PAT·키·Figma는 변경하지 않았다. 실제 모델 대화·Confluence/Jira/EMS 연동·실사용 권한 격리는 미검증이다. 아래 사내 적용 기록은 그대로 보존한다.
- **다음 개발 하나:** 환경 준비 결과를 기준으로 별도 작업트리에서 #96의 부분 결과 확정·공용 찾기 후속을 현재 main과 대조하고 로컬 검증 범위를 정한다. 이번 설치 작업에서 착수·병합하지 않았다.

## 2026-10-16 · 프로젝트 설계·AI 개발 진입점 정리

- **기준:** main `0f4c905`에 #93이 병합됐다. 아래 #93 통합/병합 대기 문구는 당시 기록이다. 별도 #94(성능)·#95(CI)·#96(기능 명세 시범)은 확인 시점에 Draft·미병합이며 이번 문서 정리로 반영되지 않는다.
- **변경:** [README](../README.md#project-design)에 전체 구조·핵심 데이터·문서 역할·코드/시험 경로를 연결하고, AGENTS의 시작 절과 CLAUDE의 공통 지침 연결을 정리했다. 독립 문서를 늘리지 않고 이번 기능에 필요한 원본만 읽게 한다.
- **Figma 반영:** 후속 사용자 요청으로 C52를 적용했다. 공통 부품 2종을 기존 8곳에 연결하고, B10 기능 명세·실행 상태표·README의 AI 개발 경로를 연결했다. 수정 전 B031 사본, 적용/남은 범위는 [작업 기록](mockups/ees-work/TASK.md#design-maintenance-20261016)에 있다. 기존 화면 번호·바깥 프레임과 권한/저장 정책은 유지한다.
- **다음:** 같은 [Draft PR #97](https://github.com/knadalkim-a11y/team-agent-poc/pull/97)의 변경 기록과 최종 head Checks를 검토한다. 전체 화면 전환과 기능별 UI/UX 다듬기는 해당 기능 작업 때 필요한 만큼 진행한다.
- **검증·적용:** Figma 실제 렌더·대표 인스턴스의 크기/문구와 문서 검사를 [증거](../evals/v4-ui-20260930.md#design-entrypoints-20261016)에 연결했다. Draft 유지·미병합이며 제품 코드·사내 설치·배포는 바꾸지 않았다. 실제 Claude 클라이언트의 자동 로드는 미검증이다.
- **별도 미해결:** 기존 Windows CI는 큰 Markdown의 CRLF 크기 증가로 문서 검사가 실패해도 뒤 명령이 이를 가린다. 위 증거의 로그·원인으로 CI 정리 때 확인하며 이번 Figma 작업에서 workflow를 변경하지 않았다. CI 녹색과 문서 검사 실제 결과를 구분한다.

## 2026-10-16 · #95 CI 개선의 최신 main 통합

- **범위:** 사용자 후속 검토·진행 요청에 따라 [Draft PR #95](https://github.com/knadalkim-a11y/team-agent-poc/pull/95)의 `7a8b43a`에 최신 main `0f4c905`(#93 병합본)을 merge commit으로 통합한다. CHANGELOG·STATUS 충돌은 양쪽 기록을 보존하며 CI 자료 분할/캐시와 공용 도구의 기존 검사를 함께 유지한다. 미병합 #94·#96의 변경은 포함하지 않는다.
- **근거/검증:** 기존 main CI는 최종 검사까지15분12초, 배포물 준비 포함17분11초이며 약1.39GB 전체 묶음을27개 검사에 전달했다. 관련65검사 중64PASS/실제frontend환경1SKIP, 시험ID감사·actionlint·docs/diff PASS다. 실제ees.13 고정자료의 생성·해시일치·재사용도 확인했다. [원자료·최초 실패·독립검토 보완·비교 한계](../evals/v4-ui-20260930.md#ci-delivery-efficiency-20261016). 최종 원격 판정은 CI 개선 PR의 Checks로 확인한다.
- **현재/다음:** 통합 전 head `7a8b43a`의 CI38856937514는39성공/배포물1정상제외이고 전달 자료52.6%·최종 검사시간7.1% 감소를 확인했다. 통합 뒤 정확한 head의 전체 CI는 [PR #95 본문/Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/95/checks)에서 별도로 판정한다. Draft 유지·PR 병합/사내 적용 미실행이며 실제 사내 적용본은 기존 사용자 확인 `d4f1806`이다.

아래 #91·#93 블록은 main에 보존된 당시 진행 기록이며, #93은 현재 `0f4c905`로 병합된 상태다.

## 2026-10-16 · #94 최신 main 통합·최적화 재검토

- **범위/현재:** 사용자 후속 진행 요청으로 [Draft PR #94](https://github.com/knadalkim-a11y/team-agent-poc/pull/94)의 `ffab0a2`에 #91·#93 병합 main `0f4c905ea6cb277b0704af32c40dd198fab3f959`를 merge commit으로 통합했다. 문서3개의 양쪽 기록·실패 증거를 보존하고 기존 조회 최적화·권한 회수 보완의 제품 증분은 그대로 유지했다. [통합 검토·검증](../evals/v4-ui-20260930.md#workspace-main-integration-20261016).
- **검증:** 통합본 workspace69·operations49·공용 Native35=153개 전부 통과·skip0. 권한 회수·공장별 접근·선택 상세 독립성·공용 pin/근거 보호와4개 인덱스를 포함한다. 동일 최신 main 기준의 합성5규모에서 전체 JSON과 조회 전후 DB 해시가 같고 SELECT 감소가 유지됐다. 이전 head CI38851073280의31성공/1정상제외는 보존하며 통합 최종 head의 원격 CI는 [#94 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/94/checks)에서 별도로 판정한다.
- **효과/한계:** 최신 main 합성500건×1작업의 SELECT12,564→3,536, 서버 중앙값91.010→69.587ms를 관찰했다. 과거8a4a716 대비 약25%와 이번 측정은 기준이 다르며 사내 화면 성능으로 확대하지 않는다. 실제 Native 연동·HTTP/직렬화·브라우저·인덱스 최초 생성/쓰기 비용은 미확정이다.
- **관계/다음:** 미병합 #95·#96은 포함하지 않았다. #96의 공용 `run_access` 그룹/사용자 조회 비용은 이번 동기 SQLite 읽기 재사용과 별도 경로이며 최적화 완료로 보지 않는다. 최종 통합 head CI 성공을 확인해 같은 Draft PR 검토를 마무리한다. main 직접 push·PR 병합·사내 실행/적용·Figma 변경은 하지 않는다. 사내 적용본은 앞선 사용자 확인 `d4f1806`이며 이번 적용은 미실행이다.

아래는 #91·#93 통합 당시 기록이다. #91·#93은 main0f4c905에 반영됐으며 당시 병합 지시는 #94의 병합 승인이 아니다.

## 2026-10-16 · #93 후속 기능 명세 시범 · Draft #96

- **현재 지시:** [#96 Claude 재검토](https://github.com/knadalkim-a11y/team-agent-poc/pull/96#pullrequestreview-5544185853)(head `6748300`)와 Figma C51의 작은 수정만 같은 Draft #96에서 마무리한다. 버전 문구 조사와 공용 찾기의 중복 완결성 줄을 고치고, 장애 중 관리 ST-ADMIN-8 · 부분 결과 인자 전달 · 자동 회차와 집계 규칙 · 상태 조회 비용 · 시범 중간 측정을 문서에 반영한다. 기존 관리 코드는 그대로이며 화면 다듬기는 이후 기능별 UI/UX 개선에서 다룬다.
- **#93 병합 경계:** 최초 후속 요청은 같은 PR #93의 **Draft 유지·PR 병합 금지**였다. 작업 도중 다른 세션이 원격 head `06a92e4`의 #93을 2026-10-16 15:01:03 KST에 merge commit `0f4c905ea6cb277b0704af32c40dd198fab3f959`로 병합했음을 확인했다. 이 세션은 PR을 병합하지 않았다. 명세 후속은 [Draft #96](https://github.com/knadalkim-a11y/team-agent-poc/pull/96)에 게시했으며, 이미 병합된 #93에는 같은 PR 갱신이 불가능해 승인된 GitHub 반영·Draft·CI·Claude 재검토를 #96에서 이어간다. 아래 #91 → #93 병합 승인은 당시 기록으로 보존한다.
- **원본/통합:** `ccr-5c97dda0-jb5rxv`의 `2e737ac`을 #93의 `06a92e4`에 두 부모 원격 merge commit `1aaebd44d94672c59254ae927e5a56ee23b19b4e`(같은 tree의 로컬 검증본 `631f15d`)로 합쳤다. rebase·force-push 없이 CHANGELOG 양쪽 항목을 보존했다. [기능 명세](specs/shared-tools.md), B10-1 `1369:732`·B10-2 `1368:724`·B10-5 `1372:741`와 공통-3 S1 `944:1036`을 먼저 읽고 구현한다. 조건·권한·저장/반영 시점은 명세, 배치·문구·상태 표현은 카드가 기준이다.
- **범위:** 카드의 ‘다름’, 공용 읽기 재조회, 그룹 밖 실행 단추 숨김, 실행 중/멈추지 않은 자동 회차의 버전 교체 단추 숨김, 서버·화면 문구 원본 통합을 반영한다. 사람이 확정한 부분 결과의 다음 작업·회차 종료와 공용 찾기 0건/0개 선택 완료를 구현하며, 확정 전 부분 결과 차단과 이전 방식 0개 완료 거부는 유지한다. 게시자의 PAT(ST-OPEN-4)는 바꾸지 않는다.
- **검증/다음 작업:** C51 관련 로컬 UI103개 · Native 문구 일치1개를 통과했다. [이번 구현·최초 실패·C51 검증](../evals/v4-ui-20260930.md#shared-tools-spec-20261016)은 원본을 보존하며, 기록 커밋 이후 **최종 head CI·버전 바뀜/0건 2장 판정은 [#96 본문/Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/96/checks)가 원본**이다. 이전 head의 성공으로 대신하지 않는다. 다음은 같은 Draft #96의 최종 CI·2장 확인 뒤 댓글 하나로 Claude 재검토를 요청하는 것이다.
- **금지/미확인:** main 직접 push·PR 병합·사내 실행/적용·Figma 수정·#77/#79 착수·사내 도구 삭제/재등록/덮어쓰기·TLS 검증 해제·공용 PAT를 하지 않는다. 사내 Confluence 설치 원본·주소·허용 공간·암호화·팀원 PAT와 실제 적용은 미확인이다.

아래는 이번 명세 시범 지시 이전의 승인·구현·실패·검증 기록이다. #93의 현재 범위와 병합 여부는 위 항목을 따른다.

## 2026-10-16 · #91 병합 완료·#93 main 통합

- **승인/순서:** 사용자가 두 PR의 병합까지 요청했다. #91 최종 CI 성공 → merge commit 병합 → #93에 main 통합 → 최종 CI 성공 → #93 merge commit 병합 순서다. 아래 Draft/병합 보류 문구는 당시 기록이다.
- **현재:** #91 head7dd9132의 최종 CI38850315905가31성공/1정상제외로 끝나 merge commit `ff0641628860c78f13e8f33ab60eee8cd3491a4d`로 병합했다. 이 main을 #93에 merge 통합하고 문서3개 충돌의 양쪽 기록·증거를 보존했다. #93의 추가 자동 검토3건도 게시 필수 인자·자료형, 선택 범위 pin, 수동 연결 보존으로 보완했다. [첫 실패·회귀](../evals/v4-ui-20260930.md#shared-tools-merge-review-20261016).
- **통합 첫 CI/추가 보완:** ba6aa64의 Native64개 중62PASS/2FAIL은 C45로 달라진 출발 칸을 기존 시험이 같은 칸으로 취급한 문제다. 원본 프레임을 보존하고 실제 목적지/이전 칸0 감시를 연결했다. 추가 자동 검토3건(제외 작업 pin·목록 결과 호환·장애 중 제한적 관리)도 회귀와 함께 보완했다. 공용 Native/workspace93PASS·Node355PASS. [실패·재검 조건](../evals/v4-ui-20260930.md#shared-tools-merge-review-20261016).
- **검증:** #93 로컬 Python111PASS/이전 source fixture 미준비1SKIP. main 통합 뒤 전체 Node354PASS·Python controller1PASS·문서/신규 diff 검사 통과. 실제 브라우저/Windows는 최종 통합 CI로 확인한다.
- **추가 통합 CI:** b51ad90의 CI38853958726은31성공/PR배포1정상제외, 실제 Native64PASS로 첫 통합 CI의2실패가 해소됐다. main의 #91 병합 CI38852021564도 성공했다. 후속 자동 검토의 execution 인자 검사·선택 결과 범위·다른 시스템 이동을 보완하고 새 head를 다시 검사한다.
- **942a6f9 후속:** 자동 검토의 종료 회차 과거 근거·계획/시작 버전 경계·예약 사용처 표시·발견 장애 격리4건을 보완한다. 해당 CI native-work의1실패는 제품 접속 전 Chrome handshake30초 시간 초과이며 원본 JSON을 보존했다. 나머지11시험은 통과했다. 새 보완 head의 실제 Native 검사로 재확인한다.
- **다음 작업:** 통합 #93 최종 head CI 성공 후 merge commit 병합과 최종 main CI 확인. 사내 적용·설치 확인은 미실행이며 설치 원본·주소·허용 공간·암호화·팀원 PAT는 미확인이다. Figma 수정·#77/#79·main 직접 push는 하지 않는다.

## 2026-10-16 · 공용 Confluence 도구 #93 재검토 반영

- **기준/범위:** 최신 main `8a4a716`(#90 병합 포함), #92와 B10-1/2/5. [현재 계약](mockups/ees-work/TASK.md#shared-tools-phase1-20261015). 기존 계약은 보존하고 기본 제공 조회2개를 공용으로 확인·사용한다.
- **병합 순서:** 열린 #91(Native 복귀 선택)과 launcher/view, 시험, TASK/STATUS/CHANGELOG/evals가 겹친다. #91 검토·병합 뒤 이 PR에 최신 main을 통합하고 양쪽 행동/기록을 보존한다. 이번 작업은 병합하지 않는다. #90은 이미 main에 반영되어 별도 병합 대기가 없다.
- **현재 검증:** head4778b97의 Claude 재검토3건과 확인창 보완을 같은 Draft #93에서 반영했다. 이전 방식→공용의 인자 정리, 게시 시 입력 키/목록 연결 거부, 관리자 운영 안내와 변경 요약·그룹/담당 분리다. 로컬 공용 Native24개(22개+호환 경로2개), 기존 operations48개, Node196개가 통과했다. [첫 실패·새 회귀·실제 화면/CI](../evals/v4-ui-20260930.md#shared-tools-rereview-20261016). 이전7건의 최종 CI38834234451 성공은 당시 증거이며 새 head 결과는 [Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/93/checks)가 원본이다.
- **다음 작업:** 최종 head CI 성공 후 Claude 재검토. 항목별 답변/요청은 PR 댓글 하나로 남긴다. Draft 유지·병합 없음. 리뷰 마지막 묶음은1단계-2로 넘기며 #91 통합 순서를 유지한다.
- **사내:** Confluence 설치 원본·주소·허용 공간·개인 설정 암호화·팀원 PAT 저장은 미확인. 사내 실행/적용·Figma 수정·#77/#79 착수 없음.

## 2026-10-16 · #91 → #93 병합 승인·남은 리뷰 보완

- **승인·순서:** 사용자가 두 PR의 병합까지 승인했다. 기존 Draft 유지·병합 금지는 이 요청으로 대체하며, #91의 최종 CI 성공 후 merge commit 병합 → 최신 main을 #93에 merge 통합 → 그 head CI 성공 후 #93 병합 → main CI 확인 순서다. main 직접 push·rebase·force-push는 하지 않는다.
- **#91 보완:** 병합 전 자동 리뷰2건을 실제 controller에서 재현했다(새4시험 FAIL). 다른 목적지의 캐시 내용은 workspace·operations의 새 접근 확인이 끝날 때까지 가리고, 경로 이동 실패는 Native 선택·작성값을 유지하며 재시도 안내를 표시한다. 새 선택 우선과 이전 계정의 늦은 실패 무시도 검사했다. 조회 실패 시에는 preview와 캐시를 함께 폐기해 오류/재시도 화면으로 복구한다. 전체 Node345개·Python controller 진입점1개 PASS. [첫 실패·보완·CI](../evals/v4-ui-20260930.md#native-return-selection-evidence-20261015).
- **#93 상태:** Claude 2차 재검토에서 이번1단계-1의 남은 지적 없음. 검토 head는 `e0b163a`이며 그 CI는31success/1정상skip이다. #91 뒤 main 통합과 새 head CI를 별도로 확인한다. #90과 양 PR의 기록·증거를 보존한다.
- **다음 작업 하나:** 보완 #91 CI 성공을 확인하고 승인된 순서로 두 PR 병합과 최종 main CI 확인을 마친다. 사내 실행/적용·Figma 수정·#77/#79는 범위 밖이며 사내 적용본은 사용자 확인 `d4f1806`이다.

아래는 각 단계 당시의 병합·적용 준비 기록이며 현재 설치 상태와 이번 작업 범위는 위 항목을 따른다.

## 2026-10-15 · #88 병합 완료·#89에 main 통합

- **현재 원본:** #88 head `584e3c91a49402d81d449de869e32578deee4fcb`의 [CI 두 번째 시도](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38655286601/attempts/2)는31개 성공·배포파일1개 정상 제외다. 사용자 승인에 따라 merge commit `4da2d1c2cb18320778c392892c252388070891dd`로 병합하고 이 main을 #89에 통합했다. 문서5개 충돌에서 양쪽 기록을 모두 보존하고 CHANGELOG는 날짜별로 합쳤다.
- **검증/미확인:** Windows CI에서 실제 길이 값이 채워진 적용 블록2,491자와 PowerShell 구문을 통과했다. 첫 CI의 Chrome 준비 timeout과 실패 작업1회 재실행은 [기존 평가](../evals/v4-ui-20260930.md#apply-block-length-20261015)에 보존한다. 재실행 성공은 Chrome 지연의 근본원인 해결이나 사내 적용 성공이 아니다.
- **다음 작업 하나:** 통합 #89의 [최종 head CI](https://github.com/knadalkim-a11y/team-agent-poc/pull/89/checks) 성공 후 merge commit으로 병합하고, 최종 main CI 성공과 실제 바깥 Actions ZIP 네 값을 대조해 단일 블록을 Claude 검토용으로 전달한다. 실제 사내 설치는42cc756이고 사내 실행·Figma 수정·#77/#79·main 직접 push는 하지 않는다.

- **통합 CI 첫 실패:** 공식 Native baseline Chrome 시작 응답이30초 안에 오지 않아 EES 코드 검증 전에 멈췄다. [최초 실패·범위·1회 재검 조건](../evals/v4-ui-20260930.md#apply-block-length-20261015)을 보존했고 제품·검사·시간 제한 변경 없이 기록만 추가한 새 head에서 확인한다.

- **별도 Windows 미확인:** 새 실행은 Chrome 비교를 통과했으나 Windows 합성 launcher의 Node 시작 표식 미관측/10초 timeout1건으로 멈췄다. 같은 모듈33개와 전체28개 job은 통과했다. 원래 실패와 로컬 단일PASS·새 head1회 재검 조건을 같은 평가에 보존하며 검사 기준은 유지한다.

아래는 각 단계 당시의 기록이다. 미병합/Draft 유지 지시는 위 승인과 순서로 대체한다.

## 2026-10-15 · #88·#89 순서 병합 승인과 적용 블록 길이 보완

- **승인:** 사용자가 Claude 재검토 후 #88 → main을 #89에 통합 → 최종 head CI 성공 후 #89 병합을 승인했다. 저장소 관례인 merge commit을 사용한다. 아래 병합 보류 문구는 당시 기록이며 이번 승인으로 대체한다.
- **보완/검증:** #88 적용 안내의 Write-Host를 줄이고 Windows CI가 40자리 SHA·64자리 ZIP 해시·10자리 바이트 수·실제 형식 Actions 링크를 채운 뒤 길이와 구문을 검사하도록 했다. 같은 값으로 이전 블록은 LF 2,522자, 수정본은 LF 2,456자/CRLF 2,491자다. 문서 검사·diff 검사를 통과했고 원격 Windows 검사는 [#88 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/88/checks)에서 확인한다. [검증 근거](../evals/v4-ui-20260930.md#apply-block-length-20261015).
- **다음 작업 하나:** #88 최종 CI 확인 후 지정 순서로 병합하고 문서 5개의 양쪽 기록을 보존한다. 최종 main CI 성공 뒤 바깥 Actions ZIP의 실제 SHA256·정확한 바이트·링크와 전체 main SHA를 채운 한 블록을 Claude 대조용으로 전달한다. 사내 설치는 사용자 확인42cc756이며 새 적용은 미실행이다. main 직접 push·사내 실행·Figma 수정·#77/#79 착수는 하지 않는다.

## 2026-10-15 · #88 검토 보완: 처음 범위의 받는 중·CI·선택 목록

- **기준/범위:** 미병합 R11 head `1fd7f9a5f152e9e624370ddf27dfacdcfc1c63ce`의 Claude 검토4건을 같은 PR에서 수정했다. 사용자 확인 사내 설치는42cc756이다. [현재 계약](mockups/ees-work/TASK.md#scope-review-20261015).
- **변경:** 새 범위는 메뉴 틀을 유지하며 바뀌는 목록만 받는 중으로 표시하고 응답 전 없음/0개를 막는다. 받은 범위의 공용 목록·도구·예약은 즉시 보존한다. system_id 없는 선택 목록의 타 시스템 공장 노출과 검색0개 안내를 고쳤다.42cc756 상시 음성 대조와 actions:read를 제거하고 과거 증거는 보존했다.
- **검증:** 현재 head의 새 controller/renderer4개와 권한 목록3개 실패를 먼저 확인했다. 수정 뒤 고정Node268개·소스24개·workspace63개 통과. 독립 검토에서 발견한 캐시 operations 소실도 실패 재현 뒤 보완했다. 실제 첫 범위 프레임·브라우저·Windows는 새 head CI로 판정하며 [기존 평가](../evals/v4-ui-20260930.md#scope-review-evidence-20261015)에 최초 실패와 경계를 남긴다.
- **다음 작업 하나:** 최종 head CI를 확인해 #88/#89 재검토를 요청한다. 적용 블록에 Work 설정 확인을 직접 넣었고 회신 둘째 줄에 work_tool을 추가했다. 병합·main 직접 push·사내 실행·Figma 수정·#77/#79는 하지 않는다.

아래는10-14 당시 기록이며 범위 변경의 자리표시 합격 기준은 위 정정을 따른다.

## 2026-10-14 · 2-1 후속: 이동 상태·A2 범위·R11 메뉴/막대

- **실제 사내 상태:** 사용자가 main `42cc7568eb8477013abcf0a042617dd9e3279db2` 적용 완료를 확인했다. 워크스페이스의 스킬·지침 → 업무 절차 이동 때 ‘불러오는 중…’과 깜빡임이 남는다고 보고했다. 아래 `4e89341` 적용 및 #86/#87 준비 기록은 당시 이력이며 현재 설치 상태를 대신하지 않는다.
- **범위와 구현:** 최신 main 위 후속 PR 하나에서 경로 변경 중 마지막 업무 상태를 유지하고 Native 권한을 별도로 관리한다. 처음 여는 대상만 자리표시를 사용하고, 같은 대상의 새 응답은 달라진 부분을 갱신해 펼침·스크롤·미저장 글을 유지한다. 계정 변경·권한 거부와 늦은 응답 보호는 유지한다. [#84 1장과 작업 계약](mockups/ees-work/TASK.md#navigation-state-20261014).
- **첫 CI와 보완:** [Draft PR #88](https://github.com/knadalkim-a11y/team-agent-poc/pull/88) 첫 head `b4f370b`의 [CI38515563587](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38515563587)에서 기준42cc756은 로딩1082프레임으로 같은 시험에 실패했고, 후보는23이동 구간2644감시 프레임에서 메뉴/패널 로딩0건이었다. Native-compose57개와 신규 이동/보존3개가 통과했으나 기존 비공개 근거 제거3개·전체 제품의 갱신 대기1개는 실패했다. 근거 조회 실패/의미상 접근 거부를 캐시 유지와 분리하고, 제품 시험은 알려진 진행 건 표시를 기다리도록 보완했다. 최초 실패와 수치는 [이번 평가](../evals/v4-ui-20260930.md#navigation-state-evidence-20261014)에 보존한다.
- **추가 전 검증:** head `4470049977c464fcafc0b96638b0a2b3a0bccd44`의 [CI38518902180](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38518902180)은31success/정상 PR 조건부1skip이다. `f719f784`의 Chrome 준비 실패도 재검 통과했으며 [처음 실패·재검 근거](../evals/v4-ui-20260930.md#navigation-state-ci-handshake-20261014)는 보존한다. 이 결과를 아래 새 드롭다운의 검증 결과로 대신하지 않는다.
- **사용자 추가 범위:** 같은 PR #88에 Figma 공통-1 A2 `832:8953`/C41의 칸 아래 드롭다운을 구현했다. 업무 공장·시스템과 워크스페이스 관리 시스템, 검색·선택 체크·권한 없음·키보드/포커스·내부 스크롤·화면 변경 닫기를 포함한다. 범위 변경 중 로딩0건과 입력 보존을 실제 Native 시험에 추가했으며 [이번 구현·검증 증거](../evals/v4-ui-20260930.md#scope-dropdown-evidence-20261014)에서 판정한다.
- **Figma와 전달:** 2026-10-14부터 관리 `897:760`의 기능 지도 `1288:2`와 공통-1 페이지 `1284:3046`를 기준으로 찾는다. 기존 노드 ID와 과거 `832:131` 기록은 보존한다. [병합 뒤 적용 템플릿](03-openwebui-native-agent.md#source-phase2-route-cache-zip-20261014)은 브라우저 열기·최대15분 ZIP 대기·크기/해시 검사·기존 Upgrade를 한 블록으로 묶고 예상 설치 SHA를 `42cc756`으로 고정한다. 최종 main·ZIP 확정 전에는 실행할 수 없다.
- **A2 포함 검증:** head `fe936ba`의 [CI38526788935](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38526788935)는31성공/정상1skip이다. 세 드롭다운 실제 동작과 A2 화면 대조를 완료했고 범위 변경 감시1,171프레임·Native/대화 이동 감시2,646프레임에서 메뉴·패널 로딩0건이었다. 기준42cc756의 같은 시험은1,080프레임으로 기대한 실패였다. 최초 시험 입력/아이콘 가정 오류와 보정, 화면3장·원자료는 위 평가 기록에 보존한다. 이후 문서·증거 전용 최종 head의 CI는 PR Checks에서 별도로 확인한다.
- **실제 목록의 추가 보완:** 앞 CI는 권한 없음 표시를 합성 응답으로만 확인했다. production API에는 해당 항목이 없어 A2 요청의 실제 경로가 빠졌음을 발견해 최소 선택 metadata를 별도 제공하도록 보완했다. 상세·설정·조회·명령 권한은 유지하고 factory-only 사용자의 다른 허용 시스템 전환도 공장 해제 후 권한으로 계산한다. workspace62개/Node92개가 통과했으며 제한 사용자·실제 권한 HTTP 응답을 쓰는 브라우저 시험으로 교체했다. 이전31성공을 새 보완의 CI로 대신하지 않는다.
- **추가 직전 완료 확인:** #88의 실제 권한 목록 보완 head `ae788f4985a51914551aa75f5691d06625baf83e`의 [CI38531260469](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38531260469)와 별도 Work 도구 원본 갱신 #89 head `bdc8a4405a79e8befaccf3382b50a9dad59ef77b`의 [CI38530487433](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38530487433)가 completed/success임을 재확인했다. 두 PR은 미병합이며 이 결과를 아래 R11 추가의 CI로 사용하지 않는다.
- **R11 추가 구현:** 사용자 2026-10-14 C42 요청에 따라 같은 #88에서 ‘워크플로우 찾기’ 메뉴/대화상자와 위쪽 막대의 ‘참고’·‘일반 대화’를 제거했다. 닫힌 패널에만 글자 있는 열기 단추를 표시하고 열기/닫기 초점을 옮긴다. 패널 가시성만 바꿔 새 절차 시작·실제 대화 참고·작성값을 보존한다. [계약과 2-3 착수 조건](mockups/ees-work/TASK.md#r11-toolbar-20261014), [첫 실패·검증·미확인](../evals/v4-ui-20260930.md#r11-toolbar-evidence-20261014)을 연결한다. 새 R11의 고정 소스 빌드·소스24개/Node167개는 통과했다. 로컬 Chrome 시작은 socket EPERM으로 막혀 실제 브라우저와 최종 head CI는 새 PR Checks에서 판정하며 앞 CI 성공과 구분한다.
- **다음 작업 하나:** R11을 포함한 #88의 실제 화면/포커스·보존 검사와 최종 head CI를 마치고 검토를 요청한다. 2-3은 #88 병합 뒤 최신 main에서 시작하며 #89와 별개다. 두 PR 병합 뒤 최종 main/ZIP의 사내 적용 안내는 한 번으로 합친다. 현재 병합·main 직접 push·사내 실행·Figma 수정·#77/#79 착수는 하지 않는다.

아래는 후속 요청 이전의 준비·검토 기록이다.
## 2026-10-15 · #89 검토 보완: 알려진 원본 줄바꿈과 안내

- **기준:** 미병합 head `bdc8a4405a79e8befaccf3382b50a9dad59ef77b`의 Claude 검토2건을 같은 PR에서 고쳤다. 사내 설치는 사용자 확인42cc756이며 등록본 버전/사내 해결은 미확인이다.
- **변경:** 알려진 원본 인식에만 CRLF/CR→LF·양끝 공백 정규화를 적용했다. ready·출하 검증·갱신·백업·복원은 정확 바이트를 유지한다. 불일치 창은 쉬운 설명·해시8자리·개발 담당에게 알릴 행동을 표시한다. [현재 계약](mockups/ees-work/TASK.md#work-tool-review-20261015).
- **검증:** 변경 전 실제 Native의11개 변형이 모두 blocked_existing으로 실패함을 먼저 확인했다. 수정 뒤 실제 Native96개·guard19개·Git/Black24형태 재생성·고정Node UI70개가 통과했다. 정확한 결과와 최초 실패는 [기존 평가 기록](../evals/v4-ui-20260930.md#work-tool-review-evidence-20261015), 최신 head 전체 CI는 [PR Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/89/checks)에서 구분한다.
- **전달/다음:**42cc756과 Work 출하 파일이 같으므로 update_needed 없이도 적용 뒤 설정 확인을 직접 안내한다. 둘째 회신 줄 work_tool 결과를 포함하며 두 PR은 검토·병합 후 한 번 적용한다. 현재 PR의 최종 CI를 확인해 재검토를 요청하며 병합·사내 실행은 하지 않는다.

아래는 10-14 당시 구현·검증 이력이며, 알려진 원본 인식 조건은 위 보완을 따른다.

## 2026-10-14 · 2-2 후속: Work 도구 원본 갱신

- **사내 상태:** 사용자 확인 설치는 main `42cc7568eb8477013abcf0a042617dd9e3279db2`다. 새 절차 질문의 업무 도우미 사용 불가와 설정의 `blocked_existing`이 보고됐다. 등록본의 정확한 해시/버전은 미확인이다.
- **수정:** main 기준 별도 PR에서 Git 이력의 제품 원본·고정 편집기 정렬본을 정확한 해시로 확인하고 알려진 이전 원본만 같은 ID로 바꾼다. 명시적 확인·예상 token·비공개 백업/복원으로 이름·소유자·읽기 권한·설정을 보존한다. 모르는 원본은 지원 형태와 다름으로 표시하며 쓰지 않는다. [사용 절차](03-openwebui-native-agent.md#work-tool-source-update-20261014).
- **검증:** 제품 수정 전에 main에10-02 원본과 정렬본을 등록한 두 시험이 `blocked_existing != update_available`로 실패함을 확인했다. 수정본의 실제 Native79개·기존 guard16개·UI Node69개가 통과했다. 갱신·도우미 available·직접 질문 Work 도구 연결, 설정 보존·복원·모르는 원본·권한·동시 변경·프로그램 교체를 포함한다. 배포/공통 요약80개 중77PASS/PowerShell3SKIP이며 Windows는 새 head CI로 판정한다. 최초 복원 실패와 독립 검토의 완료기록 저장 실패 보완은 [이번 평가](../evals/v4-ui-20260930.md#work-tool-update-evidence-20261014)에 보존한다. 최종 head CI 성공과 사내 해결은 구분한다.
- **전달:** 성공 적용 뒤 출하 Work 도구 파일이 달라지면 설정 확인 안내를 추가했다. #88의 이동 상태/A2 드롭다운과 별도 검토하며 둘 다 병합한 뒤 예상 설치42cc756에서 한 번만 사내 적용하도록 안내한다. 원인별 전체 알림은2-3으로 남긴다.
- **첫 CI 보완:** [Draft PR #89](https://github.com/knadalkim-a11y/team-agent-poc/pull/89)의 첫 CI는 Windows 출하 원본 줄바꿈/갱신 뒤 백업 판정과 기존 계정 전환의 단계 추가 대기로 실패했다. 제품 원본·fixture의 LF를 고정하고 미확인 출하 바이트는 쓰기 전에 막으며 영향12개 Native가 통과했다. 계정 화면 실패의 근본원인은 미확정이라 읽기 전용 클릭 진단만 추가해 새 head에서 재검한다. 최초 실패·재검 범위는 [같은 평가](../evals/v4-ui-20260930.md#work-tool-update-evidence-20261014)에 남기고 최종 판정은 [#89 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/89/checks)에서 확인한다.
- **보완 코드 검증:** head `848c769`의 [CI38525473317](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38525473317)은31성공/정상1skip이다. Linux·Windows 각81개 Native 및 Windows upgrade59개가 통과했고 계정 전환11개도 통과했다. 최초 계정 클릭 실패의 근본원인은 미확정이며 재발 시 보존한 이벤트 진단으로 확인한다. 이후 문서·증거 전용 최종 커밋의 전체 CI는 PR Checks에서 별도로 확인한다.
- **최종 기록 뒤 별도 실패:** `91f1db0`의 CI는 이번 갱신·복원 검사에 통과했지만 기존 Windows venv 종료 시험이 예상 밖 후손 관계를 감지해 안전 중단했다. 실제 후손의 원인은 미확정이며 제품·검사 기준·제한시간을 유지하고 실패 시 최소 프로세스 식별 진단만 추가해 새 head에서 확인한다. 최초 실패/재검 근거는 위 평가 기록에 보존한다.
- **다음 작업 하나:** 두 PR의 최종 head CI를 확인해 검토를 요청한다. 검토·병합 뒤 최종 main/ZIP을 확정해 사내 적용 안내를 한 번만 전달한다. 병합·main 직접 push·사내 실행·Figma 수정·#77/#79 착수는 하지 않는다.

아래는 이번 Work 도구 후속 요청 이전의 기록이다.

## 2026-10-14 · #86 병합·#87 검토 3건 반영과 통합 적용 준비

- **승인과 원본:** 사용자가 #86 병합 및 #87 화면 수정3건의 최종 head CI 성공 후 순서대로 병합을 승인했다. #86 head `ac2ec0120adb6eb99da833f818977fc524eee112`의 CI 성공과 Claude 검토를 재확인해 main `f872fc9dfc7de10ca087935d6e64256296c95e7d`로 병합했다. #87은 같은 브랜치를 유지하고 base를 main으로 바꿨다. [최신 계약](mockups/ees-work/TASK.md#helper-chat-review-20261014).
- **수정:** 도우미 답의 특별 라벨을 제거해 모든 답에 Native 모델명·모양을 사용한다. 기존 대화에는 입력창 바로 위 질문3개만, 빈 대화에는 전체 안내를 유지한다. 사용 불가 안내를 질문 바로 위 C36 아이콘·문장으로 옮기고 관리자 확인 요청 fallback을 적용했다. 전송·참고·작성 중 글/첨부·권한 경계는 보존한다.
- **검증:** 고정 upstream에 최종 patch 적용과 전체 소스 SHA 일치를 확인했고 소스22개 검사를 통과했다. 실제 컴파일 UI의1366×768 높이120px 상한·응답 이름/모양 동일성·C36 위치/폭과 기존 전송/보존 조건을 기존 필수 브라우저 시험에 추가했다. 최신 빌드/실행 및 실패·미실행의 구분은 [이번 평가](../evals/v4-ui-20260930.md#helper-chat-review-evidence-20261014), 최종 head CI는 [#87 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/87/checks)에서 판정한다.
- **다음 작업 하나:** #87 최종 head CI 성공 후 병합하고 최종 main CI·프로그램 ZIP·바깥 SHA256을 확인해 [브라우저 ZIP 안내](03-openwebui-native-agent.md#source-phase2-local-zip-20261014) 하나를 확정한다. 현재 사내 설치 원본은 사용자 보고 `4e89341a4db453bab16fc91baa0af7884b92fef9`다. 결과는1~2줄·`menu_flash`/`helper_chat` 포함이며 실제 적용/모델 품질은 미확인이다. main 직접 push·사내 실행·Figma 수정·#77/#79는 수행하지 않는다.

아래는 승인 전 단계의 당시 기록이다. Draft 유지·병합 보류는 위2026-10-14 승인으로 대체됐다.

## 2026-10-13 · 사내 `.14` 적용 보고와 #83 2단계 착수

- **사내 적용 원본:** 사용자가 2026-10-13 브라우저 ZIP으로 main `4e89341a4db453bab16fc91baa0af7884b92fef9`를 적용하고 `result=ok / stage=complete / running=true / commit=4e89341`을 보고했다. 실행 결과는 사용자 보고이며 첫 로딩(새로고침·주소 직접 열기)의 깜빡임 여부와 기존 대화·업무 화면 정상 여부는 미기입/미확인이다.
- **사용자 관측:** 메뉴·패널 이동 때 Native 화면이 먼저 보이고 EES 화면이 덮는다. 새 절차의 ‘업무 도우미’는 오른쪽 상자이고 질문 버튼은 입력창에 글만 넣는다. 당시 적용본의 전역 MutationObserver·Native DOM 교체와 입력만 채우는 경로가 이 관측에 부합한다. 최초 로딩 가림만으로 이동 중 덮어 그리기가 해결됐다고 하지 않는다. [적용·관측·검증 경계](../evals/v4-ui-20260930.md#source-phase2-internal-20261013).
- **승인된 범위:** 최신 main 위 2-1 Draft PR에서 소스가 처음부터 세 영역·왼쪽 메뉴·이동을 소유하도록 전환한다. 완료한 2-1을 기반으로 별도 2-2 Draft PR에서 업무 도우미 안내·질문을 대화 안에 넣고 즉시 전송·문맥 참고·작성 중 글/첨부 보존을 구현한다. 두 PR의 의존 관계를 명시하고 검토 변경을 분리한다. [착수 계약](mockups/ees-work/TASK.md#source-phase2-20261013).
- **2-1 구현·검증:** 소스 컴포넌트가 세 영역·왼쪽 메뉴·라우트를 소유하고 런처의 전역 감시/가로채기·Native DOM 변경·4초 가림을 제거했다. Figma C39 이후 지정5화면, `EES.*` i18n/한국어·영어 fallback과1MiB 목록 보호를 대조했다. 최종 로컬 build3의 이동/레이아웃6개·보존20개가 통과했고21구간145프레임에서 원래 메뉴 노출·소스 틀 소실0건이다. 실제 사내 인증/모델 시험과 구분하며, 최초 실패·한계·남는 임시 렌더는 [검증 기록](../evals/v4-ui-20260930.md#source-phase2-internal-20261013)과 [이전 표](mockups/ees-work/TASK.md#source-phase2-20261013)에 남긴다. 원격 최종 head 결과는 아래 CI 후 보완과 구분해 기록한다.
- **2-1 CI 후 보완:** [Draft PR #86](https://github.com/knadalkim-a11y/team-agent-poc/pull/86)을 게시했다. 두 번째 CI에서 발견한 다른 탭 계정 변경의 Native 재초기화 누락과 기존 DOM 검사 이전을 보완했다. 새 build4의 계정/작성5개·이동/레이아웃6개가 통과했고21구간154프레임에서 원래 메뉴 노출0이었다. Windows의 누적 시간 초과는 같은 검사를 필수4+1개로 나눠 재검한다. 최초 실패·최신 원자료는 [같은 평가 기록](../evals/v4-ui-20260930.md#source-phase2-internal-20261013)에 보존하며 최종 head CI는 PR Checks에서 판정한다. 세 번째 CI의 구형 과거 참고 선택자를 소스 slot으로 고쳤으며 최종 head `ac2ec0120adb6eb99da833f818977fc524eee112`의 [CI38372381486](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38372381486)는 completed/success다.
- **2-2 검토 준비:** #86을 기반으로 오른쪽 도우미 상자/입력 채우기를 제거하고, 소스 Chat 안 안내·질문과 같은 대화의 답변을 연결했다. 명시적 도우미 요청만 읽기 전용 안내로 제한하고 일반 직접 전송의 문맥 참고·첨부·기능은 보존한다. 등록 자산을 바꾸거나 자동 초안/저장/실행을 추가하지 않는다. [화면·전송 계약](mockups/ees-work/TASK.md#helper-chat-phase2-20261013)에 따라 별도 Draft PR로 검토한다. 고정 소스 build2의 실제 브라우저30개 중 최초29PASS/참고 상태 대기식1FAIL을 기록했고, 올바른 빈 화면 조건으로 고친 해당1개가 통과했다. 영어 질문·첫 안내/작성창·첨부·중복/거절 보존과 Figma 치수를 확인했다. 소스22PASS/Node286PASS이며 [최초 실패·원자료·검증 한계](../evals/v4-ui-20260930.md#helper-chat-phase2-evidence-20261013)를 보존한다. [Draft PR #87](https://github.com/knadalkim-a11y/team-agent-poc/pull/87)의 두 번째 CI는 helper 진입 시험에서 현재 절차 편집기→목록 이동을 빠뜨려 전송 전에 실패했다. 목록 클릭만 추가했고 같은 build2 실제 UI의 질문 전송·업무 이동·대화 reload 단일1PASS를 확인했다. 세 번째 [CI38375410891](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38375410891)의 실제 Native/helper·provider/ACL 게이트는 통과했으나 Windows contracts의 기존 fast 자식 실행이10초 제한으로 실패했다. 동일 시험의 직전 CI2/PR86 성공과 원인 미확정을 같은 평가 기록에 보존하고, 제품·제한·검증식은 유지한 채 자식 단계 표식만 추가했다. Linux 단일1PASS를 확인했으며 기록·진단을 포함한 새 head에서 한 번 재검한다.
- **다음 작업 하나:** 두 Draft PR의 최종 head CI와 실제 화면·보존 검증을 마치고 순서대로 검토를 요청한다. 두 PR 모두 병합·Draft 해제·main 직접 push·사내 실행·Figma 수정은 하지 않는다. #77·#79와 말로 초안 만들기(B1-2a)는 범위 밖이다. 적용 안내는 사용자가 두 PR을 병합한 뒤 최종 main CI·ZIP을 기준으로 하나만 준비하며 결과 항목에 `menu_flash`·`helper_chat`을 포함한다.

아래 #85 작업은 병합·사내 적용 보고 이전의 기록이다. 현재 승인 범위는 위 2단계 지시를 따른다.

## 2026-10-13 · #85 검토 반영과 #83 설계안 보완

- **기준과 범위:** main `1c6ddaa04f05b2eea02bbf15155b8602f1e4a1a8`에서 `feat/source-frontend-phase1-20261013`을 시작했다. [#83 설계·착수 댓글](https://github.com/knadalkim-a11y/team-agent-poc/issues/83#issuecomment-6133363909)과 [8문항 설계안](mockups/ees-work/TASK.md#source-frontend-phase1-20261013)을 게시했다. 이번 구현은 고정 0.11.3 소스/CI 빌드·컴파일 후 바이트 패치 제거·초기 깜빡임/안내 문구·CI ZIP 전달/복구까지다. 2단계 화면 이전과 #77·#79는 미구현이며 설계 검토·확정 뒤 별도로 시작한다.
- **사내 상태:** #83에서 사용자가 PR #82 병합본 적용 뒤 Native 화면 깜빡임과 새 절차 안내의 문제를 보고했다. 이는 사용자 관찰이며 모든 로그인·첨부·팀원 완료 항목의 수락 결과로 확대하지 않는다. 새 `.14`는 아직 사내 적용하지 않았다. 아래 10-12의 결과 대기/착수 보류는 당시 기록이고 현재 작업 허가는 이번 #83 요청을 따른다.
- **검토 반영:** 사용자가 [#85 검토](https://github.com/knadalkim-a11y/team-agent-poc/pull/85#issuecomment-6134606371)의 보완과 최종 head CI 성공 후 병합을 승인했다. 화면 제품명은 `EES Workflow`로 표시하고 코드 식별자·경로·등록 자산·과거 기록은 유지한다. 새 절차 안내의 세 번째 질문을 `빈 절차로 시작하면 무엇부터 정하나요?`로 바꾸고, 토큰이 없으면 처음부터 [브라우저 ZIP 안내](03-openwebui-native-agent.md#source-frontend-local-zip-20261013)를 따른다. [#83 검토](https://github.com/knadalkim-a11y/team-agent-poc/issues/83#issuecomment-6134603956)의 네 가지 보완은 설계안에 반영하며 2단계 구현은 별도 지시를 기다린다.
- **검증:** 보완 전 head `101479e282f3a8305a908168839b611dea17f369`의 [CI38318606922](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38318606922)는27개 성공·main 전용1개 skip이었다. 표시명 변경 뒤 새 소스 빌드·실제 Native 표시/질문 입력은 통과했다. 보완 head4fa89ced CI는 Windows 설치 검사가 전체10분 제한에 걸려 미완료였고, 기존 실제 wheel1개를 양 OS 별도 필수 묶음으로 분리한다. 전체71개 설치/복구·검증식·10분 제한은 유지하며 새 head의 전체 CI를 판정한다. 최초 실패·로컬 결과·검증 한계는 [같은 기록](../evals/v4-ui-20260930.md#source-frontend-phase1-review-20261013)에 보존하고 최종 head와 병합 main CI는 [PR #85](https://github.com/knadalkim-a11y/team-agent-poc/pull/85)의 본문/Checks에서 확정한다.
- **다음 작업 하나:** 최종 head CI 성공 후 승인된 PR #85를 병합하고, 병합 main CI 성공과 해당 프로그램 ZIP을 확인해 사용자가 사내 적용한다. 복사 블록은 각각2,500자 이하, 사용자 결과는1~2줄이다. 사내 적용·main 직접 push·Figma 수정은 하지 않는다. Native 초안 복원 유지·회차 대화 카드 우선 이전·제안 기록의 권한/호환성·처리/오류 표시를 반영한 [설계안 v2를 #83에 게시했으며](https://github.com/knadalkim-a11y/team-agent-poc/issues/83#issuecomment-6134977642) 2단계·#77·#79는 구현하지 않는다.

아래는 선행 작업 당시의 기록이다.

## 2026-10-12 · PR #82 병합본의 사내 재실행

- **현재 결정:** 사용자가 PR #82의 코드 보완을 승인했다. 문서를 병합 후 절차에 맞추고 최종 head CI 성공 후 병합한다. **적용 대상은 PR #82의 병합 SHA**이며, 해당 SHA의 main CI 성공을 확인한 뒤 [#78](https://github.com/knadalkim-a11y/team-agent-poc/issues/78)에 전체 40자리 SHA와 결과를 확정한다. f0148에는 긴 경로 보완이 없으므로 재실행 대상으로 사용하지 않는다.
- **변경:** 임시 원본만 clone 부모의 고유 폴더로 분리하고 Windows 경로 예산을 사전 검사한다. 원본 바이트·로컬/링크 보호·기존 state_root ZIP/복구 계약을 유지하며 정리 실패는 최초 오류와 함께 남긴다. 설치/데이터/키/Windows 정책·기존 복사 블록은 변경하지 않는다.
- **검증:** 코드head951e799의 [CI38213662729](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38213662729)는24개 성공/조건부1skip이다. Windows 정책0에서 기존290자 경로의 읽기 실패와 새241자 경로의 준비·정리 성공을 재현했고 정책 복원 뒤 전체 platform 검사도 통과했다. 관련 Linux76개 중74PASS/Windows 전용2skip과 [최초 실패·검증 한계](../evals/v4-ui-20260930.md#internal-pilot-trial-source-failure-20261012)를 함께 보존한다. 이후 문서만 고친 최종 head와 병합 SHA의 CI는 PR #82 및 #78에 구분해 기록한다.
- **다음 작업 하나:** 사용자가 #78에서 확정한 병합 SHA와 [적용·복구 원문 블록](03-openwebui-native-agent.md#internal-pilot-20261012)으로 사내 재실행한다. 예상 설치 SHA는 `7670a1b8f43e122250e0b766bc86986a2abb34ee` 그대로다. 실제 적용·로그인·기존 대화와 [확인5개](03-openwebui-native-agent.md#internal-pilot-checks-20261012)는 미확인이다. 그 결과를 받을 때까지 후속 병합과 #78 PR2~4·#79·#77 착수는 보류한다.
- **최초 Windows CI 보완:** 코드head5b21398의 platform 시험에서 무관한 worktree 보존 시험이 실제 CRLF를 LF로 잘못 기대해1실패했다. 실행 전/후 바이트 보존 비교로 고쳤고 Linux에서도 CRLF checkout을 명시해 같은 조건을 재검한다. Windows 정책0 핵심 검사는 전체 suite보다 먼저 실행해 결과를 독립적으로 얻으며 기존 전체 검사를 유지한다. 제품 코드·기존 블록은 직전 head와 같다.

아래 두 절은 PR #82 검토 승인 전의 실패·판단 이력이다. 당시 f0148 고정·병합/재실행 보류는 위 결정으로 대체됐으며 현재 실행 지시가 아니다.

## 2026-10-12 · 적용 묶음의 Git 원본 준비 실패

- **새 사내 결과:** 예상 SHA 정정 블록을 실행한 뒤 사용자가 `upgrade / failed / changed=false / wrapper_changed=false / trial_source_failed / TrialBundleError / ees_trial_bundle.py:180`을 보고했다. 전사된 stage는 `trail_build`, wrapper는 `f0148aa9de59`이며 실제 저장값과 구분한다. 코드상 대응 단계는 `trial_build`이고 Update 뒤 서버 Stop·Backup·Apply 전에 중단하는 경로다. 실패 뒤 웹 접속·현재 서버 상태는 미확인이다.
- **14:56 KST 재시도 결과:** 로컬 Git 긴 경로 설정 후 한 번 재시도하는 안내 뒤, 사용자가 `trial_build / operation_failed / StateError / ees_deploy_state.py:142 / changed=false / wrapper=f0148aa0de59`를 보고했다. `_safe`가 검사 경로의 존재를 확인하지 못한 오류이며 Stop 이전이다. 이 단계에서는 원본 파일 검사 또는 완성 ZIP 검사로 좁힐 수 있으나 어느 경로인지는 저장 결과만으로 알 수 없다. [최초 실패·재시도·검증 한계](../evals/v4-ui-20260930.md#internal-pilot-trial-source-failure-20261012)를 보존한다.
- **15:07 KST 당시 판단:** 사용자가 `git=true / win32=0 / sparse=unset`을 보고했다. Git 긴 경로 처리는 켜졌고 Windows 긴 경로 지원은 꺼져 있어 Python의 290자 경로 확인 실패 가설과 강하게 부합했다. 개별 실패 경로는 미확인이다. 임시 원본 worktree만 짧은 고유 경로로 분리하고 실제 파일/디렉터리 길이 검사·기존 보호를 유지하는 [구체적인 수정 계획](https://github.com/knadalkim-a11y/team-agent-poc/issues/78#issuecomment-6118780138)을 #78에 남겼다. 당시 코드·검사 보완까지 사용자 확인을 기다렸으나 구현 보류 범위가 넓었다고 정정하고 수정·검증을 완료했다.
- **당시 범위:** 추가 사내 진단/재적용·복구·PC 정책 변경을 안내하지 않았고 사건 기록만 갱신했다. 당시 main/적용 대상 `f0148aa0de592df89ab841c7c9e82cd6ca268149`와 병합 보류는 위 PR #82 승인·새 병합 SHA 확정 절차로 대체됐다.

## 2026-10-12 · 실제 설치 SHA 확인과 적용 안내 정정

- **사내 첫 결과:** 사용자가 기존 안내를 실행했고 예상 원본 불일치로 Update·Stop·Apply 전에 중단했다. 실제 설치 원본은 `7670a1b8f43e122250e0b766bc86986a2abb34ee`(PR #76), `valid=true / running=true`다. 프로그램 파일 검증·등록 프로세스 확인이며 웹 접속 health, 새 적용 성공, 로그인·기존 대화는 미확인이다.
- **당시 작업:** 사용자 승인에 따라 [적용 블록](03-openwebui-native-agent.md#internal-pilot-20261012)의 예상 설치 SHA 한 줄만 정정해 Draft PR #82에서 검토·Windows 구문/길이 검사를 받았다. 처음에는 문서 수정·병합 보류 범위였고 이후 긴 경로 보완을 같은 PR에 포함했다. [사내 중단과 기존 main hover 실패 기록](../evals/v4-ui-20260930.md#internal-pilot-installed-sha-20261012)에 최초 결과와 확인 한계를 함께 보존한다.
- **당시 대상:** PR #81 병합 SHA `f0148aa0de592df89ab841c7c9e82cd6ca268149`의 [main CI38193958368](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38193958368)는 25개 작업 모두 성공했다. 당시 이 SHA로 고정해 사용자가 실행했고 이후 긴 경로 오류가 발생했다. 현재 적용 대상은 위 PR #82 병합 SHA 확정 절차를 따른다.

아래는 정정 전 준비 이력이다.

## 2026-10-12 · 첫 사내 적용 준비

- **병합 완료:** [PR #80](https://github.com/knadalkim-a11y/team-agent-poc/pull/80)의 Q5는 Native 배경막·초점 제한 유지로 확정했다. 제품 변경 없이 결정을 기록했고 최종 head `7415dfd3851942343237acd594b486e19e0c4b87`의 [CI38189324021](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/38189324021) 24 success/조건부1skip을 확인해 main `2f0e00c8a40beb72ed5aae39943ac2f3c7c43e89`로 병합했다. 최초 CI 실패와 Native39PASS는 [기존 기록](../evals/v4-ui-20260930.md#c18-review-focus-20261011)에 연결한다.
- **현재 작업:** [PR #81](https://github.com/knadalkim-a11y/team-agent-poc/pull/81)의 준비1~5는 사용자 검토를 받았으며, 종료 실패 복구 블록(1,752자)·검토 근거 예시와 Windows 두 블록 구문/길이 검사를 보완했다. 최종 head CI 성공 시 병합 승인을 받았다. 위 최신 main의 새 브랜치에서 [#78 준비 항목1~5](https://github.com/knadalkim-a11y/team-agent-poc/issues/78#issuecomment-6115636532)를 Draft PR 하나로 제출한다. [착수 계획](https://github.com/knadalkim-a11y/team-agent-poc/issues/78#issuecomment-6115694225)에 따라 단일 적용·실패/DB복원 안내, 등록 Python 시간대 사전 검사, 실제3a51 ees.12 Windows 적용/Restore 검사와 [실제 업무 안내](07-team-quickstart.md#first-work-20261012)를 보완했다. 화면/Figma·Q5 동작은 변경하지 않았다.
- **검증과 경계:** [준비 검증·최초 실패·한계](../evals/v4-ui-20260930.md#internal-pilot-prep-20261012)에 로컬 결과를 보존한다. 최종 원격 HEAD/Windows CI는 이 준비 PR 본문/Checks에서 판정한다. 자동 검사 성공은 사내 적용·실제 인증/ACL·개인 PAT·모델 품질·팀원 사용성 확인을 대신하지 않는다.
- **다음 작업 하나:** 준비 PR의 CI·검토·병합 후 사용자가 [한 번 적용 안내](03-openwebui-native-agent.md#internal-pilot-20261012)를 실행한다. 결과는 [5개 확인](03-openwebui-native-agent.md#internal-pilot-checks-20261012)을 한 줄로 받으며, 실제 적용 성공·기존 대화 유지·관리자 준비·**비관리 팀원1명의 실제 회차 완료**가 우선이다. 최종 병합 SHA와 main CI 결과는 [#78](https://github.com/knadalkim-a11y/team-agent-poc/issues/78)에 기록한다. 사내 실행 결과는 아직 미수신이다.
- **사내 설치 상태:** 마지막 보고는 10-01 복구 ees.12이며 정확한 설치 SHA는 미수신이다(3a51 추정). 준비 블록이 Status로 전체 SHA를 확인하고 예상 원본이 다르면 적용 전 중단한다. 09-10·10-01 `process_stop` 실패의 근본원인은 미확정이며 새 실패만 기존 기록/명시 복구 경로로 판단한다.
- **미룬 작업:** #78 PR2~4·#79·#77은 착수하지 않는다. 사내 결과의 결함을 먼저 고치고 위 목표 완료 뒤 최신 main에서 PR2를 시작한다. 지침 변경 뒤 열린 회차를 정상 완료할 수 없는 문제는 #79 착수 계획에서 결정하며 이번 업무는 스킬·자동 실행·EES 요청을 쓰지 않는다. B6-1의 모든 대화 즉시 적용 문구는 확인되지 않으면 표시하지 않는다.

아래 항목은 선행 작업 당시의 기록이다.

## 2026-10-06 · C15 권한별 메뉴와 Open WebUI 왕복

- **기준:** 최신 첨부의 추가 E를 같은 [Draft PR #76](https://github.com/knadalkim-a11y/team-agent-poc/pull/76)에 반영한다. 착수 head `e9a34e16d158c7553cfcf66a2cfc01ff794ebbd0`의 [CI 37427430144](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37427430144)는 24 success·기존 조건부1skip이며, main은 `e55bfb125ddf84d14030b1b56bb604bd8b14d088`이다. 선행 #74/#75 병합과 C15 이후 변경 없음, 기존 A–D 본문 동일을 확인했다.
- **구현:** [착수 비교표](mockups/ees-work/TASK.md#menu-integration-20261006)에 따라 세 메뉴 묶음·서버의 실제 Native 권한·직접 경로·원래 위치 복귀를 추가했다. Native 관리자 설정의 모달 redirect와 계정 전환 중 늦은 flush를 보완했다. 관측 가능한 이미지/업로드 중 첨부는 이동을 차단하고 이유를 표시한다.
- **로컬 검증:** 서버73·실제 Native 계정 API6개 통과. Node 관련 범위225개는 freeze2의 author95/execution64와 마지막 runtime66을 합친 범위이며 단일225개 실행은 아니다. 최종 build4의 실제 Native5개는 PASS/0skip/exit0이며 스킬 검색·관리자 모달 왕복·미저장 작성 값·이미지 차단·직접 진입/삽입점 부재·역할 메뉴를 확인했다. build4 SHA256은 `ecf138543e933a6c8ecefa13887c8210142068bb47e06e4743f9a25661a86c1a`다. [최초 실패·빌드·시각 보완·한계 기록](../evals/v4-ui-20260930.md#menu-integration-evidence-20261006)을 보존한다.
- **첫 CI 보완:** head `92f59d0`의 [CI 37434967430](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37434967430)에서 양 OS services/platform이 기존 시험의 권한 fixture·CSS 참조 목록 누락으로 실패했다. 해당 시험2개만 갱신하고 제품 권한·builder·실제 Native gate는 유지했다. 같은 run의 Native compose34개와 전체 제품/중앙 대화 checkpoint는 통과했으며, 최초 실패와 보완 결과는 위 검증 기록에 보존한다.
- **경계와 다음:** 파일 선택 직후 미리보기 전 준비 구간의 완전 보존은 Native 신호가 없어 미확인이다. 새로고침/탭 종료 시 메모리 복귀 정보는 사라진다. 실제 사내 적용·비기본 모델 설정 전체·실제 답변 품질은 별도 확인 대상이다. 최종 HEAD의 자동 CI·후보는 같은 PR 본문/Checks에서 판정하며 병합·Draft 해제·배포·실제 EES/EMS 연결은 포함하지 않는다.

아래 항목은 선행 작업 당시의 기록이다.

## 2026-10-06 · 새 절차 예시 구현·첫 CI 보완

- **기준:** 사용자 승인으로 [PR #75](https://github.com/knadalkim-a11y/team-agent-poc/pull/75)를 병합했다. 최종 head `481fb553f8f94b990edcda4659cdd32f0065cc0a`의 [CI 37413644400](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37413644400)는 completed/success이며 24개 job 성공과 기존 조건부 1개 skip을 확인했다. 병합 main `e55bfb125ddf84d14030b1b56bb604bd8b14d088`에서 새 브랜치를 시작했다.
- **현재 작업:** [제품 수정 전 비교표](mockups/ees-work/TASK.md#procedure-examples-20261006)에 따라 C 예시 3개·서버 초안 복사·빈 절차 기본값·절차 화면 D를 구현하고 [Draft PR #76](https://github.com/knadalkim-a11y/team-agent-poc/pull/76)을 게시했다. Figma C/Note/B2/B4와 C13을 대조했으며 AP 장애 예시는 제외한다. 새 생성 의도와 요청 재시도를 구분하고 취소·시스템 전환 뒤 늦은 응답을 차단한다.
- **초기 로컬 검증:** 관련 서버71PASS, 작성기·런타임 Node142PASS, 패키징2PASS, 설치61PASS/기존 조건부6SKIP이다. 실제 이전112/114 설치의 파일·DB·키 보존과 Apply/Restore를 확인했다. 실제 빌드 Native는 UUID 없는 빈 절차1개(build1)와 C 예시/도움말/대화/게시 차단1개(build2)가 통과했다. 580px 및600px의 이름·footer 접근을 확인했으며, 600px은 Native 메뉴를 다시 여는 조건이다.
- **첫 CI와 보완:** head5669699의 [run37425706328](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37425706328)은 전체 제품 검사에서 실패했다. Native-compose29개·최종600px 메뉴 조건과 양 OS 서버/설치/복구는 통과했다. 이름 입력 후 첫 생성 클릭 중 footer 교체가 클릭을 없애는 결함을 재현했고, 같은 원인의 도구 저장도 확인했다. 두 입력 경로에서 버튼을 유지하며 필수값·권한·busy 상태를 갱신한다. 작성기94개가 통과했으며 실제 입력 직후 첫 클릭 회귀로 보완했다.
- **근거와 한계:** [최초 실패·수정·최종 화면·해시](../evals/v4-ui-20260930.md#procedure-examples-evidence-20261006)를 보존한다. 보완 build3 SHA256은 `7eb76af53b3ce34cb42cd6a2f782c8a7467ed75ea1c2612a199ce6f41ee664a6`이며 입력 직후 첫 클릭의 Native3개를 확인했다. 세 번째 시험 로그 누락은 보존하고 해당 read1개의 독립 Ran1/OK로 보완했다. 기존 전체 Native 제품·중앙 대화 gate의 바이트/기한은 변경하지 않았다. 실제 사내 적용·모델 답변 품질은 미확인이다.
- **다음 작업:** 같은 Draft PR #76 본문/Checks에서 보완한 정확한 최종 HEAD의 자동 CI·배포 후보를 판정한다. 이 문서의 이전 head·로컬 성공을 최종 원격 성공으로 대신하지 않는다. 새 PR 병합·사내 적용·운영 연결은 포함하지 않는다.

아래 항목은 선행 작업 당시의 기록이다.

## 2026-10-06 · 공통 도움말과 쉬운 도구 등록 구현·검증

- **기준:** 사용자 승인으로 [PR #74](https://github.com/knadalkim-a11y/team-agent-poc/pull/74)를 병합했다. 최종 head `ea5108542bd1d774bedaca4ed394e6ec4edff9be`의 [CI 37409566696](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37409566696) 성공을 확인했고, 병합 main `29b95b56917a5b587056d33f1df4d43783ecfdb2`에서 `feat/work-easy-tools-20261006`을 시작했다.
- **현재 작업:** [착수 비교표와 D1–D8 기본안](mockups/ees-work/TASK.md#easy-authoring-20261006)에 따라 A 공통 도움말·대화창 연결, B 쉬운 도구 등록, 도구 화면 D 안내를 구현·검증하고 [Draft PR #75](https://github.com/knadalkim-a11y/team-agent-poc/pull/75)를 게시했다. 첫 CI에서 확인된 시험용 패키지 자료 누락을 보완하며, 정확한 최종 HEAD의 판정은 PR 본문/Checks에서 관리한다. 절차 예시 C는 이번 PR 병합 후 다음 PR이다.
- **디자인:** Figma 변경 기록과 관련 화면/Note를 읽기 전용으로 재조회했다. C13 이후 변경이 없고 A/B 관련 내용·스타일·화면 PNG도 이전 조회와 동일하다.
- **검증:** 최종 UI Node132PASS, Operations48PASS, Native bridge16PASS, Workspace/공개 Tool/과거 조회67PASS, 관련 패키징 PASS다. 실제 빌드 Native3흐름(읽기·요청·도움말)이 통과했고, 고급 도움말 갱신 후 초점까지 최종 build3에서 확인했다. installer60PASS/6SKIP와 실제 이전 ees.13의 파일·자료 보존 Apply/Restore를 검증했다. [처음 실패·독립 검토 보완·빌드/화면 근거](../evals/v4-ui-20260930.md#easy-authoring-evidence-20261006)를 보존하며, 최종 원격 HEAD/CI·배포 후보는 새 PR 본문/Checks에서 확정한다.
- **보완:** 시스템별 비공개 초안과 저장 중 입력을 보존하고, 요청/direct 필수 계약·현재 권한·검사중 revision을 재검한다. 도움말 실패는 모델 호출 전에 안내하고, 기존 설치의 인증된 이전 파일 목록만 복구 가능하게 유지한다. 현재 신규 묶음의 JSON 필수 검사와 기존 RECORD/file hash 보호는 유지했다.
- **첫 CI:** 신규 Native3흐름과 전체 Native 제품은 통과했지만 계정 시험 fixture의 JSON 복사 누락과 별도 Chrome 준비30초 초과로 필수2개 job이 실패했다. [최초 실패·확정 원인·보완 및 미확정 지연](../evals/v4-ui-20260930.md#easy-authoring-evidence-20261006)을 보존한다. 제품 및 Chrome 준비 기한은 유지하고 누락을 고친 새 head의 자동 CI로 판정한다.
- **경계:** 새 PR의 병합·Draft 해제·사내 배포·실제 EES/EMS 연결·Figma 수정·사용자 자산 삭제는 수행하지 않는다. 실제 사내 적용·사용성 결과는 미확인이다.

아래 항목은 선행 작업 당시의 기록이다.


## 2026-10-06 · HTTP 환경의 초안 생성 오류 수정

- **현재 작업:** #73 병합 후 main `a454e9e01b40d6d89a62ca93d9daa12af77de284`에서 `fix/work-http-id-20261006`으로 선행 긴급 수정을 준비했다. `workUI.newId()`가 `crypto.randomUUID`를 우선 사용하고, 없으면 `getRandomValues`로 UUIDv4를 생성한다. 작성기 6곳·launcher 4곳을 공통 함수로 전환했다.
- **검증:** 관련 Node 110개(기존 103·신규 7), 실제 빌드 Native 작성·저장·새로고침 1개, strict 패키징 2개가 통과했다. 수정 전 신규 7개 실패와 최초 시도는 [기존 평가 기록](../evals/v4-ui-20260930.md#work-http-id-20261006)에 보존한다. CI 검사 목록 점검은 누락 오류 0이며 새 Native 시험도 기존 native-compose에 포함된다.
- **확인 범위:** Chrome 153·임시 SQLite·합성 세션/대화/모델에서 `randomUUID`만 시험용으로 미제공한 검사다. loopback의 보안 문맥에서 수행했으므로 실제 사내 HTTP·Windows 시험이나 사내 사용성 검증으로 간주하지 않는다. [Draft PR #74](https://github.com/knadalkim-a11y/team-agent-poc/pull/74)를 게시했다. 첫 CI에서 신규 초안 검사 포함 작성4개는 통과했고 기존 Q1 폭 검사의 1/64px 차이를 확인해 시험만 보완했다. 최종 HEAD의 판정은 PR 본문/Checks로 확정한다.
- **후속:** [쉬운 작성 화면 비교표·D1–D8](mockups/ees-work/TASK.md#easy-authoring-20261006)와 Figma 작업실 5개/C13을 확인했다. 첨부 0절에 따라 A/B/D는 선행 수정이 병합된 최신 main에서 시작하고, C의 새 절차 예시는 다음 PR로 진행한다. 현재 A/B/C/D 제품 구현은 미착수다.
- **경계:** 기존 권한·요청 receipt·revision·사용자 자료를 보존했다. 이번 hotfix의 병합·Draft 해제·사내 적용과 Figma 수정은 수행하지 않았다.
- **게시 승인:** 최초 push는 자동 승인 검토에서 목적지 전송 권한 미확인으로 차단됐고, 사용자가 2026-10-06 해당 저장소로 수정 코드·시험 증거 push와 Draft PR 생성을 명시 승인했다. GitHub 앱으로 같은 브랜치를 게시했으며 원격 tree와 로컬 검증본의 동일성을 확인했다. 정확한 HEAD의 자동 CI 결과를 PR 본문/Checks에 기록한다. 병합·Draft 해제·사내 적용 승인은 포함하지 않는다.

아래 10-05 및 이전 항목은 당시 상태를 보존한 기록이다. 현재 작업 범위는 위 10-06 항목을 따른다.

## 2026-10-05 · PR #73 C08~C12 후속 구현

- **현재 범위:** 같은 Draft PR #73과 `docs/ees-restructure-step0a-20261001`을 갱신한다. 착수 head는 `f9337175a1d9bd6a351f4da780c0ea4407765a14`, main은 `55832bad328cdfb91c1c284749f7959dd664176c`다. [화면·규칙별 현재/최신/차이/처리 표](mockups/ees-work/TASK.md#figma-followup-20261005)를 제품 변경 전에 기록했다.
- **구현:** A8 수시 업무 진행/새 시작·중복 차단, B2-2 판정 규칙, B2-3 게시 전 확인, S3 근거·사람 확인 표시, 부분 결과 출처, 직접 실행 예외 도구 등록/차단, 일정대로 회차 열기, 정확한 형식별 요청 입력/별도 사유, A7 자동 저장과 카드 기준 시각을 반영했다. Q1의 sidebar/패널/대화 폭·끌기·개인 기억·768 높이의 행동 바·대비를 적용했다. Figma는 읽기만 했고 예시 값을 운영 기본값으로 넣지 않았다.
- **검증:** 전체 Native20 checkpoint·중앙 대화9 checkpoint·runtime8개와 최종 빌드 Q1 2개/계정 전환1개를 통과했다. [최초 실패·보완·실제 Native 결과](../evals/v4-ui-20260930.md#figma-followup-20261005)에 구분해 기록한다. 첫 자동 CI의 Native 작성 구형 선택자와 게시 버튼 준비 관측 실패는 시험만 보완했고 동일 제품에서 작성3개·전체20 checkpoint 재검이 통과했다. 최종 source의 자동 CI는 게시 후 [PR #73 본문/Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)에서 정확한 HEAD/run과 함께 확정한다. 과거 10-02 결과를 이번 CI 성공으로 대신하지 않는다.
- **첫 자동 CI 보완:** `4b618e2`의 run37284962975에서 게시 검사 Native 시험의 이전 선택자와 비동기 준비 조건을 수정했다. 게시 차단·오류 이동·실제 게시 검사는 유지한다. 현재 대화 카드에도 서버에 저장된 기준 시각을 보존하도록 보완했다. 원래 실패와 새 검증은 같은 평가 기록에 남기며 최종 CI와 구분한다.
- **사용자 확인 필요:** checklist/human_confirm의 의미 통합, 저장 폭/끌기로 패널을 넓혀서만 대화560미만이 되는 경우의 처리. A1 일정 조정/B3 되돌리기 대화 카드 버튼은 보류한다. 실제 EES API·상태/효과 조회, 송부 채널, D-5 이후 미승인 CR 처리, 휴일 자료는 미제공이며 해당 행동만 사유와 함께 막는다. 미정 송부·D-5 정책은 게시의 확인 권장으로 표시한다.
- **경계:** Open WebUI0.11.3·기존 사용자 자료/자산·Native 인증·개인 설정·불변 기록을 보존했다. 병합·Draft 해제·사내 적용·실자산 삭제·운영 요청은 수행하지 않았다. 다음 사내 확인과 적용은 별도 승인 대상이다.

아래 10-02 및 이전 기록은 당시 상태이며 이번 후속 구현의 남은 작업 지시가 아니다.


## 2026-10-02 이어가기 · 27프레임 구현 및 작업 환경 복구

- **현재 범위:** 통합 구현을 같은 Draft PR #73/`docs/ees-restructure-step0a-20261001`에서 계속한다. main `55832bad328cdfb91c1c284749f7959dd664176c`, 원격 PR head `659d3ac1bfb646e720aa87d9ec3b7de189ab0eb0`를 재확인했다. main push·병합·사내 적용/삭제는 수행하지 않는다.
- **복구된 제품:** 추가 Figma 7개를 포함한 27프레임 대응 제품 commit `2770382fa29968abe0d469ac9f49988806fbacc3`/tree `15976fe195deaec0cc89873eee4c159e91a847ed`를 GitHub 객체에서 정확히 복구했다. 아직 PR ref에 게시되지 않은 제품 commit과 최종 검증된 HEAD를 구분한다.
- **환경 사건:** 06:54 UTC에 로컬 `.git`·코드·미커밋 시험·docs/evals/dist 경로가 없어졌다. 이후 일부 기존 의존성 파일만 보였고 원인은 미확정이다. 기존 경로를 덮지 않고 별도 checkout으로 복구한다. 앞선 실행의 15개 checkpoint 통과 관측은 남기되 원본 화면 파일을 현재 제출 가능하다고 표시하지 않는다. 좁은 S2 화면 캡처는 당시 로딩 중이었으므로 시각 검수 보완 대상이다.
- **디자인:** 전체27프레임·추가7개 실제 context/렌더를 복구했다. 06:32:42 UTC 최종 관련 A6/A7 재조회는 변경 없음. [화면/기능 대응과 계약](mockups/ees-work/TASK.md#integrated-work-20261002), [평가와 유실/복구 경계](../evals/v4-ui-20260930.md#integrated-recovery-20261002).
- **새 검수 완료:** 실제 Native15checkpoint/종료0·좁은 화면 복원/실제 스크롤 PASS. Native 작성3/runtime5/현재 읽기2, Workspace17·일정18·UI96·작성8·역사/공개도구/Operations/배포업무/branding86개 및 installer/Restore4개를 새로 확인했다. 원래 실패·재구성 fixture 보완은 평가에 보존하며 겹치는 회귀 숫자를 합산하지 않는다. 정확한 전체 source의 새 CI는 게시 뒤 자동 실행 결과로 구분한다.
- **게시와 적용 후보:** 제품/시험/검증 문서를 분리한 커밋으로 같은 Draft PR에 반영한다. 최종 HEAD·그 HEAD의 자동 CI/실제 업로드 파일·해시가 붙은 배포 후보의 최종 판정은 [PR73](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)의 최신 본문/Checks가 원본이다. 이 문서 commit 시점에는 해당 CI가 아직 실행되기 전이며 앞선 통과를 최종 CI 성공으로 간주하지 않는다. 결과 기록만을 위한 동일 CI 수동 반복을 하지 않는다.

아래 통합 구현/CI 상태는 작업 공간 손실 이전 원격 head에 남아 있는 당시 기록이다.

갱신일: 2026-10-02

현재 작업·다음 작업·미해결·실제 적용 원본을 관리합니다. 이슈·검증 근거는 [평가 기록 찾아보기](../evals/scenarios.md#evidence-index), 환경은 [versions](../versions.md), 완료된 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 현재 작업과 다음 작업

- **현재 작업:** [Draft PR #73](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)의 [2026-10-02 통합 계약](mockups/ees-work/TASK.md#integrated-work-20261002)에 따른 제품 구현·로컬 검수·검토용 배포 후보를 보존하고, 여섯 번째 CI에서 관측한 Chrome 첫 유효 응답 지연과 새 Windows 시험 실패를 보완한다. 최신 확인 head는 `5556b573c8ab4430eb44b7e608fc6a8045e0e2bd`이며 전체 필수 CI는 아직 통과하지 않았다. 이전 Step별 중단/설계 승인 대기는 이번 지시로 대체됐다.
- **Git 기준:** main `55832bad328cdfb91c1c284749f7959dd664176c`, 시작 head `b41e23917273e1d2d0ead1ddadfea75b2dda1e32`, branch `docs/ees-restructure-step0a-20261001`. 검토 SHA 이후 원격 변경0·착수 로컬 변경0을 확인했다. #72/#53은 혼합·병합·종료하지 않았다. 제품 구현 커밋은 `051f7facf5176edabd9dab0b886a4a4c2ad71ee3`이며 로컬 검사 원본과 [Git tree/배포 wheel 동일성](../evals/artifacts/ees-integrated-20261002/native-product-evidence.json)을 기록했다.
- **구현 상태:** 기본 데모 제거/빈 상태/재등록 차단, 기존 Native 서버·업무 SQLite의 초안/불변 게시본/진행/시도/판정/권한·공장 설정, 예약 복원·요청 확인/추적/효과, 새 공통 UI와 중앙 대화의 조회·초안·과거 시도 참조를 연결했다. 입력 AI 제안/반영/저장/실행을 분리하고 현재 Native 도구·모델 권한을 매번 확인한다. [실제 테이블·API·화면 대응](mockups/ees-work/TASK.md#integrated-work-20261002).
- **로컬 검증:** 고정 Open WebUI 0.11.3 기반 ees.13 build10의 실제 Native CLI/임시 DB에서 작성→저장→검사→게시→진행→사람 확정, Native 대화·실제 첨부·리로드·서버 재기동 복원을 통과했다. 별도 실제 중앙 대화 게이트도 도구 호출→AI 제안→사람 반영→별도 저장→이전 메시지의 정확한 과거 시도 읽기를 통과했다. 초기 Native/font37개 개별 근거에 이어 네 번째 자동 CI에서 Native4묶음42개(실제 브라우저36/helper·font6)가 모두 PASS였다. 이후 실제 제품 수집기 보완의 로컬 helper8개와 완전 Native1회도 통과했다. 초기 Chrome 응답 지연의 원인은 미확정으로 유지한다. [명령·초기 실패·보완·검증 범위](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002), [원본 PNG/DOM/report 목록·해시](../evals/artifacts/ees-integrated-20261002/native-product-evidence.json).
- **디자인 기준:** page832:131 전체20프레임·추가 안내를 조회하고 구현 뒤 관련 metadata/A1/B3 context·렌더를 다시 대조했다. 관측된 노드/문구/좌표 변화는 없었다. Native 원래 대화·첨부 컨트롤을 재사용하고 추가 계약 필드는 공통 폼으로 연결했다. 모든20프레임의 픽셀 단위 동일성이나 향후 Figma 변경 반영 완료를 주장하지 않는다. [조회 기준·화면 대응](mockups/ees-work/TASK.md#integrated-work-20261002).
- **원격 검사:** 첫 통합 head89d910e의 [run36954271808](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36954271808)은 failure다. Native37개/완전 Native 두 게이트·Linux contracts/platform은 PASS이며 실제5artifact93파일의 digest·PNG/DOM/report를 확인했다. Linux services는 기능 PASS 뒤 고정 archive 숨김 파일 누락 문서15FAIL, Windows는 LF 고정 fixture·시간대 데이터·JS 주입·OS 경로/UTF-8 fixture 문제를 확인했다. 각각 최소 보완했으며 긴 ees.10/11/12 실제 설치·복구는 정확한 ID별 필수 묶음으로 나눈다. 첫 Windows platform의10분 취소·미완료를 성공으로 바꾸지 않는다. [첫 결과·원인/재현·수정](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)을 보존한다. 이후 **최종 head의 완료 CI·배포 후보 식별/해시는 [PR 본문과 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)**에서 관리하며 이전 실패와 구분한다.
- **외부·정책 경계:** 실제 EES 기능/인증/상태·효과 조회 연결은 미제공이며 운영 요청은 사유를 표시해 차단한다. 결과 송부 채널·미승인 CR 처리·휴일 계산 정책도 미정이다. 계약/화면/저장/검토·합성 전송 검사는 구현했고 이를 사내 성공으로 표현하지 않는다. Native 개인 PAT·기반 모델·사용자 자료는 보존한다.
- **잔여 검사 보완:** 두 번째 [run36956218460](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36956218460)의 Windows 서비스·실제 복구3개와 완전 Native 두 게이트는 통과했다. Native 애니메이션 준비 전 관측 실패는 실제 pending→회전 진단으로 원인을 확인해11개 재검을 통과했다. Windows 시험 SQLite 종료 누수8개는 명시 close 뒤 영향8개 PASS이며, 작은 Node fixture의 지연 원인은 미확정으로 단계 진단을 추가했다. 긴 일반 설치58개·Native 예제5개를 누락 없이 필수 묶음으로 분리했다. [첫/두 번째 원격 실패·취소와 로컬 보완](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)을 보존한다. **마지막 HEAD의 실제 Windows/전체 CI 완료 판정과 후보는 PR 본문/Checks에서 확인**하며, 앞선 실패·미실행을 성공으로 바꾸지 않는다.
- **적용 준비:** [기존 설치 업데이트·새 설치·백업·프로그램/자료 복구 안내](03-openwebui-native-agent.md#integrated-work-install-20261002)를 갱신했다. 실제 ees.12→13 Apply 중단→명시 Resume→Restore12는 Linux 합성 설치에서 통과했다. 실제 사내 Windows 설치/등록 목록·사용자 수정 여부는 미확인이다. 자산 정리 도구는 미리보기/정확한 hash/사용자 변경 보호/백업/중복 방지/복구를 개발 데이터로 검증했으며 실제 삭제는 수행하지 않았다.
- **변경 금지 경계:** main 직접 push·PR 병합·Draft 해제·실제 사내 배포·실제 사용자 자산 삭제·운영 변경 요청·Figma 원본 수정은 수행하지 않는다. 별개 PR #72의 완료된 사용자 복구도 반복하지 않았다.
- **최근 원격 확인:** 세 번째 [run36957905733](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36957905733)에서 양 OS16개 서비스/계약/플랫폼/설치/복구 job과 완전 Native 두 gate·계정/업무/compose가 통과했다. Native 실행1건의 화면 진입 전 Chrome 초기 응답 timeout은 실패로 보존한다. 기존15초 내 준비 확인·첫 실패 진단 보완 후 helper6개/영향 Native5개가 로컬 통과했고 실제 Chrome 지연 원인은 미확정이다. [이력·보완·후보 동일성](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)과 마지막 HEAD의 PR Checks를 구분한다.
- **네 번째 CI와 후속 보완:** [run36958974158](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36958974158)은 Native4묶음42PASS·플랫폼16묶음 중15success였으나 완전 제품 Chrome 첫 응답 timeout과 Windows 자연 종료 관측2ERROR로 failure다. 실제 제품 수집기에 누락된 첫/종료 진단 보존을 보완했다. Windows 제품은 신원 미확인 프로세스에 신호 없이 차단했고 실제 Win32 원인은 미확정이다. 원래 시간·보호 조건을 유지하며 시험 소유 child의 자연 종료 관측을 보완하고 최종 CI에서 검증한다. [실패·원본 파일·보완·재검](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)을 보존한다.
- **다섯 번째 완료 CI:** head `403b0685e26f13add0ff4354ba118788a0e95678`의 [run36960650678](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36960650678)은 failure다. 양 OS16개 서비스/계약/플랫폼/설치/복구 job은 모두 success이며 Linux1159PASS/11SKIP·Windows1168PASS/2SKIP이다. Windows 자연 종료 관측2ERROR의 영향 검사는 실제 Windows에서 통과했으나 원래 Win32 원인은 미확정이다. Native는43PASS/1FAIL(실제 브라우저35PASS/1FAIL·helper/font8PASS), 실제 제품8단계·중앙 대화9단계는 PASS다. 실제5 ZIP의94파일(50PNG/43JSON/합성 TXT1) hash를 확인했다. 남은 실패는 화면 진입 전 `Browser.getVersion`15초 timeout이며 첫 진단 JSON이 보존됐다. [완료 결과·최초 실패·파일 검증](../evals/v4-ui-20260930.md#integrated-fifth-ci-20261002)에 기록하고 계속 조사한다. 집계 failure/cancelled·일반 package의 기존 PR 제외 skip을 성공으로 바꾸지 않는다.
- **이어가기 보완:** Native fixture에 누락된 종료 진단을 별도 `-cleanup.json`으로 저장해 최초 실패 파일을 그대로 보존한다. 최초 handshake timeout 때만 같은 id1의 늦은 응답을 ChromePipe 생성 후 총30초까지 수신하고, 원래15초 실패·예외·성공 조건은 유지한다. 재전송·제품 화면 진입·시험 재개는 없다. helper/font13개와 영향 Native5개가 기존 Chrome153에서 PASS였고 독립 리뷰를 마쳤다. [명령·소스 hash·실제 PNG5개](../evals/artifacts/ees-integrated-20261002/chrome-bootstrap/resume-observation-evidence.json). 변경한 수집기의 자동 CI Chrome154 결과는 최종 PR Checks에서 확인하며 이전 기동 지연의 근본 원인은 미확정이다.
- **여섯 번째 완료 CI:** [run36966415796](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36966415796)은 completed/failure이며 Native는48PASS/1FAIL(실브라우저35PASS/1FAIL·helper/font13PASS)이다. 최초15초 timeout 뒤 별도 수집기에서 같은 id1의 유효 Chrome154 응답을15.3498초에 관측하고 정상 종료를 확인했다. 제품 진입 전 준비 응답 지연은 확인했으며 OS/DBus가 늦어진 원인은 미확정이다. 실제 제품8단계·중앙 대화9단계와95증거파일(50PNG/44JSON/TXT1)은 확인했다. 플랫폼16개는15success/1failure(Linux1159PASS/11SKIP·Windows1166PASS/2FAIL/2SKIP)다. Windows의 첫 실패는 정상 작업 중0.15초 fixture lease 만료를 확인했고, 두 번째 rollback의 같은 원인은 가설로 남긴다. fixture의 정상 작업 lease와 죽은 worker 복구 전제를 분리한 영향6개는 Linux에서 PASS했으며 Windows 재검은 남았다. 전체25job은20success/3failure/1cancelled/1skipped다. [원본 최초/종료 진단·후속 경계](../evals/v4-ui-20260930.md#integrated-sixth-ci-20261002).
- **관측 후 보완:** 생성 진입부터 절대30초인 단일 Chrome 준비 예산과 준비 뒤 기존15초인 Target/후속 CDP 동작 예산을 분리했다. 오류/무응답·재전송 금지·제품 UI/권한/저장 assertion은 유지한다. helper/font17PASS와 영향 Native-compose11PASS/PNG10개를1회 확인했으며 성공 준비시간은151.765~238.674ms다. [명령·소스 hash·회귀·화면 근거](../evals/artifacts/ees-integrated-20261002/chrome-bootstrap/startup-phase-evidence.json).
- **다음 작업:** 최소 시험 도구 보완을 독립 검토·커밋한 정확한 최종 HEAD의 자동 CI에서 Chrome154와 Windows 영향 검사를 확인한다. 같은 조건의 긴 CI 수동 반복·고정 sleep·재전송·skip·제품 동작 제한 확대 없이 완료 결과와 정확한 head 후보를 같은 Draft PR에 갱신한다. 완료한 제품 구현·환경 설치·Windows 보완을 처음부터 반복하지 않는다. 실제 사내 적용/자산 정리는 별도 승인이 필요하다.

착수 전 STATUS와 과거 실패는 [날짜가 있는 기존 평가](../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)에 보존했다. 아래 9월/이전 적용 이력은 현재 작업 지시나 신규 사내 적용 성공이 아니다.

<a id="2026년-9월-개발검사-방침"></a>

## 원격 검사 방침 · 10-01 재개 경계

10-01 KST 첫 재개로 아래 9월 한시 생략 기간은 종료됐다. PR70 문서 head `1b85a642`의 [자동 실행36788646851](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36788646851)은 Windows/Linux 모두 runner 미배정·steps0 상태에서 failure, 전달물은 skipped다. 시험 코드가 실행되어 실패한 것으로 해석하지 않는다. 로그는404이며 연결 도구로 annotation/계정 잔여량을 조회하지 못해 원인·무료분 복구는 미확인이다. 새 커밋에 `[skip ci]`를 넣지 않고 원격 검사를 재개하되, 성공이나 Windows 검증 완료로 기록하지 않는다. 10-01 복구 승인 당시의 한 번 복구는 기존 재배포 권한 아래 로컬 검증·정확한 보관 원본·백업·명시적 단일 서버 종료를 전제로 준비하며 기본 Upgrade의 CI 확인은 변경하지 않는다.

### 9월 당시 방침과 종료 조건

사용자 선택으로 **2026-09-30까지 이 작업의 GitHub 원격 검사를 생략**한다. 이 저장소에 게시하는 개발·문서 커밋 메시지마다 `[skip ci]`를 넣어 기존 `push`/`pull_request` 자동 검사를 생략하며 수동 실행·재실행은 요청하지 않는다. PR 본문에만 적거나 이전 커밋의 표시가 이후 커밋에도 적용된다고 가정하지 않는다. 이는 작업 커밋별 생략이며 계정 전체 Actions를 비활성화한 것이 아니다.

코드 작성·Git 반영·변경 범위의 로컬 검토/시험과 문서 검사는 계속한다. **후속 사용자 합의로 원격 검사 생략을 9월 전체 배포 금지로 확대하지 않고, 로컬 검증 후 변경별로 제한된 시험 적용을 준비한다.** 검토한 정확한 원본·배포물 해시·자료 보존·기존 프로그램 복원 수단을 확보하고 적용 뒤 기동·기존 대화·업무 저장·변경 화면을 필요한 소수 항목으로 확인한다. 사내 사용자 자료의 백업과 프로그램 Restore를 구분한다. Windows·사내 실환경의 미실행은 남기고, Work Native 브라우저 검사와 실제 사내 적용 전후 결과를 구분한다. 기본 Upgrade/ApplyDemo의 CI 확인은 유지한다. 후속 사용자가 배포 진행과 수동 ZIP 단계 자동화를 요청해 공개 TrialCommit 경로·Backup·자동 묶음 준비를 연결했으며, 검토한 원본의 병합과 실제 사내 적용 성공은 각각 확인한다. 상시 실행기·별도 브라우저 시험 프레임워크·결제 설정 변경은 추가하지 않는다. 09-21 후속 승인으로 Work의 저장소 검증 환경 한 곳을 준비했으며 회사 PC의 제품 설치·운영 환경과 구분한다.

**2026-10-01 이후 처음 작업을 재개할 때** 이 한시 생략을 종료하고 무료분 복구 상태와 최종 변경 범위를 확인한다. 마지막 코드에 대해 표시 없는 새 커밋 또는 기존 수동 실행으로 필요한 원격 검사를 수행한다. 10월 1일 예약 실행을 만든 것은 아니며 과거 생략된 검사가 자동으로 재개되지 않는다. 사용자 변경 지시가 있으면 해당 지시를 우선한다. [근거·재개 조건](../evals/scenarios.md#work-ui-refactor-20260915).

10-01 Step0-A의 진행 중 관측과 Step0-B에서 확인한 완료 결과는 [기존 평가에 각각 보존](../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001)한다. 새 자동 CI는 최종 변경 head 기준으로 따로 확인하며 취소·skip·미실행을 통과로 간주하지 않는다.

## 마지막으로 확인된 적용 상태

아래 표는 조사 기준 main에 기록된 이전 적용 이력입니다. 이후 복구·UI 일부 반영 보고는 위 PR #72 참조가 최신이며, 아래 실패 상태를 현재 장애로 단정하거나 재복구하지 않습니다. 사용자 보고 시점의 확인이며 실시간 서버 점검 결과가 아닙니다. Git 게시·CI 성공·안내한 SHA를 실제 사내 등록 바이트와 혼동하지 않습니다.

| 대상 | 마지막 확인과 적용 원본 | 남은 한계·근거 |
|---|---|---|
| EES Work 업무 UI | #68 적용 뒤 파손 보고. #69 병합 후 10-01 재배포는 Stop timeout으로 Apply 미진입 | 설치본은713, 수정본3a51은 미적용. 최초 UI 파손과 이번 종료 실패는 다른 단계이며 실제 새 UI 정상은 미확인. [V4 결함 조사](../evals/v4-ui-20260930.md#v4-ui-breakage-investigation) |
| EES 프로그램 | 10-01 Status `713ed5e4e5dc`, customized/running=true, 등록 포트 listener=false | 등록 신원 존재와 설치 원본 보고이며 health 성공이 아니다. HTTP/새 UI·복구 성공은 미확인 |
| 운영 래퍼 | #70 main `0e88af6189812` 고정 블록 뒤 recover_stop 경로 오류 보고 | 안내 순서상 Update·SHA 확인 통과와 부합하지만 새 UI 적용은 아니다. 경로 보완 래퍼의 실제 실행은 미확인. [이번 종료 실패](../evals/v4-ui-20260930.md#v4-stop-timeout-20261001); [이전 이력](../evals/scenarios.md#integrated-work-beta-20260921) 보존 |
| 분석·업무 패널 자산 | #66 적용 안내 뒤 ApplyDemo ok 사용자 보고 | changed·등록 바이트·실제 UI 재사용 검사 미수신. 이번 시각 보완 때문에 사용자 자산을 재등록/일괄 동기화하지 않음 |
| 대표 시작 질문 | 09-15 `87f3f2922a4a`의 v0.2.10 관리 목록을 포함한 ApplyDemo 성공 | 질문의 실제 표시 여부는 미확인. 변경 3건을 특정 질문 변경으로 단정하지 않음. [이번 적용](../evals/scenarios.md#work-ui-refactor-20260915), [이전 접속 실패](../evals/scenarios.md#connector-demo-starters) |
| WO 목업 | v0.1.6 안내 원본 `ba396da8d1d0abcb4e17494e8d9b37c5add514fc` 뒤 크기 조절 정상 보고; Git은 v0.1.8 통합 패널 원본 | 실제 EMS 미연결. 이후 패널 적용 보고와 개별 등록 바이트 검증을 구분. [목업 이력](../evals/scenarios.md#wo-mockup) |
| 기본 Assistant·기존 조회 | 이름·로고·기존 대화·평소 Confluence/Jira/GitHub 조회 정상, 초기 Rich UI 제거·변경 Prompt 반영 완료 보고 | Tool별 최신 등록 코드·SHA·새 일반 답변/원문 직접 대조 미실행. [반영 보고](../evals/scenarios.md#plain-output-applied-report), [이전 자산별 SHA](../evals/scenarios.md#status-history-20260911) |
| 정책·Skill | 합성 정책·지침 저장 보고, P02 PASS·P03 일부 확인. Git/UI 등록 Skill 3개, 기존 2개의 사용 확인 | 실제 사내 정책·나머지 P 시험·confluence-read 실제 로딩 미확인. [기준](../evals/scenarios.md#instruction-revision) |

## 이전 적용 이력의 이슈와 확인 범위

아래는 통합 구현 착수 전 사내/기존 제품의 관측이다. 새 코드 구현·검증 여부는 위 현재 작업과 최신 평가를 따른다.

- **9월 원격 검증 보류:** 사용자 Billing 화면에서 Actions 무료분 `2,000/2,000` 사용 및 현재 Actions 청구 대상 `$0`를 확인함. 사용자는 9월 원격 검사 생략·개발 계속을 선택함. 결제 실패로 단정하거나 예산 상향을 다음 작업으로 요구하지 않음. R1~R3의 Windows·브라우저 자동 검사는 미실행이며 이전 실패와 로컬 결과를 보존함. ees.9 사내 적용·기동·지정 자산 반영 성공은 이번 사용자 보고로 따로 확인함. [이번 무료분 확인·한시 방침](../evals/scenarios.md#work-ui-refactor-20260915), [앞선 관측](../evals/scenarios.md#workflow-refactor-20260915).

- **공통 자산 업데이트 중 동시 편집:** 기존 GET→POST 사이 지원 description 유실의 합성 결함을 R0 조건부 저장·native 보호 경로로 수정하고 실제 wheel 회귀에서 확인함. 이번 ees.9 설치와 보호 API를 사용하는 ApplyDemo 성공으로 사내 반영을 확인함. 실제 사내 동시 편집 충돌 재현까지 확인한 것은 아님. 보호 미적용 원본 서버·외부 DB writer·일반 UI끼리의 오래된 폼 충돌은 보장 밖. [원래 재현/오탐 정정](../evals/scenarios.md#ai-runtime-preservation-20260915), [수정·검증·적용 경계](../evals/scenarios.md#conditional-assets-20260915).
- **사외 Windows CI 지연:** 이전에 통과한 동일 코드에서 PowerShell 20초·Node 10초 제한시간 초과가 각각 발생했으며 원인은 미확정임. 두 시험의 단계 표식·런타임 버전·timeout의 단계 표식를 보존하도록 보완했으므로 자연 재발 시 그 증거로 진입 관측 여부와 시험 내부 단계를 구분함. 재검사 성공을 근본원인 해결이나 사내 서버 진단 필요로 바꾸지 않음. [실패·관측·최종 CI](../evals/scenarios.md#sidebar-refinement-20260914).
- **메인 채팅의 업무 활용:** 읽기 전용 후보/절차 조회·스킬 지침·기존 진행의 고정본 계획과 목표 기반 Prompt를 구현함. 사내 첫 요청은 Knowledge 검색만 한 뒤 업무 도구 미연결로 답했으나 사용자가 재시도 정상 동작을 보고함. 요청의 도구 선택 상태와 실제 호출 이력은 미확인으로, 일시적 비활성화·브라우저 갱신 지연·모델 선택 중 원인을 확정하지 않음. 정상 사용을 계속하며 자연 재발 시에만 해당 대화의 도구 노출을 확인함. 이는 당시의 확인 경계다. 09-25 새 실행 계약은 [TR 기록](../evals/scenarios.md#shared-native-runtime-20260925)으로 따로 검증하며 과거 사내 보고를 새 실행 성공으로 확대하지 않는다. 기존 DB/AP 모의 점검과 공유 미구현 범위는 유지한다. [이번 관측·판단](../evals/scenarios.md#work-ui-refactor-20260915).
- **팀 공동 작업:** 사용자가 공장 1개·시스템 1개·프로세스 1개, 참여자 2~3명의 첫 단위를 선택함. 현재 진행 건과 대화 연결은 사용자 소유이며 개인 선택 상태도 진행 건에 있어 공동화 때 분리가 필요함. 참여/역할·이력·충돌 처리는 아직 구체화·구현 전임. [새 단위·현황 표시 제안](mockups/ees-work/TASK.md#shared-pilot-first), [전체 목표](mockups/ees-work/TASK.md#ees-work-shared-target).
- **공장별 업무 UX:** 09-15 사용자 보고로 이번 사이드바 선택 영역·직계 펼침·글꼴·대화/초안 유지의 사내 확인을 완료함. Workspace 탭 반복 재삽입·첫 메시지 경합의 사외 재현과 자동 검사는 [기존 근거](../evals/scenarios.md#ees-work-factory-ux-20260914)에 보존함. 이번 네 항목에 없던 Workspace 반복 전환·실제 모델 호출 등으로 확인 범위를 확대하지 않고 다음 관련 사용·변경 시점에만 판단함. [새 UI 수락](../evals/scenarios.md#sidebar-refinement-20260914).
- **이전 폴더 변경 실패:** `dba0677ffe3e`의 Apply 407행 rename 접근 거부 뒤 Restore·Start·웹 접속 복구를 확인함. 이후 ees.7 실행은 확인했으나 어떤 재시도·수동 복구 경로로 적용됐는지와 제한 대기의 사내 효과는 미보고. 파일 잠금·ACL·특정 보안 제품의 원인은 미확정이며 [당시 복구](../evals/scenarios.md#ees7-apply-recovery-20260914)와 [실패 대응 보완](../evals/scenarios.md#windows-program-rename-20260914)을 구분함.
- **과거 업데이트 장애 조사:** 종료 처리·오류 보존의 재현 가능한 결함은 수정/적용했으나 최초 포트 소실과 Windows rename 접근 거부의 근본 원인은 미확정. 마지막 종료 실패 로그의 `KeyboardInterrupt/other/ValueError/OperationalError`만으로 DB 손상·잠금·취소 원인을 확정하지 않음. 약속한 추가 확인은 끝났으며 정상 서버 재현·반복 진단 없이 유지함. 자연 재발 시 개선된 래퍼의 실패 요약을 사용함. [조치와 조사 종결](../evals/scenarios.md#ees-update-failure-causes).
- **접속·스트리밍:** 09-14 수신 소실은 CPython accept 오류→listener 종료 경로와 일치함. 임시 복구 이후 자식 Proactor 보호를 사내 적용하고 기동 health를 확인했으나 유휴 이후 안정성은 미확인. 최초 단절 주체는 미확정이고 제한된 System 이벤트 0건으로 모든 전원·세션 원인을 배제하지 않음. 과거 Selector 준비본은 미적용. [검증·남은 확인](../evals/scenarios.md#accept64-guard-20260914).
- **연동과 팀 공개:** 최신 일반 출력·페이지 이동·부분 실패/빈 결과·개인 권한/비밀 보호는 다음 관련 사용·변경 또는 공개 시점에 확인함. Confluence 검색 범위/시각·본문 근거·C07 개별 오류·Skill 로딩은 일반 조회 성공으로 통과 처리하지 않음. 초기 카드 디자인/키보드 검사는 제거 작업의 남은 게이트가 아님. [시점과 공개 기준](../evals/scenarios.md#validation-timing).
- **정책·격리·사용성:** 팀원 로그인 화면 접속과 자산 Public 설정 보고는 있으나 전송 보호·I01~I05·비개발자 실제 업무/공유 확인은 미완료. 합성 Knowledge POC-POL-001 v0.1과 공통 정책 v0.2를 구분하고 기존 PASS를 미확인 시험으로 확대하지 않음. 초기 EES Memory·Chat History·위험 실행 기능 OFF를 유지함. 운영 DB 직접 연결·자격증명·범용 SQL·Shell·쓰기를 제공하지 않으며 S06은 승인된 DB 중계 기능을 도입할 때만 실행함.
- **운영 연동:** EMS/APC/FDC 시연은 합성 자료임. 공유 DB의 실제 의미/권한·스키마는 미조사이고 실제 발행은 미구현. 설비 조회는 운영 설계에서 독립 Tool로 관리하되 이번 시연은 기존 단일 등록 항목을 유지하는 합의임. [관계 발견](03-openwebui-native-agent.md#shared-db-relations), [발행 경계](03-openwebui-native-agent.md#legacy-ui-design).

<a id="delivery-plan"></a>

## 실행 계획

현재 순서와 완료 게이트는 [통합 구현 계약](mockups/ees-work/TASK.md#integrated-work-20261002)을 따른다. 아래 목표별 표는 이전 진행 이력이다.

| 목표 | 현재 위치 | 후속 범위 |
|---|---|---|
| 1. 쉬운 Chat UI | 이름·로고·스트리밍·폭/조절 표시 정상 보고 | 새 제안 확인, 비개발자 사용성, 관리자 팀 공지 |
| 2. 문서 시스템 | Confluence·Jira·GitHub 읽기·변경 Prompt 반영 보고 | 실제 업무 조회·후속 해석·새 일반 답변/원문 확인 |
| 3. 관리자 공통 정책 | 합성 지침·정책 답변 Skill 저장 보고 | 실제 공통 원칙·상세 절차·권한/Tool 제한·변경 반영 |
| 4. 관리자 워크플로 | #68 파손 뒤 #69 수정 병합, 종료·보관 ZIP 경로 실패 후 [복구 수정](../evals/v4-ui-20260930.md#v4-stop-timeout-20261001) | 승인된 재배포의 종료 실패 복구. 실제 사내 결과·Native 왕복·A/B와 V4-01~15 수락 확인은 남음 |
| 5. 레거시 연동 | 실제 업무 API·DB 미연결 | 승인된 API/Query Broker의 작은 읽기 기능 하나 |
| 6. 레거시 간접 UI | 같은 폼에서 직접 입력·AI 작성/수정의 WO 합성 시연 | 시연 피드백 → 운영 목업 → 실제 EMS 연결 |

사용자 결정으로 WO와 시스템 간 분석 시연을 먼저 진행했습니다. 준비된 화면을 상황에 맞게 활용하고 SHOP → LINE → PROCESS 검색 계층을 유지합니다. 공통 정책의 미완료 상태를 지우지 않으며 전체 시스템·권한 세분화·대형 오케스트레이션 기반을 시연의 선행조건으로 늘리지 않습니다. 첫 파일럿은 범용 채팅과 세 문서 시스템 읽기를 바탕으로 실제 업무 완료·결과/오류/공유 이해를 확인합니다. 기능 하나의 구현·관련 검사·짧은 사내 확인을 묶고 영향 없는 인증/저장 시험은 반복하지 않습니다.

<a id="resume-branch"></a>

## 재개와 환경 유지

현재 재개 대상은 위 통합 구현과 PR #73이다. 아래 첫 항목의 V4 복구·재배포 설명은 당시 이력이며, 최신 사용자 보고로 완료된 사내 복구를 다시 수행하라는 지시가 아니다.

- 다음 세션은 그때의 원격 최신 main·관련 열린 PR·로컬 변경을 확인하고 AGENTS와 이 문서를 읽습니다. 과거 적용 SHA를 개발 head로 고정하지 않습니다. EES Work의 현재 작업은 [4차 UI 후속 수정](../evals/v4-ui-20260930.md#v4-ui-breakage-fix)이며 #69 병합3a51의 종료 실패와 PR #70 병합 뒤의 retained_bundle_mismatch 후속 수정·최신 main/열린 PR을 먼저 확인한다. 설치본713·등록 프로세스 잔류·listener 부재 보고 뒤의 실제 복구 결과부터 확인하며 과거 Status 확인을 반복하지 않는다. PR #68은 main에 병합됐고 사용자가 사내 화면 파손을 보고했다. 이번 권한은 09-30 18:04의 #69 후속 승인에 근거하며 완료한 수정/검사를 반복하지 않는다. #67까지의 C안은 병합된 기반이며 종료된 시각 작업을 재개하지 않는다. 기존 [09-29 C안 2단계](mockups/ees-work/TASK.md#c-design-phase2-20260929)와 [검토 보완](mockups/ees-work/TASK.md#c-design-phase2-review-20260929)을 보존하고 [3차 개발환경 검수](mockups/ees-work/TASK.md#c-design-phase3-20260929)를 완료했다. 완료된 1·2단계·보완·3차 검사를 미완료로 보아 반복하지 않는다. [09-23 A안](mockups/ees-work/TASK.md#a-design-20260923)·Figma 478:131/498:363은 기존 구현 근거로 보존하고 [09-22 단계별 UX](mockups/ees-work/TASK.md#step-progress-ux-20260922)·[확정 왼쪽](mockups/ees-work/TASK.md#sidebar-final-20260922)·[오른쪽 기록 계약](mockups/ees-work/TASK.md#right-panel-20260922)을 보존합니다. 기존 HTML·223번 통합안·공동 작업 장기안은 이번 단계별 진행 화면을 대체하지 않습니다. 새 ZIP이나 이전 대화 전체가 없어도 이 경로에서 이어갑니다. 별도 인계 파일은 만들지 않습니다. 수락 보호는 [적용 가이드](03-openwebui-native-agent.md#ees-accept64-guard)·[장애·검증 근거](../evals/scenarios.md#accept64-guard-20260914)를 보존하며 관련 변경이 있을 때만 해당 코드/시험을 읽습니다.
- 브랜치 정리 완료: 사용자 `branch_cleanup=ok, deleted=32` 보고와 원격 조회로 대상 32개 삭제를 확인함. 정리 당시 남은 브랜치는 `main`과 미병합 커밋 3개가 있는 `fix/upgrade-apply-failure`였으며, 미병합 head `b088f3be029dae108d82d6feec003fbd55bf5245` 보존을 확인함. [고정 대상·완료 근거](../evals/scenarios.md#repository-maintenance-20260911).
- 사내 결과 전달은 직접 타이핑 1~2줄만 가능함. 전체 로그·파일·사진을 요구하지 않으며 복사 블록은 각각 2,500자 이내. 기존 clone·Git 프록시 설정 완료 보고를 재사용하고 허용된 외부 호스트·기존 캐시만 전제함. 웹 프로젝트 지침의 저장소 참조 문구도 이미 설정한 것으로 유지함.
- 등록된 `manage-ees.ps1`의 Python·작업 위치·주소·DATA_DIR·DB·키·계정을 유지함. 설치 예제의 loopback·기본 폴더로 현재 등록값을 덮지 않음. [등록 설정과 기록 위치](03-openwebui-native-agent.md#ees-local-state). 중단한 후보 환경 Diagnose/Deploy는 재개하지 않으며 과거 도구·실패·복구 증거는 보존함.
- 현재 사내 모델은 [GLM 5.3 UI 반영 보고](../versions.md#사내-모델-운용-기준)를 따르며 작은 Tool·짧은 절차·일반 JSON을 유지함. 과거 GLM 5.2 결과를 새 모델의 검증으로 바꾸지 않고 다음 관련 사용에서 대표 업무·실패/금지 요청을 비교함. 화면·답변에 이모지를 쓰지 않음. 기존 Hermes·팀원 작성물은 보존하며 서비스화·서버 이전·별도 Router/A2A/자동 동기화·공통 UI 프레임워크는 실제 필요에 따라 후속으로 다룸. [공통 자산 관리 경계](../README.md#원본과-배포본).

## 최근 점검

2026-10-01 Step0-B: 기본 계약과 미확정 상세 경계 반영, 저장소 검증환경 준비, 실제 Native CLI/합성 데이터 브라우저 왕복, 관련8개 회귀를 검증했다. 제품/CI는 변경하지 않았으며 기본 설계·시험 도구 커밋을 분리했다. [이번 평가](../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001)에 원래 실패·후속 실패·재검·원격 CI를 각각 보존한다.

상태가 바뀔 때만 이 문서를 갱신하고 다음 작업 하나·현재 미해결·최근 점검 요약을 유지합니다.
