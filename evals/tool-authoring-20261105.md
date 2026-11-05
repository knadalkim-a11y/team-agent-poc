# 도구 작성·연결·시험·사용 설정 검증

<a id="pr123-merge-review-20261105"></a>

## 2026-11-05 · 전체 PR 병합 검토와 실제 설치 worker 보완

- **범위/원본:** 사용자 전체 검토·병합 요청. #124 `7eca930`의 CI483 성공·실제 제품 검증 근거를 확인하고 Node 실행/Native 복귀166개·workspace85개·문서/diff를 재검해 main `c01bf098f1e11aa42bec6c8a1f8f0d6eef5121d1`로 병합했다. #123 원격 `cdfa7c5`에 해당 main을 merge하고 STATUS의 양쪽 기록을 보존했다. 원래 개발 사본의 수정 중 문서는 건드리지 않았다.
- **최초 실패:** [CI484](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41990693577)의 Complete Native product 작업 `127124145454`는 실제 새 도구 시험에서 `unknown/tool_trial_worker_load_failed`로 실패했다. 합성 fixture의 제한 진단은 `ees_asset_guard._active_guard`의 `503 conditional_write_unavailable`을 확인했다. 앞선 CI480 실패와 단위 loader 통과는 그대로 보존한다.
- **확인된 원인/조치:** 배포 빌더가 명시 `content`를 받는 Native loader에도 서버 guard를 적용했다. 짧은 수명의 시험 프로세스는 서버 guard가 없어 읽기/쓰기 없는 코드 로딩도 막혔다. 준비된 로컬 `f887c27`의 수정 7개 파일을 검토 사본에 적용했다. 고정 loader의 문자열 content 경로만 독립 호출을 허용하고, 기존 guard가 있거나 content가 없으면 기존 guard를 통과해야 한다. Native DB 쓰기와 캐시 로딩 차단은 유지한다.
- **재발 방지:** worker 단위 fixture도 실제 배포 빌더의 loader 데코레이터를 포함한다. Native 버전이 같아도 설치된 작성 실행·검사·guard 파일 바이트 변경/누락이 이전 시험 및 사용 재개 확인을 무효화하도록 검사한다. 실제 설치 CLI의 연결→worker→결과→재조회 검사를 계속 최종 CI의 필수 조건으로 둔다.
- **통합 검증:** Linux Python3.11.17의 작성·정적 검사·시험·Native80/80, guard20/20과 Node 작성·실행·Native 복귀478/478 통과. Python은 `EES_TEST_UPSTREAM_WHEEL`로 고정 공식0.11.3 wheel과 실제 배포 패치 fixture를 사용했고 `EES_REQUIRE_ASSET_NATIVE=1`로 생략을 허용하지 않았다. 패키징33통과·현재 frontend 자료 필요1생략, 시험 ID 감사1,690개 오류0, 문서/diff 검사 통과. 전체 필수 CI는 최종 head 기준으로 확인한다. 최종 커밋·CI·병합 결과는 [PR #123 본문과 Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/123)에 연결한다. 사내 연결/토큰/데이터·실제 적용은 미사용/미실행이다.

<a id="phase1-evidence"></a>

## 기준과 실행 환경

- 2026-11-05, main `8258318`, 공통 계약 `1b81452`. [ST-P1](../docs/specs/shared-tools.md#tools-redesign-v2-phase1-20261105)의 새 작성 경로만 구현한다. 실제 사내 연결/토큰/DB는 사용하지 않는다.
- Linux, 단일 Python 3.11.17 venv, CI 고정 Python 의존성. Python 3.12 기본 환경의 검사와 고정 3.11 검사를 구분한다. 공식 wheel은 관리 pin SHA256을 대조한 뒤 로컬 시험 자료로 보존했다.
- 서버 `72b2524`·화면 `bcd9cb5`는 같은 계약에서 독립 worktree로 개발하고 총괄이 merge로 통합했다. 별도 검증 담당이 실제 Native UI 검사를 추가하고 리뷰 담당이 수정 전 재현으로 보완을 확인했다. 실제 사내 배포는 미실행이다.
- Figma 2판 T01/T02/T02A/T03/T04의 PNG·노드·해시는 [고정 자료](../docs/mockups/ees-work/tools-phase1-20261105/metadata.json)에 보존했다. 참조 이미지 보존은 제품 렌더 비교 통과를 뜻하지 않는다.

## 확인 조건

| ID | 확인할 행동 |
|---|---|
| P1-01 | 관리자 생성/저장/재조회, 불완전 코드와 정적 검사 결과 구분 |
| P1-02 | 비관리자의 코드·정의 조회/변경/검사/가져오기 거부 |
| P1-03 | 구문·형식 검사에서 사용자 코드·모듈·함수·외부 요청 미실행 |
| P1-04 | 현재 Native 읽기 권한 재검사, 코드 복사 후 원본·설정·PAT 보존 |
| P1-05 | expected_revision 충돌·동일 request_id 재전송과 중복 저장 방지 |
| P1-06 | 수정본 저장 후 사용본 참조·기존 도구·작업 연결·진행·기록 불변 |
| P1-07 | 입력 질문·선택지 이름·결과 표시 정의 저장, 코드 정의와 차이 진단 |
| P1-08 | 화면 미저장/실패/충돌 입력 유지, 정적 확인과 시험/활성화 분리 |
| P1-09 | 고정 2판 T01/T02/T02A/T03/T04 시각 대조와 실제 서버 왕복 |
| P1-10 | 새 배포 모듈 포함, 이전 ees.14 Apply/Restore, 누락 출하물 거부 |

## 실행 결과

- 공통 계약 문서 검사: 오류/검토 후보 0, diff 검사 통과.
- 빌드/복원: 새 모듈 두 개의 포함 및 이전 ees.14 양방향 Apply/Restore·누락 incoming 거부 신규 검사를 통과했다. 기존 delivery-suite/customization 합계 72개 중 67통과·실환경 자료 필요 5건너뜀(18.639초, Python3.11).
- 통합본 Node 22.16.0: `ees_delivery_suite.NODE_SCRIPTS['services']`의 10개 스크립트 전부 종료 0. TAP 653/653 통과·실패/건너뜀 0, 별도 retirement assertion 2개 통과. 이 중 작성 UI 287개(신규 15개) 통과.
- 통합본 Python 3.11: 새 저장 서비스 12개·정적 검사 32개, 기존 operations 55개·workspace 85개·Figma authoring 8개·Figma contracts 24개·delivery suite 11개 통과. 새 모듈 두 검사는 기본 인코딩 경고를 오류로 처리했다.
- 고정 공식 wheel을 쓴 `test_ees_shared_tools_native.py`는 통합본에서 45/45 통과(198.088초). 코드 복사 권한·설정 컬럼 미조회·원본 보존과 기존 사용 도구 회귀를 확인했다. 실제 사내 서비스 호출이나 브라우저 검사가 아니다.
- 기존 authoring 29개 중 23개 통과·과거 ees.10 실제 wheel이 필요한 6개 건너뜀. branding 34개 중 33개 통과·현재 고정 소스 frontend 산출물이 필요한 공식 wheel 최종 감사 1개 건너뜀. 건너뛴 7개는 성공으로 집계하지 않는다.
- 통합 후 새 모듈의 이전 ees.14 Apply/Restore·누락 출하물 거부 검사를 다시 통과했다. 독립 아이콘 목록에 새 `e01ea.svg`를 추가해 포함·누락 거부를 함께 확인했다.
- 시험 ID 감사: 과거 1,332개·현재 1,647개, 오류 0. 새 Python 두 모듈을 services에 등록하고 기존 브라우저 검사 모듈 안에 실제 저장/재열기·충돌/권한 회수·가져오기 검사 3개와 1920/1366/360 창 검사를 추가했다. 브라우저 검사는 구문만 확인했으며 실행 성공으로 집계하지 않는다.
- 상세 로컬 로그는 `dist/tools-phase1-verification/`의 스크립트별 로그와 Node/Python JSON에 남겼다. 이후 원격 CI 결과가 로컬 결과를 대신하거나 이미 확보된 실패 기록을 지우지 않는다.
- 마지막 통합 Python 범위는 위 10개 모듈과 추가 Restore 1개를 합쳐 336개 중 329통과·7건너뜀이다(초기 branding 실패 보완 후). 별도로 앞서 수행한 72개 빌드/복원 검사와 겹치는 항목은 합산하지 않는다. 문서 35개·링크 2,894개 오류/검토 후보 0, Python/JS 구문·diff 검사 통과. 로컬 리뷰 범위에서 남은 확인된 결함은 없으며 P1-09의 실제 브라우저 왕복·시각 대조는 미완료다.

## 최초 관측과 보완

1. 새 배포 복원 검사 첫 실행에서 누락 모듈 차단은 성공했으나 시험이 bundle 자체를 바꾸기 전의 tree와 비교해 2개 단언이 실패했다. 실패 fixture 준비 후의 tree를 기준으로 비교하도록 고쳤고 재검 통과했다. 제품의 검증/복원 조건은 약화하지 않았다.
2. 공식 소스 checkout을 저장소 dist 안에 두자 문서 검사가 upstream CHANGELOG의 1MiB 초과로 실패했다. 외부 소스 작업공간으로 옮겼으며 문서 검사 한도는 유지했다.
3. 로컬 Chromium은 about:blank부터 `socket() failed: Operation not permitted` / `ptrace Operation not permitted`로 기동 실패했다. 제품에 도달하지 않은 환경 제한이며 브라우저 통과로 처리하지 않는다. 실제 UI/합성 계정 Native 시험은 원격 필수 CI에서 확인해야 한다.
4. 최초 통합 브랜치 push는 자동 승인 검토에서 소스 외부 게시에 대한 명시적 승인 미확인으로 거절됐다. 다른 전송 수단으로 우회하지 않았다. 원격 PR/CI는 아직 없으며 로컬 코드/검증을 끝낸 다음 게시 승인을 요청한다.
5. 독립 리뷰에서 조건부·클래스 내부·튜플/예외/패턴 바인딩으로 기본형 이름을 가리거나 Tools를 재할당할 때 정적으로 지원 형식으로 오판할 수 있었다. `ees_workflow_tool_draft_check.py`의 이름 바인딩과 메서드 검사를 보완하고 원재현·32개 회귀로 확인했다. 약 33KB 코드가 6.4MB 검사 결과로 확대되는 재현은 정의 수·크기 budget으로 377바이트 `definition_limit` 응답과 빈 schema가 됐다.
6. 잘못된 `output_ui.fields` 구조가 저장되면 화면이 열리지 않는 재현은 저장 envelope 검사로 거부하고 누락 표시 필드를 보완했다. 불완전한 내용의 저장은 유지했다. 기존 도구 코드 읽기는 Native ORM 전체 대신 필요한 컬럼만 조회해 설정·PAT를 읽지 않는 것을 검사했다.
7. 첫 코드 확인을 생략하고 바로 저장할 때 질문 수정이 저장되지 않던 문제, 새 도구에 이전 생성 캐시가 복원되는 문제, 권한 회수 후 코드 캐시가 남는 문제를 UI에서 보완했다. 충돌 비교와 관리자 상태 갱신 회귀도 추가했다. 코드의 인자·선택지 변경 후 보이지 않는 이전 설정이 남는 경우는 사용자 입력을 보존하고 명시적인 정리 경로를 제공한다. 리뷰 담당이 수정 전 절차로 재검증했다.
8. 통합 branding 최초 실행은 wheel 안 새 모듈이 존재해도 설치 시험이 고정 목록만 추출해 `ModuleNotFoundError`를 냈다. 시험의 독립 추출·import 목록에 두 모듈을 추가했으며 실제 빌드 포함 조건이나 기존 단언은 완화하지 않았다. 재검 33통과·고정 frontend 필요 1건너뜀. 최초 로그와 최종 로그를 별도로 보존했다.
9. 사용자는 2026-11-05 작업 브랜치 게시·Draft PR·CI 진행을 명시 승인했다. 이후 일반 Git push는 `could not read Username`으로 실패했다. 연결된 GitHub 계정의 Git objects API로 동일한 파일 tree를 게시하고 로컬/원격 tree SHA를 대조한다. 본문의 앞선 커밋들은 로컬 개발 이력이며 원격 게시 커밋·최종 CI·브라우저 산출물의 현재 판정은 해당 PR 본문과 Checks에 기록한다. 새 정적 검사/저장 검사와 공통 fixture만 바꿔도 CI가 실행되도록 경로 필터를 추가했다.
10. [CI477](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41970974473)의 실제 제품 중앙 대화 검사에서 `tool_create`가 보이지 않아 실패했다. 새 목록의 접힌 이전 방식 관리 영역 안에 기존 버튼이 보존돼 있지만 `helper_chat_flow`가 바로 클릭한 것이 원인이다. 해당 흐름과 같은 진입을 쓰는 `create_legacy_tool` 공통 fixture에 접힌 summary를 실제 클릭하는 경로를 추가했다. 제품 권한·저장 동작·도움말 단언은 바꾸지 않았다. 실제 브라우저 재검은 수정 head의 최종 CI로 판정한다.
11. 같은 CI477 실패 캡처에서 새 도구 버튼의 흰 글자가 흰 배경에 겹치는 제품 결함도 확인했다. `.ew-author .ew-author-heading button`이 공통 primary 배경을 덮는 CSS 우선순위 충돌을 수정했고 기본·hover·disabled의 공통 토큰을 유지했다. 기존 왕복 검사에 새 도구·코드 저장 버튼의 실제 computed 글자/배경 대비 단언을 추가했다. T01/T02/T03 대표 캡처도 추가해 기존 T02A/T04와 함께 다섯 화면을 대조할 수 있게 했다. 로컬 작성 UI 287개·관련 Python 구문·diff 검사를 통과했으며 실제 렌더 재검은 최종 CI에서 확인한다.

12. CI477의 native-compose는 16건 실패했다. 접힌 이전 방식 버튼을 직접 누른 14건은 10번과 같은 원인이며, 나머지 두 건은 새 제목과 맞지 않는 움직임 검사의 문자열과 권한 회수 후 이전 공용 도구 선택이 남는 제품 문제였다. 움직임 검사는 새 제목을 정확히 확인하고 기존 목록·범위·이동 단언은 유지한다. 제품은 현재 권한 목록에 없는 선택을 해제해 새 목록으로 돌아간다. 비관리자 전환·빈 접근 목록·접근 복구 후 상세 자동 재열림 방지 Node 회귀를 추가해 288개 통과했다.
13. CI477 신규 3개 브라우저 검사(작성/재열기, 충돌 입력 보존/권한 회수, 기존 코드 가져오기)는 모두 통과했다. 그러나 실제 T02A 360px 캡처에서 하단 버튼이 좁아져 여러 줄로 쌓이고 사용 함수·검사 결과와 겹치는 시각 결함을 확인했다. 모달 직계 영역의 flex 축소를 막고 600px 이하에서 안내와 버튼 행을 분리했다. 같은 3개 창 크기에서 footer가 본문 아래인지, 버튼 글자가 1~2줄 안에 보이며 실제 hit-test가 가능한지 검사하고 스크롤 후 캡처를 추가했다. 수정 화면의 최종 판정은 새 CI 산출물에서 한다. T04 1920/1366/360과 충돌 화면은 읽을 수 있었으며, 이것만으로 T01/T02/T03 전체 디자인 비교 통과로 처리하지 않는다. 원본 PNG 7개의 SHA256·바이트 수가 CI manifest와 일치한다.
14. CI477 최종 결과는 40개 job 중 성공 35·실패 3·취소 1·건너뜀 1이다. 실패는 Complete Native product, native-compose와 그 결과를 요구한 Ubuntu Delivery checks다. Windows 집계는 실패 중 취소됐고 배포 산출물 준비는 건너뛰었다. 최초 실패를 보존하며 수정 head의 전체 CI를 새 판정으로 삼는다. 앞선 CI476은 새 head 생성으로 대체된 실행이다.
15. CI477 T04 1920px 실제 렌더는 고정판보다 결과 행이 약 16px 높고 파란 제목으로 표시됐으며, 미리보기도 예시 문서 목록 대신 정의 항목 목록이었다. 기존 details 여백 상속과 신규 컴포넌트 우선순위를 보완하고 결과 역할·숨김을 반영한 예시 문서 목록으로 맞췄다. 실행 결과로 표시하지 않으며 예시의 열기는 비활성이다. T02A의 기본 정보 이동은 링크 형태로, T03의 이름 편집은 제목 안으로 옮기고 선택지의 의도한 높이가 적용되도록 했다. T02 설명은 줄바꿈 편집을 유지하며 초기 높이를 시안에 맞췄다. 결과 종류의 고정 Figma 아이콘 88f2f를 배포·독립 포함/누락 검사 목록에 추가했다. 공통 패널·탭 토큰과 편집 기능은 유지한다. 실제 T03 비교는 추가 캡처를 생성한 수정 CI에서 수행한다.

수정 통합본 로컬 재검: Node 22의 services 스크립트 10개 전부 종료 0, TAP 655/655와 별도 assertion 스크립트 2개 통과(작성 UI 289개). 새 아이콘 포함/누락 거부를 포함한 branding 34개 중 33통과·실제 frontend 필요 1건너뜀. 문서 35개·링크 2,894개 오류/검토 후보 0, 시험 ID 1,647개 감사 오류 0, 변경 Python 구문·diff 검사 통과. 최초 로그와 수정 후 `post-ci477-*` 로그는 별도로 보존했다.

16. [CI478](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41973921019), head `326038c`는 필수 39 jobs 성공·PR에서 배포 파일 준비 1건너뜀으로 완료했다. native-compose 100/100, 최초 실패 16개 ID와 신규 3개 ID 모두 통과했다. 실제 캡처·실측에서 1920/1366/360 코드 footer와 본문 간격 20px, 두 버튼 모두 한 줄·34px·잘림 없음·hit-test 가능을 확인했다. T04 행 높이와 예시 목록 구조 차이도 해소했다. artifact `13391736647`은 24,971,773 bytes, SHA256 `61a12478f5e17054bb0117b1bd5394e363c0bac6b4c5284d2238b2d21428fc66`이며 ZIP·PNG/DOM/실측 manifest가 일치했다.
17. CI478 최종 T02A 대조에서 첫 코드 검사 뒤 함수·입력 정의를 자동 보완하고도 보완 전 진단을 현재 검사로 표시하는 추가 문제를 발견했다. `authoredChecked`를 실제 검사 요청 당시 snapshot으로 보존해 자동 변경 뒤에는 다시 확인이 필요함을 정확히 표시한다. 수정 전 실패/수정 후 통과 재현과 늦은 응답 때 추가 입력 보존을 검사했다. 처음 보고된 r1 저장 후 함수 경고는 같은 CI의 PNG·DOM을 다시 대조해 오독으로 확인했다. r1에는 함수가 정상 저장됐으며 결과 경로·표시 항목 두 진단만 있었다. 이 정상 저장 경로와 첫 검사 상태를 브라우저 회귀에서 구분한다. T01 검색 라벨, T03 연결 요약의 한국어 형식, T02 입력 중 제목의 세부 차이도 신규 작성 패널 안에서 보완했다. 제목·연결 요약의 텍스트만 갱신해 입력 포커스를 보존한다. T03 링크의 파란 테두리는 가시 포커스였으므로 제거하지 않았다. 수정 head의 CI·화면을 최종 판정으로 삼는다.

마지막 진단·표시 보완의 로컬 재검: Node services 10개 스크립트 종료 0, TAP 658/658(작성 UI 292개)와 별도 assertion 스크립트 2개 통과. 문서 35개·링크 2,894개 오류/검토 후보 0, 시험 ID 감사 1,647개 오류 0, Python 구문·diff 통과. `post-ci478-*`로 앞선 결과와 구분했다.

## 남은 확인

원격 게시 `018aa96`과 로컬 검증본 `fd786b2`의 tree `9711e922c1c5daf4427a3b20f36b69ce1340e8f1` 일치를 확인했고 [Draft PR #123](https://github.com/knadalkim-a11y/team-agent-poc/pull/123)을 생성했다. 최종 원격 CI와 실제 브라우저·디자인 비교 결과는 이 PR의 최신 head Checks·본문에 갱신한다. 고정 소스에서 빌드한 실제 UI와 디자인의 시각 대조, 사내 실제 환경 확인은 로컬 함수/DOM 검사로 대체하지 않는다.


## 1페이즈 최종 판정

[CI479](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41976283599), head `448f9aa4eaf704c054bdc71d5a04aa14ac93c7ac`는 필수 39 jobs 성공·PR의 배포 파일 준비 1정상 생략으로 완료했다. native-compose 100/100·작성 화면 34/34가 통과했다. 최종 PNG 12개와 DOM·치수의 manifest를 검증하고 T01/T02/T02A/T03/T04와 1920/1366/360을 대조했다. artifact `13393110009`, 25,096,053 bytes, SHA256 `f7e5ae1bc94ac24b8b131889ee987191aa14fe28c32b34faec3b485c90d8b4c9`. 원격 tree `8d03e062ce2f573ae0d3c5f989832beb8e091a71`은 로컬 최종 제품과 일치했다. 이 판정은 뒤의 2페이즈 코드 성공을 대신하지 않는다.

<a id="phase2-evidence"></a>

## 2페이즈 기준과 완료 조건

2026-11-05 사용자 요청으로 PR #123에서 [ST-P2](../docs/specs/shared-tools.md#tools-redesign-v2-phase2-20261105)를 이어 구현한다. 기준은 위 CI479 head, 공통 계약 `92e9bf9`, 합성 fixture `aff087b`다. Python 3.11.17·기존 고정 의존성·공식 0.11.3 wheel과 Node 22를 재사용한다. 브라우저의 로컬 OS 기동 제한은 그대로이며 실제 브라우저 판정은 CI에서 한다. 실제 서비스·사내 토큰·사용자 DB는 사용하지 않는다.

| ID | 확인할 행동 |
|---|---|
| P2-01 | 관리자 연결 저장·조회, 기존 Native 암호화 재사용·원본 보존, 토큰 비노출 |
| P2-02 | 직접 Native 자격 변경 감지·전체 설정 CAS·다른 계정 시험 격리 |
| P2-03 | 저장/조회 미실행, 명시적 저장본 시험·정확한 코드/설정·예약 인자 바인딩 |
| P2-04 | 중복 시험 1회 실행·실행 중 재전송·시간/크기 한도·실패/중단 이력 |
| P2-05 | 입력 schema·실제 결과 path/필드/URL 검사, 0건·부분·형식 오류 구분 |
| P2-06 | 현재 성공 시험과 그룹/근거로 사용 설정, 변경 후 이전 시험 차단 |
| P2-07 | 수정본과 사용본 분리·v1/v2·동일 내용 재확인, 읽기 전용 이력 |
| P2-08 | 그룹 revision 충돌·권한 회수·사용 중지 지속·명시 재개·장애 중 축소 |
| P2-09 | T02B/T05/T05A~E/T06 상태·실제 서버 왕복·1920/1366/360·기존 흐름 회귀 |
| P2-10 | 새 3모듈 배포·이전 1페이즈 프로그램 Apply/Restore·누락 배포 거부 |

### 구현 중 판단

- Native 개인 설정 spec 조회가 후보 코드를 로드할 수 있어 새 도구의 설정용 Native identity는 고정 코드·빈 업무 함수 목록으로 둔다. 실제 시험은 정확한 Work 저장본 코드를 worker에 전달한다. 기존 관리 도구·10함수 실행 계약은 확장하지 않는다.
- worker는 기존 관리자 코드 신뢰 수준이며 sandbox가 아니다. 자동 requirements 설치를 금지하고 제한 시간/출력·응답 비밀 제거를 적용한다. 0건 시험의 표시 필드 미확인과 `complete`의 수신 형식 검사 의미를 명시했다.
- 기존 계정 토큰은 암호화 저장소를 재사용한다. Native 암호문 blob의 비공개 지문으로 직접 변경을 감지하며 전체 settings CAS로 다른 변경을 덮지 않는다. 별도 자격 저장소·시스템 매핑·타 계정 대행은 만들지 않는다.
- 시험은 worker 완료까지 제한 시간 안에 await한다. 먼저 running을 기록해 같은 요청 재전송은 해당 기록을 재사용한다. 브라우저 fixture의 요청 event loop를 바꾸거나 별도 상시 작업 서버를 만들지 않는다.

### 실행 결과

구현·통합 검증 중이다. 이후 실제 실행 결과와 최초 실패·보완을 이 절에 추가한다. 최종 원격 head·필수 CI·화면 판정은 [PR #123](https://github.com/knadalkim-a11y/team-agent-poc/pull/123)에 연결한다.


### 2페이즈 최초 검토와 보완

- 독립 서비스 검토에서 Native 접근 회수 후 시험 자료 표시, 마지막 권한 확인 중 자격 변경, 활성화 실패 뒤 Native 그룹 확대 잔존, 그룹 축소 실패의 성공 처리, 근거의 비밀 형식 누락, 잘못된 URL 포트 수락을 재현했다. 현재 접근에 따른 근거 숨김·최종 자격 재확인·정확한 Native 상태 비교 복구·실패 전파·근거/URL 검사를 보완했고 동일 재현 6개가 통과했다. 복구 중 다른 변경이 있으면 덮지 않고 동기화 필요 실패를 남긴다.
- 총괄 검토에서 실제 토큰 원문만 쓴 확인 근거와 연결 저장 영수증의 개인 시험 복제/이전 응답 재생 경계를 추가로 확인했다. 현재 계정 토큰 대조로 근거를 거부하고 연결 영수증에는 비밀 아닌 값과 기본 수정본만 보관하며 재전송 응답은 현재 권한으로 구성한다.
- 화면 검토에서 공통 전송기의 요청 캐시 키에 연결 토큰이 포함될 수 있음을 확인해 연결 저장은 불투명 request_id만 사용한다. 연결·그룹 저장 응답을 기다리는 동안 새로 입력한 값이 닫히며 사라지는 2개 재현을 먼저 실패시킨 뒤 보낸 값과 이후 편집을 구분해 보존했다. 관련 작성·실행 Node 442/442 통과했다.
- 통합 Node services 10개 스크립트가 모두 종료 0이었다. 최초 실행 명령은 tests/ 접두사를 누락해 모듈을 찾지 못했고 시험을 실행하지 않았다. 명령 경로를 바로잡은 결과 TAP 675/675·별도 assertion 2개 통과, 이후 저장 중 편집 보존 2개를 추가한 관련 442/442가 통과했다. 최초 명령 로그와 후속 결과는 dist/tools-phase2-verification에서 구분한다.
- 이전 1페이즈 프로그램에서 새 3모듈을 적용하고 Restore로 정확한 이전 파일 tree를 복원하는 검사와 incoming 모듈별 누락 거부가 통과했다. 원래 프로그램의 검증 목록·사용자 자료는 바꾸지 않는다.


### 2페이즈 통합 로컬 결과

- UI 통합 `87ee76a`, 서버 통합 `bbd110d`, Native 브라우저 검사 `304416a`에서 확인했다. Python 관련 9모듈 279개 중 278통과·실제 frontend 산출물이 필요한 branding 1건너뜀이다. 신규 lifecycle 18개, 기존 draft/AST 44개, operations 55개, workspace 85개를 포함한다. 프로그램 복원·누락 거부 3개도 통과했다. 이후 삭제된 그룹의 사용 재개를 막는 최소 후속과 lifecycle 1개가 추가돼 담당자 19/19를 통과했다.
- 최종 관련 Node 작성·실행 443/443, 앞서 통과한 나머지 services 235개와 별도 assertion 2개를 보존했다. UI는 실제0건과 현재 접근상 숨긴 결과를 구분하며 숨김 응답에 개인 입력/근거 캐시도 비운다. T02B/T05A의 공통 간격·제목·모서리를 고정판과 대조했다. 실제 제품 렌더 판정은 CI에서 한다.
- 공식 wheel의 실제 Native 계정/암호화 저장과 loader/binder 기반 child 시험은 최초 11/11(37.723초)와 후속 3개를 각각 통과했다. 후속은 carrier 변경 경쟁, 마지막 권한 대기 중 PAT 교체, 실제 WorkflowService→Native 설정→child→2건 trial→v1이다. 14개 전체를 한 번에 실행했다고 합산하지 않는다. 단위 child fixture는 고정 wheel의 loader/binder 함수를 추출하므로 전체 설치 import 검증과 구분한다.
- 전체 설치 Open WebUI의 import·계정·Native 설정·30초 worker를 그대로 쓰는 API smoke를 기존 실제 CLI CI에 추가했다. 합성 fixture로 2건·실제 저장/재조회·응답/로그 토큰 비노출을 검사한다. 로컬에서는 미실행이며 최종 Complete Native product 결과가 이 경계의 증거다.
- 브라우저 새 5흐름은 실제 HTTP/service/SQLite와 합성 Native 경계로 검사한다. 연결 복귀, 시험 성공/실패/0건/부분/unknown, v1/v2·그룹·중지, 중복/이전 시험 차단, 권한 회수·지연 응답과 Figma 상태별/3폭 캡처를 포함한다. 로컬은 구문·합성 adapter/service smoke만 통과했으며 실제 브라우저는 CI 대상이다.
- 시험 ID 감사는 기존 1,332·통합 1,685개에서 오류 0, 문서 35개·링크 2,906개 오류/검토 후보 0, diff 검사 통과했다. 최종 후속 head에서 ID 감사·필수 CI를 다시 판정한다.


### CI480 최초 통합 결과

[CI480](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41987460942), 원격 head `cc28c7b93ffe4efb4952811ebbe2feb9e89ed72c`·tree `966e9d8d40ead8c05943ce3e64c02027c30f31c0`는 로컬 `dc87350`과 동일한 제품이다. 최종 40 jobs 중 35성공·3실패·1취소·1정상 생략이었다. 실패는 Complete Native product, native-compose와 이를 집계한 Ubuntu Delivery checks이며 Windows 집계는 취소됐다. 첫 실패를 보존하고 수정 head로 재판정한다.

- 새 `test_ees_tool_native.py`는 Ubuntu 14/14(22.802초), Windows 14/14(33.189초)로 실제 전체 실행 통과했다. 기존 Native 계정·암호화·CAS와 추출 loader/binder child 경계를 검증했다.
- 전체 설치 제품은 기존 UI 두 흐름과 새 수정본·Native 연결 저장 뒤 실제 worker 시험에서 `unknown/tool_trial_worker_failed`로 실패했다. 약 6초이며 30초 제한 초과는 아니다. 원문 예외를 폐기하는 기존 보호 때문에 실패 단계는 미확정이었다. socket 이름 가림 가설은 실제 wheel 구조에서 반증했고, 공식 함수의 future annotations를 단위 fixture에 추가한 통합 1개도 통과해 원인이 아니었다.
- 고정 단계 오류코드와 합성 fixture 전용 CI 실패 진단을 추가해 실제 설치 환경에서 원인을 구분한다. 생산 worker의 stdout/stderr·원문 예외 비공개는 유지하며 진단 성공으로 원래 시험 실패를 덮지 않는다. native-compose의 개별 실패·화면 관찰과 후속 결과는 아래에 추가한다.


CI480 후속 분리: 새 2페이즈 브라우저 5개와 작성 모듈 39개는 모두 통과했다. native-compose 실패는 기존 `test_navigation_v2_geometry_modes_categories_global_tools_and_draft` 1개이며 개별 원인을 확인한다. 전체 worker 후속 `1dd211a`는 원인 해결이 아닌 안전한 단계 진단 변경이다. 이 변경의 Native 15개 전체는 실제 공식 wheel 지정으로 68.279초에 통과했고, 처음 wheel 경로 누락으로 15개를 건너뛴 실행과 구분한다. 합성 진단 메시지에 시험 PAT·WEBUI_SECRET_KEY를 함께 넣어 모두 제거되는 것을 확인했다. 고정 loader/binder fixture에는 원본의 future annotations도 보존한다.


CI480 native-compose 최종은 105개 중 104통과·기존 motion 1실패였다. 1920→1366 전환에서 자동 접기 flag는 이미 true지만 축소 초반의 너비가 200px보다 커 공통 open_sidebar helper가 열린 상태로 오인했다. 그 뒤 애니메이션 완료를 기다려 접힌 제목 높이 [0,0,0]을 읽었다. 실패 PNG/DOM의 실제 56px·펼치기 단추와 일치했다. `ced97c5`는 source sidebar의 compact=false도 요구해 실제 토글을 거치게 하며 기존 치수·hit-test·단언·시간 제한을 유지한다. 새 브라우저 검증 성공을 대신하지 않는다.

CI480 artifact는 26,876,710 bytes, SHA256 `807248628a8196afab7bcbe44e2c11aa0425a9cd59d16ab6880a86e3a20218a7`이고 ZIP CRC·내부 증거 589개 size/SHA256가 일치했다. PNG 316개 중 2페이즈 25개다. 연결 복귀 6건 scroll delta0, T02B/T05A의 1920/1366/360에서 footerGap20px·버튼 hit=true·한 줄·잘림 없음, T05/T06 가로 넘침0을 확인했다. 실제 화면 대조에서 T06 사용 가능 배지의 상태 색상 누락을 발견해 공통 상태 태그 매핑을 보완한다.


실제 캡처 대조 후 `86c0a6c`는 공통 available 색상을 쓰는 사용 가능 배지, 평문 형태의 확인 근거 textarea 자동 높이(최대180px 뒤 스크롤), 안내 글자 크기·원본 결과 펼침의 회색 표현, 연결 전 버튼의 세로 배치를 보완했다. 공통 패널·탭 토큰과 가시 포커스는 유지한다. T05C의 예시 401 문구는 실제 HTTP 상태가 확인되지 않았으므로 추가하지 않았고, 실제 실패 안내·입력 보존·연결 설정/재시험·사용 차단을 확인했다. 수정 후 실제 근거 가독성과 상태 색상은 다음 CI 캡처로 재검한다.


실행 환경 고정 추가 검토: 기존 Native 환경 stamp는 호스트/배포 식별·Native/Python·일부 의존성 버전만 포함해 같은 ees.14의 작성 도구 실행 코드가 바뀌어도 이전 시험을 유지할 수 있었다. `2571808`은 작성 도구만 native/worker/lifecycle/static-check 네 배포 파일의 bytes hash를 함께 확인한다. 읽기 실패는 거부하며 기본 제공 도구의 기존 환경 stamp는 유지한다. 실제 Native/SQLite 회귀에서 네 파일 각각 변경·파일 누락·이전 시험/활성화/재개 차단, 재시험 후 v1·중지 유지와 명시 재개를 확인했다(신규1개 5.833초, Native전체16개 67.172초 통과). 내용이 같은 재확인은 불변 버전을 고치지 않고 별도 확인 환경 기록을 갱신한다.


### CI484 원인 확인과 실제 로더 보완

[CI484](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/41990693577), head `cdfa7c5bba7bccb8e3e05d023a78a0c161d5048a`에서 안전 진단으로 실제 원인을 확인했다. import는 성공했고 `tool_trial_worker_load_failed`의 원인은 배포된 `ees_asset_guard.protected`→`_active_guard`의 HTTP503 `conditional_write_unavailable`이었다. 별도 시험 프로세스에는 기존 서버 자산 보호 context가 없었다. 원문 비밀값을 노출하지 않는 합성 진단의 프레임으로 이 경계를 확정했다.

수정 `ec60d96`은 보호를 가짜 초기화하거나 __wrapped__로 우회하지 않는다. 고정 공식 loader는 content=None일 때만 Native DB 조회·소스 정규화 쓰기를 하므로, 전용 decorator에서 active guard가 있으면 기존 잠금을 그대로 쓰고 guard가 없는 별도 프로세스는 명시 str content 경로만 허용한다. closing guard, content 생략/None/비문자열, 캐시, Native table writer는 계속 차단한다. builder의 실제 장식과 생산 guard 원본을 child fixture에도 포함해 이전 단위 fixture의 누락을 해소했다.

환경 고정은 `710f4de`에서 자산 보호 파일까지 5개 bytes hash로 확장했다. Native17개 전체 59.141초, guard20개 1.356초, builder 장식·기존 Native DB정규화/호출자 잠금3개 4.474초 통과했다. 실제 전체 제품의 성공과 수정 UI는 다음 통합 head CI에서 판정하며 진단 성공을 기능 성공으로 대신하지 않는다.


CI484 native-compose에서는 기존 motion 6/6이 통과해 앞선 준비 경계를 해소했다. 새 근거 가독성 단언이 360px에서 실패했다: T05A textarea width294px·clientHeight21px·scrollHeight42px로 2줄 중 한 줄만 보였다. 폭 변경은 paint/input을 발생시키지 않아 기존 자동 높이가 유지된 제품 결함이다. 작성39개 중38통과, 신규5개 중4통과이며 왕복 검사는 이 근거 단계에서 중단됐다. 기존 가독성 단언을 유지하고 실제 폭 변경에도 높이를 재계산하도록 보완한다.

공통 자산 보호 변경의 총괄 재검은 guard20개와 branding33개 통과·현재 frontend 산출물 필요1생략이었다. 최초 asset-native 실행은 필수 환경 변수를 지정하지 않아64개 모두 건너뛰었으므로 성공으로 집계하지 않는다. 공식 wheel과 EES_REQUIRE_ASSET_NATIVE=1을 지정한 실제64개를 별도로 재검한다.


CI484 최종은 40 jobs 중 35성공·3실패·Windows 집계1취소·출하1정상 생략이다. Native contracts는 Ubuntu15/15(26.680초)·Windows15/15(43.265초) 통과했다. artifact 26,614,799 bytes·SHA256 `2e6a6cd0a0b8c4dc1afed1385dd5fcbdc0a289c63b062dd1d8aa4764f0059bad`, 증거580개 size/SHA·PNG313개를 검증했다. 연결 복귀6건 scroll delta0, T02B6화면과 T05A1920/1366은 정상이며 T05A360 실패 후 T06 이후는 이번 실행에서 미도달이다.

`6f5e473`은 열린 확인 근거 입력칸의 폭만 단일 ResizeObserver로 감지해 높이를 다시 계산한다. 높이 변경 자체는 재계산하지 않고 요소 교체·닫기·초기화 시 해제한다. 입력 없이 폭430→294px 변경·height42px·관찰 중복/늦은 callback/해제 회귀를 포함해 작성 Node311/311 통과했다. 실제3폭 가독성 단언은 그대로 유지한다.

자산 보호 수정의 실제 공식 Native64개 전체는 157.718초에 통과했다. 추가 동시 변경 검토에서는 set_groups 첫 identity 조회 뒤 await 중 실제 Native AccessGrants.grant_access가 완료되면 authored 저장이 그 그룹을 지우는 lost update를 재현했다(2.954초). `f3ef6be`는 save_connection/set_groups 전체를 기존 guard_operation으로 보호해 첫 읽기부터 commit·최종 확인까지 같은 TaskGuard 안에 둔다. 새 잠금은 만들지 않는다. 실제 다른 task의 Native writer 대기→두 변경 보존→오래된 identity 거부, 개인 설정 보존·중첩 재진입2개(4.831초) 및 Native19개 전체(58.609초)를 통과했다.


최신 main `c01bf09`를 포함한 로컬 `aa2404a`에서 Node작성/실행444개(6.604초), Native19개(72.068초), guard20개(1.145초), ID1692개·문서35개/링크2914개 오류0을 확인했다. 감사 명령의 필수 output 인자 및 파일/폴더 혼동으로 준비 명령2회가 실패했으며 실제 감사는 올바른 폴더로 완료됐다. 원격 게시 직전 병합 검토 세션이 같은 PR을 `54e8e2e`로 전진시켜 expected head 보호가 갱신을 막았다. 새 원격의 변경은 검토 문서뿐이며 제품 추가 수정은 없음을 대조하고 merge로 양쪽 기록과 개발 후속을 보존했다. 최종 head의 전체 CI/화면 결과는 PR 본문과 Checks에서 판정한다.


<a id="phase3-evidence"></a>

## 3페이즈 · 업무절차 연결·실행

2026-11-05 KST. 사용자 요청에 따라 main `16cf557`에서 시작했다. 이전 2페이즈 CI487 head `fdf82c7`과 main의 tree `8ea725d9`가 같고 필수39개·브라우저105개가 성공했다. 실제 제품 worker2건/5.999초·자격 비노출, 최종 화면8장 및 증거589개 해시 검증을 완료한 상태다. 이전 실패 기록은 위에 보존한다.

3페이즈 시작 시 열린 관련 PR은 없었다. 기존 AGENTS는 main과 bytes가 같음을 확인했고 현재기준·ST-P2 보존조건·shared catalog/회차/실행·Figma T06A~T09/O15 화면을 확인했다. [ST-P3 계약](../docs/specs/shared-tools.md#tools-redesign-v2-phase3-20261105)과 공통 fixture `tests/fixtures/tools_phase3_contract.json`을 `cc66c23`에 정의했다. Figma는 읽기만 하며 저장/게시·기존 진행·사람 판정의 구분을 유지한다.

초기 조사에서 작성 도구의 Optional/float/bool/primitive list/typed enum이 기존 shared 질문 생성에서 자료형을 잃을 수 있음을 확인했다. 작성 도구에만 원래 property schema를 보존하고 실제 고정 사용본 schema로 검사하는 경계를 둔다. 기존 Native의 일반 사용자 UserValves 조회/저장 경로는 실제 고정 Native HTTP handlers·SQLite에서 성공했고 다른 사용자 PAT·inert identity는 보존됐다. 이는 실제 로그인/브라우저 검증과 구분한다. 제품·통합 검사는 구현 후 결과를 아래에 기록한다.

구현 중 독립 검토에서 다음을 재현하고 보완했다. required를 비어 있지 않음으로 처리하는 화면 오류는 인자 존재와 값 검사를 나누고, 일반 목록은 한 줄에 한 항목 입력으로 제공한다. 첫 실행 질문의 기본값은 아직 사용자가 편집하지 않은 authored 필드에만 적용한다. Native 마지막 비동기 읽기 중 Work 사용 중지·버전 변경과 완료 뒤 heartbeat 정리 중 개인 PAT 변경은 최종 Native 재조회와 동기 Work 검사 직후 저장하도록 고쳤다. Native 역할·그룹 관측도 실행 메타데이터에 결합한다. timeout/권한 회수 뒤 불확실한 원문은 붙이지 않고 기존 기록을 보존하며 자동 재실행하지 않는다.

로컬 중간 검사: 기존 서버 lifecycle/operations/workspace 159개 통과, Native 기존19개·최초 신규10개 통과. `node --test tests/test_*.cjs`는 첫 통합에서736/736 통과했다(후속 기본값 수정은 별도 검사 대상). durable execution은 신규3개 포함40개 중38통과·실제 wheel 환경2생략/6.319초였다. 최초 검사에서 과거 독립 service에 shared_tools가 없는데 managed 직접 호출까지 새 dispatcher를 검사한 오류를 발견해 shared_tool_id가 있는 경우로 한정하고 재검했다. 합성 브라우저 fixture를 실제 service/SQLite에 연결한5묶음 smoke는 공동 실행/whole-job 판정/재실행 이력/버전수락·중지/0건·partial/unknown·중복/권한회수를 통과했다. 이는 실제 source-built 브라우저·전체 Native 제품 실행을 대신하지 않으며 그 결과는 최종 CI에서 기록한다.

명세 밖 선택: 새 연결의 기본 사람 판정은 유지하되 기존 절차에서 명시적으로 정한 자동 판정·completion까지 강제 변경하지 않는다. 기존 execution.calls도 같은 authored 버전·권한 검사를 거치지만 새 여러 도구 연결 UI를 만들지는 않는다. 미완성 게시 허용은 유지하고 실제 실행 시 필요한 값을 검사한다. 최종 통합 결과와 PR은 후속 기록으로 관리한다.

통합 head 로컬 검사: 전체 Node739/739(8.444초), 고정 공식 wheel과 `EES_REQUIRE_ASSET_NATIVE=1`, EncodingWarning 오류 모드에서 작성 도구 Native12/12(38.421초), builder34개 중33통과/실제 소스 frontend가 필요한1개생략(4.774초), pre-draft/P1/P2 Apply→Restore3/3(1.240초), 시험 ID1734개/기존1332개분류오류0, 문서35파일2930링크오류0. 새 P2 Restore 테스트의 처음 실패는 후보 ZIP을 바꾼 뒤에도 바꾸기 전 fixture 전체 tree와 비교한 시험 오류였다. 새 ZIP 저장 직후 기준을 잡고 Apply가 프로그램을 전혀 변경하지 않음을 다시 검증해 통과했다. 최종 사용자 입력 근거에는 원제출 arguments와 기본값 적용 effective_arguments를 함께 보존하고 권한 회수 시 둘 다 숨긴다. 수동 목록 수정으로 파생한 근거에도 같은 metadata를 보존한다.

### 최초 전체 CI489와 시험 준비 보완

[CI489](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/42005620218), [PR #125](https://github.com/knadalkim-a11y/team-agent-poc/pull/125), 원격 head `dece1b0` / 로컬 `0fce2b2`의 tree `75a8914a` 일치를 확인했다. 전체40 job은33성공·5실패(실제4묶음과최종gate)·1취소·출하1정상생략이었다. Windows/Linux 실행 계약·서비스·복원 등 성공을 보존한다.

- 실제 Native 제품은 새 작성 도구 시험·사용v1·미시험r2 저장 뒤 새 공장 준비에서 `revision_conflict`로 중단됐다. 시험 helper의 새 객체 `expected_revision:0` 누락이었다. 명시 revision override를 보존하며 보완했다. 남은 준비 코드의 과거 `sharing` 그룹 요청/기대도 현재 공장·시스템 scope access only 계약에 맞췄다. 실제 service/SQLite에서 같은 helper를 사용해 factory/access/create/save/validate/publish/start와 일반 사용자의 동일 run 조회까지 확인했다. 실제 제품의 중앙 채팅 후속 검사는 이 실패 때문에 미실행이다.
- Windows/Linux platform의 유일한 원인은 새 선택창이 재사용한 기존 `88f2f.svg`를 독립 CSS 캐시 검사 목록에서 누락한 것이다. 제품 builder는 올바른 해시 URL을 만들고 있었다. 고정 목록만 보완했고 CI489의 실제 frontend artifact(sha256 `5d203a0e81debc0bc5ff75aad7aab1128e58ee29d87476524d17981222c0b50b`)와 현재 UI·공식 wheel로 해당 시험1/1을29.396초에 통과했다. 과거 frontend로 먼저 시도한 검사는 provenance 불일치로 차단됐으며 성공으로 세지 않았다.
- 실제 native-compose는110개 중108개 통과했다. 기존105개는 전부 통과, 신규5개 중3개 통과다. 작성 흐름은 미연결 작업을 errors로 기대했으나 기존 계약은 errors[]+작업별 경고·게시 허용이었다. 정확한 job-0 경고를 검사하도록 보완하고 기존 미연결 실제 실행 차단 회귀도 통과했다. 공동 시작 흐름은 서비스용 일반 사용자 객체에 Native 세션 permissions가 없어 Navbar에서 `undefined.chat`으로 실패했다. 기존 정식 세션 fixture를 복사하고 사용자 id/role=user 및 채팅 소유자를 맞췄다. 콘솔 오류 검사·제품 권한은 완화하지 않았다.
- Native-compose ZIP sha256 `92cfb7075dccba307fbe8dc3a39e990db0fccdc50582889dd3dc676da38e4675`, manifest602파일의 크기·SHA와PNG326개를 확인했다. 신규6장의1920 화면 중 부분 판정·사용 중지 화면 원본을 직접 대조했다. 정상 T06A/T07/O15의3폭은 앞단 실패로 미생성이므로 시각 완료가 아니다. FullNative ZIP sha256 `90383006f607ca0f024810a51fe07cce854811fbe84d1f0e98b7ee2457ec9c84`의84개 파일·PNG36개도 일치했다.

보완은 시험 코드 `65a8d56`, `f3b023f`, `7789a4e`이며 제품 코드 변경은 없다. 최초 실패는 이 기록에 보존하고 다음 head의 전체 CI와 실제 화면으로 최종 판정한다. 최종 head·CI·화면 증거와 병합 여부는 PR #125 본문/Checks를 최신 원본으로 삼는다. 사내 배포는 미실행이다.

CI489 원본 `tools-phase3-unknown-single-dispatch-1920.png`를 직접 검토하면서 현재 unknown/blocked 카드의 ‘결과 미확인’ 상태 문구가 두 번 붙는 표시 오류를 확인했다. `ea89d38`은 판정할 수 없는 현재 attempt의 비활성 판정 자리만 비우고 오른쪽 상태를 한 번 유지한다. 정상 판정 단추와 과거 실행 표시를 보존하며 관련3개 Node 검사를 통과했다. 이 작은 제품 표시 수정까지 최종 head에 포함하므로 진행 중인 CI490은 대체하고 새 head의 전체 결과로 판정한다.
