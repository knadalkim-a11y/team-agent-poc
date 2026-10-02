# EES Work 기존 WebUI 통합 작업 지시

<a id="restructure-step0b-20261001"></a>

## EES Work 재구성 · Step 0-B 기본 계약 · 2026-10-01

**현재 합의:** 아래 7개 기본 계약은 Step 0-A 조사 후 사용자가 정한 후속 기준이다. 데이터와 업무의 의미를 정한 것이며 **상세 DB 구조·API·공유 정책·서버의 사용자 확정 방식까지 확정한 설계는 아니다.** 기존 조사의 코드 근거와 제약은 [Step 0-A](#restructure-step0a-20261001)에 보존한다. 당시 미정 항목 중 아래에서 정한 의미만 갱신하며, 과거 조사·실패·검증 결과를 새 구현 결과로 바꾸지 않는다.

후속 작업의 시작점은 조사 main `55832bad328cdfb91c1c284749f7959dd664176c`, [Draft PR #73](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)의 문서 head `d5b1df77dd5fe436a7d54b8b44a532e39b2dbed5`다. Step 0-A 전체 조사를 반복하지 않고 이번 기본 계약과 직접 충돌하는 지점만 연결한다. 이번 요청으로 Step 0-A의 환경 보완 금지는 **최소 검증환경 준비와 기존 Native UI 시험 harness 결함 보완**에 한정하여 확대되었다. 기본 문서 반영과 그 검증 준비 외 제품 코드·업무 저장 구조·Figma·데모 자산·사내 설정은 변경하지 않는다. 환경 준비나 시험 보완의 실제 결과는 [STATUS](../../STATUS.md)와 [이번 평가 기록](../../../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001)에서 별도로 판정한다.

### 확정한 기본 계약과 현재 코드의 차이

아래 짧은 Python 파일명은 `agent-pack/skills/ees-work-demo/scripts/` 아래며, 근거 행은 위 조사 main 기준이다. “필요 변경”은 후속 설계·구현의 대상이지 이번 단계에 구현했다는 뜻이 아니다.

| 기본 계약 | 확정된 의미 | 현재 근거와 필요한 후속 변경 |
|---|---|---|
| 1. 편집 초안과 게시 버전 | 편집 중 초안과 게시 버전을 구분한다. 게시 버전을 보존하고 진행 건은 시작할 때 선택한 게시 버전을 참조한다. 이후 편집·게시로 그 진행 건의 기준이나 과거 게시본을 덮어쓰지 않는다. | `ees_workflow_authoring.py:_write_publication(515)`은 현재 catalog JSON을 덮어쓰고 전역 version을 증가시킨다. P별 초안/검사와 `ees_workflow.py:_new_case(358)`의 정의 snapshot은 재사용할 수 있으나 모든 게시 버전 보존·선택 참조는 추가 설계가 필요하다. 테이블·버전 식별자·API 형태는 아직 정하지 않는다. |
| 2. 진행 건과 개인 대화 | 진행 건과 개인 대화를 별개 대상으로 취급한다. 선택한 탭·작업 같은 개인 화면 상태는 공동 업무 상태와 분리한다. 공동 업무 권한과 대화 연결의 상세 규칙은 미정이다. | `ees_workflow.py:_chat(97),_case(129)`은 개인 소유를 검사하고 `case_chat`은 사용자·대화별 한 case만 허용한다. `selected_id` 변경도 case revision을 갱신한다. 이 소유·연결·선택 구조는 새 계약과 대조해 수정할 대상이며, owner 조건 삭제나 개인 대화 공유로 대체하지 않는다. |
| 3. 반복 업무 설정과 이번 진행 입력 | 반복 사용할 업무 설정과 이번 진행 건의 입력을 구분한다. 개인·시스템·공장별 공유 범위는 미정이다. PAT와 비밀값은 Native 개인 설정에서만 취급하며 업무 입력·실행 기록으로 복사하지 않는다. | 현재 P `execution_inputs` schema, case/run 입력, Native Valves/UserValves는 있으나 일반 업무 설정의 범위·상속·이력 모델은 없다. `ees_workflow_native.py:invoke(451)`의 개인 연결 재사용을 유지하면서 비밀값이 입력·snapshot·결과·오류에 복제되지 않는 경계를 검증해야 한다. 기존 public-key 검사나 결과 정규화만으로 모든 입력의 비밀정보 보호가 보장된다고 간주하지 않는다. |
| 4. 같은 진행 건의 입력 보완과 재실행 | 같은 진행 건 안에서 입력을 보완하고 재실행할 수 있도록 설계한다. 매 시도의 입력·도구 참조·결과를 별도로 보존한다. 과거 결과를 덮어쓰지 않으며, 그 결과에 의존한 후속 작업의 완료 상태를 검토 없이 그대로 유지하지 않는다. | `ees_workflow.py:627–633`은 run 수락 후 기존 입력 변경을 막고 `ees_workflow_execution.py:plan(227),_control(454)`도 저장된 입력 변경을 제한한다. “입력 변경마다 새 case”는 현재 제약이며 새 목표가 아니다. 호출 attempt/history·요청 receipt·legacy `_invalidate(396)`의 의존성 추적을 검토하되, 실제 runtime의 영향받는 후속 상태·재검토 방식·재사용할 결과를 상세 설계해야 한다. UNKNOWN 차단을 우회하는 재실행 승인은 아니다. |
| 5. 도구 성공과 업무 완료 | 도구 호출 성공은 업무 완료와 다르다. 필수 사람 확인 전에는 완료 처리하지 않는다. 실패·부분 결과·결과 불명을 성공으로 합치지 않는다. | `ees_workflow_contract.py:evaluate_completion(390),evaluate_final(475)`과 `ees_workflow_execution.py:_control(454),_require_resolved(444),_late(826)`의 판정·사람 확인·UNKNOWN/늦은 결과 보존을 재사용한다. 현재 `observed_v1`은 제한된 조회를 관찰 완료로 판정할 수 있으므로 transport/status뿐 아니라 completeness·scope_complete·사람 확인·최종 업무 조건을 함께 검토한다. CR별 판정과 UNKNOWN 해소 규칙은 별도 확정 대상이다. |
| 6. AI 제안과 사용자 확정 | AI 제안·초안과 저장·게시·실행·확정을 구분한다. 버튼을 숨기거나 요청에 `source=panel`을 붙이는 것만으로 권한이나 사용자 확정을 보장하지 않는다. 서버가 검증할 확정 경계의 상세 방식은 미정이다. | 입력 제안의 `persisted=false/executed=false`, 별도 authoring save/validate/publish는 기반이 있다. 그러나 `workflow_tool.py:ees_workflow_action(425),ees_execution_action(192)`에는 실제 생성·입력 저장·실행 요청이 남아 있다. UI/Tool 양쪽이 같은 서버 권한·대상·revision·요청 검증을 거치게 설계해야 하며 prompt나 호출 출처 문자열만으로 해결하지 않는다. 패널 전용 처리와 A1 대화의 시작/진행 표현 사이 경계도 이 상세 계약에서 확인한다. |
| 7. 기존 Native 기반 재사용 | Native 인증·기반 모델 호출·GitHub/Jira/Confluence 실제 연동을 재사용한다. 전문 Assistant preset을 제거해도 기반 모델 접속·호출이 끊기지 않게 한다. 새 서버·DB 엔진·범용 실행기를 기본 전제로 추가하지 않는다. | `ees_workflow.py:_production_service(719)`, `ees_workflow_native.py:NativeBridge`, `ees_workflow_model.py:NativeModelAdapter.invoke(149)`를 출발점으로 삼는다. 모델 adapter가 Native Model DB 행과 `app.state.MODELS`를 함께 요구하는 제약은 남아 있다. 전문 preset ID 보존을 강제하거나 기반 연결까지 지우는 대신, 허용된 기반 모델 선택·접근 확인을 별도로 설계한다. 같은 `skills/ees-work-demo` 폴더의 실제 공통 서버를 데모 콘텐츠와 함께 제거하지 않는다. |

이 기본 계약에 맞추기 위해 바꿔야 할 기존 제약을 기능 요구의 축소 근거로 삼지 않는다. 반대로 기본 계약을 상세 구현 승인으로 확대하지 않는다. 계약 변경이 필요하면 **변경 이유·대안·영향**을 제출하고, 데이터 의미·권한·저장 범위·완료 조건을 임의로 바꾸지 않는다.

### 상세 설계에서 남겨 둔 결정

| 결정 영역 | 이번에 확정하지 않은 내용 |
|---|---|
| 저장 구조·API | 게시 버전 식별/보관 구조, case·attempt·업무 설정의 관계, migration 방식, endpoint·payload·오류 계약. 기존 SQLite와 서비스 안에서 가능한 선택지를 먼저 비교한다. |
| 공동 업무·개인 대화 | 공동 진행 건의 참여·역할·조회/수정/실행 권한, 개인 대화와 진행 건의 연결 수·변경 방식, 개인 화면 상태 저장 위치와 사용자별 접근. Native 대화는 자동으로 공동 공개하지 않는다. |
| 설정과 실행 입력 | 개인/시스템/공장별 공유 범위·우선순위·변경권한, 기본값과 이번 입력의 조합, 실행 시 유효값·출처를 고정하는 시점. PAT는 이 공유 모델에 포함하지 않는다. |
| 재실행과 완료 의존성 | 시도의 경계, 변경 입력의 영향 범위, 기존 근거 재사용 조건, 후속 완료의 재검토/무효화/재확정 절차, 진행 중 호출과 중복 요청 처리, UNKNOWN 해소에 필요한 증거·담당·권한. 자동 무효화와 사람 검토 중 하나를 이번에 일괄 확정하지 않는다. |
| 서버의 확정 검증 | AI 제안 대상·revision과 사용자가 확정한 작업/입력의 일치, 저장/게시/실행/완료별 검증, 재전송·동시 변경·권한 회수 처리. UI 위치·버튼 노출·출처 필드는 확정의 증거를 대신하지 않는다. |
| 첫 실제 업무·기존 자료 전환 | Step 0-A의 CR 조건·필수 첨부·송부·미승인 처리·일정 세칙과 과거 절차 사용 중지/기록 열람/내보내기/삭제·복구 범위. 이번 7개 계약만으로 업무 정책이나 사내 삭제 목록을 확정하지 않는다. |

Step 0-A에서 확인한 Figma의 화면 배치·입력 선언·사람 목록 확정 등 결정은 유지하되, 현재 조회본을 영구 고정본으로 취급하지 않는다. 이번에는 `2026-10-01T05:22:11Z`(14:22:11 KST)에 페이지 `832:131`의 metadata만 다시 조회하여 이름 `EES Work · 대화 중심 정리안 10.01`과 기존 6개 frame ID가 같음을 확인했다. 상세 화면·상호작용·스타일 전체가 동일하다고 검증한 것은 아니며 새 스크린샷이나 원본 수정은 없다. 상세 UI 근거는 Step 0-A 조회본을 재사용하고 기본 계약은 이번 사용자 지시를 따른다. 이후 단계 착수·검수 때 관련 화면을 다시 확인하고 스타일 변경·화면 행동 변경·백엔드 계약 변경을 구분한다. 목업의 예시 이름·날짜·건수·성공 결과는 운영 기본 데이터가 아니다.

### 이후 단계의 완료 조건 보완

아래는 [Step 0-A 단계표](#restructure-step0a-20261001)에 대한 현재 보완이다. 아래에 보존된 “Step 0-B 미확정”은 당시 조사 상태이며, 지금은 **7개 기본 계약 확정 / 상세 설계와 Step 1 구현 계약 미확정**으로 구분한다.

| 단계 | 현재 완료·진행 조건 |
|---|---|
| 이번 후속 범위 | 7개 기본 계약과 코드 충돌을 문서에 반영한다. 허용된 최소 환경 준비·기존 Native UI 시험 harness 보완은 원인과 재검 증거로 따로 검증한다. 이 문서 반영만으로 실제 제품 기동·화면·기능 왕복을 PASS 처리하지 않는다. |
| Step 0-B 상세 검토 | 위 미확정 의미를 필요한 수준까지 정하고 Step 1의 삭제/재사용/수정 범위·빈 상태·모델 연결·보존·검증 계약을 전달해야 한다. 전체 향후 기능의 DB/API를 한 번에 확정한 것으로 간주하지 않는다. |
| Step 1 빈 상태 | 별도 구체 지시 후 시작한다. seed 의존/빈 catalog 검증·재등록 경로·기반 LLM/실제 connector 보존을 확인한다. 최소 환경 준비나 문서 통과만으로 시작·병합·배포·자산 삭제를 허용하지 않는다. |
| Step 2 화면 구조 | 새 Figma의 Native 대화/업무 패널 구조를 실제 제품에서 검증하고, 개인 화면 상태·업무 상태·미저장 입력과 첨부를 구분한다. 화면만 바꾸고 기존 case 상태에 섞어 저장하는 것으로 계약 2를 충족했다고 판단하지 않는다. |
| Step 3 절차 작성 | 초안/검사/게시와 보존된 게시 버전, 선택 버전 참조, 동시 수정·현재 권한 및 AI 제안/확정 경계를 검증한다. |
| Step 4 진행·실행 | 반복 설정/이번 입력·시도별 snapshot·같은 case 재실행·후속 완료 재검토·실제 개인 연결·사람 확인·부분/실패/UNKNOWN과 중복 요청을 검증한다. |
| Step 5–7 | 첫 실제 업무는 확정된 도메인 범위만 구현하고 통합 검증·배포 준비를 진행한다. 실제 사내 자산 정리·배포·실환경 확인은 기존 단계표의 별도 승인과 현재 inventory·백업/복구 조건을 유지한다. |

각 구현 단계의 상세 설계→Work 구현/시험→검토 담당 검증→보완/통과 순서는 유지한다. **이번 범위를 마친 뒤 멈추며 Step 1 구현·데모 제거·사내 변경을 자동 시작하지 않는다.**

### Step 0-B 잔여 검증 · 검토 head d0b0aa3 이후

사용자는 위 기본 계약·환경·실제 Native 최소 왕복·Linux 가입/계정 전환 검증을 수용했다. 이번 후속 범위는 다음 세 항목이며 조사·설치를 반복하지 않는다. [잔여 검증 근거](../../../evals/v4-ui-20260930.md#restructure-step0b-residual-20261001)에 관측·가설·수정·재검을 구분한다.

| 대상 | 허용된 보완과 완료 조건 |
|---|---|
| CSS 기대값 | 승인한 아이콘 URL의 원본 SHA256 query 삽입과 그 외 바이트 보존을 독립 검증한다. 잘못된 해시·누락·무관한 변경을 거부하고 고정 원본·RECORD·무관한 파일 검사를 유지한다. 제품 캐시 처리 제거·query 일괄 제거·빌더 반환값 자기검증은 금지한다 |
| Windows 두 실패 | 이전 ees.10 archive hash와 게시 계약 ERROR를 별도 프로세스에서 각1회 실행해 종료/완전 오류를 확보한다. 기존 Windows CI에 앞선 진단·증거 수집을 연결하되 기존 검사·트리거·보호를 유지하고 실패는 실패로 종료한다. upstream·소스 commit·멤버/해시·RECORD·ZIP 정보를 대조하기 전에 해시를 교체하거나 추가하지 않는다. Linux 추정은 Windows 해결 증거가 아니다 |
| 한글 화면 증거 | 기존 artifact의 가입 대기 화면을 실제로 확인하고 환경 글꼴·실제 glyph 로딩·캡처 준비를 구분한다. 시험환경/수집기 결함만 최소 보완하며 제품/디자인 변경이나 이미지 사후 수정으로 증거를 만들지 않는다 |

직접 영향받는 helper 회귀·고정 패키지·앞서 막혔던 Native 업무/대화 통합 검사를 확인한다. 제품 수정이 필요하면 근거와 필요한 범위를 제출하고 해당 제품 변경은 멈춘다. 최종 결과·증거 파일 실체·CI 상태를 확인하여 같은 Draft PR에 반영하고 검토를 기다린다. 병합·Draft 해제·배포·Step 1 권한은 없다.

현재 확인된 결과는 CSS31개 PASS, 실제 CI 한글28 glyph/읽을 수 있는 원본 캡처, Windows 고정 소스 CRLF 변환과 SQLite fixture 미닫힘의 원인 분리다. 원래 패키지 pin을 유지하고 시험용 LF archive/명시적 close를 보완했으며 로컬 관련31개 PASS다. `cddf0eb`의 자동 Windows 지정2개도 PASS이고 원래 pin/전체 source·member·RECORD·ZIP 일치를 확인했다. 전체 run은 후속 검사에서 cancelled이며 위 평가/PR에서 head별로 구분한다. Native 통합의 최초 로컬 고유12PASS/3FAIL/58미실행은 보존하며 직접 helper 후속까지 고유20개13PASS/7FAIL/53미실행이다. **옛 A안 치수 기대, Native 입력 저장 경계, 과거 결과의 완료 집계**는 판정 완화 없이 남겼다. Step 0-B 기본 계약을 바꿀 근거 또는 Step 1 통과로 사용하지 않는다. 검토 담당은 이 세 관측과 최종 CI의 미분류 실패·미완료 범위를 확인하고 별도 Step 1 구현 계약을 전달해야 한다. 최종 CI에서 같은 닫힌 패널/구 select-value 준비 로직이 남은 직접 호출부만 추가 보완했으며 제품/판정 변경으로 확대하지 않는다.

<a id="restructure-step0a-20261001"></a>

## EES Work 재구성 · Step 0-A 조사 · 2026-10-01

**현재 기준과 범위:** 이 절은 10-01 사용자 요청과 실제 main·Figma 조회에 근거한다. 아래 09-30 V4와 이전 기록은 당시 기준·증거로 보존하며 새 구현 기준으로 우선하지 않는다. 이번 변경은 조사·최소 검증환경 확인·관리 문서·검증 증거·커밋/push·Draft PR뿐이다. 제품/시험/배포/CI 코드를 변경하지 않았고 삭제·구현·병합·배포·사내 데이터 변경을 하지 않았다. **백엔드 최종 설계는 미확정**이며 Step 0-B 검토 후 Step 1 계약을 받아야 한다.

기준 main은 `55832bad328cdfb91c1c284749f7959dd664176c`. 기존 로컬은 clean인 `docs/v4-recovery-report-20261001` / `02fbfa502c728714b7437ceb0f7308ac0c9f7f58`; 그대로 두고 main 기반 새 worktree/브랜치 `docs/ees-restructure-step0a-20261001`을 만들었다. 원격 모든 branch와 열린 PR을 확인했으며 동일 재구성 작업은 없었다. 열린 Draft [#72](https://github.com/knadalkim-a11y/team-agent-poc/pull/72)(위 로컬 head, 복구 사용자 보고)와 [#53](https://github.com/knadalkim-a11y/team-agent-poc/pull/53)(`3aadd7279276914fb790fdb496ceb37b223ec737`, 과거 설계)의 AGENTS·STATUS를 읽었다. 둘 다 적층/변경/병합/종료하지 않았다. #72의 최신 복구 보고는 참조하되 새 사내 검사로 취급하지 않는다. 이 조사에 필요한 미병합 제품 코드 의존성은 발견하지 못했다.

**충돌 적용 범위:** 기존 V4 외형 고정, 시연 워크플로우·전문 모델·등록 Skill의 보존/ApplyDemo 안내는 이번 재구성 방향으로 대체한다. 기본 상태는 기존 데모 콘텐츠 없이 시작한다. 그러나 계정·개인 대화·첨부·개인 PAT·기반 LLM 연결·사용자 작성 자산까지 삭제하는 승인은 아니다. 등록 Skill 콘텐츠 제거와 Skill 관리 기능, 모델 preset 제거와 LLM 접속, 절차 콘텐츠 제거와 절차 작성/실행 기능은 각각 분리한다. 폴더 이름이나 파일 길이로 일괄 폐기하지 않는다.

### A. 실제 연결과 변경 대상

아래 짧은 Python 파일명은 별도 표시가 없으면 `agent-pack/skills/ees-work-demo/scripts/` 아래다. 함수·행 번호는 조사 main의 근거 위치이며 시험명은 **후속 영향 범위**, 이번 실행 PASS가 아니다.

| 영역 / 분류 | 실제 파일·함수·연결 | 직접 의존성·삭제 위험 / 영향받는 검사 |
|---|---|---|
| Native 기반 — 재사용 | `scripts/build_ees_webui.py:PATCHES,assemble_work_launcher(582)`가 고정 Open WebUI 0.11.3 wheel의 Native draft/message bridge·main 설치부를 패치. `ees_workflow.py:install(981),_production_service(719)` → 기존 Users/Groups/Chats/Tools 및 DATA_DIR | 별도 웹앱/인증 서버가 아님. Native 로그인·대화·첨부·저장·LLM 호출 보존. `test_ees_branding_build.py,test_ees_webui_customization.py,test_ees_work_routes.py` |
| 화면 배치 — 수정·교체 | `branding/ees/ui/ees-work-view.js:openHost(1017),sizePanel(993)`, `ees-work-launcher.css`, `chat-theme.css` | 현재 중앙 업무/우측 대화의 DOM 장착·폭·overlay를 새 중앙 대화/우측 업무로 변경해야 함. 중복 CSS는 실제 selector 참조를 추적한 뒤 정리. V4/C안 외형 시험은 새 기준으로 교체, Native 입력/포커스 보호 회귀 유지 |
| 대화/상태 controller — 선별 재사용·수정 | `ees-work-launcher.js:request,action(192),stashDraft/restoreDraft(242),ensureChat,selectWork/switchScope(325),captureReference(375)` → `/api/ees-work/state,action` | 사용자/route 세대, 늦은 응답, CAS·request_id, 미저장 입력/첨부 보호 재사용. 현재 선택을 case에 저장하는 제약은 공동화 계약에 따라 변경. `test_ees_work_controller.py,test_ees_v4_drafts.cjs,test_ees_execution_ui.cjs` |
| 절차 작성기 — 화면 교체·서버 재사용 | `ees-work-designer.js:hideWorkspaceContent/renderDesigner(87),authorAction(184),requestAuthoring(269),confirmPublish(329)` → `GET /api/ees-work/authoring`, `POST /api/ees-work/authoring/action` | 현재 Native chat을 숨기고 메모리형 자체 AI 대화를 표시. 새 Native 대화+오른쪽 작성기 연결 필요. P별 저장/검사/게시·초안 cache·충돌 보호는 재사용. `test_ees_work_designer.py,test_ees_work_authoring_ui.cjs,test_ees_work_authoring_account_switch.py` |
| 절차/진행/권한 API — 재사용·계약 수정 | `ees_workflow.py:WorkflowService,_case(129),_new_case(358),_save_case(345),handle_action/_dispatch(576)`; `ees_workflow_authoring.py:authoring_action(525)` | Native 사용자 확인 + `ees-work.sqlite3`. 실제 공통 서버이므로 demo 폴더 전체 삭제 금지. `test_ees_workflow.py,test_ees_work_authoring.py,test_ees_work_authoring_native.py` |
| 공통 실행 — 재사용·필요 확장 | `ees_workflow_execution.py:plan(227),_start(384),process_once(620)` → NativeBridge/NativeModelAdapter → completion/final validator → case history; 기존 app lifespan worker | 영속 실행·호출/재시도·중복/UNKNOWN 보호 유지. 새 서버/범용 실행기를 기본 대안으로 만들 이유 없음. `test_ees_workflow_execution.py,test_ees_workflow_native.py,test_ees_workflow_contract.py` |
| 초기 절차/예시 — 콘텐츠 삭제 + 코드 수정 후보 | `workflow_seed.json`; `ees_workflow_definition.py:_seed(25),_draft_shape_errors(49)`; `WorkflowService.__init__(68)`; `_new_case`, `ees_workflow_view.py:_inputs(92)` | 기존 DB에서도 seed를 먼저 읽으며 첫 DB에 insert. 빈 nodes/tools/skills/sites 거부·common 정책 Skill 강제·us-a/EMS/setup-p 및 db/ap 예시 fallback. seed 파일만 삭제하면 기동/첫 작성이 깨짐. 빈 catalog/선택/작성 계약을 함께 바꿔야 함. workflow/authoring/UI fixture·build 시험 영향 |
| 모의 실행 — 신규 사용 제거 후보 | `ees_workflow.py:_run_job(412)`의 mock/failOnce 및 legacy P/T loop; `ees_workflow_view.py:_finished` | manual/draft 저장·사람 확인까지 함께 제거하면 안 됨. 과거 기록 열람/실행 중지 범위 결정 후 모의 실행 분기만 정리. `test_ees_workflow.py,test_ees_work_v4.py` |
| 실제 연동 — 재사용 | `agent-pack/skills/{github-read,jira-read,confluence-read}/scripts/*_tool.py:Tools._context,_request`; `ees_workflow_native.py:NativeBridge._snapshot(288),approval_action,check(439),invoke(451)` | Native 등록 원본·ACL·개인 UserValves/PAT 재사용. 실제 함수 허용목록·등록 hash 승인·호출 직전 재확인 유지. connector/native/개인 격리 시험 영향 |
| 기반 LLM — 재사용, preset 의존 수정 검토 | `ees_workflow_model.py:NativeModelAdapter.invoke(149)` → Native `generate_chat_completion`; designer의 `/api/models,/api/chat/completions` | 특정 전문 모델 ID는 필수 아님. 그러나 background adapter는 Native Model DB 행과 app.state.MODELS를 둘 다 요구. 모든 preset 제거 후 direct base ID 사용은 미지원 가능성이 있어 별도 계약/검증. `test_ees_workflow_model*.py` |
| 전문 Assistant/합성 조회/WO — 삭제 후보 | `agent-pack/ees-demo.json`, `cross-system-analysis/scripts/specialists_tool.py,demo_data_tool.py`, 전문 prompt·`ees-orchestration-demo.md`, `ems-work-order/scripts/wo_demo_tool.py` | 실제 connector·공통 bootstrap와 구분. Git 제거는 사내 등록 삭제가 아님. `test_ees_demo_assets.py,test_ees_specialists_tool.py,test_ees_demo_data_tool.py,test_wo_demo*` |
| 등록 Skill/지침 — 콘텐츠 정리, 관리 기능 재사용 | `structured-troubleshooting,policy-grounded-answer,confluence-read` SKILL 콘텐츠; `ees_workflow.py:_registered_assets(733)`의 Native Skills 조회 | Skill 이름은 사내 ID/무수정 증거가 아님. 실행 코드·서버 강제 정책·향후 관리 기능은 유지. 등록 Skill 권한/snapshot 표시·authoring 참조 시험 영향 |
| 옛 독립 화면 — 삭제 후보 | `ees_work_demo.py:install`의 `/ees-work-demo/`, 같은 기능의 `ui/index.html,ees-work.js,ees-work.css` | builder WORK_ASSETS/PATCHES가 여전히 배포/설치. 실제 Native 업무 API와 별개. `test_ees_work_demo.py`, build/restore inventory 시험 영향 |
| 패널 bootstrap — 선별 수정·교체 | `cross-system-analysis/ui/work-panel.js` → builder `WORK_BOOTSTRAP` → `/_ees12/ees-work-panel.js` | workflow registry와 분석/설비/WO demo adapter가 공존. 폴더째 삭제하면 실제 업무 패널도 끊김. `test_ees_cooperation_panel.cjs,test_ees_work_panel.py` |
| ApplyDemo — 재등록 경로 폐기/교체, 보호 코드 재사용 검토 | `manage-ees.ps1:ApplyDemo` → `ees_apply_demo.py:main/apply` → `ees_demo_assets.py:load_manifest/apply_assets` → `ees_asset_guard.py` | 현재 manifest가 tool2/3·전문모델3개를 강제. 빈 JSON만으로 재등록 방지 불가. 공통 `ees_workflow` Tool 등록도 함께 묶여 있음. apply/asset guard/Native preservation 시험 영향 |
| 빌드·설치·업데이트·복구 — 선별 재사용·목록 수정 | `build_ees_webui.py:WORK_ASSETS/WORK_FILES/LEGACY_WORK_FILES/WORK_FILES_V6/V9/V11`; `build_demo_bundle.py:included_source`; `ees_upgrade.py,ees_trial_upgrade.py,ees_webui_customization.py:restore` | bundle은 tracked agent-pack 원본을 포괄 포함. ZIP 포함과 API 등록을 구분. 이전 버전 복원 목록은 남겨야 함. 기존 stop/backup/health/복구 보호를 재구성 이유로 제거하지 않음. build/bundle/customization/upgrade/trial/deploy 검사 영향 |

**핵심 행동의 실제 상태 변경:** 화면의 버튼/Tool 설명과 서버 동작을 구분하여 추적했다.

| 행동 | 실제 진입 → 저장/상태 효과 |
|---|---|
| 입력 저장 | launcher.saveInputs → POST /api/ees-work/action(update_inputs) → case.execution_inputs 또는 legacy job.inputs, case revision/CAS·receipt. 실행하지 않으며 run 수락 후 기존 값 교체는 차단 |
| 문서 초안 저장 | launcher.saveDocument → 같은 action(run, document) → _run_job의 document 저장 + **review** 상태. action 이름 run만 보고 실제 실행/완료로 판정하지 않음 |
| 실행 계획/실행 | POST /execution/plan은 snapshot/hash/계획, /execution/action(start)는 요청·run 수락/영속화. worker가 실제 Native 호출 뒤 call 결과·validator·case history를 갱신. 수락/HTTP200은 완료가 아님 |
| 사람 확인/완료 | legacy manual/draft는 명시 confirm(문서는 먼저 저장), runtime confirm은 human J·선행조건·입력 확인 후 판정. 사람 확인을 AI Tool에서 호출할 수 없게 제한한 기존 경계와 결과 불명 보호 유지 |
| 절차 초안 저장 | POST /authoring/action(save_draft) → process_management.draft 저장·draft_revision 증가·validation 초기화 |
| 게시 전 확인/게시 | validate_draft → 현재 초안/참조/권한의 validation token. publish → 최신 revision/owner/token 재검사·선택 P catalog 병합·version 증가·audit/receipt. 기존 case 정의는 그대로 |
| AI 입력 제안 | workflow_tool.ees_workflow_input_draft → target/revision/schema/ACL 확인 → browser 미저장 입력만 반영, Native 메시지에 제안 receipt. persisted=false/executed=false |
| 현재 연결의 불일치 | generic workflow Tool에는 save_draft/validate_draft/publish 설명이 남아 있지만 /action 서버는 authoring_upgrade_required로 거부. 실제 작성기는 위 /authoring/action 사용. 새 Figma의 전체 절차 AI 초안 생성도 현재 instructions-only 도움과 다름 |

### B. Git 정리와 사내 등록 자산 정리의 분리

아래는 **저장소가 정의하거나 탐색하는 ID**다. 사내 현재 등록 목록·수정 여부·사용 건수는 조회하지 않았다.

| 종류 | 알려진 ID / 식별 방법 | 관리·참조와 사내 적용 전 확인 |
|---|---|---|
| manifest Tool | `ees_specialists,ees_demo_data,ees_workflow`; marker `ees-demo-v1` | 정확한 content/owner/ACL/UserValves/hash·연결 모델·진행/실행 참조 비교. `ees_workflow`는 공통 기능이라 앞의 두 시연 Tool과 같은 폐기 판단 금지 |
| 전문 preset | `ees_demo_ems,ees_demo_apc,ees_demo_fdc` | toolIds=ees_demo_data, 기존 통합 Assistant의 base_model_id 복사. 과거 대화 model ID·변경/사용 여부 확인 |
| 통합 Assistant / WO / 실제 connector | 통합 Assistant는 명시 ID 또는 이름 탐색, WO는 연결목록+marker/source hash, connector는 runtime discovery. 고정 사내 ID 없음 | 이름만으로 삭제/재등록 금지. 통합 preset의 관리 구역 밖 Prompt·toolIds·knowledge/skillIds·기반 모델 연결 분리 |
| Native Skill | repo 이름 `structured-troubleshooting,policy-grounded-answer,confluence-read` | 수동 등록 가이드 대상. ApplyDemo는 Skill을 생성하지 않음. 실제 ID·내용 수정·공유·연결은 사내 inventory 대상 |
| workflow nodes | `setup-p,prep-t,scope-j,infra-t,infra-j,install-t,install-j,db-j,ap-j,interface-t,interface-j,ops-p,ops-t,ops-j,incident-p,incident-t,incident-j,recovery-t,recovery-j` | catalog 내부 ID. Native 등록 Tool ID와 다름. 현재 초안/게시/진행 건의 같은 ID가 현장 수정본인지 비교 필요 |
| 예시 tools/skills/sites | tools `gateway,db-target,db-read,network,process,health,smoke,infra,if-config,if-round,logs`(mock/example); skills `setup,connection,handoff`(+common 정책); sites `us-a,hu-a,kr-ca` | 예시 site를 실제 공장 master로 취급하지 않음. `workflow_policy.json`은 공통 강제 규칙의 근거여서 등록 콘텐츠와 분리 검토 |

현재 ApplyDemo는 Tool content/marker/name, preset 관리 Prompt 구역·function_calling·지정 toolIds/시작 질문·전문 모델 name/memory·지정 valve를 관리한다. `_projection/_merge_model/_payload`와 CAS/journal은 unmanaged 내용·ACL·사용자 질문을 보존하고 관리 필드 충돌을 중단한다. journal(`demo-assets-<scope>/ees-demo-assets.json`)의 previous_value·desired·source_commit은 삭제 백업/복구 명령이 아니다.

**재생성 지점:** 신규 catalog의 seed insert, ApplyDemo의 누락 Tool/preset create, 기존 수동 등록 가이드, bundle/wheel의 콘텐츠 포함이다. 조사한 Upgrade/TrialUpgrade는 프로그램 교체 후 `next=apply_demo`를 안내하지만 자체 자산 API 자동 호출은 확인되지 않았다. 후속 지침·단축 명령까지 추적하여 폐기 자산 재등록을 막아야 한다. 이전 프로그램으로 rollback하면 seed/ApplyDemo가 다시 살아나는 경계도 필요하다.

**삭제 지원 격차:** 조건부 자산 API의 operation은 create/update, kind는 tool/model/valves다. 삭제 미리보기·정확한 ID/현재 hash/참조 확인·조건부 delete·삭제 receipt·개별 자산 복구는 미구현이다. 기존 보호 코드를 활용할 수 있지만 현재 기능처럼 보고하지 않는다. P의 disable과 미게시 P soft-delete는 Native 모델/Skill/Tool 삭제가 아니며, disable은 이미 만들어진 case의 snapshot 실행을 막지 않는다.

**기록/복구 선택:** 과거 절차의 새 사용 중지, 기존 진행 건 실행 중지, 기록 읽기, 내보내기, 실제 삭제를 각각 결정해야 한다. 과거 실행 호환을 무조건 보장하지 않으며 기록도 자동 삭제하지 않는다. case snapshot이 있어도 현재 Tool/Skill ACL·가용성에 따라 읽기/실행이 막힐 수 있다. 모델 삭제 후 과거 Native 대화 열람/계속 답변은 실제 제품에서 별도 확인 대상이다. `manage_ees.backup`은 stopped/port 확인 후 DATA_DIR/설정/키를 hash 복사하지만 DB 검사 대상은 webui.db이고 ees-work.sqlite3 별도 integrity 검사는 확인되지 않았다. 프로그램 `restore`의 `data_changed=False`, switch의 `data_restored=False`는 등록 자산/DB를 되돌리지 않음을 뜻한다.

### C. Step 0-B에 필요한 백엔드 사실·선택지

| 항목 | 현재 지원·코드 근거 | 제약 / 다음 결정 |
|---|---|---|
| 정의·초안·게시 버전 | catalog published/draft/revision + `process_management`의 P별 draft_revision/base_fingerprint/validation/published_version. `authoring:_init_authoring(62),_write_publication(515),authoring_action(706–736)` | 저장·검사·게시는 분리. 버전은 catalog 전역 증가, 현재 JSON 덮어쓰기. 모든 미실행 게시본까지 불변 보관하는 버전 저장소는 아님. 절차별 버전 이력/보존 범위 결정 |
| 반복 진행 건 | UUID case + process/site/system/version·정의/작업 snapshot. `workflow:_new_case(358)` | 반복 case 생성 가능. owner 개인 소유, UNIQUE(owner,chat_id)로 대화 하나에 case 하나. 공동 참여자·역할·명명·대화 연결 cardinality 결정 |
| 개별 작업/시도/재실행 | case.jobs/history + execution_runs/calls/events; unique(run,job,call,attempt). `execution:init_execution(45),_job_result(755)` | 재실행은 새 plan/run, 실행 run 수락 뒤에는 호출 전이어도 기존 입력 변경은 새 case가 필요. 입력 대기의 누락값 보충과 기존 값 변경, 인증 대기 resume와 재실행/새 진행 건을 구분할 정책 필요 |
| 업무 설정 vs 진행 건 입력 | P execution_inputs schema + case.execution_inputs/run.inputs; old site db/ap 기본값. `contract:validate_execution(223),resolve_arguments(343)` | 별도 업무 설정 저장소·변경이력 API·scope/우선순위 없음. Native global Valves와 개인 PAT는 업무 설정 공유 모델이 아님 |
| 설정 공유 범위 | Native 개인 UserValves, 전역 Valves, authoring system_groups/owner_system, catalog sites | 개인/시스템/공장/절차 중 소유·조회·변경 권한·상속/덮어쓰기·다음 조회 적용을 결정. PAT는 Native 개인 설정에 유지 |
| 입력 선언/도구 인자 | constant/input/result 참조 + 제한된 identity/strip/to_string/to_integer 변환, 실제 Native 함수 schema 재확인 | 선언 값의 업무 의미와 attachment/file/CR 도메인은 추가. 임의 코드·SQL·Shell·템플릿 실행기 불필요 |
| 실행 snapshot | case 정의/site/version/접근 가능한 Skill 본문 복사; plan case_snapshot/hash; run schema/inputs; call 인자/input_sources/도구 hash/결과. `workflow:365–385,execution:259–270,705–719` | 설정 유효값·출처·적용 버전/사용자·결과의 보존/내보내기·보안 범위 결정. snapshot은 현재 권한을 대체하지 않음 |
| 선행조건/상태/사람/완료 | dependencies/applicability, execution fixed/ai/human, observed/selection/grounded-summary 및 final validator, `_control confirm(512)` | 실행 성공과 업무 완료 분리 유지. worker는 ready J/call 하나씩 선택하며 독립 branch 표현이 같은 run 병렬 실행 보장을 뜻하지 않음. CR 목록 확정/승인 기준·부분 결과 정책 필요 |
| AI 제안/초안 vs 실제 변경 | 입력 제안 persisted=false/executed=false; 별도 authoring save/validate/publish; human confirm은 AI Tool에서 제외 | 현재 `workflow_tool.py:ees_workflow_action(425),ees_execution_action(192)`은 create/update_inputs/run/start 가능. 새 패널 확정 규칙은 Tool 노출/API 계약까지 바꿔야 함. prompt만으로 강제 불가 |
| 개인 대화 vs 공동 업무 | Native chat 소유 확인·case owner 조건; `case.selected_id`는 서버 case revision과 함께 저장. 작성기 자체 대화/미저장 cache는 메모리 | 공동 진행 건·개인 선택/초안·Native 사적 대화의 분리와 참여자 접근 모델 필요. owner WHERE 제거만으로 공동화 금지 |
| 조회/작성/게시/실행 권한 | verified_user, 현재 계정/그룹 재조회, system authorizer, P owner, Native ACL·관리자 함수 승인·현재 개인 PAT | 게시 별도 역할 없음(작성과 같은 authorizer). 공장별 읽기/실행 ACL 미구현. Native 회원/그룹 재사용 범위와 서버 강제 정책 결정 |
| 동시 수정/중복 요청 | SQLite BEGIN IMMEDIATE, case/P/owner/map CAS; actor+request_id/fingerprint receipt; 중복 동일 게시 version 증가 방지 | 좋은 재사용 기반. Native DB와 workflow DB의 분산 원자성은 보장 아님. stale conflict UI/재시도 계약 필요 |
| 중복 실행/실패/부분/결과 불명 | plan TTL600/run TTL1800/lease30, 호출 전 영속 기록, overlap 차단, timeout/worker 소실/진행 중 cancel→UNKNOWN, 늦은 결과 별도 보존. `execution:_require_resolved(444),_late(826)` | UNKNOWN 조정 endpoint 없음. 새 실행까지 차단되므로 확인/해소 담당·증거·권한 필요. partial observed와 scope complete/final complete를 혼동하지 않음. 보존기간/정리 정책 미구현 |
| 전환/복구 | additive table·legacy catalog snapshot·import/reconcile·protocol-1 write guard, 이전 case snapshot 보존 | 새 migration 미설계. 옛 프로그램 read 호환과 write/실행 호환을 구분. 이전 데모 중지·기록 읽기/내보내기·삭제 및 DB/자산 복구 계약 필요 |

권장 검토 방향은 **기존 app·Native 인증/도구·SQLite 저장/실행 서비스를 우선 재사용하되 필요한 의미를 확장**하는 것이다. 현재 P draft/case/run에 version/settings 관계를 추가하는 안과 같은 DB 안에서 별도 version/settings 테이블을 두는 안을 비교할 수 있다. 공유/보존/권한 요구부터 결정하며 탭마다 테이블을 만들거나 새 framework/server/범용 runner를 전제하지 않는다. 구조 확정은 Step 0-B의 책임이다.

실제 Native 호출 흐름은 `_registered_assets`의 사용자별 metadata → `NativeBridge._snapshot`의 ACL/code/spec/common Valves hash → 관리자 exact reference 승인 → 개인 UserValves → Native loader의 동일 코드 → 호출 직전 현재 권한/참조 재확인 → 실제 함수 → 비밀값 제거/결과 정규화다. 자동 실행 허용 함수는 Confluence `search_pages/get_page`, Jira `jira_dashboard/jira_get_issue`, GitHub `github_list_pull_requests/github_get_pull_request` 6개다. 일반 Chat의 check_access 함수와 구분한다. CR 조건 검색/필수 첨부 다운로드·파일 내용 검사/결과 송부/일정 계산은 이 allowlist만으로 지원되지 않는다.

### D. 현재 Figma와 실제 기능 대응

[기준 페이지](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=832-131)는 `EES Work · 대화 중심 정리안 10.01`. 2026-10-01 13:25–13:31 KST에 metadata·read-only page inventory/text·화면을 조회했다. 페이지 직계는 **프레임6 + icon component3**이며 알려진 6개 프레임 모두 동일 페이지에 존재한다. 추가 화면 프레임/이동은 이번 조회에서 발견하지 못했다. component는 `832:8905(factory),832:8910(server),834:8398(user)`. 모든 프레임 descendant의 prototype reactions는0이라 실제 클릭 전이 검증은 하지 않았다. Figma 서버 version/revision ID는 사용한 API 응답에 없으며 [PNG/해시 관측 증거](../../../evals/v4-ui-20260930.md#restructure-step0a-evidence-20261001)로 이번 조회본을 식별한다. 영구 고정본/최종 승인본이 아니다.

분류: **기존 지원 / 화면·연결 수정 / API·데이터·실행 확장 / 규칙·디자인 결정**. 하나의 화면에 여러 분류가 가능하다.

| 화면/행동/상태 | 코드 대응과 분류 | 확인된 결정 / 남은 경계 |
|---|---|---|
| [안내 832:132](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=832-132): 왼쪽 위치/탐색·중앙 대화·오른쪽 패널 | Native shell/controller 재사용, view/designer 장착 교체 — 화면·연결 수정 | 대화는 설명·작업 chip, 저장/실행/재점검/완료는 패널. 현재 chat Tool mutation과 충돌하므로 실행 권한 계약도 확장 필요 |
| [A2 832:8953](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=832-8953): 공장/시스템 분리 선택·검색·담당/참여/권한 없음 | selectWork/switchScope 및 그룹 확인 기반 — 화면·연결 수정 + API 확장 | 위치 변경 시 트리 범위 변경·대화/작성 글 유지, 시스템 업무는 전체 공장에 표시, 실제 목록은 그룹 권한 기반은 이미 명시됨. 실제 공장 master/공장 업무 적용 범위·서버 ACL은 추가 결정 |
| [A1 832:8219](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=832-8219): 진행 건 시작·내 업무/찾기/실행/대화 기록·트리 | create/state/history와 Native 대화 — 기존 지원 + 화면·연결 수정; 팀 범위/목록 API 확장 | 반복 case 기반 존재. 공동 업무·한 대화 여러 진행 건·추천/목록 정책은 별도. 예시 3건/0/8/날짜/이름을 기본 데이터로 넣지 않음 |
| A1 현재 상태/실행 기록/작업 기준 | view workExecutionDetailHTML + 실행 state/history/rule — 화면·연결 수정 | 세 탭 의미와 실행 기록 읽기 전용은 결정됨. 현재 결과/부분/UNKNOWN 실제 상태를 연결해야 하며 미제공 결과 상세 화면을 임의 완성하지 않음 |
| A1 업무 설정 수정/변경 기록, 이번 진행 건 값 수정 | 현재 case 입력 저장만 존재 — API·데이터 확장 | 업무 설정은 다음 실행에 재사용·변경 이력, 진행 건 값은 이번만, 다음 조회부터 새 설정·과거 실행 기록 불변은 결정됨. 공유 주체/범위/우선순위는 미정 |
| A1 CR 목록 조회 → 목록 보정/확정 → 다음 작업 | runtime plan/start + Native Jira read + human confirm 기반 — 실행/도메인 확장 | 프로젝트·배포 상태·배포 기준 날짜가 조회 인자라는 의미, 조회 후 사람 확정 필요는 결정됨. 현재 Jira dashboard는 이 날짜/상태 조건 검색 기능이 아님. 목록 결과/보정 UI·필수 첨부·CR별 판정은 미제공 |
| A1 일정 카드/공휴일 경고/일정 조정 화면 열기/이대로 진행 | 일정 기능 없음(view의 일정 미등록, designer 미지원) — API 확장 + 규칙·디자인 결정 | 격주 화요일(기준09.15), D-8/D-6/D-5/D+1/D+2 큰 순서 명시. 날짜 계산/휴일·Freeze 조정 책임/달력 원본·시간대·확정 저장은 미정. 대화의 이대로 진행 버튼과 패널만 처리 규칙 관계 확인 필요 |
| [B1 835:323](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=835-323): 시스템별 절차 목록/새 절차/복사 제안/최근 편집 | authoring state/create/copy/관리 시스템 기반 — 기존 지원 + 화면·연결 수정 | 초안은 업무 화면에 미노출, 게시해야 다음 진행 건 적용은 결정됨. 숫자·예시 절차는 합성. 도구/스킬·지침 관리 진입의 상세 화면은 제공되지 않음 |
| [B2 836:372](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=836-372): 절차 개요/단계·작업/초안 상태 | P/T/J 정의 및 authoring — 기존 지원 + 화면·연결 수정 | 구조/일정/판정규칙/게시기록 탭은 명시. immutable 게시기록과 일정·CR별 반복 모델은 데이터 확장 필요 |
| B2/B3 초안 저장/게시 전 확인/게시 | designer.authorAction → authoring save_draft/validate_draft/publish → SQLite draft/token/catalog | 실제 지원(저장→revision+1·검사무효, 검사→token, 게시→현재 P 병합·version+1). Figma에는 게시 lifecycle 설명은 있으나 최종 게시 확인 화면은 미제공. 숨은 버튼 존재만으로 새 UX 완료 판정 금지 |
| [B3 832:8468](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=832-8468): 작업 편집/수행방식/도구/사람확인/선행·다음 작업 | 기존 mode·deps·execution human/tool/model 및 validator — 화면 수정 + 계약 확장 | 조회 후 사람 목록 확정해야 완료는 이미 결정. CR/첨부 실제 완료 기준은 임시값 상태. 도구 실행 성공을 완료로 치환 금지 |
| B3 사람이 정하는 값(형식·쓰이는 곳·저장 범위)/값 추가 | P input schema + J argument binding UI — API·데이터 확장 | 작성기는 값 칸 선언, 실제 값은 실행 담당자가 업무 패널에서 입력/저장, 빈 값은 첫 실행 때 물음. 현재 schema를 개인/공유 설정 구현으로 오인 금지 |
| B2/B3 AI 초안/변경 보기/되돌리기/저장 전 | 현재 instructions 전용 authoringReply 및 input_draft 경계 — 화면·연결/제안 계약 확장 | 설명→전체 단계/작업/입력선언 초안 생성은 현재 instructions-only AI보다 넓음. AI 제안≠저장/게시; 사용자의 이후 수정과 현재 대상/revision 보호 필요 |

**이미 정해진 것과 미정의 구분:** 공장·시스템 독립 선택/전체 공장의 시스템 업무/그룹 기반 목록/대화 유지, 초안→검사→게시→다음 진행 건, 업무 설정/진행 입력 분리, 실행 snapshot 불변, 사람 목록 확정은 재결정할 필요가 없다. 공장 업무와 시스템 업무의 정확한 적용/공유 범위, CR 조회 필드 매핑, 필수 첨부 목록과 CR별 판정 화면, 메일/Jira 댓글 등 송부 방식, D-5 이후 미승인 처리, 영업일/공휴일 조정 세칙은 남는다. 개발 설계서·개발자 테스트는 Figma가 **임시값**으로 표시한다.

안내는 패널만 실제 처리한다고 하나 A1 대화에는 “진행 건을 만들었습니다”와 “이대로 진행”이 있다. 시작 의도에서 case 생성까지의 확정 경계와 해당 버튼이 단순 이동인지 실제 상태 변경인지 확인해야 한다. 이 상충을 해소하기 전 임의 자동 실행을 설계하지 않는다.

### E. 실제 제품 검증환경과 다음 단계

현재 Work는 Linux/Python3.12.14/Node24.19.0이며 조사 범위에 Python3.11·기존 .venv·공식 wheel·로컬 Chrome이 없었다. 실제 빌더는 원본 wheel 없음에서 exit1, full-app 검사 진입은 httpx import에서 exit1이다. 제품 기동·브라우저 렌더·왕복은 **미실행**이고 제품 결함으로 판정하지 않는다. Figma 화면 확인·정적 코드 조사·합성 DOM·실제 Native 제품·사내 확인을 구분한다. [날짜/명령/환경/오류와 최소 보완](../../../evals/v4-ui-20260930.md#restructure-step0a-evidence-20261001).

최소 보완안은 저장소 한 곳의 Python3.11 검증 환경, 고정 원본 SHA의 Open WebUI0.11.3 wheel, 필요한 기존 의존성, Chrome1개를 확보하여 기존 full-app harness/ChromePipe를 쓰는 것이다. 기존 harness의 setup-p/ap-j/C안 가정은 새 빈 상태 계약에 맞게 후속 최소 수정해야 한다. 현재 단계에서 설치/환경 보완/시험 코드 수정/새 상시 서비스를 시작하지 않았다.

### 단계별 완료 조건과 차단 항목

| 단계 | 완료 조건 / 이번 조사에서 드러난 선행조건 |
|---|---|
| 0-A 이번 조사 | 최신 main·PR·지침·현재 Figma 전수 확인, 근거 있는 대상/기능/설계 쟁점표, 환경의 실제 실행/미실행 구분, 문서 검사·diff·커밋/push·Draft PR. 백엔드 확정/구현 없음 |
| 0-B 검토 담당 | 위 사실 검토 후 procedure/version/case/job attempt/settings/snapshot/권한·공동업무/완료·UNKNOWN/전환의 최소 계약과 Step1 범위 확정. 조사 자료로 착수 가능, 제품 환경 차단은 설계 차단 아님 |
| 1 빈 상태 | 구체 계약 후 데모 제거·재등록 방지·빈 catalog/첫 작성/기반 모델·실제 connector 보존 검사. 0-B 미확정, 실제 Native 검증환경, 기존 Native 가입 UI 검사 실패 미해결은 수락 차단 |
| 2 화면 구조 | 착수 시 관련 Figma 변경 재조회. 실제 Native 중앙 대화·오른쪽 패널/작성기·위치 변경/초안·첨부·권한 왕복과 화면 대조 |
| 3 절차 작성 | AI 제안/미저장·저장 초안·검사·게시/버전·동시 수정·그룹 권한의 서버/화면 증거 |
| 4 진행·실행 | 진행 건/공유 설정·입력 mapping·snapshot·현재 개인 PAT/ACL 실제 도구 호출·사람 확인·부분/실패/UNKNOWN·재실행/기록 검증 |
| 5 첫 업무 | 배포 산출물 점검의 확정된 CR 조건·첨부/판정·일정·송부 범위만 구현. 미정 업무정책을 기본값으로 발명하지 않음 |
| 6 통합/배포 준비 | 실제 Native E2E·새 Figma 대조·합성 사용자 자산 보존·잔여 참조/재등록 경로·복구 범위·배포물 검증 |
| 7 별도 승인 후 | 사내 현재 자산 inventory/사용자 변경·삭제 preview·백업/복구·정확한 삭제목록 승인 후 정리/배포/실환경 확인. 지금의 미확인은 Step7 실제 삭제를 차단 |

각 구현 단계는 상세 설계→Work 구현/시험→검토 담당 검증→보완/통과 순서다. 통과는 병합·배포·사내 삭제 승인이 아니며 다음 단계 자동 시작을 허용하지 않는다. Figma 변경은 스타일/화면 행동/백엔드 계약으로 나누고 착수·검수 때 관련 화면을 재조회한다. 이번 최종 보고 후 검토를 기다린다.


<a id="v4-ui-20260930"></a>

## 4차 UI · Native 업무 수행과 Assistant 재배치 · 2026-09-30

**현재 작업 기준:** 사용자 첨부 인계서 **v1.1**이 v1.0을 대체한다. 최초 구현 기반은 `b0515d594da36112919a14c814a95e2b5900035e`(#67 병합)였고 #68은 main `713ed5e4e5dce7e99866c1dbe0db31ef5be94af3`에 병합됐다. 사내 파손 보고 뒤 후속 수정 요청에 따라 같은 Draft PR #69, `fix/ees-v4-native-layout-20260930`에서 보완한다. #66/#67의 당시 결과와 아래 C안 기록은 과거 증거다. 이번 시각 기준은 [Figma 4차 A](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=747-559) / [4차 B](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=751-612), 페이지 `726:131`, v4 변수·텍스트 스타일·Button/Status와 `Icon/*`이다. 이전 A/C 외형을 현재 기준으로 재사용하지 않는다. Draft #53은 혼합하지 않는다.

**승인 범위:** 최초 요청은 실제 제품 원본의 구현·관련 검사·관리 문서·커밋/push·같은 작업의 Draft PR까지였고 병합·Draft 해제·사내 배포/서버를 제외했다. 09-30 사용자의 시험 배포 요청과 `응 진행해` 후속 승인으로 #68 Draft 해제·main 병합·기존 TrialCommit 시험 적용 진행을 허용했다. 승인 전 검토 head는 `f72b53aef76cc9c25dc5d264ad47c21aa4a24a43`, 제품 원본은 `6c4111a9afbaadda78256c8276b41cbb875673db`였다. #68의 병합과 시험 적용 안내 뒤 사용자가 화면 파손을 보고했고 조사 후 수정을 요청했다. #69의 범위는 코드·관련 검사·관리 문서·커밋/push·같은 Draft 갱신이며 새 병합·사내 재배포로 확대하지 않는다. Figma/PDF 원본 수정은 계속 제외한다. 실제 작업일 09-30의 STATUS에 따라 개발/문서 커밋에 `[skip ci]`를 붙이고 원격 Actions를 실행하지 않는다. 정확한 종료 head/PR은 [STATUS](../../STATUS.md), 시험별 판정은 [V4 평가](../../../evals/v4-ui-20260930.md)를 관리 원본으로 사용한다.

**#69 후속 승인:** 2026-09-30 18:04 KST 사용자가 “병합 재배포까지 하자”로 #69의 Draft 해제·병합·기존 TrialCommit 재배포를 승인했다. 위 최초/수정 마감의 제외 범위는 당시 경계로 보존하며 이번 승인은 새 요청에 근거한다. 제품 원본 `05d25a5bdfe8fe22d0dbfe2859808e54c69d85f7`과 유효 검사는 유지하고, 실제 적용 원본은 원격 병합 SHA로 확정한다. 실제 Native 시각/왕복 미실행과 사내 결과 미수신은 승인만으로 PASS가 되지 않는다. [승인·실행 경계](../../../evals/v4-ui-20260930.md#v4-fix-redeploy-20260930).

**자료 확인 경계:** 첨부 [v1.1 원문 보존본](../../../evals/assets/v4-20260930/EES_Work_UI_V4_Implementation_Handoff_20260930_v1.1.md), Figma A/B context·변수·기준 이미지와 PDF 13쪽 추출문을 확인했다. ZIP/PDF 원본 바이트의 내려받기는 502로 실패해 내용물·해시·원본 PDF 렌더를 검증하지 못했다. 원본을 수정하지 않았으며, 보존된 PNG는 **Figma 기준 이미지**다. 실제 제품 스크린샷 또는 제품 시각 PASS가 아니다.

| 새 UI / 필요한 연결 | 재사용 원본·변경 범위 | 반드시 확인할 조건 |
|---|---|---|
| 왼쪽 탐색 / 중앙 목록·상세 / 오른쪽 실제 Assistant | `ees-work-view.js`, 기존 launcher와 두 CSS. Native DOM과 대화 저장·입력·첨부 경로를 유지하고 배치 변경 | 실제 Native에서 목록→상세→저장/실행→결과→목록, Assistant 입력 도움; 새 채팅·독립 실행기 금지 |
| 상태별 작업표·추천·복귀 | 기존 definition children/deps, case/node/job 상태, 현재 실행 기록과 view 상태 | 실제 데이터만 집계; 할 일/진행 중/대기/완료, 대기2개+더 보기·완료 접힘, 후보1개, 초점·스크롤·초안 유지 |
| 모든 지원 J의 입력·행동·판정 | 기존 legacy `update_inputs/run`, Native `execution/plan/start/action`, schema renderer/validator | 초안/저장값/호출 snapshot 분리, 기존 승인·기본값 실행·UNKNOWN 보호, 모의와 실제 완료 구분 |
| AI 초안·근거·되돌리기 | 기존 workflow Tool/Native event call, 사용자·대화/메시지·target 확인, 기존 입력 초안 map과 메시지 statusHistory의 ActionRecord | 실제 반영 성공 전 입력함 표시 금지, 저장/실행0, 이후 사용자 수정 보존, 당시 참고와 다음 참고 분리. 실제 Native 카드·되돌리기 검수 미실행 |
| P/T·관리·자산 | 기존 범위 실행·최종 validator·Workspace/작성/게시·회원/그룹·개인 도구/설정 | 미설계를 삭제 사유로 삼지 않음; 이전 진행/기록/자산은 그대로 사용 |

H-01~H-06을 [평가의 적용표](../../../evals/v4-ui-20260930.md#handoff-rules)에 기록한다. 1920 원안의 중앙 내부 정보 칸300과 본문 하단 행동 바를 유지한다. H-03에 따라 저장과 점검 시작을 분리한다. Native 첫 실행 전의 공개 입력 저장은 기존 case 저장 경로에서만 처리하고, 이미 시작한 실행의 입력은 기존 입력 확인/재개로 보완한다. 저장과 승인·명시 실행을 임의 결합하지 않는다.

**진행과 수락:** 원본 코드의 재구성과 순수 렌더/서비스/컨트롤러 검사는 수행했으나, 최초 마감 당시 고정 upstream wheel과 로컬 브라우저를 확보하지 못해 **실제 Native A/B 대조·대표 왕복·실제 Assistant 입력 도움은 차단/미실행**이다. 제품 연결 코드의 존재·합성 테스트 성공을 전체 구현 검수 완료로 표시하지 않는다. 기존 Native 보내기·첨부·IME·반응형·다크·사용자 자산 실제 왕복·사내 결과도 새 PASS가 아니다. V4-01~15의 원문 기준과 남은 항목은 [평가표](../../../evals/v4-ui-20260930.md#v4-acceptance)에 유지한다. 최초 마감은 Draft였으며 후속 승인에 따른 Draft 해제·병합과 사용자 시험 적용을 제품 검수 완료로 해석하지 않는다. 후속 수정의 [회귀·환경 차단 근거](../../../evals/v4-ui-20260930.md#v4-ui-breakage-fix)를 보존하고 실제 Native에서 다시 대조한다. 공식 원본 backend는 Python 확장 모듈 불일치로 기동 실패했고, 보조 진단 서버의 cloud browser 접근도 차단됐다. 코드 검사 결과를 새 배포나 제품 시각 수락으로 바꾸지 않는다.

남은 제품 선택은 추천의 담당/검색 필터 적용 범위, 부분 결과 전용 표현, 담당·일정 공동 데이터 모델, 반응형·다크와 실행 이후 전용 디자인이다. 임시 구현과 기존 동작 보존을 최종 디자인 승인으로 바꾸지 않는다. 사용자에게 사내 원문 로그·파일 반출이나 대신 제품 검수를 요청해 이번 미실행을 PASS로 대체하지 않는다.

<a id="c-visual-match-20260929"></a>

## C안 전체 화면 시각 일치 보완 · 2026-09-29

**시작·승인:** 최신 main `8027aaf2e654778f052a966e5a49feed0fc54f69`와 깨끗한 로컬을 확인했다. #66은 병합 완료이며 재개하지 않는다. 같은 시각 보완 PR이 없어 최신 main에서 `fix/ees-c-visual-match-20260929`로 분기했다. 별도 Draft #53과 Windows 작업은 섞지 않는다. 이번 승인은 구현·검증·문서·커밋/push·Draft PR까지이며 병합/재배포/사내 변경은 사용자 시각 확인 후 별도 승인이다. 09-30까지 커밋별 `[skip ci]`·원격 검사 생략을 유지한다.

**정정:** 사용자가 새 입력 저장/더 보기와 함께 왼쪽·중앙·전체 외형 불일치를 보고했다. 기존 기능 PASS는 보존하되 시각 일치 PASS로 확대하지 않는다. 과거 Native 외형 보존·overflow footer를 의도된 차이로 적은 기록은 이번 면제 근거가 아니다. 기능·상태·저장 계약을 보존하면서 실제 Native 컴포넌트와 래퍼의 외형을 바꾼다.

**유일한 기준:** Figma `XK2wTos6sEuxSHhIj7cqg6` 페이지 `582:131`, 비교 `603:963` 오른쪽 C. J `582:132`, `584:169/405/634/869/1098`, P/T `586:555/958/1397`의 현재 context·변수·자산·렌더를 읽는다. 기준 원문/렌더/측정은 `dist/c-visual/figma`에 보존하고 최종 증거 묶음으로 제공한다. A/B·현 제품은 시각 기준이 아니며 Figma 원본은 수정하지 않는다.

| 영역 | 차이·수정 대상 | 확인 조건 |
|---|---|---|
| 전체·왼쪽 | 기존245px/회색 바깥면·세로 메뉴를 C의 흰 바탕과 1920 기준312/768/840 세 영역, 상단 정렬, 브랜드36px/제목22·32, 가로 새 대화/검색에 맞춤 | 설정 없는 기본값과 저장된 폭을 분리; 사용자 저장값 덮기 금지; 검색/기록/Workspace/계정 실제 접근 |
| 업무 탐색 | 공장/시스템 선택 표면·단계/J 간격·선택/점/상태·진척 표시를 context에 맞춤 | 실제 정의/집계·선택·펼침·독립 스크롤·키보드 유지 |
| 가운데 | Native 제목+업무 띠를 업무 대화18/28·경로13/22의 배치로 정돈; 메시지 여백과 실제 입력창의 외형 대조 | 실제 Native 입력/첨부·도구/모델 선택·보내기·중단·새로고침/대화 저장 보존; 가짜 입력창/대체 채팅 금지 |
| J | 제목30/42·상태 묶음, 입력56px, 입력 바로 다음 단일 행동, 결과/기준/보조 링크 | 짧은 입력+긴 설명으로 버튼 하단 이동 금지; 긴 입력/낮은 화면에도 같은 행동 하나만 접근 가능; 기본값 실행·추가 상태 계약 유지 |
| P/T | 해당 노드의 숫자/단위 위계·진척 막대·짧은 검색+필터 한 줄·목록/조건/페이지 | 실제 집계/검색/페이지/조건 펼침·완료 복귀와 목록 상태 보존 |
| 상세 | C에 연결된 상세의 제목/탭/본문/닫기/여백 | 없는 기준을 추측하지 않음; 기존 dialog/read-only/닫기/Escape/초점과 조회 실패 자료 제거 보존 |

**완료 행동:** 완료 J의 다시 모의 점검은 기존 서비스가 허용하는 현재 진행 건의 재실행 액션을 사용한다. 전체 P 완료의 read-only/쓰기 차단을 바꾸지 않는다. 입력 변경·현재 결과/과거 기록은 기존 저장 계약대로 보존한다.

**검수 순서:** 공식 제품 CLI 앱·임시 DB·실제 Native 인증/대화에 합성 자료를 준비해 1920×1080 J 입력 전(`582:132`)/완료(`584:1098`)와 T 관리(`586:958`)부터 맞춘다. 같은 업무/상태/문구·내용량/배율/테마/폭으로 비교하며 목업 예시 집계·대화를 제품 상수로 넣지 않는다. 1920×1080 제품 원본 PNG는 그대로 보존한다. Figma 검토 띠32px와 browser chrome 제외를 명시하고, 유효 앱 높이1048에 맞춘 별도 실제 재렌더/원점 변환을 조건으로 기록한다. 원본 검사를 대체하지 않으며 확대축소·넓은 마스크·시험 CSS·이미지 덮기를 금지한다. 전체 나란히 비교+50% 겹침, 주요 요소 좌표/크기/computed style을 함께 판정한다.

차이→수정→동일 조건 재검 뒤 다른 J/P/T로 적용한다. 1536×960·1366×768·긴 내용·좁은 패널·다크는 C 규칙 확장으로 구분한다. 불가피한 외형 차이는 이유/대안을 남기고 사용자 승인 전 제외·시각 완료 처리하지 않는다. 영향 회귀는 보내기/첨부·저장/새로고침·실행/대기·이력·완료 복귀·닫기/재열기·Tab/Enter/Escape·조회 실패 자료 숨김이다. 관련 시험·문서·diff·원본/패키지 바이트 확인, 정확한 head와 Draft 상태 확인까지 수행한다.

**추가 P/Native 대조에서 확인한 보완:** C9의 P 요약은 원본 높이111px 대신162.5px였고 진행 막대가 해당 완료 수치 아래가 아닌 전체 폭으로 배치됐다. 단계 제목 y377→428.5, 완료 조건 y816→894.984, 범위 행동 y868→989.984 차이를 기존 P 렌더/스타일에서 수정한다. 실제 조치/점검 가능 수치는 예시에 맞춰 덮지 않는다. 실제 비활성 Native 보내기는 원본과 같은 외곽에도 inherited opacity로 색이 흐리므로, 기존 disabled/전송 차단을 유지한 채 업무 화면의 외형만 기준 색으로 맞춘다. 같은 공식 앱 원본/겹침·P 단계표 geometry/style와 빈 입력 전송 차단을 재검한다.

**원본 순서의 구현 대응:** C의 왼쪽4개 요약은 완료된 설치·설정→선택 DB→서비스→AP인 반면 T목록은 DB→서비스→AP→검토→사람 확인→설치·설정이다. 실제48개 중 미완료23개를 보존하면 전체 완료 후순 정렬은 이6행을 재현하지 못한다. T목록은 기존 절차 순서·실제 전체 수를 유지하고 한 페이지6개로 표시한다. 왼쪽 요약은 선택 J의 같은 T 안에서 완료된 직접 선행을 먼저 포함한 뒤 선택 J와 인접 절차 순서로4개를 표시하며 기존 선택/완료 후 membership을 보존한다. 실제 deps/status를 사용하고 특정 업무 ID·예시 count를 제품에 고정하지 않는다. 복귀 때 검색/필터/페이지/조건 펼침/스크롤/초점 유지도 재검한다.

**상세 최종 대조 보완:** 실제 상세587:4886에서 dialog880×920/header68은 같지만 공통 h2/h3/p margin이 남아 제목+22px·탭+96px 차이가 확인됐다. 실행 상세 한정 margin0, 원본 탭500 굵기, 불투명 #202c3e backdrop을 적용하고 실제 상세 title y156/identity100/invocation y276·78/tab y378과 닫기/Escape를 재검한다. 기록 #/시각·실제 결과 필드는 보존한다.

**현재 종료 경계:** 구현·회귀·원본/패키지 검증과 동일 조건 증거를 갖춘 Draft로 제시한다. 전체 시각 일치/사용자 수락은 미완료이며 실제 자료·schema·추가 기능·원본 충돌과 재현하지 못한 상태를 [이번 평가 기록](../../../evals/c-design-phase3-20260929.md#c-visual-match-20260929)에 항목별로 남긴다. 병합·배포는 수행하지 않는다.

역할: EES Work 업무 탐색·실제 AI 대화·작업 패널 통합 담당자

저장소: knadalkim-a11y/team-agent-poc

입력: 현재 실행 계약은 [09-25 공통 Native 도구·P/T 실행](#shared-native-runtime-20260925), 신규 작성 권한은 [09-24 시스템 담당자·P별 작성/게시](#system-authoring-20260924), 현재 화면 변경은 [09-30 4차 UI](#v4-ui-20260930)이며 [09-29 C안 전체 화면 시각 보완](#c-visual-match-20260929)은 과거 시각 구현 근거다. [C안 2단계](#c-design-phase2-20260929)는 기능·상태 계약 근거이며 [09-23 A안 상태·실행 상세](#a-design-20260923)는 기존 구현 근거로 보존한다. [09-22 왼쪽 워크플로우 확정 디자인](#sidebar-final-20260922)과 [오른쪽 업무·수행·결과](#right-panel-20260922)의 탐색·기록 계약을 보존한다. [앞선 시각 계층 후속](#visual-hierarchy-20260922)과 [단계별 진행·무테 합의](#step-progress-ux-20260922)의 기존 실행·권한·저장 계약과 Workspace 구현은 보존한다. [09-21 통합 UX 첫 베타](#integrated-work-beta-20260921)는 당시 기준으로 보존한다. 이전 화면 참고자료는 [사이드바 개선 목업](ees-sidebar-refinement.html)이며, 이전 [공장별 업무 트리 목업](ees-factory-workspace.html)과 [최초 세부 편집 예시](ees-demo-workspace.html)는 보존한다. 목업 이후 확정한 [공장·시스템 공동 작업 목표](#ees-work-shared-target)는 아래 기록을 우선한다. ZIP 첨부 없이 저장소에서 읽는다. HTML 목업은 대화 내 표시용 참고자료이며 실제 제품은 기존 WebUI 컴포넌트·테마·AI 대화를 사용한다.

<a id="c-design-phase3-20260929"></a>

## C안 통합 회귀·개발환경 최종 검수 · 3단계 · 2026-09-29

**후속 승인·남은 gate(09-29):** 사용자 요청으로 실제 Native composer의 입력 → 보내기 클릭 → 요청/응답 표시 → 대화 저장 → 새로고침 복원을 기존/새 대화에서 확인한다. 업무패널을 연 상태에서 대화/진행 대상 유지와 중복 제출 부재를 검사하며 completion API 직접 호출·저장 메시지 주입으로 대체하지 않는다. 공식 앱·실제 Native 인증/대화·임시 DB를 사용하고 외부 HTTP/모델만 loopback 합성한다. 관련 결함만 같은 PR에서 수정·재검한다. 필수 경로 통과·관련 검사/문서/diff와 원격 검증 head 확인 후 Draft 해제·#66 병합을 승인받았다. 아래의 병합 미승인 표현은 앞선 검수 당시 경계다. 정확한 병합본의 프로그램/manifest/바이트와 복구 수단을 확인해 사내 시험 적용을 안내하되 회사 PC 작업은 사용자가 실행한다. 병합·배포 준비·사내 적용 성공은 각각 별도 상태로 기록한다.

시작 원격/로컬 head `7d9f2caaa7ef39522fd5fa3f69af732e5fcebeeb`, main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`를 대조했다. 같은 Draft #66에서 1·2단계와 세 보완을 보존하고 관련 결함만 수정한다. 새 설계/기능, Draft 해제, 병합/배포·실서버·Draft #53·별도 Windows 작업은 범위 밖이다. 기존 아래 유형 대응표의 서비스를 그대로 사용한다.

| 필수 경로 | 이번 실행·근거 구분 | 합격/중단 조건 |
|---|---|---|
| legacy 모의/초안/확인, Native 고정/AI/사람, P/T | 실제 CLI·Native 인증/대화·EES HTTP/임시 DB 종단 + 유형별 fixture 브라우저 | 저장/재접속·계획/대기/재개·판정/기록/복귀를 실제 행동으로 확인; 호출과 J/P/T 완료, 현재 입력과 snapshot 구분 |
| 완료 CTA·과거 판정·활성 중 초안 | inline/dock 실제 버튼, 더 보기→이력→과거 건, 클릭/Enter/폼 | T 상태/초점·T→P 보존, 실제 대상/당시 정의/저장 판정, 잠금 중 편집 보존·종료 후 기존 조건 적용 |
| 경합·전환·정보 보호 | 실제 두 Chrome 탭 + 늦은 응답, 기존 scope/user/revision/ACL 검사 | 원격값 덮어쓰기·중복 실행·다른 건의 자료 노출 없음; 조회 실패/권한 회수 시 열린 상세 제거 |
| 재기동·자산·프로그램 교체 | 기존 worker restart/UNKNOWN, 실제 Native 임시 계정/자산 및 같은 DB로 프로그램 교체 | UNKNOWN 자동 실행/성공 없음; Git 밖 합성 자산과 기록 보존; 프로그램 Restore와 DB 복원을 구분 |
| C안 시각·조작 | Figma 원본 읽기와 별도로 3개 크기·긴/좁은/다크·키보드 제품 검사 | 단일 행동·독립 스크롤·버튼/초점 접근; Native 계획 dialog·기본값·추가 상태 등 합의된 차이 유지 |

시험 준비 후 제품 원본과 wheel을 고정하고 관련 suite·핵심 종단을 같은 패키지에서 실행한다. 결함 수정 시 새 고정본으로 영향 검사를 재실행하며 초기 제품 실패·시험/환경 오류·최종 판정을 분리한다. 필수 차단이나 미해결이 있으면 개발환경 검수를 미완료로 남긴다. 기존 유효 검사는 변경 영향과 재사용 이유를 표시하고 중복 합산하지 않는다. 합성 HTTP/모델과 실제 Native 경로를 구분하고 비개발자 자체 검토를 실제 사용자 수락으로 표시하지 않는다. [최종 판정·증거](../../../evals/scenarios.md#c-design-phase3-20260929)는 같은 관리 기록에 남긴다.

<a id="c-design-phase2-20260929"></a>

## C안 기존 유형·P/T·예외 확대 · 2단계 · 2026-09-29

PR #66의 `022cf239b038877efbc75dff7c6dd87f82317f51`에서 이어간다. 시작 시 원격 main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`·Draft #66 head와 깨끗한 로컬을 대조했다. main STATUS의 #65 병합 대기 표현은 과거 기록이며 이미 끝난 병합/배포 준비를 반복하지 않는다. 1단계 공통 패널과 `panel_parent`/`returnPanel`을 보존하고 같은 view/CSS/controller의 차이를 구현한다. Draft #53, 별도 Windows 작업, Native 대화/폭·회원/그룹·Workspace·자산·저장소/키·P별 게시·과거 진행/실행은 변경하지 않는다.

**직접 확인한 시각 기준:** 09-29 07:52~07:57 KST(09-28 22:52~22:57 UTC)에 같은 Figma 파일의 비교 `603:963`과 아래 J 6개/P·T 3개 노드의 속성·반환 렌더를 다시 읽었다. 가로/세로 여백 32/24, 섹션 간격 24, 제목 30/42·결과 22/34, 상태 묶음·선택된 필터·보조 상세·단일 행동 영역과 독립 스크롤을 기준으로 삼는다. 원본 수정은 없으며 예시 고정 열 폭·집계·타이머는 제품 계약이 아니다. Native 공개 입력은 기존 계획 dialog에서 검토 후 시작하고 대기 중 보완은 별도 반영/재개로 처리하는 의도된 차이가 있다.

### 변경 전 대응표와 완료 조건

| 유형/상태 | 화면·행동 | 기존 서비스/저장 계약 | 이번 시험 |
|---|---|---|---|
| legacy 모의 tool / 미연결 | 공개 입력, 저장과 점검 분리, 결과·기준·이력; 미연결 사유 | `action/update_inputs`, `action/run`; 기본값 실행 허용, 변경 시 과거 결과 보존 | 저장/복원·기본값·실패/재시도·현재 입력과 실행 snapshot |
| legacy manual / draft | 입력 없는 확인은 가짜 저장 없음; 초안 반영과 검토 완료 분리 | 기존 명시 confirm / document→review→confirm | 사람 확인 취소·완료, 초안 변경/동시 수정 |
| Native fixed / ai / human | 공통 C 제목·상태·입력/결과·단일 행동 영역; 보조 상세 | `execution/plan` 조회→명시 `start`; 공개 schema renderer/validator; 고정 0회·AI 한도·사람 직접 확인 | 실제 서비스 고정 조회·AI·사람 확인, 호출과 업무 완료 구분 |
| Native 입력 대기/후보 선택 | 현재 실행 입력 확인→반영→명시 이어가기 | `execution/action(inputs/resume)`; legacy 입력 저장과 합치지 않음 | 후보 선택·재접속·실행 당시 arguments 보존·stale revision |
| P/T 및 혼합 범위 | 실제 집계·검색/필터/페이지·선행 사유·범위 계획; Native/모의 구분 | 기존 범위/최종 validator; 호출 성공만으로 P/T 완료 안 함 | T/P 범위 실행·부분 결과·목록/스크롤/초점·완료 행 소실 |
| queued/running/paused/failed/cancelled | 실제 사유·상태에 맞는 시작/중지/재개/취소 | 기존 worker와 revision; 중지/취소는 다음 호출 경계 | 실행 중 이동·재접속·재개·취소 및 실제 버튼 |
| waiting_input/authorization/dependency, UNKNOWN | 조건·다음 행동 표시; UNKNOWN 변경/자동 재실행 금지 | 호출 직전 현재 권한·참조/승인 재검, 미확정 호출 보호 | 권한 회수·승인 변경·UNKNOWN·동시 실행/수정 |
| 제외/미기록/빈·부분 결과/조회 실패/접근 제한 | 서로 구분하고 과거 민감 자료를 대신 노출하지 않음 | 기존 projection·complete/partial/empty/truncated/unknown·조회 redaction | 관련 renderer+실제 서비스/브라우저 재현 |

구현 전 검토에서 Native J의 옛 조기 렌더 경로, P/T의 공통 행동 영역 누락, UNKNOWN에서 서버가 거절하는 취소 버튼 표시를 확인했다. C안 공통 렌더에 연결하고 서버가 허용하는 행동만 제공한다. 별도 실행기·입력 schema·저장소, 업무 이름별 분기, Figma의 타이머/합성 결과는 추가하지 않는다. Native 실행 계획 입력은 명시적 시작으로 접수하며, 대기 중 입력 반영과 재개를 분리한다.

완료 조건은 위 모든 유형의 대응표 판정, 수정 영향 상태의 직접 재현·동일 조건 재검, 실제 제품 세 크기/긴 내용/좁은 패널/다크/키보드에서 행동·저장·호출·표시 확인이다. 영향받은 권한·동시 변경·기록 보존은 이번에 검사한다. 전체 광역 통합 회귀·최종 수락은 3단계이며 병합/배포·실서버 작업은 수행하지 않는다. Figma 조회/속성·렌더 대조와 제품 동작 검증, 합성 외부 응답과 실제 사내 검증을 분리해 [2단계 평가](../../../evals/scenarios.md#c-design-phase2-20260929)에 기록한다.

<a id="c-design-phase2-review-20260929"></a>

### PR #66 2단계 검토 보완 · 과거 판정·초안 반영

후속 지시의 시작 head `a9fdeae9c626138ad2b384bc52e1f64eb116bdb8`에서 두 누락만 보완한다. 완료 복귀·2단계 공통 화면과 서버의 차단/저장 계약은 보존한다. Figma `584:1098`의 완료 결과·판정·행동 묶음을 읽기 전용으로 재확인하며 레이아웃/자산이나 원본을 수정하지 않는다.

| 대상 | 기존 경로에 연결할 맥락 | 완료 조건 |
|---|---|---|
| 과거 Native 실행 | `run.node_id`의 실제 J/T/P 대상, 과거 진행 건에 고정된 definition/case, 읽기 전용 이력 | 실제 **더 보기 → 실행 이력 → 과거 진행 건**에서 저장된 J/범위 판정을 대조. T 성공을 P 완료로 만들지 않고 미기록·부분·UNKNOWN·접근 제한 유지 |
| Native 활성 중 legacy draft | 같은 진행 건의 비종료 Native 실행과 기존 서버 `blocks_legacy` 조건 | 초안 글 보존, 버튼·폼/키보드 제출·controller가 일관되게 차단하고 POST/저장/완료 기록 불변. 종료 후에도 기존 실행 조건을 충족할 때만 반영 허용 |

실패를 먼저 재현하고 같은 실제 패키지 브라우저 조건으로 재검한다. 완료 복귀·조회 실패 자료 숨김·현재 입력과 호출 snapshot의 영향 범위만 회귀 확인한다. 3단계 확대/통합 최종 수락·병합/배포는 포함하지 않으며 결과와 초기 시험 준비 오류를 [후속 평가](../../../evals/scenarios.md#c-design-phase2-review-20260929)에 구분한다.

<a id="c-design-phase1-20260928"></a>

## C안 공통 외형과 대표 J · 1단계 · 2026-09-28

최신 main은 #65 병합본 `e995fe16e4835f2d1799c95f3d6d1b74ce381389`이며 작업 브랜치는 `feat/ees-c-phase1-20260928`이다. Figma `XK2wTos6sEuxSHhIj7cqg6`의 페이지 `582:131` **정제안 · EES Work 09.28**, [보드 `603:963`의 오른쪽 C안](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=603-963)을 기준으로 삼는다. A안과 #65의 실행·저장·권한 계약을 보존한다. 이번에는 1단계만 수행하며 Draft #53·main 병합·사내 배포를 변경하지 않는다.

| 조회한 역할/상태 | C안 노드 |
|---|---|
| J 입력 저장 전 / 저장 후 미실행 | `582:132` / `584:169` |
| J 실행 중 / 실패 | `584:405` / `584:634` |
| J 재시도 중 / 완료 | `584:869` / `584:1098` |
| P / T 입력 전 / J 완료 후 T | `586:555` / `586:958` / `586:1397` |

1단계는 공통 패널의 가용 폭·여백·글자 위계, 제목 옆 현재 상태, 입력 저장과 실행의 분리, 결과·완료 조건의 우선순위, 보조 상세와 독립 스크롤을 다듬는다. Figma의 고정 열 너비·예시 값·시도 번호를 제품 상수로 복제하지 않으며 실제 Native 대화/입력창과 사용자가 조절한 폭을 함께 보존한다. J의 고정 헤더와 본문 스크롤을 확인하고 P/T 참조의 차이를 모든 역할 구현 완료로 확대하지 않는다.

**입력 저장**과 **모의 점검 실행/다시 모의 점검**은 기존 입력/실행 액션을 그대로 사용한다. 결과가 있으면 **입력 변경**을 접어 결과를 먼저 읽게 하고, 완료 뒤 기존 부모 이동을 **단계로 돌아가기**로 표시한다. 본문이 넘칠 때만 같은 실행 영역을 하단에 배치하며 버튼 복제나 본문 가림을 만들지 않는다. 공장 기본값으로 이미 실행 가능한 기존 조건에 새 저장 필수 gate를 추가하지 않는다.

대표 종단 흐름은 기존 AP 연결 확인(`ap-j`)의 모의 서비스로 입력 저장 → 첫 실패 → 명시적 재시도 → 완료 → 같은 시도/호출의 입력·출력 상세를 확인한다. 같은 태스크의 DB 연결 확인은 표시 대조에 사용한다. 저장만으로 실행하거나 업무 이름별로 전용 화면/실행기를 만들지 않는다. 타이머로 진행률·완료를 만들지 않고 실제 요청 대기와 저장 결과로 판정한다. 새 실행 뒤에도 이전 실패 이력은 남고 입력을 바꾸면 이전 성공을 현재 완료로 표시하지 않는다.

기존 #65 Native 업무의 계획·입력·접수/진행/결과 계약은 외형 수정과 분리해 보존하고 관련 선별 회귀를 확인한다. Native 대화·Workspace·개인 자산/권한·P별 작성·진행 snapshot은 변경하지 않는다. **2단계**의 전체 J/P/T 및 예외 상태 반영, **3단계**의 통합 회귀·PR 마무리는 후속 사용자 지시로 분리한다.

Figma 조회/렌더 대조, 실제 조립 frontend와 실제 서비스 fixture의 제품 검사, 전체 Native 앱 기동·실제 외부 서비스/사내 검증을 구분한다. 구현/검증 결과와 미실행은 [1단계 평가](../../../evals/scenarios.md#c-design-phase1-20260928)가 원본이며 기존 A안 수락을 새 C안 PASS로 합산하지 않는다.

<a id="shared-native-runtime-20260925"></a>

## 공통 Native 도구 재사용과 P/T 실행 · 2026-09-25

첨부 `EES_Work_Shared_Tools_Runtime_Design_Handoff_20260925_v1.0.md` 14절을 이번 구현 범위로 삼는다. 시작 main은 #64 병합본 `991cdb1d80ae07471fb50594831d74fe602b1ef7`이며 별도 기능 PR은 없고 Draft #53은 그대로 보존한다. A안·Native 회원/그룹·시스템 담당 권한·P별 저장/검사/게시·기존 사용자 자산과 진행 기록을 유지한다. 이번 승인은 구현·Work 검증·문서·커밋/push/PR까지이며 main 직접 push/병합·사내 배포·실제 계정/도구 등록·실서버 변경은 제외한다.

### 실행 계약

- **원본 하나:** 기존 Native Tool ID의 코드·저장된 함수 schema·ACL·Valves/UserValves를 재사용한다. 별도 코드/인증/PAT 저장소·동적 설치·범용 코드 실행기를 만들지 않는다. J의 `execution`에는 승인된 함수와 내용/schema/비밀 아닌 설정/환경 hash·revision, 공개 입력 연결, 완료 validator와 호출 한도만 둔다. 조회·작성 중에는 코드를 import하지 않는다.
- **검토 후 호출:** 기존 관리자만 검토 근거를 붙여 기능을 승인/중지한다. 미검증·불일치·삭제·조회 실패는 실행 불가다. 현재 사용자/그룹/도구 권한·승인 hash·필수 개인 설정을 호출 직전 재검사하며 사용자별 새 Native 도구 객체를 사용한다. 내부 예약 인자는 서버가 주입하고 업무 입력은 이를 덮지 못한다.
- **하나의 서비스:** `execution/plan`, `execution/action`, `execution/state`를 기존 앱에 추가한다. 채팅 `ees_execution_plan/action/state`와 패널은 같은 서비스를 사용한다. 계획은 조회이고 명시적 start가 실행을 접수한다. 단일 앱 lifespan worker와 기존 SQLite의 짧은 transaction/claim/lease가 실행을 이어가며 외부 I/O 동안 쓰기 transaction을 유지하지 않는다.
- **결과와 완료 분리:** 호출 결과·근거·완전성·오류, J 업무 validator, P/T 최종 validator를 따로 기록한다. 고정 J는 모델 0회, AI J는 현재 허용 모델 1회 이하의 구조화 근거 정리, 사람 J는 직접 확인이다. 공통 정책과 해당 P/T/J의 고정 지침·현재 허용된 Skill·선언한 근거만 모델에 준다. 검색 결과의 명령은 지침이 아니다.
- **유실·재기동:** 요청 식별자/계획 hash/revision·겹친 실행 차단과 영속 호출 의도로 중복 호출을 막는다. 브라우저 종료는 서버 실행을 종료하지 않는다. lease 소실·시간 초과·중단 뒤 미확정 호출은 UNKNOWN으로 남기고 성공/자동 재시도로 바꾸지 않는다. pause/cancel은 다음 호출 경계에 적용하며 이미 시작한 외부 작업의 취소를 보장하지 않는다. 권한·입력 대기는 조치 후 명시적 재개, 실제 사람 확인은 패널에서 기록한다.
- **범위 제한:** 계획 유효기간 10분, 실행/근거 재사용 범위 30분과 J별 제한을 둔다. 대상 입력 변경은 새 진행 건을 요구하고 성공한 이전 결과를 새 입력과 섞지 않는다. 예제의 자동 재시도는 0회이며 명시된 재시도/총 호출 한도 안의 `rate_limited`만 최대 1회 다시 시도한다. 나머지 실패·불명확한 호출을 조용히 반복하지 않는다. 결과를 다시 노출하거나 AI/후속 입력으로 재사용할 때 원천 권한을 다시 검사한다.

### 10.1의 두 워크플로우

| 예제 | 등록 도구와 실행 | 완료 범위 |
|---|---|---|
| A 운영 현황 확인 | T1 Jira `jira_dashboard` → GitHub `github_list_pull_requests` → Confluence `get_page`; T2 선언한 저장 근거의 AI 정리 | T1 단독은 모델 0회. P 실행은 T1 뒤 T2. Jira 집계·PR 페이지 상태·문서 제목/버전의 실제 값과 부분 범위를 검증. CI/리뷰 승인·전체 자료 조사를 추정하지 않음 |
| B 설치 문서 사전 확인 | 같은 Confluence ID의 `search_pages` → 후보 선택 대기 → `get_page` | 확인된 검색 결과의 실제 page_id만 연결. 모호한 후보는 임의 선택하지 않음. 문서 읽기 완료이며 Windows 설치 완료가 아님 |

`ees_workflow_examples.py`의 factory는 승인 참조와 모델 ID를 받아 정의를 만든다. 운영 ID를 추측하거나 도구/P를 자동 등록·게시하지 않는다. 기존 P별 작성 API로 초안을 저장·검사·게시하며 새 J 편집기는 기존 도구의 허용 함수를 선택한다. Windows 셋업은 추후 같은 입력/검증/근거/승인/재개 계약에 연결하고 이번 여섯 읽기 함수 범위를 쓰기나 Shell로 확장하지 않는다.

제품/복원 경계는 [운영 가이드](../../03-openwebui-native-agent.md#shared-native-runtime-20260925), 시험별 판정·초기 실패는 [TR-01~24](../../../evals/scenarios.md#shared-native-runtime-20260925)가 원본이다.

<a id="system-authoring-20260924"></a>

## 시스템 담당자의 P별 작성·게시 · 2026-09-24

첨부 `EES_Work_System_Authoring_Design_Handoff_20260924_v1.1.md`를 구현 기준으로 삼는다. 1.0의 시스템별 권한·P별 저장/게시·보존 계약에 Native 회원 기능 재사용과 첫 이용 검수를 추가한 단일 기준이다. A안 #63 병합 main `a443d30c6694df0e1cbe082a0b99aa5f2d566917`에서 이어가며 [A안 표현](#a-design-20260923)을 다시 구현하지 않는다. 설계 Draft #53은 변경하지 않는다. 이번 범위는 구현·합성 환경 검증·문서·후속 PR이며 main 병합·사내 배포·실제 계정/그룹 변경은 아니다. 실제 결과는 [SA-01~28·NU-01~08 평가](../../../evals/scenarios.md#system-authoring-20260924), 운영/첫 이용은 [Native 가이드](../../03-openwebui-native-agent.md#system-authoring-20260924)·[팀 안내](../../07-team-quickstart.md#system-authoring-20260924)에서 관리한다.

### 관리·이용 권한의 분리

| 권한 단위 | 원본과 허용 범위 |
|---|---|
| 계정·역할·그룹 소속 | 기존 Native 가입/로그인/사용자/그룹 관리. 개인 계정 `user` 유지, 관리자 신원 확인 뒤 `pending → user` 승인 |
| 시스템 담당자 | Native group ID와 EES system-group 연결. EMS/APC/FDC/EGIS/EPT별 활성 그룹 하나, 같은 그룹의 중복 시스템 연결 없음 |
| 저장·검사·게시·충돌 | 선택한 P 하나와 하위 T/J. 같은 시스템의 다른 작성자 P도 관리 가능하며 다른 P의 미게시 변경은 제외 |
| 관리 시스템 | 서버 `owner_system`/`owner_revision`. 시스템 하나 또는 관리자 전용 `COMMON`/`UNASSIGNED`. node 적용 범위/URL/작성자 이름으로 권한 추론 금지 |
| 업무 이용·자산 접근 | 기존 진행 건 소유권·Native ACL·개인 인증·실행 정책 유지. 담당 권한은 다른 사람의 대화/진행 조회나 실제 외부 실행 권한이 아님 |

전용 담당 그룹에는 Native Workspace 모델/도구/지식/프롬프트/스킬 관리 권한이나 자산 ACL을 추가하지 않는다. 가입·일반 이용 승인·담당 지정은 독립이며 기본 가입 그룹을 담당 그룹으로 자동 연결하지 않는다. EES는 별도 담당자 명단·회원 DB·비밀번호·JWT·이메일 재설정·SSO/Redis 체계를 만들지 않는다. 실제 회사의 기본 권한이나 다른 그룹 설정은 수정하지 않는다.

### 작성과 서버 보호 계약

- 현재 계정/역할과 Native 그룹 소속을 보호 요청마다 조회한다. 이름 변경은 ID가 같으면 유지하고 삭제/동일 이름 재생성/연결 해제/계정 pending·삭제는 허용 근거가 아니다. 그룹 조회 실패는 관리 요청을 차단하며 캐시로 허용하지 않는다. 그룹 제거 완료 뒤 다음 요청은 재로그인 없이 거절한다. Native/EES DB 간 분산 트랜잭션이나 이미 커밋한 작업의 소급 취소는 약속하지 않는다.
- 담당 P는 관리 시스템=적용 시스템 하나다. 공통/미지정 P와 소유권 지정/이관, 시스템-그룹 연결은 관리자 전용이다. 기존 P의 적용 시스템으로 소유권을 자동 추론하지 않는다. 다중 시스템 P는 그대로 관리자 관리하거나 새 ID와 내부 참조로 시스템 전용 복사본을 만든다. 이관은 owner revision을 증가시키고 검사 승인을 무효화하며 기존 진행 snapshot을 바꾸지 않는다.
- 한 요청에 P 하나의 subtree와 그 P 전용 참조만 받는다. 다른 P의 node/roots, 공통 정책·공장 목록·공유 자산 정의, 소유자/role 위조·교차 P 의존·ID 충돌·순환·크기 초과는 저장부터 차단한다. 미완성 초안 허용과 권한/구조 보호는 구분한다. 접근 불가 기존 참조는 불투명 ID로 보존하되 필요한 참조를 확인할 수 없는 새 게시는 거절한다.
- 동일 P의 draft/owner revision과 게시 기준을 확인해 오래된 저장을 충돌로 거절한다. 검사 기록은 정확한 저장 초안 hash/revision, 소유권, 해당 P 게시본과 참조/정책에 결합한다. 게시 때 권한/자산 접근을 다시 확인하고 미저장 브라우저 값은 섞지 않는다. 검사 통과는 실제 업무 실행 성공이 아니다.
- 최신 `catalog.published` 안에 선택한 P만 원자적으로 병합한다. 다른 P의 동시 게시/미게시 초안은 보존하고 무관한 catalog 변경만으로 충돌시키지 않는다. catalog/version·초안 기준·감사 저장이 부분 성공하면 안 된다. 중복 게시는 한 번만 반영하며 중복 응답 재생도 현재 인가를 거친다.
- Native Tool/Skill은 허용된 기존 자산의 참조다. 자산 코드/본문/인증값을 P 초안에 복제하거나 참조만으로 외부 실행 어댑터를 만들지 않는다. 새 P는 기존 사람 확인·초안 검토·모의 점검을 사용한다. 게시 P 사용 중지는 새 시작을 제한하고 기존 진행/이력은 유지한다.

### 구현 인터페이스

| 경로/항목 | 실제 구현 계약 |
|---|---|
| `GET /api/ees-work/authoring/capabilities` | `is_admin`, `managed_systems`, `can_author`, `actor_id`, `protocol:1`. 기존 runtime의 `can_manage`는 admin 의미를 유지 |
| `GET /api/ees-work/authoring?system_id=…&process_id=…` | 인가된 P 목록/초안/검사 상태/참조만 조회. legacy 보존본 조회는 관리자 경로 |
| `POST /api/ees-work/authoring/action` | P `create/copy/add_node/save_draft/validate_draft/publish/disable/delete`와 관리자 `set_system_group/transfer_owner/import_legacy`. 관리용 envelope이며 runtime `scope`와 분리 |
| 기존 runtime 전체 작성 액션 | 관리자라도 `authoring_upgrade_required`(409)로 거절. 기존 runtime `state/action`·공개 `open_webui.ees_workflow`·진행 입력/실행 계약 유지 |
| P 저장 메타데이터 | 서버 `owner_system/owner_revision`, `draft_revision`, 해당 P의 `published_version`. 입력 중 새 T/J 임시 식별자는 저장 시 서버 발급 ID로 확정 |

Native 현재 사용자와 비동기 `Groups.get_groups_by_member_id`를 매 요청/쓰기 직전에 읽는다. 실제 처리 코드는 같은 기능 폴더의 `ees_workflow_authoring.py`에 두고 기존 WorkflowService로 연결한다. 테이블은 기존 업무 SQLite에 추가하며 별도 회원 DB를 만들지 않는다. API가 구현된 사실과 인가/보존/Native 수락 통과는 구분해 평가표에 기록한다.

### 기존 셸의 작성기와 자료 보존

모델·도구 등 Native Workspace 관리 권한이 모두 없는 일반 담당자도 기존 앱 셸 안에서 **업무 절차**에 진입·새로고침·복귀할 수 있어야 한다. 기준 canonical 진입은 `/?ees=workflow`이며 기존 Workspace 탭/관리자 URL은 같은 작성기의 호환 경로다. 실제 구현 URL은 가이드와 시험을 함께 맞춘다. Native Workspace 가드를 우회하거나 별도 HTML/서버/로그인 화면을 만들지 않는다. 관리 진입은 runtime의 업무 생성/대화 연결·기존 `scope`와 분리한다.

툴바는 대상 P 이름·관리 시스템·저장 초안/해당 P 게시 버전·미저장 상태를 표시한다. 담당 시스템/P 이동은 유지/저장 후 이동/명시적 버리기를 구분하고 자동 저장·게시하지 않는다. 동일 사용자 세션의 미저장 글은 충돌/권한 회수에도 보존하되 저장 불가를 표시한다. 계정 전환/로그아웃에서는 초안·capability·늦은 응답과 AI 문맥을 정리한다. 수동 작성은 모델 연결 없이 가능해야 한다. A안 패널과 Native 대화/Workspace DOM·접근성은 보존한다.

기존 전체 `draft/published/revision/validated`는 정확한 읽기 전용 보존본을 먼저 만들고 초기 전환으로 published/cases를 바꾸지 않는다. P별 초안만 활성 편집 원본이며 과거 전체 초안의 P 가져오기는 관리자 명시적 검토로 한다. `catalog.draft`는 게시본 호환 mirror다. 오래된 전체 저장/게시 요청은 관리자라도 갱신 필요로 거절하고 기존 runtime API/공개 모듈은 유지한다.

프로그램 Restore는 새 초안·Native 그룹·사용자 자료를 되돌리지 않는다. 이전 프로그램은 담당자 기능을 지원하지 않으며 admin-only 경계를 유지한다. 재업그레이드 때 fallback 중 작성한 전체 초안을 추가 보존하고 새/이전 프로그램이 같은 DB에 동시에 쓰지 않게 한다. 실제 지원 복원본 검사가 없으면 사내 데이터 변화의 배포 준비 완료로 표시하지 않는다. 감사에는 actor·대상·revision/hash·요청/시각·결과만 남기고 본문/자격증명은 제외한다. Native 구성원 변경의 운영 감사 보존은 별도 확인하며 이벤트 호출만으로 영속 로그를 보장하지 않는다.

<a id="a-design-20260923"></a>

## A안 상태와 실행 상세 · 2026-09-23

사용자 첨부 `EES_Work_A_Design_Implementation_Handoff_20260923.md`의 A안을 기존 제품에 구현한다. 기준은 Figma `XK2wTos6sEuxSHhIj7cqg6`의 페이지 `478:131`, [검토 보드 `498:363`](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=498-363)다. 최신 사용자 합의 → A안 표현 → 실제 기능·저장·권한 계약 순서로 대조하되 없는 기록이나 기능은 만들지 않는다. #61·#62 병합 main `e5b799ed22d193341fa23e1269e4d7083d0766f7`에서 이어가며 이전 구현·시험·사내 적용 보고를 보존한다. 이번 요청은 구현·검증이며 새 병합·사내 설치 승인은 아니다.

| 상태 | P | T | J |
|---|---|---|---|
| 입력 전 | `511:393` | `511:642` | `478:132` |
| 입력 반영 | `514:978` | `514:1227` | `481:382` |
| 실행 진행 | `515:655` | `514:1512` | `481:600` |
| 실패 | `514:729` | `511:927` | `478:795` |
| 재시도 진행 | `515:904` | `514:1797` | `514:511` |
| 재시도 완료 | `511:1497` | `511:1212` | `478:1016` |

상세는 사용 구성/실행 이력/입력/출력/미기록/절차·근거 `516:701/766/811/876/947/990`, 조회 실패/접근 제한/미수행 `544:1111/1153/1195`를 대조한다. 상태별 추가 Dialog와 Prototype 복제본은 별도 제품 화면으로 만들지 않는다. 실제 조회 범위와 제품 수락 결과는 [A-01~A-11 평가](../../../evals/scenarios.md#a-design-20260923)에만 기록한다.

### 표현과 기존 동작의 연결

- 연속된 작업면·얇은 구분선·약한 선택색을 사용한다. P/T의 핵심 집계, J의 입력·결과와 완료 조건을 먼저 읽게 하되 모든 내용을 카드/굵은 글자로 감싸지 않는다. 제목 28~30px·본문 14~16px·보조 12~13px의 Figma 계층은 Work 범위에서 실제 읽기 폭에 맞춘다. 기존 로컬 폰트·EES 토큰과 로고를 유지하고 외부 폰트/아이콘 다운로드나 Native/Workspace 전역 재디자인을 추가하지 않는다.
- 실제 1920/1536/1366 창에서 중앙 대화·입력창과 오른쪽 독립 세로 스크롤을 함께 확인한다. Figma의 열 너비를 유일한 breakpoint 공식으로 고정하지 않는다. 작은 창의 왼쪽 넘친 내용도 접근 가능해야 한다. 상세 대화상자는 880×960 예시를 기준으로 가용 폭·높이를 제한하고 헤더/닫기와 본문 스크롤을 분리한다.
- P→T→J와 상위 복귀·닫기/재열기는 같은 업무 맥락을 유지한다. T 작업명과 조건 화살표의 이벤트를 분리하고 선행 업무 이동 뒤 검색·필터·페이지·스크롤·유효한 펼침·미저장 입력을 보존한다. 오른쪽 추천 카드와 왼쪽 J별 안내는 복원하지 않는다.
- 입력 반영은 실행이 아니다. 실제 요청 중 결과 대기·미판정과 중복 차단을 표시하며 타이머/가짜 진행률로 완료시키지 않는다. 재시도는 별도 이력이며 현재 입력/최신 결과로 과거 기록을 덮지 않는다. J 완료 뒤 상위 집계·후속 조건을 재평가하되 점검 가능만으로 후속 J를 자동 실행하지 않는다.
- 현재 범위 실행 가능 수와 최종 처리 수를 구분한다. 실행 시 권한·조건과 사람 확인·실패 재시도·제외·미연결 경계는 기존 서비스 계약을 따른다. Figma의 합성 수치·시각·시도 번호를 제품 상수로 넣지 않는다.
- 기존 읽기 전용 dialog와 시도/호출 선택을 재사용한다. Tab·Escape·포커스 가둠/해제·원 진입 버튼 복귀를 유지하고 상세 안의 이전 화면 이동도 보존한다. 입력/출력은 같은 시도와 `checks[index]`에서 읽고 고정 절차를 실제 지침 제공/준수 기록으로 표현하지 않는다. 미기록·빈 결과·조회 실패·접근 제한·미수행·사람 확인을 구분하며 raw/schema/버전/출처를 추정하지 않는다.

기존 Native 대화·첨부·도구/스킬 선택, Workspace 편집/저장/게시, 권한·개인 설정·사용자 작성 자산과 진행 snapshot을 보존한다. 새 backend·저장 형식·권한 구조·범용 실행기는 없다. 제품 수락은 실제 조립 wheel의 Native 검사와 관련 계약 검사로 판정하며 Figma 속성/이미지 대조와 분리한다. 사내 Windows·실제 LLM·운영 데이터는 접근하지 않은 범위를 미실행으로 남긴다.

<a id="right-panel-20260922"></a>

## 오른쪽 업무 내용·수행·결과 후속 · 2026-09-22

사용자 첨부 `EES_Work_Right_Panel_Implementation_20260922.md`의 마지막 합의를 적용한다. 왼쪽 #61의 구현과 검수·배포 범위를 보존하고 오른쪽은 구분 가능한 후속 변경으로 관리한다. 첨부 작성 당시 main은 `b1c47643c7a5ab4fd85c50a000db3f92ceda82b2`, #61 head는 `0e9e17556be7c5f251105350f288544a9afe59ea`였다. 초기 구현 시도의 GitHub/Figma 읽기는 `HTTP 400: Invalid MCP request metadata`로 차단됐으나, 같은 날 재개 시 실제 조회가 정상화됐다. 사용자의 새 병합·배포 안내 요청에 따라 왼쪽 [PR #61](https://github.com/knadalkim-a11y/team-agent-poc/pull/61)은 main `cfe5e4d36ca902c8706aed4d07f0cd87ffa16a78`에 병합했으며 오른쪽은 별도 후속으로 검수한다. 실제 사내 적용 결과는 아직 수신하지 않았다. 새 조회와 실제 검사 결과는 [오른쪽 평가 기록](../../../evals/scenarios.md#right-panel-20260922), 현재 종료 상태는 [STATUS](../../STATUS.md)에 기록한다.

Figma 기준은 `XK2wTos6sEuxSHhIj7cqg6`, 페이지 `335:131`의 **검토안 · 업무 내용·수행·결과 09.22**다. 우선순위는 아래 마지막 사용자 합의 → 역할별 최신 목업 → 기존 업무·권한·저장 계약이다. 아래 지정 16개 노드의 design context·screenshot을 **2026-09-22 재개 시 실제 조회**했다. 초기 실패나 앞선 왼쪽 조회와 구분하며 Figma 원본은 수정하지 않는다.

| 영역 | 대조할 최신 노드 |
|---|---|
| P/T 최신 비교·단계별 문제 요약 | [368:192](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=368-192), `364:175` |
| T 목록·실패 사유·선행 조건 | `364:367`, `366:217`, `366:447` |
| J 입력·반영 후·완료·실패 | `335:523`, `339:140`, `339:312`, `339:485` |
| 상세 진입·사용 구성/입출력 비교 | `347:152`, [357:160](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=357-160) |
| 사용 구성·이력·입력·출력·미기록 | `347:323`, `347:494`, `347:665`, `347:836`, `347:1007` |

### P/T/J의 정보와 행동

- P는 목적·적용 범위, 직속 단계 완료 수와 적용 J 완료 수를 구분한다. 단계 행에는 수행 내용·작업 완료 수를 표시하고 문제 있는 단계에 상태별 분포를 추가한다. 입력 필요·실패·선행 대기·적용 제외를 완료로 합치거나 개수 비율을 일정 진척으로 표현하지 않는다. 모든 접근 가능한 단계는 동일한 방식으로 연다.
- T는 수행 범위·완료 조건과 전체 작업 검색·필터·페이지를 유지한다. 작업명은 J 열기, 별도 화살표는 등록 조건·관측 사유 펼침이다. 사실이 있는 모든 작업에 같은 접근을 제공하고 이벤트를 분리한다. 선행 J 이름은 이동 가능하며 패널의 돌아가기에서 검색·필터·페이지·스크롤·유효한 펼침·미저장 입력을 보존한다. 단순 실패 상태로 없는 원인을 생성하지 않는다.
- P/T의 **범위 모의 점검 실행**은 기존 실행 경로를 사용한다. 현재 가능한 수와 최종 처리 수를 구분하고 실행 중 조건·권한을 다시 검사한다. 사람 확인·실패 재시도·적용 제외·실행 미연결의 기존 경계를 유지하며 새 실행 계획 엔진·확인창을 추가하지 않는다.
- J는 확인/수행 내용·완료 기준·읽기 전용 업무 범위와 기존 입력 계약을 표시한다. 등록된 입력이 필요한 경우에만 입력 반영을 제공하고 새 공통 대상 선택기·다중 DB/AP 저장소는 만들지 않는다. 입력 반영·별도 모의 점검·명시적 사람 확인·결과와 실패 재시도를 분리한다. 입력 수정으로 과거 결과를 삭제하거나 세부 점검 수를 J 완료 수에 합산하지 않는다.
- 오른쪽의 **지금 할 일/다음 할 일·추천 작업 카드**를 제거한다. 대기·필수 입력·실패·미연결·모의 실행 범위는 수행 사실이므로 패널에서 유지한다. 이전 섹션의 오른쪽 추천/다음 조치 배치는 이번 합의로 대체하며 왼쪽 단일 선택·단계 구조와 가운데 Native 대화는 보존한다.

### 사용 구성과 실제 기록 연결 범위

기존 `ees-work-view.js`의 사용 구성·실행 이력·전달 입력·반환 출력 상세는 읽기 전용이다. 기본 결과에서 선택한 시도와 호출로 연결하고, 여러 호출과 같은 도구의 반복은 저장 배열의 순서와 기록된 식별자·시각으로 구분한다. 재시도 선택 시 다른 시도의 호출 값을 섞지 않는다. 단일 호출은 별도 호출 선택 없이 해당 상세를 표시한다.

목업과의 의도된 차이로, 수행 상세는 별도 화면 체계를 만들지 않고 기존 상세 대화상자와 닫기·초점 복귀 경로를 재사용한다. 목업의 풍부한 호출 예시는 현재 저장 계약의 실제 기록이 있는 범위만 연결하며, 없는 외부 원문·출처·형식 검사·개별 버전은 만들어 채우지 않는다.

| 보여줄 정보 | 현재 원본과 표시 경계 |
|---|---|
| 적용 구성 | 진행 건의 `definition`·`version`과 접근 가능한 `context.skills`. 시작 전은 게시 정의. Workspace의 현재 편집 초안과 구분하며 설정됨을 실제 호출·지침 전달·준수로 표시하지 않음 |
| 실행 한 건 | `jobs[J].history`의 `attempt/status/at/kind`. 사람 확인은 `human_confirmation` 기록이며 도구 호출로 만들지 않음 |
| 호출별 입력 | 선택한 시도의 `checks[index].input`. 기존 모의 실행이 사용해 저장한 값만 표시하며 현재 폼 값이나 전체 `inputs`로 과거 호출을 채우지 않음 |
| 호출별 결과 | 같은 `checks[index]`의 `status/detail/simulation/at/id/name`. 저장된 모의 점검 결과이며 외부 시스템 원시 응답이 아님. blocked/skipped는 전달·반환 없음과 미수행으로 구분 |
| 없는 상세 | 호출 고유 ID·당시 개별 도구 버전·입력 출처/이전 출력 연결·출력 형식 정의/검사·외부 원시 응답을 추정하지 않음. 기록 없음, 현재 조회 실패, 접근 제한, 실제 미수행을 구분 |

업무 결과·완료 판정을 상단에 두고 호출 상태·형식 확인을 구분한다. 현재 출력 형식 검사 기록은 없으므로 **미확인**이며 업무 실패를 형식 적합/도구 정상 반환으로 완료 처리하지 않는다. 진행 건의 고정 절차 버전과 호출 당시 개별 버전 기록은 다르다. 상세의 읽기 허용 항목만 표시하고 내부 Skill snapshot 전체·비공개 Prompt·인증값을 새로 노출하거나 전체 요청/응답을 수집·저장하지 않는다. 기존 서버·API·저장 형식은 이번 변경에 포함하지 않으며 새로운 범용 호출 수집·민감값 마스킹을 구현했다고 보고하지 않는다. 외부 호출 기록이나 새 버전/형식 검사 계약이 필요하면 저장 호환·민감정보·권한 영향을 따로 검토한다.

### 이번 수락과 배포 경계

P 집계/T 필터 일치, 0개·적용 제외·다량 작업, 조건 펼침/이동/복귀, J 입력·실행·확인·실패/재시도 보존, 실제 모의 실행과 상세 값의 일치를 새로 검사한다. 다중/반복 호출과 과거 기록 누락은 합성 검증 범위와 실제 지원 경로를 구분한다. 실제 Native의 같은 데이터·폭·선택에서 밝음/어두움·긴 한글·스크롤·포커스·닫기/재열기와 왼쪽·Workspace·대화/사용자 자산 회귀를 확인한다. Figma 대조와 필요한 검사가 막혀 있으면 후속 PR은 Draft와 이유를 유지하며 완료된 검사나 과거 PASS로 대체하지 않는다. 이번 병합 요청은 위 새 사용자 승인에 따른 것이며, 오른쪽 최종 검증본과 병합 main의 일치를 확인한 뒤 적용 원본을 안내한다. 병합 완료와 실제 사내 설치·기동·화면 확인은 별도로 기록한다. [사용·기록 해석·적용 전제](../../03-openwebui-native-agent.md#ees-right-panel-20260922)를 따른다.

<a id="sidebar-final-20260922"></a>

## 왼쪽 워크플로우 패널 확정 디자인 · 2026-09-22

사용자 첨부 `EES_Work_Sidebar_Final_Implementation_20260922.md`와 왼쪽 패널 수락을 기준으로 PR #60 병합 main `b1c47643c7a5ab4fd85c50a000db3f92ceda82b2`에서 이어간다. Figma `XK2wTos6sEuxSHhIj7cqg6`, 페이지 `313:131`의 [비교판 313:680](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=313-680), P `313:132` / T `313:319` / J `313:515`의 design context·이미지를 **2026-09-22 실제 조회**했다. 승인 범위는 이 화면의 왼쪽 워크플로우 패널이며 오른쪽은 참고 영역이다. 기존 Figma 원본·변수는 수정하지 않는다.

| 범위 | 확정 표현과 선택 기준 |
|---|---|
| 분류·주변 바탕 | 밝은 테마의 주변은 `#f5f7fa`, 분류 영역/탭은 흰색. 선택 분류는 청색 글자와 짧은 밑줄이며 P/T/J 선택과 독립 |
| 워크플로우 P | 이름·완료 수 전체가 하나의 클릭 영역. 비선택은 흰색, P 선택 전체는 `#dcebf7`, 이름은 `#37658b` |
| 단계 T | 기본 제목과 펼친 하위 영역은 흰색. T 선택 때 제목 행만 `#eef5fa`와 청색 이름. 펼친 부모의 `data-expanded`는 선택을 뜻하지 않음 |
| 작업 J | 작업명+상태, 선택 행만 `#eef5fa`와 청색 이름. 좌우 들여쓰기와 행 전체 클릭 영역 유지. 한 줄 기본 최소 높이 42px이며 긴 문구는 행 확장 |
| J 내부 경계 | 인접 J 사이에만 1px `#e4e9ef`: N개면 N−1개. 첫 행 위/마지막 행 아래/전체 작업 보기 경계와 외곽에는 선 없음 |
| 상호작용·어두운 테마 | 실제 P/T/J 선택은 하나. hover는 더 약하고 다른 행 hover에도 선택 유지, focus-visible은 독립. 상태 의미별 색·문구와 어두운 테마의 의미별 토큰·가독성 유지 |

앞선 **진한 청색 선택·청회색 T 제목·J 구분선 없음** 기준은 왼쪽에서 위 합의로 대체한다. 밝은 테마의 흰색을 어두운 테마에 강제하지 않는다. 변경은 기존 `ees-work-launcher.css`의 `#ees-work-entry` 범위에 한정하고 전역 EES 토큰·오른쪽 업무 패널·Workspace·실행 버튼은 변경하지 않는다. 왼쪽 제목이나 J별 안내문을 복원하지 않으며 동작·권한·저장 계약·개인 인증을 바꾸지 않는다.

실제 Native의 같은 P/T/J 선택에서 목업 왼쪽과 직접 대조하고, 마우스를 치운 선택/다른 행 hover/키보드 포커스/밝음·어두움/좁은 폭·긴 한글/0·1·여러 J의 경계를 확인한다. 대량 작업 접근·선택 유지와 기존 오른쪽·Workspace·Native 선택기의 스타일 보존도 확인한다. 새 검사·실패·보완·남은 차이는 [이번 평가 기록](../../../evals/scenarios.md#sidebar-final-20260922)이 원본이다. 이전 PR #60 적용 안내 뒤의 사용자 “응 확인했어”는 앞선 적용 확인으로만 기록하며 이번 후보의 설치·기동·새 화면 검증으로 확대하지 않는다. 최초 종료점은 구현·검증·문서·후속 PR·새 배포 준비였고, 이후 같은 날 사용자 병합 요청으로 PR #61을 main `cfe5e4d36ca902c8706aed4d07f0cd87ffa16a78`에 병합했다. 해당 변경의 실제 사내 적용 보고는 아직 없다.

<a id="visual-hierarchy-20260922"></a>

## 시각 계층 후속 보완 · 2026-09-22

당시 기준은 사용자 첨부 `EES_Work_UI_Visual_Hierarchy_Followup_20260922.md`다. PR #59의 단계별 UX와 사용자가 정상 수행을 확인한 main `c4c6ab8d1df3e50a7e25fc8f47e969eb1360a4f1`에서 이어갔다. 아래 기준은 PR #60 구현 이력이며 왼쪽 색상·J 구분선은 [후속 확정 디자인](#sidebar-final-20260922)으로 대체한다. 오른쪽·Workspace 보완과 기존 행동 계약은 유지한다.

| 범위 | 선택·펼침 기준 | 바탕·글자·경계 |
|---|---|---|
| 워크플로우 P | 이름과 완료 수를 포함한 요약 전체가 하나의 버튼. P 선택 때만 강한 선택 | EES 청색 바탕과 테마별 대비 글자. 하위 선택 때는 약한 요약 바탕이며 별도 제목 버튼/중첩 버튼 없음 |
| 단계 T | 펼침 범위는 `data-expanded`, 실제 선택은 `aria-current`. 두 의미를 분리 | 기본 제목은 번호·굵은 이름·완료 수와 청회색 바탕. T 선택 때 제목만 강한 선택, 펼친 하위 목록은 약한 그룹 |
| 작업 J | 이름+상태만 유지하고 선택 J 하나만 강조 | 양쪽 최소 10px 안쪽 여백과 추가 들여쓰기, 둥근 선택 면이 부모 경계에 닿지 않음. 행별 카드/실선 없음 |
| 공통 상태 | P/T/J 탐색의 강한 선택은 하나, hover와 키보드 포커스는 별도 | hover는 약한 바탕이고 선택 바탕을 지우지 않음. focus-visible은 독립 외곽선, 업무 상태는 읽을 수 있는 별도 배지. 비선택 활성 항목을 비활성처럼 흐리지 않음 |

오른쪽 제목·상태·핵심 수치·주요 행동은 본문보다 명확히 하고, Workspace 편집 제목이 AI 보조 제목보다 우선한다. 편집 가능 입력과 읽기 전용을 구분하되 무테 표현을 유지한다. Runtime/Workspace Native에서 같은 데이터·폭·선택의 수정 전후, 마우스를 치운 선택/다른 항목 hover/키보드/밝음·어두움/1920·900 및 Workspace 600px, 긴 문구·다량 작업·닫기/재열기·입력·snapshot 보존을 확인한다. 기존 대화·권한·개인 인증·사용자 자산은 변경하지 않는다. 이후 별도 사용자 승인으로 PR #60을 main `b1c47643c7a5`에 병합하고 적용 안내를 제공했다. 앞선 실제 검사와 이번 왼쪽 후보 검사는 구분한다.

<a id="step-progress-ux-20260922"></a>

## 단계별 진행·무테 · 2026-09-22

사용자가 첨부한 `EES_Work_UX_Implementation_Verification_20260922.md`의 확정 요구를 따른다. 우선순위는 **마지막 문구/행동 합의 → Figma 09-22 단계별 배치 → 기존 EES 토큰과 업무/권한/저장 계약**이다. Figma `XK2wTos6sEuxSHhIj7cqg6`, 페이지 `281:131`(수정안 · 단계별 진행·무테 09.22), 시작 `289:425`를 기준으로 한다. Runtime `281:132/289/458/601`, `286:146/311/476`; Workspace `287:155/283/422/835/974/1113`; 연결·개인 인증 제안 `287:561/698`과 같은 페이지의 닫기/재열기 경로를 대조한다. 실제 접근/대조 여부는 [이번 평가 기록](../../../evals/scenarios.md#step-progress-ux-20260922)을 따른다. 이전 223:131·182/188/193을 최신 배치로 혼용하지 않는다.

- 왼쪽은 공장/시스템 → 셋업·운영·장애대응 가로 분류 → 선택 워크플로우 요약 → 모든 단계 이름·상태·완료 수를 표시한다. 선택 단계/선택 작업의 상위 단계에서 작은 작업 목록을 바로 보여준다. 많은 작업은 작은 요약과 전체 검색/필터/페이지로 모두 접근하며 다른 워크플로우·여러 진행 건 선택을 유지한다.
- 왼쪽 **이 단계에서 할 일**, **지금 확인할 작업**, 작업 아래 안내문은 제거한다. 작업명과 실제 상태만 남기며 구체 입력·대기·실패 안내는 오른쪽에 둔다. 목업에 삭제 전 문구가 남아 있어도 이 합의를 우선하며 의도된 차이로 기록한다.
- 내부 P/T/J 보존을 Runtime 재귀 트리 보존으로 해석하지 않는다. 단계 번호는 읽는 순서이며 병렬·선행 조건을 바꾸지 않는다. 작은 목록은 선택을 보존하고 정의 순서/서버 상태로 구성하며 작업 중 자동 재정렬하거나 완료 직후 선택 결과를 숨기지 않는다. Workspace 구조 편집은 그대로 유지한다.
- P/T는 목표·완료 조건·집계·전체 목록·범위 점검을 유지한다. 입력/실패 조치는 해당 작업 열기를 우선한다. **현재 점검 가능한 수**와 범위 실행의 실제 처리 건수는 다르다. 기존대로 실행 중 선행 조건이 풀린 작업도 이어가며 조건/권한을 다시 확인한다. 사람 확인과 실패 재시도는 일괄 실행에 섞지 않는다.
- J의 입력 반영, 별도 실행, 결과/이력, 다음 가능한 작업 열기를 구분한다. 다음 작업은 이동만 한다. 입력 변경은 기존 결과를 삭제하지 않고 재반영 필요를 표시한다. 저장 버튼 전환 직후 이중 클릭/연속 Enter가 실행으로 이어지지 않게 한다. 재시도 결과는 완료 기준으로 판정하며 과거 실패 이력을 보존한다.
- 일반 버튼·필터·요약/안내 박스는 장식용 실선 없이 EES 청색 주요 행동·옅은 청색 선택·의미별 상태로 구분한다. `--ees-*`를 재사용하고 Work/Workspace의 회색 덮어쓰기를 제거한다. Native 전체를 재디자인하지 않는다. 긴 한글·좁은 창·패널 폭·밝음/어두움·Tab/focus-visible·대비를 실제 화면과 computed style로 확인한다.
- 대화/첨부·Tool/Skill 선택·개인 인증, Workspace AI/수동 편집·늦은 응답 보호·저장/검증/게시, 기존 진행 snapshot·결과·권한은 보존한다. 새 일정/인증 저장소/범용 실행기/공유 권한/가중 진척률은 추가하지 않는다. 미지원 연결·날짜를 동작하는 기능으로 표시하지 않는다.

완료 조건은 새 원본 Native 제품 화면의 단계 배치·100개 이상 탐색·연속 입력 방지·P/T/J 동작·보존 회귀, 동일 상태의 Figma 실물 대조, 문서/커밋/push/후속 PR 및 새 원본 묶음이다. 미실행 범위는 정확히 남기며 이전 PR #58 승인/검사를 새 변경에 확대하지 않는다. 세부 문구·간격은 이 범위 안에서 마무리하고 실제 업무 규칙·권한·저장 계약 변경만 영향을 분리한다.

**09-22 재개 대조:** GitHub/Figma 플러그인 접근을 새로 확인하고 위 Runtime·Workspace·연결 프레임의 design context와 이미지를 실제 대조했다. 공장/시스템 가로 배치·선택 단계 강조·J 입력 주 버튼·결과/다음 행동 순서를 기존 view/CSS에서 보완했다. Native 주변 화면·반응형 폭과 편집 구조 tree는 유지한다. 연결 M2/M8의 다중 대상과 일정은 미지원이며 M7은 기존 전체 초안 게시 계약을 보존한다. 이 차이를 구현 누락이나 완료된 새 계약으로 바꾸지 않는다. 조회한 세부 노드·실행/실패/재검증은 [재개 평가](../../../evals/scenarios.md#step-progress-resume-20260922)에 기록한다.

<a id="integrated-work-beta-20260921"></a>

## 통합 UX 첫 베타 · 2026-09-21

이번 구현 기준은 Figma `XK2wTos6sEuxSHhIj7cqg6`의 **223:131 통합 UX · 업무·작성·연결 09.21**, 검토 시작 **241:416**이다. 이전 182/188/193 검토안과 PR #57의 단순 UX를 최신 통합안으로 간주하지 않는다. 기존 아래 설계·증거는 당시 기준으로 보존한다.

- 워크플로우(P)는 단계와 모든 적용 작업의 진행·문제를 관리하고, 단계(T)는 작업 목록의 검색/상태 필터/페이지 탐색과 다음 행동을 제공한다. 완료 수는 실제 적용 J를 기준으로 계산하며 적용 제외와 선행 대기를 문제/완료에 섞지 않는다.
- 작업(J)은 입력 반영·모의 점검·사람의 명시적 확인·결과/재시도를 구분한다. Native 대화와 패널은 기존 대상·revision·권한·실행 경로를 공유하고 선택 이동/패널 닫기에서 대화·미저장 입력·결과를 보존한다.
- Workspace는 같은 계층의 구성/입력/도구/스킬/안내를 편집하고, AI 수정은 미저장 안내에만 반영한다. 초안 저장·확인·전체 초안 게시를 구분하며 기존 진행 건은 시작 시 고정본을 유지한다.
- 연결 화면은 접근 가능한 기존 Tool/Skill 참조와 원래 설정 진입만 제공한다. Valves/UserValves·주소·키를 복제하지 않는다. 도구 등록과 업무 실행 연결·개인 인증 검증은 별개다. 미지원 다중 대상·일정·공유 권한은 후속으로 남긴다.
- 첫 베타의 완료 조건은 새 변경의 자동/Native 화면 검증, 사용자 자산·snapshot·이력 보존, 후속 PR과 정확한 원본의 묶음/적용/Restore 안내다. 병합·사내 적용은 별도 승인과 결과 확인을 필요로 한다. [이번 대조·검증 근거](../../../evals/scenarios.md#integrated-work-beta-20260921).

<a id="work-panel-chat-design-20260916"></a>

## 2026-09-16 업무 패널·대화 통합 상세 설계

**09-16 당시 요청은 설계와 검토까지였다.** 사용자가 확인한 대화 목업의 방향을 이 절에 구체화했다. 이 절은 아래 09-15 패널의 표시 순서·기술 설정 노출·시작 진입·버튼 문구에 관한 후속 설계이며, 이전 구현·시험 증거는 보존한다. 후속 `구현배포도 진행하자` 승인으로 09-17에 아래 범위의 구현과 검토를 진행한다. 실제 구현·사내 적용 상태는 [STATUS](../../STATUS.md), 당시 [설계 검토](../../../evals/scenarios.md#work-panel-chat-review-20260916)와 이후 [구현 검사](../../../evals/scenarios.md#work-panel-chat-implementation-20260917)는 별도로 기록한다.

### 1. 목표와 화면의 책임

잡에서 실제 업무를 수행·점검하고 결과와 근거를 축적한다. 검증된 잡을 연결해 태스크·프로세스의 자동 수행 범위를 넓히고, 같은 업무를 자연어로 관리한다. 익숙한 담당자는 패널을 직접 사용하고, 신입·다른 시스템 담당자는 대화로 절차와 용어를 이해하며 진행한다. AI는 게시 절차와 저장된 상태를 읽어 안내하고 실행을 요청한다. 완료 판정과 권한·선행 조건 검사는 업무 서비스가 맡는다.

| 영역 | 사용자가 하는 일 | 기본으로 보여줄 내용 | 업무 처리 역할 |
|---|---|---|---|
| 사이드바 `업무` | 공장·시스템·업무 선택 | 게시된 P/T/J, 선택한 위치와 진행 상태 | P 아래 직속 T, T 아래 직속 J 탐색. 현재 진행 건이 없어도 절차 조회 가능 |
| P 프로세스 | T 단위로 전체 진행 관리 | 목표, 직속 T 현황, 막힌 단계, 다음 조치 | 실행 가능한 하위 점검을 이어서 수행하거나 필요한 T로 이동 |
| T 태스크 | J 단위로 단계 진행 관리 | 완료 조건, 직속 J 현황, 진행에 영향을 주는 선행 조건 | J의 입력·확인·실패를 살피고 해당 T 범위 점검 진행 |
| J 잡 | 실제 작업 처리 | 최근 결과, 필요한 입력/검토 대상, 완료 조건, 다음 조치 | 입력 반영, 자동 점검, 사람 확인, 결과·근거 확인 |
| 메인 대화 | 이해·작성·명령 | 선택한 업무 맥락, 짧은 설명, 입력 초안, 처리 결과·다음 행동 | 화면과 같은 조회·변경·실행 경로 사용. 특정 업무 선택 전 탐색과 범용 질문도 유지 |
| Workspace 업무 절차 | 수행 방법과 자동화 설정 관리 | P/T/J 구조·조건·연결, 입력 정의·점검 기준, 지침·스킬·도구 참조 | 전문가/관리자가 초안을 편집·구조 검증·게시. 기존 자산 편집 기능 재사용 |

P/T의 관리에는 범위 내 자동 점검 진행이 포함된다. 사람의 실무 확인과 실행 결과는 J에 기록하며 P/T에는 같은 결과를 집계한다. P/T별로 같은 입력을 다시 받거나 완료 버튼을 별도로 만들지 않는다. 일상 담당자에게 모델·프롬프트·스킬·도구 선택을 요구하지 않는다. 기존 UI에 반영한 GLM 5.3 연결과 사용자 자산은 보존하며, 구현에 모델명을 고정하지 않는다.

### 2. 오른쪽 패널의 정보와 배치

공통 순서는 **위치·업무명 → 현재 상태/핵심 내용 → 직속 하위 목록 또는 입력·결과 → 다음 할 일 → 주요 행동 하나**다. 공장·시스템을 한 번 명확히 표시하고 설명문·목표·상태를 여러 카드에 반복하지 않는다. 상위로 돌아가는 경로와 실행 이력은 항상 찾을 수 있게 둔다.

| 패널 | 본문 구성 | 목록 열 또는 입력 | 기본 펼침 / 상세 |
|---|---|---|---|
| P | 한 줄 목표, 직속 T 완료 수, T 목록, 다음 조치 | `태스크 / 잡 완료 n/N / 상태` | T를 선택해 해당 패널로 이동. P에 모든 J를 나열하지 않음 |
| T | 한 줄 완료 조건, 직속 J 완료 수, J 목록, 다음 조치 | `잡 / 수행 방식 / 상태` | 수행 방식은 `사람 확인·초안 검토·자동 점검`. 시연은 `모의 점검`, 미연결은 원인을 명시 |
| J | 현재 유효한 최근 결과, 업무에 필요한 입력/초안, 완료 조건, 다음 조치 | 실제 입력 계약에 있는 필드만 사용. 자동 점검/사람 확인/초안 검토에 맞춰 행동 변경 | 수행 내역은 접고, 결과 요약·문제·필수 입력은 펼침. 이전 시도는 실행 이력에서 열람 |

- P 상단은 적용 대상 **T 완료 수**, T 상단은 적용 대상 **J 완료 수**다. P의 각 T 행에는 해당 T의 적용 J 완료 수를 표시한다. 분모·단위를 함께 표시하고 현재 서버의 잡 기준 `progress`를 T 완료 비율로 오해해 재사용하지 않는다. 직속 자식의 서버 상태로 계산하며 새 진척률을 따로 저장하지 않는다.
- 적용 제외는 완료 수·분모에서 빼고 `제외 n개`로 보조 표시한다. 적용 대상이 0개면 `적용 제외`이며 100% 완료로 표현하지 않는다. 빈 절차와 적용 제외를 구분한다. 수량은 소요시간·일정·자동화율을 뜻하지 않는다.
- 실패·입력 필요 등 조치할 행에만 짧은 사유와 절제된 강조를 쓴다. 정상 행은 같은 높이·열 정렬·구분선을 사용한다. 선행 대기, 입력 부족, 실행 연결 필요를 모두 오류나 실패로 표시하지 않는다.
- J의 `수행 내역`에는 업무 이름으로 표현한 점검 순서, 결과, 실패·미수행 사유, 실제 기록된 시각·근거를 표시한다. 도구 실행 여부는 확인 가능하되 내부 Tool ID·프롬프트 원문·비밀값·원시 디버그 로그는 일상 패널에 넣지 않는다. 예: `서버 접속 완료 → 응답 시간 초과 → 후속 통신 미수행`.
- 필요한 업무 근거 문서는 권한이 확인된 제목·링크로 제공한다. 사람이 실제 수행·확인하는 데 필요한 짧은 작업 안내·주의사항은 패널에 남긴다. Workspace로 옮기는 것은 도구·스킬·지침의 등록·연결·원문 편집이며, 화면에서 설정을 숨겨도 AI와 서버의 지침 적용·권한 검사는 유지한다. 관리자용 원시 진단 화면은 이번 범위에 새로 만들지 않고 기존 보호된 운영 기록을 사용한다.
- 현재 저장하지 않는 담당자·기한·자유형 확인 메모·자동화 점수는 표시하지 않는다. 실행 시각은 시도 기록에서 가져오며 `updated_at`을 대신 쓰지 않는다. `rule` 설명 문구를 AI나 서버가 자동으로 실행 가능한 판정식으로 바꾼다고 가정하지 않는다.

### 3. 상태에 맞는 행동과 실행 범위

버튼은 아래와 같이 실제 가능한 다음 행동을 표현한다. 클라이언트의 예상 안내가 실행 허가를 대신하지 않으며, 최종 판정과 결과 집계는 기존 서비스 응답을 사용한다.

| 상태 | P/T의 주요 행동 | J의 주요 행동 | 처리 원칙 |
|---|---|---|---|
| 실행 가능한 점검이 있음 | `계속 진행` | `점검 실행` | 선택한 P/T/J 범위와 실행 종류를 짧게 표시. 현재 시연에는 `모의 점검`을 함께 명시 |
| 실패 항목이 있음 | `문제 확인`으로 직속 T/J 이동 | `다시 점검` | 이전 실패는 보존. 실패 사유 확인과 재실행을 구분 |
| 필수 입력·검토·사람 확인 필요 | `다음 업무 열기` | `입력 반영` / `검토 완료` / `확인 완료` | 한 번에 필요한 행동만 표시. 일반적인 자동화 요청으로 사람 확인을 대신하지 않음 |
| 선행 미완료·미연결·접근 제한 | 조치할 업무 열기 | 원인과 가능한 조치 표시 | 실행 불가 이유를 설명하고 지원하지 않는 실행/권한 신청 버튼을 만들지 않음 |
| 실행 중 | 현재 진행 확인 | 중복 실행 비활성 | 실제 실행 응답에 근거해 표시. 지원하지 않는 취소·예약 실행을 추가하지 않음 |
| 현재 진행 건의 해당 노드 완료 | 결과 확인·상위 업무 이동 | 결과 확인·상위 업무 이동 | 입력 수정은 진행 중인 건에서만 별도 가능. P/T 수동 완료 단계 없음 |
| 진행 건 전체 완료·과거 이력 | 결과·근거 열람 | 결과·근거 열람 | 읽기 전용. 별도 새 실행 요청으로 새 건을 생성하며 과거 건을 다시 열어 쓰지 않음 |

P/T의 `계속 진행`은 미완료·적용 대상 잡 중 현재 연결·입력·권한·선행 조건을 충족하는 범위만 실행한다. 사람 확인 뒤에 이어지는 잡은 대기하며, 독립적으로 가능한 다른 잡은 기존 실행 정책에 따라 진행할 수 있다. 실패와 독립 실행 가능 항목이 함께 있으면 주 행동은 `문제 확인`, 보조 행동은 `가능한 점검 진행`으로 유지하고 대화에서도 같은 범위를 요청할 수 있다. 하나의 실패로 모든 형제 업무가 막혔다고 단정하지 않는다.

하위 잡 종류별 개수는 구성 안내다. 서버의 실행 계획 응답이 없으면 `이번에 정확히 n건 실행`이라고 확정하지 않는다. 실제 실행 전에는 대상 범위·가능한 종류·사람에게 남는 일을 보여주며, 읽기 점검마다 별도 확인창을 추가하지 않는다. 기존 정책상 승인이 필요한 외부 변경은 해당 명시적 승인 절차를 유지한다. 이번 설계는 외부 발행·운영 DB 쓰기·원격 셋업 권한을 추가하지 않는다.

### 4. 상시 업무 탐색과 진행 건 연결

`게시 절차`는 반복할 업무의 정의, `진행 건`은 특정 대상에서 수행한 기록이다. 공장·시스템별 워크플로는 항상 탐색할 수 있어야 하며, 별도 `이 공장에서 시작` 버튼을 진입 조건으로 두지 않는다.

1. 공장·시스템·P/T/J를 누르면 바로 업무 패널을 연다. 진행 건이 없으면 적용 가능한 게시 절차를 읽어 목표·단계·필수 입력을 보여준다. 질문·절차 열람·단순 선택으로 진행 건을 생성하지 않는다.
2. 사용자가 명시해 연결한 접근 가능한 진행 건을 우선한다. 명시 연결이 없고 같은 범위의 이어갈 건이 하나면 그 건을 제시한다. 여러 건이면 이름·구분 가능한 대상·상태로 선택하게 하며 임의의 최신 건을 선택하지 않는다. 이 선택 전 질문은 정의 기준, 쓰기는 대상 확정 후 수행한다.
3. 이어갈 건이 없을 때 최초 `입력 반영·저장` 또는 `실행` 의도에서 생성·연결을 내부적으로 처리한다. 대상 공장·시스템·프로세스를 확정하고 필요한 생성 조건만 한 번 받는다. 잡 선택에서 시작해도 진행 건은 상위 프로세스 단위로 만들고 해당 J를 선택한다.
4. 첫 쓰기는 생성과 후속 입력/실행 사이의 실패·재시도를 다룰 서비스 계약이 필요하다. 동일 요청 재전송으로 건·실행을 중복 생성하지 않는다. 최초 요청 식별자와 확정 대상·생성된 건의 연결을 기존 업무 저장소에서 복구할 수 있게 하고, 같은 요청의 재시도와 사용자가 명시한 별도 새 실행을 구분한다. 생성만 성공하고 후속 단계가 실패하면 생성한 건을 유지·표시해 이어가며, 실행 실패 기록을 삭제해 새 시작처럼 만들지 않는다. 이 처리가 없는 상태에서 시작 버튼만 숨기는 구현은 수락하지 않는다.
5. 완료 기록은 보존한다. 완료 건만 있으면 최근 완료 결과·이력을 열고, 프로세스의 `새 실행` 요청으로 새 기록을 만든다. 일반 질문이나 완료 J 선택을 새 실행 의도로 해석하지 않는다.
6. 진행 건은 시작 때의 절차 버전·적용 조건에 고정한다. Workspace의 새 게시가 기존 건을 재작성하지 않는다. 첫 저장 전 게시본이 바뀌면 선택한 정의와 새 정의를 대조하고 변경된 조건을 안내한다.

이 구조는 기존 한 사용자·한 저장 대화에 한 진행 건 연결의 경계를 우선 유지한다. 모든 공장에 빈 건을 미리 생성하거나 현재 소유 건을 다른 사용자에게 자동 공유하지 않는다. 공동 참여·역할·개인 대화 분리는 [공동 작업 설계](#shared-pilot-first)의 별도 후속 범위다.

### 5. 메인 대화와 업무 패널의 동기화

메인 대화는 기존 실제 WebUI 대화다. 업무 전용 대화창이나 별도 모의 AI를 제품에 넣지 않는다. 선택 업무의 공장·시스템·P/T/J와 진행 건을 가볍게 표시하되 범용 질문·기존 문서 조회·첨부·대화 이력도 유지한다. 업무 선택 전에는 대화로 후보를 찾을 수 있다.

진행 건이 없는 탐색에서는 화면의 공장·시스템·프로세스·노드·게시 버전을 **조회 전용 선택 맥락**으로 전달한다. 현재 화면의 `browseNodeId`만으로 기본 `ees_workflow_view`가 그 선택을 안다고 가정하지 않는다. 서비스는 전달된 ID의 소속·적용 가능성·권한·버전을 검증하며, 기존 대화에 연결된 다른 진행 건을 대신 조회하지 않는다. 맥락이 없거나 충돌하면 대상 확인만 하고 생성·연결 쓰기로 보정하지 않는다. AI 답변에는 `게시 절차 기준`과 `선택한 진행 건 기준`을 구분한다. 과거 이력을 설명할 때도 해당 기록을 읽기만 하며 현재 실행 연결을 바꾸지 않는다.

| 사용자 의도 | 대화에서 할 일 | 업무 상태 변화 |
|---|---|---|
| `처음인데 무엇부터 하나요?` | 게시 절차/해당 건의 고정 절차를 읽어 목적·선행 조건·다음 업무를 설명하고 해당 업무로 연결 | 읽기만 수행 |
| `왜 막혔나요?` | 저장된 결과와 누락 조건을 구분해 설명. 확인되지 않은 원인은 추정이라고 표시 | 읽기만 수행 |
| `점검 대상 작성 도와줘` | 필요한 값만 묻고 J의 필드에 맞는 초안을 제시 | 반영 전에는 저장된 입력·완료 상태 유지 |
| `이 값으로 반영해줘` 또는 초안의 반영 버튼 | 대상 J·변경 필드와 값을 표시하고 같은 입력 저장 동작 수행 | 해당 J에 입력 저장. 실행은 수행하지 않음 |
| `이 태스크 계속 진행해줘` | 현재 T의 범위·가능한 작업을 확인하고 같은 실행 동작 호출 | 실행한 J에 결과 저장, T/P 집계·패널 갱신 |
| `확인했으니 완료로 기록해줘` | 해당 사람 확인/검토 J와 확인 내용을 명확히 한 뒤 동일 완료 동작 호출 | 사람 확인으로 기록. 자동 점검 성공으로 기록하지 않음 |

- 초안은 작성 당시 공장·시스템·진행 건 또는 게시본·J·기준 revision에 묶는다. 다른 업무로 이동해도 초안의 대상이 자동 변경되지 않는다. 반영은 저장 직전 다시 대상·권한·revision을 확인하며, 충돌 시 최신값과 초안을 비교해 필요한 차이만 다시 판단한다. 새로 입력한 값이나 다른 사용자의 변경을 덮지 않는다.
- 폼에 타이핑한 값도 아직 반영 전의 임시값이다. UI와 대화 초안 모두 **저장 성공 후** 서버의 입력 무효화 규칙을 적용한다. 입력·초안·선행 결과 변경으로 영향받는 J와 후속 J는 재점검이 필요해지고 이전 성공은 이력으로 남는다. 관계없는 형제 결과까지 초기화하지 않는다.
- 같은 페이지 세션의 업무 이동·패널 닫기/열기·조회 갱신에서는 J별 임시값을 대상과 함께 보존한다. 서버 조회값으로 조용히 덮거나 자동 저장하지 않는다. 브라우저 전체 새로고침을 넘는 미저장 값 영속화는 이번에 새로 추가하지 않으며, 기존 저장 초안은 복원한다. 미저장 표시·기존 이탈 안내로 저장 여부를 구분하고 임시값을 저장된 것으로 표시하지 않는다. 기존 제품이 제공하는 보존 동작을 제거하지 않고 후속 구현에서 현재 경로와 대조한다.
- 현재 유효한 결과가 사라지면 `재점검 필요`와 이유를 표시한다. 과거 결과를 보여줄 때는 `이전 결과`로 구분하고 당시 입력·절차·시각·사람 확인/모의 결과를 함께 보존한다. 전체 완료 건·과거 기록에 초안을 반영하지 않는다.
- 자연어의 실행 의도가 명확하고 대상이 정해졌으면 실제 지원 범위에서 수행한다. 포괄적인 `다 해줘`를 사람 확인·외부 발행 승인·절차 게시로 해석하지 않는다. 지침을 조회하는 것과 사용자를 대신해 확인했다는 기록을 만드는 것을 구분한다.
- 명령 접수 시 대상과 revision을 고정한다. 실행 중 사용자가 다른 업무를 선택해도 결과는 원래 실행한 건/J에 저장한다. 완료 안내에는 원래 업무 이름과 결과 열기 동작을 제공하고 현재 선택·폼을 강제로 덮지 않는다. 입력 반영 뒤에도 현재 위치를 강제로 바꾸지 않고 대상 업무 열기를 제공한다.
- 실행 결과 저장 성공과 UI 갱신 실패를 구분한다. 화면 갱신 실패 시 상태를 다시 조회하며 실행을 반복하지 않는다. 연속 클릭·같은 요청 재전송·오래된 revision의 변경은 공통 서비스 경로에서 제어한다.

기존 액션 이름과 사용자 의미를 구분한다. 입력 반영은 현재 `update_inputs`, 문서형 잡의 초안 저장은 현재 `run(document)` 후 `review`, 사람의 검토 완료는 별도 `confirm:true` 경로다. 따라서 `run`이라는 내부 이름만으로 초안 저장을 자동 점검·발행으로 취급하지 않는다. 문서형 잡의 검토 초안과 대화에서 제안하는 필드 입력 초안도 각각 원래 저장 계약을 사용한다. 새 안내·버튼·자연어 요청은 같은 의미의 기존 서비스 동작에 연결하고, 없는 첫 쓰기 확보·조회 맥락·재시도 보호 계약만 필요한 범위에서 보완한다.

### 6. Workspace와 기존 디자인의 통합

업무 절차는 기존 Workspace 본문·탭·서체·색상·버튼·입력폼을 사용한다. 큰 별도 제목, 겹친 외곽 카드, 독립 페이지 여백, 개발자용 문구를 줄인다. 업무 구조와 선택 노드의 상세 편집을 중심으로 정리하며 기존 `업무 구조 / 도구 연결 / 스킬·지침 / 적용 조건`의 관리 기능을 보존한다. 화면별 저장 단위처럼 보이더라도 실제 저장·구조 검증·게시는 기존 전체 초안 단위를 유지하고 그 범위를 표시한다.

일상 패널은 업무에 필요한 기준·근거만 보여준다. 실행에 쓰이는 프로젝트/지식기반·프롬프트·스킬·도구 등의 자산은 Workspace에서 관리한다. 다만 현재 저장 계약에 있는 도구·스킬·지침과, 아직 명시적 연결 계약이 없는 프로젝트/지식기반·프롬프트를 구분한다. 이 설계만으로 후자의 자동 적용을 표시하거나 새 자산 관리 체계를 만들지 않는다. 자산 작성·편집은 기존 Native 기능으로 연결하고 Git에 없는 사용자 자산도 보존한다.

대화의 `이 잡 입력값을 바꿔줘`와 `절차·완료 기준·자산 연결을 바꿔줘`는 서로 다른 변경이다. 후자는 권한 있는 Workspace 편집의 **전체 초안 → 구조 검증 → 명시적 게시** 흐름을 따른다. 현재 AI가 지원하는 공개 동작까지만 실행하고 지원이 없으면 해당 편집 위치로 안내한다. 자연어 요청이 현재 진행 건의 고정 절차를 바꾸거나 자동 게시하는 통로가 되어서는 안 된다.

데스크톱에서는 실제 중앙 대화와 오른쪽 업무 패널의 기존 열기·닫기·폭 조절을 유지한다. P/T 목록은 이름·진행·상태 열을 정렬하고 J는 결과·입력·다음 조치를 묶는다. 기존 번들 글꼴·명암·테마·포커스 표시를 재사용하며 상태는 색상과 문구를 함께 사용한다. 좁은 화면에서는 줄바꿈과 기존 패널 전환 방식을 사용하고, 대화 목업의 모바일 상하 배치를 제품 동작 변경 지시로 해석하지 않는다. 실제 1920×1080·좁은 창·밝은/어두운 테마의 사용자 확인은 구현 후 별도다.

### 7. 구현 시 나눌 작업과 수락 기준

아래는 09-16에 정한 구현 순서이며 후속 구현·배포 승인에 따라 09-17부터 적용한다. 새 모델·대화 엔진·실행 서버·DB 제품·현황판을 선행 도입하지 않는다. 기존 `ees-work-view.js`·controller·designer와 업무 조회/액션 서비스 경계를 재사용한다. 09-15의 표시 변경과 달리 시작 진입·초안 대상·쓰기 재시도는 서버/Tool 계약까지 검토한다.

| 순서 | 후속 작업 | 반드시 확인할 결과 |
|---|---|---|
| 1 | 공통 패널 표시와 P/T/J 정보 정리 | 직속 하위만 표시, 정확한 분모·제외, 업무용 상태/다음 행동, 설정은 Workspace, 부모 실행 유지 |
| 2 | 게시 절차 상시 탐색·첫 쓰기의 생성/연결 | 읽기만으로 건 생성 없음, 기존 건 이어가기·복수 건 선택, 중복 생성 방지·부분 실패 복구, 완료 건 보존 |
| 3 | 대화 설명·초안·명령과 같은 업무 상태 연결 | 초안/저장/실행 구분, 대상·revision 검증, 같은 액션/권한/결과, 다른 업무로 이동해도 원래 대상에 반영 |
| 4 | 기존 Workspace와 통합 마무리 | 전체 초안 저장·검증·게시 유지, 등록 자산·모델 보존, 실제 대화·기존 조회·패널 조작 유지 |

후속 검수는 다음 사용자 흐름을 기준으로 필요한 범위만 수행한다. 아래는 **시험 설계이며 제품 시험 PASS 기록이 아니다.**

1. 처음 온 직원이 사이드바 또는 대화로 업무를 찾고 `무엇부터?`를 질문한다. 절차·용어·다음 업무를 이해할 수 있고 진행 건·확인 기록은 생기지 않는다.
2. P에서 직속 T, T에서 직속 J로 내려가 결과와 필요한 입력을 찾는다. 부모의 진행 수는 실제 하위 상태와 일치하고 적용 제외·미수행·미연결을 혼동하지 않는다.
3. AI가 J 입력을 제안한다. 반영 전 상태는 불변이고 반영 뒤 같은 J의 입력만 저장된다. 실행은 별도 의도에서 수행한다. 직접 입력과 AI 반영의 결과가 같다.
4. 초안을 만든 뒤 다른 업무로 이동하거나 누군가 값을 바꾼다. 원래 대상과 최신 revision을 확인하고 잘못된 업무 반영·덮어쓰기를 방지한다.
5. 자동 점검과 사람 확인이 섞인 T/P를 진행한다. 가능한 점검만 실행하고 사람 확인을 만들어내지 않으며 실패·독립 진행·선행 대기를 구분한다.
6. 첫 저장/실행 요청을 재전송하거나 생성 뒤 통신이 끊긴다. 같은 건·같은 실행을 중복 생성하지 않고 저장된 결과로 복구한다. UI 갱신 실패가 재실행으로 이어지지 않는다.
7. 진행 중인 J의 입력·초안을 변경한다. 영향받는 결과만 재점검 상태가 되고 과거 결과·입력·시각은 이력에 남는다. 완료 건과 과거 이력의 읽기 전용은 유지한다.
8. 결과 조회 중 다른 업무를 선택해도 원래 실행 대상에 기록된다. 일반 채팅·문서 조회·기존 대화·폼 초안·GLM 5.3 설정·사용자 자산을 보존한다.

실제 실무 절차·완료 기준·도구 연결과 공동 작업 권한은 별도 후속 구체화 대상이다. 현재 합성 셋업 예시와 모의 DB/AP 점검을 운영 검증으로 확대하지 않는다. 위 설계 검토를 브라우저 사용성·사내 모델 호출·구현·설치 성공으로 보고하지 않는다.

### 8. 2026-09-17 구현과 전달 계약

프로그램 ees.10과 Agent Pack v0.2.11에서 위 설계를 같은 기존 업무 서비스·패널·Native 대화에 연결한다. 현재 제품 구현과 시험 범위는 [구현 평가 기록](../../../evals/scenarios.md#work-panel-chat-implementation-20260917)을 따른다.

- P/T는 직속 하위 목록과 상태별 주요 행동을 표시하고, 부모의 가능한 점검은 실패한 J의 자동 재실행·사람 확인 완료와 분리한다. J는 저장된 결과·입력/초안·필요한 업무 안내를 보여주며 수행 내역은 펼쳐서 확인한다. 등록 도구·스킬 원문 등 설정은 기존 Workspace로 모은다.
- 게시 절차의 선택 맥락은 공장·시스템·프로세스·노드·게시 버전으로 조회하며 진행 건을 만들거나 다른 건을 연결하지 않는다. 첫 저장/실행은 확정 범위와 요청 식별자를 받고, 같은 요청은 저장된 처리 결과로 복구한다. 같은 범위의 기존 건은 선택 후 이어가고, 완료된 기록만 있으면 명시적인 새 실행을 구분한다. 생성 뒤 업무 단계 실패는 생성된 건과 실패 결과를 남긴다.
- Native Workflow Tool 0.3.0은 조회에서 받은 대상을 변경 요청에 고정하고 현재 화면 대상과 다시 대조한다. 응답을 잃은 요청은 같은 식별자로 재조회/재전송하며 최신 revision을 추측해 새 변경으로 바꾸지 않는다. 게시 절차·현재 진행·과거 이력의 조회를 구분하고 과거 이력에서는 쓰지 않는다.
- J별 임시값은 작성 당시 범위와 연결해 보존한다. 저장 전에 이동·서버 변경·충돌을 확인하고, 입력 반영과 실행/확인을 구분한다. 서버가 완료하거나 무효화한 결과를 임시 입력의 성공으로 표시하지 않는다.
- `ees-work.sqlite3`의 요청 기록 테이블 추가는 기존 정의·진행 건·이력 자료를 유지한다. 프로그램 Restore는 DB·Agent Pack을 되돌리지 않으며, 이전 프로그램에서 새 Workflow Tool 계약은 지원하지 않는 것으로 안내한다. 실제 호환 범위는 [버전 기준](../../../versions.md#open-webui-대상-환경)을 따른다.

[09-17 적용 안내](../../03-openwebui-native-agent.md#ees-work-panel-trial-20260917)는 검증한 원본의 Update → Upgrade 시험 경로를 재사용하며 지정 자산 적용은 Upgrade가 수행한다. 실제 외부 업무 어댑터·팀 공동 소유·일정·새 Runtime은 이번 구현에 추가하지 않는다. 별도 후속 설계를 이번 화면 구현의 배포 조건으로 확장하지 않는다.

<a id="sidebar-refinement"></a>

<a id="work-panel-goal-design-20260915"></a>

## 2026-09-15 목표에 맞춘 업무 패널 설계

**잡을 수행·점검하는 방법과 근거를 쌓고, 검증된 잡을 조합해 태스크·프로세스의 자동화 범위를 넓히며, 같은 업무를 AI와 자연어로 관리한다.** 아래는 09-15 당시 설계·구현 범위이며 PR #52에 병합되었다. 이후 합의한 표시·시작·대화는 위 [09-16 상세 설계와 09-17 구현 계약](#work-panel-chat-design-20260916)을 우선한다. 현재 셋업 트리는 합성 참고 예시이고, 실제 실무 절차와 공동 참여 범위는 [후속 합의](#setup-first)를 따른다.

### 화면별 역할과 표시 순서

| 위치 | 사용자가 판단할 일 | 우선 표시 | 실행·편집의 역할 |
|---|---|---|---|
| Workspace 업무 절차 | 이 업무를 어떻게 반복 수행할 것인가 | 업무 구조, 적용 조건·선행 관계, 잡 수행 방식·입력 매핑·완료 기준, 참조 도구·스킬·지침 | 전문가가 절차를 저장·구조 검증·게시. 현재 여러 프로세스를 포함한 하나의 초안 단위 유지 |
| 프로세스 패널 | 전체 목표까지 무엇이 남았고 어느 범위까지 이어서 실행할 수 있는가 | 목표·완료 기준, 적용 잡 완료 수/제외 수, 태스크별 진행, 먼저 확인할 잡과 사유, 하위 자동 점검 범위 | 자동 점검을 묶어 실행하고, 사람 확인·미연결·오류가 남은 잡으로 이동 |
| 태스크 패널 | 이 단계가 끝나려면 무엇을 충족해야 하는가 | 단계 목적·완료 기준, 선행 작업, 하위 잡의 수행 방식·상태, 필요한 다음 행동, 이 단계의 자동 점검 범위 | 잡별 입력·결과로 이동하거나 해당 태스크의 자동 점검 실행 |
| 잡 패널 | 무엇을 입력하고 어떻게 수행하며 무엇으로 완료를 판단하는가 | 수행 방식·완료 기준, 최근 결과와 다음 행동, 입력/초안·수행 버튼, 도구 순서·적용 지침·근거·이전 시도 | 사람 확인/초안 검토/연결 점검 구분. 실패 결과를 보존하고 필요한 값을 보완해 재시도 |
| 가운데 AI 대화 | 같은 업무를 자연어로 찾고 계획·진행·확인할 수 있는가 | 현재 범위, 수행 계획, 부족한 값/사람 확인, 실행 결과·근거·다음 행동 | 기존 업무 조회/액션으로 화면과 같은 상태·권한·revision·결과 저장 사용 |

도구·지침·프롬프트는 자동화에 필요한 자산이고 잡은 이를 적용하는 실행 단위다. 태스크·프로세스는 잡을 조합하고 진행 조건을 관리한다. 일상 담당자에게 도구나 모델 선택을 요구하지 않는다. Workspace의 자산 관리와 실제 진행 건의 수행/이력 편집을 섞지 않는다. 도구·스킬의 기존 UI 참조는 유지하며, 지식기반·프롬프트의 명시적인 잡 연결은 현재 저장 계약에 없으므로 연결된 것처럼 표시하지 않는다.

### 현재 데이터로 구현할 범위

1. P/T에 같은 카드를 복제한 현 화면을 위 역할에 맞춰 분리한다. 완료 기준은 기존 `rule`과 적용 대상 하위 잡 완료 조건을 함께 표시한다. `rule` 문구를 실행 엔진이 해석해 판정한다고 설명하지 않는다. 진척은 서버의 `node_states.progress`·`excluded_count`를 사용하며 시간·자동화율로 해석하지 않는다. 현재 점검은 모의 실행이므로 상단에서 **예시 진행**임을 밝히고 실제 공장 완료율로 표시하지 않는다. 적용 대상이 0개인 경우 전체 통과가 아닌 적용 제외로 표시한다.
2. P에서는 직계 태스크별 완료 수와 제외 수를, T에서는 잡별 사람 확인/초안 검토/모의 점검/실행 연결 필요 구분과 현재 상태를 보여준다. 부모의 `mode`로 자동화 여부를 판단하지 않는다. 원래 하위 선택·`run` 액션을 유지하며 새 일정·담당자·공유 상태·자동화 점수를 만들지 않는다.
3. 다음 할 일은 미완료·적용 대상 잡과 선행 조건을 근거로 제시한다. 자동 실행 가능을 보장하는 문구를 쓰지 않고, 사람 확인·초안·입력 보완·실행 연결 필요·앞선 실패/대기 사유를 설명한다. 클라이언트는 안내만 계산하며 최종 입력/권한/스킬/선행 검증과 실행 여부는 기존 서버가 판단한다. 하위 전체의 스킬 접근 권한을 현재 선택 노드의 스킬 정보로 추측하지 않는다.
4. P/T의 일괄 실행을 유지하되 버튼은 현재 기능에 맞춰 `하위 예시 점검 실행`으로 표시한다. 실행 전 범위에 적용 대상 미완료 잡의 모의 점검 수·사람 확인/검토 수·미연결 수를 보여주고, 선행이 충족되는 점검만 진행됨을 설명한다. 이 집계는 실제 이번 실행 예정 수가 아니다. 사람 확인 단계의 후속은 대기하며 독립적인 다른 잡은 계속될 수 있다. 모의 연결만 있는 현 구현을 실제 자동화 완료로 표현하지 않는다.
5. J는 사람 확인·초안 검토·도구 점검의 완료 버튼과 기준을 구분한다. 저장된 최근 결과/확인 기록과 실패 뒤 다음 행동을 입력폼보다 먼저 표시한다. 현재 결과가 입력/초안 수정이나 선행 잡 재실행으로 무효화되면 과거 성공을 최신 성공처럼 노출하지 않고 이력으로 보존한다. 점검 내부 `skipped`는 **미수행**, 조건으로 빠진 노드의 `skipped`는 **적용 제외**로 구분한다. `blocked`를 모두 선행 작업 대기라고 부르지 않는다.
6. 도구 순서·점검 기준·참조 지침/스킬을 유지한다. 체크 근거와 시도별 입력·초안·사람 확인·실패/미수행은 저장된 기록 범위에서 열어 볼 수 있게 한다. 수동 잡의 자유형 확인 메모 저장은 현재 없으므로 새 메모 폼을 만들지 않는다. `updated_at`을 실행 시각으로 쓰지 않고 시도 기록의 시각을 사용한다. 완료 건·이력은 읽기 전용이다. 과거 이력 조회는 현재 채팅·선택을 바꾸지 않고, 완료된 현재 건은 기존 P/T/J 탐색을 유지한다. 계층별 목적·기준은 시작 전 미리보기에도 표시하되 실행 전 결과를 만들어 보여주지 않는다. 완료 건·과거 이력에도 저장된 사람 확인/모의 결과·시각·입력/초안 근거를 적용한다. 과거 프로세스/태스크에서 하위 잡의 기준·근거까지 펼쳐 볼 수 있게 하며 현재 실행의 `select` 액션은 호출하지 않는다. 기존 AI의 `case_id` 읽기 조회는 같은 하위 자료를 제공한다.
7. Workspace는 앞서 작성한 Native 여백·서체·버튼·회색 입력폼 정리를 유지한다. `검증`은 **구조 검증**으로 명확히 하고, 게시나 구조 검증 성공이 실제 실행 연결/점검 성공을 의미하지 않음을 짧게 설명한다. 별도 새 HTML 화면이나 자산 편집기를 만들지 않는다. 사이드바 제목은 `업무`로 유지한다.

### 영향과 검토 기준

- 제품 변경 위치는 `branding/ees/ui/ees-work-view.js`의 표시·기존 폼과 `ees-work-designer.js`의 검증 안내이며, 필요한 소규모 스타일만 기존 CSS에 둔다. 서버·Tool API·저장 형식·자산 등록·모델 연결·권한·배포 래퍼를 바꾸지 않는다. 후속 실제 실행 연결은 이 패널의 입력/기준/결과 구조를 사용하되 별도 업무 단위로 설계·검증한다.
- 기능 검토는 P/T/J 역할 차이, 부모 자동 실행 유지, 등록/연결/구조 검증/실행 결과 구분, 사람 확인과 모의 근거, 입력 수정 후 무효화/이력, 버튼·AI 공통 액션 보존을 확인한다. 목표와 무관한 현황판 장식·추상 실행 엔진·중복 준비 상태 저장을 추가하지 않는다.
- 검사는 실제 서버가 만든 합성 진행 건으로 표시 결과/경계 조건을 확인하고, 기존 부모 실행·사람 확인·미연결·입력 변경/이력 시험과 배포 JS 조립/구문·문서 점검을 수행한다. 새 표시 검사는 문구만 복제하지 않고 입력 미충족/선행 대기/실패·재시도/완료 읽기 전용을 다룬다. 브라우저·Windows·사내 GLM 5.3은 실행한 범위만 기록한다.
- 전체 목표의 후속 범위는 실제 업무 절차 확정 → 승인된 도구 연결과 잡의 실제 결과 검증 → 태스크/프로세스의 자동 수행 범위 확장이다. 기존 메인 채팅 조회/액션 경로를 계속 사용한다. 공동 작업·개인 대화 분리와 명시적인 프롬프트/지식기반 연결은 각각 현재 미구현 계약을 먼저 정한다.

설계 검토 결과와 구현·시험 결과는 [기존 평가 기록](../../../evals/scenarios.md#workspace-native-design-20260915)에 이어서 남기며, 기록만으로 실제 사내 반영을 뜻하지 않는다.

<a id="workspace-native-design-20260915"></a>

## 2026-09-15 업무절차 편집 화면과 자동화 목표

사용자는 잡을 수행·점검할 도구, 지침, 프롬프트 등의 자산을 등록·보완하고 검증된 잡을 연결해 태스크와 프로세스의 자동화 범위를 넓히며, 같은 업무를 AI와 자연어로 관리하는 목표를 재확인했다. 자산 등록, 실제 실행 연결, 결과 검증을 구분한다. 미연결 도구를 등록만으로 실행 가능하게 표시하지 않고 사람 확인이 필요한 단계는 임의로 완료하지 않는다. 화면과 채팅은 같은 업무 액션·권한·결과를 사용한다. 현재 구현의 지원 범위와 후속 자동화 목표를 혼동하지 않는다.

- Workspace의 업무 절차 탭을 기존 모델·지식기반·프롬프트·스킬·도구와 같은 디자인에 맞춘다. 고정 Open WebUI 0.11.3의 Workspace 본문 정렬·회색 계열·글꼴·버튼·입력폼을 기준으로 하며, 별도 큰 제목과 이중 여백·카드 테두리를 줄인다.
- 현재 여러 프로세스와 연결 자산은 하나의 절차 초안으로 저장·검증·게시한다. 이 의미를 유지하며 처음부터 프로세스별 독립 자산·저장 단위로 바꾸지 않는다. 기존 업무 구조·도구 연결·스킬/지침·공장 조건의 편집 기능과 필드, 미저장 변경·검증 상태를 유지한다.
- 외형 변경은 업무 절차 영역에 한정하고 Native 탭의 배치·복원·접근 권한과 개인 설정을 보존한다. 기존 사용자 자산과 사내 UI에 반영한 GLM 5.3 연결을 재등록하거나 덮어쓰지 않는다. 모델 기준은 [versions](../../../versions.md#사내-모델-운용-기준)를 따른다.
- 사이드바 제목은 `업무 · 현재 진행`에서 `업무`로 줄인다. 각 진행 건·노드의 실제 상태와 실행 이력은 유지한다. 당시 Workspace 외형 변경에서 제외한 P/T/J 패널은 후속 사용자 지시에 따라 위 [목표 기반 설계](#work-panel-goal-design-20260915)로 검토 후 진행한다.
- 확인 조건은 실제 조립 JS의 구문/포함, 기존 공개 action·폼 필드 보존, 다른 Workspace 탭과의 전환 및 미저장 초안 유지, 밝은/어두운 화면과 축소 창에서의 가독성이다. 브라우저·사내 확인을 수행하지 못하면 소스 검사와 구분해 기록한다. [검증 기록](../../../evals/scenarios.md#workspace-native-design-20260915).

## 2026-09-14 사이드바 후속 목업 승인

사용자는 P/T/J 설명 행 제거, 프로세스 펼침 시 직계 태스크만 노출, 기존 WebUI와 새 영역의 글꼴 통일, 작업 공장·시스템 선택 디자인 개선을 요청했다. 후속 목업을 확인한 뒤 기존 WebUI 안에 최대한 자연스럽게 반영하도록 승인했다.

- 별도 `P 프로세스 · T 태스크 · J 잡` 설명 행만 제거하고 각 노드의 P/T/J 표식과 접근성 이름은 유지한다.
- 펼침 화살표와 업무 선택을 구분한다. 프로세스는 직계 태스크만, 각 태스크는 직계 잡만 펼친다. 부모를 접었다가 열거나 상태를 갱신해도 사용자가 접은 하위가 일괄로 다시 열리지 않는다. 다른 공장·시스템·진행 건의 동일 노드 ID와 혼동하지 않는다.
- 공장과 시스템은 한 선택 영역의 두 행으로 배치한다. 현재 국가·공장과 시스템을 명확히 표시하고 목록의 선택 상태·키보드 조작·닫기·좁은 사이드바를 지원한다. 기존 공장 전환과 초안 보존 경로를 재사용한다.
- 기존 번들 Inter/Noto Sans KR를 채팅·사이드바·업무 패널·Workspace에서 일관되게 사용한다. 글꼴 이름뿐 아니라 메뉴의 크기·굵기·색상도 맞추며 코드·수식의 전용 글꼴은 유지한다. 사외 소스 대조만으로 사내 실효 폰트 로딩을 확정하지 않는다.
- 이번 프로그램 후보는 `0.11.3+ees.8` / `/_ees8/`이다. Agent Pack v0.2.9는 새 프로그램에서 기존 전문 Tool의 정확한 버전 호환성을 유지한다. 업무 API·권한·저장 구조·실제 대화는 유지하며 공동 작업 기능을 추가하는 변경이 아니다.

이 절의 최신 UI 기준이 아래 ees.7 당시 표현보다 우선한다. 목업의 예시 대화·ChatGPT 아이콘 런타임은 제품에 삽입하지 않는다. 구현·검사·사내 반영은 [현재 상태](../../STATUS.md)와 [검증 기록](../../../evals/scenarios.md#sidebar-refinement-20260914)에서 구분한다.

## 2026-09-14 요구사항 정정

최초 지시의 ‘EES Work 시연 버튼으로 별도 화면 열기’와 ‘가운데 AI 응답까지 모의 처리’는 사용자의 의도와 달랐다. 이 지시에 따라 ees.5에 별도 시연 창을 구현했고 사용자가 사내 화면에서 차이를 확인했다. 당시 구현·검사 기록은 [기존 평가 기록](../../../evals/scenarios.md#ees-work-demo-integration-20260914)에 보존한다. 해당 구현의 검사 통과는 아래 통합 요구 충족을 의미하지 않는다.

현재 승인된 목표는 **기존 Open WebUI의 사이드바·실제 AI 대화창·오른쪽 업무 패널·워크스페이스를 활용해 목업의 업무 구조를 구현하는 것**이다. 별도 데모 앱이나 모의 채팅으로 대체하지 않는다. 원본 HTML은 화면 구성과 업무 예시의 참고자료이고, 실행 구조가 충돌하면 이 정정된 지시와 후속 사용자 합의를 따른다. 구현·검증·문서·커밋·push·PR 생성 또는 갱신까지 수행하고, 실제 사내 반영 여부는 [STATUS](../../STATUS.md)에서 구분한다.

### ees.7 구현 기준 — 공장별 업무 트리와 기존 WebUI 스타일

사용자는 워크스페이스의 업무 절차 진입·내용을 확인했고, 업무 탐색의 혼란과 새 업무 절차 탭의 글꼴·반복 깜빡임을 보고했다. 이 보고의 정확한 사내 설치 SHA는 미확인이다. 후속 목업에서 합의한 **공장·시스템 선택 → 셋업·운영·장애대응 → 프로세스·태스크·잡 트리**를 기존 사이드바 안에 구현한다. 목업의 구조와 동작을 따르되 글꼴·버튼·입력창·탭·테마는 기존 WebUI와 맞추며, 서비스 표시 이름은 **EES Work**로 통일한다. 현재 대상은 프로그램 `0.11.3+ees.7`·정적 자산 `/_ees7/`·Agent Pack v0.2.8이며 ees.5/ees.6의 당시 구현·검증 근거는 보존한다.

<a id="ees-work-shared-target"></a>

### 2026-09-14 최신 합의 — 공장·시스템 단위의 공동 작업

**최종 목표는 여러 담당자가 같은 공장·시스템의 업무를 함께 진행하고, 작업 상태·결과·이력을 다음 담당자와 다음 세션에서도 이어가는 플랫폼이다.** 이번에는 합의를 문서에 기록한다. 아래 공동 작업은 후속 구현 목표이며, ees.8까지의 사용자별 진행 건 격리·개인 대화 연결을 팀 공유 구현 완료로 해석하지 않는다. 2026-09-15 ees.8 사이드바 UI 네 항목의 사내 확인은 완료됐고 실제 적용 원본·공동 작업 상태는 [STATUS](../../STATUS.md)에서 구분한다.

**확정한 구조와 동작**

- 탐색 계층은 **공장 → 시스템 → 업무(셋업·운영·장애대응) → 프로세스 → 태스크 → 잡**이다. 국가·공장 정보를 보여주고, 선택한 공장 안의 시스템 담당자가 해당 업무에 진입한다. 기존 사이드바에서 트리를 펼쳐 큰 작업과 세부 작업을 오가며, 가운데는 기존 실제 AI 대화창, 오른쪽은 선택 단계의 작업 패널로 유지한다. 새 독립 데모나 별도 모의 채팅을 만들지 않는다.
- 공동 작업의 진행 건은 특정 공장·시스템·업무에 속한다. 같은 진행 건의 상태·업무 결과·실행 이력을 담당자들이 권한에 따라 함께 확인하고 이어간다. 완료한 작업과 진행 중인 작업은 트리 상태와 실행 이력으로 구분하고, 담당자·화면·대화가 바뀌어도 기존 기록을 유지한다. 완료 이력을 덮어쓰거나 새 실행을 기존 실행의 연속으로 임의 선택하지 않는다.
- **공유 업무 기록과 개인 AI 대화 기록·개별 권한은 별도로 관리한다.** 같은 진행 건을 다루더라도 다른 사람의 채팅을 자동으로 공유하지 않는다. 업무가 공유된다는 이유만으로 상대의 문서·도구 접근 권한이나 개인 자격증명을 함께 사용하지 않으며, 각 사용자가 허용된 범위에서 작업한다.
- Workspace는 전문가·관리자가 업무 절차를 만드는 공간이고, 사이드바는 담당자가 게시된 절차로 실제 진행 건을 수행하는 공간이다. 시스템 전문가가 비개발자용 폼으로 P/T/J 구조·적용 조건·선행 작업·도구 매핑·스킬·지침을 편집한다. 기존 모델·지식기반·프롬프트·Tools·Skills 기능과 글꼴·탭·테마를 재사용하며, 필요한 스킬·지침 작성도 해당 기존 편집 기능과 연결한다.
- 국가·공장·시스템, 라인·인프라 재사용·시스템 간 연계 등 현장 조건에 따라 적용 단계가 달라진다. 공통 절차의 게시 버전과 실제 진행 건을 구분하고, 시작 당시 절차·조건·결과를 유지한다. 새 게시본을 진행 중인 공동 작업에 자동으로 덮어쓰지 않는다.
- 대표 프로세스는 **P 신규 공장 횡전개**이며, 하위는 **T 사전준비 → T AP, DB 인프라 준비 → T 시스템 설치 → T 각 시스템간 인터페이스 확인**이다. 시스템 설치 아래에 **J DB 연결 확인·J AP 연결 확인** 등을 둔다. 잡 하나에 여러 도구를 순서와 입력 매핑으로 연결하고, 개별 점검 결과에 따라 성공·실패·후속 미수행을 판정한다. P/T/J별 스킬·지침·도구 연결을 지원하되 자동 실행·판정은 구현된 연결의 범위에서만 수행한다. 현재 DB/AP 점검은 합성 예시이며 실제 공장 점검 성공으로 기록하지 않는다.
- 오른쪽 패널은 프로세스의 전체 진행·다음 할 일, 태스크의 목적·선행 조건·하위 잡, 잡의 입력·도구 순서·판정 기준·결과·근거·실패 이력을 보여준다. AI 요청과 패널 조작은 같은 업무 액션·권한·결과 저장 경로를 사용한다. 작은 잡부터 실제 자동화를 연결해 범위를 넓힌다.

**구현 전에 구체화할 사항 — 아직 확정·구현되지 않음**

- 공장·시스템별 참여자 등록과 열람·수행·편집·게시 역할, 작업 담당·변경 주체 표시 범위. 기존 개인 권한을 보존하면서 필요한 역할만 정한다.
- ees.7의 사용자별 기존 진행 건을 공동 작업으로 옮길 대상·이관 방법과, 기존 개인 대화 연결·이력을 보존하는 방법. 기존 데이터를 자동으로 공개하거나 전부 이관하기로 합의한 것은 아니다.
- 개인 대화와 공유 업무 기록의 연결 방식, 업무에 남길 결과·요약·근거·첨부의 범위. 누가 무엇을 볼 수 있는지 정하고, 대화 원문·개인 비밀을 자동 복제하지 않는다.
- 여러 담당자의 동시 수정·실행에서 중복 실행·충돌을 어떻게 알리고 처리할지, 실패·재시도와 변경 이력을 어떻게 일관되게 보존할지. 이를 정하기 전에 별도 DB 스키마·API·서비스 구조를 확정하지 않는다.

<a id="shared-pilot-first"></a>

### 2026-09-15 첫 공동 작업 단위와 팀 사용 우선순위

**사용자가 선택한 첫 단위는 공장 1개·시스템 1개·프로세스 1개를 2~3명이 함께 처리하는 것이다.** 목표는 UI/UX를 빠르게 다듬어 실제 팀원이 업무를 시작하고 이어받게 하는 것이다. 사용자는 업무 트리를 활용한 진척·일정 현황판에 관심을 표현하고 개발 시점을 질문했다. 현황판 전체 범위나 일정 관리 기능을 첫 단위에 추가하기로 확정한 것은 아니다.

첫 단위의 구현 방향은 기존 공장·시스템 선택 → 공유 진행 건 찾기/시작 → 다음 할 일 확인 → 입력·실행·완료 → 다른 담당자가 이어가기이다. 공동 진행 건·참여 범위·변경 주체와 충돌 안내를 정의하면서 개인 대화·초안·선택 단계는 사용자별로 유지한다. 기존 개인 진행 건은 자동으로 공개하지 않는다. 버튼과 AI는 같은 권한·액션·결과 저장 경로를 사용하며 완료된 사이드바 외형 검사를 반복하는 것을 새 기능의 선행조건으로 두지 않는다.

<a id="setup-first"></a>

**첫 업무 영역과 후속 정정(2026-09-15): 셋업을 우선하되 실제 의미 있는 절차는 새로 정의한다.** 사용자는 기존 흐름이 임의 예시임을 명확히 하고 실제 업무 절차를 새로 만들겠다고 정정했다. 기존 **셋업 → 신규 공장 횡전개**는 화면·검증의 참고 예시이며 확정된 사내 실무 절차가 아니다. 공장 1개·시스템 1개·참여자 2~3명의 첫 단위는 유지한다. 실제 파일럿 공장·시스템·참여 계정은 아직 지정되지 않았다.

- 기존 **사전준비 → AP, DB 인프라 준비 → 시스템 설치 → 각 시스템간 인터페이스 확인** 트리는 참고·회귀 검증 자료로 보존한다. 실제 새 절차에 이 단계·입력을 강제하지 않는다. 운영·장애대응 절차는 보존하고 첫 공동 작업 구현·확인의 대상은 셋업으로 한정한다.
- 첫 사용 흐름은 참여 가능한 셋업 진행 건 찾기/시작 → 현재 단계·다음 할 일 확인 → 입력·실행/사람 확인 → 다른 담당자가 이어가기이다. 기존 업무 목록·트리·오른쪽 패널에서 완료 수·막힌 이유·담당/수행자를 연결하며 일정표·간트·공장별 종합 현황판은 첫 사용의 선행 과제로 두지 않는 방향을 제안한다.
- 첫 수락 예시는 **A가 사전준비를 마치고 B가 같은 진행 건의 인프라 준비를 이어서 수행하며 두 사람이 같은 결과·진척·변경 주체를 확인하는 것**이다. 각자의 대화·초안·탐색 위치 보존과 동시 변경·권한·재접속 조건도 위 첫 단위의 기준을 그대로 적용한다.
- 기존 셋업은 태스크 4개·잡 6개이며 수동 확인 2개(셋업 범위, 설치·설정)와 모의 점검 4개(인프라, DB, AP, 인터페이스)로 구성된다. 실제로 확인한 준비·설치 항목은 사람 확인으로 기록할 수 있다. 인프라 준비를 실제 업무 인계로 사용할 때는 담당자 확인 방식과 게시할 실무 절차를 먼저 정한다. 모의 점검 결과를 실제 셋업 완료율에 섞어 표시하지 않으며, 실제 자동 점검은 승인된 API가 연결된 잡부터 별도 검증한다.

셋업 우선 범위는 확정됐으며, 참여자 등록·역할·공유 기록·개인 대화 연결·동시 실행 정책은 위 미결정 사항을 구체화한 뒤 구현한다. 이 우선순위 기록을 공동 작업 기능의 구현·사내 적용 완료로 표현하지 않는다.

<a id="chat-workflow-entry-20260915"></a>

**메인 채팅에서 업무 찾기·계획·진행 요구(2026-09-15):** 사용자가 메인 채팅에서 해야 할 일을 말하면 AI가 게시된 워크플로를 찾아 활용할 수 있어야 한다. 사이드바의 사전 선택을 필수로 하지 않으며, 직접 화면에서 선택하는 진입도 유지한다. 이 요구는 R0~R3 리팩토링의 기존 검수와 구분하는 업무 흐름이며, 후속 사용자 요청으로 아래 최소 구현을 같은 준비본에 반영했다.

- 사용자 목표에 맞는 프로세스와 접근 가능한 기존 진행 건을 찾고, 공장·시스템·대상 범위 중 빠진 값만 확인한다. 여러 후보가 있으면 선택 이유와 차이를 짧게 설명하고 필요한 구분을 묻는다. 임의의 최신 진행 건이나 예시 현장을 실제 대상으로 확정하지 않는다.
- 단계·선행 조건·필수 입력·연결된 도구와 스킬의 유효한 지침을 읽어 수행 순서, 자동으로 가능한 일, 사람 확인과 미연결로 남는 일을 짧은 계획으로 제시한다. 실제 사내 절차가 정해지지 않은 부분을 새로 만들어 확정하지 않는다.
- 대상이 정해지면 알맞은 진행 건을 이어가거나 새로 만들고, 기존 UI와 동일한 업무 액션·권한·revision·결과 저장 경로로 선택·입력·실행을 수행한다. 사람 확인이 필요한 단계와 미연결 도구에서 멈추고 필요한 다음 행동을 설명한다. 포괄적인 자동화 요청을 사람의 실제 확인·완료 응답으로 간주하지 않는다.
- 현재 [업무 Tool](../../../agent-pack/skills/ees-work-demo/scripts/workflow_tool.py)의 `ees_workflow_view(include_navigation=true)`와 `ees_workflow_action`에 목록 탐색·생성·선택·입력·실행 기반이 있다. `process_id`로 게시 절차의 단계·참조 도구/스킬을 읽고 `case_id`로 기존 실행의 고정본을 읽도록 보강했다. 탐색·상세 조회는 선택 연결·진행 건 생성·쓰기 없이 수행하며 스킬 본문은 현재 접근 권한을 확인한다. 별도 모델·에이전트·계획 서버를 추가하지 않는다. 현행은 일반 저장 대화 하나에 본인 진행 건 하나를 연결하고 DB/AP 실행은 모의 어댑터이며, 이 경계를 공동 작업·실제 운영 연결 완료로 확대하지 않는다.

구현의 로컬 검수는 읽기 무변경·절차 범위/고정본·권한·실행 보호·구서버 안내로 확인했다. 사내 후속 검수는 **사이드바 미선택 상태의 자연어 요청 → 후보 탐색·필수값 확인 → 짧은 계획 → 진행 건 연결 → 같은 상태의 실행 결과와 화면 반영** 한 흐름으로 정한다. 기존 Tool·합성 시험 통과와 사내 GLM의 자연어 호출 성공은 구분하며, 실제 모델의 이 흐름은 아직 미확인이다. [현재 코드 검토·리팩토링과의 경계](../../../evals/scenarios.md#work-ui-refactor-20260915).

**AI 개발·현장 자산 보존 요구(2026-09-15):** 사용자는 모든 개발을 AI가 맡으며 이 환경에서 알 수 없는 사내 UI 작성 Skill·Tool도 훼손 없이 계속 사용할 수 있어야 한다고 명시했다. 기능별 지침·실행 코드 묶음, 기존 WebUI·래퍼·업무 저장소, 버튼/AI의 공통 서버 액션을 유지하는 방향을 권한다. 당시 필요성 검토를 구체화한 후속 원본은 아래 [제한적 리팩토링 설계](#refactoring-design)이며, 패널 크기/배치 공통화는 최종 범위에서 제외했다. 현재 단계는 설계·검토이고 코드 구현·배포와 구분한다. 사용자 자산은 WebUI를 관리 원본으로 두고 지정 공통 자산의 관리 필드만 Git 배포 대상으로 삼는다. 프로그램/자산 갱신·데이터 이관의 보존 기준과 지원 필드의 동시 편집 한계는 [검토 기록](../../../evals/scenarios.md#ai-runtime-preservation-20260915)을 따른다.

**현황 표시의 단계적 범위 제안**

| 시점 | 범위 |
|---|---|
| 첫 공동 작업 단위 | 기존 업무 목록·트리·오른쪽 패널에서 진행 건 이름·상태·완료 n/N·막힌 이유·다음 할 일을 명확히 표시. 담당/수행자 표시는 공동 작업의 역할·기록 정의와 함께 구현 |
| 소수 팀원의 실제 사용 이후 | 필요한 담당·기한 입력 단위를 정하고 기한 임박·지연 표시 등 작은 현황 기능부터 확장 |
| 후속 현황판 | 실제 사용 요구에 따라 일정표·간트·공장/시스템 비교·통계·업무량 화면을 별도 범위로 설계 |

현재 진척률은 적용 대상 잡 중 완료한 잡의 비율이며 적용 제외는 분모·완료 수에서 뺀다. 작업별 소요시간·가중치·일정 준수율을 뜻하지 않는다. 생성 시각·수정 시각·실행 시각은 있지만 담당자·계획 시작/종료·기한·예상 소요시간은 아직 없다. 특히 기존 `updated_at`은 단계 선택·대화 연결에도 바뀌므로 최근 실제 업무 수행 시각으로 표시하지 않는다. UI에서 막힌 이유는 선행 미완료뿐 아니라 입력 부족·연결/스킬 이용 불가도 구분해 안내해야 한다.

첫 단위의 수락 기준은 A가 만든 지정 공유 건을 B가 이어서 처리하고 같은 결과·변경자를 확인하는 것, 각자의 대화·초안·선택 유지, 동시 변경의 덮어쓰기·중복 실행 방지, 권한 없는 계정의 접근 차단, 재접속 후 결과·이력 유지이다. 실제 자동 점검은 승인된 API가 연결된 범위만 판단하며 사람 확인 업무로 먼저 공동 사용을 검증할 수 있다. 공개할 기능의 계정·자산 권한·전송 보호·가동 조건은 [공용 파일럿 기준](../../../evals/scenarios.md#validation-timing)에 맞춰 확인한다. 전용 서버·새 DB 제품·공통 대시보드 프레임워크를 먼저 도입하지 않고 기존 WebUI·래퍼·업무 저장소의 재사용 가능 범위부터 구체화한다.

위 우선순위는 현황판 시점에 대한 제안이며, 공동 작업 구현·일정 기능·팀 파일럿 성공은 아직 미완료다. [현재 근거와 검수 범위](../../../evals/scenarios.md#shared-pilot-priority-20260915).

<a id="refactoring-design"></a>

## 제한적 리팩토링 구현 설계 (2026-09-15)

목적은 AI가 한 기능의 변경 범위와 호환 조건을 파악하기 쉽게 만들고, 사내에서 작성한 자산을 보존하면서 공동 작업 기반을 추가할 준비를 하는 것이다. 현재 WebUI·Python 빌더·래퍼·업무 저장소를 유지한다. 이 절은 구현 기준 설계이며, R0의 후속 구현은 [조건부 자산 적용 기록](../../../evals/scenarios.md#conditional-assets-20260915)에 연결한다. R1 서버/정책 분리는 [구현·호환 검증](../../../evals/scenarios.md#workflow-refactor-20260915)에 연결하며, R2 화면 분리 구현과 R3 배포 호환 검증은 [후속 기록](../../../evals/scenarios.md#work-ui-refactor-20260915)에 연결한다. 원격 Windows/브라우저 통과와 사내 적용 여부는 해당 기록과 STATUS를 따르며 구현만으로 완료 처리하지 않는다. 설계 검토 결과와 실제 구현/시험 여부는 [설계 검토 기록](../../../evals/scenarios.md#refactoring-design-review-20260915)에서 구분한다.

### 범위와 작업 단위

| 단위 | 변경 목적·대상 | 끝내야 할 조건 |
|---|---|---|
| R0 자산 동시 편집 결함 수정 | ApplyDemo의 조회 이후 현장 수정 덮어쓰기를 서버 조건부 저장으로 차단. 클라이언트·고정 upstream 저장 경로·빌더 변경 | UI 저장과 ApplyDemo의 실제 서버 경합, 취소·부분 실패·권한·구버전 거절 검사. 순수 리팩토링과 별도 커밋/검수 |
| R1 업무 서버 책임 분리 | 정의/검증·화면용 파생 상태·저장/권한을 기존 기능 폴더에서 분리. 공통 정책과 참고 seed 분리 | 공개 모듈/API·완성 seed·기존 저장 자료·오류/결과 호환. 사용자 자료 재작성 없음 |
| R2 업무 화면 책임 분리 | launcher의 제어·표시·절차 편집 책임을 세 소스로 분리하고 기존 빌더에서 한 JS로 조립 | 실제 배포 JS로 기존 UI·대화/초안·요청 순서 회귀 확인. 기존 분석 패널 동작 유지 |
| R3 배포 호환 확인 | 앞 단계의 실제 wheel·파일 목록·기존 래퍼 Apply/Restore 검증 | 기존 자료를 가진 합성 환경에서 갱신·추가 저장·이전 프로그램 Restore 후 자료/공개 연결 확인 |

구현 순서는 R0 → R1 → R2 → R3이다. R1·R2는 R0의 새 API를 업무 처리에 사용하지 않으며 독립적으로 되돌릴 수 있다. 각 구현 단위는 코드·의미 있는 검사·가이드·실패 기록까지 끝낸 뒤 다음으로 넘어간다. 구조 정리를 자산 재등록·ApplyDemo 실행·DB 이관과 묶지 않는다. 공동 진행 건/역할/개인 선택 분리, 실제 셋업 절차, 실제 시스템 연결, 일정·종합 현황판은 후속 기능이다.

패널 공통화와 성능 최적화는 이번 범위에서 제외한다. 기존 공통 패널 관리자는 재사용하되 업무 패널의 기본 520px/340~760px·850px 전환과 분석 패널의 기본 480px/350~800px·형제 폭/ResizeObserver는 서로 다르다. 이를 합치면 사용자 동작까지 바뀐다. 전체 subtree 감시·진행 건 전체 조회도 측정된 병목이 아니므로 이 설계에서 교체하지 않는다.

### 모든 단계의 보존 계약

- 운영 DATA_DIR·DB·키·계정·PAT·개인 대화와 Git에 없는 Skill/Tool/Prompt/모델·연결·권한·개인 설정을 보존한다. 등록 ID를 바꾸거나 보이지 않는 자산을 미사용으로 판정하지 않는다. 공통 자산은 기존 명시 ID와 관리 필드만 갱신한다.
- `open_webui.ees_workflow`, 기존 Tool ID·`workflow_tool.py` 호출 인자/결과, 업무 API/action 이름·오류 코드/HTTP 상태·revision·권한 판정을 유지한다. 현재 사용자별 진행 건을 자동 공유하지 않는다.
- `ees-work.sqlite3`의 파일명·테이블/인덱스·owner/chat/선택/버전·catalog/draft/게시본/case/이력/Skill snapshot 형식은 바꾸지 않는다. 기존 자료를 새 seed·정책으로 재합성하거나 재게시하지 않는다.
- 데이터 보존과 이용 가능성을 함께 확인한다. Git에 없는 합성 Skill/Tool을 기존 사용자 권한으로 조회·참조·게시하고 지원 공개 인터페이스를 통해 재사용한다. 업무 엔진의 미지원 실행 어댑터는 계속 차단하며 이를 임의 Tool 실행 가능으로 바꾸지 않는다.
- 실제 배포 시에만 프로그램 버전·정적 캐시 경로·파일 manifest를 함께 갱신한다. 설계 문서 작성은 새 프로그램 생성이나 사내 반영이 아니다. 프로그램 Restore는 최신 DB·자산을 남기며 자산 변경 자체를 되돌리지 않는다.

### R0: 조건부 자산 저장

새 원본 `scripts/ees_asset_guard.py`를 기존 Python 빌더로 `open_webui/ees_asset_guard.py`에 포함한다. 기존 `ees_deploy_accept.py`처럼 프로그램 운용을 보호하는 런타임 코드이며 업무 Skill 규칙과 분리한다. 별도 폴더 계층·서비스·DB·배포 체계는 만들지 않는다. 기존 `scripts/ees_demo_assets.py`와 `scripts/ees_apply_demo.py`는 새 조건부 API를 사용하고 현재 관리 필드 비교·journal·부분 실패/재실행 처리를 유지한다.

| API | 요청·응답 계약 |
|---|---|
| `GET /api/v1/ees/assets/capabilities` | 관리자 인증. 전체 보호 설치와 지원 환경 확인 후에만 `version=1`, `conditional_apply=true`, `process_scope=single` 반환 |
| `POST /api/v1/ees/assets/snapshot` | 관리자 인증과 대상 권한 확인. `kind=tool/model/valves`, `id`. 기존 native 읽기·쓰기 권한과 원본 가시성을 확인한 `asset`, `exists`, `token` 반환. valves에는 비교용 부모 Tool 상태도 포함 |
| `POST /api/v1/ees/assets/apply` | 관리자 인증과 대상 권한 재확인. 같은 `kind/id`, `operation=create/update`, `expected_token`, native Form에 맞는 `payload`. 잠금 안에서 최신 권한/상태 확인 → token 비교 → native 검증/저장 → 재조회. 성공 응답은 저장 후 snapshot과 token, Tool이면 다음 valves 작업용 부모 포함 snapshot도 반환 |

관리자 인증만으로 다른 소유자의 읽기 전용/비공개 자산을 수정할 수 있게 하지 않는다. 기존 owner·ACL·원본 가시성·grant 필터를 재사용한다. kind는 고정 세 종류이고 요청 id와 payload id가 달라지거나 임의 URL·메서드를 지정하면 거절한다. 새 API는 개인 UserValves·Skill 쓰기·삭제를 제공하지 않는다.

token은 매 프로세스 메모리에서 생성한 키로 protocol/사용자 ID/kind/id/존재 여부와 **native 저장이 덮을 수 있는 전체 지원 상태**에 HMAC을 적용한다. 기존 비밀 키/파일을 변경하지 않으며 재시작 전 token은 무효다. Tool은 owner/name/content/지원 meta/정규화 ACL/common Valves를 한 충돌 범위로 묶고, 모델은 owner/id/name/base/meta/params/활성 상태/정규화 ACL을 포함한다. 개인 UserValves는 제외한다. 관리 필드만 뽑는 기존 projection은 현장 수정 판정에 계속 쓰며 token을 대신하지 않는다. 새 보호 코드에서 원문·자격증명·token을 진단 로그에 복제하지 않으며 native 저장 오류는 고정 응답으로 바꾼다. 이 범위를 기존 WebUI 전체 예외 로그의 비밀정보 차단 보장으로 확대하지 않는다.

조회·계획·저장은 다음 규칙을 따른다.

1. 전체 대상의 사전 검사를 먼저 수행한다. 각 쓰기 계획의 `{baseline asset, expected_token, merged payload}`는 같은 snapshot에서 만든다. 이후 token이 달라지면 `409 concurrent_edit`로 중단하며 새 token만 받아 예전 payload를 재전송하지 않는다. 자동 강제 적용·무조건 POST fallback은 없다.
2. Tool 저장으로 자신의 부모 token이 바뀐 뒤 valves를 갱신하는 경우에만 성공 응답의 부모 포함 snapshot을 다음 기준으로 삼는다. 그 snapshot으로 관리 필드 충돌 검사와 기존 비관리 값 보존 merge를 다시 수행한다. 기존 journal에 확인된 자신의 변경만 반영하고, 반환된 snapshot 이후 다른 변경은 다음 apply 비교에서 중단한다. 다른 대상의 사전 계획 token은 교체하지 않는다.
3. Tool 응답이 유실되면 성공을 가정하지 않는다. 기존 pending journal과 재조회로 실제 저장을 확인하기 전에는 valves 등 후속 쓰기를 하지 않는다. 별도 자산들의 일괄 트랜잭션이나 자동 원복을 약속하지 않는다.
4. 보호가 없는 구버전 서버에는 첫 쓰기 전에 `changed=0`, `conditional_write_unavailable`로 중단하고 프로그램 갱신을 안내한다. 새 프로그램 Upgrade 후 새 ApplyDemo를 사용한다. 이전 프로그램으로 Restore하면 새 ApplyDemo 쓰기는 다시 차단된다. 구형 클라이언트의 무조건 POST까지 소급해 보호했다고 표현하지 않는다.

**서버 잠금의 경계:** 한 event loop의 공통 재진입 잠금으로 아래 native 경로와 조건부 API를 모두 보호한다. 현재 Task가 소유권을 갖고 중첩 호출만 재진입한다. 자식 Task로 복사되는 ContextVar만으로 소유권을 판정하지 않는다. 잠금 획득 뒤 새 DB session에서 현재 사용자·owner·ACL·자산을 다시 읽고 그 session과 사용자 객체를 native 호출에 명시적으로 전달한다. snapshot만 새로 읽고 저장은 요청의 오래된 ORM/session으로 하는 구현은 허용하지 않는다. 기존 외부 caller session을 강제로 rollback/expire하여 미완료 작업을 버리지 않는다.

취소된 요청보다 DB 작업이 오래 살 수 있으므로 실제 작업 Task가 **잠금 획득부터 DB 종료·실패 정리·캐시 처리까지** 소유한다. 요청 취소는 시작된 작업을 중간 취소하지 않으며 작업 완료까지 잠금/session을 유지한다. 외부 Task가 잠금을 잡고 shield 자식 Task에 native 쓰기를 넘기는 교착 형태는 사용하지 않는다. 대기 중 취소는 쓰기 없이 끝내고, 쓰기 시작 후 취소/연결 소실은 journal 재확인 대상으로 남긴다.

지원 실행 환경은 기존 등록 래퍼가 시작하는 로컬 DB·단일 프로세스/worker다. `workers=1` 검사 외에 정규화한 실제 DATA_DIR/DB에 대응하는 `ees-assets.lock`의 **프로세스 수명 OS 배타 잠금**을 startup 때 확보한다. Linux `flock`/Windows 파일 잠금으로 커널이 소유권을 관리하고, PID·TTL 파일 삭제로 빼앗지 않는다. 두 번째 앱은 capability만 끄는 것이 아니라 startup을 거절한다. shutdown 때도 남은 guarded Task와 DB 작업의 종료·정리를 마친 뒤 OS 잠금을 해제한다. symlink/경로 우회는 기존 경로 보호 방식으로 거절한다. 보호 미적용 원본 앱·외부 DB writer·다중 프로세스/서버는 보장 밖이며 기존 래퍼의 등록 프로세스 확인을 유지한다. 지원 여부를 확인하지 못하면 조건부 쓰기를 제공하지 않는다.

설치는 `routers/models.py`·`routers/tools.py`의 `APIRouter(route_class=AssetGuardRoute)` 생성 시 고정 patch한다. `AssetGuardRoute.get_route_handler()`가 두 router 전체의 원래 handler를 감싸 **Depends의 인증/session 생성 이전**에 잠금을 잡는다. endpoint 함수 decorator나 include 후 함수 변수 교체로 대신하지 않는다. 새 assets router도 같은 route class를 쓰고 기존 router include 부근, SPA mount 전에 등록한다. lifespan은 `app.state.main_loop` 설정 직후·첫 config/model 조회 전에 guard를 시작하고 startup 실패와 정상 종료 모두 finally에서 정리한다. 새 API는 잠금 뒤 자기 소유 fresh session을 열어 조회/권한을 확인하고 native 저장에 전달하며, upstream session-sharing 설정 자체나 native의 기존 commit 정책은 바꾸지 않는다. 외부 `session.begin()`으로 전체 작업을 감싸지 않는다.

고정 Open WebUI `v0.11.3`의 보호 대상은 다음과 같다. 빌더에서 고정 입력 hash·함수/삽입 위치·횟수를 대조하고 앱 요청 수락 전에 모두 설치한다. 누락·불일치는 빌드/기동 실패이며 부분 설치로 capability를 활성화하지 않는다.

| upstream 경로 | 보호할 경계 |
|---|---|
| `routers/tools.py` | `create_new_tools`, `update_tools_by_id`, `update_tool_access_by_id`, `delete_tools_by_id`, `update_tools_valves_by_id`: 권한 확인·module 준비부터 DB/ACL·캐시 처리까지 |
| `models/tools.py`의 `ToolsTable` | `insert_new_tool`, `update_tool_by_id`, `update_tool_valves_by_id`, `delete_tool_by_id`. 내부 table 직접 호출도 동일 잠금 사용 |
| `routers/models.py` | `create_new_model`, `update_model_by_id`, `update_model_access_by_id`, `toggle_model_by_id`, `import_models`, `sync_models`, `delete_model_by_id`, `delete_all_models` |
| `models/models.py`의 `ModelsTable` | `insert_new_model`, `update_model_by_id`, `update_model_updated_at_by_id`, `toggle_model_by_id`, `sync_models`, `delete_model_by_id`, `delete_all_models`. `_to_model_model`의 knowledge 정상화 저장을 유발하는 조회도 최초 ORM 읽기 전부터 보호 |
| `models/access_grants.py`의 `AccessGrantsTable` | Tool/Model 대상 `grant_access`, `revoke_access`, `revoke_all_access`, `set_access_control`, `set_access_grants` |

실제 wheel 전수 대조에서 `utils/plugin.py`의 Tool import 정상화, `routers/knowledge.py`의 지식 삭제 후 모델 재저장, 여러 native 조회 caller의 선행 session, `utils/tools.py`의 채팅용 Tool 캐시 공개도 보호 범위에 추가했다. 빌더의 `ASSET_GUARD_HOOKS`·고정 파일 hash와 서버의 설치 검사를 함께 대조한다. 채팅 Tool 로딩은 로컬 조회/권한/module/valves/호출 연결만 같은 Task에서 보호하고 원격 Tool 호출은 밖에 유지한다. Ollama 외부 모델 조회 전체를 잠그던 초안 hook은 제거하고 첫 자산 조회의 table 경계를 보호한다.

읽기 중 정상화하는 모델 조회는 `get_all_models`, `get_models`, `get_base_models`, `search_models`, `get_model_by_id`, `get_models_by_ids`를 보호 목록에 포함한다. 보호 대상 내부 호출은 같은 작업 Task/session을 명시적으로 이어받는다. 독립 table 진입은 잠금 뒤 새 session을 열고, 기존 session을 가진 내부 호출은 최초 읽기/트랜잭션 시작 이전의 caller 경계까지 보호 위치를 올린다. 새 session으로 미완료 트랜잭션을 몰래 대체하지 않는다. 고정 wheel에서 해당 caller·직접 SQL writer를 대조해 보호 밖 쓰기가 있으면 출하하지 않는다.

Tool 캐시는 기존처럼 DB 성공 전에 새 module을 전역 공개하지 않는다. 잠금 안에서 지역 준비하고 DB·ACL 성공 후 공개하며 실패하면 해당 Tool 캐시를 무효화해 DB를 원본으로 삼는다. 이미 실행 중인 Tool 호출을 강제 교체하지 않는다. 본체·ACL 저장의 별도 commit은 mutex를 적용해도 전체 원자적 DB 트랜잭션이 되지 않으므로 부분 실패를 기록하고 재조회하며 과거 payload 자동 복구는 하지 않는다. 보장 범위는 **ApplyDemo가 비교 이후의 다른 사용자 저장을 덮지 않는 것**이고, 일반 UI 두 편집기의 오래된 폼 충돌 해결은 별도다.

### R1: 업무 서버와 정책/예시 분리

파일은 기존 `agent-pack/skills/ees-work-demo/scripts/`에 둔다. 새 계층·서버·저장소를 만들지 않는다.

| 소스 | 단일 책임·공개 연결 |
|---|---|
| 기존 `ees_workflow.py` | `WorkflowService`, 권한/SQL/변경, `WorkflowError`, `_value`, `_resolve`, `_now`, `_service`, `_production_service`, `_registered_assets`, `get_state`, `handle_action`, `install`. 공개 facade 유지 |
| 새 `ees_workflow_definition.py` | 상수/크기 제한, `_dump`, `_seed`, 정책 읽기, `_ancestors`, `_leaves`, `_dependencies`, `_draft_shape_errors`, `validate_definition` |
| 새 `ees_workflow_view.py` | `_applicable`, `_finished`, `_missing`, `_view`의 순수 파생 상태 계산. DB·인증·저장 수행 없음 |
| 새 `workflow_policy.json` | 기존 seed의 `skills.common` 객체를 ID·본문·값 그대로 이동 |
| 기존 `workflow_seed.json` | 참고 업무 예시. `_seed`가 policy를 `common` 첫 키에 결합해 기존 완성 정의 반환 |

의존 방향은 facade → definition/view, view → definition이다. definition/view가 facade를 역참조하지 않는다. 기존 외부/시험에서 참조하는 이동 helper는 facade에서 명시적으로 다시 노출한다. `_now`·`_service`는 기존 위치를 유지한다. 단독 파일 실행을 맞추려고 production `sys.path` 수정이나 광범위 `ImportError` fallback을 넣지 않는다.

분리 전후 `_dump(_seed())`의 **완성 정의 bytes·키 순서·version=1·ID·공통 정책 객체**가 같아야 한다. seed 원본 파일 자체는 common 이동으로 바뀐다. validation은 새 policy 원본을 읽되 판정·오류 순서/문구를 유지한다. 현재 생성자의 seed 읽기와 catalog `INSERT OR IGNORE`를 유지하고, 기존 draft/게시본/진행 건/Skill snapshot에는 새 policy를 다시 적용하지 않는다. db/ap/site/interface 등의 고정 입력과 mock/unavailable 판정도 유지하므로 이 작업을 범용 실무 엔진 완성으로 해석하지 않는다.

빌더 `WORK_ASSETS`에 새 Python 두 개와 policy를 포함하고 설치 위치는 모두 `open_webui/` 아래로 유지한다. `WORK_FILES`·manifest·새 버전 Restore 대상도 같은 원본에서 산출한다. ees.6~ees.8은 분리 이전 `WORK_FILES_V6` 목록을 유지해 새 파일을 과거 백업에 요구하지 않는다. `ees_upgrade.py`의 프로그램 입력 목록과 CI 변경 경로 필터가 새 파일을 포함하는지 대조한다. `test_ees_workflow.py`·`test_ees_work_demo.py`의 업무 서버 로더는 시험 전용 package namespace로 바꿔 상대 import를 실행하고, 실제 wheel의 `open_webui.ees_workflow` import와 서비스 호출도 검사한다. `test_ees_workflow_tool.py`의 기존 공개 모듈 mock 계약은 유지한다. 설계 초안에 포함했던 `test_ees_specialists_tool.py`의 comparison 로더는 실제로 `demo_data_tool.py`를 읽으므로 분리 대상이 아니다. R1 구현 때 실제 파일 경로를 대조해 이 오기를 정정했다.

### R2: 업무 화면의 제어·표시·편집 분리

파일은 기존 `branding/ees/ui/`에 둔다. 세 파일을 한 lexical scope의 자유변수 공유로만 나누지 않고 다음 factory와 인자로 책임을 분리한다.

| 소스 | 소유 상태·역할 |
|---|---|
| 기존 `ees-work-launcher.js` | controller. 서버 state/revision/busy/error, 인증/route/generation/request/navigation 순서, 공장/시스템/진행 건 선택, 이력 요청 token, 개인 대화 초안·생성 ticket. API/액션/대화 전환과 전역 이벤트·MutationObserver의 유일한 소유자 |
| 새 `ees-work-view.js` | `createWorkView`. 사이드바·선택 영역·트리·업무 패널/결과/이력 DOM. nav/picker/트리 펼침/패널 폭·열림·drag 등 화면 상태만 소유 |
| 새 `ees-work-designer.js` | `createWorkDesigner`. Workspace 탭 숨김/복원과 절차 편집 DOM, 편집 대상·revision·dirty·tab·접힘 및 편집 초안 소유 |

controller → view는 `render(snapshot)`, `setBusy`, `openPanel`, `closeHost`, `reset`, `readJobEdits`와 `handleEvent(event)`/`updateLayout()`으로 연결한다. view → controller는 `selectWork`, `switchScope`, `openCase`, `startCase`, `showHistory`, `saveInputs`, `saveDocument`, `runJob` 콜백으로 기존 액션을 요청한다. 서버 snapshot은 view에서 변경하지 않는다.

controller → designer는 `acceptServer(result)`, `readDraft()`의 `{definition, revision, dirty}`, `markSaved`, `render`, `restoreWorkspace(removeTab)`, `reset`이다. designer는 저장/검증/게시를 기존 `save_draft`, `validate_draft`, `publish` 콜백으로 요청하며 직접 fetch하지 않는다. 공용 순수 tree renderer는 데이터·선택 ID와 `editing/selectedId/collapsed/expanded/statuses/summaries` 옵션을 받고 editor/controller 자유변수를 읽지 않는다. 전역 click/input/change/keydown/scroll/resize는 controller가 해당 view/designer의 `handleEvent(event)`로 전달한다. 수신 객체는 자신의 DOM/상태에만 반응하고 `{handled, preventDefault}`를 동기 반환하며 controller가 중복 처리·기본 동작 여부를 결정한다. 일반 SPA route 전환에서는 DOM detach/Workspace 복원·관찰 대상 갱신만 하고 현재 동작대로 editor dirty·트리 펼침·폭을 보존한다. 인증 사용자 변경/로그아웃 때 개인 상태를 reset한다. 전역 listener/observer는 기존 document 수명과 런처 중복 로딩 방지를 유지하며 SPA 이동마다 새로 등록하지 않는다. R2에서는 별도 dispose API나 pagehide 수명 변경을 추가하지 않는다.

`scripts/build_ees_webui.py`의 조립 함수 하나로 **view → designer → launcher** 순서를 고정하고 외부 IIFE 안에 넣어 기존 단일 `ees-work-launcher.js`를 생성한다. 기존 launcher IIFE는 마지막에 실행하고 새 factory를 전역으로 노출하지 않는다. WebUI 로딩은 기존 work-panel → launcher의 defer 순서를 유지한다. 입력 없음/빈 파일/symlink/중복 factory·잘못된 순서는 빌드 실패로 처리하고 bytes·hash·wheel RECORD/manifest를 결정적으로 생성한다. 런타임 module loader·npm bundler·외부 CDN을 추가하지 않는다.

호환 대상은 `__eesNativeWorkV1`의 ensureChat/beginChatCreation/finishChatCreation/refresh/open/display, `__eesNativeDraftV1`의 기존 read/flush/ready/restore 연결, `__eesWorkPanelV1` 전체 계약, `ees-work-changed`, display allowlist, DOM ID/CSS class/data-action 및 기존 업무 API payload다. 초안에 `toolApprovalMode`를 직렬화하지 않는다. 이전 generation/route/auth의 응답과 navigation/history/draft ticket은 계속 무시한다. source 이동 과정에서 개인 선택의 DB 의미나 기존 폼 저장 시점을 바꾸지 않는다.

### 검증·되돌리기와 완료 판정

| 대상 | 구현 시 필요한 증거 |
|---|---|
| R0 조건부 저장 | 고정 wheel의 실제 native router/table/ACL 경로에서 최종 snapshot 뒤 지원 `meta.description`·Tool code/valves·모델 params/ACL 변경을 각각 삽입해 409와 새 값 보존 확인. 생성 ID 충돌·비공개/읽기 전용 거절·다른 ID/개인 UserValves 불변·응답 유실/pending/부분 commit 재조회 |
| R0 잠금 경계 | 단일 worker와 같은 DB의 두 프로세스 기동 거절, 내부 writer·정상화 GET 경합, session sharing 켜짐/꺼짐, 대기/쓰기 중 취소·DB 예외·캐시 실패에서 교착/조기 잠금 해제 없음. hash/함수/삽입점 불일치와 구버전 서버는 쓰기 전 중단 |
| R1 저장/계약 | 기존 관리자 수정 게시본·검증된/미검증 draft·진행 건/이력·Skill snapshot을 가진 합성 DB로 전후 결과 대조. 완성 seed bytes 일치, 시작만으로 기존 row 변경 없음, 공개 모듈/Tool 호출·권한/오류/revision 호환 |
| R2 화면 | `test_ees_branding_build.py` 조립/실패/manifest 검사, `test_ees_work_demo.py`의 기존 native browser 시나리오. `native_ui_fixture.py`가 빌더의 같은 조립 결과를 제공. `test_ees_cooperation_panel.cjs`·`test_wo_demo_state.cjs`로 단일 관리자/탭·초안·닫기/대화 복원 호환 |
| R3 실제 배포물 | Python 3.11·고정 Open WebUI 0.11.3 wheel의 import/서비스/브라우저 검사와 기존 Linux/Windows Apply/Restore CI. 분리 파일 누락 없음, Git 밖 합성 사용자 자산 재사용, 업그레이드 뒤 추가 저장한 자료가 이전 프로그램 Restore 뒤에도 유지됨 |

설계 검토 완료는 위 시험이 통과했다는 뜻이 아니다. 구현 PR마다 실제 실행 명령·환경·실패와 수정·미실행을 기존 evals에 남긴다. 사내 확인은 코드/배포 준비가 끝난 뒤 변경에 필요한 소수 항목만 기존 1~2줄 보고 방식으로 묶고 이미 받은 `ui/tree/font/chat=ok`를 문서 변경 때문에 반복 요구하지 않는다. R0는 프로그램 Restore로 기능을 되돌릴 수 있어도 이미 저장한 자산/ACL까지 자동 복원하지 않는다. R1·R2는 DB 형식·공개 API가 같으므로 코드 revert와 기존 Restore 경로를 유지한다.

아래 1~6절은 **현재 ees.7 통합 구현·검증 기준**을 보존한 것이다. 공동 작업 구현 시에는 이 최신 합의를 적용하고, 사용자별 격리·대화 연결 기준을 필요한 범위에서 함께 갱신한다. 다음 세션의 실제 작업 순서와 배포 상태는 [STATUS](../../STATUS.md)를 따른다.

## 1. 시작과 기존 기능 재사용

- 최신 main·관련 열린 PR·로컬 변경과 AGENTS.md·docs/STATUS.md를 확인한다. 기존 변경·승인·과거 증거를 보존한다.
- 기존 로그인·모델 선택·실제 대화·스트리밍·첨부·대화 이력·문서 조회와 오른쪽 업무 패널을 유지한다. 별도 대화 입력창이나 가짜 AI 응답을 만들지 않는다.
- 기존 프로그램·래퍼·Agent Pack 배포 경로와 Open WebUI Native Tool 호출을 사용한다. 별도 서비스·범용 오케스트레이터·의존성 전체 재설치를 추가하지 않는다.
- [기능 폴더](../../../agent-pack/skills/ees-work-demo/)의 업무 상태·액션과 기존 UI를 연결한다. 참고 HTML을 저장하거나 단독 화면으로 띄우는 것만으로 통합 완료라고 보고하지 않는다.

## 2. 업무 탐색과 실제 대화

- 왼쪽 사이드바 상단에서 작업 공장(국가·공장명)과 시스템을 선택한다. 그 아래 셋업·운영·장애대응을 펼치면 등록된 프로세스(P) → 태스크(T) → 잡(J)이 같은 사이드바 안에서 보인다. 트리 펼침과 작업 선택을 구분한다. 별도 팝업 탐색기나 탐색기 고정 버튼을 일상 진입 흐름으로 사용하지 않는다.
- ‘신규 공장 횡전개’ 같은 업무 절차와 ‘미국 A공장 EMS 셋업’ 같은 실제 진행 건을 구분한다. 진행 건은 공장·시스템·절차 버전·조건·실행 결과를 가진다.
- 공장·시스템별 트리에서 시작 전·진행 중·완료·실패·선행 대기·적용 제외를 구분한다. 적용 제외를 완료로 세거나 진행률 분모에 넣지 않는다. 게시본이 변경되더라도 기존 실행의 트리와 결과는 시작 당시 버전으로 표시한다.
- 해당 공장·시스템·프로세스에 진행 중인 실행이 있으면 이어서 진행할 실행을 먼저 보여준다. 기존 다중 실행은 보존하고 여러 건 중 임의의 최신 건을 현재 실행으로 선택하지 않는다. 완료한 실행의 과거 결과와 새 실행을 구분한다.
- ees.7에서는 본인 소유의 일반 저장 대화에 본인의 진행 건 하나를 연결하고 현재 공장·업무 경로를 명확하게 표시한다. 임시 대화(`temporary-chat=true`)에서는 업무 진행을 지원하지 않는다. 같은 진행 건의 하위 태스크·잡을 바꿔도 대화 이력과 작성 중 메시지는 유지한다. 다른 진행 건은 연결된 대화에서 이어가거나 새 일반 대화로 시작한다. 이 개인 연결을 공동 작업 참여자의 채팅 공유 규칙으로 확대하지 않는다.
- 선택만으로 실행하지 않는다. 패널 닫기는 표시만 닫으며 상태·결과를 지우지 않는다. 다른 잡으로 이동하더라도 실행 결과는 원래 잡에 기록한다.
- 가운데 실제 AI가 현재 진행 건·선택·입력값·실행 결과를 조회하고 지원 액션을 호출할 수 있어야 한다. 일반 질문과 기존 Jira·Confluence·GitHub 조회는 기존 대화 경로로 계속 사용한다.
- 오른쪽 버튼, AI의 업무 Tool, E2E 검사는 같은 서버 액션·검증·저장 경로를 사용한다. 대화 요청을 단순 문구 매칭으로 가짜 응답하거나 버튼만 누를 수 있는 기능으로 제한하지 않는다.

## 3. 오른쪽 작업 패널

| 선택 단계 | 표시할 내용 |
|---|---|
| 프로세스 | 대상 공장·시스템·버전, 전체 단계·진행 상황, 다음 할 일 |
| 태스크 | 목적·선행 조건, 하위 잡 상태·실행 항목 |
| 잡 | 대상·입력값, 실행 순서·점검 기준, 결과·근거·실패 이력·재시도 |

- 기존 오른쪽 업무 패널의 열기·닫기·폭 조절·다른 업무 화면과 공존하는 구조를 재사용한다. 가운데 대화를 다른 화면으로 교체하지 않는다.
- **현재 작업 / 실행 이력**을 구분한다. 과거 실행 조회는 읽기 전용이며 현재 트리 상태·선택·대화·진행 건 revision을 바꾸지 않는다. 실행 이력에서 날짜·절차 버전·상태를 보고 세부 결과를 확인할 수 있어야 한다. 생성 시각을 저장하지 않았던 기존 실행은 알 수 없는 날짜를 만들어 표시하지 않는다.
- 대표 흐름은 사전준비 → AP, DB 인프라 준비 → 시스템 설치 → 각 시스템간 인터페이스 확인이다. 시스템 설치에는 설치·설정 확인, DB 연결 확인, AP 연결 확인 잡을 둔다.
- DB 잡은 진단 경로·대상 식별·읽기 기능을, AP 잡은 네트워크·서비스·상태 API·기능 응답을 순서대로 점검하는 합성 예시를 제공한다. AP 첫 실행의 상태 API 실패와 후속 미수행, 재시도의 통과를 구분하고 이전 실패를 보존한다.
- 선행 미완료·미연결·실패·미수행을 성공으로 집계하지 않는다. 재실행에 따른 후속 결과 무효화와 상위 진행 상황을 일관되게 연결한다.
- 자유문장 완료 기준은 사람·AI가 참고하는 지침이다. 자동 판정은 연결된 모의 어댑터의 개별 점검 상태를 집계하며 임의의 기준 문장을 실행 코드로 평가한 것으로 표현하지 않는다.

## 4. 관리자 워크스페이스

- 기존 워크스페이스의 모델·지식기반·프롬프트 등 기존 메뉴와 동작을 유지하고 ‘업무 절차’ 탭으로 진입하게 한다. 탭과 편집 폼의 글꼴·간격은 기존 UI를 따르며 화면 변경을 감지할 때 탭을 반복 제거·재삽입해 깜빡이거나 포커스를 잃지 않도록 한다. 실제 사용자 역할에 따라 편집·게시 권한을 서버에서 확인한다. 화면의 역할 선택만으로 관리자 권한을 부여하지 않는다.
- 비개발자가 폼과 목록으로 P/T/J 추가·이름·순서·사용 여부·적용 조건·선행 작업·완료 기준을 편집한다. 단계별 도구·스킬·지침을 연결하고 잡의 도구 순서·입력 매핑을 지정한다.
- 기존 Workspace Tools·Skills를 재사용해 접근 가능한 등록 목록에서 참조를 선택한다. 도구를 매핑한 것과 실행 어댑터가 구현된 것을 구분하며, 실행 연결이 없으면 미연결로 차단한다. 폼에서 이름이나 지침을 작성한 것만으로 임의의 코드·API가 구현된 것으로 표시하지 않는다.
- 국가·공장·라인·인프라 재사용·시스템 간 연계 여부로 적용 범위를 설정한다. 미국·헝가리·한국의 예시를 제공하고 전문가가 아직 정의하지 않은 시스템 절차는 예시로 표시한다.
- 초안 저장 → 검증 → 변경 확인·게시 → 새 진행 건 적용을 연결한다. 게시한 새 버전은 새 진행 건에만 적용하며 진행 중인 건은 시작 당시 절차·현장 조건·결과를 유지한다.
- 잘못된 입력 매핑·미연결 도구·순환 선행 조건을 검증한다. 검증 후 수정하면 재검증해야 게시할 수 있어야 한다.

## 5. 저장·실행 경계

- 실제 AI 대화·문서 조회와 합성 DB/AP 점검의 경계를 화면과 결과에 표시한다. ‘모든 것이 시뮬레이션’이라는 기존 지시를 적용하지 않는다. 이번 DB/AP 예시는 승인된 실제 업무 연결이 없는 모의 어댑터이며 실제 공장 점검 성공으로 표현하지 않는다.
- 업무 정의·진행 건·결과는 기존 DATA_DIR 아래 별도 업무 저장소에서 유지한다. 기존 Open WebUI DB·키·모델·대화·개인 자산은 재생성하지 않는다. ees.7에서는 사용자별 진행 건을 격리하고 관리자 정의 수정은 공유 절차에만 적용한다. 이 현행 저장 경계와 후속 [공동 작업 목표](#ees-work-shared-target)를 구분한다.
- 등록된 도구·스킬을 조회할 때 현재 사용자에게 허용된 범위를 따른다. 운영 DB 직접 접근·DML/DDL·범용 Shell을 추가하지 않는다. 후속 실제 연결은 승인된 API/Query Broker로 별도 검증한다.
- 기존 Workspace Skill 본문과 갱신 시각은 진행 건 시작 시 스냅샷으로 고정하고 공유 절차에는 참조만 둔다. 조회 시 현재 읽기 권한·활성 상태를 다시 확인하며, 권한이 없거나 비활성이면 본문을 제공하지 않고 관련 실행을 차단한다. 허용된 스냅샷 본문만 선택 업무의 AI 문맥에 제공한다.
- 기존 EES preset의 관리 구역과 지정 업무 Tool만 ApplyDemo로 연결하고 개인 Prompt·모델 선택·연동 자격증명·공유 설정을 보존한다. 미지원 기존 등록본이나 수동 수정 충돌은 덮어쓰지 않는다.
- 외부 CDN·폰트·아이콘·ChatGPT 전용 런타임 없이 로컬 자산을 사용한다. 한국어 가독성과 밝은/어두운 화면, 1920×1080과 축소 창을 확인하고 이모지는 사용하지 않는다.

## 6. 완료 조건과 배포

- 기존 실제 채팅 안에서 업무 선택 → 대화 요청 또는 패널 버튼 → 같은 실행 결과 → AI 후속 설명이 이어져야 한다. 독립 데모·iframe·가짜 입력창의 검사로 이를 대신하지 않는다.
- 공장·시스템 전환, 여러 진행 건 선택, 시작 전/완료/제외 표시, 고정된 절차 트리와 읽기 전용 실행 이력을 검증한다. AI 도구에서도 공장·프로세스 탐색·실행 재개·이력 조회를 같은 권한으로 수행할 수 있어야 한다.
- DB 성공·AP 실패/미수행·재시도·선행 조건·후속 무효화·상위 집계를 검증한다. 버튼과 Tool이 같은 상태를 읽고 변경하는지 확인한다.
- 관리자 편집·도구/스킬 매핑·검증 실패·수정·재검증·게시·새 진행 건 버전 적용·기존 진행 건 보존을 검증한다.
- 인증·사용자 간 격리·관리자 권한·대화별 진행 건 연결·새로고침 후 보존을 검증한다. 탐색·패널 열고 닫기·대화 이동 때 메시지와 작성 중 입력이 보존되는지 확인한다.
- 작성 중 텍스트·일반 첨부·도구/스킬 선택은 upstream의 기존 초안 직렬화와 복원 경로를 재사용해 검증한다. 이미지 임시 첨부는 upstream 기본 초안 보존 범위와 구분하고 모든 첨부의 영구 보존을 약속하지 않는다. 기존 Workspace 메뉴 이동 중 업무 절차 탭의 중복·반복 삽입·포커스 손실을 확인한다.
- 기존 일반 대화·문서 조회와 패널 진입의 회귀를 확인하고 네트워크 요청에서 합성 점검이 실제 DB/AP를 호출하지 않는지 구분한다. 사외 fixture/모의 모델 검사를 사내 실제 LLM·권한·SSO·업무 API 검증으로 표현하지 않는다.
- 관련 빌드·자동 시험·브라우저 E2E·문서 점검·diff 검사를 수행하고 실행한 범위만 기존 평가 기록에 남긴다. 불가능한 환경은 미실행으로 기록한다.
- 현재 프로그램 Upgrade와 지정 자산 ApplyDemo 경로로 배포한다. main·CI·산출물 상태와 실제 사내 반영을 구분한다. 사내에서만 가능한 마지막 단계는 짧은 PowerShell 블록과 화면 확인 항목으로 안내하며 기존 설정·복구 보호를 재사용한다.

## 참고 원본 보존

- 최초 HTML 원본은 87,747 bytes, SHA-256 `802a8943870e568e58f17976f2c478470b47a6a12b30b9caec486cf008687f67`이다. 당시 자료 식별값이며 현재 프로그램과 같은 바이트라고 주장하지 않는다.
- 원본의 ChatGPT Lucide 초기화·독립 앱·모의 대화는 참고 구현이다. 실제 포털에서는 기존 인증·Native 채팅·도구·패널을 사용한다.
- 원본 등록 당시 구문·모의 DOM 검사와 ees.5 브라우저 시연 검사는 과거 [참고 원본 기록](../../../evals/scenarios.md#ees-work-mockup-reference-20260914)·[배포 기록](../../../evals/scenarios.md#ees-work-demo-integration-20260914)에 보존한다. 현재 적용 방법은 [Native 가이드](../../03-openwebui-native-agent.md#ees-work-demo), 상태는 [STATUS](../../STATUS.md)가 원본이다.


<a id="integrated-work-20261002"></a>

## 2026-10-02 통합 구현 계약과 진행 기준

사용자가 제공한 `EES_Work_Integrated_Work_Directive_20261002.md` 및 후속 변경 관리 지시를 구현 기준으로 수용한다. 이 절은 앞의 Step별 구현 중단/추가 설계 승인 대기를 대체한다. 과거 조사·실패·완료 기록은 당시 근거이며 삭제하지 않는다. 개발·통합 검증·자체 수정·커밋/push·동일 Draft PR #73·배포 후보 준비까지 진행하고, main push/병합/실제 사내 적용/실제 사용자 자산 삭제/운영 변경 요청은 수행하지 않는다.

착수 Git: main `55832bad328cdfb91c1c284749f7959dd664176c`, PR #73 head `b41e23917273e1d2d0ead1ddadfea75b2dda1e32`, branch `docs/ees-restructure-step0a-20261001`. 검토 SHA 이후 변경 0, 로컬 변경 0. #72/#53은 별개 열린 Draft로 보존한다. 작업 공간의 이전 검증환경은 정리되어 없었으며 저장소 고정 환경을 같은 위치에 복구한다. 기존 조사·사내 복구는 반복하지 않는다.

### 구현 서비스와 보호 조건

| 의미 | 구현 위치/경계 | 완료 조건 |
|---|---|---|
| Native 인증·사용자·그룹·모델·대화·첨부 | 기존 Open WebUI, 개인 PAT/도구 설정 재사용 | 별도 인증/공용 PAT 없음, 계정·대화 격리 |
| 절차 초안·게시본·공장 설정·진행 건 | 기존 업무 SQLite 안의 Workspace 서비스, `/api/ees-work/workspace` | 게시본/시도 불변, 예상 revision·요청 ID/내용 지문, 미지정과 빈 값 구분 |
| 공유 범위·개인 화면 | Native ID 기반 명시적 시스템/공장 매핑 및 개인 화면 상태 | 그룹 이름 권한 추정 금지, 개인 대화 본문 공유 금지, 전체 공장도 ACL 적용 |
| 실행·예약·요청 | 동일 서버 수명과 DB를 쓰는 Operations 서비스, `/api/ees-work/operations` | 슬롯/claim/lease 영속, 현재 권한 재검사, 결과 불명 변경 요청 재전송 금지 |
| 사람 확정·EES 요청 | AI 도구와 분리된 인증 사용자 명령, 제한된 서버 intent | 0/1/2명 승인·최종 확인·내용/권한 변경 시 무효화, 완료 보고와 효과 확인 분리 |
| AI 초안 | Native 허용 모델, 구조/대상/context/revision 검증 | 제안만 반영, 자동 저장·게시·실행 금지, 모델 0개 명시 |
| UI | 기존 Native 대화 + 공통 탐색/업무/작성 패널 | 8입력/8블록, 내 업무 실제 건수, 키보드/스크롤/충돌/복원 |
| 기존 데이터·폐기 자산 | 기존 기록 보존, 새 설치 빈 상태, 명시적 정리 계획 | 옛 실행 중지와 기록 열람 분리, ApplyDemo 재등록 차단, 프로그램 Restore와 데이터 복구 구분 |

실제 EES 기능/인증/상태 조회 계약, 송부 채널, 미승인 CR 배포 정책 및 휴일 정보는 임의 생성하지 않는다. 화면·저장·검토·검증 가능한 서비스까지 구현하고 해당 외부 행동만 사유와 함께 차단한다. 외부 미연결·정책 미정·구현 누락을 구분한다. 기존 도구의 실제 Native 호출은 유지하며 합성 HTTP/모델 시험은 실제 사내 성공이 아니다.

### 변경 가능한 Figma 비교 기준

file `XK2wTos6sEuxSHhIj7cqg6`, page `832:131`, 2026-10-02 착수 조회. 페이지 metadata에서 최상위 20개 프레임을 확인했다. 페이지 자체 design context는 선택 레이어 필요 오류였으므로 개별 화면 context와 렌더를 조회한다. 이 제한은 화면 조회 성공으로 기록하지 않는다. 원본/노드 ID는 수정하지 않는다. 노드·렌더·context 해시와 화면→서비스→시험 대응은 이번 평가 근거에 기록한다. 버전 식별자를 제공하지 않는 도구의 조회 시점을 영구 디자인 버전으로 취급하지 않는다.

| 영역 | 현재 노드 |
|---|---|
| 안내/관리 | `832:132`, `897:762` |
| 내 업무/회차/위치/항목 판정 | A0 `919:7788`, A1 `832:8219`, A2 `832:8953`, A3 `875:8674` |
| 변경 요청/확인/추적 | A4 `881:659`, A4-1 `885:764`, A4-2 `888:758` |
| 절차 목록/개요/작업 편집/공장 차이/도구 | B1 `835:323`, B2 `836:372`, B3 `832:8468`, B4 `863:464`, B5 `920:728` |
| 규칙 | R1 `859:8586`, R2 `864:8706`, R3 `875:536`, R4 `879:641`, R5 `888:8861`, R6 `922:785` |

관련 화면을 구현·검수할 때 변경 여부를 다시 확인한다. 문구/스타일 변경은 영향 UI에, 입력/행동 변경은 API·저장·검증까지 반영한다. 새 업무·큰 정책 변경은 필요한 결정과 영향을 남기고 독립 작업을 계속한다. 예시 인명/공장/날짜/CR/성공 수치는 운영 기본 데이터가 아니다.

### 통합 검증과 완료 게이트

빈 설치/동시 초기화/재기동, 실제 Native 가입·승인·대화·첨부·격리, 절차 초안→검사→게시→진행, 입력/설정 snapshot·재실행·후속 재판정, 내 업무/예약 복구/복수 worker/권한 회수, 도구 검토/intent/요청 추적/효과, 고정 패키지·RECORD·기존 설치/프로그램 복구·자산 정리/데이터 복구를 각각 검증한다. 새 제품 코드의 실제 브라우저 검수는 이전 full-app smoke로 대체하지 않는다. 옛 데모 검사는 제거·재등록 방지로, 옛 UI 검사는 새 화면과 동일 보호 조건으로 대체하며 누락 ID를 명시한다. CI 분할은 모든 필수 job을 완료 게이트에 포함하고 실패/취소/미실행을 구분한다.

### 물리 저장소와 API 구체화

Native 인증·사용자·그룹·대화·첨부 DB는 기존 원본이다. 업무 데이터는 기존 DATA_DIR의 `ees-work.sqlite3` 안에서 확장한다. 별도 DB 엔진/서비스/범용 실행기를 추가하지 않는다. 초기화는 `BEGIN IMMEDIATE`의 같은 DB에서 수행하며, 기존 catalog/cases는 과거 기록으로 보존한다.

| 실제 테이블/진입 | 저장 의미와 강제 조건 | 직접 검증 |
|---|---|---|
| `work_schema`, `work_definitions`, `work_versions` | schema1·초안 revision·불변 게시본, `(workflow_id,version)` 고유, 검사한 정확한 정의/자원 버전만 게시 | `test_ees_work_workspace.py` 초기화/동시 생성/부분 손상/게시/rollback |
| `work_factories`, `work_access`, `work_settings` | Native ID 역할과 시스템/공장 범위, 반복 기본/공장 override. 공장 전용 입력은 기본·진행 입력으로 저장 금지 | 같은 파일 권한/설정/false·0·미지정/공장 담당 검사 |
| `work_runs`, `work_jobs` | 대화와 독립된 회차·시작 버전·개별 상태·담당 claim. 현재 담당자의 명시적 해제만 허용 | 같은 파일 격리/공유 경합/claim·release/종료·취소 |
| `work_attempts`, `work_decisions` | 입력/설정 출처·도구·모델·공장·근거·기한 snapshot, 끝난 attempt 불변·사람 판정 append-only | 재실행·의존 작업 재검토·과거 이력·현재 ACL 회수 |
| `work_receipts`, `work_audit`, `work_ui`, `work_chat_links` | actor+request ID+payload hash 멱등·감사, 개인 화면/개인 대화 참조 | 중복·다른 payload·늦은 응답·계정/대화 분리 |
| `work_tool_contracts`, `work_external_requests`, `work_request_intents`, `work_operation_events` | 검토된 Native 함수/hash·별도 요청 권한·제한된 intent·외부 요청과 효과 관측 | `test_ees_work_operations.py` 승인0/1/2·내용 변경·만료·권한 회수·결과 불명 |
| `work_schedules`, `work_schedule_slots`, `work_scope_runs`, `work_job_claims`, `work_operation_receipts` | 동일 서버의 영속 일정/P·T 조정/lease, workflow+범위+예정 슬롯 고유 | 같은 파일 재기동·복수 worker·놓침·위임·선행/시각·비상 |
| GET `/api/ees-work/workspace` | 현재 권한의 절차/진행/내 업무/개인 화면·관리자 매핑. 다른 사람 도구 근거와 권한 회수된 본인 근거는 본문 비공개 | HTTP route·Native 계정/작업 검사 |
| POST `/workspace/command`, `/workspace/proposal`, `/workspace/options` | 변경 명령, 저장하지 않는 AI 제안, 실제 Native/공통 선택지 조회를 분리 | route/model/dynamic choice 계약·실제 Native UI |
| GET/POST `/api/ees-work/operations` | 도구 검토·J 실행·동일 J의 P/T 조정·예약·요청/추적. 외부 connector 미설정은 typed 차단 | Operations + NativeBridge + 실제 HTTP |
| GET `/api/ees-work/legacy`, `/api/ees-work/export` | 소유자·대화·현재 근거 접근을 검사하는 과거 읽기, 현재 권한의 진행 기록 내보내기. 개인 대화 링크/화면/intent 제외 | route·workspace export·브라우저 내려받기 |

주요 일반 명령은 `create_workflow`, `copy_workflow`, `save_draft`, `validate_workflow`, `publish_workflow`, `save_factory`, `save_access`, `save_settings`, `start_run`, `save_inputs`, `claim_task`, `release_task`, `human_confirm`, `decide`, `amend_items`, `close_run`, `cancel_run`, `link_chat`, `save_ui`다. 일반 명령과 실행 서비스 모두 인증·현재 대상 권한·expected_revision·request ID/지문을 검사한다. AI 공개 도구는 조회/초안 제안/화면 안내 세 가지이며 변경 endpoint를 제공하지 않는다.

선택지와 선행 목록 인자 연결은 선언한 Native 함수·인자·결과 경로만 허용한다. 확정 목록 ID를 받는 후속 작업은 실제 확정된 현재 source attempt/revision/선택 ID를 snapshot하고, 부분 조회·미확정 목록·다른 사용자 비공개 근거를 자동 재사용하지 않는다. 결과의 `all_resolved`는 AI 보고 초안에만 허용하며 CR 미확인/보완 필요를 승인으로 바꾸지 않는다.

기한은 날짜 입력·calendar-day offset·명시적 timezone의 제한된 schema로 계산한다. 계산 결과와 입력 revision은 실행 snapshot에 남긴다. business-day/공휴일 자료가 없으면 날짜를 임의 당기지 않고 확인 불가로 남긴다. 외부 효과 API·송부 채널·미승인 CR 포함/제외 정책도 자동 확정하지 않는다.

### 화면·기능·검사 대응

아래는 구현 경로 대응이다. 단위/HTTP 계약 통과와 실제 Native 최종 통과는 [이번 평가](../../../evals/v4-ui-20260930.md#integrated-work-evidence-20261002)에서 별도로 판정한다. [Figma 비교 기준](../../../evals/artifacts/ees-integrated-20261002/figma-baseline.json)의 20프레임과 안내 `911:631`을 사용했고, A0/B3 재조회 metadata는 착수본과 동일했다. 원본 SVG44개를 읽기 전용으로 추출했고 기존33개를 유지했다. 디자인 원본은 수정하지 않았다.

| 화면/규칙 | 연결된 공통 기능 | 서비스/검사 근거 |
|---|---|---|
| A0 / R6 | 실제 내 업무·배지·기한/장애 정렬·담당·복귀, 정상 자동 대기 제외 | Workspace MyWork·Operations actionable / workspace·execution UI·Native work |
| A1 / R1 | 회차/게시 버전·업무 설정/이번 입력·P/T/J 실행·예약/놓침/기록 | Workspace/Operations / scheduler·scope·Native execution |
| A2 | 허용 공장/시스템·전체 공장 범위, 대화/미전송 글·편집 초안 보존 | workspace scope/private UI + Native chat / account·compose |
| A3 | 현재 결과의 CR별 AI 제안과 명시적 사람 판정·후속 재검토 | immutable attempts/decisions / delivery artifacts·workspace·UI |
| A4 / A4-1 / A4-2 / R5 | 등록/검토된 요청·0/1/2 승인·취소 초기초점/Esc·수락·상태·효과, 결과 불명 재전송 금지 | operations intent/request + Native dialog / request contracts·Native |
| B1 / B2 | 실제 절차 목록·검색·초안/게시·구조/일정/판정/게시 기록 | Workspace definitions/versions / authoring UI·Native authoring |
| B3 / R3 / R4 | 공통8입력/8블록·Native 도구/스킬·정확한 인자/선택지·AI 편집 제안 | schema/options/proposal + designer / authoring47+workspace/model |
| B4 / R2 | 기본 정의·공장 override/조건·복사·반수 경고·끊긴 참조 차단 | definition checker/settings / factory·publication tests |
| B5 / R6 | 조회/요청 도구 초안·가이드·담당자 검토·정의 hash 변화 | Operations tool contract + Native inspect / authoring·operations |
| 안내/M0 | Native 실제 모델 이름/0·1·복수 접근, 사람/AI/EES Work/EES 주체 구분 | NativeModelAdapter·safe Work Tool / model·Native chat |
| 별도 상세 프레임 없음 | Native 대화 기록·스킬 관리 진입, 관리자의 범위 설정·빈/오류/권한/충돌·내보내기 | 기존 Native route·공통 폼/토큰, 새 인증/스킬 복제 없음 |

배포 산출물 점검은 운영 기본 데이터가 아니다. 시험에서 작성 API로 만든 절차를 게시하고 실제 loopback Jira HTTP로 여러 페이지 CR→확정 목록→필수 파일 이름/존재/접근→AI 제안→CR별 사람 판정→보완 재실행→보고 초안/검토/내보내기를 연결한다. 파일 내용 적정성 미검토를 승인으로 표현하지 않는다. 실제 회사 Jira/LLM/EES 성공으로 보고하지 않는다.
