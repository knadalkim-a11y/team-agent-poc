# 실행 방식 제거·도구 연결 전 게시 검증 기록 · 2026-11-02

<a id="no-run-mode-20261102"></a>

## 2026-11-03 · PR #115 CI439 후속

- **병합 요청·기준:** 사용자 “병합하고 진행해”에 따라 head `08d18280f1d1614dc988e23bdfa4333acb6105e1`과 main `20bafd0`을 확인했다. [CI439](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41547709688)의 `native-compose`가 실패했고 다른 29개 job은 성공했다. 실패를 보존하고 수정 head의 필수 CI 성공 뒤 병합한다.
- **확인된 원인:** 작성 브라우저 시험 두 개가 새 절차에 없어진 `mode`를 직접 읽어 KeyError가 났다. 그중 기본 절차 복사 시험에는 도구 미연결이 게시 오류라는 옛 기대도 남아 있었다. 서비스·Node 기대값은 앞서 바꿨지만 실제 Native 작성 시험의 이 경로가 빠졌다. 별도 시각 시험은 compact 속성이 바뀐 뒤 폭 전환이 끝나기 전에 사이드바를 측정해 56px 대신 90.578125px를 읽었다. 기존 레이아웃·motion 시험은 전환 종료를 기다리지만 작성 viewport helper에는 누락됐다.
- **조치:** 기존 시험 ID를 유지하고 새 절차의 mode 부재·게시 오류 없음·도구 연결 경고·게시 가능을 검사한다. 게시/실행하지 않았다는 단언은 보존한다. 작성 viewport helper는 기존 Native 시험과 같은 `getAnimations()` 종료 조건을 기다리고 치수 단언은 완화하지 않는다. 제품 코드는 변경하지 않는다.
- **로컬 검증:** Linux, Python 3.11.17·CI 고정 의존성, Node 22.22.0. 작성 UI Node 269/269, 기본 예시 서비스 시험 1/1, Python 구문 검사, 시험 ID 감사(기존 1,332/현재 1,586·오류 0), 문서 점검을 통과했다. 실제 Native·Windows는 새 head CI로 확인하며 로컬 통과로 대신하지 않는다. 사내 적용은 하지 않는다.
- **재발 방지:** 사라진 정의 필드의 읽기와 그 뒤 도달하지 못했던 게시 단언까지 같은 시험에서 함께 대조했다. 동작 속성 변경과 애니메이션 종료를 구분하는 기존 helper 기준을 적용했다. 새 시험 삭제·건너뛰기·시간 제한 확대는 없다.

## 2026-11-02 · 실행 방식 제거와 도구 연결 전 게시

이 기록은 처음 [4차 UI 기록](v4-ui-20260930.md)에 썼다. Windows 줄바꿈(CRLF)에서 그 파일이 문서 점검의 1 MiB 한도를 넘어, 2026-11-02에 이 파일로 옮겼다.

- **요청·범위:** 사용자가 ‘게시 전 확인’에서 `j-44c6d08dbe10: 검증된 Native 도구 참조가 필요합니다.`가 무엇인지 묻고, 도구가 없어도 게시할 수 있어야 한다고 했다. 또 주기·수시·비상 구분이 맞지 않는다고 판단했다. 결정과 명세 밖 판단은 [변경 계약](../docs/mockups/ees-work/TASK.md#no-run-mode-20261102)에 있다. 출발점은 main `745e5ef99528bfcb4947e720d11f02f7abf727bf`이고, 작업 브랜치는 `ccr-5c97dda0-jb5rxv`다.
- **출발 상태(관측):** main 기준으로 확인했다.
  - 기본 예시 3개(배포 산출물 점검·신규 공장 횡전개·일일 시스템 점검)는 게시를 막는 오류가 각각 4·4·1개였다. 모두 도구를 연결하지 않은 ‘도구로 처리’ 작업이 원인이었다.
  - 단계 실행은 도구 미연결 작업에서 거절되면 단계 전체를 ‘막힘’으로 끝냈다. 그래서 뒤에 있는 연결된 작업도 실행되지 않았다(`ees_workflow_operations.py`).
  - 비상은 시작 직후 단계를 자동 실행했다. 같은 공장 중복 금지는 수시에만 걸렸다.
  - 바꾸기 전 services 시험은 모두 통과했다.
- **구현:**
  - 도구 미연결 판단을 `tool_connection_required()` 하나로 모았다. 게시 전 확인은 확인 권장만, EES 요청 작업은 계속 오류로 남는다.
  - 서버는 작업 실행·단계 실행 모두에서 `tool_connection_required`로 거부하고, 화면은 실행 단추를 끄고 ‘도구 연결 필요’를 표시한다.
  - 작성 화면에서 실행 방식 탭·일정·예약 만들기를 없앴다. 시작 입력은 업무 내용 탭으로 옮겼고, 게시 기록 탭에 이전 예약 목록과 멈추기를 두었다.
  - 장애 진행 건은 분류 기준으로 내 업무 맨 위에 올린다. 중복 시작 예외는 `concurrent_runs_allowed()`가 판단하며, 비상 자동 실행은 없앴다.
  - 시작 창을 하나로 합쳤고, 도움말·예시·질문 문구를 고쳤다. 저장 형식과 예약 서버는 바꾸지 않았다.
- **첫 검사·발견·보완:**
  - 바뀐 동작을 단언하던 기존 시험이 실패했다(Python 8개, Node 10개). 사용자 결정에 맞게 고치되 보존·권한·저장 단언은 남겼다. 처음 고친 시험 하나는 fixture의 mode를 비어 있다고 가정했다. 실제 값은 `on_demand`여서 원래 값과 비교하도록 바로잡았다.
  - 새 시험이 결함 하나를 찾았다. 도구 미연결 작업에 조회 재시도가 있으면 `read_retry_invalid`가 먼저 나왔다. 그래서 `execute()`에서 도구 연결을 먼저 검사하도록 고쳤다.
  - 시작 창에서 대화 연결을 없애면서 `link` 변수가 남아 ReferenceError가 났다. Node 시험이 이를 잡았고, 해당 호출을 지웠다.
  - 한 번은 결과를 `head -40`으로 잘라 보아서 `test_ees_work_figma_runtime_ui.cjs`의 실패 3개를 놓쳤다. 스크립트를 직접 다시 실행해 찾았고, 시험 기대값을 새 결정에 맞췄다. 통과 여부는 잘린 출력이 아니라 집계 줄과 종료 코드로 판정한다.
  - **frontend 고정 해시 누락(커밋 전 발견):** frontend 패치의 질문 ② 문구 2줄을 고치고도 `frontend/open-webui-source.json`의 해시를 갱신하지 않았다. 빠진 값은 패치 해시와 패치 결과 파일 2개(`EesProcedureIntro.svelte`·`ko-KR/translation.json`)의 해시다.
    - 원인: services·contracts 시험만 실행하고 platform의 frontend 시험을 빠뜨렸다. [설치 가이드](../docs/01-openwebui-install.md)에는 이미 ‘패치를 바꾸면 패치·패치 결과 해시도 갱신’ 규칙이 있다.
    - 발견: 커밋 전 전체 diff를 다시 읽다가 찾았다. 갱신 전 값으로 `test_ees_frontend_build.py`를 돌리면 오류 11개가 났다. #113의 첫 로컬 실패와 같은 유형이다.
    - 새 값 계산: 고정 커밋의 원본 20개를 받아 해시가 맞는지 확인했다. 이전 패치를 적용해 기존 고정값 2개를 그대로 재현한 뒤 새 값을 계산했다.
    - 확인: 새 패치 전체가 `git apply --check`를 통과했고, 패치 결과 29개 해시가 모두 맞았다.
- **최종 로컬 결과(2026-11-02, Linux 컨테이너):** 환경은 Python 3.11.15 `.venv`(ees-delivery 고정 의존성)와 Node v22.22.0이다. CI 고정 버전 Node 22.16.0/npm 10.9.2와는 다르다.
  - `ees_delivery_suite.py --suite services`: 505개 실행, 502 통과·0 실패·3 건너뜀. 바꾸기 전과 같은 건너뜀 수다.
  - Node 12개 스크립트: 661/661 통과(작성 265·실행 화면 146·실행 131 포함).
  - `--suite contracts`: 0 실패지만 실제 wheel·Native가 필요한 52개를 건너뛰어 ‘미완료’다.
  - `--suite platform` 전체: 732개 실행, 637 통과·0 실패·95 건너뜀(Native·Windows·실제 patched checkout 필요). 그중 `test_ees_frontend_build.py`는 19 통과·13 건너뜀이다.
  - 시험 ID 감사: 오류 0(기존 1,332 / 현재 1,582).
  - 문서 점검과 `git diff --check`도 통과했다.
- **main 합치기(2026-11-02):** 그사이 main에 #114(`20bafd0`)가 병합돼 이 브랜치에 합쳤다. 컨테이너가 새로 만들어져 `.venv`가 사라졌으므로, CI의 `EES_FIXED_TEST_DEPENDENCIES`로 Python 3.11.18 `.venv`를 다시 준비했다.
  - 충돌 8개: 코드 2개(`ees-work-designer.js`·`ees-work-view.js`)는 main 쪽 줄을 기준으로 두고, 이 변경의 일정 코드 삭제와 ‘도구 연결 필요’ 표시를 다시 적용했다. main이 바꾼 아이콘 이름(`a9175`)과 도구 관련 코드는 그대로 두었다. 기록 문서 5개는 양쪽 항목을 모두 남겼다(이 변경을 위에).
  - frontend 고정 해시: main 쪽 값에서 시작해, 고정 커밋 원본 20개(해시 일치)에 합친 패치를 적용했다. 결과 29개 중 main 값과 다른 것은 이 변경의 2개(`EesProcedureIntro.svelte`·`ko-KR/translation.json`)뿐이었고, 값은 합치기 전 계산과 같다. 패치 해시는 `bc16e48b…`로 갱신했다.
  - 합친 뒤 시험: Node 12개 스크립트 667/667(작성 268·움직임 Svelte 29 포함), services 506개 실행·503 통과·0 실패·3 건너뜀, contracts 58 통과·0 실패·52 건너뜀, platform 732개 실행·637 통과·0 실패·95 건너뜀(frontend 19 통과·13 건너뜀).
  - 시험 ID 감사 오류 0(기존 1,332 / 현재 1,586), 문서 점검·`git diff --check` 통과.
- **미실행·남은 확인:**
  - 고친 Native·브라우저 시험(`test_ees_work_figma_authoring_native.py`, `ees_work_integrated_app.py`)은 CI가 빌드한 wheel이 필요해 실행하지 않았다.
  - Windows·최종 CI·사내 적용도 하지 않았다.
  - 사내에 맡겨 둔 예약이 있는지는 볼 수 없다. 그 예약은 그대로 돌고, 게시 기록에서 멈출 수 있다.
  - 명세 밖 결정(중복 시작 예외·단계 기한 미구현·시작 창 선택 제거)은 결정표로 알렸고, 사용자가 바꾸지 않아 유지한다(2026-11-02).
- **PR #115 첫 CI 실패와 조치:** 합치기 커밋 `5754f71`의 [CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41544296558)에서 Source audit (windows-2022)의 문서 점검이 실패했다.
  - 원인: `evals/v4-ui-20260930.md`는 LF로 1,045,579바이트였지만 Windows CRLF로는 1,049,324바이트가 되어 `check_docs.py`의 1 MiB 한도(1,048,576바이트)를 넘었다(`document_too_large`). 이 기록을 더하기 전 main에서는 CRLF 1,040,482바이트였다.
  - 재현: 저장소 사본의 문서 27개를 CRLF로 바꿔 같은 점검을 돌려 같은 오류를 확인했다. Linux 로컬 점검은 LF 크기만 보므로 통과했다.
  - 조치: 이 기록을 이 파일로 옮기고 이 기록을 가리키던 링크(STATUS·TASK·CHANGELOG·시나리오)를 고쳤다. #114가 같은 원인으로 탐색·패널 기록을 [별도 파일](navigation-motion-20261102.md)로 옮긴 것과 같은 방식이다.
  - 검증: 고친 커밋 `91927ed`의 사본을 같은 방법으로 CRLF로 바꿔 점검했고 `DOCS OK`(문서 28개, 오류 0)였다. CRLF 크기는 `evals/v4-ui-20260930.md` 1,040,482바이트(main과 같음), 이 파일 약 10KB다. 시험 ID 감사도 오류 0이다. CI 결과는 PR #115에서 확인한다.
- **Codex 리뷰 지적과 조치(`ac7b0f6`, P2):**
  - 증상: 진행 건 상세의 ‘단계 실행’·‘절차 실행’ 단추가 도구 미연결 작업이 남으면 꺼진 채로 그려진다. 그런데 `panel()`이 곧바로 부르는 `setBusy()`가 `data-own-disabled="true"` 표시가 없는 `data-mutation` 단추를 모두 다시 켰다. 서버가 `tool_connection_required`로 거부하므로 실행되지는 않지만, 화면은 실행할 수 있는 것처럼 보였다.
  - 원인: 같은 PR의 단계 화면 단추와 작업 줄 단추에는 표시가 있었고, 진행 건 상세의 단추에만 빠졌다. 시험도 단계 화면만 확인했다.
  - 조치·검증: 표시를 더했다. 진행 건 상세에서 두 단추가 표시와 함께 꺼져 있는지, 그 작업을 제외하면 다시 켜지는지 보는 시험을 더했다. 고치기 전 코드에서는 이 시험이 실패하고 고친 뒤에는 통과한다. Node 시험은 668개 모두 통과했다.
  - 재발 방지: 꺼진 단추에 표시를 함께 붙이는 것은 기존 단추들이 따르는 관례라 새 지침은 만들지 않고 시험으로 막았다.
- **통합 브라우저 시험 실패와 조치(`ac7b0f6`):**
  - 증상: [CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41545158588/job/125622188340)의 Complete Native product에서 `tests/ees_work_integrated_app.py`가 `[data-author-action="start_input_add"]`를 누르지 못했다(`Not clickable`).
  - 원인: 작업을 추가하면 그 작업의 상세가 열린다. ‘시작할 때 받는 값’은 단계와 작업 화면에만 있다. 예전에는 시험이 ‘실행 방식’ 탭을 눌러 선택이 풀렸는데, 이 PR에서 그 클릭만 지우고 돌아가는 동작을 넣지 않았다. 제품 결함이 아니라 시험 순서의 잘못이다.
  - 조치: 시험이 작업 상세 머리의 ‘단계와 작업’ 링크로 돌아간 뒤 시작 입력 단추를 누르게 했다. UI 시험에 같은 흐름을 더했다(작업을 추가하면 단추가 없고, 링크로 돌아가면 있다).
  - 검증: 새 UI 시험 통과, Node 669/669. 이 개발 환경에서는 CI가 만든 프로그램을 받을 수 없어(저장 서버 `productionresultssa10.blob.core.windows.net`이 네트워크 정책에서 막힘) 통합 브라우저 시험을 로컬에서 다시 돌리지 못했다. CI 결과로 확인한다.
  - 재발 방지: 로컬에서 돌릴 수 없는 브라우저 시험의 단계를 고칠 때는, 그 단계 직전의 화면 상태를 UI 시험으로 먼저 확인한다. 이번 한 번의 사례라 지침에는 올리지 않고 이 기록에 남긴다.
  - 재발 방지: #114에 이어 두 번째로 같은 유형이 나왔다. 빠진 이유는 로컬 점검이 Windows CRLF 크기를 보지 못하는 것이다. 점검기에 CRLF 기준 크기 검사를 넣는 일은 이 PR 범위를 넓히므로 따로 제안한다.
- **Figma(C133 · 백업 B067):**
  - ‘워크 · 업무 절차’ 13판, 운영 33판으로 갱신했다. 실행 방식 화면 5개를 91 · 보관 `1970:10201`로 옮겼다.
  - 다른 페이지의 규칙·대응표·탭·꼬리표 문구도 정리했다. 바뀐 노드의 전후 값과 일부러 남긴 표시는 [전후 기록](artifacts/no-run-mode-20261102/figma-c133-changes.json)에 있다.
  - `scripts/figma_check.js` 결과는 오류 0이다. 경고 두 가지 중 ‘워크 · 업무 절차’ 요소 10,545개·글자 61,221자의 정리 신호는 해소하지 않았다. B067 기록 경고는 C133 줄의 첫 언급으로 해소되는 조건이다.
  - `get_screenshot` 내려받기는 프록시 403으로 막혀, `use_figma`의 노드 캡처로 확인했다.
- **재발 방지:**
  - 도구 미연결 판정을 정의 모듈 함수 하나로 모았다. 게시 전 확인, 작업 실행, 재시도 실행, 단계 실행이 같은 함수를 쓴다.
  - 게시 허용·실행 거부·EES 요청 차단·순서(재시도보다 먼저)를 회귀 시험으로 막았다.
  - 시험 출력 잘림으로 실패를 놓친 일은 이 기록에 남겼다. 지침에 일반 규칙으로 올리지 않은 것은 기존 ‘필요한 증거 확보’ 원칙으로 충분하다고 판단했기 때문이다.
  - frontend 고정 해시 누락은 기존 가이드 규칙과 frontend 시험(오류 11개)이 이미 막는 유형이다. 이번에 빠진 것은 시험 선택이다. 패치를 바꾸면 platform의 frontend 시험을 함께 돌린다는 점을 이 기록에 남기고, 새 지침은 만들지 않았다.


### 2026-11-03 · 최종 CI440와 #115 병합

- CI439의 30개 job 언급은 첫 조회 범위였다. 전체 40개 최종 집계는 36성공·2실패·1취소·PR 출하1정상생략이다. 실제 시험 실패 native-compose와 이를 반영한 Delivery checks 실패/취소를 구분한다.
- 보완 head `0b1338840276248cc59d60e62878eebef8d7c0bc`의 [CI440](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41553995759)은 39성공·PR 출하1정상생략. Native 작성·브라우저·전체 제품, Windows 및 양쪽 Delivery checks가 모두 통과했다.
- 사용자 “병합하고 진행해” 요청에 따라 [#115](https://github.com/knadalkim-a11y/team-agent-poc/pull/115)를 main `253cb3c6a16880aeb8be7113ecb7006a6f15585c`에 병합했다. 병합 뒤 Figma B067을 정리했다(C134에 기록). 사내 적용은 하지 않았다.


## 2026-11-05 후속 · 게시 상태를 완성도와 분리

[사용자 계약](../docs/mockups/ees-work/TASK.md#procedure-publication-20261105)이 위 11-02의 게시 차단 조건을 대체한다. 불완전한 EES 요청도 목록 게시가 가능하며 실제 시작/실행은 준비 검사로 막는다. 기존 자동 실행 금지·Native 권한과 도구 지문·근거 검증은 그대로 유지한다.

로컬 검증과 최종 통합 CI는 이 변경 PR에 기록한다. 업무절차 DB의 기존 행·진행 건·버전은 이동하거나 삭제하지 않는다. Figma 14판 상태/버튼을 갱신했으며, 화면 캡처의 게시 상태·저장·게시·미게시로 변경이 겹치지 않는지 확인했다. 사내 실제 적용·기존 5개 절차 게시 여부는 아직 확인하지 않았다.

CI452 (`28bc7af`)에서 이전 문구를 기다리던 Native 계정·제품·빈 목록 시험과 이전 게시 차단 기대를 확인했다. 새 문구·실제 메뉴 진입으로 갱신하며 저장 revision 확인은 보이는 문구 대신 `data-author-revision`과 기존 서버 데이터 단언으로 유지한다. 로컬 Chromium은 소켓 생성 제한으로 브라우저가 기동되지 않아 제품 브라우저 판정은 CI의 실제 Chrome에서 수행한다. 기존 데이터 보존/권한/실행 차단 단언은 제거하지 않았다.

공용 도구의 인자·결과 형태 검증도 시작 경로에서 수행한다. 공장 조건으로 제외된 작업은 실행 검사 대상에서 제외하고, 시작 권한은 작성 권한이 아닌 참여 권한으로 확인한다. 이는 기존 정상 참여자 실행과 조건 제외 동작을 유지하면서 미완성 게시가 잘못된 연결의 실행으로 이어지지 않게 하는 범위다.

공식 wheel을 사용하는 로컬 공용 도구 Native 43건을 모두 통과했다. CI452의 새 실제 브라우저 시험은 미완성 게시·업무 목록 표시·미게시 전환·목록 숨김과 버전 보존을 통과했다. 같은 실행의 기존 작성 시험 2건은 예전 저장 차단/문구 기대 때문에 실패했고 새 계약으로 갱신했다. 작성 중 미게시로 변경한 뒤에도 입력을 보존해 저장되는 회귀 시험을 포함한 Node 작성 UI는 272건 통과했다. 편집 항목 바로 저장과 360px 하단 단추 시험도 추가했다. 이 증거는 최종 전체 CI의 성공을 대신하지 않으며 최종 판정은 PR에 기록한다.

PR 리뷰의 입력 범위 변경 지적을 `930e492`에서 재현했다. 기존 공통 설정의 입력을 이번 진행 건/공장 입력으로 바꾸거나 삭제한 뒤 게시하면, 새 진행 건 시작 때 예전 값이 남는 4개 조건이 실패했다. 기존 설정 호환성 검사를 내용 확인과 새 시작이 함께 쓰도록 정리했다. 게시는 계속 허용하고, 새 시작은 시스템 공통 설정과 해당 공장 설정만 확인한다. 다른 공장의 불일치는 현재 공장을 막지 않는다. 설정을 정리한 뒤에는 이전 값 없이 정상 시작한다. 회귀 시험 2건을 포함해 workspace 85·operations 54·Figma 계약 24건 통과. 기존 진행 건/설정 데이터를 자동 변경하지 않는다.

CI456 (`77ca5cd`)의 실제 전체 제품과 새 미완성 게시/360px 흐름은 통과했다. 작성 Native의 C44 동시 편집 시험 한 곳이 여전히 상태 문구에 `r4`가 나타나기를 기다려 실패했다. 앞선 고정 문자열 검색에서 동적으로 조합한 기대값을 놓쳤다. 모든 `data-author-status` 참조를 다시 확인하고 이 한 곳도 `data-author-revision`을 비교하게 고쳤다. 동시 편집 경고·포커스·양쪽 입력 보존·불필요한 저장 없음 단언은 그대로 유지한다. 제품 코드 변경 없이 최종 전체 CI로 확인한다.


### 2026-11-05 · 공장별 참여 권한을 새 시작 검사에 전달

- **재현:** PR #120 `2578073`에서 특정 공장 `f1`에만 participant 권한이 있는 합성 사용자가 승인된 기존 방식 요청 도구를 포함한 게시 절차를 시작하면 `execution_not_ready / j1: scope_forbidden`이 발생했다. 같은 SQLite 시험 자료로 변경 전 제품 코드는 정상 시작했다. 기존 workspace 85·operations 54·작성 UI 272건은 통과했지만 공장 한정 권한과 기존 도구 계약을 함께 다루지 않았다.
- **원인·수정:** 시작 경로의 `validate_publication(authoring=False)`가 선택 공장을 받지 않아 빈 공장 범위로 다시 권한을 검사했다. 실행 준비 검사에 선택한 `factory_id`를 전달하며 작성 검사는 기존 시스템 manager 범위를 유지한다.
- **검증:** Linux/Python 3.12에서 `-X warn_default_encoding -W error::EncodingWarning`으로 operations 55/55·workspace 85/85 통과. 새 회귀 시험은 f1 participant 정상 시작, f2 viewer·공장 없는 시작 거부, participant 작성 검사 거부, 진행 건 한 개만 생성됨을 확인했다. 이전 실패·기존 범위 검사·실제 사용자 자료는 보존한다. 최종 통합 head의 Native·Windows 전체 검사는 [PR #120](https://github.com/knadalkim-a11y/team-agent-poc/pull/120)에서 판정한다.

- **main 통합:** #118 최종 head `791ddb6`의 CI462 39성공·출하1정상생략과 병합 main `818e31c`을 확인하고 #120에 merge로 통합했다. #118·#119·#120의 STATUS·CHANGELOG·사용 안내·TASK 기록을 모두 보존하고 문서·diff 검사를 다시 통과했다. 최종 CI는 이 통합본에서 새로 실행한다.


<a id="publication-save-20261106"></a>

## 2026-11-06 · 게시 상태 선택과 저장 통합

- 기준: #125 병합 main `7a56cdbbcbf104a8a0847a446e951d262907a167`. 사용자 승인에 따라 업무절차17판의 상태 선택/저장을 구현한다. 도구의 수정본 저장/사용 설정 계약은 바꾸지 않는다.
- UI: 상태만 바꿔도 미저장 표시·저장 활성화, 다른 절차 왕복·외부 refresh 보존, 원래 상태로 되돌리면 깨끗한 상태, 계정 전환 정리, 실패 후 재시도. 저장 전에는 서버 요청을 만들지 않는다.
- 서버: 게시 상태 save_draft는 제출 내용으로 참조 검사 후 같은 트랜잭션에서 편집본·버전·포인터·revision·receipt를 저장한다. 중복 request는 한 번만 반영하고 재시도에도 권한을 다시 확인한다. 미게시 저장·재게시에도 과거 버전과 진행 건 snapshot은 유지한다.
- 회귀: 기존 publish 버튼 기대6개가 실패해 상태 선택/단일 저장·서버 미변경/변경의 실제 계약으로 갱신했다. 검사 범위를 없애지 않고 게시 중 수정 반영·실패 선택 보존·state-only refresh를 추가했다. `node --test --test-reporter=tap tests/test_ees*.cjs`:733/733, workspace88/88, operations55/55 통과. SQLite version INSERT 실패 주입 뒤 내용·revision·포인터·버전·receipt 전체 rollback과 정상 재시도, stale revision과 접근 회수도 확인했다.
- 빌드: main CI 산출물(검증된 공식 wheel·source frontend)을 재사용하려던 첫 빌드는 `Frontend inputs differ from this wrapper checkout; rebuild in CI.`로 중단했다. 변경된 UI 입력을 탐지한 정상 보호이며 manifest/컴파일 결과를 우회 수정하지 않는다. 최종 head의 CI 새 source 빌드와 실제 Native 검증으로 확인한다.
- Figma: 업무절차 페이지1285:1829·루트1804:2546, 대표 패널1804:2551/1804:2673, 이전 B070 보존. 열 개 편집 화면에 상태 선택·단일 저장을 반영했다. 폰트/부품은 기존 것을 재사용한다. 라벨에 남은 상태 주황색을 공통 보조 글자 토큰으로 수정했다.
- 실제 Native·최종 CI·고정 점검은 진행 중. 사내 화면·실데이터·사용자 사용성은 미확인, 병합·배포는 미실행이다.

- 로컬 브라우저 첫 시도: CI494의 frontend ZIP `f6c6189d19929276b594fcb33e1f9ad624d6e1a8bce5415bfda84f5c88bd253e`를 검증해 공식 builder로 현재 wheel `c0e35f3f49bbccecd813d4a6a5d3161430125d4a8754d11b411759e4fef47a2f`를 조립했다. Chromium은 제품을 읽기 전 `process_singleton_posix.cc:297 socket() failed: Operation not permitted`로 종료했고 ptrace도 차단됐다. 두 대상 검사는 환경 준비 실패이며 제품 실패/성공으로 판정하지 않는다. 이 제한을 우회하지 않고 CI의 실제 브라우저를 사용한다.
- Figma 최종: 업무절차17판과 도구2.1판의 T08/T08A를 동기화하고 C156/PR126/B070을 기록했다. 고정 점검을 페이지당 한 호출로 나누되 기준·링크/이력 검사를 유지했다. 비백업17페이지 오류0, 기존 업무절차 크기 경고1(10,487요소·60,543자)은 관련 없는 대규모 정리 없이 보존한다. 기록 후 관리 페이지 재검사 오류0·경고0. [고정 PNG4개·해시](../docs/mockups/ees-work/procedure-publication-20261106/metadata.json)와 [점검 결과](../docs/mockups/ees-work/procedure-publication-20261106/figma-check.json)를 보존하고 실제 렌더를 직접 확인했다.
- 시험 ID 감사: `python tests/ees_delivery_suite.py --audit --output dist/procedure-test-id-audit`는1737개 오류0. 실제 브라우저 회귀는 상태 선택만으로 쓰기 없음·게시 중 내용 저장·미게시 저장 전후의 서버 포인터와 이력 보존을 추가 확인한다.

- 최초 CI494([실행](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/42133313139), head `6ac9433`, 통합 시험 commit `85fb305`): 실제 로그인·작성·저장·재시작·채팅·일반 사용자 실행을 포함한 Complete Native product는 성공했다. services의 `test_normalized_published_definition_never_replaces_the_authoring_draft`는 예전 “게시 중 저장 후에도 게시본은 human” 기대가 남아 실패했다. 제출 편집본이 게시본에 반영되는 기대와 저장 전 불변 단언을 함께 적용하고, normalized definition이 편집본을 덮지 않는 원래 단언은 유지했다. 해당 파일8/8 재검사 통과.
- CI494 실제1920 화면의 상태 선택란은 기존 Native appearance 초기화 때문에 화살표가 없었다. 선택 가능한 상태값임을 드러내도록 해당 select에만 `appearance:auto`를 지정하고 Figma의 입력 배경과 같은 공통 흰색 토큰을 사용했다. 최종 새 빌드 화면에서 다시 확인한다. 게시 상태·저장 동작/크기는 바꾸지 않는다.

- CI494 작성 Native40개 중39개가 통과했고 `test_procedure_visual_geometry_matches_figma_and_preserves_native_draft`는 선택란 글자가12px가 아닌13px로 계산돼 실패했다. 기존 일반 입력 규칙의 `:is(input:not(...),select,textarea)`가 선택란 규칙보다 우선해 padding/font를 덮었다. 새 상태 선택란의 ID에 한정한 규칙으로 우선순위를 맞추고12px 단언을 유지한다. 상태 선택·미완성 게시/미게시·도구 연결 흐름은 통과했다. 새 head로 넘어가며 남은 CI494 compose와 최종 집계가 취소됐으며, 이 실행을 전체 성공으로 간주하지 않는다.

<a id="doc-size-crlf-20261111"></a>

## 2026-11-11 재발 · 문서 점검 1 MiB 한도(Windows CRLF)와 점검기 보완

- **증상:** 브랜치 `ccr-5c97dda0-jb5rxv`에서 Figma 구조 개선 1단계 기록을 [4차 UI 기록](v4-ui-20260930.md)에 더한 커밋 `df8d483` 때, 그 파일은 LF 1,048,422바이트로 Linux 점검을 통과했다. 그러나 CRLF로는 1,052,195바이트라 한도(1,048,576)를 넘었다. 2단계 기록을 더해 LF로도 1,051,923바이트가 되자 Linux 점검이 `document_too_large`로 실패해서 드러났다. 이 브랜치에는 PR이 없어 CI는 돌지 않았다.
- **같은 유형:** #114(탐색·패널 기록), [#115](#2026-11-02--실행-방식-제거와-도구-연결-전-게시)(이 파일의 첫 CI 실패)에 이어 세 번째다. 두 번 모두 기록을 다른 파일로 옮겼고, Linux 로컬 점검이 LF 크기만 세는 원인은 남아 있었다. 계획 커밋 `a04e8cd` 때 CRLF 여유는 1,458바이트였다.
- **원인:** `*.md`에는 줄바꿈 규칙이 없어 Windows CI에서는 CRLF로 체크아웃된다. 그래서 같은 문서가 Windows에서만 한도를 넘는다.
- **조치:**
  - Figma 구조 개선 기록(조사·1단계·2단계)을 [별도 파일](figma-page-structure-20261110.md)로 옮기고 TASK·STATUS·CHANGELOG의 링크를 고쳤다.
  - [문서 점검기](../scripts/check_docs.py)가 문서 크기를 CRLF로 셌을 때로 본다. LF 줄마다 1바이트를 더하고 이미 CRLF인 줄은 그대로 센다. 이제 Linux에서도 Windows CI와 같은 결과가 나온다.
- **검증:**
  - 시험 `test_document_size_is_counted_with_windows_line_endings`를 더했다. 고치기 전 점검기에서는 실패하고 고친 뒤에는 통과한다(점검기 시험 44개 통과).
  - 옮긴 뒤 CRLF 크기는 4차 UI 기록 1,044,619바이트(여유 3,957), 새 파일 11,914바이트, 시나리오 35,633바이트 여유다. 저장소 문서 가운데 CRLF로 한도를 넘는 것은 없다.
  - Windows CI는 아직 돌지 않았다(PR 없음).
- **남은 항목:** 4차 UI 기록의 여유가 4KB가 안 된다. 새 기록은 주제별 파일에 쓴다. 넘으면 이제 로컬 점검에서 바로 오류가 난다.

<a id="ci-on-demand-20261117"></a>

## CI를 필요한 만큼만 실행 (2026-11-17)

- **요청·결정:** 사용자가 “CI는 최소화하고 필요할 때만 특정해서 실행”하기로 정하고 트리거 변경을 지시했다. main `3b7c653`에서 시작했고 관련 열린 PR은 없었다. 같은 시각 다른 세션이 업무 절차 등록 화면을 고치고 있어 그 파일(`ees-work-designer.js`, 작성 화면 시험)은 건드리지 않았다.
- **바꾸기 전 측정:** PR #147의 [실행 576](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44055042593)은 작업 40개, 작업 시간 합계 104.2분, 시작부터 끝까지 16.7분이었다. 가장 긴 경로는 프런트엔드 빌드 4.3분 뒤의 native-compose 10.6분과 Windows contracts 10.5분이다. README만 고친 PR #141도 같은 전체 검사를 돌았고, PR과 병합 뒤 main에서 한 번씩 두 번 실행됐다.
- **바꾼 것:**
  - PR에서는 빠른 검사만 자동으로 돈다. 시험 ID 감사, 문서 점검, 프로그램 빌드 없이 도는 services·platform 묶음과 계약 모듈 두 개(`test_ees_workflow_execution.py`, `test_ees_work_authoring.py`)다. 변경 경로 목록은 없앴고 모든 PR에서 돈다.
  - main push의 자동 실행을 없앴다. 그 밖의 검사는 Run workflow에서 범위(`full`·`quick`·`browser`·`linux`·`windows`)와 묶음 이름을 골라 실행한다.
  - main에서는 전체만 실행된다. 사내 Upgrade(`ees_update_download.py`)가 main의 성공한 실행을 전체 검사 통과로 믿으므로, main에서 부분 범위를 고르면 계획 단계가 실패로 끝난다. 프로그램 ZIP은 전체 범위에서만 만들고 기본으로 프로그램 wheel을 포함한다.
  - 범위별 작업, 묶음별 자료, 시간 제한을 `tests/ees_delivery_suite.py`의 `plan()` 한 곳으로 옮겼다. 워크플로에 따로 적혀 있던 묶음 목록과 자료 목록은 없앴다. 마지막 집계 작업은 모든 작업이 계획한 결과(성공 또는 건너뜀)로 끝났는지 비교한다.
- **빠른 검사에서 빠지는 것:** 프로그램 wheel이 필요한 시험은 건너뛴다. 로컬 실행 기준 services 3개, platform 98개, 계약 모듈 두 개에서 8개다. contracts 묶음의 나머지 네 모듈과 브라우저·설치·복구 묶음은 빠른 검사에 없다. 모두 전체 검사에서는 필수다.
- **검증:**
  - 로컬(Linux, Python 3.11.18, Node 22.23.4): 빠른 검사 통과(130초, services 649 통과, platform 653 통과), 계획 단위 시험 9개를 더한 `test_ees_delivery_suite` 20개 통과, 시험 ID 감사 오류 0, 문서 점검 오류 0.
  - GitHub, 작업 브랜치 `45ee699`: 빠른 검사 [실행 581](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44062928871) 성공, 2분 51초. 나머지 작업 8종은 건너뜀으로 끝났다.
  - GitHub, 같은 커밋: `browser` 범위에 `native-work` 묶음만 고른 [실행 582](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44062934057) 성공, 7분 43초. 프런트엔드 빌드, 프로그램 준비, native-work, 집계만 실행됐고 ZIP 작업은 건너뛰었다.
  - 전체 범위 [실행 583](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44064381780), 커밋 `611c2cc`. 첫 시도는 17.6분에 실패로 끝났다. 작업 37개가 성공했고 Ubuntu native-compose가 초점 시험 두 개로 실패해 집계가 실패했다. 실패한 시험은 [같은 날 실행 568과 같은 두 개](navigation-motion-20261102.md#narrow-viewport-load-20261117)이고, 같은 제품 코드의 main 실행 577은 통과했다. 이번 변경은 제품과 그 시험을 건드리지 않았다. 달라진 조건이 없어 기존 간헐 실패로 보고 실패한 작업만 한 번 다시 돌렸고(상한 1회) 통과했다.
  - **이번 변경의 결함(실행 583 둘째 시도에서 발견):** 모든 검사와 집계가 성공했는데 프로그램 ZIP 작업이 건너뛰어졌다. 전체 범위에서는 빠른 검사 작업이 건너뜀으로 끝나고, GitHub는 앞선 작업 가운데 하나라도 건너뛰면 기본 성공 조건에 기대는 뒤 작업을 건너뛴다. ZIP 작업은 집계 작업을 거쳐 빠른 검사 작업 뒤에 있었다. 부분 범위 실행 582는 ZIP을 만들지 않는 범위라 이 결함을 드러내지 못했다. 커밋 `8452e11`에서 ZIP 작업 조건에 필요한 결과(계획 성공, 집계 성공)를 직접 적고, 그 조건과 각 작업의 선행 작업이 계획과 맞는지 보는 시험을 더했다.
  - 수정 뒤 전체 범위 [실행 584](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44069983964), 커밋 `8452e11`. 첫 시도는 17.1분에 실패로 끝났다. native-compose는 통과했고 Windows platform의 `test_another_process_can_stop_saved_identity` 한 건이 `process_inspect`·`identity_unavailable`로 실패했다. [같은 날 실행 567과 같은 시험](tool-authoring-20261105.md#workspace-resource-and-guide-20261116)이고 이번 변경이 건드리지 않은 파일이다. 실패한 작업만 한 번 다시 돌려(상한 1회) 통과했다. 둘째 시도에서 작업 41개 성공, 빠른 검사 1개 건너뜀으로 끝났고 ZIP 작업이 프로그램을 포함한 묶음을 만들어 올렸다. 작업 브랜치의 실행이라 사내 Upgrade는 이 ZIP을 고르지 않는다.
  - 그 뒤 main `06cccd3`(PR #148)을 합친 `8819160`에서 빠른 검사 [실행 585](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44075405650)가 3분 6초에 성공했다. 합친 상태의 전체 범위는 실행하지 않았다. 이 줄을 더한 커밋은 문서 변경뿐이다.
- **전체 검사의 간헐 실패:** 전체 범위 두 번 모두 첫 시도에 실패했고 원인은 서로 다른 기존 간헐 실패였다. 재실행으로 통과한 것은 원인을 고친 것이 아니다. 전체 검사를 사내 배포 전에만 돌리게 되면 이 재실행이 배포 직전에 몰린다. 두 유형의 원인 조사 여부는 사용자가 정한다.
- **정리한 것:** 어디서도 불러오지 않는 시험 도구 다섯 개(1,707줄)를 지웠다. `tests/ees_work_c_phase1_app.py`, `ees_work_c_visual_fullapp.py`, `ees_work_c_visual_interactions.py`, `ees_work_c_visual_compare.py`, `ees_source_navigation_baseline.py`다. CI와 다른 시험, 스크립트에서 참조가 없고 과거 기록에 이름만 남아 있다. 9월 C 화면 수동 게이트와 특정 옛 커밋의 대조 게이트였고 지금은 `ees_work_integrated_app.py`가 전체 제품 검사를 맡는다. 원문은 커밋 `45ee699`에 있다.
- **미확인:**
  - PR 이벤트로 시작되는 실행은 PR을 만들지 않아 확인하지 못했다. 수동 `quick` 실행과 같은 작업을 쓴다.
  - GitHub 브랜치 보호에 필수 검사 이름이 걸려 있는지는 확인할 수 없었다. 집계 작업 이름 `Delivery checks (ubuntu-24.04)`는 모든 범위에서 유지하고, `(windows-2022)`는 전체 범위에서만 나온다.
  - 사내 Upgrade는 실행하지 않았다. 워크플로 파일이 프로그램 빌드 입력이라, 병합 뒤 첫 사내 적용 전에 main에서 전체 검사를 한 번 실행해 새 프로그램 ZIP을 만들어야 한다.
- **재발 방지 연결:** 운영 방법은 [가이드의 검사 범위](../docs/03-openwebui-native-agent.md#ci-scopes), 판단 기준은 [AGENTS의 CI 실행 비용 관리](../AGENTS.md#ci-cost)에 반영했다.

<a id="flaky-root-cause-20261118"></a>

## 전체 검사 간헐 실패의 원인 조사 (2026-11-18)

사용자가 [CI 실행 방식 변경](#ci-on-demand-20261117) 뒤 간헐 실패 두 유형의 원인 조사를 지시했다. main `368a60f`(PR #149 병합)에서 시작했다. 실패가 기록된 시험은 여섯 개이고 원인은 다섯 가지다. 다섯 가지 모두 재현하거나 측정해 확인했다. 하나(Windows)는 제품 결함이고 넷은 시험 쪽 문제다.

### Windows · 프로세스 종료 시험 (제품 결함)

- **증상:** Windows platform의 `test_another_process_can_stop_saved_identity`가 `process_inspect`·`identity_unavailable`로 가끔 실패한다. [실행 567](tool-authoring-20261105.md#workspace-resource-and-guide-20261116), 실행 584, 이전의 CI327·CI426과 같은 시험이다. 실행 584의 값은 오류 5(접근 거부), 0.27초였다.
- **확인된 원인:** Windows에서 프로세스는 종료 코드가 정해진 뒤 핸들이 신호 상태가 되기 전까지 실행 파일 경로 조회(`QueryFullProcessImageNameW`)를 접근 거부로 거절한다. 제품의 `_windows_identity`는 조회가 실패하면 같은 핸들을 대기 시간 0으로 한 번만 다시 보고, 아직 신호 전이면 ‘검사할 수 없는 살아 있는 프로세스’로 판단해 오류를 냈다.
- **측정(수정 전, [임시 실행 44190057410](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44190057410), windows-2022 빌드 20348, Python 3.11.9):**
  - 종료 신호 뒤 같은 Windows 호출을 연속으로 불렀다(80번, 표본 273,575개). 80번 모두에서 `GetProcessTimes`는 성공하고 경로 조회만 오류 5로 실패하는 상태가 있었다. 그때 종료 코드는 이미 0이었고 핸들은 1.5~2.5ms(중앙값 1.7ms) 뒤 신호됐다.
  - 제품의 `_identity()`를 같은 방식으로 부르면 80번 가운데 80번 `process_inspect`·`identity_unavailable`·오류 5를 냈다.
  - 시험과 같은 상황(다른 프로세스가 `stop_server` 호출)은 200번 가운데 0번 실패했다. 제품은 0.1초 간격으로 확인하므로 2ms 구간에 걸리는 일은 드물다. CI의 간헐 실패가 이 경우다.
- **조치(`71ae4da`):** 조회가 거절되면 같은 핸들을 최대 2초 기다린다. 그 안에 신호되면 정상 종료로, 아니면 전과 같은 오류로 처리한다. 다른 핸들이나 PID로는 판단하지 않는다. 콘솔 연결·신호 실패 뒤의 확인과 명시적 종료(`terminate_registered_process`)의 같은 조회에도 적용했다. Stop·Apply·Status가 모두 이 함수를 거친다.
- **검증:**
  - [임시 실행 44191294199](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44191294199)(같은 환경): Windows의 거절 상태는 그대로 80번 모두 있었고, 제품의 `_identity()`는 80번 가운데 0번 오류를 냈다. 시험 상황 200번 가운데 0번 실패.
  - 계약 시험 `test_exiting_process_that_refuses_its_image_query_is_an_ordinary_exit`를 더하고 기존 두 시험의 기대값을 맞췄다. 수정 전 코드에서는 새 시험을 포함해 실패한다(오류 4, 실패 1). Linux 로컬 69개 통과, 2개 건너뜀.
  - 정식 Windows platform 묶음: 범위 지정 [실행 588](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44192980459)(`windows`, `platform`) 성공, 14분.
  - 임시 실행 44191294199는 실패로 끝났다. 임시 워크플로에 더한 시험 모듈 실행 단계가 고정 의존성(cryptography)을 설치하지 않아 `CustomizedLauncherTests` 14건이 가져오기 오류로 실패한 것이고, 측정 단계와 종료 관련 시험은 통과했다.
- **남은 항목:** 사내에서 이 오류로 Stop이나 Apply가 실패한 적이 있는지는 확인하지 않았다. 사내 적용은 미실행이다.

### 브라우저 · 설정 메뉴의 관리자 항목 시험 (시험의 대기 누락)

- **증상:** native-compose의 `test_native_admin_dialog_contains_keyboard_focus`가 마지막 단언에서 `True is not false`로 실패한다(실행 568, 583). 관리자 권한을 뺀 뒤에도 설정 메뉴에 관리자 항목이 있었다.
- **확인된 원인:** 시험은 권한 fixture를 바꾸고 `refresh()`를 기다린 뒤 메뉴를 연다. 그런데 관리자 설정 화면에서 돌아오는 순간 제품이 화면 전환용 새로고침을 따로 시작하고, 그보다 먼저 시작한 시험의 `refresh()`는 밀려나 상태를 반영하지 않은 채 끝난다. 제품의 새로고침은 요청을 한 번 더(`operations`) 거친 뒤에야 상태를 반영하므로, 서버 응답이 느리면 시험이 이전 권한의 메뉴를 읽는다.
- **재현(로컬, Chromium 153, 서버 응답 200ms 지연):** 수정 전 14번 가운데 6번이 같은 줄, 같은 단언으로 실패했다. 한 회차의 기록에서 시험의 `workspace` 요청이 시작된 2.6ms 뒤 제품의 `workspace` 요청이 시작됐고, 시험의 요청이 끝난 20ms 뒤 시험이 메뉴를 눌렀으며, 그때 제품의 `operations` 요청은 아직 끝나지 않았다.
- **조치:** 시험 fixture에 `refresh_until()`을 더해, 반영된 상태가 바꾼 권한을 담을 때까지 다시 요청한다. 같은 지연에서 18번 모두 통과했다.
- **제품 판단:** 제품 결함으로 보지 않는다. 메뉴는 권한이 바뀌면 스스로 닫히고 권한은 서버가 따로 검사한다.

### 브라우저 · 대화상자 초점 시험 (시험이 다른 절차를 엶)

- **증상:** native-compose의 `test_c3_dialog_and_help_close_preserve_draft_and_release_modal_blocker`가 `Timed out: document.activeElement?.matches('[data-author-action=copy]')`로 실패한다([실행 568, 575, 583](navigation-motion-20261102.md#narrow-viewport-load-20261117)).
- **확인된 원인:** 작성 화면에 처음 들어가면 제품이 기본 절차를 만들고 목록을 다시 그려 줄이 아래로 밀린다. 시험은 자기가 만든 절차의 줄을 좌표로 누르는데, 좌표를 잰 뒤 목록이 밀리면 그 자리의 기본 절차 ‘일일 시스템 점검’이 열린다. 그 절차는 메뉴 첫 항목으로 ‘절차 편집’이 하나 더 있어 Tab 두 번이 ‘다른 이름으로 저장’에 닿지 못한다.
- **증거:**
  - 실행 583의 실패 로그에 찍힌 화면 글자가 시험이 만든 ‘모달 움직임 검증 절차’가 아니라 ‘일일 시스템 점검’과 ‘절차 편집’ 항목이었다.
  - 계측을 넣고 되풀이한 [임시 실행 44193589216](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44193589216)(ubuntu-24.04, Chrome 157.0.8103.50)에서 70번 가운데 1번 같은 단언으로 실패했다. 그 회차의 초점은 메뉴 단추에서 ‘절차 편집’, ‘업무 절차 정보·분류 수정’ 순으로 움직였다.
  - 수정 전 시험에서 목록이 늘어난 뒤 이전 좌표로 누르게 하면(로컬) 3번 모두 같은 단언으로 실패했다. 만든 절차의 줄은 y 191에서 371로 밀렸고 이전 좌표에는 ‘일일 시스템 점검’이 있었다.
  - 기록 범위를 넓힌 [임시 실행 44195587840](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44195587840)(수정 전 시험, 같은 환경)에서는 220번 가운데 3번 실패했고, 세 번 모두 열린 절차가 ‘일일 시스템 점검’이었다. 첫 실패 회차에서 기본 절차 세 줄이 목록에 추가된 시각은 875.5ms, 시험의 클릭이 닿은 시각은 879.7ms였고 이어진 요청은 만든 절차가 아닌 다른 절차를 읽었다. 두 임시 실행을 합치면 수정 전 290번 가운데 4번 실패다.
- **재현하지 못한 시도(로컬, Chromium 153):** 부하 프로세스 4개로 20번, 화면 처리 속도를 4배·8배 늦춰 12번씩, 메뉴 닫힘 시간을 무작위로 바꿔 40번, 서버 응답을 200ms 늦춰 8번·무작위로 늦춰 36번 돌렸고 한 번도 실패하지 않았다. 메뉴와 대화상자가 닫히는 순서가 원인이라는 가설은 순서를 뒤바꿔도 통과해 버렸다.
- **이전 조치와 빠진 경로:** 같은 문제를 막는 도우미 `open_initialized_author_list()`가 작성 화면 시험과 API 명세 시험에는 쓰이고 있었다. 이 도우미는 작성 화면 시험 클래스에만 있었고 움직임 시험은 쓰지 않았다.
- **조치:** 도우미를 공통 fixture(`IntegratedNativeCase`)로 옮기고 `refresh_until()`을 쓰게 했다. 움직임 시험이 이 도우미로 들어가고, 연 절차가 만든 절차인지 바로 확인한다.
- **같은 유형이 남은 곳:** `test_ees_source_shell_native.py`와 `test_ees_work_figma_layout_native.py`, `test_ees_helper_chat_native.py`에도 작성 화면에 들어가 줄을 누르는 곳이 있다. 진입 과정 자체를 재는 시험이 섞여 있어 바꾸지 않았다. 이 시험들이 다른 절차가 열린 화면으로 실패하면 같은 원인을 먼저 본다.
- **제품 관찰:** 사용자가 어떤 시스템의 작성 화면에 처음 들어갈 때도 기본 절차가 잠시 뒤 추가되면서 줄이 밀린다. 시스템마다 한 번이다. 제품은 바꾸지 않았다.

### 브라우저 · 좁은 창 대화 패널 시험 (시험의 누르기가 화면을 밂)

- **증상:** native-compose의 `test_c3_overlay_panel_closing_releases_hit_testing_and_restores_focus`가 `Opening narrow chat should never take space away from the work surface`로 실패한다([실행 566](navigation-motion-20261102.md#narrow-viewport-load-20261117), [실행 589](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44196652378)).
- **확인된 원인:** 시험 도우미 `click()`은 누를 대상에 `scrollIntoView`를 호출하고 좌표를 잰다. 이 시험은 창을 480px로 줄인 직후(대화 패널이 닫히며 오른쪽으로 미끄러져 나가는 중)에 대화 단추를 누르고, 패널이 되돌아오는 도중에 입력창을 누른다. 그때 입력창 오른쪽 끝이 화면 밖에 3~4px 남아 있어 브라우저가 화면 틀(`.ees-source-shell`)을 그만큼 가로로 스크롤한다. 패널이 제자리에 오면 넘치는 부분이 없어져 스크롤은 0으로 돌아온다. 그 사이에 프레임이 하나 그려지면 왼쪽 메뉴와 업무 영역이 함께 3~4px 왼쪽에 찍히고, 시험은 이를 ‘대화가 업무 영역 폭을 차지했다’로 잰다.
- **증거:**
  - [임시 실행 44199974623](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44199974623)(수정 전, ubuntu-24.04, Chrome 157.0.8103.50): 180번 가운데 12번 실패. 실패 회차마다 어긋난 프레임은 대화 단추를 누른 직후의 하나뿐이고 값은 3 또는 4px, 업무 영역 폭은 424px 그대로였다.
  - 스크롤 위치·좌표·스크롤을 일으킬 수 있는 호출을 기록하게 한 [임시 실행 44202740123](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44202740123)(수정 전, 같은 환경): 150번 가운데 26번 실패. 로그에 남은 17건 모두 어긋난 프레임에서 화면 틀의 가로 스크롤이 3 또는 4였고 왼쪽 메뉴가 [-4, 52]처럼 함께 밀렸다. 스크롤 직전의 호출은 17건 모두 시험 도우미의 `scrollIntoView(#chat-input)`였다. 제품이 대화 영역과 입력창에 초점을 옮기는 호출 두 번은 모두 `preventScroll: true`였다.
  - 로컬(Chromium 153, 같은 기록): 수정 전 60번 가운데 7번 실패, 기록 내용은 CI와 같다. 통과한 회차 3개 가운데 2개에서도 화면 틀의 스크롤 이벤트가 있었고, 프레임이 그려지기 전에 0으로 돌아와 잡히지 않았을 뿐이다. 기록을 본 실패 3회차는 패널이 3프레임, 통과 3회차는 2프레임 동안 나갔다가 되돌아왔다.
- **기각한 가설:** 제품이 대화 입력창으로 초점을 옮기면서 화면이 밀린다고 보았으나, 제품의 초점 이동은 스크롤 방지 옵션을 쓰고 기록에서도 스크롤을 일으키지 않았다. [2026-11-17의 가설](navigation-motion-20261102.md#narrow-viewport-load-20261117)(창 크기 반영 전 조작)도 이 시험의 원인이 아니었다.
- **조치(`77e5470`):** 움직임 시험에 `chat_at_rest()`를 더해, 창을 줄인 직후와 패널 안(입력창·닫기 단추)을 누르기 전에 패널의 전환이 끝나기를 기다린다.
- **검증:** 같은 기록 조건에서 로컬 120번 가운데 0번 실패, [임시 실행 44203582254](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44203582254)(CI, Chrome 157.0.8103.50) 150번 가운데 0번 실패. 수정 뒤 통과 회차 8개의 기록에서 화면 틀 스크롤 이벤트는 0건이다.
- **제품 판단:** 이 실패는 시험의 누르기가 만든 움직임이고 제품 결함이 아니다.
- **제품 관찰(조사 때는 고치지 않았고, 같은 날 사용자 위임으로 [고쳤다](#shell-no-sideways-scroll-20261118)):** 화면 틀은 `overflow:hidden`이어서 보이지는 않아도 스크롤은 된다. 대화 패널이 닫혀 화면 밖에 있을 때는 창 너비와 관계없이 대화 폭만큼 가로로 스크롤할 여지가 생긴다.
  - 실험(로컬, 제품 빌드): 대화를 닫은 상태에서 대화 안의 요소를 화면으로 끌어오는 호출을 하면 화면 전체가 480px 창에서 395px, 1920px 창에서 519px 왼쪽으로 밀리고 2.6초 뒤에도 그대로였다. 대화를 열면 0으로 돌아온다.
  - 대화를 닫은 상태에서 입력창에 글을 넣는 제품 내부 함수(`__eesNativeDraftV1.restore`)를 직접 부르면 편집기가 커서 위치로 스크롤하면서 화면이 267px 밀렸다. 이 함수를 부르는 제품 코드는 찾지 못했다.
  - 실제 사용 흐름 두 가지에서는 밀리지 않았다. 초안을 쓰고 대화를 닫은 뒤 새로고침(480px·1920px), 초안을 쓰고 대화를 닫은 채 시스템을 바꿨다가 돌아오기(1920px).
  - 확인하지 않은 흐름: 대화를 닫은 동안 도구 결과 화면이 도착하는 경우(제품이 그 화면으로 자동 스크롤한다)와 업무 화면에서 대화를 열며 질문을 넣는 경우. 사용자가 화면이 왼쪽으로 밀린 채 남는 현상을 보면 이 항목을 먼저 본다. 화면 틀을 스크롤되지 않게 바꾸면 가능성 자체가 없어지지만 제품 화면 패치 변경이라 사용자가 정한다.
- **같은 유형:** 도우미 `click()`은 모든 브라우저 시험이 쓴다. 프레임마다 좌표를 재는 시험이 움직이는 패널 안을 누르면 같은 일이 생긴다.

### 브라우저 · 창 크기를 바꾸는 작성 화면 시험 (옛 상태를 읽고 누름)

- **증상:** 시험 도우미 `authoring_viewport()`가 창 크기를 바꾼 뒤 다음 가운데 하나로 실패한다.
  - `Timed out: …dataset.compact === "true"`: [실행 566](navigation-motion-20261102.md#narrow-viewport-load-20261117)의 `test_procedure_visual_geometry_matches_figma_and_preserves_native_draft`.
  - `Timed out: …dataset.eesChatState === 'docked'`: 개발 환경의 `test_tools_phase2_trial_activation_revision_groups_and_disable_roundtrip`(2026-11-17 기록에서 8번 중 3번, 14번 중 4번).
  - `Control not visibly ready for a physical click:[data-ees-sidebar-toggle]`: 같은 시험, 대화상자가 열린 채 창 크기를 바꿀 때.
- **확인된 원인:** 창 크기를 바꾸면 `innerWidth`는 바로 바뀌지만 제품은 다음 프레임에 오는 resize 이벤트에서 새 폭을 받아 대화 상태와 왼쪽 메뉴 접힘을 스스로 맞춘다. 도우미는 `innerWidth`만 기다린 뒤 곧바로 상태를 읽어, 이전 창 크기의 상태를 보고 ‘대화가 닫혀 있다’ 또는 ‘메뉴 접힘이 다르다’고 판단해 단추를 누른다. 누르기는 두 프레임 뒤에 닿으므로 그때는 제품이 이미 맞춰 놓은 상태이고, 누르기가 그것을 반대로 뒤집는다. 그 뒤의 대기는 끝나지 않는다.
- **재현(로컬, Chromium 153, 부하 없음):** 수정 전 10번 가운데 4번 실패했고 위 세 문구가 모두 나왔다. 한 회차의 기록에서 360px에서 1920px로 바꾼 뒤 제품이 대화 상태를 `docked`로 바꾼 시각은 1953.0ms, 시험의 대화 단추 클릭은 1979.0ms, 그 클릭으로 상태가 `closed`가 된 시각은 1980.7ms였다. 다른 회차에서는 1366px로 바꾼 11ms 뒤 시험이 왼쪽 메뉴 단추를 눌러 제품이 접어 둔 메뉴를 다시 폈다.
- **이전 조치와 빠진 경로:** [2026-11-05](navigation-motion-20261102.md#q1-viewport-settle-20261105)에 같은 유형(제품이 resize를 반영하기 전에 조건이 만족됨)을 확인했지만 그때는 한 전환에 기대 상태 대기를 더하는 데 그쳤다. 반영 전 상태를 읽는 것 자체는 도우미마다 남아 있었다.
- **조치:** 공통 fixture에 `viewport_applied()`를 더했다. 창 크기를 바꾼 뒤 화면이 두 프레임 그려질 때까지 기다려 resize 이벤트가 전달된 뒤에 상태를 읽는다. `authoring_viewport()`가 이것을 쓴다. 이 도우미를 부르는 곳은 작성 화면·API 명세·작업 등록 시험 세 모듈의 34곳이다.
- **검증:** 같은 시험을 로컬에서 24번 되풀이해 0번 실패했다. 회차마다 6.6~7.0초였다(수정 전 실패 회차는 8.8~14.2초).
- **제품 판단:** 제품 결함이 아니다. 사용자는 창 크기를 바꾼 같은 프레임 안에 단추를 누를 수 없다.
- **같은 유형이 남은 곳:** 창 크기를 바꾸는 도우미는 다른 시험 모듈에도 있다(`test_ees_motion_native.py`의 `viewport()`, `test_ees_work_figma_layout_native.py`, `test_ees_work_figma_runtime_native.py`, `test_ees_source_shell_native.py`, `test_ees_helper_chat_native.py` 등). 이 도우미들에서 같은 실패가 기록된 적은 없다. 하나씩 확인하지 않았고 바꾸지 않았다. 창 크기를 바꾼 직후의 대기에서 시간이 넘으면 이 원인을 먼저 본다.

### 검증과 남은 것

- 로컬(Linux, Python 3.11.18, Chromium 153): 바꾼 도우미를 쓰는 브라우저 시험 네 모듈(움직임 6개, 작업 등록 1개, API 명세 8개, 작성 화면 43개)이 통과했다. 임시 파일을 지운 뒤의 빠른 검사는 1,373개 통과, 109개 건너뜀이고 시험 ID 감사와 문서 점검은 오류 0이다.
- GitHub `browser` 범위 [실행 589](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44196652378)(커밋 `0343bc1`, 앞의 세 건만 고친 상태): native-account·native-work·native-execution과 전체 제품 검사는 성공했다. native-compose는 고친 두 시험을 포함해 129개 가운데 128개가 통과했고 `test_c3_overlay_panel_closing_releases_hit_testing_and_restores_focus` 한 건이 실패했다. 이 실패가 위 ‘좁은 창 대화 패널 시험’ 조사의 출발점이다.
- GitHub: 고친 대화상자 초점 시험을 되풀이한 [임시 실행 44196698628](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44196698628)은 221번 가운데 0번 실패했다(수정 전 290번 가운데 4번).
- GitHub `browser` 범위 [실행 590](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44206456099)(다섯 건을 모두 고친 커밋 `cff1ac8`, Chrome 157.0.8103.50): 첫 시도에 성공했다. native-compose·native-work·native-account·native-execution과 전체 제품 검사가 통과했고 17분 32초가 걸렸다. 한 번의 통과는 간헐 실패가 없어졌다는 증거가 아니다. 근거는 위의 원인별 반복 측정이다.
- 실행하지 않은 것: 마지막 커밋의 `windows`·`linux` 범위와 전체 검사(`full`). Windows platform 묶음은 제품 수정 직후의 커밋에서 실행 588로 확인했고 그 뒤에는 브라우저 시험과 문서만 바꿨다. 전체 검사는 사내 배포 전에 main에서 실행한다.
- 조사에 쓴 임시 워크플로와 임시 스크립트는 지웠다. 측정 값은 위 임시 실행들의 로그에 있다.
- 실패가 기록된 시험 가운데 원인을 확인하지 못한 것은 없다. 다만 간헐 실패는 일어나지 않았다는 것으로 고쳐졌음을 증명할 수 없다. 위 시험들이 다시 실패하면 같은 문구인지부터 보고 이 기록에 잇는다.
- **재발 방지 연결:** 제품 수정은 `scripts/ees_deploy_process.py`, 시험 보완은 `tests/ees_work_integrated_fixture.py`의 `refresh_until()`·`open_initialized_author_list()`·`viewport_applied()`와 `tests/test_ees_motion_native.py`의 `chat_at_rest()`에 있다.

<a id="restore-tests-removed-20261118"></a>

## 이전 버전(ees.10~13) 복구 시험 삭제 (2026-11-18)

- **요청·근거:** 사용자가 사내 PC의 프로그램이 ees.14라고 알리고(2026-11-17) 이전 버전 복구 시험을 지우라고 지시했다(2026-11-18). 사내에 설치된 커밋은 이 작업에서 확인하지 않았다. 같은 날 다른 세션의 기록에는 사용자 보고로 `d0f205874936`이 적혀 있다.
- **지운 것:**
  - `tests/test_ees_webui_customization.py`의 시험 다섯 개와 그 시험만 쓰던 도우미 두 개(194줄). 실제 ees.10·ees.11·ees.12(두 커밋)·ees.13 프로그램을 설치한 상태에서 실제 새 프로그램을 적용하고 복구해, 프로그램 파일·DB·키가 그대로인지 보던 시험이다.
    - `test_real_ees10_to_authoring_apply_restore_preserves_program_and_data`
    - `test_real_ees11_to_execution_apply_restore_preserves_program_and_data`
    - `test_real_ees12_visual_revision_apply_restore_preserves_prior_asset_inventory`
    - `test_real_ees12_v4_apply_restore_preserves_program_and_additive_work_database`
    - `test_real_ees13_to_source_frontend_apply_restore_preserves_program_and_data`
  - 이 시험만 돌리던 CI 묶음 `restore-ees10`·`restore-ees11`·`restore-ees12`·`restore-ees13`(Linux·Windows 각 4개).
  - 이 시험만 쓰던 고정 자료 `previous12`·`previous-v4`·`previous13`의 준비 작업과 내려받기 단계, Windows에서 ees.12를 다시 빌드하던 세 줄.
- **남긴 것:**
  - 고정 자료 `legacy`(ees.10)와 `previous`(ees.11). 업무 절차 시험과 Windows 진단이 계속 쓴다.
  - 같은 파일의 나머지 시험 72개. 만든 wheel로 적용·복구·중단 뒤 재개·이전 버전 파일 목록 고정을 본다. 실제로 빌드한 현재 wheel의 구성 검사(`program-wheel`)도 그대로다.
  - 제품의 이전 버전 호환 코드(`scripts/ees_webui_customization.py`의 ees.12·ees.13 파일 목록 등)는 바꾸지 않았다.
- **없어진 보호:** 실제로 설치된 이전 프로그램 위에 실제 새 프로그램을 적용하고 복구하는 시험은 남지 않았다. 사내 설치본(ees.14)에서 다음 버전으로 올리는 경로를 실제 파일로 보는 시험도 없다. 프로그램 버전을 올릴 때 그 시점의 설치본을 고정 자료로 삼는 시험이 필요한지 사용자가 정한다.
- **보존한 증거:** 지운 시험의 코드는 커밋 `098aeb3`까지의 Git 기록에 있다. 당시 실행 결과는 [v4 기록](v4-ui-20260930.md)과 [제품 대조 기록](figma-product-parity-20261111.md)의 해당 날짜 항목에 그대로 둔다. 시험 ID 감사 기준(`tests/ees_delivery_baseline.json`)에 있던 세 개에는 삭제 사유와 남은 시험을 적었다.
- **효과:** 전체 검사의 작업이 41개에서 30개로 줄었다(묶음 8개, 고정 자료 준비 3개). 2026-11-17에 13개가 준다고 보고한 것은 `legacy`·`previous`를 다른 시험도 쓴다는 점을 빼고 센 값이었다.
- **검증:** 로컬(Linux, Python 3.11.18)에서 시험 ID 감사 오류 0, 계획 시험 20개와 고정 자료 시험 10개 통과, 남은 설치·복구 시험 72개 통과(3개 건너뜀), 빠른 검사 1,373개 통과(109개 건너뜀), 문서 점검 오류 0. GitHub [실행 591](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44210635619)(커밋 `4ed3127`, 범위 `full`, 묶음 `program-install program-wheel platform`)에서 Linux·Windows의 여섯 작업과 고정 자료 준비 두 개(`legacy`, `previous`)가 첫 시도에 성공했다. 12분 17초가 걸렸다. Windows의 platform 작업에는 고친 다시 빌드 단계와 프로세스 종료 시험이 들어 있다. [PR #150](https://github.com/knadalkim-a11y/team-agent-poc/pull/150)의 빠른 검사 [실행 592](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44210699601)도 3분 5초에 성공했다. 나머지 묶음(`services`·`contracts`·`native-contracts`·`native-grounding`)과 전체 검사는 이 커밋에서 실행하지 않았다.

<a id="shell-no-sideways-scroll-20261118"></a>

## 화면 틀이 가로로 스크롤되지 않게 함 (2026-11-18)

- **요청·근거:** [간헐 실패 조사](#flaky-root-cause-20261118)에서 찾은 제품 관찰이다. 사용자가 남은 결정을 판단대로 진행하라고 지시했다(2026-11-18).
- **증상(수정 전, 로컬 제품 빌드 `6576f33`):** 대화를 닫은 상태에서 대화 안의 요소를 화면으로 끌어오면 왼쪽 메뉴와 업무 영역이 함께 왼쪽으로 밀린 채 남는다. 480px 창에서 395px(왼쪽 메뉴 [-395, -339], 업무 영역 [-339, 85]), 1920px 창에서 519px(왼쪽 메뉴 [-519, -263], 업무 영역 [-263, 1401]). 대화를 열면 돌아온다.
- **원인:** 닫힌 대화 패널은 화면 틀의 오른쪽 밖에 놓인다. 화면 틀이 `overflow:hidden`이라 넘친 만큼 스크롤할 수 있었고, 대화 입력창의 편집기가 커서 위치로 스크롤하거나 요소가 `scrollIntoView`될 때 브라우저가 화면 틀을 움직였다.
- **판단:** 실제 사용 흐름에서 재현하지는 못했다(확인한 두 흐름에서는 생기지 않았다). 그래도 고쳤다. 원본 Open WebUI는 도구 결과 화면이 도착하면 그 화면으로 자동 스크롤하고, 그 코드는 대화 패널이 열려 있는지 보지 않는다. 생기면 화면이 깨진 것처럼 보이고, 막는 데 드는 것은 한 줄이다.
- **조치:** `frontend/patches/0001-ees-native-hooks.patch`의 화면 틀 규칙에 `overflow:clip`을 더했다(지원하지 않는 브라우저를 위해 `overflow:hidden`을 앞에 둔다). 넘친 부분은 전과 같이 잘려 보이지 않고 스크롤만 되지 않는다. `overflow:clip`을 모르는 브라우저에서는 앞의 값이 적용돼 전과 같이 동작한다. 패치와 결과 파일의 고정 해시를 함께 고쳤다.
- **회귀 시험:** `test_closed_chat_content_brought_into_view_never_moves_the_shell`(`tests/test_ees_source_shell_native.py`). 480px와 1920px에서 대화를 닫고, 입력창을 화면으로 끌어오고 닫힌 입력창에 초안을 넣은 뒤에도 화면 틀의 스크롤과 왼쪽 메뉴·업무 영역의 위치가 그대로인지 본다.
- **검증:**
  - 회귀 시험은 수정 전 빌드에서 두 창 크기 모두 위 증상의 값으로 실패하고, 수정 후 빌드에서 세 번 모두 통과했다(로컬, Chromium 153).
  - 수정 후 빌드에서 화면 틀 시험 17개, 움직임 시험 6개, 배치 시험 5개, 도움 대화 시험 11개가 통과했다(로컬). 빠른 검사는 1,373개 통과, 109개 건너뜀이고 문서 점검은 오류 0이다. 프런트엔드 빌드가 고친 고정 해시로 성공했다.
  - GitHub `browser` 범위 [실행 594](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44219668133)(커밋 `c65514b`, Chrome 157): 첫 시도에 성공했다. 고친 고정 해시로 프런트엔드를 빌드했고, 새 회귀 시험을 포함한 브라우저 묶음 네 개와 전체 제품 검사가 통과했다. 17분 4초가 걸렸다. `windows`·`linux` 범위와 전체 검사는 실행하지 않았다.
- **남은 것:** 도구 결과 화면이 닫힌 대화에 도착하는 실제 흐름은 직접 돌려 보지 않았다. 사내 확인은 미실행이다.

<a id="cleanup-candidates-kept-20261118"></a>

## 정리 후보 두 가지를 지우지 않기로 함 (2026-11-18)

사용자가 남은 결정을 판단대로 진행하라고 지시했다(2026-11-18). [2026-11-17에 남긴 정리 후보](#ci-on-demand-20261117) 두 가지를 조사했고 지우지 않기로 했다. 지운 것은 없다.

### 폐기한 데모 적용과 중단된 배포 명령

- **확인한 것:** `ApplyDemo`는 사내 운영 명령 파일(`scripts/manage-ees.ps1`)에 남아 있고 실행하면 거절한다. 그 모듈(`scripts/ees_apply_demo.py`)의 연결 도우미는 데모 자산 정리(`scripts/ees_demo_assets.py`)가 쓴다. 중단된 배포 방식(Diagnose·Plan·Prepare·Deploy·Rollback)은 `scripts/manage_ees.py`(999줄) 안에서 지금 쓰는 Start·Stop·Apply·Restore·Backup과 잠금·기록·프로세스 확인 도우미를 함께 쓴다. 운영 스크립트(`manage_ees.py`와 `ees_deploy_*.py` 아홉 개)는 4,032줄, 배포·적용 관련 시험은 15개 파일 9,640줄이다.
- **지우지 않는 이유:**
  - 쓰는 경로와 쓰지 않는 경로가 같은 함수를 공유해 깔끔하게 떼어 낼 수 없다. 잘못 떼면 사내의 서버 중지·적용·복구가 깨진다.
  - 이 명령들은 사내 Windows PC에서만 실제로 확인할 수 있다. 개발 환경과 CI로는 깨뜨리지 않았다는 것을 끝까지 확인할 수 없다.
  - 화면 작업 속도와 관계가 없다. 이 시험들은 2026-11-17부터 필요할 때만 돈다.
  - 옛 명령을 실행했을 때 거절하고 이유를 알려 주는 동작은 운영자에게 필요한 보호다.
- **다시 볼 때:** 사내 운영 명령을 고칠 일이 생기면 그 작업 안에서 쓰지 않는 명령을 함께 정리한다.

### 화면 좌표 시험

- **확인한 것:** 좌표를 재는 확인은 따로 떨어진 시험이 아니다. 이 변경 전 기준으로 작성 화면 시험 43개 안에 좌표 읽기가 57곳, 화면 틀 시험 16개에 36곳, 움직임 시험 6개에 29곳 있고, 같은 시험이 단추 동작·저장·초점도 함께 본다. 확인의 상당수는 정확한 숫자가 아니라 ‘넘치지 않는다’, ‘패널이 서로 붙어 있다’ 같은 조건이다.
- **지우지 않는 이유:**
  - 좌표 확인만 골라 지우려면 시험 9천여 줄을 한 줄씩 판단해 다시 써야 한다. 그 비용이 아끼려는 비용보다 크다.
  - 이 확인이 비용이 되는 때는 그 화면을 바꿀 때뿐이고, 그때 바뀐 화면의 확인은 어차피 고친다. 미리 지워도 지금 줄어드는 것이 없다. PR마다 돌지도 않는다.
  - 2026-11-18에 간헐 실패 원인을 고쳐, 이 시험들이 이유 없이 병합을 막는 일은 줄었다.
- **화면을 바꿀 때 권하는 방식:** 바뀌는 화면의 정확한 좌표·크기 확인은 새 숫자로 다시 고정하지 말고 지운다. 동작과 ‘보인다·넘치지 않는다·겹치지 않는다’만 남긴다. 목업과의 정확한 대조는 구현할 판이 지정됐을 때 한 번 하고 결과를 기록에 남긴다. 이것을 규칙(`AGENTS.md`)으로 둘지는 사용자가 정한다.

<a id="main-8866719-apply-prep-20261118"></a>

## 2026-11-18 · main 8866719 전체 검사와 사내 적용 준비

- **요청:** 사용자가 main에서 전체 검사를 실행하고, 끝나면 사내 적용 명령을 알려 달라고 지시했다(2026-11-18). main `88667199157da5a9688a91ac74273c1362c3f8a7`([PR #151](https://github.com/knadalkim-a11y/team-agent-poc/pull/151) 병합), 열린 PR 없음.
- **전체 검사:** Run workflow로 main에서 `full`(프로그램 포함)을 실행했다. [실행 597](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44230229471)은 첫 시도에 성공했다(작업 30개 성공, 빠른 검사 작업 1개는 전체 범위에서 건너뜀, 약 18분 30초). CI를 필요한 만큼만 돌리기로 바꾼 뒤 main에서 한 첫 전체 검사다.
- **프로그램 ZIP:** `ees-program-88667199157da5a9688a91ac74273c1362c3f8a7`([artifact 14395597128](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44230229471/artifacts/14395597128)), 바깥 ZIP 155,821,472 bytes, SHA256 `7f712f62eb8e2723ea5cb8f6c6ddea1e7a78a6578548c3d9010b5eb38e568cd1`(올린 작업의 로그와 GitHub artifact 정보가 같다), 안쪽 `EES-demo-88667199157d.zip`, 보관 2027-02-16까지. 포장 작업은 모든 묶음을 통과한 프로그램 바이트를 그대로 썼고 `test_ees_webui_customization` 72개(건너뜀 2)가 통과했다.
- **이 개발 환경에서 하지 못한 것:** 실제 ZIP을 내려받아 바이트를 검증하지 못했다. artifact 저장소 호스트(`productionresultssa0.blob.core.windows.net`)가 이 환경의 네트워크 정책에 막혀 있다(프록시 403). 2026-10-30 준비 때 한 내려받은 ZIP의 크기·해시·내용 검증은 이번에는 미실행이다. 사내 블록이 받은 파일의 크기와 SHA256을 위 값과 대조하고, Upgrade가 서버를 멈추기 전에 ZIP의 manifest·파일 해시·버전을 검사한다.
- **적용 블록:** [2026-10-30 블록](../docs/03-openwebui-native-agent.md#main-6b1c256-apply-prep-20261030)에서 값 다섯 개(원본 커밋, ZIP 해시, ZIP 크기, artifact 주소, 설치돼 있어야 할 커밋 `d0f2058749364e3b5626a17aa71ecf85d90b587b`)와 주석 두 줄만 바꿨다. 주석과 값을 뺀 제어 흐름이 그 블록과 같은 것을 확인했다. CRLF 기준 적용 2,272자, 되돌리기 438자. 이 환경에 PowerShell이 없어 구문 실행 확인은 미실행이다.
- **설치 기준:** 사용자가 사내 설치본을 `d0f205874936`·ees.14라고 알렸다(2026-11-17). 블록은 Status의 정확한 커밋·정상 프로그램·미완료 없음을 Stop 전에 확인하고 다르면 멈춘다. `d0f2058` 뒤로 관리·적용 스크립트에서 바뀐 것은 `ees_deploy_process.py`(종료 중인 Windows 프로세스의 조회 거부 처리)와 `ees_webui_customization.py`(프런트엔드 버전 표기 검사)이고 Upgrade·관리 진입 스크립트는 같다. 서버 저장 형식은 바뀌지 않았다.
- **유효 조건:** Upgrade는 main의 최신 커밋과 블록의 커밋이 같아야 진행한다. 적용 전에 main에 무엇이든 병합하면(문서만이어도) 이 블록은 Update 뒤 원본 불일치로 멈추고, 전체 검사와 블록을 다시 만들어야 한다.
- **미실행:** 사내 적용·기동·화면 확인(사용자 실행 결과로 따로 기록한다).
- **사내 적용 결과(사용자 보고, 2026-11-19):** 사용자가 적용 명령을 실행해 두었다고 알렸고(2026-11-18), 결과를 묻자 ‘성공, 새 판으로 동작 중’이라고 답했다. 선택지로 받은 답이며 결과 줄 원문과 화면 확인 내용은 받지 않았다. 이 세션에서 따로 확인하지 않았다. 다음 적용 블록의 설치 기준은 `88667199157da5a9688a91ac74273c1362c3f8a7`이고, 블록이 Status의 커밋을 서버를 멈추기 전에 확인하므로 실제 설치본이 다르면 그 자리에서 멈춘다.

<a id="main-bb55e36-full-check-failure-20261125"></a>

## 2026-11-25 · main bb55e36 전체 검사 실패: Windows에서만 걸리는 시험 코드 두 곳

- **증상:** [PR #156](https://github.com/knadalkim-a11y/team-agent-poc/pull/156)을 병합한 main `bb55e365d26e6cfb7a37d4c2b4acbcdb097d0874`의 전체 검사 [실행 634](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/45569247081)가 실패했다(Python 3.11.9, windows-2022). 작업 31개 가운데 Windows `services` 묶음 하나가 실패했다. 성공 26개, 건너뜀 2개(빠른 검사, 프로그램 ZIP 만들기)이고 최종 집계 둘은 그 실패 때문에 실패·취소로 끝났다. 프로그램 ZIP은 만들어지지 않았다. Linux의 모든 묶음과 Windows의 다른 묶음은 통과했다.
- **실패한 시험 11개(세 모듈):**
  - `test_ees_work_figma_authoring` 8개와 `test_ees_work_figma_schedule` 2개: `FileNotFoundError: [WinError 206] The filename or extension is too long`.
  - `test_ees_work_try`의 `test_try_open_makes_a_try_of_an_unpublished_draft_stored_for_rollback` 1개: 임시 폴더를 지우다 `PermissionError: [WinError 32]`(`work.sqlite3`가 사용 중).
- **확인된 원인 1(길이를 재서 확인):** 앞의 두 모듈은 `tests/test_ees_work_authoring_ui.cjs`의 첫 시험 앞부분(시험용 화면 틀)을 읽어 `node -e`의 인자로 넘겼다. 그 앞부분은 사내 판 `e494605`에서 30,135자였고, ‘게시 전에 시험해 보기’([PR #157](https://github.com/knadalkim-a11y/team-agent-poc/pull/157), main `80493e3`)에서 38,530자가 됐다. 지금은 38,576자다. Windows는 32,767자를 넘는 명령줄을 거절한다. Linux의 한도는 훨씬 커서 통과한다.
- **원인 2(코드로 확인, Windows에서 따로 재현하지 않음):** PR #157이 더한 그 시험이 `with sqlite3.connect(...)`로 DB를 열었다. 이 구문은 거래만 끝내고 연결을 닫지 않는다. Windows는 열린 파일을 지우지 못한다. 같은 모듈의 다른 30개는 제품의 연결 함수만 써서 통과했다.
- **왜 이제 드러났나:** PR #157은 병합 전에 빠른 검사와 `browser` 범위(Linux)만 실행했다. Windows 묶음은 전체 검사에만 있고, #157 뒤 main의 전체 검사는 이번이 처음이다. 마지막으로 성공한 전체 검사는 `e494605`의 실행 611이다. PR #154·#155·#156의 병합 전 검증도 같은 범위였다.
- **조치(`7ea9890`):** 세 곳의 스크립트를 명령줄 대신 표준 입력으로 넘긴다(`node -`). 그러면 스크립트 뒤의 첫 인자가 한 칸 뒤로 가므로 두 스크립트의 인자 위치를 맞췄다. DB 연결은 `closing()`으로 닫는다. 제품 코드는 바꾸지 않았다. 시험을 끄거나 건너뛰지 않았다.
- **검증:** 로컬(Linux, Python 3.11)에서 세 모듈 8·22·31개 통과. 작업 브랜치 `7ea9890`에서 `windows` 범위의 `services` 묶음만 실행한 [실행 635](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/45572142657)가 첫 시도에 성공했다(windows-2022, 묶음 약 7분 30초). 로그에서 33개 모듈에 실패가 없고, 앞서 실패한 세 모듈의 시험이 실행돼 통과한 것을 확인했다.
- **재발 방지와 남은 것:** 명령줄로 스크립트를 넘기던 곳은 이 세 곳뿐이었고 모두 표준 입력으로 바꿔 길이 한도가 없어졌다. 연결을 닫지 않는 `with sqlite3.connect()`는 Windows에서 도는 시험 가운데 이 한 곳뿐이었다(같은 구문이 `tests/ees_work_integrated_app.py`에 한 번 더 있으나 Linux에서만 도는 점검이라 그대로 두었다). 다음에 쓸 판단 기준: Python 시험이 다른 프로세스를 띄우는 방식이나 임시 DB 파일을 여는 코드를 바꾼 변경은, 병합 전에 브랜치에서 `windows` 범위의 그 묶음을 한 번 실행한다(이번 확인은 약 10분). 첫 사례라 `AGENTS.md`에는 넣지 않았다.
- **사용자 승인:** 실패와 원인을 알리고 수정용 PR을 만들어 병합해도 되는지 묻자 사용자가 “PR 만들어 병합”을 골랐다(2026-11-25, 선택지 답).

<a id="main-62d58c2-apply-prep-20261125"></a>

## 2026-11-25 · main 62d58c2 전체 검사와 사내 적용 준비(게시 전에 시험해 보기, 작성 화면 PR #156 기준)

- **요청:** 작성 화면을 PR #156 기준으로 맞춘 결과와 남은 결정을 보고하자 사용자가 “너 판단대로 하고 머지해. 사내배포하고 확인해볼거니까”라고 했다(2026-11-25). [PR #156](https://github.com/knadalkim-a11y/team-agent-poc/pull/156)과 시험 수정 [PR #158](https://github.com/knadalkim-a11y/team-agent-poc/pull/158)을 병합한 main `62d58c274fb230d5fd10bf188516367d7344aac0`, 열린 PR 없음. 사내 적용은 사용자가 한다.
- **이번 적용에 들어가는 것:** 사내 판(`e494605`) 뒤로 main에 들어간 것 전부다. 게시 전에 시험해 보기([PR #157](https://github.com/knadalkim-a11y/team-agent-poc/pull/157), 저장·게시 나누기와 ‘시험해 보기’ 탭)와, PR #156의 이름 옆 업무 분류·단계 안에서 작업 이어서 추가, 그리고 [맞추면서 고친 것](figma-product-parity-20261111.md#pr156-basis-20261125)이다. PR #154·#155의 화면과 서버 변경은 들어 있지 않다.
- **병합 전:** PR #156은 빠른 검사가 병합한 head `416214d`에서 통과했고 자동 리뷰가 그 커밋에서 지적이 없었다. 그 병합 뒤 main `bb55e36`의 첫 전체 검사(실행 634)는 Windows에서만 걸리는 시험 코드 두 곳 때문에 실패했다([기록](#main-bb55e36-full-check-failure-20261125)). 사용자가 “PR 만들어 병합”을 골라 시험만 고친 PR #158을 넣었다. PR #158은 빠른 검사가 head `1a0d859`에서 통과했고 자동 리뷰 지적이 없었다. main의 내용은 그 커밋과 같다(tree `bc3c0067d136`). 제품 코드는 PR #156의 head와 같다.
- **전체 검사:** Run workflow로 main에서 `full`(프로그램 포함)을 실행했다. [실행 637](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/45575504744)은 첫 시도에 성공했다(작업 30개 성공, 1개는 전체 범위에서 건너뜀, 약 19분). Windows 묶음, 화면 시험 묶음, 제품 통합 점검이 모두 들어 있다.
- **프로그램 ZIP:** `ees-program-62d58c274fb230d5fd10bf188516367d7344aac0`([artifact 15005870151](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/45575504744/artifacts/15005870151)), 바깥 ZIP 155,913,357 bytes, SHA256 `c16ad38f3a72eae1009aa31db62341d3f02f7cd5bbe5c2c9974d4cc32b5259be`(올린 작업의 로그와 GitHub artifact 정보가 같다), 안쪽 `EES-demo-62d58c274fb2.zip`, 보관 2027-02-23까지. 포장 작업의 `test_ees_webui_customization` 72개(건너뜀 2)가 통과했다.
- **이 개발 환경에서 하지 못한 것:** 실제 ZIP을 내려받아 바이트를 검증하지 못했다(artifact 저장소가 이 환경의 네트워크 정책에 막혀 있다). 사내 블록이 받은 파일의 크기와 SHA256을 위 값과 대조하고, Upgrade가 서버를 멈추기 전에 ZIP의 manifest·파일 해시·버전을 검사한다.
- **적용 블록:** [안내서의 2026-10-30 블록](../docs/03-openwebui-native-agent.md#main-6b1c256-apply-prep-20261030)에서 값 다섯 개(원본 커밋, ZIP 해시, ZIP 크기, artifact 주소, 설치돼 있어야 할 커밋 `e49460569155693f2189fa6ece51a882dc4e2882`)와 주석 두 줄만 바꿨다. 값과 주석을 뺀 나머지가 그 블록과 글자 단위로 같은 것을 스크립트로 대조했다. CRLF 기준 적용 2271자, 되돌리기 429자. 이 환경에 PowerShell이 없어 구문 실행 확인은 미실행이다. 같은 틀의 블록으로 사용자가 지난 세 번의 적용을 마쳤다고 알렸다.
- **설치 기준:** 사용자가 `e494605` 적용이 성공했다고 알렸다(2026-11-20). 블록은 Status의 정확한 커밋·정상 프로그램·미완료 없음을 Stop 전에 확인하고 다르면 멈춘다. `e494605` 뒤로 관리·적용 스크립트(`scripts/`)와 CI 설정(`.github/`)은 바뀌지 않았다. 바뀐 것은 업무 서버 파일 여섯과 화면 파일 다섯이며 모두 프로그램 ZIP에 들어 있다. 도구를 다시 등록하지 않는다.
- **자료:** 표 구조는 그대로다. 시험해 보기의 시험은 `work_runs`의 한 줄로 남는다. 되돌리기는 프로그램만 되돌린다. 이전 프로그램(`e494605`)으로 되돌린 뒤에는 남아 있던 시험이 실행 기록의 취소 건으로 보이고, 저장만 해 둔 초안은 이전 프로그램의 다음 저장 때 함께 게시된다. [호환 범위](../docs/mockups/ees-work/TASK.md#try-before-publish-implementation-20261124)에 적은 그대로이며 이전 프로그램으로 실제로 되돌려 보지는 않았다.
- **유효 조건:** Upgrade는 main의 최신 커밋과 블록의 커밋이 같아야 진행한다. 적용 전에 main에 무엇이든 병합하면 이 블록은 Update 뒤 원본 불일치로 멈추고, 전체 검사와 블록을 다시 만들어야 한다. 이 기록은 작업 브랜치에만 두고 적용 결과를 받은 뒤 main에 넣는다.
- **미실행:** 사내 적용·기동·화면 확인(사용자 실행 결과로 따로 기록한다).

<a id="main-e494605-apply-prep-20261119"></a>

## 2026-11-19 · main e494605 전체 검사와 사내 적용 준비(작업 아래에서 값 묻기)

- **요청:** 값을 묻는 작업(목업 19번 3판) 구현을 본 사용자가 “main에 넣고 사내 적용하자.”라고 했고, 이어서 “전체 검사 끝나면 사내 적용 명령 알려줘”라고 했다(2026-11-19). [PR #153](https://github.com/knadalkim-a11y/team-agent-poc/pull/153)을 병합한 main `e49460569155693f2189fa6ece51a882dc4e2882`, 열린 PR 없음.
- **병합 전:** PR의 빠른 검사가 병합한 head `fb668d1`에서 통과했다. PR의 자동 리뷰(Codex)가 찾은 두 건과 두 번째 독립 검토가 찾은 것을 고친 뒤, 재검토에서 지적이 없었다([기록](figma-product-parity-20261111.md#ask-in-row-product-20261119)). 처음 head `941f993`의 실행은 새 커밋으로 빠른 검사가 취소돼 최종 집계가 실패로 표시됐다. 제품 실패가 아니며 PR에 그 설명을 남겼다.
- **전체 검사:** Run workflow로 main에서 `full`(프로그램 포함)을 실행했다. [실행 611](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44636839323)은 첫 시도에 성공했다(작업 30개 성공, 빠른 검사 작업 1개는 전체 범위에서 건너뜀, 약 19분). Windows 묶음, 화면 시험 네 묶음, 제품 통합 점검이 모두 들어 있다.
- **프로그램 ZIP:** `ees-program-e49460569155693f2189fa6ece51a882dc4e2882`([artifact 14586115836](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44636839323/artifacts/14586115836)), 바깥 ZIP 155,844,472 bytes, SHA256 `0fe8d23dfc83a47fc258fc8561a528c915778696d3be56fb619899ffccb24ea7`(올린 작업의 로그와 GitHub artifact 정보가 같다), 보관 2027-02-17까지.
- **이 개발 환경에서 하지 못한 것:** 실제 ZIP을 내려받아 바이트를 검증하지 못했다(artifact 저장소가 이 환경의 네트워크 정책에 막혀 있다). 사내 블록이 받은 파일의 크기와 SHA256을 위 값과 대조하고, Upgrade가 서버를 멈추기 전에 ZIP의 manifest·파일 해시·버전을 검사한다.
- **적용 블록:** [2026-11-19 블록](#main-77ec384-apply-prep-20261119)에서 값 다섯 개(원본 커밋, ZIP 해시, ZIP 크기, artifact 주소, 설치돼 있어야 할 커밋 `77ec384d5e76bbcd9700622a9be7bcb1b5923590`)와 주석만 바꿨다. 값과 주석을 뺀 나머지가 지난 블록과 글자 단위로 같은 것을 스크립트로 대조했다. CRLF 기준 적용 2,272자, 되돌리기 438자. 이 환경에 PowerShell이 없어 구문 실행 확인은 미실행이다. 지난 블록은 사용자가 사내에서 실행해 적용을 마쳤다고 알렸다.
- **설치 기준:** 사용자가 `77ec384` 적용을 마쳤다고 알렸다(2026-11-19). 블록은 Status의 정확한 커밋·정상 프로그램·미완료 없음을 Stop 전에 확인하고 다르면 멈춘다. `77ec384` 뒤로 관리·적용 스크립트(`scripts/`)와 CI 설정은 바뀌지 않았다. 바뀐 것은 화면 파일 셋, 업무 서버 파일 하나(`ees_workflow_workspace.py`의 예시 검증), 기본 가이드 정의(`workflow_confluence_guide.json`)이며 모두 프로그램 ZIP에 들어 있다. 도구를 다시 등록하지 않는다.
- **자료:** DB 구조는 그대로다. 절차 정의의 입력에 `example` 값이 늘 수 있으나 예시를 적는 작성 화면이 없어, 사내 자료에 생기는 경우는 기본 가이드를 새로 설치할 때뿐이다(사내는 이미 설치돼 있어 생기지 않는다). 줄 아래에서 넣은 값은 지금의 회차 입력으로 저장된다. 되돌리기는 프로그램만 되돌린다.
- **유효 조건:** Upgrade는 main의 최신 커밋과 블록의 커밋이 같아야 진행한다. 적용 전에 main에 무엇이든 병합하면 이 블록은 Update 뒤 원본 불일치로 멈추고, 전체 검사와 블록을 다시 만들어야 한다. 이 기록은 작업 브랜치에만 두고 적용 결과를 받은 뒤 main에 넣는다.
- **미실행:** 사내 적용·기동·화면 확인(사용자 실행 결과로 따로 기록한다).
- **사내 적용 결과(사용자 보고, 2026-11-20):** 사용자가 “배포는 성공했지만”이라고 알렸다(main `e494605`). 결과 줄 원문은 받지 않았고 이 세션에서 따로 확인하지 않았다. 같은 말에서 화면이 여전히 초심자에게 직관적이지 않다고 했다([기록](figma-product-parity-20261111.md#ask-in-row-product-20261119)).

<a id="main-77ec384-apply-prep-20261119"></a>

## 2026-11-19 · main 77ec384 전체 검사와 사내 적용 준비

- **요청:** 사용자가 이번 구현(첫 사용자 보완, 첫 사용자 흐름, 확인 항목)을 main에 넣고 새로 사내 적용을 준비하라고 정했고, 전체 검사가 끝나면 사내 적용 명령을 알려 달라고 했다(2026-11-19). [PR #152](https://github.com/knadalkim-a11y/team-agent-poc/pull/152)를 병합한 main `77ec384d5e76bbcd9700622a9be7bcb1b5923590`, 열린 PR 없음.
- **병합 전:** PR의 빠른 검사가 병합한 head `89d4b9c`에서 통과했다. PR의 자동 리뷰가 찾은 결함 한 건을 고친 뒤 재검토에서 지적이 없었다([기록](figma-product-parity-20261111.md#first-user-usability-20261118)). 앞선 head의 실행 601은 새 커밋으로 취소되어 최종 집계 작업이 실패로 표시됐다. 제품 실패가 아니다.
- **전체 검사:** Run workflow로 main에서 `full`(프로그램 포함)을 실행했다. [실행 604](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44442479736)는 첫 시도에 성공했다(작업 30개 성공, 빠른 검사 작업 1개는 전체 범위에서 건너뜀, 약 20분). Windows 묶음과 화면 시험 네 묶음, 제품 통합 점검이 모두 들어 있다.
- **프로그램 ZIP:** `ees-program-77ec384d5e76bbcd9700622a9be7bcb1b5923590`([artifact 14492538409](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/44442479736/artifacts/14492538409)), 바깥 ZIP 155,834,568 bytes, SHA256 `f2c20f714aaeb59bb7575e6a01fa2fa622b1a322e6b54162f3c5f97c28f5dc4c`(올린 작업의 로그와 GitHub artifact 정보가 같다), 안쪽 `EES-demo-77ec384d5e76.zip`, 보관 2027-02-17까지. 포장 작업은 모든 묶음을 통과한 프로그램 바이트를 그대로 썼고 `test_ees_webui_customization` 72개(건너뜀 2)가 통과했다.
- **이 개발 환경에서 하지 못한 것:** 실제 ZIP을 내려받아 바이트를 검증하지 못했다(지난번과 같이 artifact 저장소가 이 환경의 네트워크 정책에 막혀 있다). 사내 블록이 받은 파일의 크기와 SHA256을 위 값과 대조하고, Upgrade가 서버를 멈추기 전에 ZIP의 manifest·파일 해시·버전을 검사한다.
- **적용 블록:** [2026-11-18 블록](#main-8866719-apply-prep-20261118)에서 값 다섯 개(원본 커밋, ZIP 해시, ZIP 크기, artifact 주소, 설치돼 있어야 할 커밋 `88667199157da5a9688a91ac74273c1362c3f8a7`)와 주석만 바꿨다. 값과 주석을 뺀 나머지가 지난 블록과 글자 단위로 같은 것을 스크립트로 대조했다. CRLF 기준 적용 2,272자, 되돌리기 438자. 이 환경에 PowerShell이 없어 구문 실행 확인은 미실행이다. 지난 블록은 사용자가 사내에서 실행해 성공했다고 알린 것이다.
- **설치 기준:** 사용자가 지난 적용이 성공해 `8866719` 판으로 동작 중이라고 알렸다(2026-11-19, 선택지 답). 블록은 Status의 정확한 커밋·정상 프로그램·미완료 없음을 Stop 전에 확인하고 다르면 멈춘다. `8866719` 뒤로 관리·적용 스크립트(`scripts/`)는 바뀌지 않았다. 바뀐 것은 화면 파일, 왼쪽 메뉴의 소스 패치, 업무 서버 파일 둘(`ees_workflow_workspace.py`, `workflow_help.json`)이며 모두 프로그램 ZIP에 들어간다. 도구 재등록은 필요 없다.
- **자료:** DB 구조는 그대로다. 절차 정의의 작업에 확인 항목 값이 늘 수 있다. 되돌리기는 프로그램만 되돌리므로, 새 프로그램이 쓴 자료를 `8866719`의 서버 코드로 열어 읽기·저장·확인·끝내기가 되는 것을 확인했다([기록](figma-product-parity-20261111.md#first-user-usability-20261118)). 이전 프로그램의 화면은 띄워 보지 않았다.
- **유효 조건:** Upgrade는 main의 최신 커밋과 블록의 커밋이 같아야 진행한다. 적용 전에 main에 무엇이든 병합하면 이 블록은 Update 뒤 원본 불일치로 멈추고, 전체 검사와 블록을 다시 만들어야 한다. 이 기록은 작업 브랜치에만 두고 적용 결과를 받은 뒤 main에 넣는다.
- **미실행:** 사내 적용·기동·화면 확인(사용자 실행 결과로 따로 기록한다).
- **사내 적용 결과(사용자 보고, 2026-11-19):** 사용자가 ‘사내배포 완료했고’라고 알리고, 기본 가이드(Confluence 문서 확인 가이드)의 단계 화면에서 작업 둘을 보고 ‘실행’을 눌러 ‘실행 준비’ 창이 뜨는 데까지 써 보았다고 했다. 결과 줄 원문은 받지 않았다. 이 세션에서 따로 확인하지 않았다.
