# Confluence·관리 작업 사외 검증 기록

> Confluence Tool과 관련 관리 작업의 날짜별 사외 검증 증거를 보존합니다. 최신 준비 상태는 [STATUS](../docs/STATUS.md), 항목별 실환경 결과는 [C01~C09](scenarios.md#confluence-live)에서 확인합니다. 이후 코드 변경이나 배포에 이 결과가 자동으로 적용되는 것은 아닙니다.

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

<a id="status-history"></a>

## STATUS에서 옮긴 과거 검증 증거

2026-09-06 정리 시 [이전 STATUS](https://github.com/knadalkim-a11y/team-agent-poc/blob/3614af44fffd2bb887683e0fdcf2f415edef45fe/docs/STATUS.md)의 날짜·환경·결과를 보존해 옮겼습니다. 아래 기록은 이번 정리 후 재검증이나 사내 배포 완료를 뜻하지 않습니다.

## 비개발자 사용성 기준 반영 — 2026-09-06

- 기존 개발 지침·상태·변경 이력 3개만 갱신. 별도 사용성 문서·UI 프레임워크·새 기능은 추가하지 않음. Confluence 읽기 MVP와 후속 순서는 유지.
- Linux / Python 3.12.13에서 `python scripts/check_docs.py`: Markdown 20개·내부 링크 101개·오류 0·검토 후보 0. `git diff --check` 통과. 실제 화면·사내 모델·초보 사용자 사용성 검증과 WebUI 배포는 미실행.

## 이전 모델 운용 기준 반영 — 2026-09-06

- 사용자 보고와 설계 전제를 기존 문서 4개에 반영. 신규 파일·모델 분기 코드·실행 설정은 추가하지 않음.
- 현재 GLM 5.2 기준 Tool 호출 성공률·되묻기 동작·응답 시간의 비교 측정은 미실행. 모델 교체 시 기존 평가 질문을 재사용하며 별도 평가 프레임워크는 만들지 않음.
- Linux / Python 3.12.13에서 `python scripts/check_docs.py`: Markdown 20개·내부 링크 101개·오류 0·검토 후보 0. `git diff --check` 통과. 코드·Skill·설정·시험 파일 변경 없음; 실제 모델·WebUI 실행과 배포는 미실행.

## 이전 지침 개정 검증 — 2026-09-06

- 환경: Linux / Python 3.12.13. 기존 Markdown 8개를 수정했으며 새 파일·서버·Tool 코드·실행 설정·자동 테스트 코드는 추가하거나 변경하지 않음.
- `python scripts/check_docs.py`: Markdown 20개, 내부 링크 98개, 오류 0·검토 후보 0. `git diff --check` 통과.
- skill-creator의 `quick_validate.py agent-pack/skills/policy-grounded-answer`: 형식 검사 통과. 지침 간 일치·과설계·권한 범위에 대한 독립 정적 검토에서 수정 필수 문제 없음.
- Python 전체 테스트·사내 모델·Windows·Open WebUI 실행은 미실행. 형식·정적 검토는 정책 준수와 실제 Tool 차단의 행동 검증을 대신하지 않음.
- 아래 이전 실행 기록은 보존. 개정본의 사내 응답 검증은 [P02~P10](../evals/scenarios.md#instruction-revision)에서 관리하며, Tool 설정의 암호화·사용자 권한 검증은 기존 C01~C09를 따른다.
- 앱 프로젝트 지침은 기존 파일 참조 문구를 유지하며 앱 설정을 직접 변경하지 않음. 개정 Agent Pack도 WebUI에는 아직 반영하지 않음.

## 이전 Rich UI 사전 준비 검증 — 2026-09-05

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

### MVP 우선 범위 정리 — 2026-09-06

- 이번 범위 정리 점검(2026-09-06): Linux / Python 3.12.13에서 STATUS만 변경. `python scripts/check_docs.py`는 Markdown 20개·내부 링크 101개·오류 0·검토 후보 0, `git diff --check` 통과. 실제 사내 검증은 미실행.

<a id="pre-mvp-cleanup"></a>

## 사내 복귀 전 정리·결함 보완 검증 — 2026-09-06

- 실행 환경: Linux / Python 3.12.13 / Pydantic 2.13.4. 실제 사내 데이터·PAT·네트워크를 사용하지 않은 합성 mock 시험.
- 변경 전 기준선: `python -m unittest discover -s tests -v` 86개 통과, `python scripts/check_docs.py` Markdown 20개·내부 링크 101개·오류 0·검토 후보 0.
- Confluence Tool v0.1.1은 평문 변환에서 표 셀 경계를 보존. `get_page` 회귀시험으로 헤더·12/34 수치 분리와 인라인 텍스트의 보존을 확인하며, 병합 셀·복잡한 표 렌더링은 구현하지 않음.
- `smoke-test.ps1`의 자동 리디렉션 차단은 정적 검토만 수행. PowerShell 미설치로 Windows 실행은 미검증이며, 사내에서 loopback 정상 응답과 리디렉션 실패 처리를 확인해야 함.
- 관리·설치 가이드 정리와 과거 STATUS 증거 이동. 신규 파일·계층·의존성·실행 환경을 추가하지 않음. Prompt·Skill 본문·공통 정책·모델 설정과 기존 실환경 시험 판정은 유지.
- 변경 후 `python -m unittest discover -s tests -v`: 문서 점검 43개 + Confluence 44개, 총 87개 통과. `python scripts/check_docs.py`: Markdown 20개·내부 링크 122개·오류 0·검토 후보 0. `git diff --check` 통과.
- 이전 STATUS의 날짜별 검증 블록 원문과 평가표의 ID·판정·날짜별 결과 보존을 대조 확인. STATUS는 80줄에서 48줄로 정리. 변경하지 않은 Prompt·Skill 본문·공통 정책·모델 버전 기준·설정·기동 스크립트는 기존 내용과 동일함을 확인.
- 변경한 기존 파일 15개의 최종 독립 검토에서 차단할 문제 없음. 관리 경계·평가 범위·코드 회귀·과설계·실환경 상태 구분을 확인했으며, 별도 실행 시험을 추가한 결과는 아님.
- 실제 GLM 성능·Windows·WebUI·Confluence·사용자 권한 및 사용성 검증·배포는 미실행. 이전 PASS를 이번 배포나 실행 결과로 갱신하지 않음.

<a id="review-process"></a>

## 검수 절차와 기록 기준 보완 — 2026-09-06

- 확인 범위: `AGENTS.md`의 시작·검증·종료 규칙과 `docs/STATUS.md` 갱신 규칙, README의 문서 관리 안내를 대조. 작은 표현 수정·기능/정책 변경·반복 결함에 따른 검수 범위, 기록 위치, 실환경 미확인의 구분을 검토.
- 발견 사항: AGENTS의 매 세션 STATUS 갱신으로 읽히는 문구와 종료 시 평가 증거·STATUS 갱신 요구가 STATUS의 조건부 갱신 규칙과 불일치. 기존 규칙에 의미 검토는 있었지만 실제 대조 대상·중요 조건·발견과 처리 결과를 드러내는 완료 기준은 부족했음.
- 처리: 기존 지침에 규모별 검수, 관련 문제 수정 후 필요한 재검증, 네 가지 결과 요소를 반영. 작은 수정은 짧은 보고, 재사용할 근거는 기존 evals, STATUS는 상태 변경 시 갱신으로 통일. README는 기존 지침 위임과 충돌하지 않아 유지. 새 파일·CI·검수 자동 실행은 추가하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 122개·오류 0·검토 후보 0, `git diff --check` 통과. 변경은 기존 Markdown 4개뿐이며 실행 코드·설정·시험 코드·평가표는 유지. 과거 검증 원문과 다음 사내 작업의 보존도 대조 확인.
- 독립 검토: 변경한 4개 문서와 README를 대조해 규모별 검수·결과 기록·STATUS 조건이 일치함을 확인. 설명 요청의 구현 확대, 매번 전체 시험·독립 검토·별도 보고서 강제가 생기지 않았으며 확인 범위에서 수정 필수 문제 없음. 정적 의미 검토이며 자동 시험 재실행을 뜻하지 않음.
- 미확인: 개정 지침이 향후 세션에서 누락을 얼마나 줄이는지는 아직 관찰하지 않음. 실행 코드 변경이 없어 Python 전체 시험은 이번에 재실행하지 않았으며, Windows·사내 GLM·WebUI·Confluence·권한·사용성·배포 검증도 미실행. 이전 87개 통과는 직전 정리의 증거로 유지.

<a id="manual-startup"></a>

## 수동 기동 안내 검토 — 2026-09-06

- 범위·발견: 수동 기동 유지라는 사용자 방침에 비해 Confluence 가이드는 저장소 스크립트만 예시로 제시하고 있었음. `docs/01-openwebui-install.md`, `scripts/start-openwebui.ps1`, C01/C02 조건과 대조해 기존 창·경로·키·프록시를 유지하는 수동 대안을 추가함. 새 스크립트 파일이나 실행 의존성은 추가하지 않음.
- 정적 검토: 경로 불일치·키/DB 환경변수 재정의·빈 키·8080 사용·복사/해시 비교 실패 때 재기동하지 않는 순서를 확인. 새 백업 폴더는 기존 폴더를 덮어쓰지 않고 핵심 DB·키 해시는 출력 없이 비교함. 백업 성공·기동·Valve 저장 암호화 판정을 구분하며 실제 PAT 입력 순서와 기존 C01~C09 판정은 유지.
- 검증: Linux에서 `python scripts/check_docs.py` 오류·검토 후보 0, `git diff --check` 통과. 기존 Markdown 3개만 변경했으며 Python Tool·설정·기동 스크립트·자동 시험·실환경 평가표는 변경하지 않음.
- 미실행: PowerShell이 없어 명령의 Windows 실행·오류 분기·백업 복원·재기동은 시험하지 못함. 사용자 보고의 원래 창 검사 결과는 STATUS에만 기록하며, 아직 백업·암호화 저장·WebUI 등록 성공으로 간주하지 않음. 이전 Python 시험 87개는 이번 재실행 결과가 아님.

<a id="canary-db-check"></a>

## 가짜 PAT DB 검사 코드 검증 — 2026-09-06

- 근거: Open WebUI v0.11.3의 `models/tools.py`, `models/users.py`, `utils/valves.py`, `serve()` 키 로드를 대조. 개인 UserValves는 `user.settings.tools.valves[tool_id]`에 dict 전체의 Fernet 암호문 문자열로 저장됨. 관리자 `tool.valves`나 문자열 모양만 검사하는 방식은 개인 PAT 저장 증거가 되지 않음.
- 구현: 기존 키를 공백 제거 없이 읽고 읽기 전용 SQLite에서 해당 가짜 PAT와 일치하는 암호문을 확인. 평문 dict·잘못된 키·누락·중복·DB/WAL/journal 잔존은 통과하지 않음. 앱 import·API 호출·DB 마이그레이션·자격증명/사용자 ID/오류 전문 출력 없음. 실환경은 metadata 0.11.3만 허용하며 결과에서 로그·재기동 미검증을 명시.
- 합성 환경: Linux / Python 3.12.13 / Pydantic 2.13.4 / cryptography 46.0.0. 새 검사 시험 10개 통과: 암호문·DB 원본 유지, 평문, 잘못된 키·누락, 중복·혼합, committed WAL, journal 잔존, 청크 경계·UTF-16, DB 미생성, 44자 키, 오류 비노출. 표준 32자 형태 외에 줄바꿈이 있는 합성 키도 그대로 검증.
- uv 실행 검토: Linux / uv 0.11.33의 임시 오프라인 합성 패키지 실험에서 `패키지@버전` 실행과 `--from 패키지==버전 python` 및 stdin 실행이 같은 Python 환경을 재사용함. Open WebUI 설치·기동은 수행하지 않음. `--offline`이 로컬 캐시 재구성까지 금지하는 옵션은 아님.
- 검증 결과: `python -m unittest discover -s tests -v` 97개 통과, `python scripts/check_docs.py` 오류·검토 후보 0, `git diff --check` 통과. 기존 업무 Tool·기동 스크립트·C01~C09 판정은 변경하지 않음.
- 미확인: Windows/사용자 uv 버전에서 검사 실행, 실제 DB·로그 및 가짜 값 저장 후 재기동은 미실행. 사용자 저장 보고는 서버 DB 저장 성공을 독립 검증한 것이 아니며 C01/C02는 계속 대기. 모든 로그·백업·스냅샷을 검사하거나 실제 PAT 입력을 승인하는 결과가 아님.
