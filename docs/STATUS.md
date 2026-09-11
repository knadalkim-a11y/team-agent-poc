# 현재 작업 상태

갱신일: 2026-09-11

현재 작업·다음 작업·미해결·실제 적용 원본을 관리합니다. 이슈·검증 근거는 [평가 기록 찾아보기](../evals/scenarios.md#evidence-index), 환경은 [versions](../versions.md), 완료된 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 현재 작업과 다음 작업

- 이번 작업: v0.2.6에서 대표 제안 세 개 중 독립 설비 조회를 WO 흐름에 묶고 Jira·GitHub·Confluence 업무 현황 질문을 추가함. 실제 읽기 범위·이전 관리/수동 질문 갱신·사내 안내를 대조함. [변경·검증](../evals/scenarios.md#connector-demo-starters). 문서·브랜치 정리 완료와 [과거 근거](../evals/scenarios.md#repository-maintenance-20260911)는 유지함.
- 최근 제품 변경: 옛 제안이 계속 표시되던 `suggestionPrompts`/`suggestion_prompts` 불일치를 v0.2.5에서 수정함. [PR #33](https://github.com/knadalkim-a11y/team-agent-poc/pull/33) main 병합과 [CI 성공](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34549891999)을 확인함. **사내 수정본 적용·새 화면은 아직 미확인**이며 이전 v0.2.4 적용 안내 후의 화면 실패를 지우지 않음.
- 다음 제품 작업 하나: [기존 ApplyDemo 절차](03-openwebui-native-agent.md#first-use-entry)로 main CI 성공 후 v0.2.6을 한 번 갱신하고 새 EES 대화의 제안 세 개와 업무 현황 조회를 확인함. 실제 결과를 받기 전 완료 처리하지 않으며 서버 재시작·수동 제안 삭제를 선행하지 않음.

## 마지막으로 확인된 적용 상태

사용자 보고 시점의 확인이며 실시간 서버 점검 결과가 아닙니다. Git 게시·CI 성공·안내한 SHA를 실제 사내 등록 바이트와 혼동하지 않습니다.

| 대상 | 마지막 확인과 적용 원본 | 남은 한계·근거 |
|---|---|---|
| EES Portal 프로그램 | 2026-09-10 `c099e427f62b` 복구·적용·기동 성공, 대화 폭 확대·분석 패널 조절 시 파란 테두리 제거 모두 정상 보고 | 장기 안정성·최초 접속 소실 원인은 미확정. [복구·화면 확인](../evals/scenarios.md#ees-stop-recovery) |
| 운영 래퍼 | 2026-09-11 `Update result=ok wrapper_changed=true wrapper=62a112c78a78` 보고. 프로그램 교체 없음 | 종료 처리·진단 보존 수정 적용 완료. `next=upgrade`만으로 추가 Upgrade를 요구하지 않음. [근거](../evals/scenarios.md#ees-update-failure-causes) |
| 분석·업무 패널 자산 | v0.2.1 안내 원본 `bc8bffbb6043fb1401f995b312bf5709f50e5983` 이후 계획·오른쪽 패널 표시 정상 보고 | 실제 사내 SHA·개별 수치/회신 정확성 직접 대조 미실행. [확인 범위](../evals/scenarios.md#plan-work-panel-accepted) |
| 대표 시작 질문 | Git v0.2.5, PR #33/main `5c6926b943e6c7a0d7785403d19f604686724c65` 및 CI 성공 | 패치 후 옛 질문 표시 보고가 마지막 화면 증거. 수정본 적용 SHA·화면 미확인. [원인·실제 UI 계약 검사](../evals/scenarios.md#starter-ui-field-fix) |
| WO 목업 | v0.1.6 안내 원본 `ba396da8d1d0abcb4e17494e8d9b37c5add514fc` 뒤 크기 조절 정상 보고; Git은 v0.1.8 통합 패널 원본 | 실제 EMS 미연결. 이후 패널 적용 보고와 개별 등록 바이트 검증을 구분. [목업 이력](../evals/scenarios.md#wo-mockup) |
| 기본 Assistant·기존 조회 | 이름·로고·기존 대화·평소 Confluence/Jira/GitHub 조회 정상, 초기 Rich UI 제거·변경 Prompt 반영 완료 보고 | Tool별 최신 등록 코드·SHA·새 일반 답변/원문 직접 대조 미실행. [반영 보고](../evals/scenarios.md#plain-output-applied-report), [이전 자산별 SHA](../evals/scenarios.md#status-history-20260911) |
| 정책·Skill | 합성 정책·지침 저장 보고, P02 PASS·P03 일부 확인. Git/UI 등록 Skill 3개, 기존 2개의 사용 확인 | 실제 사내 정책·나머지 P 시험·confluence-read 실제 로딩 미확인. [기준](../evals/scenarios.md#instruction-revision) |

## 남아 있는 이슈와 확인 범위

- **과거 업데이트 장애 조사:** 종료 처리·오류 보존의 재현 가능한 결함은 수정/적용했으나 최초 포트 소실과 Windows rename 접근 거부의 근본 원인은 미확정. 마지막 종료 실패 로그의 `KeyboardInterrupt/other/ValueError/OperationalError`만으로 DB 손상·잠금·취소 원인을 확정하지 않음. 약속한 추가 확인은 끝났으며 정상 서버 재현·반복 진단 없이 유지함. 자연 재발 시 개선된 래퍼의 실패 요약을 사용함. [조치와 조사 종결](../evals/scenarios.md#ees-update-failure-causes).
- **접속·스트리밍:** 기존 기동 재시작 뒤 health 성공, CORS 안내 뒤 실시간 답변 복구 보고는 유효함. 수락 오류 재발 방지·재부팅 뒤 설정 유지·장기 안정성은 미확인. 선택 Windows 실행 파일은 미적용이며 현행 래퍼 기동을 임의 교체하지 않음. [접속](../evals/scenarios.md#windows-existing-restart), [스트리밍](../evals/scenarios.md#chat-live-update-observation).
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
| 4. 관리자 워크플로 | 분석 계획·실제 진행·통합 업무 패널 구현/정상 보고 | 가독성 피드백, 반증·EMS 단독·분석 정확성 |
| 5. 레거시 연동 | 실제 업무 API·DB 미연결 | 승인된 API/Query Broker의 작은 읽기 기능 하나 |
| 6. 레거시 간접 UI | 같은 폼에서 직접 입력·AI 작성/수정의 WO 합성 시연 | 시연 피드백 → 운영 목업 → 실제 EMS 연결 |

사용자 결정으로 WO와 시스템 간 분석 시연을 먼저 진행했습니다. 준비된 화면을 상황에 맞게 활용하고 SHOP → LINE → PROCESS 검색 계층을 유지합니다. 공통 정책의 미완료 상태를 지우지 않으며 전체 시스템·권한 세분화·대형 오케스트레이션 기반을 시연의 선행조건으로 늘리지 않습니다. 첫 파일럿은 범용 채팅과 세 문서 시스템 읽기를 바탕으로 실제 업무 완료·결과/오류/공유 이해를 확인합니다. 기능 하나의 구현·관련 검사·짧은 사내 확인을 묶고 영향 없는 인증/저장 시험은 반복하지 않습니다.

<a id="resume-branch"></a>

## 재개와 환경 유지

- 다음 세션은 그때의 원격 최신 main·관련 열린 PR·로컬 변경을 확인하고 AGENTS와 이 문서를 읽습니다. 과거 적용 SHA를 개발 head로 고정하지 않습니다. 이번 관련 문서는 [첫 화면](03-openwebui-native-agent.md#first-use-entry)·[연동 시연](../evals/scenarios.md#connector-demo-starters)·[필드 오류 근거](../evals/scenarios.md#starter-ui-field-fix)이며 필요할 때만 해당 코드/시험을 읽습니다.
- 브랜치 정리 완료: 사용자 `branch_cleanup=ok, deleted=32` 보고와 원격 조회로 대상 32개 삭제를 확인함. 정리 당시 남은 브랜치는 `main`과 미병합 커밋 3개가 있는 `fix/upgrade-apply-failure`였으며, 미병합 head `b088f3be029dae108d82d6feec003fbd55bf5245` 보존을 확인함. [고정 대상·완료 근거](../evals/scenarios.md#repository-maintenance-20260911).
- 사내 결과 전달은 직접 타이핑 1~2줄만 가능함. 전체 로그·파일·사진을 요구하지 않으며 복사 블록은 각각 2,500자 이내. 기존 clone·Git 프록시 설정 완료 보고를 재사용하고 허용된 외부 호스트·기존 캐시만 전제함. 웹 프로젝트 지침의 저장소 참조 문구도 이미 설정한 것으로 유지함.
- 등록된 `manage-ees.ps1`의 Python·작업 위치·주소·DATA_DIR·DB·키·계정을 유지함. 설치 예제의 loopback·기본 폴더로 현재 등록값을 덮지 않음. [등록 설정과 기록 위치](03-openwebui-native-agent.md#ees-local-state). 중단한 후보 환경 Diagnose/Deploy는 재개하지 않으며 과거 도구·실패·복구 증거는 보존함.
- GLM 5.2 기준의 작은 Tool·짧은 절차·일반 JSON을 유지하고 모델 교체 때 대표 업무·실패/금지 요청을 비교함. 화면·답변에 이모지를 쓰지 않음. 기존 Hermes·팀원 작성물은 보존하며 서비스화·서버 이전·별도 Router/A2A/자동 동기화·공통 UI 프레임워크는 실제 필요에 따라 후속으로 다룸. [공통 자산 관리 경계](../README.md#원본과-배포본).

## 최근 점검

2026-09-11: 최신 main `0913d506ed595af71594adb5177ec1fdb36e3353`와 같은 tree에서 시작하고 열린 PR 0개를 확인했습니다. v0.2.6 문구를 기존 세 연동의 읽기 범위와 대조하고 제안 적용·실제 frontend 필드 계약·이전 질문 보존 관련67개와 문서/diff 점검을 통과했습니다. 사내 수정본 화면과 실제 연동 시연은 아직 미확인입니다. [검사 결과·범위](../evals/scenarios.md#connector-demo-starters).

상태가 바뀔 때만 이 문서를 갱신하고 다음 작업 하나·현재 미해결·최근 점검 요약을 유지합니다. 날짜별 증거와 과거 적용 원본은 기존 evals에 기록합니다.
