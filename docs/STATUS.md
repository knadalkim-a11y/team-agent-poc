# 현재 작업 상태

갱신일: 2026-09-05

이 파일은 새 GPT 세션의 짧은 인계 지점입니다. 기능별 판정 원본은 [평가표](../evals/scenarios.md), 환경 기준은 [versions](../versions.md), 과거 변경은 [CHANGELOG](../CHANGELOG.md)에 둡니다. 아래 요약이 증거와 충돌하면 단정하지 말고 증거를 확인합니다.

## 목표와 이번 작업

- 목표: 비개발자가 Open WebUI의 `EES 통합 Assistant`에서 사내 LLM·팀 지침·읽기 기능을 쓰는 POC.
- 현재 경로: Open WebUI Native. Windows·Docker 미사용이며, 사내 PC 밖에서 코드·문서 준비만 할 수 있는 상황.
- 이번 작업: GPT 개발 진입점 추가와 상태·검증 기록의 원본 정리. 기존 Skill·Tool·실행 스크립트·테스트 경로와 동작은 유지.
- 다음 작업 하나: 사내 복귀 후 **Confluence 제품·버전과 개인 PAT 인증 방식을 확인**한다. [설치 안내](04-confluence-read-tool.md)의 제품 확인부터 시작하며, 현재 Tool은 Data Center PAT/Bearer용 초안이다.

## Git 준비와 WebUI 적용을 구분

| 대상 | Git에서 준비한 것 | WebUI 반영 마지막 확인 | 검증 근거 | 적용 원본 커밋 |
|---|---|---|---|---|
| 기본 Assistant | Prompt·정책·기존 Skill 2개·합성 Knowledge | 사용자 보고로 생성·사용 확인 | [W·D·P 시험 및 기록](../evals/scenarios.md); 전체 Gate 통과를 뜻하지 않음 | 당시 수동 반영 SHA 미기록 |
| Confluence 추가 기능 | Skill 1개 + Python 읽기 Tool, 원본 [0cb6096](https://github.com/knadalkim-a11y/team-agent-poc/commit/0cb60962c44c2d0b59c4cb028faf2030161699f5) | 반영 확인 없음 | [사외 자동 시험 증거](../evals/confluence-offline.md), [실환경 C01~C09](../evals/scenarios.md#confluence-live) | 미확인 |
| 실행 스크립트 | 시작·smoke test·암호화 준비 옵션 | 이 저장소 스크립트로 기동한 사실과 적용 SHA는 미확인 | UI의 /health 성공과 Windows 스크립트 실행 검증은 별개 | 미확인 |

**Git에는 Skill 3개가 있고, 기존 UI에서 생성·사용을 확인한 것은 2개입니다.** Confluence 코드가 Git에 존재한다고 설치·활성화됐다고 판단하지 않습니다. 적용 커밋은 저장소의 최신 커밋이 아니라 실제로 복사·등록한 원본을 적습니다.

## 남아 있는 검증과 제한

- 사내 연결·저장 암호화·두 사용자 권한 확인은 [C01~C09](../evals/scenarios.md#confluence-live)의 판정으로 관리합니다. 실제 PAT를 넣기 전에 가짜 값으로 암호화 저장·키 유지부터 확인합니다.
- Open WebUI 재시작·스트리밍·문맥·반복 안정성·데이터 위치·사용자 격리의 미확인 항목은 [전체 평가표](../evals/scenarios.md)를 따릅니다. 기존 UI 성공이나 mock 테스트로 미확인 항목을 PASS 처리하지 않습니다.
- 사내 프록시·CA·네트워크 경로는 환경별 확인 대상입니다. 과거 HTTP 200 또는 연결 오류를 현재 경로의 확정 근거로 재사용하지 않습니다.
- 개인 Memory·위험 Tool은 초기 구성에서 제외합니다. 운영 DB 직접 연결·범용 SQL·Shell·쓰기 기능을 추가하지 않습니다.
- 기존 Hermes 설치·사내 모델 Q/A 확인 이력은 유지하되, WebUI↔Hermes 연동·재설치는 보류합니다. 실제 Native 한계가 확인될 때만 비교합니다.
- Router·A2A·EMS/APC 자동 라우팅·자동 배포·개인화·서버 이전은 후속 범위입니다. 사용자 PC 공개나 외부 서비스 추가를 이번 준비 작업에 포함하지 않습니다.

## 이번 관리 리팩토링 검증

- 문서·상태 원본 정리 완료. 신규 파일은 AGENTS와 STATUS 두 개이며, 실행 코드·설정·시험 코드와 기존 기능 경로는 유지.
- 기존 자동 테스트 43개 재통과, 내부 문서 링크·평가 판정·증거 보존 검사 통과. [이번 재검증 기록](../evals/confluence-offline.md#management-refactor)을 확인한다.
- 독립 문서 검토에서 차단할 문제를 발견하지 않음.
- 실제 Windows 실행·Confluence·WebUI 배포: 수행하지 않음.

원격 게시 여부는 해당 Git 커밋으로 확인합니다. 문서 게시를 WebUI 배포 완료로 해석하지 않습니다.

## 갱신 규칙

현재 작업·다음 작업·미해결·적용 원본이 바뀔 때만 이 파일을 갱신합니다. 시험별 상태표와 과거 세션 전문은 붙이지 말고 증거에 연결합니다. 새 기능의 원본·배포·실환경 검증을 서로 다른 상태로 기록합니다.
