# 현재 작업 상태

갱신일: 2026-10-01

현재 작업·다음 작업·미해결·실제 적용 원본을 관리합니다. 이슈·검증 근거는 [평가 기록 찾아보기](../evals/scenarios.md#evidence-index), 환경은 [versions](../versions.md), 완료된 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 현재 작업과 다음 작업

- **현재 작업:** [Draft PR #73](https://github.com/knadalkim-a11y/team-agent-poc/pull/73)의 검토 head `d0b0aa338a47f73fac322bcb4426afc4381a68f6`에서 Step 0-B 잔여 CSS 시험·Windows 두 오류·한글 캡처를 보완한다. 기본 계약·환경·실제 Native 최소 왕복·Linux 가입/계정 전환은 검토 수용된 근거로 재사용한다. [이번 관측·검증](../evals/v4-ui-20260930.md#restructure-step0b-residual-20261001)에서 각 문제를 구분하며 전체 CI 통과로 보고하지 않는다. [7개 기본 계약](mockups/ees-work/TASK.md#restructure-step0b-20261001) 이후 상세 DB/API·공유 정책·서버 확정 방식은 계속 미확정이다.
- **Git 기준:** main `55832bad328cdfb91c1c284749f7959dd664176c`, 이번 잔여 검증의 검토/시작 head `d0b0aa338a47f73fac322bcb4426afc4381a68f6`, branch `docs/ees-restructure-step0a-20261001`. 시작 시 검토 SHA 이후 원격 변경0·추적277파일의 blob 동일을 확인하고 끊어진 로컬 Git 연결만 복구했다. 이전 Step 0-B 시작 `d5b1df7`과 기본 계약/시험 보완의 구분 커밋은 보존한다. #72/#53은 적층하지 않는다.
- **변경 경계:** 제품 코드·업무 저장 구조·Figma·데모 자산·사내 설정은 변경하지 않는다. 별도 서버/DB 엔진/브라우저 프레임워크를 추가하지 않는다. 환경·Native fixture·실제 제품·사내 연동 결과를 [이번 증거](../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001)에서 구분한다.
- **검증 상태:** 저장소 단일 `.venv`(Python3.11.16)·공식 해시 wheel·Chrome153과 실제 제품 빌드를 준비했다. Native 가입/승인/권한·계정 전환·직접 영향 회귀8개 PASS(skip0), 실제 Native CLI/임시 DB에서 첫·기존·새 대화 물리 보내기3회·저장/리로드/격리 PASS. 모델은 loopback 합성이며 사내 호출 성공이 아니다. sidebar·V4 탐색 selector의 시험 결함을 보완했고 최초 CI 가입 탐색 실패의 정확한 원인은 미확정이다. [환경 재사용·명령·실패/최종 증거](../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001).
- **잔여 검증:** CSS 독립 해시/바이트 검사31개 PASS, 실제 CI 가입/승인6개·계정 전환1개 PASS 및 한글 원본 PNG/Noto28 glyph 확인. Windows 고정 source의 CRLF 변환과 SQLite 연결 미닫힘을 보완해 최종 지정2개가 실제 Windows에서 PASS했고 원래 archive SHA·모든 source/member/RECORD/ZIP가 일치했다. 관련 로컬31개도 PASS다. Native 로컬 최초 고유12PASS/3FAIL/58미실행은 보존하고, 직접 호출부 보완 후 고유20개13PASS/7FAIL/53미실행을 따로 기록한다. 원격 부분 실행과 합산하지 않는다. [원인/가설/보완/재검·원본 증거](../evals/v4-ui-20260930.md#restructure-step0b-residual-20261001).
- **원격 검사:** `cddf0eb`의 [완료 run36830859677](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/36830859677)은 cancelled, 전달물 skipped다. Windows 지정2개 PASS 뒤 shared suite에서 선행 FAIL/ERROR 없이10분 후 취소. Linux는 Native/CSS 등 PASS 뒤 demo 통합에서 성공4개·실패메서드12개 증거를 남기고 취소, 후속 C1/C2/C3는 원격 미실행이다. Windows artifact11147292820 실제10파일·Linux11147134607 실제44파일/실패12쌍의 digest와 한글 화면을 확인했다. 종료 후 발견한7개 닫힌 패널 대기·1개 구 select-value 기대의 직접 helper 누락만 보완했다. 추가 대표5개는 준비가드를 통과해1PASS/4FAIL이며 구 tree/집계/버튼 기대의 새 실패 지점에서 중단했다. 옛 A안 치수·Native 입력 저장 경계·과거 완료 집계 및 원격 나머지 미분류 실패는 유지한다. 후속 최종 helper 변경의 자동 결과는 [PR Checks](https://github.com/knadalkim-a11y/team-agent-poc/pull/73/checks)/본문에 정확한 head로 연결하며 기존 실패/취소를 덮어쓰지 않는다.
- **사내 상태:** 미병합 [PR #72](https://github.com/knadalkim-a11y/team-agent-poc/pull/72)의 10-01 10:26 KST 사용자 복구·UI 일부 반영 보고가 최신 출처다. 완료한 복구/배포를 반복하지 않는다. 새 사내 접속·모델·PAT·DB·등록 목록 확인은 이번에 수행하지 않는다.
- **다음 작업 하나:** 검토 담당이 이번 계약·검증과 남은 CI 차단을 검토하고 상세 설계·Step 1 구체 구현 계약을 전달하기를 기다린다. Step 1·자산 삭제·병합·Draft 해제·배포는 자동 시작하지 않는다.

이전 V4 복구 이력과 Step 0-A 조사/당시 실패는 기존 평가에 보존한다. 과거 승인을 이번 사내 변경 승인으로 사용하지 않는다.

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

## 남아 있는 이슈와 확인 범위

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

현재 재구성 순서와 통과 조건은 [Step0-B 기본 계약·수락 보완](mockups/ees-work/TASK.md#restructure-step0b-20261001)과 그 안의 Step0-A 단계표를 따른다. 아래 목표별 표는 이전 진행 이력이며 Step1 실행 권한이 아니다.

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

현재 재개 대상은 위 Step 0-B와 PR #73이다. 아래 첫 항목의 V4 복구·재배포 설명은 당시 이력이며, 최신 사용자 보고로 완료된 사내 복구를 다시 수행하라는 지시가 아니다.

- 다음 세션은 그때의 원격 최신 main·관련 열린 PR·로컬 변경을 확인하고 AGENTS와 이 문서를 읽습니다. 과거 적용 SHA를 개발 head로 고정하지 않습니다. EES Work의 현재 작업은 [4차 UI 후속 수정](../evals/v4-ui-20260930.md#v4-ui-breakage-fix)이며 #69 병합3a51의 종료 실패와 PR #70 병합 뒤의 retained_bundle_mismatch 후속 수정·최신 main/열린 PR을 먼저 확인한다. 설치본713·등록 프로세스 잔류·listener 부재 보고 뒤의 실제 복구 결과부터 확인하며 과거 Status 확인을 반복하지 않는다. PR #68은 main에 병합됐고 사용자가 사내 화면 파손을 보고했다. 이번 권한은 09-30 18:04의 #69 후속 승인에 근거하며 완료한 수정/검사를 반복하지 않는다. #67까지의 C안은 병합된 기반이며 종료된 시각 작업을 재개하지 않는다. 기존 [09-29 C안 2단계](mockups/ees-work/TASK.md#c-design-phase2-20260929)와 [검토 보완](mockups/ees-work/TASK.md#c-design-phase2-review-20260929)을 보존하고 [3차 개발환경 검수](mockups/ees-work/TASK.md#c-design-phase3-20260929)를 완료했다. 완료된 1·2단계·보완·3차 검사를 미완료로 보아 반복하지 않는다. [09-23 A안](mockups/ees-work/TASK.md#a-design-20260923)·Figma 478:131/498:363은 기존 구현 근거로 보존하고 [09-22 단계별 UX](mockups/ees-work/TASK.md#step-progress-ux-20260922)·[확정 왼쪽](mockups/ees-work/TASK.md#sidebar-final-20260922)·[오른쪽 기록 계약](mockups/ees-work/TASK.md#right-panel-20260922)을 보존합니다. 기존 HTML·223번 통합안·공동 작업 장기안은 이번 단계별 진행 화면을 대체하지 않습니다. 새 ZIP이나 이전 대화 전체가 없어도 이 경로에서 이어갑니다. 별도 인계 파일은 만들지 않습니다. 수락 보호는 [적용 가이드](03-openwebui-native-agent.md#ees-accept64-guard)·[장애·검증 근거](../evals/scenarios.md#accept64-guard-20260914)를 보존하며 관련 변경이 있을 때만 해당 코드/시험을 읽습니다.
- 브랜치 정리 완료: 사용자 `branch_cleanup=ok, deleted=32` 보고와 원격 조회로 대상 32개 삭제를 확인함. 정리 당시 남은 브랜치는 `main`과 미병합 커밋 3개가 있는 `fix/upgrade-apply-failure`였으며, 미병합 head `b088f3be029dae108d82d6feec003fbd55bf5245` 보존을 확인함. [고정 대상·완료 근거](../evals/scenarios.md#repository-maintenance-20260911).
- 사내 결과 전달은 직접 타이핑 1~2줄만 가능함. 전체 로그·파일·사진을 요구하지 않으며 복사 블록은 각각 2,500자 이내. 기존 clone·Git 프록시 설정 완료 보고를 재사용하고 허용된 외부 호스트·기존 캐시만 전제함. 웹 프로젝트 지침의 저장소 참조 문구도 이미 설정한 것으로 유지함.
- 등록된 `manage-ees.ps1`의 Python·작업 위치·주소·DATA_DIR·DB·키·계정을 유지함. 설치 예제의 loopback·기본 폴더로 현재 등록값을 덮지 않음. [등록 설정과 기록 위치](03-openwebui-native-agent.md#ees-local-state). 중단한 후보 환경 Diagnose/Deploy는 재개하지 않으며 과거 도구·실패·복구 증거는 보존함.
- 현재 사내 모델은 [GLM 5.3 UI 반영 보고](../versions.md#사내-모델-운용-기준)를 따르며 작은 Tool·짧은 절차·일반 JSON을 유지함. 과거 GLM 5.2 결과를 새 모델의 검증으로 바꾸지 않고 다음 관련 사용에서 대표 업무·실패/금지 요청을 비교함. 화면·답변에 이모지를 쓰지 않음. 기존 Hermes·팀원 작성물은 보존하며 서비스화·서버 이전·별도 Router/A2A/자동 동기화·공통 UI 프레임워크는 실제 필요에 따라 후속으로 다룸. [공통 자산 관리 경계](../README.md#원본과-배포본).

## 최근 점검

2026-10-01 Step0-B: 기본 계약과 미확정 상세 경계 반영, 저장소 검증환경 준비, 실제 Native CLI/합성 데이터 브라우저 왕복, 관련8개 회귀를 검증했다. 제품/CI는 변경하지 않았으며 기본 설계·시험 도구 커밋을 분리했다. [이번 평가](../evals/v4-ui-20260930.md#restructure-step0b-evidence-20261001)에 원래 실패·후속 실패·재검·원격 CI를 각각 보존한다.

상태가 바뀔 때만 이 문서를 갱신하고 다음 작업 하나·현재 미해결·최근 점검 요약을 유지합니다.
