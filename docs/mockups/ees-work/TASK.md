# EES Work 기존 WebUI 통합 작업 지시

역할: EES Work 업무 탐색·실제 AI 대화·작업 패널 통합 담당자

저장소: knadalkim-a11y/team-agent-poc

입력: 최신 화면 참고자료는 [승인한 사이드바 개선 목업](ees-sidebar-refinement.html)이며, 이전 [공장별 업무 트리 목업](ees-factory-workspace.html)과 [최초 세부 편집 예시](ees-demo-workspace.html)는 보존한다. 목업 이후 확정한 [공장·시스템 공동 작업 목표](#ees-work-shared-target)는 아래 기록을 우선한다. ZIP 첨부 없이 저장소에서 읽는다. 목업은 대화 내 표시용 HTML fragment이며 실제 제품은 기존 WebUI 컴포넌트·테마·AI 대화를 사용한다.

<a id="sidebar-refinement"></a>

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
