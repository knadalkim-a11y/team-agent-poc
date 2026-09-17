# 현재 작업 상태

갱신일: 2026-09-18

현재 작업·다음 작업·미해결·실제 적용 원본을 관리합니다. 이슈·검증 근거는 [평가 기록 찾아보기](../evals/scenarios.md#evidence-index), 환경은 [versions](../versions.md), 완료된 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 현재 작업과 다음 작업

- 이번 장애 수정: 사용자가 배포 실패 뒤 복구 진행을 보고하고 원인 분석·수정을 요청함. main `0d46b8e1dcf8e9961e05cfc1a42f4768d2241311`의 공통 `port_is_free`에 Windows bind `10048`만 0.25초 간격·10초 예산·최대 40회 재확인을 준비함. 지속 점유는 실패로 유지하고 주소 공유·프로세스 종료·자동 복구를 추가하지 않음. 기존 [Draft PR #55](https://github.com/knadalkim-a11y/team-agent-poc/pull/55)를 재사용해 bind 실패 뒤 close 오류를 잘못 재시도하던 경계도 보완함. 코드·시험 변경은 미병합이며 사내에 적용하지 않음.
- 관측과 한계: ees.10 Upgrade의 `changed=false`, `port_check`(입력은 `prot_check`), `operation=port_bind`, `errno/winerror=10048`, `ees_deploy_process.py:171`을 코드와 대조함. 직후 Status의 기존 프로그램 `7bdd2ce93dc4`, `running=false`, TCP/owners 없음과 이후 복구 진행 보고를 구분함. 실패는 Stop 뒤 프로그램 Apply 전의 단발 bind 검사 경로와 일치함. 후속 사용자 보고에서 Restore 없이 안내 1번의 Start만 실행해 정상 서비스로 복구한 것을 확인함. 당시 소켓 상태가 없어 TIME_WAIT·특정 점유 프로세스를 확정하지 않으며 최종 실행 SHA·health 수치는 새로 수신하지 않음.
- 다음 작업 하나: 이 포트 수정 브랜치에서 전체 checkout을 확보해 관련 운영 시험과 `scripts/check_docs.py`를 실행하고, 기존 `evals/scenarios.md`·운영 가이드·CHANGELOG에 이번 근거와 변경을 통합한 뒤 검토를 마침. 현재는 부분 checkout 검사만 가능해 Draft로 유지함. 원격 CI 생략 방침은 유지하며 복구된 사내 서버에서 Stop/Restore/재배포를 반복하지 않음.
- 앞선 업무 패널 구현: 09-16의 `설계까지만 진행` 뒤 사용자가 `구현배포도 진행하자`와 이어서 진행을 승인해 [업무 패널·대화 통합 설계](mockups/ees-work/TASK.md#work-panel-chat-design-20260916)를 ees.10 / Agent Pack v0.2.11에 구현·검토함. P는 직속 T 표, T는 직속 J 표, J는 입력·결과·근거를 중심으로 정리하고, 게시 절차의 읽기 전용 선택·첫 저장/실행·중복 요청 복구와 대화의 대상 고정·초안 충돌 보호를 연결함. 기존 Workspace 디자인·GLM 5.3 설정·사용자 자산을 보존함. [당시 설계 검토](../evals/scenarios.md#work-panel-chat-review-20260916)와 [이번 구현·검사 근거](../evals/scenarios.md#work-panel-chat-implementation-20260917)를 구분함.
- 앞선 준비: 업무 패널·Workspace [PR #52](https://github.com/knadalkim-a11y/team-agent-poc/pull/52)는 병합·고정 원본 시험 적용 안내까지 준비됨. 당시 제품 검사는 77 PASS·3 SKIP, 적용 경로 검사는 추가 30 PASS·1 SKIP이며 이번 설계의 시험 결과로 합산하지 않음. [기존 적용 안내](03-openwebui-native-agent.md#ees-work-panel-trial-20260916), [당시 근거](../evals/scenarios.md#workspace-native-design-20260915). 사내 GLM 5.3 설정과 기존 자산을 유지하며 해당 원본의 실제 설치·화면 확인은 여전히 미수신임.
- Git 원본: 구현·검사 원본은 [PR #54](https://github.com/knadalkim-a11y/team-agent-poc/pull/54)에 게시함. 코드 커밋 `cb48636887d144b0436e86e34f3669941ff3d64f`의 tree를 검증한 로컬과 대조했고, 배포 안내는 이 PR의 최종 병합 40자리 SHA를 사용함. 이번 구현은 [PR #52](https://github.com/knadalkim-a11y/team-agent-poc/pull/52)가 반영된 main `7bdd2ce93dc47ffb58b732f35662ad8e849c7215`에서 이어감. 별도 Draft [PR #53](https://github.com/knadalkim-a11y/team-agent-poc/pull/53)의 `docs/ptj-contract-runtime-poc-20260916`은 후속 Runtime/Figma 설계로 보존하며 이번 제품 구현·시험 배포의 원본으로 채택하거나 함께 병합하지 않음. 검토·배포 목적이 달라 이번 변경은 별도 PR로 관리함. 09-15의 성공 확인 원본 `87f3f2922a4ab830bcee1022ed7045e624a36777`을 보존함. 이후 장애 당시 Status의 `7bdd2ce93dc4`와 최종 복구 원본 미확인을 위 관측에 별도로 기록하며 Git 병합·안내 전달을 사내 설치 성공으로 간주하지 않음.
- 최근 UI 확인: 09-15 앞선 ees.8의 공장·시스템 선택 박스, 프로세스 직계 태스크 펼침, 글꼴·설명 행 정리, 대화·작성 중 초안 유지 네 항목 정상 보고는 보존함. 이번 ees.9 설치 후 화면·기존 대화 확인은 아직 미보고이며 앞선 수락을 새 화면 결과로 바꾸지 않음. [앞선 수락](../evals/scenarios.md#sidebar-refinement-20260914).
- 최근 운영 확인: 09-15 `stop → backup → apply`, `upgrade result=ok changed=true wrapper_changed=false version=0.11.3+ees.9 running=true` 보고. 정상 완료의 실행 순서상 검증 백업과 기동 health도 통과한 것으로 판단함. 새 다운로드와 원본 캐시 재사용 중 어느 경로였는지는 출력에서 구분되지 않음. 유휴 안정성과 이전 rename 접근 거부의 근본원인은 이번 성공으로 확정하지 않음. [이번 적용](../evals/scenarios.md#work-ui-refactor-20260915), [이전 복구](../evals/scenarios.md#ees7-apply-recovery-20260914), [수신 보호](../evals/scenarios.md#accept64-guard-20260914).
- 최근 제품 변경: 같은 원본의 `apply_demo result=ok changed=3 stage=complete code=- next=new_chat` 보고. 관리 목록 내 적용·쓰기 후 확인 성공이며 개별 변경 대상 3개를 추측하지 않음. 기존 v0.2.9/ees.8 수락과 과거 자산 충돌은 [앞선 기록](../evals/scenarios.md#sidebar-refinement-20260914), [정렬 충돌 이력](../evals/scenarios.md#specialists-editor-format-20260914)에 보존함.
- 장애 수정 뒤 재개할 UI 확인: 포트 수정 [PR #55](https://github.com/knadalkim-a11y/team-agent-poc/pull/55)의 남은 검증·문서 통합·병합 후 그 고정 원본으로 ees.10 적용과 기존 대화·P/T/J·입력 초안 유지 여부를 확인함. 수정이 없는 기존 PR #54 원본을 재배포 완료본으로 안내하지 않음. [기존 시험 적용 경로](03-openwebui-native-agent.md#ees-work-panel-trial-20260917)의 Upgrade는 성공 뒤 ApplyDemo까지 호출하므로 중복 자산 적용을 추가하지 않음. 실제 Windows 설치·Native 화면·사내 GLM 확인은 코드 검사와 분리하며, 이미 안내한 PR #52의 적용 결과가 나중에 도착하면 당시 원본의 별도 근거로 기록함.
- 이전 사내 성공 확인: 09-15 래퍼/프로그램 `87f3f2922a4a`의 ees.9 기동과 같은 자산 원본의 변경 3건 성공에 이어, 메인 채팅의 업무 요청 재시도 정상 동작을 사용자가 보고함. 첫 Knowledge 전용 응답과 일반 Upgrade의 CI 실패를 보존하며 재시도 성공을 원인 해결로 해석하지 않음. [실패·성공·한계](../evals/scenarios.md#work-ui-refactor-20260915).

## 2026년 9월 개발·검사 방침

사용자 선택으로 **2026-09-30까지 이 작업의 GitHub 원격 검사를 생략**한다. 이 저장소에 게시하는 개발·문서 커밋 메시지마다 `[skip ci]`를 넣어 기존 `push`/`pull_request` 자동 검사를 생략하며 수동 실행·재실행은 요청하지 않는다. PR 본문에만 적거나 이전 커밋의 표시가 이후 커밋에도 적용된다고 가정하지 않는다. 이는 작업 커밋별 생략이며 계정 전체 Actions를 비활성화한 것이 아니다.

코드 작성·Git 반영·변경 범위의 로컬 검토/시험과 문서 검사는 계속한다. **후속 사용자 합의로 원격 검사 생략을 9월 전체 배포 금지로 확대하지 않고, 로컬 검증 후 변경별로 제한된 시험 적용을 준비한다.** 검토한 정확한 원본·배포물 해시·자료 보존·기존 프로그램 복원 수단을 확보하고 적용 뒤 기동·기존 대화·업무 저장·변경 화면을 필요한 소수 항목으로 확인한다. 사내 사용자 자료의 백업과 프로그램 Restore를 구분한다. Windows·Native 브라우저 미실행은 그대로 남기고 실제 사내 적용 전후 결과를 별도로 기록한다. 기본 Upgrade/ApplyDemo의 CI 확인은 유지한다. 후속 사용자가 배포 진행과 수동 ZIP 단계 자동화를 요청해 공개 TrialCommit 경로·Backup·자동 묶음 준비를 연결했으며, 검토한 원본의 병합과 실제 사내 적용 성공은 각각 확인한다. 자체 실행기·Linux 가상환경 설치·브라우저 시험 이식·결제 설정 변경은 추가하지 않는다.

**2026-10-01 이후 처음 작업을 재개할 때** 이 한시 생략을 종료하고 무료분 복구 상태와 최종 변경 범위를 확인한다. 마지막 코드에 대해 표시 없는 새 커밋 또는 기존 수동 실행으로 필요한 원격 검사를 수행한다. 10월 1일 예약 실행을 만든 것은 아니며 과거 생략된 검사가 자동으로 재개되지 않는다. 사용자 변경 지시가 있으면 해당 지시를 우선한다. [근거·재개 조건](../evals/scenarios.md#work-ui-refactor-20260915).

## 마지막으로 확인된 적용 상태

사용자 보고 시점의 확인이며 실시간 서버 점검 결과가 아닙니다. Git 게시·CI 성공·안내한 SHA를 실제 사내 등록 바이트와 혼동하지 않습니다.

| 대상 | 마지막 확인과 적용 원본 | 남은 한계·근거 |
|---|---|---|
| EES Work 업무 UI | 09-15 ees.9 설치 완료, 메인 채팅 업무 요청 재시도 정상 보고, 앞선 ees.8 UI 수락 유지 | 도구 호출 원문·단계별 실행·화면 반영·기존 대화 접근은 이번 보고에서 별도 확인하지 않음. [이번 배포·사용 보고](../evals/scenarios.md#work-ui-refactor-20260915), [앞선 UI 수락](../evals/scenarios.md#sidebar-refinement-20260914) |
| EES 프로그램 | 09-17 장애 직후 Status `7bdd2ce93dc4`, `running=false`; 이후 Restore 없이 Start만으로 정상 서비스 복구 보고 | 최종 실행 SHA·health 수치는 미수신. 09-15 `87f3f2922a4a` / ees.9 기동 성공은 [당시 기록](../evals/scenarios.md#work-ui-refactor-20260915)에 보존. 새 ees.10 설치 성공으로 해석하지 않음 |
| 운영 래퍼 | 09-17 실패 출력 `0d46b8e1dcf8`, `wrapper_changed=false`, Upgrade `changed=false` | 포트 수정은 미병합·미배포. 09-15 시험 Upgrade/ApplyDemo 성공은 [당시 기록](../evals/scenarios.md#work-ui-refactor-20260915)에 보존 |
| 분석·업무 패널 자산 | 09-15 `87f3f2922a4a` / Agent Pack v0.2.10 ApplyDemo 성공, 변경 3건, 메인 채팅 업무 요청 재시도 정상 보고 | 개별 변경 항목·분석 기능·업무 전체 실행의 확인으로 확대하지 않음. [이번 적용·사용](../evals/scenarios.md#work-ui-refactor-20260915) |
| 대표 시작 질문 | 09-15 `87f3f2922a4a`의 v0.2.10 관리 목록을 포함한 ApplyDemo 성공 | 질문의 실제 표시 여부는 미확인. 변경 3건을 특정 질문 변경으로 단정하지 않음. [이번 적용](../evals/scenarios.md#work-ui-refactor-20260915), [이전 접속 실패](../evals/scenarios.md#connector-demo-starters) |
| WO 목업 | v0.1.6 안내 원본 `ba396da8d1d0abcb4e17494e8d9b37c5add514fc` 뒤 크기 조절 정상 보고; Git은 v0.1.8 통합 패널 원본 | 실제 EMS 미연결. 이후 패널 적용 보고와 개별 등록 바이트 검증을 구분. [목업 이력](../evals/scenarios.md#wo-mockup) |
| 기본 Assistant·기존 조회 | 이름·로고·기존 대화·평소 Confluence/Jira/GitHub 조회 정상, 초기 Rich UI 제거·변경 Prompt 반영 완료 보고 | Tool별 최신 등록 코드·SHA·새 일반 답변/원문 직접 대조 미실행. [반영 보고](../evals/scenarios.md#plain-output-applied-report), [이전 자산별 SHA](../evals/scenarios.md#status-history-20260911) |
| 정책·Skill | 합성 정책·지침 저장 보고, P02 PASS·P03 일부 확인. Git/UI 등록 Skill 3개, 기존 2개의 사용 확인 | 실제 사내 정책·나머지 P 시험·confluence-read 실제 로딩 미확인. [기준](../evals/scenarios.md#instruction-revision) |

## 남아 있는 이슈와 확인 범위

- **9월 원격 검증 보류:** 사용자 Billing 화면에서 Actions 무료분 `2,000/2,000` 사용 및 현재 Actions 청구 대상 `$0`를 확인함. 사용자는 9월 원격 검사 생략·개발 계속을 선택함. 결제 실패로 단정하거나 예산 상향을 다음 작업으로 요구하지 않음. R1~R3의 Windows·브라우저 자동 검사는 미실행이며 이전 실패와 로컬 결과를 보존함. ees.9 사내 적용·기동·지정 자산 반영 성공은 이번 사용자 보고로 따로 확인함. [이번 무료분 확인·한시 방침](../evals/scenarios.md#work-ui-refactor-20260915), [앞선 관측](../evals/scenarios.md#workflow-refactor-20260915).

- **공통 자산 업데이트 중 동시 편집:** 기존 GET→POST 사이 지원 description 유실의 합성 결함을 R0 조건부 저장·native 보호 경로로 수정하고 실제 wheel 회귀에서 확인함. 이번 ees.9 설치와 보호 API를 사용하는 ApplyDemo 성공으로 사내 반영을 확인함. 실제 사내 동시 편집 충돌 재현까지 확인한 것은 아님. 보호 미적용 원본 서버·외부 DB writer·일반 UI끼리의 오래된 폼 충돌은 보장 밖. [원래 재현/오탐 정정](../evals/scenarios.md#ai-runtime-preservation-20260915), [수정·검증·적용 경계](../evals/scenarios.md#conditional-assets-20260915).
- **사외 Windows CI 지연:** 이전에 통과한 동일 코드에서 PowerShell 20초·Node 10초 제한시간 초과가 각각 발생했으며 원인은 미확정임. 두 시험의 단계 표식·런타임 버전·timeout의 단계 표식를 보존하도록 보완했으므로 자연 재발 시 그 증거로 진입 관측 여부와 시험 내부 단계를 구분함. 재검사 성공을 근본원인 해결이나 사내 서버 진단 필요로 바꾸지 않음. [실패·관측·최종 CI](../evals/scenarios.md#sidebar-refinement-20260914).
- **메인 채팅의 업무 활용:** 읽기 전용 후보/절차 조회·스킬 지침·기존 진행의 고정본 계획과 목표 기반 Prompt를 구현함. 사내 첫 요청은 Knowledge 검색만 한 뒤 업무 도구 미연결로 답했으나 사용자가 재시도 정상 동작을 보고함. 요청의 도구 선택 상태와 실제 호출 이력은 미확인으로, 일시적 비활성화·브라우저 갱신 지연·모델 선택 중 원인을 확정하지 않음. 정상 사용을 계속하며 자연 재발 시에만 해당 대화의 도구 노출을 확인함. 단계별 실행·화면 반영·공유 검증으로 확대하지 않고 한 진행 건/한 대화·외부 도구 미연결·DB/AP 모의 점검 경계를 유지함. [이번 관측·판단](../evals/scenarios.md#work-ui-refactor-20260915).
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

| 목표 | 현재 위치 | 후속 범위 |
|---|---|---|
| 1. 쉬운 Chat UI | 이름·로고·스트리밍·폭/조절 표시 정상 보고 | 새 제안 확인, 비개발자 사용성, 관리자 팀 공지 |
| 2. 문서 시스템 | Confluence·Jira·GitHub 읽기·변경 Prompt 반영 보고 | 실제 업무 조회·후속 해석·새 일반 답변/원문 확인 |
| 3. 관리자 공통 정책 | 합성 지침·정책 답변 Skill 저장 보고 | 실제 공통 원칙·상세 절차·권한/Tool 제한·변경 반영 |
| 4. 관리자 워크플로 | ees.9 적용·채팅 업무 재시도 정상 보고, ees.10 P/T/J 패널·대화 계약 로컬 검증 완료 | 이번 개인 진행 흐름의 원본 게시·시험 적용을 마무리한 뒤 [참여·개인 대화 분리·동시 변경·이어가기 UX](mockups/ees-work/TASK.md#shared-pilot-first)를 구체화. 일정·종합 현황판은 별도 후속 범위 |
| 5. 레거시 연동 | 실제 업무 API·DB 미연결 | 승인된 API/Query Broker의 작은 읽기 기능 하나 |
| 6. 레거시 간접 UI | 같은 폼에서 직접 입력·AI 작성/수정의 WO 합성 시연 | 시연 피드백 → 운영 목업 → 실제 EMS 연결 |

사용자 결정으로 WO와 시스템 간 분석 시연을 먼저 진행했습니다. 준비된 화면을 상황에 맞게 활용하고 SHOP → LINE → PROCESS 검색 계층을 유지합니다. 공통 정책의 미완료 상태를 지우지 않으며 전체 시스템·권한 세분화·대형 오케스트레이션 기반을 시연의 선행조건으로 늘리지 않습니다. 첫 파일럿은 범용 채팅과 세 문서 시스템 읽기를 바탕으로 실제 업무 완료·결과/오류/공유 이해를 확인합니다. 기능 하나의 구현·관련 검사·짧은 사내 확인을 묶고 영향 없는 인증/저장 시험은 반복하지 않습니다.

<a id="resume-branch"></a>

## 재개와 환경 유지

- 다음 세션은 그때의 원격 최신 main·관련 열린 PR·로컬 변경을 확인하고 AGENTS와 이 문서를 읽습니다. 과거 적용 SHA를 개발 head로 고정하지 않습니다. EES Work는 [최종 공동 작업 합의를 포함한 작업 지시](mockups/ees-work/TASK.md#ees-work-shared-target)와 그 문서가 연결한 목업을 읽습니다. HTML은 이전 화면 참고이며 공동 작업·권한 설계는 최신 문구가 우선합니다. 새 ZIP이나 이전 대화 전체가 없어도 이 경로에서 이어갑니다. 별도 인계 파일은 만들지 않습니다. 수락 보호는 [적용 가이드](03-openwebui-native-agent.md#ees-accept64-guard)·[장애·검증 근거](../evals/scenarios.md#accept64-guard-20260914)를 보존하며 관련 변경이 있을 때만 해당 코드/시험을 읽습니다.
- 브랜치 정리 완료: 사용자 `branch_cleanup=ok, deleted=32` 보고와 원격 조회로 대상 32개 삭제를 확인함. 정리 당시 남은 브랜치는 `main`과 미병합 커밋 3개가 있는 `fix/upgrade-apply-failure`였으며, 미병합 head `b088f3be029dae108d82d6feec003fbd55bf5245` 보존을 확인함. [고정 대상·완료 근거](../evals/scenarios.md#repository-maintenance-20260911).
- 사내 결과 전달은 직접 타이핑 1~2줄만 가능함. 전체 로그·파일·사진을 요구하지 않으며 복사 블록은 각각 2,500자 이내. 기존 clone·Git 프록시 설정 완료 보고를 재사용하고 허용된 외부 호스트·기존 캐시만 전제함. 웹 프로젝트 지침의 저장소 참조 문구도 이미 설정한 것으로 유지함.
- 등록된 `manage-ees.ps1`의 Python·작업 위치·주소·DATA_DIR·DB·키·계정을 유지함. 설치 예제의 loopback·기본 폴더로 현재 등록값을 덮지 않음. [등록 설정과 기록 위치](03-openwebui-native-agent.md#ees-local-state). 중단한 후보 환경 Diagnose/Deploy는 재개하지 않으며 과거 도구·실패·복구 증거는 보존함.
- 현재 사내 모델은 [GLM 5.3 UI 반영 보고](../versions.md#사내-모델-운용-기준)를 따르며 작은 Tool·짧은 절차·일반 JSON을 유지함. 과거 GLM 5.2 결과를 새 모델의 검증으로 바꾸지 않고 다음 관련 사용에서 대표 업무·실패/금지 요청을 비교함. 화면·답변에 이모지를 쓰지 않음. 기존 Hermes·팀원 작성물은 보존하며 서비스화·서버 이전·별도 Router/A2A/자동 동기화·공통 UI 프레임워크는 실제 필요에 따라 후속으로 다룸. [공통 자산 관리 경계](../README.md#원본과-배포본).

## 최근 점검

2026-09-18 후속: 사용자의 Start 단독 복구 보고를 반영하고 같은 Draft PR #55를 보완함. bind/close 동시 오류의 3개 subcase가 초안에서 실패하는 것을 확인한 뒤 수정함. 전체 포트 시험 파일을 `python -B -X warn_default_encoding -W error::EncodingWarning -m unittest discover -s tests -p test_ees_deploy_port.py -v`로 실행해 23 PASS·0 SKIP. 이 중 Linux 실제 모의 자식의 시작→health→정상 종료→같은 포트 재시작 1개를 포함하며 Windows 실환경·전체 Upgrade 통합은 아님. 운영 코드의 나머지 AST 불변·기준 Git blob 일치·`git diff --check`를 확인함. 사내 실행·main 병합·전체 문서 검사는 완료하지 않았으며 앞선 45개 선택 시험을 이번 결과로 재합산하지 않음. 상세 결과와 남은 범위는 같은 PR에 남김.

2026-09-18: 포트 검사 원본·기존 시험·이 STATUS의 Git blob을 대조한 부분 checkout에서 일시적 `10048` 주입 시 기존 171행 실패를 재현함. 수정 후 신규 포트 시험 20 PASS, 기존 시험 파일의 `ProcessContracts`·`WindowsIdentityContracts`·`StopFailureContracts`·`ExplicitTerminationContracts` 45 PASS. Python 3.13.5/Linux에서 `-X warn_default_encoding -W error::EncodingWarning`으로 실행함. 45개는 관련 클래스 AST를 선택 로딩했으며 무관한 builder import·나머지 시험은 실행하지 않음. 실제 Windows/Winsock·전체 운영 통합·문서 검사·사내 적용은 미실행. shell Git은 GitHub DNS 조회 실패였고 connector 파일 조회·게시와 구분함. 영구 평가 기록/가이드/CHANGELOG 통합은 위 다음 작업에 남기며 기존 과거 증거를 삭제하거나 재판정하지 않음.

2026-09-17: P/T/J 표시·첫 쓰기·현재 선택 조회·대화 액션·초안 보호·ees.10/v0.2.11 전달 경로의 로컬 검사·독립 검토를 마침. 관련 검사는 398 PASS·12 SKIP이며 별도 Native 브라우저 클래스는 실행 0개·1 SKIP임. 최초 실패·수정과 명령별 결과는 [이번 평가 기록](../evals/scenarios.md#work-panel-chat-implementation-20260917)에 보존함. 실제 wheel·Windows/PowerShell·Native 브라우저·사내 모델 검증과 새 설치는 미실행이며 아래 09-16 검사를 새 코드 결과로 재사용하지 않음.

2026-09-16: 최신 main·PR #52의 지침/원본을 재확인하고 같은 ees.9의 다른 source_commit 갱신·묶음 검증·Stop→Backup→Apply→Start·자동 자산 확인·직전 프로그램 Restore 범위를 코드로 대조함. 고정 원본 적용/묶음 로컬 검사는 30 PASS·1 SKIP(PowerShell 부재). 앞선 패널 77 PASS·3 SKIP과 새 실제 브라우저/Windows/사내 모델 미실행을 구분하며 원격 검사는 사용자 한시 방침대로 생략함. 사건별 결과와 최초 실패는 [기존 평가 기록](../evals/scenarios.md#workspace-native-design-20260915)에 보존함.

상태가 바뀔 때만 이 문서를 갱신하고 다음 작업 하나·현재 미해결·최근 점검 요약을 유지합니다. 날짜별 증거와 과거 적용 원본은 기존 evals에 기록합니다.
