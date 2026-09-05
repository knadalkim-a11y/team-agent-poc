# 현재 작업 상태

갱신일: 2026-09-05

이 파일은 새 GPT 세션의 짧은 인계 지점입니다. 기능별 판정 원본은 [평가표](../evals/scenarios.md), 환경 기준은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)에 둡니다. 아래 요약이 증거와 충돌하면 단정하지 말고 증거를 확인합니다.

## 목표와 이번 작업

- 목표: 비개발자가 Open WebUI의 `EES 통합 Assistant`에서 사내 LLM·팀 지침·읽기 기능을 쓰는 POC.
- 현재 경로: Open WebUI Native. Windows·Docker 미사용이며, 사내 PC 밖에서 코드·문서 준비만 할 수 있는 상황.
- 이번 작업: Confluence 검색 결과용 합성 Rich UI 참고 예제와 되묻기·화면 선택 기준, Jira/GitHub 후속 연동 준비 항목을 추가. 기존 Skill·Python Tool·서비스 실행 스크립트·설정은 유지.
- 다음 작업 하나: 사내 복귀 후 **Confluence 제품·버전과 개인 PAT 인증 방식을 확인**한다. [설치 안내](04-confluence-read-tool.md)의 제품 확인부터 시작하며, 현재 Tool은 Data Center PAT/Bearer용 초안이다.
- 후속 순서: Confluence 읽기 MVP 검증 → Jira 읽기 연동 → GitHub 읽기 연동. 각 연동 전에 [제품·인증·조회 범위](03-openwebui-native-agent.md#rich-ui)를 확인하고, Rich UI는 실제 사용사례가 정해질 때 적용한다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool, 원본 [0cb6096](https://github.com/knadalkim-a11y/team-agent-poc/commit/0cb60962c44c2d0b59c4cb028faf2030161699f5) | 반영 확인 없음 | [사외 자동 시험 증거](../evals/confluence-offline.md), [실환경 C01~C09](../evals/scenarios.md#confluence-live) | 미확인 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | 아래 사전 준비 검증; 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션 | 이 저장소 스크립트로 기동한 사실과 적용 SHA는 미확인 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |

**Git에는 Skill 3개가 있고, 기존 UI에서 생성·사용을 확인한 것은 2개입니다.** Confluence 코드가 Git에 존재한다고 설치·활성화됐다고 판단하지 않습니다. 적용 커밋은 저장소의 최신 커밋이 아니라 실제로 복사·등록한 원본을 적습니다.

## 남아 있는 검증과 제한

- 사내 연결·저장 암호화·두 사용자 권한 확인은 [C01~C09](../evals/scenarios.md#confluence-live)의 판정으로 관리합니다. 실제 PAT를 넣기 전에 가짜 값으로 암호화 저장·키 유지부터 확인합니다.
- Open WebUI 재시작·스트리밍·문맥·반복 안정성·데이터 위치·사용자 격리의 미확인 항목은 [전체 평가표](../evals/scenarios.md)를 따릅니다. 기존 UI 성공이나 mock 테스트로 미확인 항목을 PASS 처리하지 않습니다.
- 사내 프록시·CA·네트워크 경로는 환경별 확인 대상입니다. 과거 HTTP 200 또는 연결 오류를 현재 경로의 확정 근거로 재사용하지 않습니다.
- 개인 Memory·위험 Tool은 초기 구성에서 제외합니다. 운영 DB 직접 연결·범용 SQL·Shell·쓰기 기능을 추가하지 않습니다.
- 기존 Hermes 설치·사내 모델 Q/A 확인 이력은 유지하되, WebUI↔Hermes 연동·재설치는 보류합니다. 실제 Native 한계가 확인될 때만 비교합니다.
- Router·A2A·EMS/APC 자동 라우팅·자동 배포·개인화·서버 이전은 후속 범위입니다. 사용자 PC 공개나 외부 서비스 추가를 이번 준비 작업에 포함하지 않습니다.
- 사용자 일회성 설정: README의 [GPT 프로젝트 최초 설정](../README.md#gpt-프로젝트-최초-설정)에 따라 지침을 넣고 새 프로젝트를 만들었다는 사용자 보고를 확인했습니다. 동일한 설정을 다시 요청하지 않습니다. 앱 설정 화면을 직접 검사한 것은 아닙니다.

## 이번 사전 준비 검증 — 2026-09-05

- 환경: Linux / Python 3.12.13 / Node.js. 실제 사내 데이터·인증·네트워크 호출 없는 합성 HTML 참고 예제만 추가.
- HTML 구조·ID·label과 외부 리소스 없음 확인, 추출 JavaScript의 `node --check` 통과. DOM 대체 객체로 초기 6개, 제목·공간 필터, 빈 결과, 초기화, 본문·비활성 원문 버튼, iframe 높이 메시지를 확인.
- `python scripts/check_docs.py`: Markdown 20개, 내부 링크 95개, 오류 0·검토 후보 0. `git diff --check` 통과. 이후 프로젝트 지침 설정 완료에 대한 사용자 보고를 반영하고 두 점검을 다시 통과함.
- 기존 Python Tool·Skill·Prompt·설정·테스트는 변경하지 않았고 Python 전체 테스트는 이번에 재실행하지 않음. 아래 86개 통과는 이전 실행 기록.
- 실제 브라우저 레이아웃·Windows·Open WebUI 렌더링·Confluence·Jira·GitHub 연결 및 배포는 미실행. 새 서버·공통 프레임워크·추가 업무 Skill은 만들지 않음.

## 이전 문서 점검기 추가 검증 — 2026-09-05

- 환경: 2026-09-05, Linux / Python 3.12.13 / Pydantic 2.13.4. 네트워크 호출을 막은 합성 문서·mock API 시험이며 사내 실환경 검증이 아님.
- `python -m unittest discover -s tests -v`: 문서 점검 43개 + 기존 Confluence 43개, 총 86개 통과. 파일 bytes·mtime 보존, 코드 예시 제외, 경로 이탈·심볼릭 링크·합성 resolve 경계, CLI 출력·종료 코드를 확인.
- `python scripts/check_docs.py`: Markdown 20개, 내부 링크 86개, 오류 0·검토 후보 0. `git diff --check` 통과. 문서 내용 전체의 최신성이나 실사용 여부를 보장하는 결과는 아님.
- 신규 파일은 점검기와 테스트 두 개. 문서 삭제·새 보고서 파일·스케줄러·필수 CI는 추가하지 않음. 이전 [관리 리팩토링 증거](../evals/confluence-offline.md#management-refactor)는 당시 기록으로 보존.
- 실제 Windows 실행·Confluence·WebUI 배포: 수행하지 않음.

원격 게시 여부는 해당 Git 커밋으로 확인합니다. 문서 게시를 WebUI 배포 완료로 해석하지 않습니다.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때만 이 파일을 갱신합니다. 시험별 상태표와 과거 세션 전문은 붙이지 말고 증거에 연결합니다. 새 기능의 원본·배포·실환경 검증을 서로 다른 상태로 기록합니다.
