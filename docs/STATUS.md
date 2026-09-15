# 현재 작업 상태

갱신일: 2026-09-15

현재 작업·다음 작업·미해결·실제 적용 원본을 관리합니다. 이슈·검증 근거는 [평가 기록 찾아보기](../evals/scenarios.md#evidence-index), 환경은 [versions](../versions.md), 완료된 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 현재 작업과 다음 작업

- 이번 작업: 승인한 사이드바 ees.8의 구현·검증·main 병합·프로그램 배포 준비를 마쳤고, 09-15 사용자 보고로 `9a90e19fb7f5`의 v0.2.9 ApplyDemo 1건 갱신 성공을 확인함. 새 화면 확인은 별도로 남아 있음. [승인 기준](mockups/ees-work/TASK.md#sidebar-refinement), [검증·사내 결과](../evals/scenarios.md#sidebar-refinement-20260914).
- 최근 Git 반영: [PR #47](https://github.com/knadalkim-a11y/team-agent-poc/pull/47)을 `02b880b19db6ffb353daf3309e3ff1354730e815`로 병합하고 [병합 main CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34910676906)의 Linux·Windows·ees.8 프로그램 산출물 성공을 확인함. 사내 가이드 원본 `9a90e19fb7f5f7d967d47c1f811d648b4dc1ee52`의 [main CI](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34910881151)도 전체 성공했으며 이번 사용자 ApplyDemo 보고의 원본과 같음. 이후 상태 기록은 문서만 갱신하며 검사 결과는 [최신 main 실행](https://github.com/knadalkim-a11y/team-agent-poc/actions/workflows/ees-delivery.yml?query=branch%3Amain)에서 확인함. 최초 실패·수정·원격 검증과 실제 사내 결과는 [같은 기록](../evals/scenarios.md#sidebar-refinement-20260914)에서 구분함.
- 최근 UI 확인: 사용자가 P/T/J 설명 행·하위 전체 펼침·새 영역 글꼴 차이·공장/시스템 선택 디자인을 지적하고 개선 목업을 승인함. 실제 새 프로그램 UI의 사내 확인은 아직 미실행임.
- 최근 운영 확인: 09-14 읽기 진단의 `/api/version` 응답으로 **당시 실행 프로그램 `0.11.3+ees.7`**을 확인함. 프로그램의 정확한 원본 커밋·새 UI 표시·유휴 안정성은 미확인임. 그 전 `dba0677ffe3e` Upgrade의 promote 접근 거부와 `83d56a186382` Restore·Start·기존 주소 접속 성공은 [당시 복구 기록](../evals/scenarios.md#ees7-apply-recovery-20260914)으로 보존함. [최신 진단](../evals/scenarios.md#specialists-editor-format-20260914), [수신 보호 근거](../evals/scenarios.md#accept64-guard-20260914).
- 최근 제품 변경: 09-15 `9a90e19fb7f5` ApplyDemo로 v0.2.9 관리 자산 적용과 1건 갱신 성공을 확인함. 이전 `76e566622e74`의 v0.2.8·8건 적용은 [정렬 충돌 수정 이력](../evals/scenarios.md#specialists-editor-format-20260914)에 보존함. 새 질문·새 UI·실제 모델 호출은 이번 자산 성공만으로 확인하지 않음.
- 다음 작업 하나: 브라우저 새로고침 뒤 [선택 영역·직계 펼침·글꼴·대화/초안의 최소 확인](03-openwebui-native-agent.md#sidebar-refinement)을 하고 짧은 결과를 반영함. 이미 성공한 ApplyDemo를 반복하지 않으며 이번 UI 변경에서 공유 권한·저장 구조를 변경하지 않음.
- 최신 사내 확인: 09-15 사용자 `apply_demo result=ok changed=1 commit=9a90e19fb7f5 stage=complete code=- next=new_chat` 보고. v0.2.9 자산 적용·쓰기 후 확인 성공이며 프로그램 Upgrade의 출력·현재 실행 버전/원본·새 UI·실제 모델 호출·유휴 안정성은 별도 미확인임. 앞서 안내한 블록의 중단 조건만으로 개별 Upgrade 출력을 추정하지 않음. [이번 적용 근거](../evals/scenarios.md#sidebar-refinement-20260914).

## 마지막으로 확인된 적용 상태

사용자 보고 시점의 확인이며 실시간 서버 점검 결과가 아닙니다. Git 게시·CI 성공·안내한 SHA를 실제 사내 등록 바이트와 혼동하지 않습니다.

| 대상 | 마지막 확인과 적용 원본 | 남은 한계·근거 |
|---|---|---|
| EES Work 업무 UI | ees.7 / v0.2.8 공장별 인라인 트리·이력·기존 UI 글꼴·탭 안정화·명칭 변경 구현 및 로컬 검증 완료 | 사용자가 이전 업무 절차의 존재와 글꼴·깜빡임을 보고함. ees.7 실행과 `76e566622e74` 자산 적용은 확인했으나 프로그램의 정확한 SHA·새 화면·실제 모델 호출은 미확인. [현재 검증](../evals/scenarios.md#ees-work-factory-ux-20260914), [이전 통합](../evals/scenarios.md#ees-work-native-integration-20260914) |
| EES 프로그램 | 09-14 읽기 진단의 `/api/version` 응답 `0.11.3+ees.7` | 실행 버전 확인. 정확한 프로그램 원본 커밋·새 화면·유휴 안정성은 미확인. [최신 증거](../evals/scenarios.md#specialists-editor-format-20260914). 이전 `83d56a186382` 복구·접속 성공은 [당시 기록](../evals/scenarios.md#ees7-apply-recovery-20260914)에 보존 |
| 운영 래퍼 | 09-15 ApplyDemo 실행 원본 `9a90e19fb7f5`, `result=ok changed=1 stage=complete` | 실행 프로그램 원본 SHA와 구분함. [이번 적용 보고](../evals/scenarios.md#sidebar-refinement-20260914) |
| 분석·업무 패널 자산 | 09-15 `9a90e19fb7f5` / Agent Pack v0.2.9 ApplyDemo 성공, 변경 1건 | 관리 목록의 적용·쓰기 후 확인을 마친 사용자 보고. 변경한 개별 대상은 요약에 없으며 새 UI·실제 분석 결과까지 확인한 것은 아님. [이번 보고](../evals/scenarios.md#sidebar-refinement-20260914), [이전 v0.2.8 성공과 실패](../evals/scenarios.md#specialists-editor-format-20260914) |
| 대표 시작 질문 | 09-15 `9a90e19fb7f5`의 v0.2.9 관리 목록을 포함한 ApplyDemo 성공 | 새 질문의 실제 화면은 미확인. 변경 1건을 시작 질문 갱신으로 단정하지 않음. [이번 적용](../evals/scenarios.md#sidebar-refinement-20260914), [이전 접속 실패](../evals/scenarios.md#connector-demo-starters) |
| WO 목업 | v0.1.6 안내 원본 `ba396da8d1d0abcb4e17494e8d9b37c5add514fc` 뒤 크기 조절 정상 보고; Git은 v0.1.8 통합 패널 원본 | 실제 EMS 미연결. 이후 패널 적용 보고와 개별 등록 바이트 검증을 구분. [목업 이력](../evals/scenarios.md#wo-mockup) |
| 기본 Assistant·기존 조회 | 이름·로고·기존 대화·평소 Confluence/Jira/GitHub 조회 정상, 초기 Rich UI 제거·변경 Prompt 반영 완료 보고 | Tool별 최신 등록 코드·SHA·새 일반 답변/원문 직접 대조 미실행. [반영 보고](../evals/scenarios.md#plain-output-applied-report), [이전 자산별 SHA](../evals/scenarios.md#status-history-20260911) |
| 정책·Skill | 합성 정책·지침 저장 보고, P02 PASS·P03 일부 확인. Git/UI 등록 Skill 3개, 기존 2개의 사용 확인 | 실제 사내 정책·나머지 P 시험·confluence-read 실제 로딩 미확인. [기준](../evals/scenarios.md#instruction-revision) |

## 남아 있는 이슈와 확인 범위

- **사외 Windows CI 지연:** 이전에 통과한 동일 코드에서 PowerShell 20초·Node 10초 제한시간 초과가 각각 발생했으며 원인은 미확정임. 두 시험의 단계 표식·런타임 버전·timeout의 단계 표식를 보존하도록 보완했으므로 자연 재발 시 그 증거로 진입 관측 여부와 시험 내부 단계를 구분함. 재검사 성공을 근본원인 해결이나 사내 서버 진단 필요로 바꾸지 않음. [실패·관측·최종 CI](../evals/scenarios.md#sidebar-refinement-20260914).
- **팀 공동 작업:** 최종 목표와 현재 구현의 차이가 남아 있음. 현재 사용자별 구현과 ees.8 후보의 진행 건·대화 연결은 사용자 소유이고, 공장·시스템 선택만으로 여러 사용자의 같은 진행 건 공유가 구현된 것은 아님. [합의·미결정·검증할 범위](mockups/ees-work/TASK.md#ees-work-shared-target).
- **공장별 업무 UX:** Workspace 탭 반복 재삽입은 사외 실제 프런트에서 재현하고 동일 탭 유지·글꼴 상속 검사를 통과함. Native 첫 메시지의 경로 전환과 초안 복원 경합을 보완하고 브라우저 검사를 완료함. 사내 ees.7 실행과 최신 관리 자산 적용은 확인했으나 새 글꼴·깜빡임 해소의 실제 화면은 미확인임. [UI 검증](../evals/scenarios.md#ees-work-factory-ux-20260914), [자산 적용 확인](../evals/scenarios.md#specialists-editor-format-20260914).
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
| 4. 관리자 워크플로 | ees.7 공장별 트리·개인 진행 건 보존·Native 대화·관리자 편집 구현, 사내 새 화면 미확인 | [공장·시스템의 공동 작업 목표](mockups/ees-work/TASK.md#ees-work-shared-target)를 다음 설계로 구체화. 기존 분석 정확성 미확인 유지 |
| 5. 레거시 연동 | 실제 업무 API·DB 미연결 | 승인된 API/Query Broker의 작은 읽기 기능 하나 |
| 6. 레거시 간접 UI | 같은 폼에서 직접 입력·AI 작성/수정의 WO 합성 시연 | 시연 피드백 → 운영 목업 → 실제 EMS 연결 |

사용자 결정으로 WO와 시스템 간 분석 시연을 먼저 진행했습니다. 준비된 화면을 상황에 맞게 활용하고 SHOP → LINE → PROCESS 검색 계층을 유지합니다. 공통 정책의 미완료 상태를 지우지 않으며 전체 시스템·권한 세분화·대형 오케스트레이션 기반을 시연의 선행조건으로 늘리지 않습니다. 첫 파일럿은 범용 채팅과 세 문서 시스템 읽기를 바탕으로 실제 업무 완료·결과/오류/공유 이해를 확인합니다. 기능 하나의 구현·관련 검사·짧은 사내 확인을 묶고 영향 없는 인증/저장 시험은 반복하지 않습니다.

<a id="resume-branch"></a>

## 재개와 환경 유지

- 다음 세션은 그때의 원격 최신 main·관련 열린 PR·로컬 변경을 확인하고 AGENTS와 이 문서를 읽습니다. 과거 적용 SHA를 개발 head로 고정하지 않습니다. EES Work는 [최종 공동 작업 합의를 포함한 작업 지시](mockups/ees-work/TASK.md#ees-work-shared-target)와 그 문서가 연결한 목업을 읽습니다. HTML은 이전 화면 참고이며 공동 작업·권한 설계는 최신 문구가 우선합니다. 새 ZIP이나 이전 대화 전체가 없어도 이 경로에서 이어갑니다. 별도 인계 파일은 만들지 않습니다. 수락 보호는 [적용 가이드](03-openwebui-native-agent.md#ees-accept64-guard)·[장애·검증 근거](../evals/scenarios.md#accept64-guard-20260914)를 보존하며 관련 변경이 있을 때만 해당 코드/시험을 읽습니다.
- 브랜치 정리 완료: 사용자 `branch_cleanup=ok, deleted=32` 보고와 원격 조회로 대상 32개 삭제를 확인함. 정리 당시 남은 브랜치는 `main`과 미병합 커밋 3개가 있는 `fix/upgrade-apply-failure`였으며, 미병합 head `b088f3be029dae108d82d6feec003fbd55bf5245` 보존을 확인함. [고정 대상·완료 근거](../evals/scenarios.md#repository-maintenance-20260911).
- 사내 결과 전달은 직접 타이핑 1~2줄만 가능함. 전체 로그·파일·사진을 요구하지 않으며 복사 블록은 각각 2,500자 이내. 기존 clone·Git 프록시 설정 완료 보고를 재사용하고 허용된 외부 호스트·기존 캐시만 전제함. 웹 프로젝트 지침의 저장소 참조 문구도 이미 설정한 것으로 유지함.
- 등록된 `manage-ees.ps1`의 Python·작업 위치·주소·DATA_DIR·DB·키·계정을 유지함. 설치 예제의 loopback·기본 폴더로 현재 등록값을 덮지 않음. [등록 설정과 기록 위치](03-openwebui-native-agent.md#ees-local-state). 중단한 후보 환경 Diagnose/Deploy는 재개하지 않으며 과거 도구·실패·복구 증거는 보존함.
- GLM 5.2 기준의 작은 Tool·짧은 절차·일반 JSON을 유지하고 모델 교체 때 대표 업무·실패/금지 요청을 비교함. 화면·답변에 이모지를 쓰지 않음. 기존 Hermes·팀원 작성물은 보존하며 서비스화·서버 이전·별도 Router/A2A/자동 동기화·공통 UI 프레임워크는 실제 필요에 따라 후속으로 다룸. [공통 자산 관리 경계](../README.md#원본과-배포본).

## 최근 점검

2026-09-15: 사용자 ApplyDemo 성공 요약을 원본 `9a90e19fb7f5`의 v0.2.9와 대조해 자산 1건 갱신·완료로 기록함. 프로그램 Upgrade·실행 버전·새 UI 확인은 해당 출력이 없어 미확인으로 유지하고 이미 성공한 적용을 반복하지 않음. 병합본과 가이드 원본 main의 Linux·Windows 검사·프로그램 준비 성공, 과거 실패와 수정은 [기존 평가 기록](../evals/scenarios.md#sidebar-refinement-20260914)에 연결함. 이번 변경은 상태·평가·관련 안내 문서에 한정함.

상태가 바뀔 때만 이 문서를 갱신하고 다음 작업 하나·현재 미해결·최근 점검 요약을 유지합니다. 날짜별 증거와 과거 적용 원본은 기존 evals에 기록합니다.
