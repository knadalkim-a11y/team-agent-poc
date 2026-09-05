# Confluence 사외 검증 기록

> 2026-09-05 실행 결과를 보존하는 과거 검증 보고서입니다. 최신 준비 상태는 [STATUS](../docs/STATUS.md), 항목별 실환경 결과는 [C01~C09](scenarios.md#confluence-live)에서 확인합니다. 이후 코드 변경이나 배포에 이 결과가 자동으로 적용되는 것은 아닙니다.

- 날짜: 2026-09-05
- 범위: Confluence 읽기 Tool v0.1.0, Skill, 설치 안내
- 실행 환경: Linux, Python 3.12.13, Pydantic 2.13.4
- 대상 환경: Open WebUI 0.11.3 / Windows / Python 3.11 — 기록 당시 실환경 실행은 하지 않음
- 테스트: `python -m unittest discover -s tests -v` → **43개 통과**

HTTP 응답은 전부 합성 mock입니다. 테스트 중 소켓 연결과 DNS 조회를 차단했습니다. 실제 PAT·사내 주소·사내 문서를 사용하지 않았습니다.

## 확인한 것

| 항목 | 결과 |
|---|---|
| 설정·로그인·PAT·암호화 플래그 누락 시 요청 차단 | PASS |
| 사용자별 PAT 헤더와 동시 검색 결과 분리 | PASS — mock 범위 |
| 고정 HTTPS 주소·GET API·허용 Space 제한 | PASS |
| 문서 metadata 확인 후 본문 조회, 본문 Space 재검증 | PASS |
| TLS 인증 검증, 리디렉션 차단, 기본 프록시 미사용 | PASS — 핸들러 구성 확인 |
| CQL 문자열 이스케이프·문서 ID 검증 | PASS |
| 401·403·404·429·5xx·시간 초과·HTML·잘못된 JSON | PASS |
| 응답 크기 제한 및 PAT 반사·부분 노출 회귀 검사 | PASS |
| 공개 도구가 읽기 함수 3개뿐인지 확인 | PASS |
| Python 3.11 문법 파싱 및 loader 방식 exec/타입 검사 | PASS — 실제 Python 3.11 구동 대체 아님 |
| Skill 형식 검사 | PASS |

독립 검토에서 발견한 두 항목을 수정하고 회귀 테스트를 추가했습니다.

1. 기본 Confluence CQL에서 지원이 확인되지 않은 `status = current` 조건 제거. 응답의 페이지 상태 검증은 유지.
2. 제목·본문 길이 제한 **이전**에 현재 PAT를 마스킹. HTML 디코딩 이후에도 본문을 재검사.

## 기록 당시 확인하지 않은 것

- 사내 Confluence 제품·버전과 Data Center PAT/REST API 호환성
- 실제 사내 CA, HTTPS, 프록시 경로, 문서 매크로와 검색 품질
- 실제 Open WebUI 화면 등록·설정 저장·DB 암호화와 키 유지
- 두 실제 사용자의 Confluence ACL·대화 격리
- 문서 내 prompt injection에 대한 모델의 실제 행동
- Windows PowerShell 실행 스크립트 동작 — 이 환경에 PowerShell 없음

Tool은 기본 `ENABLED=false`입니다. Skill은 지침이지 보안 경계가 아니며, 이 Tool의 제한은 다른 도구에 적용되지 않습니다. Python 테스트 통과를 운영 승인으로 취급하지 않습니다.

사내 적용 절차는 [설치 안내](../docs/04-confluence-read-tool.md)를 따릅니다. 이 보고서 작성 당시 모든 실환경 항목은 **대기**였으며, 이후 C01~C09 판정과 증거는 [실환경 체크리스트](scenarios.md#confluence-live)에 기록합니다.

<a id="management-refactor"></a>

## 관리 구조 리팩토링 후 재검증 — 2026-09-05

별도 기능 변경 없이 문서 관리 원본을 정리한 뒤 다시 확인한 기록입니다.

- 실행 환경: Linux, Python 3.12.13, Pydantic 2.13.4.
- `python -m unittest discover -s tests -v`: 기존 43개 모두 PASS. HTTP·DNS·소켓은 기존 테스트의 mock·차단을 그대로 사용.
- `git diff --check`: PASS.
- 로컬 Markdown 상대 링크·앵커 검사: 끊어진 링크 없음.
- 기존 평가표 36행과 날짜별 증거 9행 보존. Confluence C01~C09 9행은 판정·조건 변경 없이 단일 평가표로 이동.
- 실행 코드·설정·시험 코드·업무 Prompt/Skill·정책 등 기존 런타임 관련 파일 12개 무변경 확인.
- 독립 문서 검토: 차단할 문제 없음. 새 파일은 `AGENTS.md`, `docs/STATUS.md` 두 개뿐.
- Windows 스크립트 실행, 실제 Confluence·WebUI 접속, 자격증명 저장·서비스 배포: 수행하지 않음.

문서 리팩토링을 근거로 실환경 시험을 PASS로 바꾸지 않았습니다.
