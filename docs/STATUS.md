# 현재 작업 상태

갱신일: 2026-09-07

계획·다음 작업·적용 원본을 관리합니다. 시험 판정은 [평가표](../evals/scenarios.md), 환경은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)가 원본입니다.

## 목표와 이번 작업

- 목표: 비개발자가 범용 채팅·사내 자료 조회·팀원 Prompt/Skill 공유를 쉽게 사용하는 플랫폼. 현재는 Open WebUI Native와 Git Agent Pack을 사용하고 원본 WebUI는 수정하지 않음.
- 현재 위치: 개인 Windows 환경의 기본 채팅·Confluence 읽기 흐름을 확인했고, Jira 프로젝트별 현황과 첫 API 결과용 Rich UI 코드를 준비하는 단계. 실제 Jira 연결·WebUI 화면·공용 배포·비개발자 사용성 완료를 뜻하지 않음.
- 이번 작업: 사용자 보고 Jira 8.5.12·기존 개인 토큰·프로젝트 기반 시스템 구분을 반영해 프로젝트별 전체/미완료 집계와 최근 목록·상세 읽기, 결과 탐색 화면을 구현함. 실제 키는 사내 허용목록에서만 관리하고 저장소에는 합성 예시만 둠. 기본 비활성 Bearer 후보이며 코드·합성 검사와 사내 적용을 구분함.
- 다음 작업 하나: **현재 성공하는 Jira 호출의 인증 형식이 Bearer인지 확인한다.** 모르면 토큰 발급 메뉴/앱 이름만 확인하고 실제 토큰·주소·키 목록은 추가 수집하지 않음. 형식이 맞으면 [Jira 등록 안내](05-jira-read-tool.md)에 따라 새 개인 필드 저장 확인 후 정상 프로젝트 한 흐름을 확인함. 기존 업무용 토큰을 폐기·재발급하지 않음.

<a id="delivery-plan"></a>

## 실행 계획

| 순서 | 작업 묶음 | 완료 판단·진행 조건 |
|---|---|---|
| 1. 기반 활용 | 기존 범용 채팅·Confluence 검색/본문/근거 링크 사용 | 확인한 W·D·Confluence 증거를 재사용하되 환경·변경 영향이 다른 범위는 구분. 세부 정책 문답 전체 완료를 다음 기능의 선행조건으로 두지 않음 |
| 2. Jira + 첫 Rich UI | 프로젝트별 시스템 전체/미완료 비교 → 받은 최근 목록의 프로젝트/상태/담당자 필터·펼치기 → 이슈 상세·원문. 질문 예시·부분 실패·다음 페이지 안내를 함께 제공 | [읽기 Tool·화면 준비](05-jira-read-tool.md); 실제 인증 호환성·집계 일치·허용 범위·대표 실패·WebUI 동작은 미확인. 기존 전수 검증을 반복하지 않음 |
| 3. GitHub 읽기 | 제품/인증/허용 저장소 확인 후 필요한 PR 또는 이슈 조회 하나 | 원문과 결과·권한 일치 확인. 독립 후속 작업이므로 연결 준비가 지연돼도 준비된 기능의 파일럿을 막지 않음 |
| 4. 소규모 공용 파일럿 | 승인된 팀 서버에 새 배포, 선택한 기능의 공개 전 검증, 소수 비개발자 실제 사용. 허용된 Prompt·Skill 공유 흐름 확인 | 공개 전 조건과 [사용성 기준](../evals/scenarios.md#usability)을 충족하고 실제 업무에서 막힌 지점을 개선. 개인 PC 포트 공개·사용자 데이터 자동 이전으로 대체하지 않음 |
| 5. 수요 기반 확장 | EMS/APC/FDC의 승인 API가 있는 업무 하나, 필요한 역할별 기능·Rich UI | 업무 가치와 접근 경계를 먼저 정하고 작은 읽기 기능부터 추가. 쓰기·자동화·다중 Agent는 별도 필요가 확인될 때 검토 |

첫 공용 파일럿은 **범용 채팅 + Confluence + 준비된 Jira/첫 Rich UI** 범위로 시작합니다. 준비되지 않은 연동은 제외하고 그 범위를 명시합니다. GitHub·EMS/APC/FDC 전체 연동이나 Hermes 도입을 MVP 완료 조건으로 두지 않습니다. 파일럿에서 비개발자가 실제 업무 흐름을 완료하고 결과·오류·공유를 이해하는 것까지가 첫 배포의 목표입니다.

한 번에 구현할 업무 흐름은 하나로 유지합니다. 제품 확인 → 작은 읽기 기능·필요한 화면 → GPT의 코드/합성 검사 → 사내의 짧은 확인 묶음 → 결과 반영 순서로 진행합니다. 단계별 실제 권한·배포 승인을 대신하는 계획은 아닙니다. 구체 등록/화면 경계는 [Native 가이드](03-openwebui-native-agent.md#rich-ui), 시험 시점은 [평가표](../evals/scenarios.md#validation-timing)에만 관리합니다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| 지침 개정 | 2026-09-06 Prompt·공통 정책 v0.2·정책 답변 Skill 명확화 | 2026-09-07 두 지침 UI 저장 보고; 개정 후 P02 PASS, P03 창작 거절 부분 확인, P04~P10 미완료; 실행 시점은 평가표 | [P02~P10 재검증](../evals/scenarios.md#instruction-revision), [기존 지침 갱신](03-openwebui-native-agent.md#update-existing-instructions) | 전달·저장 안내 원본 [dfeb95f](https://github.com/knadalkim-a11y/team-agent-poc/commit/dfeb95fbf96cf6a2bb75a3ba75fac3bc92ed60fc); 등록 내용·사용자 추가 규칙·사내 checkout SHA 직접 대조는 미실행 |
| 조회 경로 보완 | Prompt의 [현재 POC 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션 | 부분 적용 당시 C04·P02 정상·임베딩 오류 재발 없음 보고; 이번 전체 Prompt에도 포함해 저장 안내 | [실환경 결과](../evals/scenarios.md#결과-기록), [당시 소스 검토](../evals/confluence-offline.md#knowledge-routing) | 부분 추가 안내 원본 [28f526a](https://github.com/knadalkim-a11y/team-agent-poc/blob/28f526a39162e54f126f577554f8c15fdd5940f1/agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로); 현재 전체 지침 안내 원본은 위 행. 부분 적용 당시 성공을 이번 개정 후 재평가로 간주하지 않음 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool v0.1.2; HTTP 명시적 허용 | 2026-09-07 연결·조회·문서 권한·확인한 출력의 PAT 비노출·시험한 구성의 쓰기 차단·PAT 폐기와 교체 후 복구 확인 보고. 오류 처리 등 공용 사용 전체 검증은 미완료 | [HTTP 지원 사외 검증](../evals/confluence-offline.md#http-opt-in), [실환경 C01~C09 및 결과](../evals/scenarios.md#confluence-live) | 새 Tool 안내 원본 [910ad765](https://github.com/knadalkim-a11y/team-agent-poc/blob/910ad765a777df1caf30a565a197097f8afbf8b0/agent-pack/skills/confluence-read/scripts/confluence_tool.py), 기존 Skill 안내 원본 [3495c2c](https://github.com/knadalkim-a11y/team-agent-poc/blob/3495c2c9d0fd30c6fc13c8a09e28f7ba59bb3e3f/agent-pack/skills/confluence-read/SKILL.md). C06에서 등록 코드가 전달한 원본과 같다는 사용자 확인; GPT의 등록 코드·사내 checkout SHA 직접 대조는 미실행 |
| Rich UI 참고 예제 | [합성 검색 결과 HTML](04-confluence-read-tool.md#rich-ui-demo); 실제 API·기존 Tool과 미연동 | 배포 대상 미확정 | [사전 준비 검증](../evals/confluence-offline.md#status-history); 실제 브라우저·WebUI 검증과 구분 | 해당 없음 |
| Jira 읽기·Rich UI | 기본 비활성 Python Tool v0.1.0, 코드 안의 고정 화면, 기존 Prompt의 조건부 Jira 조회 안내. 추가 Skill 없음 | 미적용. 사용자 보고 버전·기존 토큰 보유와 Bearer 호환성·WebUI 성공을 구분 | [Jira 사외 검증](../evals/jira-offline.md#initial-implementation), [J01~J05](../evals/scenarios.md#jira-live) | 사내 적용 원본 없음; 새 변경의 Git 준비와 사내 적용을 구분 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션; smoke 자동 리디렉션 차단 | 사용자 보고로 명령 복사 후 수동 실행; 정해진 기동 스크립트 채택은 안정화 이후 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |

**Skill은 Git과 UI 등록 보고 기준 모두 3개이며, Skill 자체 사용 확인은 기존 2개입니다.** Confluence Tool의 `check_access` 성공 보고는 있으나 `confluence-read`를 `view_skill`로 불러왔는지는 별도 확인되지 않았습니다. 적용 원본은 Git 최신 커밋과 구분하며, 안내 원본·사용자 보고·등록 내용 대조 여부를 함께 기록합니다.

## 남아 있는 검증과 제한

- Jira의 Bearer 인증 호환성·프로젝트별 전체/미완료 실측·새 Jira 개인 필드 저장·계정 분리·실제 Rich UI는 미확인. 프로젝트별 집계와 최근 페이지를 구분하며 일부 실패를 0건으로 바꾸지 않음. 공용 공개 조건과 기존 증거는 유지함.
- 개정 지침은 UI 저장 보고가 있고 P02 PASS, P03 창작 거절 부분 확인 상태. 나머지는 평가표의 시점에 따라 기능 확인·공개 전 묶음·진단으로 수행하며 미확인을 PASS로 바꾸지 않음. POC-POL-001 v0.1은 합성 Knowledge이고 공통 정책 관리 원본 v0.2와 다름.
- Confluence C07의 개별 HTTP 401·403·timeout 분기, confluence-read Skill의 실제 로딩은 미확인. 과거 임베딩 검색 오류는 조회 경로 보완 후 재발 없음 보고가 있으나 의미 검색 자체를 복구한 것은 아님. 운영 장애나 토큰 폐기를 불필요하게 반복하지 않음.
- 기존 W/D/S/Confluence PASS는 해당 환경·구성·합성 자료와 사용자 보고 범위임. I01~I05 사용자 격리·새 서버의 비밀 저장/권한·실제 비개발자 사용/공유는 별도 미완료. 공개할 환경과 기능의 필수 조건부터 확인함.
- 초기 EES의 Memory·Chat History·위험 실행 기능 OFF는 유지하며 개인 전역 Memory ON과 구분함. 운영 DB 직접 연결·자격증명·범용 SQL·Shell·쓰기는 제공하지 않음. S06은 승인 DB 조회 중계 기능을 도입할 때만 실행함.
- 현재 GLM 5.2를 기준으로 작은 Tool 스키마·짧은 절차·고정 UI 템플릿을 사용함. GLM 5.3 등 모델 교체 시 대표 대화·조회·실패/금지 요청을 비교하고, 영향 없는 저장·토큰 시험을 자동 반복하지 않음.
- 기존 Hermes 환경은 보존. 별도 Tool Server·Router·A2A·자동 동기화·개인화·WebUI 코어 수정·공통 UI 프레임워크는 실제 필요가 확인될 때 검토함. 팀원 작성물은 WebUI, 담당자가 채택한 공통 배포 자산은 Git이라는 [관리 경계](../README.md#원본과-배포본)를 유지함.

## 사내 전달과 유지할 환경

- 사내 PC에서는 ChatGPT에 접근할 수 없어 외부 모바일로 코드·명령을 옮기거나 Git을 사용함. `%USERPROFILE%\team-agent-poc` 최초 clone은 성공 보고가 있으므로 반복하지 않음. 새 PowerShell에서는 사내 `$gitProxy` 값을 다시 설정하고 `git -c "http.proxy=$gitProxy" ...`를 사용함. 영구 프록시나 WebUI/Confluence 네트워크 설정은 임의 변경하지 않음.
- Open WebUI의 기존 데이터·키·계정은 유지하며 실행은 아직 명령 복사 방식. 개인 환경의 정해진 시작 스크립트 전환은 안정화 이후에 진행함. 새 팀 서버에서는 배포 절차·관리할 시작 명령·내부 백업/복구·적용 원본을 함께 정하며, 개인 데이터 이전은 별도 승인 범위임.
- 웹 프로젝트 지침은 2026-09-06 README의 짧은 저장소 참조 문구로 교체했다고 보고받음. 재입력을 요구하지 않으며 저장소 지침 변경이 웹 설정 자체를 수정한 것으로 기록하지 않음.

## 최근 점검

Jira 읽기 경로·프로젝트 집계/최근 목록의 구분·고정 화면과 사내 안내를 대조함. 변경한 Jira 코드·합성 화면의 검사 결과와 미실행 범위는 [첫 Jira 구현 검증](../evals/jira-offline.md#initial-implementation)에 기록함. 직전 계획 정리와 점검 요약은 [계획 최적화 검토](../evals/confluence-offline.md#mvp-plan-review)에 보존돼 있음. 기존 Confluence 실행 코드·저장 검사·서빙 설정과 과거 실환경 판정은 변경하지 않음.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때 갱신합니다. 최근 점검은 이번 요약만 두고 날짜별 증거는 기존 evals에서 연결합니다. Git 게시·WebUI 적용·실환경 통과를 각각 구분합니다.
