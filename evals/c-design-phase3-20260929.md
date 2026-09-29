# C안 3차 검수·Native 보내기·시각 일치 보완 기록

[평가 기록 찾아보기](scenarios.md#evidence-index) · [현재 작업 상태](../docs/STATUS.md)

<a id="c-visual-match-20260929"></a>

## C안 전체 화면 시각 일치 보완 · 2026-09-29

**인수·범위:** 최신 main `8027aaf2e654778f052a966e5a49feed0fc54f69`와 관련 열린 PR·로컬 상태를 확인했다. #66은 병합 완료, 같은 시각 보완 PR은 없고 #53만 별도 Draft였다. 깨끗한 main에서 `fix/ees-c-visual-match-20260929`를 만들고 [TASK의 사전 차이/수정/검증 대응표](../docs/mockups/ees-work/TASK.md#c-visual-match-20260929)를 작성한 뒤 구현했다. 이번 범위는 구현·검증·문서·커밋/push·Draft PR까지이며 병합/재배포/사내 서버 변경은 하지 않는다.

**이전 판정 정정과 사내 보고:** #66의 Native composer 3회와 유효한 기능 PASS는 당시 근거로 보존한다. 사용자가 `Status` commit `e5b799ed22d1`/customized/running=true, 뒤이어 #66 적용 안내에 `upgrade=ok, running=true, apply_demo=ok`를 보고했다. 보내기/대화보존·C안·저장/이력 정상이라는 보고는 실제 화면 검사가 아니라 스크립트 완료를 뜻했다고 직접 정정했다. 주소 오입력 해소 후 실제 화면에서 왼쪽·중앙·전체 외형이 Figma와 다름을 확인했다. 이에 과거 “시각적 차단 없음”·Native 외형 고정·overflow footer 면제를 이번 수락에 사용하지 않는다. 사내 프로그램 적용 보고와 시각/기능 수락, 정확한 설치 바이트는 별도다.

**유일한 시각 원본:** Figma `XK2wTos6sEuxSHhIj7cqg6`, 페이지582:131·비교603:963 오른쪽 C, J582:132/584:169/405/634/869/1098와 P/T586:555/958/1397의 현재 context·변수·1920×1080 렌더를 읽었다. 상세 출력 overlay587:4886도 같은 C 원본에서 확인했다. 원본은 수정하지 않았다. `dist/c-visual/figma`에 원본9 PNG·SVG13개·해시/출처·geometry/style·비교 contract를 보존한다. asset URL 1회는 HTTP 결과가 HTML `Site Unavailable`이므로 유효 자산으로 취급하지 않았으며 반복 없이 지원되는 읽기 전용 Figma export로 확보했다. page 변수 조회는 선택 없음 오류 뒤 구체 frame 조회로 해결했다.

**비교 조건:** 기존 단일 Python3.11.16/Chrome153/공식0.11.3 wheel을 재사용한다. 실제 Native CLI 앱·가입/인증/대화·게시 API·EES 서비스·새 임시 SQLite를 사용하며 외부 모델 응답만 loopback 합성이다. 메시지는 실제 composer 입력/보내기로 생성한다. 제품1920×1080 원본은 보존하고, Figma의 검토 띠32px만 제외한 앱1920×1048과 별도의 실제 viewport1920×1048 렌더를 1:1 정렬한다. 확대/축소·넓은 마스크·시험 전용 CSS가 없다. 전체 나란히/앱 나란히/50%겹침·geometry/style을 함께 판정하며 자동 유사도 PASS를 만들지 않는다. 상세 overlay에는 검토 띠가 없어 y-32를 적용하지 않는다.

**초기 차이·실패 보존:** 원본 main 공식 앱에서 왼쪽 폭312→245, 중앙 y0→92.5/폭768→827, composer16/28→13/22.1, J 완료 행동 y496→927 등 불일치를 측정했다. 이는 기능 PASS와 무관한 시각 차이다. fixture 첫 두 번은 공개 작성 API가 새 mock tool을 거부했고 기존 승인 seed 참조로 수정했다. 세 번째는 접힌 실제 Native sidebar에서 숨긴 selector를 클릭한 시험 준비 오류다. 실제 sidebar 열기 조작으로 재검했으며 서버 guard/DB를 우회하지 않았다. 첫 baseline의 `점검 가능` 상태는 C의 `입력 필요`와 달라 별도 `baseline-exact`에서 지원 API로 저장 입력을 비우고 실제 미저장 입력을 작성했다. 초기 결과는 삭제하지 않는다.

**자료·판정 계약:** 합성 P120/T48과 완료72/25는 실제 지원 작성/실행 API로 구성한 임시 업무이며 실제 회사 작업120건을 실행한 것이 아니다. 기존 mock 체크의 이름/purpose는 공개 authoring schema에서 변경할 수 없어 C의 두 예시 체크명과 다른 점을 표시한다. 저장하지 않은 elapsed_ms/reason_code 같은 원본 상세 필드를 만들어 넣지 않는다. C09의 숫자/단위30 Bold는 C07/C08의 숫자30 Bold+단위16 Regular와 서로 달라 원본 충돌로 남긴다. 이러한 차이를 승인 전 의도된 차이로 제외하거나 시각 완료로 표시하지 않는다.

**버전·보존:** UI 보완 때문에 Native 실행 승인 environment가 무효화되지 않도록 ees.12/Pack0.2.14를 유지한다. 기존 `immutable/` 모듈 그래프 전체를 패치 후 정렬된 경로/바이트 해시의 `immutable-c<digest>/`로 옮기고 index의 검토된49개 URL을 갱신한다. 상대 import는 같은 깊이/트리 안에서 보존하며 순환 import의 hash 재귀를 만들지 않는다. chat-theme와 기존 Work 자산은 실제 내용 query hash를 사용한다. 추가 SVG는 builder 입력/RECORD에 포함하되 구형 Restore의 필수 THEME_FILES 목록은 확장하지 않는다. 버전명이 같아도 원본/manifest/전체 payload 바이트로 구분한다.

### 구현·보존과 중간 실패

- 실제 Native sidebar의 설정 없는 기본 폭312/열림과 브랜드·새 대화/검색, 제목/경로, 메시지·실제 composer를 변경했다. 저장된 폭360/닫힘은 실제 새로고침 뒤 유지한다. 실제 모델/음성/첨부/도구 선택과 응답 행동, 기록/Workspace/계정 접근은 남긴다. C 원본에 없는 추가 기능 표시는 아래 미수락 차이이며 숨겨서 통과시키지 않는다.
- J는 짧은 입력 바로 다음과 완료 결과 다음에 행동 영역 하나를 둔다. 완료 후 입력 변경을 펼치면 같은 DOM을 입력 다음으로 이동하고 닫으면 원위치로 복귀한다. 긴 입력은 같은 행동에 Tab으로 접근하며 별도 하단 버튼을 만들지 않는다. 완료 뒤 재실행은 기존 서버가 허용하는 현재 진행 건에만 제공한다.
- P/T는 실제 수치·판정·절차 순서를 유지하면서 숫자/단위·진척·6행 페이지·짧은 검색과 필터·조건 두 줄을 정돈했다. `failed/blocked` 저장 상태라도 이미 완료/실패 시도 근거가 있는 상위 범위는 진행 중으로 표시하되 원본 상태/실패 수·하위 J 판정은 바꾸지 않는다. 미연결/근거 없음은 대기로 유지한다. 상세 창880×920·기존 탭·저장 자료·닫기/초점·조회 실패 숨김을 보존했다.
- 제품 C1의 빈 입력 음성 분기에서 Native Svelte 생성/정리 계약을 잘못 연결해 보내기 버튼2개가 실제 렌더됐다. 원래 DocumentFragment lifecycle에 연결해 단일 보내기와 음성 메뉴로 수정하고 실제 입력→전송→빈 입력 및 장문 전송에서 재검했다. 초기 PNG/DOM/로그와 C1 wheel을 보존한다.
- 원본 SVG가 이미 있는데 그 내부 path만 재작성한 중간 assistant 자산은 원본 전체18px SVG 바이트를 래퍼에 임베드하는 방식으로 교체했다. 추가 자산은 실제 wheel에 포함하고 기본 avatar fallback만 변경했다. 사용자가 지정한 `profile_image_url`은 데이터 자산이므로 덮지 않는다.
- C2/C3의 첨부 메뉴 시험은 열린 portal의 애니메이션/재생성·aria-expanded 없는 원래 메뉴에서 불안정한 selector를 사용해 클릭 전 중단됐다. 관측된 실제 label을 매 frame 다시 찾고 hit가 안정된 경우에만 물리 클릭하도록 준비 코드를 보완했다. 제한을 늘리거나 JS 클릭/API 업로드로 바꾸지 않는다. C4의 저장 폭 재조회는 실제 reload 완료 이벤트 전 평가한 준비 오류였다.
- C5 완료 후 입력 수정은 저장 HTTP200까지 진행됐지만 시험의 Ctrl+A에 Windows virtualKey65가 없어 기존 텍스트 뒤에 입력이 붙었다. 실제 키 입력 정의와 저장 전 값 검사를 수정했고 C6에서 입력 변경/닫기/재열기/저장·이력 보존을 통과했다. 제품 결함으로 기록하지 않는다.
- 기존 fixture10건의 첫 실행은 새 기본 열린 sidebar를 다시 열려고 무조건 클릭해 모두 준비 단계에서 실패했다. 실제 열린 폭을 확인한 뒤 재검해9 PASS, 나머지 범위 예외1건은 옛 완료 조건 문구·높이1080에서 불필요한 scroll 기대를 고쳐1366×768에서 검사했다. 줄바꿈된 실제 수치 `3 / 104`, `2개 작업`을 공백 정규화해 정량 비교했고 C5에서 PASS했다. 원본/패키지가 바뀐 도중 재시도는 byte guard가 중단했으며 그 결과를 통과로 세지 않는다.
- C6 긴 입력 검사의 최초 실행은 더 이상 표시하지 않는 옛 current-title selector의 computed style 조회에서 중단됐다. 현재 표시되는 결과 heading으로 같은 대비 검사를 옮겼다. 같은 wheel의3개 해상도·긴 업무/입력·단일 행동·Tab/Enter·독립 스크롤·상세/초점·좁은 폭/다크 재검1건이4.742초에 PASS했다. C6 source snapshot의 제품 파일은 유지하고 시험 파일만 갱신했다.
- 최종 독립 검토에서 상위 P/T의 `attention_count`만으로 진행 중을 표시하면 아직 실행하지 않은 입력/연결 대기까지 진행 중으로 보이는 조건을 찾았다. 실제 완료 수 또는 실패 시도 수가 있을 때만 상위 진행 표시를 허용하고 조치 수만 있는 blocked는 보존하도록 좁혔다. `case.status`는 P의 집계 상태이지 Native worker의 활성 상태가 아니므로 서로 바꾸어 해석하지 않는다. leaf 판정·실제 수치·Native 추가 상태·저장 데이터 불변을 해당 renderer 회귀에 연결한다.
- C7 실제 절차 편집 클릭에서 적용 시스템 EMS를 작성 관리 주체로 넘겨403이 발생했다. 같은 임시 앱의 게시 P는 UNASSIGNED 소유였고 기존 backend는 저장 owner와 nonempty system_id가 다르면 정상 차단했다. 진입을 지원되는 `process_id` 조회로 바꾸어 서버가 실제 owner를 찾고 기존 권한을 확인하게 했다. cap/route/auth/generation 보호·초안 cache·게시 경로는 유지한다. 시험도 실제 존재하지 않는 editor-form selector 대신 기존 node-form을 확인하도록 보완했으며 owner403 제품 결함과 selector 준비 오류를 구분한다. UI36/controller22 및 기존 owner 해석/비관리자 거부/DB 불변 service1을 확인하고 같은 버튼의 공식 앱 재검을 연결한다. 독립 service 명령의 PYTHONPATH 누락 오류는 별도 로그로 보존했다.
- C8 최소 진입은 릴리스 노트 모달의 사용자 설정 누락, 처음 권한 확인 뒤 이미 열린 패널의 편집 버튼 갱신 누락, 뒤의 Workspace 대기식 따옴표 오류를 각각 구분했다. 같은 실제 T 선택 뒤 편집→setup-p/owner UNASSIGNED→계정 메뉴/Workspace 도달·작성 POST0은 `candidate8-authoring-confirmed`에서 PASS했다. 첫 권한 조회 뒤 버튼이 숨은 채 남는 제품 조건은 별도 보완했다. canAuthor 전후 변화에만 기존 state/request/route/auth/generation/available 조건을 재확인하고 초안·초점 보존 renderPanel로 갱신한다. 새 회귀의 수정 전 실패와 수정 후 controller23 PASS를 보존하고 최종 공식 앱에서 T 재선택 없이 첫 패널부터 확인한다.
- C7 시작과 재개 명령에서 Chrome DevTools용 실제 실행 파일을 찾지 못한 준비 실패는 원래 결과 파일에 남겼다. 기존 정상 Chrome의 절대경로를 확인해 사용하며 제품·패키지 결함으로 해석하거나 실패를 PASS에 합산하지 않는다.
- 최종 숫자/단위 baseline6px 보완 도중 `3 / 6`의 읽기 텍스트 공백이 사라져 renderer46 중2 FAIL이 발생했다. formatter의 공백을 복구했다. 뒤의46 재검은 상위 복귀 링크의 짧아진 표시명에 대한 옛 기대1건이 실패해 visible 이름과 기존 aria 전체 의미를 함께 검사하도록 갱신했고 이 실패 전체 로그는 별도로 보존했다. 담당자가 같은 로그 경로로 재실행해 최초 전체 로그가 덮인 증거 보존 실패가 있으며 원본 전체가 남아 있다고 주장하지 않는다. root가 이미 읽은 실패 일부만 `panel-unit-c7-spacing-failure-observed.txt`에 관측 사본으로 보존했고 이후 재검은 고유 파일명으로 기록한다. 다른 후보의 실패 PNG/JSON/로그는 유지한다.
- 문서 점검 첫 실행은 ignored dist 안의 부분 source snapshot까지 탐색해 그 안의 README 상대 링크30건을 실패로 보고했다. 원본 검사를 완화하지 않고 Git 추적 파일+새 파일 전체를 새 깨끗한 경로로 복사해 검사했다. 중간 검사31문서/1314링크·오류0/경고0이며 최종 원본에서 다시 확인한다.

### 기능 검증과 시각 판정의 경계

| 근거 | 이번 유효 결과·재사용 범위 |
|---|---|
| 실제 Native 보내기 C5 | 기존 대화2회/새 대화1회, 매번 실제 입력·보내기 클릭. 요청/작업/외부 loopback 모델 각각1회, 기존 메시지2→4·새 대화2, 응답·저장·새로고침·공장/진행 건 분리·과거 필드 보존 PASS. 뒤의 CSS/SVG 보완은 Native 전송/저장 patch를 바꾸지 않아 이 근거 재사용 |
| 영향 fixture10건 | C3의9 PASS + C5의범위 예외1 PASS. 완료 복귀/목록/필터/초점3, 조회 실패 자료 숨김2, 실제 실행 입력 대기/명시 재개1, 상세 중 권한 회수1, 부분/실패 완료 금지1, 초안/사람 확인 분리1, 미연결/제외/빈 입력1. 최종 C7의 표/복귀 표시 영향3건은 다시 PASS했고 C3의 같은3건을 중복 합산하지 않음 |
| 긴 내용·접근 | 기존 suite의3개 해상도·긴 이름/설명/입력·single action·Tab/Enter·상세/초점·좁은 폭/다크1 PASS. C6/C7(4/4 PASS, 15.887초)에 이어 C9에서4/4 PASS(14.651초), 최종 P 배치/CSS 변경 뒤 C10에서도 같은4/4 PASS(16.381초). 공식 앱 장문 메시지/실제 입력/설정은 별도 결과 |
| 원본 unit·Native patch | panel46 C7(8.492초), P 보완 후 C10(9.219초)/controller23, authoring UI36/service1, builder25, pinned 공식 wheel2, C7 일반 Native theme2(1.582초), C10 disabled-send 의미/실색/클릭 차단을 포함한 theme3(1.894초) PASS. renderer는 기존 primary Python3.12.14/Node, 공식 앱·실제 패키지 브라우저는 기존 .venv Python3.11.16/Chrome153을 사용했다. 최초 builder25의 model router fixture가 새 기본 avatar fallback을 포함하지 않아 실패한 뒤 실제 상위 원본 fixture를 보완함. 최종 asset 추가 영향은 최종 package audit으로 확인 |
| 프로그램 Restore C5 | 실제 이전 #66 ees.12→C5→Restore1 PASS. 이전 프로그램 전체 파일 hash와 합성 DB/키·Python 바이트 동일. 일반 customization54 PASS/선택 실행6 SKIP와 물리 Restore1을 구분. 이후 CSS/SVG만 바뀌며 래퍼·과거 THEME_FILES·저장 계약 불변을 최종 감사로 연결해 재사용 |

공식 앱 검사는 실제 Native 계정·대화·파일 저장과 EES 공개 API·임시 DB를 사용한다. 외부 OpenAI 응답/embedding과 HTTP만 loopback 합성이다. UI 행동은 실제 좌표 클릭/키보드·파일 선택으로 확인하며 API로 메시지를 주입하지 않는다. fixture 브라우저는 실제 제품 패키지/EES 서비스이지만 Native shell·채팅 인증은 합성이므로 공식 앱과 구분한다. 광역 backend/권한/worker 검사는 해당 원본이 변하지 않은 #65/#66의 근거를 유지하며 새로 전부 실행했다고 쓰지 않는다.

### 중단 뒤 재개 · 2026-09-29

최신 main은 `8027aaf2e654778f052a966e5a49feed0fc54f69`, 관련 열린 PR은 별도 Draft #53뿐이었다. 같은 로컬 브랜치의 미커밋 구현과 C1~C7 원본/패키지·실패/통과 증거를 인수했다. #66이나 다른 작업을 재개하지 않았다. `AGENTS.md`는 main과 바이트가 같다. C7 제품 원본88개와 snapshot, wheel의5,924개 제품 파일·member 목록·RECORD5,925행·CRC가 모두 일치했다.

- 재개 첫 공식 앱 시험은 로컬 Chrome 경로 오지정으로 브라우저 생성 전에 실패했다. 기존 설치된 headless-shell의 실제 경로를 확인해 다음 별도 경로에서 재실행했다. 앞선 실패 로그는 `candidate7-layout-resume.log`/`candidate7/`에 보존한다.
- C7 실제 Native 첨부 시험은 chooser→upload/parser/storage→원래 file ID의 실제 composer 보내기1회→응답/첨부 표시→저장→새로고침 복원까지 PASS했다. 외부 모델/embedding만 loopback 합성이다. `candidate7-attachment/interaction-result.json`의 마지막 검사는 이전 C6 파일 저장 근거에 없던 범위를 닫는다.
- C7 실제 Tab은1536×960/1366×768/1048×768에서 한 행동 영역에 도달했고 가로 넘침과 composer 내부 넘침이 없었다. 뒤의 절차 편집 gate에서 실제403을 확인했으므로 전체 실행은 PASS로 세지 않는다(`candidate7-final/`).
- **제품 결함:** 현재 조회 시스템 EMS를 실제 절차 소유 시스템으로 넘겨 UNASSIGNED 소유 절차의 편집 진입이403이었다. launcher/designer가 process ID만 기존 authoring 조회에 전달하고 서버 `_authorize_process`가 실제 소유/권한을 해결하게 수정했다. 서버·API·권한 판정을 변경하지 않았다. 잘못된 시험 form selector도 실제 `#ees-work-node-form`으로 수정하고 반환 owner를 검사한다. authoring UI36/controller22/실제 SQLite SA20 1건 PASS(`authoring-owner-*-c8.log`).
- 직접 Git transport는 자격증명 비대화형 입력 불가로 읽기에 실패했다. 연결된 GitHub 플러그인으로만 원격 게시/재확인을 진행한다. 자격증명 추출·대체 인증·보호 우회는 하지 않는다.

**최종 시각 판정·패키지·Git:** 최종 동일 조건 재검 결과와 미수락 차이, 원본/패키지 hash, 문서/diff·Draft head는 아래에 기록한다. 기능 PASS·스크린샷 생성과 전체 시각 수락은 별개다.

**시각 중간 검증 패키지 C7:** `open_webui-0.11.3+ees.12-py3-none-any.whl`, 152,030,655 bytes, SHA256 `5cddcfd22ec0cf676faa3527c600a43fb981c5b6205a54d934ecbc64d4e424ee`. 해당 source snapshot88파일, 변환된 전체 payload5,924파일·RECORD5,925행·추가31개·manifest·공식 원본·namespace·49 entry URL·4개 캐시 URL·CRC가 일치했다. C5 대비 프로그램 래퍼/Agent Pack 보호 원본과 과거 필수 inventory 변경0이므로 실제 이전 ees.12 Restore PASS를 재사용한다. 새 회사 설치용 묶음을 만든 것이 아니며 이 wheel/증거 ZIP을 사내 재배포 승인으로 해석하지 않는다.

### PR #67 최초 게시 기록 보존

게시 직전 원격 재확인에서 같은 브랜치의 Draft #67 head `e55f9a4ce8c8719947142bc1600b16cb504b5e75`를 확인했다. 원격 AGENTS/STATUS·전체 tree와22개 차이의 blob hash를 읽어 대조했다. 아래는 그 head의 **당시** 검사/실패 기록이며 C9~C11의 추가 P·상세·초기 작성 경합 검수를 대신하지 않는다. 해당 기록은 이 후속 실행에서 새로 수행한 것으로 집계하지 않는다. 원격의 SVG EOF 보정을 유지하고 기능·원본 변경은 이 후속 검증과 통합하여 같은 Draft를 갱신한다.

#### 최초 게시 당시 고정 원본과 판정

**제품 원본:** 1920×1080 원본과 별도1920×1048 렌더17개 지점을 실제 앱에서 재검했다(`final-app/visual-result.json`, `fullapp-result.json`, `final-app.log`). 기준3화면의 전체/앱 나란히·50%겹침·항목별 원본/제품 geometry/style을 함께 육안 대조했다. 기준 띠32px만 제외하며 browser chrome·이미지 확대축소·마스크·시험 CSS는 없다. 실제 프로그램은 `0.11.3+ees.12`, wheel SHA256 `6b65b1812c210e28abad8a4fe90261d380729922fb9ec0141db2497055526161`이다. 88개 고정 제품 입력이 최종 checkout과 같고5,924개 제품 member·RECORD5,925행·CRC·manifest·cache namespace 모두 통과했다. builder는 원본/패키지 바이트를 검증하며 아직 병합/배포용 ZIP을 만들지 않았다.

**재개 중 시험 보존:** 최종 후보의 첨부 보내기/복원 자체는 PASS했으나 그 뒤 layout gate를 같은 실행으로 묶자 새로고침 뒤 닫힌 패널에서 scope 버튼을 기대해 준비 단계가 중단됐다. 이 실행 전체는 FAIL로 보존하고 첨부의 구체적 통과 범위만 재사용한다. 제품값을 바꾸지 않고 단독 layout gate를 실제 패널 UI에서 재실행해 통과했다. 중간 candidate8 source 경로 충돌과 builder 출력의 기존 파일 보호 중단도 통과로 합산하지 않는다. 시험 파일이 작업 중 달라진 것을 blob 전송 길이 검사로 발견해 참조 게시 전에 중단했고, 기존 폴더는 보존한 채 추적/새 파일181개를 고정한 별도 checkout으로 검수를 마쳤다. 앞선 C1~C7·기타 중간 실패는 삭제하지 않았다.

| 영역/조건 | 최종 확인 | 판정·남은 차이 |
|---|---|---|
| 전체3영역 |1920 기준 x0/312/1080, 폭312/768/840·앱높이1048, 흰 표면·공통 상단/메시지/입력창 위치 일치 |기하 배치 확인. 사용자 저장 폭/닫힘은 C6의 실제 reload 근거로 보존하며 강제 덮기 없음 |
| 브랜드·탐색 |심볼36·원본24SVG, 새 대화/검색 가로 배치·선택 표면·단계54/간격12·J44px·연청색 선택과 구분선 |글자 지정30/22/14px·굵기·줄높이 일치. 자연 텍스트 폭은 제목+3px, 브랜드+2px, 배지 위치+3px/폭+1px 잔존. 확대축소로 숨기지 않음 |
| Native 대화 |실제 제목18/28·경로13/22, 본문·assistant28px 묶음, 실제 composer688×130·send76×44 |실제 응답 행동/모델·도구·음성/계정·기록/Workspace·절차 진입이 C 예시보다 추가 표시됨. 제거/접근불가 숨김 없이 보존. 전체 시각 수락 대상 |
| J 입력·행동 |입력과 행동의 위치/크기 일치, 짧은 입력에서 버튼을 하단으로 보내지 않음; 완료 편집도 같은 action DOM 하나 이동 |실제 schema가 text이므로 C의 선택 상자와 다르고 모의 도구 이름·설명/사이트 line도 원본 계약 유지. 상태/내용량 완전 동일 비교는 이 부분 미충족 |
| J 완료·기준/기록 |결과→단일 행동→기록 순서, 실제 값/판정/기록·선행 정보 보존 |실제 체크명이 두 줄로 되어 결과/행동 y가 기준보다18px 아래. input 저장/재실행/복귀 영역 중복 없음. 임의 체크명/elapsed_ms/reason_code 주입하지 않음 |
| P/T |실제120/72·48/25/26, 숫자30 Bold/단위16 Regular, 진척막대·toolbar 검색208×44/필터551×44·목록775×379·조건/페이지 |필터7px/목록4px 차이를 실제 CSS baseline/정렬 수정으로 제거. 수행방식88px+간격12·조건54px 원본 정렬 확인. 실제 상태·추가 토글·현재 T 선택 표현은 계약에 따라 목업 일부와 다름 |
| 상세 |C6 공식 앱880×920·Tab15회·Escape·초점복귀, 현재 final과 상세 관련 제품 코드 불변 |실제 기록 필드/설명이 예시와 달라 동일 내용량 상세 전체 시각 비교는 미완료. 실행 이력과 읽기 전용 자료·조회 실패 숨김은 유효 기능 근거 유지 |
| 작은/긴/좁은/다크 |1536×960/1366×768/1048×768 범위 버튼 실제 Tab·단일 영역·document/composer 가로 넘침 없음. C6 긴 입력/340px/다크·첨부/모델 메뉴 근거 재사용 |직접 대응 목업 없는 규칙 확장. 상위 CSS의 glyph/필터/표 보완은 실제 작은 화면에서 재검 |

**게시 직전 SVG 바이트 보완:** 새 파일까지 stage한 `git diff --cached --check`에서7 SVG의 EOF 빈 줄이 검출됐다. 이전 일반 diff는 untracked 파일을 검사하지 않아 이를 놓쳤다. Figma 읽기 전용 SVG export를 다시 조회하니 원본은LF1개이며 로컬 저장 과정에서LF1개가 덧붙은 사실을 확인했다. 원본 export 바이트로 복원하고28px avatar 래퍼에도 동일 원본을 임베드했다. path/색/크기·XML 문서는 동일하며Figma 파일은 수정하지 않았다. 최종 wheel은 `ed4d786aecad4a03c382f083e3f4d1312547143ea6440625ff1b1dfe15428f2f`이다. 화면 검사 wheel `6b65b181…`와의 차이는7 SVG·동일 SVG를 임베드한 avatar·RECORD뿐이며8 SVG의 XML 문서 동일/그 외 제품 바이트 동일을 검사해 최종 PNG와 기능 결과를 재사용한다. 기존 export 보관본/오류 해시는 삭제하지 않고 재조회·보정 JSON과 연결한다. staged diff 검사도 이제 통과했다.

**수락하지 않은 차이와 대안:** 위 차이는 `의도된 차이`로 제외하거나 전체 시각 PASS로 계산하지 않는다. (1) 실제 text schema/등록 도구명/기록 필드를 유지하는 현재 화면과 C 예시 필드 차이는 사용자 시각 확인이 필요하다. 선택 입력이나 도구명 변경은 별도 업무 정의 승인 없이는 이번 시각 작업에서 강제하지 않는다. (2) Native 추가 기능은 현재 실제 컨트롤로 접근 가능하다. 더 줄이는 배치는 접근을 보존한 기존 메뉴 재배치안을 별도 확인해야 하며 이번에 새 디자인으로 정하지 않았다. (3) C09의 전체30 Bold와 우선 C07/08의 숫자30+단위16은 원본끼리 충돌하며 이번에는 공통 강약을 적용한 상태로 미수락 차이에 남긴다. (4) 지정 폰트/굵기/크기/줄높이에도 남은2~3px 텍스트 폭 차이의 원인은 확정하지 않았다. 임의 letter-spacing/transform은 사용하지 않는다.

**미완료·미실행:** 동기 legacy 모의 점검의 실제 진행 중/DB 실패를 Figma와 동일 업무·내용으로 캡처하지 못했다. 실제 AP 첫 실패·추가 Native 대기/예외는 규칙 확장/기존 회귀이며9개 기준 상태 전체 시각 PASS는 아니다. Windows·사내 LLM/API·사내 적용·사용자 시각 수락은 미실행이다. 따라서 이번 결과는 **구현·영향 검증·Draft 검토 준비, 전체 시각 수락 대기**이다. 기존 #66 기능 PASS를 면제로 사용하지 않는다.

**최종 기능 결과:** 고정 wheel의 Native 일반 보내기1회·첨부 보내기1회와 원본 파일ID/응답/새로고침 보존,3개 작은 viewport, 실제 절차 편집(EMS 조회→UNASSIGNED 소유)·계정/Workspace 진입/authoring 쓰기0을 확인했다. 최종 panel46 PASS, 소유 조회 보완 UI36/controller22/SQLite1 PASS. C5 기존/새 대화3회, C3/C5 영향 fixture10건, C6 긴/좁은/다크1건, 이전 프로그램 Restore1건은 제품 변경 영향과 감사 결과에 따라 재사용한다. 한 항목의 재실행을 추가 고유 PASS로 합산하지 않는다. 원격 CI는09-30까지 `[skip ci]` 방침으로 미실행이며 병합·재배포·사내 변경은 하지 않았다.

**제공 자료:** `EES_Work_C_Visual_Evidence_20260929.zip`에 최종 제품 원본 PNG,3화면 전체/앱 비교·겹침,9개 Figma 원본·변수/metrics/자산 출처, 항목별 geometry/style·위 판정, 핵심 로그·실패 근거·원본/패키지 manifest·해시를 함께 제공한다. 사내 자료는 포함하지 않으며 검증용 합성 자료뿐이다. 문서31개/링크1320개 오류0·검토후보0, 변경 Python AST/Node 구문 및 staged/working diff 검사를 통과했다. Git 게시 결과는 같은 원본을 가리키는 Draft PR에서 확인한다.

**검증 패키지 C7:** `open_webui-0.11.3+ees.12-py3-none-any.whl`, 152,030,655 bytes, SHA256 `5cddcfd22ec0cf676faa3527c600a43fb981c5b6205a54d934ecbc64d4e424ee`. 최종 source snapshot88파일, 변환된 전체 payload5,924파일·RECORD5,925행·추가31개·manifest·공식 원본·namespace·49 entry URL·4개 캐시 URL·CRC가 일치했다. C5 대비 프로그램 래퍼/Agent Pack 보호 원본과 과거 필수 inventory 변경0이므로 실제 이전 ees.12 Restore PASS를 재사용한다. 새 회사 설치용 묶음을 만든 것이 아니며 이 wheel/증거 ZIP을 사내 재배포 승인으로 해석하지 않는다.


### 최종 시각 보완의 추가 확인

C9 공식 앱의17개 렌더 기록과 실제 Native 보내기1회,1536×960/1366×768/1048×768 T 단일 행동의 실제 Tab 접근·가로 넘침 없음, 현재 P 작성 진입과 계정/Workspace 접근을 PASS했다. 별도 최초 패널에서 T/J 재선택 없이 편집→실제 owner UNASSIGNED의 setup-p→Native 계정/Workspace를 확인했고 작성 POST는0회였다. `candidate9/`, `candidate9-first-authoring/`, `native-final-evidence-index.json`에 원문을 보존한다. 17은 렌더 기록 수이며 단위시험17건이 아니다.

C9 wheel SHA256 `e4ef9c947fa46ca91eb631eb1860bebe5b6f542f87a10b7e04c1ae6e7c63b6f2`(152,030,899 bytes), source snapshot SHA256 `0ca21127fcb820c8f00e96389817a5c5bee5c7c4001c2031ffd16ad5bdd45105`의88개 원본과 전체 payload5,924/RECORD5,925·manifest·namespace·49 entry URL·4 cache URL·CRC는 일치했다. 이는 C9의 유효 중간 근거이며 뒤의 보완 패키지로 바꾸어 표기하지 않는다.

추가 P 원본의 독립 비교에서 요약 높이111→162.5px, 전체 폭 진척 막대, 옛 단계표 typography/간격, 행동 y868→989.984의 제품 차이를 확인했다. 실제 완료 수 아래에 해당 비율 막대를 두고 P 단계 표의 원본 열/글자/간격·완료 조건을 적용하며 기존 전체 작업 검색과 미완료 수는 단일 행동 뒤에서 계속 접근하게 했다. 수치와 실행 계약은 그대로다. 빈 Native 보내기의 실제 disabled는 유지하고 opacity0.5→1, cursor not-allowed로 C안 색을 적용했다. 두 변경 모두 수정 전 실패 로그를 보존했다(`p-layout-c9-before-fix.log`, `send-fill-c10-before-fix.log`).

| 남은 시각 항목 | 이유·판정과 검토 대안 |
|---|---|
| 제목/브랜드 글자 폭 | 지정 font/size/weight/line-height와 요소 배치는 대조했지만 브랜드+2px, J/T+3px, P+5px의 폭 차이가 남음. 임의 글자 압축·잘라내기로 가리지 않았고 미수락으로 남김 |
| 실제 J 기록·입력 | 지원 schema는 text 입력이며 원본은 select 표현. 기존 승인 Tool 체크명/설명이 길어 완료 행동/기록이18px 내려감. 기존 schema/자료를 위조하지 않으며 별도 지원 사례로 같은 내용량 구성 가능 여부 또는 원본 표현의 조정은 사용자 검토 대상 |
| 실제 자료/상태 | 기존 site line, 추가 상태·집계·기록/시각은 원본 예시와 다름. P 조치/점검 가능 수는6/5 대신 실제8/2. 고정 값 삽입이나 DB/자산 덮기로 맞추지 않음 |
| P/T 진척·단위 원본 충돌 | T 원본 fill43.486%가 표시25/48=52.083%와 다르고 P 원본 fill121.400px도 표시72/120=60%와 다름. 실제 UA shadow fill은 T126.203px/P145.391px이며 실제 비율 유지. C09 전체30Bold와 C07/C08 단위16Regular가 서로 달라 공통 숫자/단위 규칙을 사용하되 원본 충돌을 미수락으로 남김 |
| Native 추가 기능·경계 안내 | 실제 모델/도구/음성·응답 행동·계정/Workspace/권한 접근을 유지한 가시 차이. T 범위 계약 설명도 실제 두 줄과 원본 한 줄이 다름. 기능을 없애지 않는 기존 메뉴 안 배치나 의미가 같은 짧은 설명의 후속 검토가 대안이며 승인된 차이로 제외하지 않음 |
| DB 실행 중·실패·재시도 | 현재 승인 legacy mock은 동기 응답이며 DB 원본과 같은 상태를 지원 인터페이스로 재현하지 못함. AP의 선언 실패는 별도 C 규칙 확장이고 DB 세 원본의 시각 PASS를 대신하지 않음 |

**C10 공식 앱 재검 PASS:** 동일6상태의 원본/앱 정렬12 PNG, 실제 AP 선언 실패 확장2 PNG, notice 없는 실제 상세587:4886 원본1 PNG,1366×768 P 다크 확장1 PNG 등16개 렌더를 새 패키지에서 생성했다. 실제 빈 보내기는 disabled=true·1개·opacity1·#37658b이고 실제 클릭 뒤 Native 제출0회였다. P 다크의 실제 Tab은 단일 활성 행동에 도달했으며 단계표/본문/document/composer 가로 넘침이 없었다. P 단계 목록 y377/h415, 단계표 y417/h375, 완료 조건 y816·행동 y868로 원본 배치를 다시 확인했다. P 진척은 실제 UA shadow box의 track242.328×3/fill145.391×3(72/120)를 측정했다. 상세는 실제 첫 저장 기록·현재 시각이며 원본의 #3/고정 시각을 주입하지 않았다. `candidate10/fullapp-result.json`·`visual-result.json`은 ok=true다. C9의 최초 작성 진입과 T3크기 키보드, C7첨부/저장, C5기존·새대화3회는 영향 원본이 불변이라 재사용하며 C10에서 새 실행했다고 세지 않는다.

**보존된 제품 후보 C10:** `open_webui-0.11.3+ees.12-py3-none-any.whl`, 152,031,399 bytes, SHA256 `cd04655dc6add2ae941188d73a257b1bbb47b604026db6b0092b73aca0fad31f`. source snapshot SHA256 `13ea0afc6ec30ee921c1fa5d7e25ffacb9163bdb36ce6f3fc9c71b01c436f47c`, builder SHA256 `3afa6f1371f5815c555434ab3bec011b146027e1e88c64fe1af66565ef0cee7a`. C9 대비 제품 변경은 view/launcher CSS/chat-theme3개이며 현재88개 원본=동결본, 전체5,924 payload/5,925 RECORD·31 additions·manifest/공식 원본·49 entry/4 cache URL·CRC 모두 일치했다. C5 보호 원본/과거 Restore inventory 변경0으로 물리 Restore 근거를 재사용한다. `candidate10-package-audit.json`과 최종 Git 원본 연결 감사는 첨부 증거의 관리 원본이다. wheel은 시각 검토용이며 배포 승인이 아니다.

**마지막 상세 보완·C11:** C10의 실제 상세 비교는 외곽만 같고 기존 공통 h2/h3/p margin으로 제목+22px·탭+96px, tab weight400, backdrop alpha0.18 차이가 있었다. 기존 C10 computed JSON에 같은18개 회귀 assertion을 적용해9 FAIL을 보존했다(새 UI 실행 아님). 실행 상세에 한정한 margin0·tab500·#202c3e backdrop으로 수정했다. C11 공식 앱의 같은16개 렌더 및 상세18/18 assertion PASS: title y156/h40, identity y156/h100, invocation y276/h78, tab y378/h40/500, dialog520,80,880,920. 저장된 실제 기록과 반환 필드는 바꾸지 않았다. 실제 빈 보내기 클릭 제출0·P1366 다크 단일 행동과 넘침 없음도 다시 PASS했다. 상세 변경 영향의3크기/긴 내용/상세 초점 회귀1건을 별도 재검하고 C10의 나머지 완료 복귀3건을 재사용한다.

C11 렌더에 사용한 wheel은 `open_webui-0.11.3+ees.12-py3-none-any.whl`, **152,031,415 bytes**, SHA256 **`fc741dcedf6b894090c85c782e8c76b924aa8c9b6adedefb0ab68a4880b58e08`**이다. source snapshot SHA256 `814bc867b91f44dd0513aeea9e1a76c96ee912757a1ab56d5ff45a23be1e96b4`; C10과 제품 차이는 launcher CSS 하나이며 현재88개 원본/동결본·전체5,924 payload/5,925 RECORD·manifest/공식원본/namespace/URL/CRC가 일치했다. C5 보호 원본·과거 inventory는 불변이다. `candidate11-package-audit.json`과 증거 색인·원본/비교 PNG에 해당 실행을 연결한다.

**원격 보존 뒤 최종 게시 패키지 C12:** Draft #67의 정확한 부모 `e55f9a4ce8c8719947142bc1600b16cb504b5e75` 위로 후속 변경을 연결했다. 현재 원본은 C11과 비교해 SVG8개만 다르며 원격의 Figma 원본 EOF 보정을 그대로 보존한다. 7개 SVG는 닫는 태그 뒤 LF 차이뿐이고 기본 avatar는 중첩 SVG의 같은 LF 차이뿐이다. 바깥/중첩 XML 구조·모든 속성/경로가 같고, 전체 wheel도 SVG8개·RECORD 외 모든 member 바이트가 같다. C11의16개 원본 PNG/기능 검사와7세트 비교를 이 경계에서 재사용하며 C12 UI를 새로 실행한 것으로 표시하지 않는다.

최종 wheel **`c5687ca97f0cd041c14b932fdb6110cb99a353de0effade52608ec0546337dc8`**, **152,031,411 bytes**; source snapshot **`ba680e2a60c600122cf0cf6c2b383a5aa149ed8b7872c822201da80145950c87`**. 현재88개 원본/동결본·전체 payload/RECORD·manifest/namespace/CRC 일치는 `candidate12-package-audit.json`, XML/전체 바이트 비교는 `candidate12-render-reuse-proof.json`, 최종 Git commit 원본 연결은 `candidate12-git-source-audit.json`에 기록한다. 버전명은 동일 ees.12이며 이 검토 결과는 재배포 승인이 아니다.

**마무리 gate:** Git 추적 파일과 이번 새 파일 전체를 포함한 깨끗한 원본 export에서 문서 검사·`git diff --check`를 수행했다. 문서31개·링크1321개·오류0·검토후보0이다. 부분 dist snapshot의 상대 링크 오류는 원본 검사로 대체한 이유와 초기 실패를 위에 보존한다. 검증 제품88개와 최종 Git 원본·wheel의 일치는 별도 감사에 연결하며 커밋/push 뒤 원격 head·Draft=true와 main 불변을 다시 확인한다. 커밋별 `[skip ci]`, 원격 dispatch/재실행 없음, Windows/사내 설치·실 API/모델 품질·사용자 시각 수락 미실행이다.

전체 시각 일치와 사용자 수락은 **미완료**다. 측정한 영역의 일치·관련 기능 PASS·스크린샷 생성 성공을 전체 수락으로 확대하지 않는다. 원본 없는 작은 화면/다크·추가 상태는 C 규칙의 확장으로 구분한다. 최종 원본 PNG·원본 전체/앱 영역 나란히·50%겹침·요소 좌표/computed style·항목별 판정과 핵심 로그를 첨부 증거로 제공하며 증거 ZIP은 설치 프로그램이 아니다.

### 사용자 승인 뒤 #67 병합·사내 시험 적용 준비 · 2026-09-29

사용자가 사내 적용 뒤 직접 확인하겠다고 요청했다. 기존 TrialCommit은 canonical clean main·HEAD·origin/main 일치를 요구하고 수동 Apply도 main 반영 뒤 사용하는 절차이므로, 앞서 별도 승인으로 둔 Draft 해제·병합을 확인했다. 사용자의 명시적 승인 뒤 최신 #67 head `9d7f3fc67a6a20eb4d3f10647afaf4ddea13afdf`와 main `8027aaf2e654778f052a966e5a49feed0fc54f69`를 재조회했다. 충돌 없음·리뷰/댓글 없음, main protected=false, head check/Actions run0을 확인했다. 09-30까지 원격 CI 생략은 PASS가 아니며 모든 후속 커밋/병합 메시지에도 `[skip ci]`를 사용한다.

최신 C12 wheel `c5687ca97f0cd041c14b932fdb6110cb99a353de0effade52608ec0546337dc8`/152,031,411 bytes와 동결 원본88개를 현재 Git blob과 다시 대조해 불일치0이었다. 이 후속은 승인·적용 안내 기록만 바꾸며 제품 코드는 변경하지 않는다. 병합 tree의 제품 원본이 같은지 확인한 뒤 기존 기능/시각 근거와 wheel을 재사용한다. 최종 깨끗한 병합 원본에서 기존 묶음 빌더로 ZIP의 `source_commit`·`source_dirty=false`·전체 파일 hash를 확인하며 실제 merged/main SHA와 준비 결과는 [같은 PR #67의 병합/배포 준비 기록](https://github.com/knadalkim-a11y/team-agent-poc/pull/67)에 연결한다.

회사 PC에서는 검증한 최종 main SHA의 기존 Update → Upgrade -TrialCommit 한 블록을 사용한다. 준비 검사 뒤 Stop → Backup → Apply → Start/최대120초 health → 같은 원본 ApplyDemo가 진행되며 별도 ZIP 다운로드·새 환경·자산 재등록·ApplyDemo 반복은 필요 없다. 앞 단계 실패 시 중단하고 `stage/code/next` 요약만 확인한다. 정상 적용 뒤 프로그램 Restore는 현재 DB·대화·업무 이력·사용자 자산의 되돌리기가 아니다. 상세 절차는 [기존 적용/복구 안내](../docs/03-openwebui-native-agent.md#c-design-trial-20260929)를 재사용하되 #66의 과거 SHA 대신 #67의 실제 병합 SHA를 쓴다.

이번 승인은 전체 시각 일치 PASS나 사내 적용 성공을 뜻하지 않는다. J 입력 전/완료, P/T 목록/검색, 상세/닫기와 실제 Native 보내기·기존 대화/저장/이력을 사용자가 확인하고 마지막 적용 요약과 정상/문제 1~2줄만 전달한다. 사내 화면·파일 반출은 요구하지 않으며 Windows·실제 모델/API·사내 적용·시각 수락은 결과 수신 전까지 미실행/미완료다. 기존 실패와 미수락 차이는 위 기록 그대로 유지한다.

<a id="c-design-phase3-20260929"></a>

## C안 통합 회귀·개발환경 검수 · 2026-09-29

**원본·범위:** 같은 Draft #66의 원격/로컬 `7d9f2caaa7ef39522fd5fa3f69af732e5fcebeeb`와 main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`, 두 AGENTS/STATUS·깨끗한 checkout을 재확인했다. main의 과거 #65 병합 대기는 반복하지 않았다. [필수 경로·합격/중단 조건](../docs/mockups/ees-work/TASK.md#c-design-phase3-20260929)을 먼저 정했다. 1·2단계/세 보완과 #65를 보존하고 아래 조회 실패 보호만 수정한다. CSS·backend·인증/저장/실행기·버전 ees.12/Pack0.2.14는 그대로다. #53·Windows 작업·실계정/운영 DB는 건드리지 않는다.

**환경·경계:** 기존 단일 `.venv` Python3.11.16/187개 의존성, Node24.19.0, Chrome153.0.8010.52, 공식 Open WebUI0.11.3 wheel(`8436f9bb…fa547`)을 재사용했다. 실제 CLI 앱은 실제 Native 가입/로그인/대화·Tool/Valves/승인·모델 adapter·P 게시·EES HTTP·임시 SQLite를 사용한다. 이 앱의 외부 HTTP/OpenAI 응답만 loopback 합성이다. 별도 브라우저 fixture는 실제 패키지 frontend/EES 서비스/임시 DB이며 Native 인증/채팅·외부 전송이 합성이다. 실제 Native 계정 전환 브라우저와 실제 Users/Groups/ACL/자산 검사는 따로 집계한다.

**Figma·제품 차이:** 00:52~00:55 UTC(09:52~09:55 KST)에 지정 파일/페이지의 비교603:963과 J6/P1/T2, 총10개 context/렌더 및 원본1920×1080 PNG4개를 읽었다. 원본 쓰기 없음. 동일1920 제품을 직접 대조하고 1536×960/1366×768·긴/좁은/다크는 반응형 행동으로 확인한다(해당 크기·다크 Figma 원본은 없음). 제목30/42·결과22/34·여백32/24·선택 표현·단일 행동·독립 스크롤을 기준으로 한다. Native 계획 dialog, 기본값 실행 허용, 현재 입력/호출 snapshot, 여섯 예시 밖 실제 대기/부분/UNKNOWN 등은 의도된 차이다. 고정 집계·4초 타이머·가짜 결과를 넣지 않았다. Figma asset host 과거 차단은 반복하지 않고 지원 inline 렌더를 사용했다. SVG 원본 전체 바이트 대조는 미실행이며 아래 패키지 자산 바이트 검사와 다르다. 개발자 자체 사용성 검토를 사내 사용자 수락으로 표시하지 않는다.

### 결함과 시험 준비 오류

- **제품 재현:** baseline 실제 legacy 초안 저장→검토 자료 열기→조회 실패에서 오류 안내 뒤 dialog_open/자료 잔존/본문 자료 잔존이 모두 true였다. 현재/과거의 실패한 조회는 공통 본문을 숨기고 모든 보조 자료 창의 복사 내용을 즉시 비운다. 미저장 글은 기존 draft map에 남겨 성공 재조회 뒤 복원하며 저장 DB는 바꾸지 않는다. 과거 건 ID도 창의 대상에 포함하고 최초 과거 조회 실패의 재조회 대상을 보존한다.
- **중간 제품 회귀:** v2의 controller65 중64PASS/1FAIL은 current 실패를 별도 성공한 historical 조회에도 적용한 과도한 guard였다. 각 건의 조회 성공은 독립적으로 인정하되 실패 당시 열린 과거 자료는 그 건을 다시 읽기 전까지 숨기는 조건으로 좁혔다. 같은 단독 검사 및 v3 controller21/panel44 전체 PASS로 닫았다.
- **준비 오류:** 첫 privacy 모듈이 import된 suite까지25개를 실행한 선택 오류, 과거 진행 chat 재사용/펼침·비동기 대기 오류를 분리했다. v2 브라우저41은36PASS/고유5FAIL(서브검사 포함6실패): 접힌 상세 미열기, 사람 확인 busy 전 재개, 이미 열린 메뉴 toggle, 숨긴 본문 버튼을 찾는 옛 기대, 과거 내부 이력 미펼침이었다. 실제 클릭·대기·재조회 경로를 수정하고 같은 조건으로 재검한다. 강제 DOM 열기/JS 클릭으로 우회하지 않았다.
- **전체 앱 준비:** Valves timeout 상한, 이미 연결된 chat 재사용, Native release note 설정, 게시 id_map, 선택 완료 전 클릭을 시험에서 수정했다. 실제 worker의 `encryption_required`는 임시 환경의 Native 암호화 flag 누락을 정상 차단한 결과다. 기존 임시 WEBUI_SECRET_KEY와 ENABLE_VALVE_ENCRYPTION을 사용하며 서버 보호를 완화하지 않는다. Native 계정 fixture의 import 준비 오류와 teardown 잔여 task 경고도 별도 로그로 남긴다. 실패/중간 버전을 최종 PASS에 합산하지 않는다.

### 최종 유효 판정

**3차 개발환경 검수 통과.** 최종 동일 제품 wheel SHA256 `d35bc2bb4adc789cc93752b49550a47446461f1e54ba0015a3952e6af78ca254`, 포함 자산23개와 원본 바이트 일치/불일치0. 최종 code freeze145개를 보존했다. 후반 변경은 전체 앱 시험 준비와 fixture 종료 정리뿐이며 영향 검사만 재실행했다.

| 최종 근거 | 판정 |
|---|---|
| 실제 CLI/Native 앱 | PASS, 26개 기록 지점(단위시험26건 아님). 가입/승인·두 사용자·실제 대화 API/2메시지 저장/브라우저 재표시, legacy 저장/복원/실패/재시도, Native 고정3호출·AI1·후보 입력/명시 재개·사람 확인/재기동·이력/복귀 |
| 제품 브라우저 fixture | 41/41 PASS, skip0, 125.040초. 완료 CTA inline/dock·T 목록/초점/T→P·직접 진입/재열기, 과거 판정, 활성5상태 초안 차단, 두 탭 충돌/늦은 응답, 크기3종·긴/좁은/다크·키보드 |
| 서비스/실제 Native API·자산 | 45 PASS + 실제 Native 계정 전환 브라우저1 PASS. 권한 회수/게시 충돌·snapshot·사용자 자산/키 보존·UNKNOWN. teardown 수정 영향3+1 재검도 PASS, 잔여 task 진단0 |
| 화면/controller | Node25·panel44·controller21 PASS. 문서·구문·UTF-8·diff 검사 PASS |

전체 앱의 P는 호출 성공/4개 J 완료여도 저장 `scope_complete=false/source_scope_limited`라 과거 화면의 전체 기준 미충족을 유지한다. 실제 worker 실패는 final_validation 미기록→미판정, 사람 J는 저장 succeeded→화면 통과다. 이는 호환 실패판정 fixture와 별개다. 실제 완료 버튼·과거 메뉴·초안 차단을 다시 조작했다. 강제 종료 후 같은 run/call UNKNOWN·외부 호출1회 유지/자동 재실행0을 확인했다. 직전 패키지 Restore/재적용 뒤 Native 응답8개·대화2메시지·개인 Valves/키·실행이 같았다.

준비 오류의 추가 원인은 부분 범위를 전체 통과로 기대한 시험, 최초 관리자 생성 후 가입 비활성 설정, 타인 case의 기존 `400/case_not_found`를403으로 기대한 시험이었다. 임시 가입 설정은 검사 뒤 원복했고 타인 chat401/case400에서 자료가 없음을 확인했다. 최종 완주본만 집계하며 초기9회 중단 기록은 첨부 JSON에 보존한다. 실제 Native composer 보내기 버튼은 미실행(실제 completion·chat 저장 API와 브라우저 표시/재접속 검증), fixture 채팅 클릭과 구분한다.

**보존·재사용:** 기존 ees.10/11 wheel이 이 작업 위치에 없어 과거 버전 writer/물리 Restore를 새로 실행한 것으로 표시하지 않는다. 해당 backend/builder는 불변이므로 [#65의 TR21 및 물리 Apply/Restore 3건](scenarios.md#shared-native-runtime-20260925)과 [SA25 legacy fallback](scenarios.md#system-authoring-20260924)을 당시 버전의 유효 근거로 재사용한다. Native protocol에 구형 writer를 허용한다는 뜻이 아니다. 이번 실제 앱의 직전7d9f 패키지↔최종 패키지 교체는 같은 임시 DB/키/자산의 프로그램 호환 검사이며 DB rollback이 아니다.

**미실행·제외:** Windows·사내 설치/실서버·실 API/모델 품질·OP-01~04·비개발자 실제 사용자 수락은 미실행이다. 병합·배포·Draft 해제는 승인 범위 밖이며 하지 않는다. 09-30까지 지침대로 커밋은 `[skip ci]`, 원격 dispatch/재실행 없음. 검토용 PNG·핵심 JSON/로그·증거 ZIP은 Work 결과에 첨부하고 프로그램 wheel과 구분한다.

<a id="c-design-composer-merge-20260929"></a>

### 후속 Native 보내기 gate·병합·시험 적용 준비 · 2026-09-29

**인수·승인:** 원격 main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`, Draft #66 head `a49350e31dcbbc4d1687293a0ccd8dcf0b541989`와 깨끗한 로컬이 사용자 인계 SHA와 일치했다. 두 대상 AGENTS/STATUS, 앞선 1·2·3차 기록과 dist/wheel/로그/검토 ZIP 접근을 확인했다. #53은 별도 Draft로 유지한다. 사용자가 이번 gate와 관련 보완, 조건 충족 후 Draft 해제·#66 병합, 정확한 병합본 배포 준비를 승인했다. 위의 병합 미승인 기록은 당시 경계이며 이번 승인과 다르다. 회사 PC 적용은 사용자가 실행하고 새 사내 성공 보고는 아직 없다.

**남은 필수 경로 PASS:** 기존 공식 앱 시험에 `--composer-only`를 추가했다. 같은 최종 wheel `d35bc2bb4adc789cc93752b49550a47446461f1e54ba0015a3952e6af78ca254`, 공식 CLI·실제 Native 가입/로그인·대화/EES API·새 임시 SQLite를 사용했다. 외부 모델의 SSE 응답만 loopback 합성하고 사내 모델 품질로 확대하지 않는다. 준비 단계의 빈 대화/모델·사용자 설정과 검증용 GET을 제외하고 모든 메시지는 실제 composer 입력과 보내기 클릭으로 생성·저장됐다. completion API 직접 실행이나 저장 메시지 주입은 없다.

| 실제 조작 | 최종 증거 |
|---|---|
| 업무패널을 연 기존 대화의 첫 전송 → 새로고침 → 같은 대화 두 번째 전송 | trusted 입력/클릭 각 1회, 매번 Native completion 요청/task/외부 모델 호출 각 1회, 저장 메시지 2→4개, 응답 표시 1→2개, 과거 메시지 본문/ID 보존 |
| 새 채팅 → 다른 공장(hu-a) 선택 → J 입력 저장 → 첫 보내기 | UI가 만든 미연결 진행 건이 새 대화에 1회 연결, 메시지 2개/응답 1개, 기존 us-a 대화·진행/작업 기록 불변 |
| 요청·응답·저장 대상 대조 | 기존 요청 chat_id와 반환 ID 일치; 새 첫 요청은 chat_id 없이 서버가 생성한 응답 ID를 URL/저장 메시지 ID/진행 건과 대조. 총 대화 정확히 2개, 미연결 진행 잔여0 |
| 새로고침·이동 | 두 대화의 저장 history와 복원 history 정확히 일치, 재요청0, 총 모델 호출3, API 오류0. 기존/새 제품 PNG도 직접 확인 |

**초기 준비 실패 보존:** (1) 현재 Native 요청의 `user_message`를 이전 `messages`로 기대한 오류, (2) 같은 공장/워크플로우 선택이 기존 활성 진행의 대화를 재개하는 의도된 동작을 새 진행으로 기대한 오류, (3) 새 첫 요청에 아직 없는 chat_id를 기대한 오류가 각각 중단됐다. 실제 요청/공식 서비스 계약을 확인하고 다른 공장 선택·응답 ID/저장 ID 상관 검사를 사용해 같은 버튼 경로를 재검했다. 독립 검토에서 두 번째 응답을 첫 응답 문구로 잘못 인정할 위험도 찾아 실제 렌더 응답 수와 과거 메시지 필드를 검사했다. 제품 결함은 발견되지 않았고 제품 코드 수정은 없다. 실패를 최종 PASS에 합산하지 않는다.

**명령·증거:** 기존 `.venv`/Chrome를 재사용한 아래 명령 exit0, 두 변경 Python의 compile(인코딩 경고 오류 처리)·문서 점검·`git diff --check`를 확인했다. 최종 JSON/PNG/로그는 `dist/c-phase3/composer-final/` 및 `composer-final.log`, 실패는 `composer-first/second/third`에 보존한다. 시험용 SSE는 stream 요청 분기에 한정하고 이전 non-stream 통합 검사를 새 실행으로 합산하지 않는다.

```bash
.venv/bin/python -X warn_default_encoding -W error::EncodingWarning tests/ees_work_c_phase1_app.py --composer-only --wheel dist/c-phase3/final-v3/open_webui-0.11.3+ees.12-py3-none-any.whl --chrome dist/tools/chrome-headless-shell-linux64/chrome-headless-shell --output dist/c-phase3/composer-final
```

**패키지·재사용:** 최종 `final-v3/manifest.json`의 wheel 151,959,136 bytes/SHA와 실제 파일이 일치한다. 고정 공식 wheel과 현재 builder 변환으로 전체 payload 5,916개 바이트, RECORD 5,917행·멤버 집합·중복 없음·CRC를 확인했다. 과거 `source-wheel-final.json`은 중간 산출물이며 최종 `source-wheel-final-v3.json`과 구분한다. a49350 이후 제품·backend·builder·Agent Pack 불변이므로 위의 3차 광역 및 #65/TR21·SA25 유효 증거를 재사용한다. 이번에 전체 suite나 Windows Restore를 다시 실행한 것으로 표시하지 않는다.

**문서 검사 한계와 조치:** 후속 증거 추가 시 scenarios.md가 1MiB 검사 한도를 넘어 최초 문서 검사가 실패했다. 검사 상한을 변경하지 않고 이 C안 3차 절만 날짜·과거 판정·초기 실패·본문 그대로 별도 평가 원본으로 옮겼다. 기존 두 anchor는 scenarios.md에 연결점으로 보존하고 관련 링크를 검사한다.

**Git·준비 종료 조건:** 로컬 HTTPS Git fetch는 자격증명이 없어 사용할 수 없었으나 인증된 GitHub 앱으로 조회·동일 PR 반영 경로를 사용한다. 초기 main은 unprotected/필수 status 없음, #66 clean·review/thread 없음이었다. rulesets 조회는 유료 기능 제한403으로 재호출하지 않았고 최종 원격 head/병합 가능 상태를 다시 확인한다. 09-30까지 각 커밋/병합 메시지 `[skip ci]`, 원격 dispatch/재실행 없음. 병합된 tree가 검증 제품과 같을 때만 wheel을 재사용하며 깨끗한 정확한 병합 checkout에서 기존 bundle builder로 새 ZIP의 `source_commit/source_dirty=false`·파일별 해시를 확인한다. 실제 merged 상태·병합 SHA·main과 최종 ZIP/hash는 [같은 PR #66의 병합/배포 준비 기록](https://github.com/knadalkim-a11y/team-agent-poc/pull/66)에 기록한다. 당시 준비 중 상태를 병합 완료로 추정하지 않는다.

**사내 경계:** [적용·복구 안내](../docs/03-openwebui-native-agent.md#c-design-trial-20260929)에 따라 현재 원본을 기존 Status 한 줄로 먼저 확인한다. #65→C안 Agent Pack 변경은 없고 기존 Upgrade의 자동 ApplyDemo는 지정 관리 필드 보호/불변 no-op·충돌 중단을 유지한다. 별도 초기화·재등록·사용자 전체 동기화는 하지 않는다. Stop 전 준비 검사, Stop/Backup/Apply/health, 프로그램 Restore와 DB/자산 복원을 구분한다. Windows·사내 기동/보내기/C안/업무 저장·이력, 실 API/모델·OP·실사용 수락은 결과 수신 전까지 미실행이다.
