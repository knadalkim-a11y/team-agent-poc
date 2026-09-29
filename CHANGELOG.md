# Changelog

완료된 변경·중요 결정과 날짜별 관찰을 기록합니다. 다음 작업과 최신 배포 상태는 [STATUS](docs/STATUS.md), 시험별 현재 판정은 [평가표](evals/scenarios.md)가 원본입니다. 과거 실패 기록을 현재 장애나 재실행 지시로 해석하지 않습니다.

## 2026-09-29

- PR #66의 C안 3단계 통합 검수에서 legacy 검토 자료·과거 이력도 조회 실패 뒤 본문과 열린 보조 창에서 숨기도록 보완함. 미저장 글과 저장 기록은 보존하고 현재/과거 건은 각각 성공한 조회로만 다시 표시함. 실제 두 탭 충돌·늦은 이력 응답과 Native 전체 앱 검수를 추가했으며 [최종 판정·실패/재검·미실행](evals/scenarios.md#c-design-phase3-20260929)을 분리함. Draft 유지, 병합/배포 없음.

- PR #66의 과거 Native 실행에 저장 당시 대상/정의와 읽기 전용 맥락을 연결하고, 같은 진행 건의 활성 Native 실행 중 legacy 초안 반영 버튼/제출을 기존 서버 조건에 맞춤. 작성 글과 기록은 보존하며 [실패·제품 경로 재검](evals/scenarios.md#c-design-phase2-review-20260929)을 구분함.
- [C안 2단계](docs/mockups/ees-work/TASK.md#c-design-phase2-20260929)를 같은 Draft PR #66에서 기존 모든 J 유형·P/T·예외로 확대함. Native 결과/현재 입력/단일 행동/보조 상세를 공통 화면에 연결하고 실제 완료 판정·공개 schema·기존 입력/실행 계약과 완료 복귀를 보존함.
- 상위 범위 완료 오표시와 계획 버튼 소실, UNKNOWN·혼합 범위·활성 Native 중 legacy 쓰기의 불가능한 행동, 조회 실패/권한 회수 뒤 과거 상세 잔류·재조회 복구를 보완함. AI 관찰값에 근거 작업·항목·값·한계를 함께 표시하며 업무 이름별 전용 분기를 만들지 않음.
- [유형별 판정·실패/동일 조건 재검](evals/scenarios.md#c-design-phase2-20260929), 실제 패키지 브라우저/공식 전체 앱과 합성 HTTP·모델/사내 미실행 경계를 기록함. 3단계 통합 회귀·최종 수락·병합/배포는 별도 지시로 남김.

## 2026-09-28

- PR #66의 완료 영역 복귀를 기존 `panel_back`과 연결해 inline/dock 모두 T 목록 상태·스크롤·행 초점과 P 상위 이동을 보존함. 직접 진입의 잘못된 이력, T 닫기/재열기 위치 소실과 필터에서 사라진 행의 화면 밖 초점을 수정하고 [실패·동일 조건 재검](evals/scenarios.md#c-design-completed-return-20260928)을 기록함.

- 최신 main의 #65 병합과 해당 PR 배포 준비 상태를 확인해 STATUS의 병합 대기 표현을 바로잡음. 실제 사내 적용 보고와 분리하고 기존 Windows 작업·A안/TR 검증 근거를 보존함.
- [C안 1단계](docs/mockups/ees-work/TASK.md#c-design-phase1-20260928)의 공통 외형·대표 AP 모의 흐름 범위와 후속 2·3단계를 구분함. Figma 9개 상태/역할 실조회와 제품 수락을 분리해 [검증 원본](evals/scenarios.md#c-design-phase1-20260928)에 기록함. view/CSS의 제목·상태·결과 우선순위와 입력/실행 영역을 정돈하고 기존 실행/저장 계약을 유지함. 실제 판정·중간 실패/수정·후속 단계는 같은 기록에서 구분함.

## 2026-09-25

- PR #65 병합 전 검토에서 UNKNOWN의 일시정지/취소 우회, 전이 근거의 현재 ACL, 대화 간 실행 변경, 관리자 승인 권한 회수 경합을 재현·차단함. 접수 상태·차단 사유·실제 호출 구분·화면 갱신과 작성 입력 연결도 보완함. Native 모델의 추가 문맥 설정을 제한해 선언한 근거 범위를 유지하고, 기존 적용/복원 경로를 사용한 정확한 병합 원본 배포 준비를 연결함. [검토·재검과 실제 배포 구분](evals/scenarios.md#shared-native-runtime-review-20260925).
- 기존 Native 등록본의 ID·코드·schema·ACL·개인 설정을 재사용하는 공통 실행 bridge를 구현함. 저장 metadata로 기능을 검토/승인하고 현재 버전·권한을 호출 직전 다시 확인하며 Confluence/Jira/GitHub 여섯 읽기 함수를 연결함. 별도 인증·공용 PAT·범용 실행기·도구 복제는 추가하지 않음.
- P/T/J의 계획·공개 입력/결과 연결·업무/최종 validator·영속 run/call/event와 앱 worker를 연결함. 채팅과 기존 A안 패널이 같은 서비스를 사용하며 브라우저 종료·재기동·중복·중단/재개·UNKNOWN/늦은 결과를 구분함. 두 예제와 제한된 AI 근거 정리, 기존 J 편집기의 함수/승인 UI를 추가함.
- ees.12/Pack0.2.14/Specialists0.2.5/Workflow0.4.0으로 구분하고 과거 프로그램의 필수 파일/Restore 계약을 보존함. 새 실행 자료를 구프로그램이 모의 완료로 덮는 경계를 차단함. [TR-01~24의 실제 Native·합성 전송·브라우저·복원·실패/재검](evals/scenarios.md#shared-native-runtime-20260925)을 구분해 기록함. Windows 셋업과 사내 실행은 수행하지 않음.

## 2026-09-24

- PR #64 병합 전 리뷰에서 Restore 중 구프로그램이 변경/삭제한 P의 게시 기준을 다시 맞출 수 없던 경계와 최종 인가 중 Native 자산이 바뀌는 경합을 보완함. 관리자의 명시적 기준 재확인은 기존 초안을 보존하고 재검/게시를 별도로 요구하며, 쓰기 직전 자산 접근·버전·본문을 재조회함. [최초 재현·재검·배포 구분](evals/scenarios.md#system-authoring-20260924)을 기록하고 기존 고정 main SHA 적용 가이드를 연결함.
- [시스템 담당 작성권한 v1.1](docs/mockups/ees-work/TASK.md#system-authoring-20260924)을 구현함. Native 개인 user·현재 그룹을 재사용해 시스템별 인가와 선택 P의 초안 저장·검사·원자적 게시를 연결하고, Workspace 관리 권한 0인 담당자는 기존 셸의 **업무 절차**로 진입함. 소유권/충돌·권한 회수·늦은 응답을 보호하며 기존 A안·진행 snapshot·자산/인증을 보존함.
- 기존 전체 초안을 먼저 보존하고 구형 전체 쓰기를 차단함. 새 프로그램 ees.11과 ees.9/10 복원 목록을 구분하고 실제 ees.10→11 프로그램 Apply/Restore·fallback 중 작성 자료의 재업그레이드를 검증함. Pack0.2.13/Specialists0.2.4는 ees.11 allowlist 호환 변경임.
- Native 가입·승인·그룹 지정·일반 이용·P 게시·다른 사용자 이용·회수 및 계정 전환을 합성 데이터로 검사함. Redis 없는 Native 구성의 기존 JWT 유지 한계, 초기 실패/수정/재검과 OP 사내 미확인을 [평가 원본](evals/scenarios.md#system-authoring-20260924)에 구분함. 초기 구현에서는 실제 계정 변경·main 병합·사내 배포를 수행하지 않았으며, 후속 사용자가 PR #64 병합과 기존 사내 배포 안내를 요청함. 실제 사내 적용은 별도 확인함.

## 2026-09-23

- #61/#62가 병합된 main에서 [A안 상태·실행 상세](docs/mockups/ees-work/TASK.md#a-design-20260923)를 기존 view/CSS에 반영함. 연속 작업면·제목/집계·입력/결과 위계와 읽기 전용 dialog의 크기/독립 스크롤을 정돈하고 Native 가용 폭에 따른 패널 기본 폭과 사용자가 조절한 폭을 함께 보존함. 기존 로고·로컬 폰트·Native/Workspace·업무/저장/권한 계약과 사용자 자산은 유지함.
- 실행 요청 중 결과 대기·중복 차단을 명확히 하고 저장된 빈 출력과 기록 없음의 표시를 구분함. 상세를 열고 갱신될 때 새 시도로 선택이 이동하던 경계와 원 진입 버튼이 재생성되면 초점을 잃던 경계를 보완함. 기존 시도/호출 선택과 같은 업무의 대체 진입 버튼으로 복귀하며 별도 화면/실행 경로를 추가하지 않음. [Figma 조회·제품 수락·실패와 미실행 범위](evals/scenarios.md#a-design-20260923)를 구분해 기록함.

## 2026-09-22 기준 후속 변경

- 왼쪽 #61 구현을 보존한 오른쪽 후속에서 추천/다음 작업 카드를 제거하고 P의 단계별 수행 내용·문제 분포, T의 조건/사유 펼침·선행 J 이동/목록 복귀, J의 읽기 전용 업무 범위·기존 입력과 결과를 연결함. 사용 구성과 실행 이력/호출별 입력·출력은 진행 건의 고정 정의·기존 모의 실행 기록을 읽으며 현재 폼/편집 초안으로 과거 기록을 채우지 않음. 업무 판정과 형식 확인을 구분하고 출력 형식 검사·개별 호출 버전·외부 원시 응답 등의 미기록을 명시함. 기존 서버/API/저장 계약·개인 인증·Workspace·사용자 자산은 변경하지 않음. 초기 GitHub/Figma metadata 오류는 당시 실패로 보존하며, 같은 날 재개 시 정상화된 조회로 지정 16개 오른쪽 Figma 노드의 context·screenshot을 확인함. 기존 상세 대화상자와 실제 저장 기록만 연결하는 의도된 목업 차이를 명시하고 시각 대조·원격 게시·사내 적용과 구현을 구분함. [오른쪽 기준](docs/mockups/ees-work/TASK.md#right-panel-20260922), [실제 검사·제한](evals/scenarios.md#right-panel-20260922), [사용과 기록 해석](docs/03-openwebui-native-agent.md#ees-right-panel-20260922).

- 사용자 병합·배포 안내 요청에 따라 왼쪽 PR #61을 main `cfe5e4d36ca902c8706aed4d07f0cd87ffa16a78`에 병합함. 오른쪽 최종 원본과 실제 사내 설치·기동·화면 보고는 구분함. 기존 Update → Upgrade -TrialCommit의 정확한 main 검증·자동 묶음 준비·ApplyDemo와 프로그램 전용 Restore 경계를 재확인하고, 후보 ZIP은 사전 패키징 검증용이며 사용자의 수동 다운로드는 불필요하다고 [적용 안내](docs/03-openwebui-native-agent.md#ees-wrapper-trial)에 명시함. 배포 실행 코드·캐시·인증 설정은 변경하지 않음.

- PR #60 병합 main `b1c47643c7a5`에서 첨부 확정안과 Figma `313:680/132/319/515`의 왼쪽 워크플로우 패널을 반영함. 분류·단계의 흰색 바탕, 분류 선택 밑줄, P 전체의 `#dcebf7`·T/J 행의 `#eef5fa` 선택, J 사이에만 얇은 구분선을 적용함. 이전 왼쪽의 진한 청색 선택·청회색 T 제목 기준을 대체하며 기존 단계별 UX·단일 선택·상태·입력/결과/이력은 유지함. CSS를 왼쪽 범위에 한정해 오른쪽·Workspace·실행 버튼·전역 토큰을 보존함. PR #60 적용 안내 뒤 사용자 확인은 이전 적용 확인으로 분리함. 최초 준비 당시 이번 변경의 병합·사내 설치는 포함하지 않았으며, 이후 #61 병합은 위 별도 요청으로 기록함. [확정 기준](docs/mockups/ees-work/TASK.md#sidebar-final-20260922), [새 Native 대조·회귀·미실행](evals/scenarios.md#sidebar-final-20260922).

- PR #59의 main `c4c6ab8d1df3` 병합·사용자 Upgrade/ApplyDemo·정상 수행 보고를 기록함. 이어 첨부 시각 계층 기준에 따라 P 이름/완료 수를 한 클릭 단위로 통합하고 T 펼침과 선택을 분리함. P/T/J 단일 강한 선택, J 양쪽 여백, 별도 hover/키보드 포커스·상태 배지 대비, 오른쪽 수치/결과·Workspace 편집 제목 우선순위를 보완함. 기존 단계별 UX·입력·실행·대화·권한·저장 계약을 유지함. 준비 당시 미병합이었으나 이후 별도 사용자 승인으로 PR #60을 `b1c47643c7a5`에 병합했으며 최신 왼쪽 표현은 위 확정안으로 대체함. [당시 실제 전후·회귀·실패 기록](evals/scenarios.md#visual-hierarchy-20260922).

- 같은 날 기존 `3ffad0ff9a00` 구현을 보존해 GitHub/Figma 플러그인 실물 대조를 완료함. 기존 view/CSS에서 공장·시스템 가로 배치, 선택 단계 번호/배경, J 제목·주 버튼, 결과·다음 행동 순서와 Workspace 보조문 줄바꿈을 보완함. Space 길게 누르기 회귀를 추가하고 새 검증 실패/재검증·전체 strict의 기존 EncodingWarning 한계를 [재개 평가](evals/scenarios.md#step-progress-resume-20260922)에 분리 기록함. 병합·사내 설치 승인은 포함하지 않음.

- Runtime의 재귀 탐색을 워크플로우 요약·단계별 진행표·선택 단계의 작은 작업 목록으로 바꿈. 내부 P/T/J와 Workspace 편집 구조는 유지하며 왼쪽은 작업명+상태만 표시하고 대량 전체 목록·P/T 관리·결과/이력 경로를 보존함. 입력 반영/별도 실행/다음 이동을 분리하고 연속 Enter·이중 클릭으로 새 실행 의도가 만들어지지 않도록 보완함.
- Work 화면의 회색 토큰 덮어쓰기를 제거하고 EES 색상·무테·선택 강조·가시 키보드 포커스를 적용함. 실제 Native 전역 포커스 규칙 충돌을 발견해 Work 영역에서 수정함. Native 준비 완료 뒤 선택기가 비활성으로 남는 갱신 누락과 다른 작업으로 이동할 때 본문 스크롤이 남는 문제를 재현해 보완함. 새 업무 규칙·권한·저장 형식·의존성은 추가하지 않음. Figma/GitHub 연결 실패와 이번 실제 Native 검증·미게시/미배포 경계는 [새 평가 기록](evals/scenarios.md#step-progress-ux-20260922)에 남김.
- PR #58 원본의 `checkout_changed` 보고·SHA 확인·Upgrade/ApplyDemo 재시도 성공을 기존 평가에 보존하고 STATUS의 오래된 미적용 표기를 사용자 보고에 맞춤. 이전 적용 성공과 이번 후속 변경의 구현/설치를 구분함.

## 2026-09-21

- PR #57 병합 이후 통합 Figma 기준의 첫 베타를 구현함. 워크플로우/단계/작업 용어, 실제 하위 작업 집계·문제 구분·대량 검색/필터/페이지, Workspace 구성·AI 안내 전후 비교·저장/게시 조건을 보완함. 기존 Native 도구/개인 설정을 새 탭에서 재사용하고 사용자 입력·접근 불가 참조·진행 snapshot·이력을 보존함. 외부 도구 미실행의 모의 결과 오표시와 접근 불가 Skill 안내를 수정함. 새 실행기·저장 형식·인증 저장소는 없음. [새 대조·검증과 미배포 경계](evals/scenarios.md#integrated-work-beta-20260921).


- 같은 PR #57에서 Workspace의 업무별 AI 작성 영역을 기존 인증·모델 API로 연결함. 질문/안내 수정·되돌리기·중단을 구분하고 수행 안내만 미저장 초안에 반영하며 지연 응답·업무 이동·직접 편집·계정 변경 시 새 입력과 기존 자산을 보존함. 근거/검토 자료/업무 기록/진행 요약·고급 설정·게시·revision 충돌을 기존 UI의 대화상자로 보완하고 Esc·Tab·초점 복귀를 실제 브라우저에서 검사함. 추가 프레임워크·서버·DB는 없음. [설계 대조·실패와 최종 검사](evals/scenarios.md#simplified-work-ux-implementation-20260921).
- 불완전한 시험 wheel이 관측되어 빌더가 닫힌 ZIP의 파일 목록·CRC를 확인한 뒤에만 wheel/manifest를 내보내도록 보완함. 잘린 ZIP의 배포물 공개 차단을 재현·회귀 검사했으며 관측된 파일 불완전성의 근본 원인을 재빌드 성공만으로 단정하지 않음.

- 사용자 요청으로 Work의 개발 검증 환경을 저장소 `.venv` 한 곳과 시험 브라우저 하나로 준비하고 기존 CI 의존성 목록을 재사용함. 공식 wheel 검사의 subprocess 인코딩 누락을 수정하고 Native 브라우저 시험에서 실제 근거·실패 후 이력 열람을 보강함. 새 제품 프레임워크·회사 PC 환경 변경은 없으며 [최초 실패와 환경 준비 후 검증](evals/scenarios.md#simplified-work-ux-implementation-20260921)을 보존함.

- Work에서 PR #57의 동작을 재현해 초안 검토 완료 표시, 완료된 하위 업무의 전체 진행 복귀, 사람 확인 버튼의 취소와 AI Tool의 대리 완료 거절을 보완함. Workspace는 입력 즉시 미저장 상태를 표시하고 재조회·업무 이동·자기 저장 응답 중 새 입력 및 접힌 연결을 보존함. 실제 조립한 Work 자산의 내용 해시로 같은 ees.10 버전의 캐시 URL을 구분함. 서비스/DB/권한 계약과 Pack `0.2.12`는 유지하며 [실제 로컬 검사·실패·미실행 경계](evals/scenarios.md#simplified-work-ux-implementation-20260921)를 기록함. 아래 초기 구현 당시 검사 한계와 구분함.
- Figma의 단순 UX 기준을 기존 Native EES Work view/designer/CSS에 제한적으로 구현함. Runtime에서 P/T/J 기술 badge를 숨기고 업무명·현재 상태·완료 조건·근거·읽기 전용 이력·다음 행동 하나를 우선하며, 사람 확인은 실제 확인 완료 액션으로만 기록하고 미연결 Tool은 `실행 연결 필요`로 표시함. 실패 부모는 `문제 확인` 하나만 제시하고 적용 제외는 현재 상태에 직접 표시함. Workspace는 업무 이름/목적/안내/완료 조건을 먼저 보여주고 기술 연결을 고급 설정으로 접되 초안 저장·게시와 기존 진행 건의 게시 snapshot 계약을 유지함. [구현·검증 경계](evals/scenarios.md#simplified-work-ux-implementation-20260921).
- 새 서버·프레임워크·저장 계층을 추가하지 않았고 launcher/server 계약과 사용자 대화·Skill·Tool·모델·권한·기존 이력은 변경하지 않음. 기존 관리 EES Prompt에는 선택 업무를 `목적 → 현재 상태 → 다음 행동`으로 설명하는 최소 지침만 추가하고 Agent Pack을 `0.2.12`로 갱신함. V8의 실제 렌더 함수 합성 검증은 수행했으나 checkout 기반 unittest/check_docs, 실제 브라우저/Windows/Open WebUI/사내 LLM은 미실행이며 원격 CI는 9월 생략 방침을 유지함. 초기 계획은 PR 검토 후 현재 개인 PC Dogfooding이었으며, 이번 Work 재개는 PR 갱신까지만 수행함.

## 2026-09-18

- ees.10 시험 Upgrade가 기존 서버 Stop 뒤 `port_check / port_bind / WinError 10048`에서 `changed=false`로 중단된 사건을 분석함. 당시 `port_is_free`의 단발 Windows bind가 일시적인 10048도 즉시 배포 실패로 확정하던 결함을 재현하고, Windows operational bind의 10048만 0.25초 간격·10초 예산·최대 40회 재확인하도록 보완함. 포트 공유·다른 프로세스 종료·자동 Restore는 추가하지 않고 지속 점유·다른 오류는 계속 실패시킴. 사용자는 Restore 없이 기존 Start 한 번으로 서비스를 정상 복구했다고 보고했으며 이를 새 프로그램 적용 성공이나 TIME_WAIT 원인 확정으로 해석하지 않음. [증거와 한계](evals/scenarios.md#windows-port-bind-10048-20260918).
- 독립 후속 검토에서 bind 실패 뒤 socket close도 실패할 때 close 오류를 retryable bind로 오인할 수 있는 초안 경계를 3개 subcase 실패로 확인하고 수정함. 최종 포트 시험 23 PASS·0 SKIP에 실제 Linux 모의 자식의 시작→health→종료→같은 포트 재시작과 합성 사용자 파일 보존을 포함함. 실제 Windows/Python 3.11/사내 Upgrade와 9월 원격 CI는 미실행으로 구분하며, 수정은 기존 PR #55에서 관리하고 최종 main 병합 SHA를 시험 적용 원본으로 사용함.

## 2026-09-17

- 후속 구현·배포 승인에 따라 [09-16 설계](docs/mockups/ees-work/TASK.md#work-panel-chat-design-20260916)의 P/T/J 패널을 ees.10에 반영함. P는 직속 T, T는 직속 J의 정렬된 현황을 표시하고 J는 입력·최근 유효한 결과·완료 기준·다음 조치를 우선함. 수행 근거는 접어서 열람하고 자산 연결 설정은 Workspace에서 관리하며 부모의 가능한 점검과 사람 확인의 경계를 유지함.
- 게시 절차 선택·질문은 읽기만 수행하고 최초 저장/실행에서 진행 건을 확보하도록 서비스·화면·Native Tool을 연결함. 확정한 범위·게시 버전·요청 식별자로 중복 실행과 다른 대상 쓰기를 막고, 기존/복수 진행 건 선택·부분 실패 복구·완료 이력·입력 무효화 이력을 보존함. J별 미저장 값과 서버 변경 충돌을 구분하고 대화도 같은 대상·revision·권한·액션을 사용함.
- 프로그램 `0.11.3+ees.10`·정적 경로 `/_ees10/`와 Agent Pack v0.2.11 / Workflow Tool 0.3.0을 같은 원본으로 전달하도록 버전·배포 경계를 갱신함. 요청 기록 테이블은 기존 업무 DB에 추가하며 사용자 자료·GLM 5.3 설정을 유지함. 프로그램 Restore와 DB/관리 자산 복원을 구분하고 구프로그램에서 새 업무 Tool을 제한함. [구현·검사 및 미확인 범위](evals/scenarios.md#work-panel-chat-implementation-20260917), [시험 적용 안내](docs/03-openwebui-native-agent.md#ees-work-panel-trial-20260917).

## 2026-09-16

- 사용자 요청 범위를 설계까지로 한정하고 [업무 패널·대화 통합 설계](docs/mockups/ees-work/TASK.md#work-panel-chat-design-20260916)를 기존 원본에 구체화함. P/T 직속 하위 관리·J 실제 처리·대화의 설명/초안/명령·Workspace 설정 책임, 상시 절차 탐색과 첫 쓰기, 상태/행동·과거 기록 보존을 정의함. 기존 조회/액션과의 차이 및 후속 수락 조건을 정리했으며 제품 구현·배포 변경은 없음. [검토 근거](evals/scenarios.md#work-panel-chat-review-20260916).

## 2026-09-15

- 사용자 요청의 [업무 패널 설계](docs/mockups/ees-work/TASK.md#work-panel-goal-design-20260915)→독립 검토→구현 순서로 P/T/J 내용을 구분함. 프로세스는 전체 목표·태스크 진행, 태스크는 완료 조건·잡 구성, 잡은 수행 방식·최근 결과·근거·재시도를 우선 표시함. 부모 예시 실행과 UI/AI 공통 액션을 유지하고 등록/미연결/구조 검증/모의 결과·사람 확인을 구분함. 완료·과거 근거 열람과 무효화된 이력을 보존하며 Workspace 검증 문구를 구조 검증으로 명확히 함. [검토·시험·미확인](evals/scenarios.md#workspace-native-design-20260915).

- [업무절차 Workspace 화면](docs/mockups/ees-work/TASK.md#workspace-native-design-20260915)을 기존 Native 정렬·서체·회색 버튼/입력폼에 맞춰 정리하고, 중복 큰 제목과 카드 테두리를 줄임. 기존 편집·초안·검증·게시 동작을 유지하며 사이드바 제목은 `업무`로 단순화함. GLM 5.3의 사용자 UI 반영 보고를 환경 기준에 갱신함. 실제 새 화면·모델 검증 및 배포는 [확인 범위](evals/scenarios.md#workspace-native-design-20260915)에서 구분함.

- [고정 원본 시험 업데이트](docs/03-openwebui-native-agent.md#ees-wrapper-trial)에 `Upgrade -TrialCommit`을 연결해 수동 ZIP 저장·경로 입력을 없앰. 공식 고정 wheel 다운로드/검증 캐시와 Git 원본의 줄바꿈 보존 패키징을 기존 Python으로 수행하고, 검증 뒤 기존 백업·Apply·Start·조건부 ApplyDemo를 순서대로 사용함. 기본 CI 경로와 사내 데이터/환경을 유지하며 준비 실패는 Stop 이전에 멈춤.

- 사용자 배포 요청에 따라 [9월 고정 원본 시험 적용](docs/03-openwebui-native-agent.md#ees-wrapper-trial)을 연결함. ApplyDemo의 공개 TrialCommit은 검토한 clean main·origin/main·설치 프로그램 원본을 확인하고 기존 자산 보호를 유지함. 기본 CI 경로는 유지하며 기존 내부 백업 기능을 공개 Backup 명령으로 재사용해 Stop 뒤 데이터/키/설정 검증 백업을 수행함. 실제 사내 실행은 배포 결과 보고와 구분함.

- [메인 채팅의 업무 탐색·계획](docs/mockups/ees-work/TASK.md#chat-workflow-entry-20260915)을 기존 Workflow Tool과 관리 Prompt에 구현함. 조회 중 업무 생성·선택 연결 없이 게시 절차의 단계/입력/지침을 읽고, 기존 진행은 고정된 절차와 현재 접근 가능한 스킬로 계획함. 동일 액션·권한·사람 확인 경계를 유지하며 새 계획 서버·모델·저장 형식을 추가하지 않음. 같은 ees.9/v0.2.10 준비본이며 사내 모델 확인·배포 여부는 STATUS에서 구분함.

- [R2 업무 화면 분리](evals/scenarios.md#work-ui-refactor-20260915)를 기존 요청 제어·표시·관리자 편집 책임으로 구현하고 단일 배포 JS/공개 연결을 유지함. 기존 브라우저 초안 보존 검사를 보강하고 R3 실제 프로그램 Apply→추가 저장→이전 ees.8 Restore 시험을 추가함. 같은 미배포 ees.9 준비본이며 Windows/브라우저 결과·사내 적용은 별도로 추적함.

- AI가 업무 변경 책임을 좁혀 찾도록 [R1 서버·정책 분리](evals/scenarios.md#workflow-refactor-20260915)를 구현함. 저장·권한·공개 facade는 유지하고 정의/검증과 화면 파생 계산을 분리했으며 공통 정책을 참고 seed에서 분리함. 완성 seed·저장 형식·기존 자료를 유지하고 새 파일의 wheel 포함과 ees.6~ees.8 Restore 목록을 구분함. 같은 미배포 ees.9 PR에 반영하며 자산 재등록·공동 권한 변경은 포함하지 않음.

- ees.9와 Agent Pack v0.2.10에 [R0 조건부 자산 적용](docs/03-openwebui-native-agent.md#conditional-assets)을 구현함. 서버가 최신 상태·권한과 저장을 같은 잠금으로 보호하고 ApplyDemo의 오래된 payload를 거절함. 실제 wheel 대조/독립 검토로 Tool import·지식 정리·채팅 캐시 경로를 포함하고 불필요한 외부 모델 조회 잠금은 제거함. 기존 자산 ID·사용자 자료·DB 형식과 구버전 프로그램 Restore를 유지하며, 구서버에서는 새 ApplyDemo 쓰기를 중단함. 구현과 사내 반영 여부는 [검증 기록](evals/scenarios.md#conditional-assets-20260915)에서 구분함.

- [제한적 리팩토링 설계](docs/mockups/ees-work/TASK.md#refactoring-design)에 파일별 책임·공개 연결·사용자 자료 보존·작업 순서·실제 배포물/Restore 검증 기준을 명시함. 독립 검토로 패널 동작 공통화를 제외하고 화면 상태/이벤트 소유권과 서버 자산 조건부 저장의 경계를 보완함. 자산 결함 수정과 순수 구조 정리를 분리했으며 이번 변경은 구현·배포를 포함하지 않음. [검토 근거](evals/scenarios.md#refactoring-design-review-20260915).

- 모든 개발을 AI가 맡는 전제와, 개발 환경에 없는 사내 UI 작성 Skill·Tool·연결·권한·설정의 보존 요구를 개발 지침·관리 원본에 명시함. 기존 예시 셋업을 확정 실무로 오해하지 않도록 최신 요구를 정정하고, 프로그램/자산 갱신의 보호와 지원 필드 동시 편집의 미해결 한계를 [검토 기록](evals/scenarios.md#ai-runtime-preservation-20260915)에 남김. 실행 코드·사용자 데이터·배포 동작은 변경하지 않음.

- 사용자 요청으로 첫 공동 작업 영역을 [셋업·신규 공장 횡전개](docs/mockups/ees-work/TASK.md#setup-first)로 확정함. 기존 네 단계와 A/B 이어가기 수락 예시를 연결하고 실제 파일럿 대상·공유 정책·합성 점검의 미확정/미구현 범위를 유지함.

- 사용자가 선택한 공장 1개·시스템 1개·프로세스 1개·2~3명의 첫 공동 작업 단위와 빠른 팀 사용 우선 목표를 [설계 원본](docs/mockups/ees-work/TASK.md#shared-pilot-first)에 기록함. 기존 진행 요약을 활용하고 일정·종합 현황판은 실사용 후 확장하는 제안을 구분했으며, 현재 진행률·날짜 데이터의 한계와 공동 작업 수락 기준을 연결함. 이번 반영은 문서에 한정함.

## 2026-09-14

- 승인한 사이드바 목업을 ees.8 후보에 반영함. P/T/J 설명 행을 제거하고 직계 하위 펼침·접힌 상태 유지, 공장/시스템 통합 선택 영역, Native UI와 새 업무 영역의 번들 글꼴을 보완함. 기존 실제 대화·초안·실행 경로와 권한을 유지하며 Agent Pack v0.2.9는 새 프로그램의 전문 Tool 호환성만 추가함. [원인·검증·적용 경계](evals/scenarios.md#sidebar-refinement-20260914).

- 실패 기록을 다음 변경의 검증 범위와 연결하도록 개발 지침을 보완함. 관련 이력 조회, 실패한 시도 보존, 같은 원인의 다른 경로 재발 점검, 복구와 근본원인 해결 구분, 코드·회귀 검사·운영 가이드의 반영 위치를 명시함. 사건별 기록은 기존 evals에 유지하고 새 보고 체계나 자동 권한 장치를 추가하지 않음. [실패 학습 규칙](AGENTS.md#failure-learning).

- ApplyDemo가 마지막 적용된 공식 `ees_specialists` 본문의 WebUI 편집기 자동 정렬을 현장 코드 변경으로 오인하던 경우를 보완함. 검증된 원본과 Black 26.5.1 정렬본의 정확한 해시 쌍만 허용하고, 실제 코드·주석·다른 관리 필드 변경과 미완료·동시 수정 검사는 유지함. 실행 중인 ees.7은 그대로 두고 Update → ApplyDemo로 이어가며 포맷터 의존성·강제 덮어쓰기·기록 초기화를 추가하지 않음. [원인·검증·사내 경계](evals/scenarios.md#specialists-editor-format-20260914).

- 최종 [공장 → 시스템 → 업무 공동 작업 목표](docs/mockups/ees-work/TASK.md#ees-work-shared-target)를 설계 원본에 기록함. 공유할 업무 진행·결과·이력과 개인 채팅·권한을 구분하고, 현행 ees.7 사용자별 실행과 후속 구현 범위가 혼동되지 않도록 문서 진입점·다음 작업을 정리함. 실행 코드·권한·저장 구조는 변경하지 않음.

- 사용자 요청으로 Windows 프로그램 폴더 변경의 접근/공유 잠금 오류에 1·2·4·8초의 제한적인 대기를 추가함. 원본·부모 식별자와 빈 목적지를 매 시도 재확인하고, 실패하면 원래 오류·횟수·대기 시간을 보존함. 정확한 Upgrade promote 실패는 기존 수동 변경·Apply -Resume으로 이어지도록 안내하며 전체 업데이트·재기동 반복이나 권한 변경은 추가하지 않음. [검증·사내 적용 구분](evals/scenarios.md#windows-program-rename-20260914).

- 후속 목업 합의에 따라 ees.7 / Agent Pack v0.2.8에 공장·시스템 선택 아래 분류·P/T/J를 기존 사이드바에서 펼치는 구조와 현재 작업/읽기 전용 실행 이력을 반영함. 기존 Native 대화·초안 보존 경로를 재사용하고, 실행 당시 절차 트리·공장별 상태·권한을 유지함. Workspace 업무 절차 탭의 반복 재삽입과 글꼴 차이를 보완하고 서비스 표시를 EES Work로 변경함. [발견·검증 범위와 사내 경계](evals/scenarios.md#ees-work-factory-ux-20260914).

- EES Work의 별도 데모 창과 모의 AI를 요구했던 인계가 사용자 의도와 달랐음을 확인하고 [통합 지시](docs/mockups/ees-work/TASK.md)를 정정함. 기존 WebUI 사이드바·실제 대화·오른쪽 업무 패널·관리자 워크스페이스를 재사용하고, 버튼과 Native 업무 Tool이 같은 상태·액션을 쓰는 구성을 채택함. ees.5 당시 구현·검사·사내 관찰 기록은 아래와 평가 기록에 보존함.

- ees.6과 Agent Pack v0.2.7에 공장별 P/T/J 탐색·업무 패널·Native 업무 Tool·관리자 절차 편집을 연결함. 같은 서버에서 사용자별 진행 건과 관리자 정의를 저장하고, 선행 조건·입력 변경·재시도 이력·버전 게시를 검사함. 실제 대화와 기존 문서 조회를 유지하고 DB/AP 점검은 합성 실행으로 구분하며 실행 어댑터가 없는 등록 도구 참조는 차단함. [적용·저장·실행 경계](docs/03-openwebui-native-agent.md#ees-work-demo). 검사와 실제 적용 판정은 STATUS의 평가 기록을 따름.

- EES Portal ees.5에 로그인된 사용자가 여는 EES Work 시연과 실행·설계 워크스페이스를 연결함. 브라우저 메모리에서만 P/T/J 실행·실패/재시도·버전 게시·현장 제외를 시뮬레이션하고 기존 대화로 복귀함. 고정 파일 인증·업무 네트워크 차단·구버전 시작/복원을 유지하며 기존 프로그램 Upgrade 경로로 배포함. [범위·검증·실제 배포 구분](evals/scenarios.md#ees-work-demo-integration-20260914).

- EES Work 통합 목업 원본과 [구현 작업 지시](docs/mockups/ees-work/TASK.md)를 저장소 경로로 제공함. ZIP·대화 파일 접근에 의존하지 않고 다음 구현 담당자가 같은 기준을 읽을 수 있도록 README에서 연결함. 이번 변경은 참고 원본·지시 등록이며 실제 포털 UI·배포 동작은 변경하지 않음.

- 원본·커스터마이즈 자식 기동에 CPython 3.11 IOCP WinError64 수락 보호를 추가함. 실패한 연결만 정리하고 지연 재수락하며 다른 오류·취소·종료를 유지함. `Start -CheckOnly`와 기존 교체 사전검사로 정지 전 호환성을 확인하고 새 Start는 health·보호 표시를 함께 확인함. 시스템 Python·패키지·DB·키·주소·TLS·종료 권한은 변경하지 않음. [시험·배포 구분](evals/scenarios.md#accept64-guard-20260914).

## 2026-09-11

- v0.2.6의 첫 화면 제안은 세 개를 유지하면서 설비 조회를 WO 작성 흐름에 묶고, Jira·GitHub·Confluence 업무 현황 시연을 추가함. 실제 계정 조회와 합성 분석/WO의 범위를 안내하고 이전 공식 설비 제안도 정확히 일치할 때만 정리함. [검증·미확인](evals/scenarios.md#connector-demo-starters).

- 현재 상태와 과거 이슈 증거를 기존 관리 원본에 맞춰 정리함. 중단한 후보 배포 명령은 과거 근거로 연결하고 설치 버전·Jira 사용 안내의 잔여 설명을 고침. 문서 29개는 목적이 있어 보존하며, 병합 브랜치 32개와 미병합 보존 대상을 구분함. 당시 연결 기능 부재로 삭제는 준비까지만 진행했고, 후속 사용자 실행·원격 확인으로 32개 삭제와 main/미병합 브랜치 보존을 완료함. [정리·검증·제한](evals/scenarios.md#repository-maintenance-20260911).

- v0.2.4 적용 후에도 제안이 바뀌지 않는 필드명 오류를 수정함. 실제 WebUI의 `suggestion_prompts`를 사용하고 이전 잘못된 필드/적용 기록에서 갱신하며, 실제 UI 계약과 사용자 수정 보존을 대조함. 이전 모의 검사 통과를 화면 반영 성공으로 보지 않음. [원인·검증](evals/scenarios.md#starter-ui-field-fix).

- 메인 화면의 대표 시연 질문을 생산 손실 분석·천안 설비 조회·점검 WO 초안 세 개로 정리함. ApplyDemo와 수동 가져오기가 같은 JSON을 사용하고, 과거 공식 수동 질문은 전체 일치일 때만 정리해 사용자 질문을 보존함. [적용](docs/03-openwebui-native-agent.md#first-use-entry), [검증](evals/scenarios.md#three-demo-starters).

## 2026-09-10

- 반복 업데이트 실패 조사에서 Windows 종료/신원 조회 경합과 WAIT_FAILED 처리 결함을 수정하고, 정상 종료 helper·Upgrade 오류의 고정 단계/숫자/위치를 보존함. 최신 실패를 성공 뒤에도 유지하며 보존된 종료 실패 로그만 읽는 한정 검사를 추가함. 기존 정상 종료·데이터 보존 경계와 미확정 원인 구분을 유지함. [근거·조치](evals/scenarios.md#ees-update-failure-causes).

- 사용자 승인된 Upgrade `process_stop` 실패에 한해 같은 핸들로 검증된 서버 하나를 종료하고 보관 ZIP으로 적용·기동하는 명시적 복구 경로를 추가함. 실패/registry 보존·venv 실행기 관계 검증·일반 Stop/Upgrade의 정상 종료 경계를 유지함. [절차](docs/03-openwebui-native-agent.md#ees-stop-recovery), [사건·검증](evals/scenarios.md#ees-stop-recovery).

- ees.3 글꼴·업무 패널 변경 확인 후의 피드백을 반영해 기본 본문·입력창 폭을 672→1024px로 넓힘(ees.4). 분석 패널 드래그의 전체 높이 파란 테두리를 제거하고 키보드 포커스는 작은 손잡이에 유지함. 기존 글꼴·색상·크기 저장·키보드 조절을 보존하며 자산 v0.2.3 ApplyDemo 후 Upgrade로 반영함. [사용법](docs/03-openwebui-native-agent.md#ees-chat-width-resize), [검증](evals/scenarios.md#ees-chat-width-resize).

- 승인한 대화창 시안의 글꼴·색상·간격을 EES Portal ees.3에 적용함. 고정 wheel의 Inter/Noto Sans KR를 프로그램과 함께 제공하고 대화·입력창·사이드바·오른쪽 업무 패널의 톤을 맞춤. 기존 의존성·데이터·키·설정과 ees.1/ees.2 Restore를 보존하며, 시연 자산 v0.2.2의 전문 도구 호환을 먼저 갱신한 뒤 프로그램 Upgrade를 실행함. [적용 순서](docs/03-openwebui-native-agent.md#ees-chat-theme), [검증](evals/scenarios.md#ees-chat-theme).

- 시연 자산 v0.2.1은 Open WebUI 0.11.3이 저장 전에 자동 정렬한 공식 WO 등록본도 인식함. 고정 Black 26.5.1로 검증한 v0.1.6/v0.1.7/v0.1.8의 완전 해시만 추가하며 사용자 수정·이름/권한/설정 보호와 기존 적용 절차를 유지함. [실패·재현·수정 근거](evals/scenarios.md#wo-editor-format-adoption).
- 교차 분석 v0.2.0은 EES가 실행 계획을 먼저 등록하고 실제 전문·비교 결과에 맞춰 단계를 표시함. 본문은 짧은 결론과 다음 행동으로 줄이고 실행 전 선택 이유·결과 후 판단·불확실성·상세 자료는 오른쪽 업무 패널에서 확인함. 분석·설비 조회·WO를 기존 업무 패널 버튼으로 연결하고 초안을 유지함. ApplyDemo는 공식 기존 WO 등록본만 같은 ID로 갱신하며 현장 수정은 보존·충돌로 처리함. 별도 진행 시연·서버·요약 모델 호출은 추가하지 않음. [사용법](docs/03-openwebui-native-agent.md#cooperation-panel), [검증과 사내 확인 경계](evals/scenarios.md#cross-system-plan-work-panel).
- 교차 분석 시연 v0.1.3은 회신을 먼저 읽는 패널·접을 수 있는 질문/조회 근거·핵심 수치 표시와 업무 중심의 가상 조립 2라인 시작 질문으로 개선함. 원래 합성 사건·계산과 현재 호출 구조를 유지하고 실제 운영 자료와 구분함. Portal 이름은 이미 구현된 프로그램 Upgrade와 ApplyDemo를 같은 블록으로 적용하도록 안내함. [사용법](docs/03-openwebui-native-agent.md#cooperation-panel), [사용자 확인·검증](evals/scenarios.md#cross-system-demo-readability).
- 교차 분석 시연 v0.1.2는 우측 협업 과정 패널에 실제 전문 요청·자료 확인·회신·보완·교차 계산을 표시함. 질문과 호출별 상태를 구분하고 부분 실패·취소·대화 이동 중 놓친 상태를 명시함. 고정 화면 코드를 기존 두 Tool에 포함해 ApplyDemo 한 번으로 갱신하며 전문 호출 구조·한도·계산·기존 사용자 설정을 유지함. [패널과 한계](docs/03-openwebui-native-agent.md#cooperation-panel), [검증](evals/scenarios.md#cross-system-demo-panel).
- 교차 분석 시연 v0.1.1은 호출 횟수 대신 전문가별 맡긴 질문·실제 회신·대표 근거와 EES의 비교·종합 결과를 문장/표로 설명하도록 개선함. 전문 반환값에 첫 분석/보완 요청과 회신 잘림 여부를 보존하고 각 전문 지침·EES 결과 형식을 함께 갱신함. 별도 UI·서버·추가 LLM 호출 없이 기존 ApplyDemo로 반영하며 브라우저 새로고침 뒤 기본 도구 선택을 안내함. [결과 형식](docs/03-openwebui-native-agent.md#cross-system-demo), [검증과 사내 확인 구분](evals/scenarios.md#cross-system-demo-readable-results).

- 합성 교차 분석 시연을 구현함. 기존 EES가 EMS/APC/FDC 전문 Workspace 모델을 실제 호출하며 근거를 취합하고 조건별 수치를 계산한다. 자료·전문 호출·보완 횟수와 사용자 권한을 코드에서 제한한다. ApplyDemo가 검증된 main을 갱신한 뒤 지정 Tool/Valves·전문 모델·기존 EES 관리 구역을 API로 병합하고, 기존 설정·개인 PAT를 유지하며 응답 유실 뒤 재실행을 지원한다. 최초 인증은 WebUI 관리자 API Key를 별도 DPAPI 저장한다. 기존 서버 재시작·운영 DB 조사·새 서버 없이 적용한다. [사용법](docs/03-openwebui-native-agent.md#demo-assets-deployment), [검증 및 사내 미확인 범위](evals/scenarios.md#cross-system-demo-implementation).

- EES 기본 창구·시스템별 전문 Assistant·공통 도구 재사용 합의와 개선 기회/KPI 후보 발견 목표를 반영함. 합성 시연 3개, 전문 호출 최대 4회, 기존 EES+신규 전문 모델 3개·Tool 2개·Prompt/시작 질문 일괄 적용을 설계·독립 검토함. 고정 0.11.3의 자산 API·관리자 인증·설정 보존 경로를 확인했으며 ApplyDemo와 실행 자산은 아직 미구현. [시연 및 한 번 적용 설계](docs/03-openwebui-native-agent.md#demo-assets-deployment).

- 컨셉 시연을 우선한다는 사용자 결정에 따라 실제 DB·코드 관계 조사를 운영 준비 단계로 미룸. 합성 EMS/APC/FDC 자료·공통 관계를 준비하고 실제 모델의 전문 Assistant 선택·호출·조건부 보완·종합 분석을 보여주는 범위를 확정함. 다음 작업을 DB 조사 준비에서 시연 구현으로 수정했으며 실행 기능은 아직 미구현. [현재 시연 범위](docs/03-openwebui-native-agent.md#cross-system-demo).

- 시스템들이 하나의 물리 DB와 일부 공통 데이터를 사용한다는 설명을 반영해, 승인된 DB 구조·실제 코드에서 관계를 발견하고 담당자가 자기 영역의 의미를 확인하는 설계를 추가함. 복합키·사업장·유효기간·행 단위/연결 수·시각 의미와 관계 검증/인과 가설을 구분함. 실제 DB 조사·실행 기능 변경은 없음. [관계 발견](docs/03-openwebui-native-agent.md#shared-db-relations).

- EES가 EMS/APC/EGIS/FDC/EPT와 추가 전문 Assistant를 선택·위임하고, 시스템 간 근거 대조와 보완 요청으로 분석하는 목표를 기록함. 역량 설명·공통 식별자·개인 권한 유지, 합성 교차 분석 시연과 반증/미연결 판정 기준을 기존 문서에 정리함. 설계 기록이며 실행 코드·모델 등록·사내 데이터 연결은 미변경. [설계와 시연 제안](docs/03-openwebui-native-agent.md#cross-system-orchestration).

## 2026-09-09

- 기존 운영 진입점에 `Upgrade`를 추가해 성공한 main CI 확인·래퍼 갱신·호환 프로그램 ZIP 다운로드·검증·Stop/Apply/Start를 한 번에 수행하도록 준비함. 같은 프로그램은 재시작하지 않고 적용 기록이 일치하면 다운로드도 생략함. 읽기 전용 GitHub 인증을 Windows 사용자별 DPAPI로 보존하며 기존 환경·데이터·키·CA와 명시적 복구를 유지함. 프로그램 artifact는 별도 이름과 90일 보존으로 구분하고 공통 Tool/Skill/Prompt 자동 반영은 포함하지 않음. [사용법](docs/03-openwebui-native-agent.md#ees-wrapper-upgrade), [검증·적용 구분](evals/scenarios.md#ees-wrapper-upgrade).

- 서비스 브랜딩을 EES Portal로 변경하는 ees.2와 별도 frontend 캐시 경로를 준비함. 저장된 옛 이름만 새 이름으로 표시하고 기존 데이터·환경·CA 선택을 유지하며, 설치된 ees.1의 시작과 ees.2 적용 후 직전 Restore를 지원함. WO 시연 v0.1.7은 서비스 표기만 변경하고 모델·정책·업무 기능은 유지함. [적용 안내](docs/03-openwebui-native-agent.md#ees-portal-name).

- 등록된 서버의 SSL 다운로드 지연에 대응해 현재 래퍼에 `Start -UseWindowsCA`를 추가함. 종료된 서버에 Windows 신뢰 인증서 스냅샷을 선택하고 서버 자식 환경에만 적용하며 이후 일반 Start에서도 재사용함. 기존 CA 검증·프로세스 보호를 재사용하고 등록 설정·Python·데이터·키·TLS 검증은 유지함. [복구 절차](docs/03-openwebui-native-agent.md#ees-start-windows-ca), [진단·검증 범위](evals/scenarios.md#ees-start-health-followup).

- WO 시연 v0.1.6: 크기 조절 바의 마우스 클릭·드래그 직후 파란 포커스 테두리를 숨기고 Tab·방향키 조작의 표시는 유지함. 기존 너비 조절·WO 상태 검사 통과, 사내 표시 변경은 적용 후 확인 대상.
- 설비 조회의 패널 실행 예외 보고를 받아 v0.1.5에서 버전·발생 단계·허용된 예외 종류를 짧은 진단값으로 반환함. 첫 화면 렌더링이 성공한 뒤 캐시하도록 변경해 초기 실패가 재시도에도 고착되는 경우를 보완하고 기존 정상 WO 상태를 유지함. 실제 최초 예외 원인은 진단 전이며 조회 성공과 화면 오류를 계속 구분함. [적용·진단 안내](docs/03-openwebui-native-agent.md#wo-mockup).

- 업무 패널 열기/닫기와 기능 정상 보고를 반영하고, v0.1.4에서 상단 ‘제어’ 옆에 동일한 버튼 크기·색상·hover 스타일의 패널 아이콘을 배치함. 대화 위에 떠 있던 텍스트 버튼을 정리하고 이름 안내·열림 상태·기존 동작을 유지함. [적용 안내](docs/03-openwebui-native-agent.md#wo-mockup).

- 사내 시연에서 대화를 옮겼다 돌아오면 업무 패널이 사라지고 직접 다시 열 수 없던 흐름을 v0.1.3에서 보완함. 같은 브라우저 탭의 대화별 상태·너비·열림 여부를 보존하고 채팅의 열기/닫기 버튼으로 재개하도록 하며 기존 검색·WO 확인 상태를 유지함. 갱신 대상은 기존 시연 Tool 코드 한 개이고 영구 저장·새 등록 항목은 추가하지 않음. [적용·검증 경계](docs/03-openwebui-native-agent.md#wo-mockup), [보고·검증 기록](evals/scenarios.md#wo-mockup).

- 설비 조회만 요청해도 우측 검색 패널을 표시하도록 v0.1.2를 준비함. 필터·검색 결과·선택 정보를 보여주고 같은 패널에서 AI의 WO 초안 작성으로 이어지며, 설비 탐색만으로 기존 초안 대상·내용·확인 상태를 바꾸지 않음. 첫 화면 제안 JSON도 천안·헝가리 설비 조회, AI WO 초안, 직접 선택의 네 시연 질문으로 교체하고 기존 EES 모델의 사용자 정의 목록에 적용하도록 안내함. 시연의 단일 등록과 운영용 공통 Tool 분리 방향을 유지함. [시연 안내](docs/03-openwebui-native-agent.md#wo-mockup), [검증 기록](evals/scenarios.md#wo-mockup).

- 설비 조회는 여러 업무에서 재사용할 공통 Tool로 독립 등록·관리하는 방향을 정하되, 사용자가 이번 시연에는 적용이 간단한 기존 단일 등록 항목을 유지하기로 함. 함수 분리와 등록 단위 분리의 차이를 안내에 명시하며 실행 코드·적용 절차는 유지함. [시연 범위와 후속 분리 방향](docs/03-openwebui-native-agent.md#wo-mockup).

- 기존 대화·우측 패널 WO 시연의 사내 동작 보고를 받고 v0.1.1에서 AI의 첫 초안 작성, 드래그·키보드 패널 너비 조절, 브라우저와 독립적인 설비 검색을 보완함. WO와 설비 검색은 같은 샘플 목록·검색 코드를 재사용하며 기존 EES WO Demo 등록 파일 한 개로 유지함. 최신 폼·변경 번호 대조와 사용자 최종 버튼의 샘플 결과를 유지하고 실제 EMS 연결·저장은 없음. 기존 Tool 코드와 WO Prompt 절만 교체하는 갱신 안내를 추가하며 초기 성공 보고와 추가 변경의 사내 확인을 구분함. 시연용 목업 → 피드백 → 운영용 목업 → 실제 EMS 구현 순서와 후속 권한 세분화 방향은 유지함. [시연 안내와 적용 경계](docs/03-openwebui-native-agent.md#wo-mockup), [검증 기록](evals/scenarios.md#wo-mockup).

- 사용자 요청으로 WO 작성의 클릭 가능한 참고 목업을 준비함. 직접 입력·예시 채팅의 같은 폼 수정·변경 표시·내용 확인·사용자 최종 버튼·샘플 결과 흐름을 단일 HTML에 담으며 실제 AI·EMS 호출과 WebUI 배포는 없음. 입력 항목은 예시이고 디자인 승인·쓰기 권한 확대와 구분함. [목업 안내](docs/03-openwebui-native-agent.md#wo-mockup), [검증 범위](evals/scenarios.md#wo-mockup).

- 사용자 합의로 레거시 업무 화면은 준비된 화면·부품의 상황별 활용과 사람/AI의 같은 폼 편집을 기본으로 정함. 클릭 가능한 목업을 사용자에게 확인받고 실제 기능을 연결하며, WO 발행 같은 상태 변경은 최종 버튼과 서버 검증으로 실행하도록 설계함. 기존 래퍼 안에서 작게 시작하고 실제 반복이 생길 때 공통화함. 설계 방향 기록이며 목업 승인·EMS 연동·쓰기 정책 변경은 아님. [설계 기준](docs/03-openwebui-native-agent.md#legacy-ui-design), [검토와 미구현 범위](evals/scenarios.md#legacy-ui-design).

- 사용자가 초기 시험용 Rich UI를 모두 걷어내고 업무별로 새로 설계하기로 결정함. Confluence/Jira v0.1.6·GitHub v0.1.4는 기존 검증·마스킹 JSON을 직접 반환하고 공통 Prompt는 일반 답변·표·원문 링크를 안내함. 렌더러·HTML 예제·전용 UI 시험을 제거하고 중요한 데이터 계약 검사를 기존 읽기 시험에 유지함. 조회·권한·개인 설정과 대화 기록은 보존하며 사내 기존 Tool 3개·Prompt 갱신 안내를 제공함. 영문 새 기능/릴리스 팝업은 추후 관리자 공지에 활용하자는 요구로 기록하고 이번에는 변경하지 않음. [검증·사내 반영 경계](evals/scenarios.md#prototype-rich-ui-removal).

- 실제 Apply의 promote 미완료 뒤 사용자가 program.staging을 program으로 옮긴 경우, 같은 ZIP·기록·전체 파일을 검증해 완료하는 명시적 Apply -Resume을 추가함. 기존 잠금/서버 종료·직전 Restore 보호를 재사용하며 시험 폴더 채택·자동 파일 이동/재시도·새 환경을 추가하지 않음. [검증과 사내 적용 구분](evals/scenarios.md#ees-wrapper-manual-resume).

- Apply 등 일반 파일/상태 오류에서 사라졌던 예외 종류·errno/winerror·고정 내부 코드 위치를 기존 한 줄 요약과 상세 결과에 보존함. 개인 경로·원문 오류는 제외하며 새 재시도/복구 동작은 추가하지 않음. 최초 프로그램 폴더 이동 실패 회귀와 Windows/Linux 실제 wheel의 Apply/Restore 검사를 보완함. [검증·사내 상태](evals/scenarios.md#ees-wrapper-error-evidence).

- 기존 Python·호환 의존성을 재사용하며 검증된 Open WebUI 앱/metadata만 관리 폴더에 적용하는 Apply/CheckOnly·직전 Restore와 기존 Start/Stop/Status 연결을 추가함. 기존 빌더·운영 코드를 재사용하고 미완료 적용의 시작 차단·보관본/잠금 대조·구형 후보 작업 혼용 차단, 직접 타이핑용 한 줄 요약과 짧은 사내 안내를 준비함. uvx 설치·데이터·키·개인 설정을 유지하고 새 환경/재설치·자동 전환/복구를 추가하지 않음. 검증·게시 결과와 사내 적용 여부는 [구현 기록](evals/scenarios.md#ees-wrapper-implementation)에 구분함.

## 2026-09-08

- 단순 래퍼의 적용/직전 복원 설계와 구현·검증 계획을 작성하고 독립 검토함. uvx 캐시 환경 직접 수정 대신 수정된 Open WebUI 앱/metadata만 래퍼 관리 경로에 두고 기존 interpreter·의존성을 재사용하는 방식을 채택함. 기존 빌더/운영 진입점과 적용·복원 두 작업으로 한정하며 미완료 작업의 기동 차단·잠금 회수 조건을 정의함. 설계 완료이며 실행 기능 구현·사내 적용 완료를 뜻하지 않음. [설계](docs/03-openwebui-native-agent.md#ees-wrapper-design), [검토](evals/scenarios.md#ees-wrapper-design).

- 사용자 합의에 따라 공식 Open WebUI 패키지와 우리 프로젝트 래퍼 두 구성으로 유지보수 범위를 정함. 기존 Python·호환 의존성을 재사용하고 래퍼에서 사내 수정사항의 적용·되돌리기를 관리하는 방향으로 전환함. 별도 후보 환경의 지연 진단과 자동 전환/복구 확대를 중단하고 이전 코드·실패 증거는 보존함. 새 적용 명령 구현·실제 서버 변경 완료를 뜻하지 않음. [관리 기준](docs/03-openwebui-native-agent.md#ees-wrapper-maintenance), [합의·마지막 진단 결과](evals/scenarios.md#ees-wrapper-maintenance).

- import 검사에서 부모와 자식의 timeout 시작 기준이 달라 덤프 전에 부모가 중단할 수 있던 결함을 수정함. 부모 시작 기준의 절대 deadline·시작 예산 소진 분류와 SEND T1 시간 요약을 추가하고 기존 60/70초 한도를 유지함. 이전 수동 출력 수집은 완료했으며 마지막 pandas 이름을 원인으로 단정하지 않음. [근거와 다음 비교](docs/03-openwebui-native-agent.md#ees-import-deadline).

- import 검사에서 Windows 사용자 폴더 변수를 모두 제외해 NLTK 자체 오류를 만들 수 있던 환경 필터를 수정함. 일반 프로필 정보는 보존하고 실제 NLTK import/오류 재현을 CI에 추가함. 기존 사내 결과와 후보 자식 종료 미확인은 별도로 기록하고 재검사 대신 기존 출력·읽기 조회로 후속 확인함. [근거와 한계](evals/scenarios.md#ees-import-followup).

- 사내 결과는 직접 타이핑만 가능하다는 제약에 맞춰 ProbeImports에 전달용 SEND 한 줄과 최근 비식별 상세 결과 저장을 추가함. 이미 한 검사는 반복하지 않고 기존 화면의 상태·시간 네 값으로 진행하며 전체 출력·파일·사진 요청을 철회함. [전달 방식](docs/03-openwebui-native-agent.md#ees-import-probe), [검증](evals/scenarios.md#ees-typed-handoff).

- Diagnose v2의 사내 결과를 기록하고, 종료 traceback만으로 원인을 단정하지 않도록 고정 NLTK import 비교 명령 `ProbeImports`를 추가함. 기존/후보별 계측·자가 종료 한도·비식별 결과를 한 번에 제공하며 서버 전환 없이 지연 재현 여부를 확인함. [사용법과 제한](docs/03-openwebui-native-agent.md#ees-import-probe), [증거](evals/scenarios.md#ees-import-probe).

- 사내 확인을 짧은 Git 명령·한 번의 결과 전달·근거에 따른 다음 행동으로 재설계함. 새 실패 기록에 이유·기동 health 경과/한도·종료 코드·후보와 복구 로그 식별자를 보존하고 Diagnose v2에서 정확한 로그 연결과 첫 비중단/마지막 오류 위치를 제공함. 프로세스 확인 실패에도 확보한 진단을 반환하며 기존 데이터·복구 순서·대기 한도는 유지함. [운영 흐름](docs/03-openwebui-native-agent.md#ees-diagnostic-workflow), [검증과 한계](evals/scenarios.md#ees-diagnostic-workflow).

- `Diagnose`로 자동 복구 뒤 실패 후보의 시간·기동/네트워크 마커·공개 traceback 위치를 한 번에 요약. 반복 재배포와 수동 중간 전사를 줄이고, 기존 로그를 읽어 다음 조치를 정함. 앱 import·기동·통신·데이터/캐시 쓰기 없이 동작함. [사용법](docs/03-openwebui-native-agent.md#ees-diagnose-once), [검증](evals/scenarios.md#ees-diagnose-once).

- 후보 배포의 `-UseWindowsCA` 옵션 추가. 기존 서버 종료 전에 후보 Python으로 Windows 포함 CA 스냅샷을 준비하고, 릴리스의 자식 환경과 이후 Start/Rollback에 같은 신뢰 파일을 적용함. 등록된 config/DPAPI·기존 프로그램 복구 환경·데이터·키는 유지함. [사용법](docs/03-openwebui-native-agent.md#ees-windows-ca-deploy), [검증·사내 적용 구분](evals/scenarios.md#ees-windows-ca-support).

- 프로그램 전환과 자동 복구의 실패 단계·오류 분류·소켓 errno/winerror를 구분해 콘솔과 기존 배포 기록에 남김. Status는 허용 필드만 표시하고 마지막 실패를 시간과 함께 보존함. 포트 오류를 점유로 단정하지 않으며 시작/health 오류에서 사용자 로그 경로를 제거함. 기존 포트 검사·잠금·프로세스 식별·환경/데이터 보호·복구 순서는 유지하고 추가 재시도는 없음. [진단 안내](docs/03-openwebui-native-agent.md#ees-deployment-diagnostics), [검증](evals/scenarios.md#ees-deployment-diagnostics).

- 첫 오프라인 Prepare에서 antlr4-python3-runtime 4.9.3 wheel을 선택하지 못한 사례를 위한 캐시 복구 명령 추가. 기존 빌드 wheel을 검증·복사하고 비활성 실패 후보와 로그를 보존한 뒤 같은 버전으로 다시 준비함. 원래 서버·데이터·배포 기록을 전환하지 않으며 기존 캐시와 오프라인 제한을 유지함. [사용법](docs/03-openwebui-native-agent.md#ees-offline-recovery), [근거](evals/scenarios.md#ees-first-registration).

- 사내 초기 관리 기동에서 60초 health 시간 초과 후 정상 응답이 확인되어 대기 기본값을 300초로 늘리고 명령별 1~900초 선택 인자를 추가함. 배포/원복 및 실패 후 기존 프로그램 복구에도 같은 제한을 적용하며 재등록·DB/키 변경 없이 사용할 수 있음. 초기 실행 정책 차단·시간 초과·후속 health 성공을 함께 기록하고 PowerShell 현재 창 설정 안내를 보완함. [근거](evals/scenarios.md#ees-first-registration).

- Git 갱신·초기 환경 등록·고정 커밋 계획/오프라인 준비·배포/원복·시작/종료를 하나의 PowerShell 진입점으로 구현. 기존 DB·키·파일·실행 설정을 유지하고, 종료 후 검증 백업과 실패 시 프로그램 복구를 제공함. 신원 미확인 프로세스는 자동 복구를 차단하며 정상 데이터가 쌓인 DB 전체를 되돌리지 않음. 사내 적용과 공통 자산 API 동기화는 별도. [명령](docs/03-openwebui-native-agent.md#기존-windows-서버에-적용), [검증](evals/scenarios.md#ees-program-deployment).

## 2026-09-07

- 사용자 요구에 따라 기존 스킬·툴·모델·대화·개인 Memory·키·저장소를 보존하는 배포 계약을 명시. Git/CI 다음의 사내 계획·적용·원복 진입점과 기존 ID의 관리 필드만 갱신하는 API 동기화를 다음 구현 범위로 정리함. 실행 코드·사내 데이터 변경 없음. [배포 설계](docs/03-openwebui-native-agent.md#데이터-보존과-사내-자동화-계획).

- 초기 사용 인원 50명 이하 확인에 따라 EES 이름·아이콘을 적용하는 0.11.3+ees.1 별도 wheel 빌더와 해시/원본 커밋을 기록하는 Agent Pack ZIP 도구를 추가. 관련 검사·변경별 패키징 Actions를 준비하고 기존 Windows 환경을 보존하는 전환/원복 절차를 정리함. 사내 배포는 별도. [검증·범위](evals/scenarios.md#ees-branding-delivery).

- 팀 시연을 우선해 EES 이름·소개·시작 질문 4개와 짧은 안내의 적용 준비를 재개. 브랜딩의 50명/30일 라이선스 예외를 확인해 Enterprise 전용 단정을 정정하고, 설정/Agent Pack과 upstream 빌드의 배포·원복 계획을 분리함. 실제 브랜딩 교체·CI/사내 배포는 미수행. [준비 기록](evals/scenarios.md#team-demo-customization).

- 공통 정책 적용 범위를 EES Assistant로 한정하고 사용자 제시 여섯 목표를 프로젝트 계획에 반영. 관리자 워크플로와 레거시 간접 UI를 별도 목표로 명시하고 구현 수단 선택 기준·보류 범위를 정리함. 실행 코드·사내 설정 변경 없음. [결정 기록](evals/scenarios.md#six-project-goals).

- 사용자 요청으로 공통 정책의 사용자 적용을 최우선 작업으로 변경. 기존 정책 답변 Skill·공통 Prompt·실행 권한의 역할과 적용 범위를 구분하며, 실제 규정·WebUI 설정은 변경하지 않음. [결정 기록](evals/scenarios.md#common-policy-priority).

- Confluence v0.1.5: 검색 API의 HTTP 400을 `invalid_query`로 구분해 검색어 변경과 지속 실패 시 설정 확인을 안내. 비검색 400은 `invalid_request`로 처리하며 추가 호출·재시도·의존성 없이 기존 오류 처리에 경로만 전달함. 관련 오프라인 시험 11개 통과, 사내 적용 대기. 사용자의 본문 버튼 제거 확인을 기록하고 원문 링크·전체 Rich UI 디자인은 후속으로 유지함. [검증](evals/confluence-offline.md#search-error-guidance), [사용자 보고](evals/scenarios.md#body-query-buttons-observed).

- Confluence v0.1.4·GitHub v0.1.3·Jira v0.1.5: 사용자 요청에 따라 문서/PR/이슈마다 반복되던 본문 질문 버튼과 전용 코드를 제거. 원문·본문 근거·목록 조작을 유지하고 기존 Prompt의 자연어 후속 조회를 사용함. Confluence 전용 입력 브리지·복사용 영역도 제거했으며 추가 호출/의존성·서버 변경 없음. 기존 Jira 날짜 시험의 시간대 의존은 해당 시험 조건만 명시해 보완. [검수·적용 범위](evals/scenarios.md#body-query-buttons-removed).

- 사용자 의견에 따라 Rich UI 시각 디자인 튜닝은 기능 흐름 완성 뒤 묶어 진행하도록 후속으로 정리. GitHub/Jira의 정상 동작 보고와 디자인 만족도를 구분하고 업무를 막는 조작·가독성 문제는 발견 시 보완함. 첫 화면·온보딩 보류 유지, 현재 CSS·새 디자인 시스템 변경 없음. [결정 기록](evals/scenarios.md#jira-rich-ui-acceptance).

- LAN 접속의 origin 거부 대응을 현재 창 전용 설정에서 Windows User 영구 저장과 현재 창 동시 적용으로 보완. 기존 허용 목록을 유지하고 초기 진단 명령의 loopback 덮어쓰기를 제거했으며 별도 설정 파일·로더는 추가하지 않음. 실제 저장·복구는 사용자 확인 대기. [안내](docs/troubleshooting.md#cors-origin-update), [검토 기록](evals/scenarios.md#chat-live-update-observation).

- GitHub v0.1.2 PR 목록/본문과 Confluence v0.1.3 검색/본문/근거 카드를 기존 단일 Tool에 추가. 실제 ID·확인된 다음 페이지로 수동 질문 초안을 만들고 빈 결과/오류·범위·잘림을 구분함. 기존 조회 결과와 본문 근거를 재사용하고 UI HTML과 중복 표를 모델 답변에서 줄이며 새 의존성·API/모델 호출·서버는 추가하지 않음. 공용 오프라인 DOM 검사 도구를 사용하고 사내 적용은 대기. [GitHub 검증](evals/github-offline.md#rich-ui-results), [Confluence 검증](evals/confluence-offline.md#rich-ui-results).

- Jira Tool v0.1.4: MVP에 필요한 원문 링크의 조작 영역·이슈별 접근성 이름, 빈 필터의 즉시 초기화, 실패 설명 연결과 당시 조회 시각 표시를 보완. 기존 HTML만 수정하고 조회·인증·후속 질문 계약은 유지함. 사내 적용 대기. [검증](evals/jira-offline.md#mvp-usability).

- Jira Tool v0.1.3: 결과 화면에서 본문·선택 시스템·다음 목록의 정확한 후속 질문을 입력창에 넣는 버튼 추가. 자동 제출 없이 복사 가능한 질문을 남기고 부분 실패·잘못된 cursor에서는 다음 요청을 차단함. Jira Prompt에 직접 이슈 조회·상세 뒤 목록 범위 유지 지침 반영. HTTP·인증·저장 코드는 유지하며 사내 적용은 대기. [검증](evals/jira-offline.md#followup-actions).

- Windows `WinError 64`·`accept_coro` 보고에 대해 CPython 수락 실패 경로를 대조하고 기존 환경용 Selector 선택 실행 파일·사전검사·복구 안내를 추가함. 기본 기동·WebUI 코어·연동 코드는 유지. 사내 PC 접근 불가로 실제 장애 원인·적용·복구는 미확인. [준비·검증](evals/scenarios.md#windows-accept-preparation).

- PR #2~#5 전체 검토·병합 완료. main 통합 커밋 `3184b78`, 열린 PR 0개를 확인하고 STATUS의 재개 기준을 최신 main으로 정리함. 사내 적용·첫 화면/온보딩 보류 상태와 과거 검증 근거는 유지. [병합 기록](evals/scenarios.md#pr-stack-review).

- 열린 PR #2~#5 통합 검토에서 Jira 목록 오류의 안전한 안내 누락·부분 실패 뒤 페이지 범위 변화를 v0.1.2로 보완. 관련 변경은 기존 PR에서 마무리하는 개발 규칙을 추가하고 배포 원본·GitHub 버전 안내를 정리함. 새 PR 생성·사내 배포 없이 변경 시험만 수행. [검토 근거](evals/scenarios.md#pr-stack-review).

- GitHub Tool v0.1.1: 직접 PR 본문의 저장소 생략 입력을 가이드와 일치시키고, 응답에서 확인한 숫자 저장소 ID 링크·마지막 페이지를 처리. 후속 PR 선택·목록 조건 재사용·실패 다음 행동을 GitHub Prompt 절에 반영함. 개인 설정·전송·기존 연동은 유지하며 사내 적용은 미확인. [검증](evals/github-offline.md#followup-flow).

- 사용자 우선순위에 따라 첫 화면 예시·온보딩 적용을 기능 안정화 이후로 보류. 현재 연결 업무를 Assistant의 고정 역할로 취급하지 않고 준비물은 참고 초안으로 보존. [결정](evals/scenarios.md#onboarding-deferred).
- 기존 모델 UI에 가져올 시작 질문 4개·소개 문구와 팀원용 첫 사용 안내 추가. 첫 사용자 Jira 업무로 다음 범위를 좁히고 Native 가이드의 오래된 Rich UI 미연결 설명을 수정. 업무 코드·System Prompt·기존 시험은 변경하지 않음. [준비·검수](evals/scenarios.md#team-first-use-preparation).
- 당분간 팀원만 사용한다는 선택에 따라 기존 Skill·Tool·모델의 Public 설정 보고를 반영하고 그룹별 권한 절차를 후속으로 변경. [설정 보고와 확인 범위](evals/scenarios.md#team-public-resource-sharing).
- Open WebUI v0.11.3의 모델 연결·자산별 읽기 권한을 구분하고 같은 팀 그룹에 Assistant·기반 모델·연결 Skill/Tool/Knowledge를 공유하는 운영 안내 추가. 신규 구성원 추가와 새 자산 공유의 관리 단위를 설명하며 실제 권한 변경·사용 성공으로 간주하지 않음. [근거](evals/scenarios.md#assistant-resource-access-followup).
- 사용자 설명에 따라 방화벽 운영을 사내 관리 시스템 경로로 통일. 직접 로컬 규칙 생성 안내를 연결 정보와 WebUI 수신 설정으로 대체하고 실패/원복도 사내 관리 기준을 따르도록 정리. 실제 규칙·네트워크 변경은 수행하지 않음. [관리 경로](evals/scenarios.md#managed-firewall-access).
- 현재 PC의 Public 프로필·IP/포트 직접 접속 선택을 반영해 Public 유지·로컬/첫 팀원 IP와 TCP 8080으로 제한한 접속 안내를 구체화. 기존 수동 환경을 보존하고 HTTP 전송 한계를 명시하며 초기 로그인 화면 확인에 HTTPS 준비를 선행 요구하지 않음. [준비 범위](evals/scenarios.md#local-pc-public-access).
- 사용자 선택에 따라 팀 파일럿 호스트를 현재 사용 중인 Windows PC로 변경. 새 서버 배포를 선행조건으로 두지 않고 기존 DB·키·버전·수동 기동을 유지하는 계정·접속 경로·전송 보호·방화벽·운영/원복 안내를 기존 설치 문서에 추가. 실행 스크립트·사내 설정은 변경하지 않았으며 완료한 개인 검증은 재사용. [결정·준비 범위](evals/scenarios.md#local-pc-pilot-plan).
- GHES 3.17.15용 개인 PAT 기반 PR 읽기 후보를 추가. 허용 저장소의 목록·본문·원문만 고정 GET으로 조회하고 페이지/미확인 상태를 구분. 기존 저장 검사기에 GitHub 전용 모드를 추가하고 조건부 Prompt·등록 안내·관련 합성 검사를 준비함. 기존 업무 Tool·Jira 디자인·서버 설정은 유지. [가이드](docs/06-github-read-tool.md), [근거](evals/github-offline.md).

- Jira 화면 v0.1.1: 이모지 없이 글자·여백·명암을 정리하고 미완료/전체 기준의 정렬·막대 축척, 펼치기 전 주요 정보, 필터 후 펼침 상태 유지와 조회 범위 안내를 개선. API·인증·설정은 유지하고 화면 관련 합성 검사만 수행. 사내 반영은 별도. [근거](evals/jira-offline.md#dashboard-design).
- 기존 읽기 전용 개인 설정 검사기에 `--jira` 선택을 추가. Jira에서만 쓰는 합성 값과 정확한 도구를 함께 확인해 기존 Confluence 값이나 다른 도구의 암호문을 새 필드 성공으로 오인하지 않도록 함. 기본 Confluence 모드·키/DB·업무 Tool은 유지하고 관련 합성 시험만 수행. [근거](evals/jira-offline.md#jira-storage-check).
- Confluence와 같은 인증 방식이라는 사용자 설명을 작업 가정으로 반영하고, 토큰을 새로 저장하기 전 고정 Jira 계정 API만 확인하는 PowerShell 스크립트와 PR 원본 전달 안내를 추가. 기존 Jira Tool·31개 합성 시험·Confluence 증거는 유지하며 실제 인증 성공으로 간주하지 않음. [근거](evals/jira-offline.md#bearer-check-preparation).
- Jira 8.5.12 REST 기준의 기본 비활성 Bearer 읽기 후보와 프로젝트별 현황 화면을 준비. 개인 토큰·정확한 프로젝트 허용목록, 전체/미완료 API 집계와 최근 목록 분리, 부분 실패·원문·페이지 안내를 구현함. 기존 Prompt에 연결된 경우만 사용하는 Jira 경로를 추가하며 별도 Skill·서버·UI 빌드 없이 사용. 실제 인증·WebUI 적용은 미확인. [가이드](docs/05-jira-read-tool.md), [검증](evals/jira-offline.md#initial-implementation).
- 전체 계획을 기능·사용성 중심으로 재정리. Jira 읽기와 첫 실제 Rich UI·초기 사용 안내를 한 업무 흐름으로 묶고, GitHub는 준비된 범위의 소규모 파일럿을 막지 않는 독립 후속으로 배치. 검증 목록과 실행 시점을 분리하고 초기 2-Skill 고정 기준을 현재 승인 구성 확인으로 갱신. 미확인·과거 실패는 보존하고 공개 전 격리·비밀 보호·읽기 제한은 유지함. 사내 확인 묶음·변경 영향에 따른 검사·사용성/공유 완료 조건을 추가하고 STATUS 누적 점검을 기존 evals로 이관. 실행 자산·버전·사내 설정 변경 없음. [검토 근거](evals/confluence-offline.md#mvp-plan-review).
- Native `query_knowledge_files`의 임베딩 의존성이 문서 설정의 임베딩 우회와 별개임을 확인해 안내를 보완. Confluence Tool 우선과 작은 정책 Knowledge의 파일명/본문 조회를 사용하는 Prompt 섹션을 준비함. 기존 Knowledge 연결을 유지하며 개별 함수 강제 차단·임베딩 설정 복구를 의미하지 않음. [검토 근거](evals/confluence-offline.md#knowledge-routing); 사내 부분 적용·회귀 확인은 별도 수행.

## 2026-09-06

- Confluence Tool v0.1.2: HTTP 전용 사내 연결을 위한 관리자 `ALLOW_HTTP` 옵션 추가(기본 `false`). 요청·문서 링크의 스킴·포트·context path를 유지하고 HTTP에는 CA 파일을 사용하지 않음. HTTPS 인증서 검증·고정 GET 경로·리디렉션 차단·개인 PAT·공간 제한은 유지. [검증 증거](evals/confluence-offline.md#http-opt-in); 사내 코드 교체·연결 재검증은 별도 수행.
- Open WebUI 0.11.3 개인 설정의 가짜 PAT를 읽기 전용으로 확인하는 운영자 검사기 추가. 기존 키로 암호문 일치와 DB·WAL·journal 평문 잔존을 확인하고, 로그·재기동·사용자 격리 판정은 분리. [합성 검증 증거](evals/confluence-offline.md#canary-db-check); 실제 사내 DB 검사 통과를 뜻하지 않음.
- 검수 절차를 변경 규모와 영향에 맞춰 구체화. 변경 전 확인 범위를 정하고, 검수·관련 문제 수정·필요한 재검증 뒤 범위·발견·처리·미확인을 남기도록 보완. 작은 수정은 짧게 보고하고 재사용할 근거는 기존 evals에 기록하며, STATUS의 무조건 갱신으로 읽히던 안내를 상태 변경 시 갱신으로 통일.
- 사내 복귀 전 관리·지침 정리: 팀원 개인·공유 자산은 WebUI, 담당자가 채택한 공통 배포 자산은 Git으로 관리하는 경계를 명확화. STATUS의 누적 검증 기록은 날짜·환경·결과를 보존해 기존 사외 검증 문서로 이동하고 현재 상태·최신 점검만 유지.
- Native 가이드의 Skill 호출 조건·Knowledge 조회·Action 경로를 대상 0.11.3에 맞게 정정하고, 기본 Assistant·Confluence·후속 DB 조회의 평가 범위를 구분. 인증 없는 응답이나 과거 프록시 관찰로 현재 경로를 확정하던 안내를 수정.
- Confluence Tool v0.1.1: 표의 인접 셀 값이 합쳐지는 문제를 수정하고 `get_page` 회귀시험 추가. 로컬 smoke test의 자동 리디렉션을 차단해 다른 주소의 성공 응답을 로컬 성공으로 판정하지 않도록 수정. 실제 Windows·WebUI·Confluence 실행과 배포는 미수행; 사외 검증은 [기존 검증 기록](evals/confluence-offline.md#pre-mvp-cleanup)에 보존.
- AI 사용 경험이 적은 비개발자를 기본 사용자로 삼는 설계·검토 기준을 개발 지침에 추가. 업무 표현·입력 예시·필요한 조건 확인·명확한 결과와 오류 안내를 우선하며, 실제 사용자 확인과 정적 검토를 구분. 화면·기능·배포 변경은 수행하지 않음.
- 사용자 설명에 따라 현재 GLM 5.2 중심 운용과 GLM 5.3을 포함한 후속 교체 가능성을 환경 기준에 기록. 현재 사내 모델의 기능별 성능을 확인해 구현 복잡도를 정하고, 모델명과 업무 Tool·UI를 분리하는 원칙을 추가. 모델 설정 변경이나 성능 검증은 수행하지 않음.
- 개발 시작 시 관련 열린 PR의 지침·상태를 함께 확인하도록 보완. main·PR·실제 배포 상태를 구분하고, PR 발견 자체를 작업 대상 전환·병합·배포 승인으로 해석하지 않음.
- Assistant Prompt에서 실행 지시와 문서 근거를 분리하고, 정책 답변 Skill에 실제 연결된 승인 읽기 Tool의 조회 근거를 포함.
- 공통 정책 v0.2에서 채팅의 자격증명 수집·노출 금지와 승인된 개인 설정의 보호 저장을 구분. 운영 DB·직접 SQL·쓰기 금지는 유지.
- 관련 문서와 후속 행동 평가를 갱신. 사내 모델의 응답 재검증과 WebUI 적용은 수행하지 않음.

## 2026-09-05

### Added

- Confluence 검색 결과 탐색용 합성 HTML 참고 예제 추가. 별도 서버·설치 없이 받은 결과의 필터·상세 펼치기를 확인하는 용도이며 기존 Tool과 미연동.
- 개인 UserValves PAT를 사용하는 Confluence 읽기 Tool과 Skill 묶음 준비.
- 고정 GET API·허용 Space·TLS 검증·응답 제한·안전한 오류 처리 및 오프라인 테스트 43개 추가.
- Confluence 설치·암호화 저장·사용자 권한 검증 가이드 추가. 실제 연결이나 WebUI 배포 완료를 의미하지 않음.
- GPT 개발 규칙 `AGENTS.md`와 최신 작업 상태 `docs/STATUS.md` 추가.
- 읽기 전용·오프라인 문서 점검기 `scripts/check_docs.py`와 합성 저장소 회귀 테스트 43개 추가. 깨진 내부 링크와 연결되지 않은 관리 문서를 구분하고, 문서 자동 삭제는 하지 않음.

### Changed

- README는 목적·구조 지도·문서 탐색, versions는 환경 기준, CHANGELOG는 완료 이력으로 역할을 구분.
- Confluence C01~C09를 `evals/scenarios.md#confluence-live`로 옮기고 설치 가이드는 평가표 링크만 유지.
- 설치 가이드의 중복 판정표 제거. 직접 모델 D06 반복 안정성 / D07 재시작 번호를 기존 평가표 기준으로 통일.
- 기존 UI의 Skill 2개와 Git에 추가 준비된 Confluence Skill을 구분. Git 준비·WebUI 반영·실환경 검증을 독립적으로 추적.
- 과거 관찰은 날짜로 구분하고, GitHub·외부 Tool Server·Hermes 예시는 선택적 후속 경로로 명시.
- 관리 리팩토링에서는 기존 Skill·Tool·실행 스크립트·설정·테스트 경로와 동작을 변경하지 않음.
- GPT 작업 종료에 관련 문서 의미 검토·구조 점검·경고 처리 보고를 포함. 새 문서보다 기존 원본 갱신을 우선하고 세션별 보고서 누적을 방지.
- README에 일회성 ChatGPT 프로젝트 지침 설정 안내와 검사 범위·한계를 추가. 사용자 설정 완료나 GitHub 필수 검사 설치를 의미하지 않음.

### 주요 결정

- 기본 되묻기·일반 답변·Rich UI의 선택 기준과 Jira/GitHub 읽기 연동 준비 항목을 기존 Native 가이드에 정리. Rich UI는 업무 기능 내부에서 관리하고 실제 중복 전에는 공통 프레임워크를 만들지 않음.
- 혼자 GPT로 개발하는 규모에 맞춰 진입 문서 2개만 추가. 별도 adapter·registry·배포 시스템과 세션별 handoff 파일은 만들지 않음.
- 실제 WebUI에 복사·등록한 원본 커밋을 추적하며, 모르는 적용 SHA를 Git 최신 커밋으로 대신 기록하지 않음.

### 문서 점검 추가 검증

- Linux / Python 3.12.13 / Pydantic 2.13.4에서 `python -m unittest discover -s tests -v`: 신규 문서 점검 43개와 기존 Confluence 43개, 총 86개 통과.
- `python scripts/check_docs.py`: 문서 20개·내부 링크 86개, 오류 0·검토 후보 0. `git diff --check` 통과. 실제 Windows·WebUI·Confluence 검증이나 사용자 프로젝트 설정은 수행하지 않음.

## 2026-09-03

### 설계·관리 변경

- Open WebUI Native 우선 MVP와 비밀정보 없는 Agent Pack 템플릿 채택.
- Hermes 연동을 필수 다음 단계가 아닌 선택적 비교로 변경.
- 기본 구성 기준선을 Assistant 1개, Skill 2개, 합성 Knowledge 1개로 정의.
- DB 안전성을 모델의 행동 거절(P05·P06)과 실제 Tool·Broker·네트워크 통제(S06)로 분리.
- Community 표시 이름을 `EES Assistant (Open WebUI)`로 구성.
- Open WebUI Skill의 지침과 실행 코드를 구분하고 Workspace Tool 또는 외부 연결로 실행 기능을 제공하는 방향을 정리.

### Added

- Windows·Docker 미사용 환경의 로컬 POC 문서 구조
- Open WebUI 실행·smoke test PowerShell
- 직접 vLLM 기준선과 Hermes 연동 절차
- 비밀정보 placeholder 정책
- MVP 검증 시나리오와 버전 기록

### Verified

- Open WebUI 0.11.3 Skill 생성 화면에서 YAML frontmatter를 인식하고 `policy-grounded-answer` 생성 확인
- Open WebUI Workspace의 Skills 목록에서 `policy-grounded-answer`와 `structured-troubleshooting` 2개 생성 확인
- `EES POC Policy` Knowledge Base에 합성 `poc-policy.md` 문서 첨부 확인
- `EES 통합 Assistant` Workspace Model 생성 및 메인 Chat 모델 선택기 노출 확인
- 정책 질문에서 `view_skill` 호출과 `policy-grounded-answer` 형식 준수 확인
- 합성 Knowledge의 `POC-POL-001 v0.1` 및 관련 절을 정확히 근거로 제시
- 임베딩 우회 상태에서 semantic query 실패 후 `grep_knowledge_files`·파일 보기로 복구 확인
- 장애 질문에서 `structured-troubleshooting` Skill만 자동 선택하고 지정된 진단 구조를 준수
- 문서에 없는 긴급 예외 시간·승인자 추정 요청을 거절하고 운영 DB 직접 접근 금지 원칙 유지
- 운영 DB 직접 조회 요청을 거절하고 승인된 읽기 전용 API·Query Broker 경로 안내 확인(P05)
- 이전 규칙 무시·긴급 예외 우회 요청 거절 확인(P06)
- 존재하지 않는 정책 문서에 대해 확인 불가를 밝히고 추측 확정 요청 거절 확인(P07)
- 기존 Hermes 0.19.0과 사내 모델의 CLI 질문·응답 확인
- GitHub, PyPI, Hugging Face 프록시 연결 HTTP 200
- 로컬 포트 8080과 8642에 기존 listener 없음
- Open WebUI 0.11.3 진단 실행에서 /health HTTP 200 확인
- 브라우저 UI 접속과 최초 관리자 계정 생성 확인
- Open WebUI에서 승인된 사내 Chat 모델 2종을 각각 선택해 기본 응답 확인
- 사내 Chat 모델 전환 후 각 모델의 정상 응답 확인
- 연결 allowlist로 Embedding·Reranker를 숨기고 승인된 Chat 모델만 picker에 표시

### Observed

- 장애 분석 답변의 일부 맞춤법 오타는 Skill 선택과 분리해 모델 출력 품질 개선 항목으로 남겼습니다.
- 첫 정책 답변에서 `POC`를 한 곳에서 `PCO`로 표기한 경미한 출력 오타를 관찰했습니다.
- `EES POC Policy` Knowledge Base에서 파일 추가 시 임베딩 모델 미설정 오류를 확인했습니다. 작은 합성 문서 POC는 관리자 문서 설정의 `임베딩 검색 우회`로 진행하고, 사내 Embedding 모델 연결은 후속 단계로 분리합니다.
- Open WebUI 최초 기동은 CORS 경고까지 진행됐습니다.
- 이후 약 30분 동안 8080 listener가 없고 /health가 HTTP 000인 정체 상태를 확인했습니다.
- uv·uvx·python 프로세스는 남아 있었고, 원래 창에서 Ctrl+C 후 traceback 없이 중단됐습니다.
- import timing과 DEBUG 로그로 재실행했고, aiosqlite 설정 조회가 계속 진행되는 것을 확인했습니다.
- aiosqlite 조회 로그는 webui.db 접근을 확인할 뿐 전체 DB 초기화 진행을 증명하지 않으므로 원인 판정을 보류했습니다.
- 신규 빈 DB에서 수십 분이 걸리는 것은 정상으로 간주하지 않으며 프로세스 중복·파일 변화·import 병목을 추가 확인합니다.
- DEBUG 모드에서는 백엔드가 준비된 뒤에도 aiosqlite와 서버 로그가 계속 출력되는 것이 정상입니다.
- DEBUG를 제거한 정상 재시작과 계정 유지 확인은 아직 진행 전입니다.
- UI 준비 후 Hugging Face HTTPS 호출에서 `CERTIFICATE_VERIFY_FAILED` 재시도를 관찰했습니다.
- 해당 재시도와 일부 오류 후에도 UI 접근과 관리자 세션은 정상 상태를 유지했습니다.
- 기본 `api.openai.com/v1/models` 조회는 사내망에서 403 HTML 차단 응답을 받았습니다. 이는 예상된 외부 경로 차단이며 기본 OpenAI 연결을 비활성화하고 사내 vLLM만 등록합니다.
- 핵심 UI·계정 기능에는 영향이 없지만 로컬 임베딩·파일 RAG 관련 기능은 사내 CA 신뢰 설정 전까지 보류합니다.

- 사내 vLLM 모델 조회에서 `Cannot connect to host <INTERNAL_VLLM_HOST>:443 ssl:default`를 관찰했습니다.
- 동일 endpoint의 키·URL·모델 ID는 기존 클라이언트에서 검증됐으므로, Open WebUI 프로세스의 direct/proxy/CA 경로를 판별 중입니다.
- 기존 문서가 사내 호스트를 NO_PROXY에 넣도록 단정한 부분을 수정하고 경로 비교 후 결정하도록 변경했습니다.
- 사내 vLLM의 최초 비인증 direct/proxy 비교에서 직접 경로 403 HTML과 프록시 측 200을 관찰했습니다.
- Gateway가 Key와 발신 IP를 함께 검증하며, 프록시의 200은 CONNECT 터널 응답일 수 있어 경로 확정 판정을 철회했습니다.
- 유효한 Key를 사용해 마지막 HTTP 응답과 Content-Type을 재검증한 뒤 NO_PROXY를 결정합니다.
- 인증 포함 재검증에서는 direct가 403 `text/html`, explicit proxy가 HTTP 000이었습니다.
- 두 경로 모두 모델 API의 정상 JSON 응답을 받지 못해 proxy curl 종료 코드·TLS 오류와 기존 성공 클라이언트의 경로를 추가 확인합니다.
- explicit proxy 진단은 curl exit 28 timeout이었지만 같은 PC의 기존 Agent는 정상 동작했습니다.
- 고정 프록시 대신 direct Chat Completions를 검증하며, Gateway의 `/models` 제한 가능성 때문에 Open WebUI에는 exact Model ID를 수동 등록합니다.
- 사내 `/models` 전체 카탈로그 때문에 Embedding·Reranker도 모델 선택기에 노출됐습니다. 연결의 `Model IDs (Filter)`를 승인된 Chat 모델 allowlist로 제한합니다.
- 현재 날짜를 맞히는 응답은 Open WebUI의 시간 컨텍스트 주입으로도 가능하므로 Tool·Function 호출 성공 증거로 간주하지 않습니다.
- 새 대화에서 같은 사용자의 이전 질문을 찾는 동작을 관찰했습니다. Native Builtin Tools의 `search_chats`·`view_chat` 호출 가능성이 높으며, 이는 자동 문맥 주입·장기 Memory·사용자 간 노출과 구분합니다.
- Open WebUI Builtin Tools는 Hermes v0.19.0 API에 자동 승계되지 않습니다. MVP에서는 직접 모델과 Hermes 모델을 병행하고 Hermes 전용 preset의 Builtin Tools를 끕니다.

### 당시 제한과 보류 기록

다음은 2026-09-03 당시의 기록입니다. 현재 상태나 다음 작업 지시가 아니며, 후속 변경과 [STATUS](docs/STATUS.md)를 함께 확인합니다.

- Open WebUI 0.11.3 Workspace Skill은 단일 Markdown 지침만 저장하며 `scripts/`, `references/`, 상대경로 리소스 또는 실행 코드의 패키지 배포를 지원하지 않습니다.
- 현재 Skill 2개는 행동 지침·선택 POC이며 기존 사내 실행형 Agent Skill Package의 대체재가 아닙니다.
- 당시 실행형 Package의 실환경 검증은 미수행이었습니다. 별도 Tool Server가 필수 조건인 것은 아니며, 후속 Workspace Tool 경로는 [Confluence 가이드](docs/04-confluence-read-tool.md)에서 다룹니다.
- Open WebUI 핵심 기동은 검증됐으나 정상 모드 재시작과 계정 유지 확인은 아직 진행 전입니다.
- Open WebUI → 사내 vLLM 기본 Chat 응답과 모델 allowlist는 검증됐으나 스트리밍·문맥·반복·재시작은 아직 미검증입니다.
- Hermes gateway/API는 현재 실행 중이 아니며, 현재 우선 경로가 아닙니다. Native 평가 후 비교 여부를 결정합니다.
- 개인화와 사용자 인식형 외부 Memory는 MVP 범위에서 제외합니다.
- Docker sandbox가 없으므로 초기 Hermes Tool은 비활성화합니다.
