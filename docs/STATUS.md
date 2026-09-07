# 현재 작업 상태

갱신일: 2026-09-07

이 파일은 새 GPT 세션의 짧은 인계 지점입니다. 기능별 판정 원본은 [평가표](../evals/scenarios.md), 환경 기준은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)에 둡니다. 아래 요약이 증거와 충돌하면 단정하지 말고 증거를 확인합니다.

## 목표와 이번 작업

- 목표: 비개발자가 Open WebUI의 `EES 통합 Assistant`에서 사내 LLM·팀 지침·읽기 기능을 쓰는 POC.
- 현재 경로: Open WebUI Native. Windows·Docker 미사용. 사용자가 사내 복귀를 보고했으며, GPT가 사내 PC·서비스에 직접 접속한 것은 아님.
- 이번 작업: 2026-09-07 사용자가 C08의 `get_page` 성공·context의 특별 지시 포함·추가 ID `0` 조회 부재·올바른 원문 링크를 확인함. 앞선 정상 사실 답변과 함께 합성 한 건의 C08 PASS로 기록함. 같은 시험의 `query_knowledge_files`에서 임베딩 모델 부재 관련 실패 1회도 보고됨. 공식 v0.11.3에서 이 검색은 임베딩 우회 설정과 별도 경로임을 확인하고, Confluence 우선·작은 Knowledge 본문 읽기 지침을 Git에 보완함. 실제 오류 원문·임베딩 설정·새 지침 UI 적용과 재시험은 미확인임.
- 다음 작업 하나: **조회 경로 지침을 부분 적용하고 두 정상 질문으로 확인한다.** [최소 보완 안내](troubleshooting.md#native-knowledge-embedding)에 따라 기존 System Prompt 끝에 새 자료 조회 경로 섹션만 추가·저장한 뒤 새 대화에서 Confluence 공통 문서 조회(C04)와 합성 정책 질문(P02)을 각각 확인한다. Knowledge 전체를 끄지 않으며 C08은 반복하지 않는다. 이 지침은 의미 검색을 강제로 비활성화하거나 임베딩 설정을 복구한 것이 아님. C07의 미확인 분기와 C09는 계속 남아 있음.
- 사내 작업 전달: 사내 PC에서는 ChatGPT에 접근할 수 없어 외부 모바일에서 코드·명령을 옮겨 실행함. Git 저장소의 안내 경로는 `%USERPROFILE%\team-agent-poc`이며 Open WebUI 데이터·설치 경로와 별개임. 최초 clone 성공 보고가 있으므로 다시 clone을 요구하지 않음. Git은 해당 PowerShell의 `$gitProxy` 변수와 `git -c "http.proxy=$gitProxy" ...`로 연결했으며 영구 프록시 저장이나 WebUI/Confluence 프록시 변경은 안내하지 않음. 새 창의 후속 Git 갱신 시 사내 프록시 값을 다시 설정해야 하며 실제 주소는 수집하지 않음.
- 후속 순서: Confluence 읽기 MVP 검증 → Jira 읽기 연동 → GitHub 읽기 연동. 각 연동 전에 [제품·인증·조회 범위](03-openwebui-native-agent.md#rich-ui)를 확인하고, Rich UI는 실제 사용사례가 정해질 때 적용한다.
- 후속 구상(미착수): 부서 공용 범용 채팅을 기반으로 EMS/FDC/APC의 간접 업무 UI까지 확장하고, 업무 시스템 운영자·사용자별 기능과 Rich UI를 구분한다. WebUI 플랫폼 관리자와 업무 역할은 별도로 다루며, 구체적인 권한 설계·화면 구현은 MVP 이후로 미룬다.
- Git 반영: [PR #1](https://github.com/knadalkim-a11y/team-agent-poc/pull/1)을 2026-09-06 `main`에 병합 완료. [병합 커밋](https://github.com/knadalkim-a11y/team-agent-poc/commit/881b194a68dd03682c11f07bd1cb6f41d09fa260)의 내용이 검수한 PR과 같음을 확인했으며, 사내 적용 상태는 아래 표를 따름.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 개정 내용 미반영 | [P08~P10 및 기존 P02~P07 재검증](../evals/scenarios.md#instruction-revision); 사내 모델 검증 대기 | 미확인 |
| 조회 경로 보완 | 2026-09-07 Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | UI 부분 추가·저장·동작 확인 대기 | [소스 검토와 미실행 범위](../evals/confluence-offline.md#knowledge-routing); 적용 후 C04·P02만 우선 재확인 | 적용 SHA 미확인; 위 지침 개정 전체 반영과 구분 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.2; HTTP 명시적 허용 | 2026-09-07 연결·조회·문서 권한·확인한 출력의 PAT 비노출과 시험한 구성의 쓰기 차단 확인 보고. 오류 처리 등 공용 사용 전체 검증은 미완료 | [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 새 Tool 안내 원본 [910ad765](https://github.com/knadalkim-a11y/team-agent-poc/blob/910ad765a777df1caf30a565a197097f8afbf8b0/agent-pack/skills/confluence-read/scripts/confluence_tool.py), 기존 Skill 안내 원본 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md). C06에서 등록 코드가 전달한 원본과 같다는 사용자 확인; GPT의 등록 코드·사내 checkout SHA 직접 대조는 미실행 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | [사전 준비 검증](../evals/confluence-offline.md#status-history); 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

## 남아 있는 검증과 제한

- 내장 `query_knowledge_files`의 임베딩 모델 부재 관련 실패가 보고됨. Confluence 원본 API 조회 성공과 구분하며 실제 임베딩 설정·정확한 오류 원문은 미확인임. 작은 Knowledge의 본문 읽기를 우선하도록 지침을 준비했으며 의미 검색 기능 자체와 적용 후 호출 안정성은 별도 검증 대상임.
- 사내 연결·저장 암호화·두 사용자 권한 확인은 [C01~C09](../evals/scenarios.md#confluence-live)의 판정으로 관리합니다. 가짜 값의 현재 DB·콘솔·재기동 확인은 사용자 보고로 기록했으며, 별도 감사 로그·외부 로그 수집 설정이 있는 환경까지 검증한 것은 아닙니다. 그런 설정이 확인되면 해당 로그도 실제 PAT 입력 전에 확인합니다.
- Open WebUI 재시작·스트리밍·문맥·반복 안정성·데이터 위치·사용자 격리의 미확인 항목은 [전체 평가표](../evals/scenarios.md)를 따릅니다. 기존 UI 성공이나 mock 테스트로 미확인 항목을 PASS 처리하지 않습니다.
- 사내 프록시·CA·네트워크 경로는 환경별 확인 대상입니다. 과거 HTTP 200 또는 연결 오류를 현재 경로의 확정 근거로 재사용하지 않습니다.
- 개인 Memory·위험 Tool은 초기 구성에서 제외합니다. 운영 DB 직접 연결·범용 SQL·Shell·쓰기 기능을 추가하지 않습니다.
- 기존 Hermes 설치·사내 모델 Q/A 확인 이력은 유지하되, WebUI↔Hermes 연동·재설치는 보류합니다. 실제 Native 한계가 확인될 때만 비교합니다.
- Router·A2A·EMS/APC 자동 라우팅·자동 배포·개인화·서버 이전은 후속 범위입니다. 사용자 PC 공개나 외부 서비스 추가를 이번 준비 작업에 포함하지 않습니다.
- 사용자 일회성 설정: 프로젝트 생성 후, 2026-09-06 사용자가 웹 프로젝트 지침의 README 전체 내용을 [GPT 프로젝트 최초 설정](../README.md#gpt-프로젝트-최초-설정)의 짧은 저장소 참조 문구로 교체했다고 보고했습니다. 동일한 설정을 다시 요청하지 않습니다. 앱 설정 화면 직접 검사와 교체 후 새 대화의 지침 적용 확인은 미실행입니다.

## 최근 점검

- 2026-09-07 C08의 본문 전달·추가 호출 부재·링크 확인과 별도 Knowledge 검색 실패를 분리해 기록함. 공식 Native 검색·우회 분기·그룹 토글·본문 읽기와 Prompt 보완을 대조하고 독립 백엔드 검토를 수행함. 문서 검사·회귀 확인 계획·미실행 범위는 [조회 경로 검토](../evals/confluence-offline.md#knowledge-routing)에 기록함. 사내 설정·실행 코드·의존성은 변경하지 않음.
- 브라우저 502 관찰을 기존 Tool 오류와 구분해 기록하고 서비스 복구 후 재시험으로 다음 작업을 변경함. 원본 Tool에서 받은 HTTP 502는 `upstream_error` 분기이며 이전 `connection_failed`를 502 수신 증거로 해석하지 않음. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 코드·설정 변경, 사내 서버 점검·복구·코드 시험은 실행하지 않음.
- 재연결 실패 보고를 최초 인증 성공·검색 오류와 구분해 반영함. 새 오류 코드를 추정하지 않고 이미 실패한 호출 결과 확인을 다음 단계로 정함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 실행 코드·설정 변경·코드 시험·사내 직접 호출은 수행하지 않음.
- `check_access`·`search_pages`가 공통 `_context`와 `_request`를 사용하고 v0.1.2가 기본 주소의 스킴을 보존함을 확인함. 검색에 별도 HTTPS 고정은 없으며 `connection_failed`에 시간 초과·TLS·URL/OS 오류가 포함되고 HTTP 상태 오류·리디렉션은 별도 분기임. 독립 코드 검토에서도 검색만 HTTPS로 변경된다는 근거가 없음을 확인함. 진단에는 실제 적용 설정·동시점 재인증·오류 시간 정보가 더 필요함. STATUS·평가표만 변경해 문서 점검·`git diff --check`를 확인하며 코드 시험·사내 호출은 실행하지 않음.
- 사용자 보고의 두 성공 필드를 Tool의 `check_access` 결과와 대조해 인증 성공으로 반영하고, 평가표의 PAT 비노출·검색·문서 권한 조건과 구분함. STATUS·평가표만 갱신하며 문서 점검·`git diff --check`를 확인함. 실제 사내 실행·화면·로그 직접 검사는 없고 코드 시험을 재실행하지 않음.
- Git 프록시 연결·최초 clone 성공이라는 사용자 보고를 다음 WebUI 수동 적용 단계와 구분해 반영함. 안내 원본은 Tool v0.1.2의 [910ad765](https://github.com/knadalkim-a11y/team-agent-poc/commit/910ad765a777df1caf30a565a197097f8afbf8b0)이며 실제 사내 SHA·등록 코드 대조는 대기. STATUS만 갱신하고 문서 점검·`git diff --check`를 확인함. 실행 코드·기존 실환경 판정은 유지하며 자동 코드 시험은 이번 상태 기록에서 재실행하지 않음.
- HTTP 허용 옵션·요청·문서 링크·HTTPS 검증·리디렉션·프록시 경계와 관련 안내를 검토함. 독립 코드·시험 diff 검토에서 차단할 문제 없음. 실제 주소·PAT·사내 네트워크는 사용하지 않았으며 새 검증 결과와 미실행 범위는 [HTTP 지원 기록](../evals/confluence-offline.md#http-opt-in)에 둠. C01/C02의 기존 판정을 v0.1.2 배포 시험 결과로 갱신하지 않음.
- 읽기 전용 가짜 PAT DB 검사기와 합성 SQLite 시험을 추가했던 자동 시험 97개, 문서 검사·diff 통과 이력은 [검증 증거](../evals/confluence-offline.md#canary-db-check)에 보존. 평문·잘못된 키·중복·WAL·journal·값 비노출 조건을 확인했던 당시 사외 시험임.
- 기존 스크립트 전용 암호화 안내에 수동 기동 대안을 추가. 경로·키 재정의·8080 사용 시 중단, 새 백업 폴더, 핵심 파일 비교 후 기동 순서를 정적으로 검토. 문서 검사와 미실행 범위는 [수동 기동 안내 검토](../evals/confluence-offline.md#manual-startup)에 기록함.
- 지침·STATUS·README의 검수와 기록 규칙을 대조해 STATUS 갱신 조건의 불일치를 보완. 문서 검사 오류·검토 후보 0, 상세 검증 결과와 미확인 범위는 [검수 절차 보완 기록](../evals/confluence-offline.md#review-process)에 둡니다.
- 사용자 보고의 수동 백업·재기동·W04와 Tool 생성 상태를 구분해 반영. 문서 점검 오류·검토 후보 0 및 `git diff --check` 통과. 이전 코드 시험 87개 통과는 [사내 복귀 전 정리의 증거](../evals/confluence-offline.md#pre-mvp-cleanup)에 보존. GPT의 Windows 직접 실행·고정 ps1 검증, Tool 등록 내용 대조·사내 API·사용자 격리·사용성 검증은 미실행.

원격 게시 여부는 해당 Git 커밋으로 확인합니다. 문서 게시를 WebUI 배포 완료로 해석하지 않습니다.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때만 이 파일을 갱신합니다. 시험별 상태표와 과거 세션 전문은 붙이지 말고 증거에 연결합니다. 새 기능의 원본·배포·실환경 검증을 서로 다른 상태로 기록합니다.
