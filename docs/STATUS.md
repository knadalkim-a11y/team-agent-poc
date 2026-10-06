# 현재 작업 상태

## 2026-10-06 · C15 권한별 메뉴와 Open WebUI 왕복

- **기준:** 최신 첨부의 추가 E를 같은 [Draft PR #76](https://github.com/knadalkim-a11y/team-agent-poc/pull/76)에 반영한다. 착수 head `e9a34e16d158c7553cfcf66a2cfc01ff794ebbd0`의 [CI 37427430144](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/37427430144)는 24 success·기존 조건부1skip이며, main은 `e55bfb125ddf84d14030b1b56bb604bd8b14d088`이다. 선행 #74/#75 병합과 C15 이후 변경 없음, 기존 A–D 본문 동일을 확인했다.
- **구현:** [착수 비교표](mockups/ees-work/TASK.md#menu-integration-20261006)에 따라 세 메뉴 묶음·서버의 실제 Native 권한·직접 경로·원래 위치 복귀를 추가했다. Native 관리자 설정의 모달 redirect와 계정 전환 중 늦은 flush를 보완했다. 관측 가능한 이미지/업로드 중 첨부는 이동을 차단하고 이유를 표시한다.
- **로컬 검증:** 서버73·실제 Native 계정 API6개 통과. Node 관련 범위225개는 freeze2의 author95/execution64와 마지막 runtime66을 합친 범위이며 단일225개 실행은 아니다. 최종 build4의 실제 Native5개는 PASS/0skip/exit0이며 스킬 검색·관리자 모달 왕복·미저장 작성 값·이미지 차단·직접 진입/삽입점 부재·역할 메뉴를 확인했다. build4 SHA256은 `ecf138543e933a6c8ecefa13887c8210142068bb47e06e4743f9a25661a86c1a`다. [최초 실패·빌드·시각 보완·한계 기록](../evals/v4-ui-20260930.md#menu-integration-evidence-20261006)을 보존한다.
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
