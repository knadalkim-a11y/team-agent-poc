# 탐색·패널 UI 검증

<a id="sidebar-stable-scrollbar-20261105"></a>

## 2026-11-05 · 업무/워크스페이스 스크롤바 폭 고정

- **CI472 Windows 문서 검사 실패·보완:** 통합 head `98e3006`의 [Source audit Windows](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41952865848/job/127000666708)에서 `evals/v4-ui-20260930.md`가 1MiB 한도를 넘었다. 당시 LF 원본은 1,045,608바이트·3,722줄이지만 Windows CRLF checkout은 1,049,330바이트로 1,048,576바이트 한도를 초과한다. Ubuntu 검사는 통과했으며 제품 실패와 구분한다. 이번 범위인 공통 패널·Q1 준비 기록을 이 기존 검증 문서에 원문 그대로 옮기고 원래 파일의 앵커·연결을 유지했다. 검사 한도와 제품·시험 코드는 변경하지 않는다. 로컬 tracked Markdown 전체를 CRLF로 바꾼 조건과 LF 원본 모두 문서29개·링크2,876개·오류0·검토 후보0 및 diff 검사를 통과했다. 이동 후 v4 문서는 LF 1,037,553바이트·CRLF 1,041,256바이트다. 보완 head의 전체 CI로 최종 판정한다. 최초 실패 로그는 보존한다.

- **실제 main 통합:** #121의 CI470 전체 성공·실측·캡처 검수와 병합 후 최신 main `01a192d66e7ec4ecfa1b669ec284fb732529ef85`를 merge했다. 앞서 준비한 제품·검사 코드와 동일하며, #118·#119·#120·#121 기록을 보존한다. 통합 패치 SHA256은 `3c3476fe1ce7c1111530c18dc86732b45ee6d3db5c71503514bcdfbbf71abe24`이고, 최종 head 전체 CI 및 새 `workMode`가 담긴 22회 실측·캡처 판정은 [PR #122](https://github.com/knadalkim-a11y/team-agent-poc/pull/122) 본문/Checks에 연결한다.

- **병합 검토·CI467 직접 확인:** head `3b68770`의 [CI467](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41946946574) 전체 성공과 [22회 실측·두 화면 PNG](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41946946574/artifacts/13380265922)를 직접 확인했다. 1366×783 펼침에서 업무→워크스페이스→업무의 넘침은 false→true→false, 내부 폭248px·모드 영역232px·각 버튼112px·아이콘16px가 같았다. 접힘은 외부56px·내부48px·모드 영역32px·버튼26px·아이콘16px, 예약 폭은 모두7px였다. 기존 head의 실제 색상·문구와 최신 통합본은 구분한다.
- **통합 준비·재발 근거:** #121 후보 `dbb6d05`와 합치며 게시/권한 수정·공통 패널 스타일·제목 접기 대기를 보존했다. 겹치지 않는 소스 변경을 합치고 patch SHA256을 다시 계산했으며 Sidebar 결과 해시와 #121의 나머지 결과 해시를 각각 보존했다. 실측 JSON은 `mode` 좌표 객체가 모드 이름을 덮던 기록 충돌을 발견해 이름을 `workMode`로 분리했다. 제품 변경과 실측 단언은 추가하지 않는다. 통합 후보 Node676/676·Python frontend19통과/고정 소스 필요13미실행, Python 구문·문서·diff 검사를 통과했다. #121 병합 뒤 실제 최신 main과 통합한 최종 head 전체 CI·실측을 확인하고 병합한다.

- **요청·기준:** 사용자에게 스크롤바의 상시 표시와 자리 확보를 구분해 설명한 뒤, 내용이 넘칠 때만 표시하고 자리는 항상 확보하는 구현 요청을 받았다. 시작 main은 `818e31c57403ccc9e4893b464f412a4b2494a7bf`다. 미병합 #120(게시 상태)·#121(오른쪽 패널)은 별도 범위이며 이 브랜치로 옮기지 않는다. [결정](../docs/mockups/ees-work/TASK.md#sidebar-stable-scrollbar-20261105).
- **원인:** Svelte Sidebar 바깥 폭은 256/56px로 고정되어 있지만 `.ees-sidebar-scroll`이 `overflow:auto`만 사용해 고전형 스크롤바 유무가 내부 폭을 바꾼다. 상단 모드 버튼도 내부 폭의 50%를 사용해 함께 변한다. 코드로 확인한 원인이며 사내 화면 직접 실측은 하지 않았다.
- **수정:** 스크롤 컨테이너에 `scrollbar-gutter:stable`을 적용하고 `overflow:auto`는 유지한다. 접힌 모드 버튼은 좌우 4px, 대화 버튼은 숨은 글자와의 간격 0으로 정리해 예약된 스크롤 공간 안에서도 기존 16px 아이콘을 보존한다. 저장·권한·실행·메뉴 선택 로직은 변경하지 않는다.
- **검증 설계:** 기존 `test_navigation_v2_geometry_modes_categories_global_tools_and_draft`를 확장한다. 실제 두 모드의 메뉴 높이 사이에서 창 높이를 정해 업무는 비넘침·워크스페이스는 넘침인 조건을 반드시 만든다. 1366px의 긴 창/경계 높이에서 펼침→접힘→재펼침과 업무→워크스페이스→업무를 왕복하며 실제 버튼 폭·가로 위치, 아이콘 크기/잘림, 가로 넘침 없음, `overflow:auto`, 대화 초안 보존을 확인한다. 매 측정은 `sidebar-scrollbar-geometry.json`, 경계 화면은 `sidebar-scrollbar-work.png`·`sidebar-scrollbar-workspace.png`에 보존한다.
- **환경 경계:** 앞선 진단의 로컬 Chromium 기동은 환경 제한으로 실패했고, 로컬 HTML 브라우저 열기도 URL 정책으로 차단됐다. 같은 우회·반복 실행은 하지 않는다. 실제 제품 브라우저 검증은 PR CI에서 수행하며, 로컬 소스 검사와 구분해 기록한다. 사내 적용은 미실행이다.
- **로컬 검증:** 고정 Open WebUI `2a960a5` 원본 해시와 패치 적용을 확인하고 변경된 Sidebar 1개의 결과 해시 및 패치 해시만 갱신했다. Sidebar Svelte 컴파일 오류/경고 0, Node motion/Svelte 39/39, Python 시험 구문, 문서 점검 오류/검토 후보 0, 시험 ID 감사 오류 0, diff 검사를 통과했다. frontend 32건 중 26건은 통과했고 6건은 이 소스 checkout에 TypeScript가 없어 실행 준비에서 실패했다(`Cannot find module .../node_modules/typescript`). 제품 실패로 단정하거나 제외해 성공으로 표시하지 않으며, 고정 의존성을 설치하는 PR CI에서 32건 전체와 실제 제품 브라우저를 확인한다.
- **CI465·검사 조건 보완:** [PR #122](https://github.com/knadalkim-a11y/team-agent-poc/pull/122) 최초 head `ebb0c3e`의 [CI465](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41945760866)에서 고정 프런트엔드 빌드와 source 32/32를 통과했다. 후속 자체 검토에서 공통 `ChromePipe`가 `--hide-scrollbars`를 사용함을 발견했다. 이 조건의 통과만으로 실제 스크롤바 폭 검증을 완료 처리하지 않는다. 기본값은 유지하고 MotionNativeTests만 그 옵션을 끄며, 모든 측정에서 스크롤바 예약 폭이 0보다 큰지도 검사한다. 제품 CSS는 추가 변경하지 않고 보완 head의 전체 CI로 판정한다. 최종 head·CI와 실측은 이 PR 본문/Checks에 연결한다.

<a id="initial-author-list-ready-20261105"></a>

## 2026-11-05 · 실제 제품의 첫 작성 목록 준비

- **최초 실패:** #122 통합 head `3831948`의 [CI473 전체 제품 검사](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41953277437/job/127004432217)는 본 제품 흐름을 통과한 뒤 중앙 대화 검사에서 새 절차 이름 입력을 위한 물리 클릭의 포커스 단언이 실패했다. Windows·Linux 소스 검사는 통과해 앞선 문서 크기 실패는 해결됐다. [실패 PNG·JSON·보고서](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41953277437/artifacts/13382123455)를 직접 확인했다.
- **관찰·원인:** 직전 서버 목록은 비어 있었지만 실패 화면에는 초기 절차3개와 ‘배포 산출물 점검’ 상세가 열렸고 포커스는 BODY였다. JS 예외는 없었다. mode→create→type은 초기 등록·목록 재배치를 기다리지 않았으며, launcher의 첫 author refresh는 `initialize_procedures` 뒤 목록과 선택을 갱신한다. 클릭 직전 전환 순간은 미관측이므로 정확한 프레임을 추정하지 않는다. 이는 기존 CI419에 기록된 첫 작성 준비 누락과 같은 경로다.
- **보완·검증:** 이미 Native 작성 검사에서 쓰던 `open_initialized_author_list`와 같은 준비 조건을 실제 제품 gate에 적용했다. 물리 모드 전환 뒤 공개 refresh의 초기 등록 완료, 서버/화면의 절차 ID 목록 일치, 패널 준비를 확인하고 새 양식을 클릭한다. 같은 초기 경로인 본 제품·중앙 대화 흐름 둘 다 사용하며 준비한 ID를 보고서에 남긴다. 물리 클릭·포커스·입력·저장·미게시/대화 제안 보존 단언, 제품 코드와 시간 제한은 유지한다. 변경된 Python 구문·문서29개/링크2,877개 오류0·시험 ID 감사1,597개 오류0·diff 검사를 통과했다. 보완 head 전체 CI·실제 제품 보고서로 최종 판정한다.

<a id="shared-panel-style-20261105"></a>

## 2026-11-05 · 오른쪽 패널 배경·탭 공통화

- **최종 통합·직접 검수:** #120 병합 main `c41634a`를 포함한 head `dbb6d0543998cb01433701ea1e89c3debaea323c`의 [CI470](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41950730475)가 필수39성공·출하1정상생략, native-compose97/97로 끝났다. [브라우저 증거](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41950730475/artifacts/13381327290)의 `shared-panel-styles.json` 9개 화면 배경 `rgb(250,250,250)`, 7개 탭 화면 높이36px·글자12/18px·간격20px·밑줄2px, 3개 키보드 포커스의 안쪽2px를 직접 확인했다. 작성/단계1366px·작업480px PNG에서도 공통 배경·탭·잘리지 않는 가시 포커스를 확인했다. #121은 `01a192d66e7ec4ecfa1b669ec284fb732529ef85`에 병합됐으며 아래 최초 실패와 당시 관찰은 유지한다.

- **기준·범위:** 마지막으로 전달받은 사내 배포 커밋 `cb612c9`와 작업 시작 main `93749cc`의 제품 CSS를 대조했다. 실제 사내 실행 중 커밋은 직접 조회하지 않았다. 사용자가 비교 시안을 보고 워크스페이스 기준의 배경·탭 공통화를 승인했다([결정](../docs/mockups/ees-work/TASK.md#shared-panel-style-20261105)). 열려 있던 게시 기능 #120·왼쪽 메뉴 #119와 별도 범위이며 그 작업 파일은 건드리지 않는다.
- **원인:** 공통 패널 배경은 `#F3F3F5`인데 작성과 개요/단계 화면만 `#FAFAFA`로 덮어썼다. 업무 탭은 기본 글자가 본문색을 상속하고, 작성 탭은 별도 규칙에서 보조색·다른 높이/여백을 지정했다.
- **수정:** `--ees-surface-panel`을 `#FAFAFA`로 맞추고 화면별 배경 재지정을 제거했다. `.ew-tabs`·`.ew-author-tabs`를 한 CSS 규칙으로 합쳐 기본/선택 글자·밑줄·크기·간격을 통일했다. 작성 하단도 같은 배경을 상속한다. 공통 탭의 가로 스크롤 영역에서 키보드 포커스가 잘리지 않도록 테두리를 안쪽에 표시한다. 상태 색상·카드·입력창·공장 선택기·업무 동작은 유지한다.
- **재발 방지:** AGENTS의 공통 패널 규칙과 기존 `test_c18_panel_cards_input_hover_and_keyboard_focus`에 화면 전환 후 실제 computed style 비교를 추가했다. 작성 내용·작업 편집·규칙·기록·도구, 업무 개요·단계·작업 및 좁은 화면의 패널 배경/탭·hover·overflow와 원본 정의 보존을 확인하고, 기존 카드/입력/대화 배경·키보드 포커스 단언을 유지한다. Tab/Shift+Tab으로 작성·단계·좁은 작업 탭의 가시 포커스와 안쪽 테두리도 비교한다. 기록에서 단계로 바로 진입하는 경우에는 뒤로 가기로 업무 개요도 명시적으로 연다. 결과는 CI의 `shared-panel-styles.json`과 화면 캡처에 남긴다.
- **로컬 검사:** Node `test_ees_work_figma_runtime_ui.cjs`·`test_ees_work_authoring_ui.cjs`·`test_ees_v4_layout.cjs` 446/446 통과. Python `tests.test_ees_branding_build`·`tests.test_ees_work_designer` 35개 실행, 34 통과·고정 upstream wheel이 필요한 1개 건너뜀. `scripts/check_docs.py` 오류0·검토 후보0, 변경 Native 시험의 `py_compile`, `git diff --check` 통과.
- **1차 CI457 · `a11edca`:** [실행](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41935664837). 제품 빌드·전체 Native 제품·작성/실행/움직임·기존 레이아웃 검사는 통과했다. 새 색상 시험은 작성 내용·작업 편집·판정 규칙·게시 기록·도구의 배경/탭 단언을 통과한 뒤, 워크스페이스 모드에서 업무의 `records` 단추를 누르려 해 실패했다. 작성 화면 `shared-panel-authoring-1366.png`를 직접 열어 배경·선택/비선택 탭·간격·가독성을 확인했다. 업무 화면 공통화까지 통과한 것으로 간주하지 않는다.
- **보완·현재 증거:** 시험에서 실제 메뉴로 업무 모드로 전환한 후 기록을 열도록 고쳤다. 업무 개요도 명시적으로 방문하고, 작성·단계·좁은 작업 화면에서 Tab/Shift+Tab의 가시 포커스를 확인한다. 가로 스크롤 탭의 포커스를 안쪽으로 표시하는 CSS 보완도 포함했다. 최종 head의 CI 결과·검토 요약은 [PR #121](https://github.com/knadalkim-a11y/team-agent-poc/pull/121)의 본문과 Checks가 현재 판정이다. 해당 실행의 `ees-work-browser-evidence-native-compose`에 `shared-panel-styles.json`과 작성·단계·좁은 작업 화면 캡처를 보존한다.
- **환경·제한:** 로컬 브라우저 실행은 환경의 소켓 권한 제한으로 사용할 수 없어 Native 브라우저 검증은 CI에서 수행한다(1차 Chrome 156.0.8078.79). Figma C1(`948:1078`)은 읽기만 했으며, 실제 사내 배포·운영 데이터 검사는 하지 않았다.

- **CI459 추가 실패와 보완(2026-11-05):** head `9888c1e`의 [CI459](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41938022868) native-compose는 C18의 480px 전환에서 `data-compact=true` 대기 실패다. 앞선 `open_run`이 메뉴를 수동으로 펼쳤고 1366→480은 둘 다 1440px 아래여서 제품은 그 선택을 유지한다. 추가한 시험의 준비 오류이며 제품 동작은 바꾸지 않는다. 이 흐름에서 실제 메뉴 접기 단추를 누르고 compact를 확인한 뒤 480px 스타일·Tab 포커스·가로 넘침·저장본 보존 검사를 계속한다. 최초 실패와 검사 단언을 보존하고 통합 head의 전체 CI로 확인한다.

- **세 PR 통합 준비 검수:** #118 설명·#119 제목·#120 게시 상태/공장 권한 보완과 #121 공통 스타일을 합친 로컬 후보에서 `node --test tests/*.cjs` 676/676, 문서 검사 오류0·검토 후보0, diff 검사 통과. STATUS·CHANGELOG는 모든 변경 기록을 보존했다. 각 PR은 선행 PR 병합 뒤의 최신 main을 부모로 포함한 최종 head의 전체 필수 CI 성공을 확인하여 순서대로 병합한다. 이 로컬 검사는 실제 Native·Windows 최종 CI를 대신하지 않는다.

- **최신 main 통합(2026-11-05):** #118의 CI462·#120 최종 head `9d1df66`의 [CI468](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41948573115) 성공 뒤 병합 main `c41634a`를 포함했다. #120의 공장 권한 보완과 Q1/메뉴 접기 준비 보완을 보존한다. 480px 색상·포커스 검사도 실제 overlay 상태가 반영된 뒤 측정한다. 통합 후 Python 구문·문서·diff 검사를 확인하고 #121 최종 head 전체 CI의 스타일 실측·캡처·기존 자료 보존 결과로 판정한다.
<a id="q1-viewport-settle-20261105"></a>

## 2026-11-05 · Q1 창 크기 전환의 패널 준비 조건

- **후속 검증:** #120 최종 head `9d1df66`의 [CI468](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41948573115)은 layout5/5와 native-compose97/97을 포함해 전체 필수39개가 성공했다. 최초 CI464 실패와 CI466의 별도 제목 접기 실패는 보존한다. #120은 `c41634a`로 병합했고 #121도 해당 준비 보완을 포함한다.

- **최초 실패:** #120 통합 head `153af6f`의 [CI464](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41944193231), Ubuntu 24.04·Python 3.11·Chrome 156.0.8078.79에서 native-compose 97개 중 96개가 통과하고 Q1의 1095px `overlay=true` 즉시 단언 한 곳이 실패했다. 작성 31/31과 실행 23/23은 통과했다. [최초 PNG·DOM·결과](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41944193231/artifacts/13378816153)를 보존한다.
- **관찰·준비 누락:** 마지막 대기는 sidebar/panel-space의 애니메이션 없음이고 실패 값은 `overlay=false`였다. 캡처와 DOM은 창1095px·접힌 메뉴56px에서 패널 전환 전 배치를 보여 준다. helper는 `innerWidth`와 CSS 셸 폭, 기존 compact 값만 기다렸다. 1280→1095는 compact가 계속 true여서 Svelte의 window resize 반영 전에도 모두 만족한다. 제품의 overlay 기준은 창 폭과 고정480px 기준이며 패널의 사용자 폭400px와 다르다.
- **보완·판정:** Q1의 이 전환에 실제 `data-overlay=true` 준비 대기를 추가한다. 같은 viewport helper에 선택적인 기대 상태를 전달하므로 제품 속성을 직접 바꾸거나 기다리는 시간을 늘리지 않는다. 기존 overlay 단언·대화 폭1039px·닫기/재열기와 다른 치수 단언은 유지한다. Python 구문·문서·diff 검사 후 최종 head 전체 CI로 판정하며 이 준비 누락을 단순 재시도 성공으로 해결했다고 쓰지 않는다. #121의 좁은 화면 검사에도 같은 준비 조건을 사용한다.


<a id="workspace-heading-clip-20261105"></a>

## 2026-11-05 · 워크스페이스 메뉴 제목 잘림

- **통합 후속 검증:** #120 최종 head `9d1df66`의 [CI468](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41948573115)에서 움직임6/6·native-compose97/97 및 전체 필수39개가 성공했다. 제목 접기의 실제 애니메이션 종료 후 padding0·재펼침 검사를 통과했다. #120 병합 main `c41634a`에 포함됐으며 #121 통합에서도 유지한다. 아래 최초 실패와 당시 관찰은 보존한다.

- **병합 통합 CI466 후속(2026-11-05):** #120 head `707b249`의 [CI466](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41946435594) native-compose 97개 중 96개가 통과했다. 앞서 보완한 Q1을 포함한 layout5/5·작성31/31·실행23/23은 통과했고, 이 제목 검사의 첫1920px 접기에서 높이0 대기 뒤 padding0 즉시 단언이 실패했다. [최초 PNG·DOM·확장 치수](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41946435594/artifacts/13378893830)를 보존한다. 확장 높이26/36/36과 실제 글자16px는 정상이었으며 실패 캡처는 접힌 메뉴를 보여 준다. 실패 직전 padding 수치 자체는 기록되지 않아 추정값을 쓰지 않는다.
- **누락 경로와 보완:** 기존 검사는 펼침/재펼침만 하위 애니메이션 종료를 기다렸고, 접기는 반올림되는 DOM 높이0만 기다렸다. CSS는 높이와 padding을 함께 전환하므로 높이0만으로 계산된 padding의 종료를 보장하지 않는다. 접기에도 같은 `getAnimations({subtree:true})` 종료 대기를 적용하고 실제 padding0 단언·폭/높이·일반/동작 줄이기·재펼침 조건을 유지한다. 재발 시 실제 padding 수치가 단언 로그에 남도록 측정 행도 전달한다. 제품 CSS·시간 제한·실제 클릭은 변경하지 않고, Python 구문·문서·diff 검사 및 새 통합 head 전체 CI로 판정한다.

- **요청·원본:** 사용자가 ‘업무 만들기·AI 설정·관리자만’이 반쯤 가려진다고 보고했고, 코드 비교 뒤 수정·병합을 요청했다. main `93749cc10fc551748c018a06cc85318013d2970d`에서 해당 제목 CSS와 기존 Native 탐색 시험만 수정한다. 다른 열린 PR #118은 시스템 계정 설명 변경이며 이번 수정과 분리한다.
- **설계 비교:** 2026-11-05 KST에 Figma `835:324`와 `1068:6147`의 왼쪽 패널을 읽고 렌더를 확인했다. 제목은 16px 행에 위/아래 여백 4/6px 또는 14/6px를 더한 26/36/36px다. Figma 원본에서는 잘리지 않았으나 제품의 11-02 움직임 CSS는 세 제목 모두 `height:18px;overflow:hidden`으로 제한한다. `border-box`와 기존 여백이 결합해 글자가 잘리는 코드 원인을 확인했다. 앞선 정지 화면·폭·카테고리 검사에는 제목의 실제 가용 높이 검사가 없었다.
- **수정:** 일반 설명의 18px와 그룹 제목의 26/36px를 분리한다. 접을 때 제목의 높이와 위아래 여백을 함께 0으로 전환하고 펼치면 원래 간격으로 돌아온다. 기존 속도·이징·동작 줄이기 설정을 재사용하며 새 화면·기능·설정은 추가하지 않는다. Figma·승인 목업·저장/게시·권한 동작은 변경하지 않는다.
- **재발 검사:** 기존 `test_navigation_v2_geometry_modes_categories_global_tools_and_draft`에서 관리자 제목 3개의 실제 높이, 여백을 뺀 가용 높이와 행 높이, 다음 버튼과의 겹침을 확인한다. 1920×1080·1366×768과 동작 줄이기에서 접기 후 높이/여백 0·재펼침 복구를 검사하며 `workspace-heading-1366.png`와 `workspace-heading-geometry.json`을 CI 증거에 남긴다.
- **로컬 검증:** 관련 Node motion/Svelte 39/39, branding 33통과·공식 wheel 필요 1생략, 수정한 Python 시험 구문·문서 점검(오류0/검토 후보0)·시험 ID 감사(기존1332/현재1591, 오류0)·`git diff --check` 통과. 최종 전체 CI는 이 수정 PR에서 확인한다. 최초 로컬 Chromium 기동은 `socket() failed: Operation not permitted`로 중단되어 실제 제품 브라우저 재현을 로컬 성공으로 기록하지 않는다. 사내 사용자 화면·배포는 미확인이다.
- **첫 CI·보완:** head `10d01f4`의 [CI451 native-compose](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41931724663/job/126932846049)는 95통과·1실패였다. 새 제목 검사에서 세 제목을 기다렸지만 합성 workflow fixture에는 Native 계정 DB가 없어 `native_access`가 모두 false였고 ‘AI 설정’ 그룹 자체가 없었다. 실패 캡처에서 ‘업무 만들기·관리자만’의 정상 표시는 확인했지만 세 제목 검증 완료로 간주하지 않는다. 기존 `SourceShellNativeTests.enable_native_menus`와 같은 명시적 합성 접근 응답을 이 시험 안에만 설정하고 refresh 후 검사하도록 보완한다. 제품 권한·CSS는 추가 변경하지 않으며, 높이·간격·접기/재펼침 조건도 그대로 유지한다. 보완 head의 전체 CI와 3개 제목 실측·캡처를 확인한 뒤 병합한다.
- **CI453 준비 실패·재검 경계:** head `288bd4e`의 [source-frontend job](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41934160143/job/126938318914)은 공식 wheel 비교의 첫 `about:blank` 진입에서 `Browser.getVersion` 응답 시간 초과로 중단됐다. 수정 프런트엔드 빌드나 제목 검사는 아직 시작하지 않았고 Chrome 지연의 직접 원인은 미확정이다. 같은 제품/준비 코드의 CI451 source-frontend 성공과 기존 [Chrome 준비 경계 기록](v4-ui-20260930.md#integrated-sixth-ci-20261002)을 참고하되 같은 원인으로 단정하지 않는다. 이 최초 실패를 기록하는 문서 변경만 반영한 새 head를 새 runner에서 1회 재검한다. 제품·fixture·시간 제한·assertion은 바꾸지 않으며, 같은 기동 실패가 반복되면 추가 자동 재시도 없이 준비 증거부터 조사한다. 최종 성공 조건은 새 head의 전체 필수 CI 및 3개 제목의 실측·캡처 통과다.
- **CI454 화면 상태 보완:** head `d5889aa`의 source-frontend는 준비·원본 비교·수정 빌드 모두 통과했다(Chrome 지연의 원인 해결로 간주하지 않음). [native-compose job](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41934873539/job/126943490354)은 95통과·1실패였고, 새 검사는 1920px 제목 높이/여백/접기/재펼침을 통과한 뒤 1366px에서 `[0,0,0]`을 측정했다. 실패 PNG·DOM은 1366×768, 사이드바 폭56px, ‘사이드바 펼치기’ 버튼으로 접힌 상태를 확인했다. 소스의 기존 1440px 경계 자동 접힘을 시험 준비에서 빠뜨린 원인이다. 각 창 크기 변경 뒤 기존 `open_sidebar()`의 실제 클릭·가시 폭 확인으로 펼침을 준비하며, 제품의 자동 접힘은 변경하지 않는다. 첫 실패 위치를 잃지 않도록 각 측정의 창 크기·동작 줄이기·재펼침 상태와 실측을 파일에 즉시 보존한다. 높이·행 높이·버튼 간격·접힘0 기준은 그대로 유지하고 보완 head의 전체 CI로 재검한다.

<a id="navigation-motion-product-20261102"></a>

## 2026-11-02 · 탐색·패널 시안 2 제품 반영

- **기준/환경:** main `745e5ef`, 시안2 `aecff7a`, Open WebUI0.11.3 소스 `2a960a5`, 고정 Node22.16.0/npm10.9.2. Figma C3 `1443:137` 현재 렌더를 읽고, 종전 페이드/패널16px/즉시 공간 변경과 승인2판의 차이를 TASK에 기록했다. 시안 HTML은 그대로 보존한다.
- **수정/검증 경계:** Svelte 탐색·범위·패널 및 공통 motion/CSS, 전역 기존 도구 목록·소속별 편집 권한을 구현한다. 새로운 도구 저장 형식·운영 요청·실제 사용자 자산 변경은 없다. Native 브라우저는 실제 제품과 업무 서비스/임시 SQLite를 쓰며 계정·대화 응답·외부 전송은 명시적 합성 fixture다.
- **첫 검사와 수정:** 기존 시험의 붙은 패널 내용 페이드/즉시 닫기 및 breakpoint에서 exit 취소 기대를 승인된 동일 표면 슬라이드로 갱신했다. 기존 도구 fixture의 누락된 필수 system_id와 명시적 담당 시스템 선택/비동기 담당자 조회를 보완했다. UI Node307/307, 운영 계약52/52를 통과했다. 전역 목록의 권한 회수·업무용 목록 범위, 다른 시스템 계약 저장·읽기 전용·늦은 응답을 포함한다.
- **첫 빌드 실패:** Svelte 빌드 중 도구/스타일 원본이 변경되어 provenance 검사 `Frontend inputs changed while building`이 산출물 채택을 차단했다. 실패 checkout/log는 보존하고 같은 고정 commit의 새 checkout으로 최종 원본을 다시 빌드한다. 실패 산출물을 제품 검수 통과로 사용하지 않는다.
- **첫 실제 제품 검사:** 고정 소스 빌드/패키지 후 Chromium133에서9개 Native 시험을 수행했다. 붙은 패널·범위 빠른 왕복/응답 역전·접힌1920/480 목록·키보드 패널/초안5개가 통과했다. 새 기하 측정은 메뉴 전환 중 사라진 카테고리 값을 처리하지 못했고, 기존 시험은 펼침 중 보이지 않는 패널 단추/범위 휠 지점과 새 담당 시스템 선택 단계를 고려하지 않아 실패했다. 실제 일반 패널의 닫기 아이콘 HTML이 이스케이프돼 문자열로 보이는 결함도 발견해 명시적 버튼 렌더로 수정했다. 범위 닫기의 clip-path 기준값과 라벨 flex 크기 때문에 생길 즉시 전환도 보완한다. Svelte의 새 self-closing div 경고를 제거했고 원본 검토 후 새 checkout에서 다시 빌드한다. 이 과정의 두 번째 inputs-changed 차단도 보존한다.
- **추가 자동 검사:** 전체 Node665/665, 실제 patched checkout을 쓰는 frontend32/32, 목업 빌드 계약6/6 통과.
- **진행 중:** 보완한 실제 Native 브라우저 검사, 최종 push·PR·CI. 사내 사용자 확인·병합·실제 적용은 미실행이다.

- **후속 검수:** 새 패키지14개 Native 검사에서10개가 통과했다. 이전 순간 전환을 전제로 한 overlay 폭 측정/아직 펼쳐지는 목록 클릭/도구에서 숨겨진 작업 위치 선택을 새 동작에 맞춰 보완했으며 해당3개는 후속 검사에서 통과했다. 모드 글자의 max-width가 inline span에 적용되지 않는 실제 결함을 중간 프레임 검사로 찾아 모드 단추를 flex로 바로잡았다. 이 CSS 보완본을 새 고정 checkout에서 빌드해 최종 검수한다. 기존 담당 시스템을 명시하는 도구 작성·공용 도구 스타일·Native 화면 왕복의 미저장 절차/도구 초안은 실제 제품에서 통과했다.
- **공용 도구 보존:** Python3.12의 격리된 로컬 시험 환경에서 `test_ees_shared_tools_native.py`43/43 통과. 실제 Native 자산/개인 PAT/ACL 및 임시 SQLite를 사용하며 외부 응답은 합성이다. CI의 Python3.11·Windows 검사는 별도다.


### 최종 로컬 결과

- 고정 소스 빌드와 실제 wheel 패키지를 완료했다. wheel SHA-256 `fd76a30d52f455d23338e702177f117c5e069395c665a69e80b49d3e0034ceaf`, 프런트엔드5582파일이다. 원본 지문 검사를 우회하지 않았다. EesShell의 기존 root/resize 접근성 경고3종은 남으며 새 코드의 self-closing 경고는 제거했다.
- 최종 패키지의 Native14개 대상은 모두 통과했다. 최종 묶음은13통과/1실패였고, Native 왕복 시험 준비 중 모드의 실제 조회와 목록 클릭이 겹친1건은 조회 완료 후 초안을 준비하도록 보완하여 재검 통과했다. 해당 왕복과 기하/정지 스크린샷2개 재검도 통과했다. 단순 정지 캡처를 애니메이션 검증으로 대체하지 않았다.
- 실제 프레임에서 사이드바56~256px(21개 관측값), 카테고리0~36px(27개), 작업 위치0~127px(35개), 모드 라벨0~65.75px(5개), 라벨 투명도 항상1을 확인했다. 범위 메뉴는 실제 clip-path 중간값과4px 이동, 패널은 불투명 전체 폭 슬라이드/대화 공간 전환을 확인했다. 승인2판의 동작·크기 기준과 대조한 범위이며 기존 대화/업무 본문 전체의 픽셀 동일성을 주장하지 않는다.
- 1920/1366에서 붙은 패널,1095의 겹친 패널,1920/480의 접힌 공장/시스템 목록을 검사했다. 빠른 왕복·중간 반전·동작 줄이기·메뉴 교체·응답 순서 역전·권한 회수/없음·검색·키보드/초점·대화와 업무 초안·기존 도구 작성 및 Native 화면 왕복을 포함한다. 전역 화면은 EMS/FDC 두 시스템의 실제 저장된 합성 도구를 동시에 보이고, 업무로 돌아오면 위치/카테고리 접힘/대화 초안을 유지했다.
- 재현 진입점: `node --test tests/*.cjs`665/665, `test_ees_frontend_build.py`32/32(`EES_TEST_FRONTEND_SOURCE_DIR`는 고정 patched checkout), `test_ees_work_operations.py`52/52, `test_ees_shared_tools_native.py`43/43, `test_build_design_mock.py`6/6. 실제 브라우저는 `EES_TEST_CHROME`, `EES_TEST_BRANDING_DIR`, `EES_TEST_SCREENSHOT_DIR`를 지정한 `test_ees_motion_native`6개와 SourceShell4개/작성3개/HelperChat1개를 사용했다. 로컬 원본 로그는 `scope-qa/*release*.log`, 프레임/스크린샷은 `dist/navigation-motion-product-release/`다.
- `python scripts/check_docs.py`, `git diff --check` 통과. 누적 v4 기록이1MiB 점검 한계에 닿아 **이번 기록만** 이 문서로 연결했고 기존 날짜별 근거/앵커는 보존했다. 승인된 시안2 HTML/편집 원본은 변경하지 않았다.
- 로컬 완성 뒤 같은 브랜치의 push·PR·CI를 수행한다. 원격 결과는 PR의 검사/증거로 확인하며, 실제 사내 사용자 확인·병합·적용은 수행하지 않았다.

### 원격 게시 원본 연결

로컬 Git의 HTTPS 인증 정보가 없어 직접 push가 실패했고, 이미 연결된 GitHub의 Git 객체 API로 같은 파일·부모 순서를 게시했다. 각 파일의 Git blob SHA와 각 커밋의 root tree SHA를 로컬과 대조해 모두 일치했다. 게시 시각/작성자 메타데이터가 달라 커밋 ID는 바뀌며, 기존 로컬 이력도 보존한다. 승인된 시안2는 아래 `aecff7a`에 대응하는 원격 `39d4739`에서 읽을 수 있고 HTML SHA-256은 TASK의 승인값 그대로다.

| 로컬 원본 커밋 | 원격 대응 커밋 | 동일한 root tree |
|---|---|---|
| `c8934f587a028ff244dfabe5ef3f1b4852e5a209` | [`dd76347`](https://github.com/knadalkim-a11y/team-agent-poc/commit/dd76347bd061fa877801df7ce9c487a5f60ebd86) | `1cea6f65daf28484379eaf52c44f62eca20b6e78` |
| `3d47e6b4edeff9ec48fdb9f1c3e81e26e2f034e7` | [`b3e91f7`](https://github.com/knadalkim-a11y/team-agent-poc/commit/b3e91f773342b8413b48aaae8985f697eb8ca2ed) | `458c3fef43893596fb871eea4ab4503c25023088` |
| `f0fe99e65a75cb07959f5daadd99d1293260f7fe` | [`0389e16`](https://github.com/knadalkim-a11y/team-agent-poc/commit/0389e16cf18e139d2799747dbdb0b17171f786fd) | `ae0dfa8eb76f10c6aca0f4288850756cad68b64c` |
| `aecff7a3ae41a3031eff8cffeb5252f5a7bd86af` | [`39d4739`](https://github.com/knadalkim-a11y/team-agent-poc/commit/39d473919a4457b6c50b61800c683d9f19e2a382) | `68bbac1825a5d3016b3348755d6b3d25cc099a68` |
| `93154e211a6b99e6607db6823c671d9f3f9792ba` | [`24c2869`](https://github.com/knadalkim-a11y/team-agent-poc/commit/24c28699bdbdd92c064ad37aa981ec526a158d5d) | `c20e2b9cd0dfdc7b84c69762500e611e0a88b7b9` |

이 대응 기록은 원격 게시 방식과 원본 동일성에 대한 증거다. PR·CI 최종 판정은 해당 PR의 head/Checks를 따르며, 병합·사내 적용을 뜻하지 않는다.

### CI430 Windows 문서 검사와 후속

- [CI430](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41427385280)의 head `64a4b84`는 Linux 소스 감사와 고정 wheel 검증을 통과했지만 Windows 문서 검사에서 누적 v4 기록이1MiB를 넘어 실패했다. LF 1,046,321bytes는 한계 아래였으나 Windows CRLF 변환 후1,050,030bytes가 되어 한계1,048,576bytes를 넘었다. 테스트 ID 감사는 오류0이었다.
- 이번 탐색의 시안1/2·접힌 메뉴 첫 수정 기록만 이 문서 아래로 내용 그대로 옮기고 기존 앵커를 각각 연결했다. 날짜·원본·첫 실패·검증 경계는 보존했으며 제품 코드·검사 크기 제한·줄바꿈 정책은 바꾸지 않았다. 새 head 게시로 이전 진행 중 작업은 workflow의 기존 PR 중복 취소 정책을 따른다. 최종 전체 CI는 같은 PR에서 다시 확인한다.

### CI431 실제 브라우저·Windows 첫 통합과 보완

- [CI431 첫 실행](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41427686210/attempts/1), head `d3fa248`:35성공/3실패/1취소/출하1정상생략이다. Linux·Windows 문서 감사, 실제 제품 기동/저장/재시작·계정/업무/실행·설치/복구는 통과했다. 실패는 Native 묶음3개, Windows platform1개이며 Linux 집계 실패·Windows 집계 취소가 뒤따랐다.
- **Native91/94:** Chrome156.0.8078.47에서 motion6/6·source shell10/10·작성30/30은 통과했다. Helper10중1개는 전역 도구에서 숨긴 작업 위치를 클릭했고, Q1 크기5중1개는 사이드바 전환 중251.515625px를 최종56px와 비교했다. 운영22중1개는480→1920 반응형 펼침 중 기존 `open_sidebar` 준비 동작이 다시 접어 버린 뒤 숨은 절차를 클릭했다. 로컬 Chromium133에서 같은3실패를 재현하고 실제 scope inert/높이0·사이드바56/category inert를 기록했다.
- **시험 보완:** 전역 도구에서 실제 업무절차 메뉴로 나온 뒤 범위를 바꾸고, 반응형 compact 상태와 실제 width/공간 transition 종료를 기다린 뒤 기존 최종 크기를 단언한다. DOM 강제 클릭·제품 상태 변경·대기 제한 완화는 없다. 첫 재검은2/3 통과했고 Q1에서 키보드 너비 변경 뒤 대화 공간이 아직 이동 중인744px를 최종504px와 비교한 경계가 이어서 드러났다. 같은 실제 transition 완료 대기를 키보드 helper에도 적용했다. Q1/물리 드래그2/2 후속 통과로 실패3개 및 관련 드래그까지4개 대상이 최종 통과했다. 제품 코드는 변경하지 않았다.
- **별도 Windows 시작 지연:** [platform job125221447017](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41427686210/job/125221447017)의 합성 launcher 조립1개가 `Node launcher probe timed out after 10s; stderr stages: entry not observed`로 실패했다(모듈33/34). 입력208bytes/SHA256 `c7bf9c7bf270383a3eaf5febc759fe32ba05afad6af9702a6f7679c46928797f`는 [CI418/419 기록](v4-ui-20260930.md#authoring12-rules-spacing-20261102)과 같다. 시험·조립기·10초 제한은 main부터 변경하지 않았다. Linux counterpart와 Windows 종료67/67은 통과했지만 Node 표식 전 초기화·모듈 로드·OS 중 직접 원인은 미확정이다.
- **다음 검증과 상한:** Native 시험 보완이 필요하므로 실패 Windows job을 먼저 별도 재실행하지 않고 보완 head의 전체 CI1회에 새 runner 확인을 묶는다. 이는 실행기 일시 지연 가설을 확인하는 제한 재검이며 같은 Node 실패가 다시 나면 자동 추가 재시도를 하지 않는다. 성공도 근본원인 해결로 기록하지 않는다. CI 최종 결과는 같은 PR #114에 남기고 병합·사내 적용은 수행하지 않는다.

### CI432 통과와 접힌 제품명 키보드 리뷰 보완

- [CI432](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41430757672), head `88c8dd3`는39성공/PR 출하1정상생략으로 완료됐다. Chrome156 Native94/94(Helper10·motion6·source10·입력5·실행6·작성30·레이아웃5·운영22) 및 Linux·Windows 전체 집계가 통과했다. Windows launcher34/34·종료67/67도 통과해 이번 제한 재확인에서는 진입 지연이 재현되지 않았다. 과거 지연의 직접 원인은 미확정으로 유지한다.
- **리뷰 발견:** 최종 PR 리뷰 확인에서 접힌 제품명 링크가 폭0이어도 Tab 순서에 남는 P2를 확인했다. 새 실제 키보드 회귀에서 접기 버튼→Shift+Tab이 보이지 않는 제품명 링크에 초점을 주는 실패를 수정 전 패키지에서 재현했다. 기존 애니메이션/가시성 검수는 제품명 링크의 Tab 순서를 포함하지 못했다.
- **수정:** Sidebar 소스의 제품명 링크에 compact 상태의 `inert`만 연결했다. 폭 애니메이션은 그대로이며 펼치면 링크가 다시 키보드·접근성 탐색에 포함된다. 검토 가능한 소스 patch와 해당 SHA-256을 갱신했고 새 고정 checkout에서 정상 빌드/패키지했다. wheel SHA-256 `79def116f2ab5557985f9285495c593785b2dd0090031c19ecd24ec8924a4668`다.
- **검증:** patched frontend32/32 및 새 제품의 키보드 회귀·접힌 범위 목록·전체 탐색 기하3/3이 통과했다. 물리 Tab/Shift+Tab/Enter로 숨은 링크 제외·토글 유지·펼친 링크 복구를 확인했고 가시 초점은199×22px/2px solid이며 실제 캡처를 열어 확인했다. 기존 대화 경로·초안·전역 도구·폭/높이 전환은 유지됐고 송신0건이다. 화면/실측은 `dist/navigation-motion-focus/`, 원본 로그는 `scope-qa/*focus*.log`에 보존했다.
- **후속:** 같은 PR에 리뷰 보완을 게시하고 새 head의 전체 CI를 확인한다. CI432 성공을 뒤의 소스 변경까지 검증한 것으로 간주하지 않으며 최초 실패·Windows 지연 기록은 유지한다. 병합·사내 배포는 하지 않는다.

<a id="navigation-motion-mock2-20261102"></a>

## 2026-11-02 · 요소별 움직임 · 탐색·패널 시안 2

- **요청·원본:** 사용자가 페이드 이외 방식과 요소별 적합성을 확인한 뒤 가장 아름답다고 판단하는 방식으로 만들어 달라고 요청했다. 로컬1판 `f0fe99e`를 보존하고 [같은 목업 원본](../docs/mockups/ees-work/design-mock-src/09-navigation-motion.html)과 [HTML](../docs/mockups/ees-work/design-mock-09-navigation-motion.html)을2판으로 갱신했다. 원본 SHA256 `81bf2ee71f2d32a35553c39ef5df5735524159be5351d09492ddf4d3567e2c87`, HTML `6b3aee6e99959500689cab5a7451578e249c3e691f43010b22298a93d6bf93fb`(410,166bytes)다. 제품 CSS/아이콘/고정 글꼴을 기존 빌더로 포함했고 제품 코드·Figma·원격 저장소는 변경하지 않았다.
- **변경:** 전환의 opacity/scale 효과를 제거했다(권한 없음의 정적인 비활성 표현은 유지). 사이드바 폭/라벨 잘림과 가로↔세로 모드 배치, 선택 배경 이동, 카테고리 높이/화살표, 위에서 아래로 펼쳐지는 범위 목록/4px 이동을 사용한다. 패널은 한 층에서 자기 너비만큼 이동하며 붙은 화면에서는 대화 옆 공간을 동시에 확보한다. 붙음/겹침 전환도 패널을 재배치하지 않고 공간만 바꾼다. 초기 진입에는 이동을 재생하지 않고 빠른 반전/동작 줄이기/초안과 범위 보존을 유지한다.
- **최종 상태 확인:** 같은 Chromium133.0.6943.0에서1920·1366·1024·480·320px의 범위 목록 이름/보조정보/선택 체크/검색/권한 없음/Esc, 카테고리3개, 도구 전역 범위, 업무 복귀 후 공장/시스템/접힘/초안 보존, 패널 아이콘 동일/초점 복귀/빠른 왕복을 확인했다.5폭 모두 가로 넘침 없음·JS 예외0이다.1024/320 인라인 sandbox(allow-scripts)·터치 환경에서도 범위 선택/닫기·모드·도구 진입을 확인했고 실제 캡처를 열어 확인했다.
- **움직임 확인:** 실제 진행 중 붙은 패널 공간160.21875px(0↔480)을 측정했다. 별도 검사에서는 전환 시간을 중간으로 고정해 사이드바191.03125px, 카테고리48.609375px, 선택 배경의 중간 좌표, 목록의 중간 clip/이동, 패널의 공간/위치 관계를 확인했다. 대상7개 모두 opacity1이고 opacity 키프레임0개다. 모드와 범위 목록의25ms 간격 반전,1200px에서 사이드바 조작에 따른 붙음↔겹침의 상태/오른쪽 위치 보존, reduced-motion0s를 확인했다. 이 검사는 실제 제품의 프레임률/성능 측정이 아니다.
- **첫 실패·수정:** 터치320에서 워크스페이스 버튼의 더 강한 선택자가 left3px를 남겨 선택 배경(left0)과 어긋나는 검사가 실패했다. 터치 규칙을 두 모드 버튼 모두에 적용해 최종 좌표0/0·너비43/43px를 확인했다. 축소 시 불필요한 작업 위치 제목 여백도 높이로 접도록 보완했다. 두 프레임 뒤에 전환의 중간 상태가 남아 있다고 가정한 검사도1회 실패해, 최종 상태 검사는 실제 입력/시간으로 유지하고 중간 스타일 검사는 브라우저 애니메이션 시간을 고정하도록 나눴다. 후속 두 검사 모두 통과했다.
- **경계:** 추가 제품 UI·실제 API/권한/자료·Windows·Figma 일치·사내 사용성 검증은 하지 않았다. 문서 검사와 diff 검사는 별도로 수행하며 시안 검수를 제품 Native/CI 성공으로 바꾸지 않는다. push·PR·CI는 사용자 지시에 따라 마지막으로 유지한다.

<a id="navigation-motion-mock1-20261102"></a>

## 2026-11-02 · 탐색·패널 동작 시안 1

아래는1판 당시 기록이며 원본과 HTML은 로컬 커밋 `f0fe99e`에 보존돼 있다. 아래 작업 파일 링크는 현재2판을 가리킨다.

- **환경·범위:** main745e5ef에서 분기한 `fix/compact-scope-dropdown-20261102`의 기존 접힌 범위 목록 수정3d47e6b 위에서 [시안1 원본](../docs/mockups/ees-work/design-mock-src/09-navigation-motion.html)과 [단일 HTML](../docs/mockups/ees-work/design-mock-09-navigation-motion.html)을 만들었다. 제품 CSS·v4 아이콘·고정 공식 글꼴의 해시를 확인하는 기존 `build_design_mock.py`를 사용했다. 원본 SHA256 `165bac7d98be4c534f039275dad9ddf6d7dc4095ae679a422dba205b3a98f986`, HTML `cb7f57d73e259e20cc3f5a014f4cf28cc3ef74fda6e9b1d0600a30157cada879`(407,128bytes)다. 새로운 제품 UI/서버/자료 변경이나 Figma 판 갱신은 없다.
- **실행 준비:** 기존 Playwright Chrome ZIP 실패와 구분해 시안 검수에 한정해 npm `@sparticuz/chromium@133.0.0`의 Chromium133.0.6943.0을 사용했다. 첫 자동 압축 해제는 `/tmp/libEGL.so` chown EINVAL로 실패했다. 같은 압축 자료를 작업 경로에 소유권 복원 없이 풀어 기동을 확인했다. 이 브라우저 성공을 고정 제품 빌드/Native 검증 완료로 바꾸지 않는다.
- **브라우저 확인:** 1920·1366·1024·480·320px 각각에서 접힌240px 목록의 글자/보조정보/선택 체크와 실제 검색·선택·권한 없음·Esc 복귀, 운영/셋업/장애대응의 높이0↔내용 높이, 도구 진입 때 범위 칸 높이0/복귀 때 선택·접힘·초안 보존을 확인했다. 오른쪽 패널 두 버튼의 같은 이미지, 닫기 후 초점 복귀, 35ms 간격 빠른 열기/닫기/열기와 마지막 상태, 가로 넘침 없음·JS 예외0을 확인했다. 1920/1366은 붙은 패널, 1024/480/320은 겹친 패널이다.
- **실제 중간 상태·시각 검수:** 1366에서 패널 폭이0→480px 사이의160.703125px를 지나감을 측정했고 동작 줄이기에서 전환 시간이0s임을 확인했다. 넓은/좁은 화면의 목록·업무 패널·도구 화면 캡처와1024 초기 화면을 열어 글자·간격·선택 표시를 확인했다. 작은 화면에서 항목을 선택하면 왼쪽을 접어 오른쪽을 가리지 않도록 보완했다. 입력 검사용 임의 문구는 목업의 사용 글자만 담은 부분 글꼴에 없는 글자가 네모로 보였으므로 최종 캡처에는 원본에 포함된 문구를 사용했다. 실제 제품은 부분 글꼴을 쓰지 않는다.
- **첫 검사와 보완:** 닫기 효과를 추가한 뒤 기존 즉시 hidden 검사가 Esc 직후 실패했다. 닫기 중 클릭 차단(inert)은 즉시, 숨김은150ms 뒤라는 계약에 맞춰 두 시점을 나누어 최종5폭을 다시 확인했다. 메뉴를 빠르게 다시 열면 이전 닫기 완료가 새 메뉴를 숨기지 않도록 세대값으로 보호한다. 별도 인라인 sandbox(allow-scripts), 터치 환경에서도 글꼴·공장 선택/닫기·모드 전환·전역 도구 진입을 확인했고 JS 예외0이었다.
- **남은 경계:** 시안1은 합성 데이터만 사용하고 저장/실행/실제 API 호출을 하지 않는다. 실제 제품의 전환 성능·권한·기존 시스템별 도구 유지/작성 경로·사용자 데이터·Native 회귀·Windows·사내 사용성은 미검증이다. Figma는 이번 작업에서 읽거나 수정하지 않았다. 사용자의 순서대로 push·PR·CI는 마지막으로 미루며 제품 구현 대상 판은 아직 지정되지 않았다.

<a id="compact-scope-dropdown-20261102"></a>

## 2026-11-02 · 접힌 사이드바 범위 목록의 글자·체크 숨김

- **보고·코드 근거:** 사용자는 접힌 사이드바의 목록에 아이콘만 보여 정보를 얻을 수 없다고 했다. main745e5ef의 Sidebar compact CSS가 `.ew-scope span/small/.ew-icon:last-child` 전체와 모든 하위 button을 선택해 목록의 이름·역할·선택 체크까지 숨기고 패딩을 바꾼다. 기존 absolute 목록은40px 범위 칸 너비를 따라가며 사이드바 overflow에도 제한된다. 사용자 관측과 소스에서 확인한 원인이고 로컬 실제 제품 재현 완료로 기록하지 않는다.
- **이전 검수 누락:** A2/C41의 기존 실제 scope 시험은 펼친 사이드바만 확인했다. textContent 존재만으로는 숨긴 글자와 체크를 판별하지 못한다. 새 `test_compact_scope_options_remain_readable_clickable_and_preserve_draft`는1920/480×업무/워크스페이스×공장/시스템에서 실제 크기·computed style·좌표 hit-test와 선택/검색/Esc·초안을 확인한다. 기존 펼친 상태·권한·수명/C3 시험은 유지한다.
- **수정:** compact 숨김/정렬을 `[data-scope-trigger]`의 직접 자식으로 제한한다. 접힌 목록만240px fixed로 버튼 아래에 두고 뷰포트 여백8px/최대360px 높이를 보장한다. 목록 스크롤은 유지하고 바깥 스크롤/resize 때 닫으며 action 해제 때 listener를 제거한다. 툴팁과 접근 가능한 이름에 현재 선택값을 연결한다. 빌드 patch/두 변경 원본의 SHA256을 갱신한다.
- **로컬 검증:** 고정 upstream2a960a59에 원래 patch 적용이 통과했고 변경한 EesScopeSelect/Sidebar를 고정 lock의 Svelte5.56.0으로 컴파일해 오류·경고0이었다. 공통 움직임·Svelte 수명/접힌 목록 위치·이벤트 정리 Node38/38, frontend Python32중19통과/전체 source build 자료 필요13생략, 새 Native Python 구문 확인이 통과했다. 실제 제품 브라우저·Windows·최종 CI는 다음 결과로 구분한다.
- **실행 환경 한계:** 로컬 Chrome이 없으며 Playwright 제공 Chrome Headless Shell151.0.7922.34 다운로드의 ZIP 디코딩이 실패했다. 설치 도구 내부 재시도도 같은 오류로 종료했다. 제품 오류로 판정하지 않고 임의 다른 빌드로 재현 완료를 주장하지 않는다. 새 Native 회귀와 실제 화면 검수는 저장소 CI의 고정 소스 빌드/브라우저로 진행한다.
- **원격 반영 차단:** 로컬 커밋 c8934f5의 branch push가 자동 승인 검토에서 원격 게시 명시 승인 부족으로 거부됐다. 같은 push를 우회하지 않았고 `git ls-remote --heads`로 해당 원격 브랜치가 없음을 확인했다. 뒤의 위치/이벤트 회귀2개·기록 보완도 로컬에 보존한다. 사용자 승인 뒤 같은 브랜치 push·Draft PR·새 Native/전체 CI로 이어간다.
- **남은 확인:** 최종 head의 실제 Native 결과/캡처·전체 CI. 사내 적용·실사용 확인은 미실행이며 기존 사용자 보고와 구분한다.
