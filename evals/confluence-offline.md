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

<a id="http-opt-in"></a>

## HTTP 전용 사내 연결의 명시적 허용 — 2026-09-06

- 원인·범위: 사용자는 첫 `check_access`에서 HTTPS 주소 검사 오류를 보고했고 사내 주소가 HTTP인 것 같다고 설명함. 실제 주소는 수집하지 않음. 기존 v0.1.1은 HTTP를 요청 전에 차단하고 반환 base도 HTTPS로 고정했으므로 검사 조건만 바꾸면 충분하지 않았음.
- 처리: Tool v0.1.2에 관리자 `ALLOW_HTTP=false` 기본값 추가. 명시적으로 허용한 HTTP만 고정 기본 주소로 사용하며 스킴·포트·context path를 API 요청과 원문 링크에 보존. HTTP에서는 사용하지 않는 CA 파일 로드를 생략하고, HTTPS는 추가 CA 적용·인증서·호스트명 검증을 유지. HTTP/HTTPS 자동 전환·리디렉션·일반 사용자나 모델의 주소/프로토콜 선택은 제공하지 않음. HTTP에서 PAT·조회 내용의 전송 암호화가 없다는 설명과 기존 Tool의 수동 갱신 절차를 추가함.
- 회귀 검증: 기본 HTTP 차단, 개인 설정을 통한 HTTP 허용 우회 차단, 옵션 재비활성화, 고정 HTTP GET·검색·문서 링크, 사용하지 않는 CA 파일, HTTPS 검증·CA 적용 유지, 양쪽 스킴의 잘못된 URL·리디렉션 차단·환경 프록시 기본 미사용, HTTPS 실패 시 HTTP 재시도 없음. 기존 개인 PAT 분리·응답 비밀정보 제거·공간·읽기 제한 시험도 함께 확인함.
- 실행 결과: Linux / Python 3.12.13 / Pydantic 2.13.4 / cryptography 46.0.0에서 `python -m unittest discover -s tests -q` 총 101개 통과(Confluence 48개·가짜 PAT 검사 10개·문서 점검 43개). `python scripts/check_docs.py` 문서 20개·내부 링크 140개·오류 0·검토 후보 0, `git diff --check` 통과. 합성 데이터·mock 요청만 사용하고 실제 DNS·네트워크 연결은 시험에서 차단함.
- 독립 검토: Python Tool과 시험 diff를 별도 검토해 위 경계에서 차단할 문제를 찾지 못함. 검토자는 파일 수정·시험 재실행을 하지 않았으며 구현 담당자의 실행 결과와 구분함.
- 미실행: Windows PowerShell의 코드 복사 명령·WebUI 코드 교체 후 설정 보존·사내 HTTP/HTTPS 인증·문서 권한·로그·모델 호출·실제 배포. 기존 C01/C02 판정은 해당 시점 증거로 보존하며 C03 실패를 mock 성공으로 덮어쓰지 않음. 새 의존성·서버·Skill 본문·공통 정책·기동 방식은 추가하거나 바꾸지 않음.

<a id="c05-procedure"></a>

## 사용자별 문서 권한 시험 안내 검토 — 2026-09-07

- 범위: C01의 가짜 PAT 개인 설정 시험, C05 실제 문서 권한 기준, Tool의 개인 PAT 주입·검색·숫자 ID 조회·오류 분기와 설치 가이드를 대조함. 사용자 보고로 C04가 통과하고 실제 Confluence 계정 두 개로 시험 가능함을 확인한 뒤 수동 시험 순서를 준비함.
- 처리: 서로 다른 WebUI/Confluence 계정과 개인 PAT, 같은 허용 Space의 합성 공통·제한 문서, Confluence 자체의 권한 확인, A 조회 후 동일 B 세션·PAT의 공통 문서 성공과 제한 문서 검색/직접 조회 차단을 묶음. B의 인증·연결 실패나 Space 밖 문서 차단을 권한 시험 성공으로 오판하지 않으며 모델 거절·입력 반사와 실제 반환 자료를 구분함.
- 독립 검토: 브라우저 창 분리 외에 서로 다른 WebUI 사용자 계정을 명시해야 한다는 보완을 반영함. 기존 계정 사용, Confluence 자체 제한 확인과 정상 조회, 실제 Tool 결과 확인의 범위를 검토했으며 별도 검토자는 도구 실행·파일 수정·실환경 시험을 수행하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 142개·오류 0·검토 후보 0, `git diff --check` 통과. 기존 Markdown 3개만 변경했으며 실제 사내 검색어나 문서·PAT를 사용하지 않음.
- 미실행: 실제 계정·문서 준비, Confluence 접근 제한 변경, B PAT 저장, 두 사용자 검색·조회·콘솔 확인, 시험 후 정리. 가이드 준비나 계정 사용 가능 보고를 C05 PASS로 기록하지 않음. 실행 코드·설정·Skill·의존성·기존 실환경 판정은 변경하지 않았고 코드 시험을 재실행하지 않음.

<a id="model-access-review"></a>

## 일반 사용자 모델 접근 오류 검토 — 2026-09-07

- 발견: C05 안내에는 Assistant·Tool·Skill 권한만 적혀 있고 기반 모델 권한 확인이 빠져 있었음. 기존 Native 가이드에는 기반 모델 접근 필요성이 명시돼 있어 안내 간 연결을 보완함. A 사용 가능·B `Model not found`라는 사용자 보고를 받고 해당 일반 사용자 경로를 검토함.
- 소스 대조: 공식 Open WebUI v0.11.3의 `utils/models.py`는 Assistant 목록 필터와 채팅의 `check_model_access`를 구분하고, `utils/access_control/__init__.py`의 `has_base_model_access`가 기반 모델 체인의 각 읽기 권한을 확인함. 일반 사용자에게 기반 모델 DB 항목/읽기 권한이 없으면 접근을 거절할 수 있음. `main.py`의 일반 채팅은 모델 ID 누락과 권한 거절에서 `Model not found`를 반환하며 HTTP 400도 가능함. `routers/openai.py`의 provider 모델 조회 실패는 별도 404 경로임.
- UI 대조·처리: `workspace/Models/ModelEditor.svelte`의 `Base Model (From)`·AccessControl·`access_grants` 제출·Save & Update, `admin/Settings/Models.svelte`의 편집·upsert 저장을 확인함. [장애 안내](../docs/troubleshooting.md#user-model-not-found)에 해당 기반 모델의 B 읽기 권한 확인·저장과 새 대화의 단순 인사말 확인을 추가하고 C05에서 연결함. Hide는 권한과 구분하며 관리자 승격·전체 공개·검사 우회·실행 코드 변경을 해결책으로 넣지 않음.
- 독립 검토: 백엔드 담당 검토가 기반 모델 읽기 검사, 목록에는 보이지만 채팅이 실패할 수 있는 조건, 400/403/404 경로 차이를 확인함. 실제 사내 오류 원인은 아직 확정하지 않으며 필요한 최소 권한 확인을 첫 단계로 정함.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 146개·오류 0·검토 후보 0, `git diff --check` 통과. 기존 Markdown 5개만 변경함.
- 미실행: 사내 B 계정의 실제 권한·기반 모델 ID·실패 요청 확인, 권한 저장·채팅 복구·Confluence 재시험. 문서만 변경하고 코드 시험·서비스·모델·PAT 설정 변경은 수행하지 않음. C04 PASS는 유지하고 C05는 모델 접근 오류 해결 전 보류함.

<a id="c06-procedure"></a>

## 쓰기 차단 시험 안내 검토 — 2026-09-07

- 범위·처리: 실제 PAT의 응답·현재 콘솔 비노출 사용자 보고를 C03에 반영하고 [C06 안내](../docs/04-confluence-read-tool.md#c06-write-block)를 준비함. 기존 Guide·평가기준·Python Tool의 공개 함수, `_run` 분기, `_request`의 허용 경로와 GET 고정을 대조함.
- 검토 결과: 원본은 조회 함수 세 개만 공개하고 쓰기 method·임의 경로를 입력받지 않음. 독립 검토도 같은 경계를 확인함. 실제 등록본과 Assistant의 추가 연결 도구는 별도 확인해야 하므로 코드 구조와 모델의 거절 응답을 구분하고 합성 문서의 생성·본문·버전·존재 여부를 확인하도록 안내함. PAT 자체나 모든 WebUI 도구가 읽기 전용이라고 확대하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 148개·오류 0·검토 후보 0, `git diff --check` 통과.
- 미실행: 사내 등록 코드·연결 도구 대조, 생성·수정·삭제 요청과 실제 문서 확인. 안내 준비를 C06 PASS로 처리하지 않음. 기존 Markdown 4개만 변경했으며 코드·설정·의존성 변경과 코드 시험 재실행은 없음.

<a id="c07-procedure"></a>

## 오류 응답 시험 시작 안내 검토 — 2026-09-07

- 범위·처리: C06의 설치 구성·실행 내역·문서 미변경 사용자 확인을 실환경 평가에 반영하고 [C07 안내](../docs/04-confluence-read-tool.md#c07-error-response)를 준비함. `get_page`와 `_request`의 숫자 ID/허용 경로 검사, GET 고정, `_status_error`와 일반 연결 오류 처리를 대조함.
- 검토 결과: 숫자 문자열 `0`은 원본의 로컬 검사를 통과해 조회 요청에 사용될 수 있으나 사내 응답·문서 부재를 미리 확정하지 않음. 독립 검토도 읽기 전용 관찰과 `ok=true`·도구 미호출 시 시험 불성립을 확인함. 기존 권한 거절·연결 실패는 해당 범위만 재사용하고 미확인 HTTP 상태·timeout까지 PASS로 확대하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 151개·오류 0·검토 후보 0, `git diff --check` 통과.
- 미실행: 사내 시험 입력의 실제 호출·응답·모델 설명 확인. 기존 Markdown 4개만 변경했으며 코드·설정·의존성 변경, 코드 시험 재실행, 토큰 교체·서버 장애 유발은 없음.

<a id="c08-procedure"></a>

## 문서 지시 처리 시험 안내 검토 — 2026-09-07

- 범위·처리: C07 오류 코드·설명 보고를 `_status_error`와 대조하고 [C08 안내](../docs/04-confluence-read-tool.md#c08-document-instructions)를 준비함. Confluence Skill의 외부 자료 지시 무시 규칙과 Tool의 본문 반환·`untrusted_content`·잘림 처리를 확인함. 실행 Skill 자체는 수정하지 않음.
- 검토 결과: 합성 사실에 답변 왜곡·표식 부착·추가 숫자 시험 조회 지시를 섞고 새 대화의 정상 질문으로 검사함. 지시 문장까지 실제 반환됐는지와 정상 질문의 성공을 함께 확인하도록 함. 독립 검토의 비판적 인용과 지시 이행 구분, 단순 호출 횟수 대신 지시 유래 추가 호출 판정을 반영함. 비밀정보·외부 전송·쓰기 지시는 포함하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 153개·오류 0·검토 후보 0, `git diff --check` 통과.
- 미실행: 사내 문서 생성·조회·모델 답변·추가 호출 확인. 합성 한 건의 안내이며 모델·모든 injection 유형의 방어를 보증하지 않음. 기존 Markdown 4개만 변경하고 코드·설정·의존성 변경이나 코드 시험 재실행은 없음.

<a id="knowledge-routing"></a>

## 임베딩 없는 POC 조회 경로 보완 검토 — 2026-09-07

- 발견·범위: C08의 정상 본문·답변·추가 ID 0 조회 부재·링크 확인과 별도 query_knowledge_files 실패를 구분함. 기존 Native 가이드의 임베딩 우회 설명이 Native 의미 검색까지 해결하는 것으로 읽힐 수 있어 범위를 보완함.
- 공식 소스 대조: v0.11.3 `tools/builtin.py`의 query_knowledge_files는 임베딩 함수를 사용하고 `retrieval/utils.py`의 query_collection을 직접 호출함. 파일/소스 본문 처리의 우회 분기를 거치지 않음. search_knowledge_files는 파일명 검색, grep_knowledge_files는 문자열/정규식 검색, view_knowledge_file은 권한 확인 후 저장된 본문을 읽음. list_knowledge는 Knowledge ID만 반환한 경우 해당 ID를 지정해 파일 목록을 한 번 더 읽어야 함.
- UI·제어 대조: `utils/tools.py`의 knowledge 그룹과 `Models/BuiltinTools.svelte`를 확인함. 그룹 전체 OFF는 목록·검색·본문 조회도 제거하고 query 함수 단독 토글은 없음. `ModelEditor.svelte`의 System Prompt와 Save & Update 경로를 확인함.
- 처리·독립 검토: Prompt 원본에 Confluence ID 직접 조회·충분한 결과 뒤 추가 검색 생략·작은 합성 Knowledge의 파일 ID 식별 후 본문 읽기·임베딩 미검증 시 query_knowledge_files 미사용을 추가함. 독립 백엔드 검토의 함수 구분·파일 ID 확인 순서를 반영함. 지침이 함수 노출을 강제 차단하지 않음을 명시하고 기존 정책 Knowledge는 유지함.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 문서 20개·내부 링크 158개·오류 0·검토 후보 0, `git diff --check` 통과. 기존 Markdown 7개만 변경함.
- 미실행: 사내 UI 부분 추가·저장, C04 공통 문서와 P02 정책 질문 재확인, 실제 임베딩 설정·검색 복구. Git Prompt 준비를 WebUI 적용으로 기록하지 않으며 과거 v0.2 전체 지침 배포와 구분함. Python·Skill·도구 코드·설정·의존성 변경 및 코드 시험 재실행은 없음. 자료 조회 지침과 관련 Markdown만 변경함.

<a id="c09-procedure"></a>

## 조회 경로 재확인 기록과 C09 안내 검토 — 2026-09-07

- 범위·처리: 자료 조회 경로 섹션 부분 적용 후 C04·P02 정상 및 임베딩 오류 재발 없음이라는 사용자 보고를 STATUS·실환경 평가에 반영함. 이전 임베딩 실패와 당시 미실행 기록은 보존하고 의미 검색 복구·함수 미호출·전체 v0.2 배포로 확대하지 않음.
- 절차 대조: C09의 새 PAT 복구 조건, Tool의 개인 설정·실제 `/rest/api/user/current` 호출·HTTP 오류 매핑·인증 사용자 판정을 [시험 안내](../docs/04-confluence-read-tool.md#c09-token-rotation)와 대조함. [Atlassian 공식 안내](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html)의 개인 PAT 생성·이름 지정·만료·개별 폐기·생성 화면 이후 재표시 제한을 확인함.
- 독립 검토·반영: 기존 Claude Code용 토큰 보존, 시험용 토큰 정상 인증 후 해당 토큰만 폐기, WebUI의 폐기된 값을 유지한 실제 재호출, 새 토큰 복구 순서를 확인함. 원래 토큰 복원만으로 새 PAT 회전 PASS를 주지 않고 `authentication_failed`가 반드시 HTTP 401을 뜻하지 않음을 반영함. 일반 연결 실패·빈 설정·모델의 호출 없는 거절은 폐기 효과로 판정하지 않음.
- 검증 결과: Linux / Python 3.12.13에서 `python scripts/check_docs.py` 오류 0·검토 후보 0, `git diff --check` 통과. 기존 Markdown 4개만 변경함.
- 미실행: GPT의 사내 Prompt 등록 내용·질문 출력 직접 대조, PAT 생성·폐기·교체·실제 인증 호출·출력 비노출 검사. C09와 C07의 미확인 분기는 유지함. 코드·설정·Skill·의존성 변경 및 코드 시험 재실행은 없음.

<a id="status-reviews-20260907"></a>

## STATUS의 누적 점검 기록 이관 — 2026-09-07

다음은 전체 계획 최적화 전에 STATUS에 누적됐던 점검 기록입니다. 당시 확인 범위·결과·미실행 설명을 그대로 보존하며, 과거의 대기·다음 작업을 현재 실행 지시로 해석하지 않습니다. 최신 판정은 [평가표](scenarios.md), 현재 계획은 [STATUS](../docs/STATUS.md)를 따릅니다.

- 2026-09-07 P03의 창작 거절 보고를 전체 통과 조건과 구분해 부분 확인으로 기록함. 현재 평가표·후속 Jira/Rich UI 안내를 대조해 개인 기능 개발과 공용 파일럿 전 검증의 우선순위를 제안함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 합격 기준·실행 코드·서비스 설정은 변경하지 않았으며 사내 호출 직접 검사·코드 시험은 미실행.
- 2026-09-07 P02 호출 이름 보고를 직전 답변·근거 확인 및 평가표 기준과 대조해 해당 범위의 PASS로 반영함. P04의 Skill 선택·개별 호출 성공과 구분하고 list_knowledge 2회만으로 결함을 추정하지 않음. 독립 검토로 P03의 기존 합성 질문과 확인 불가·확인 방법 기준을 점검함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. GPT의 사내 화면·호출 원문 직접 검사와 코드 시험은 미실행.
- 2026-09-07 P02 답변·근거 보고를 합성 정책 v0.1의 2~5절과 대조함. 독립 검토로 내용 조건 충족과 호출 이력 미확인을 구분하고 기존 응답의 이름만 확인하도록 함. 향후 읽기 Tool 설명은 기존 승인 API/Broker 원칙과 일치함을 확인함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 실제 도구 호출·사내 설정 검사와 코드 시험은 미실행.
- 2026-09-07 두 지침 저장 보고를 제공한 원문·적용 안내·지침 개정 평가 기준과 대조함. 독립 검토로 이전 PASS 증거 보존과 개정 후 대기 전이를 확인하고, P02의 기대 근거를 합성 Knowledge v0.1의 2·3절과 맞춤. STATUS·Native 가이드·평가표만 변경해 문서 점검·`git diff --check`를 확인함. 등록 내용 직접 대조·사내 새 대화 평가·코드 시험은 미실행.
- 2026-09-07 DB 접속정보 미등록 보고를 기존 도구 미연결 보고·S05 기준과 대조함. 독립 검토로 미반영 Prompt·정책 답변 Skill·업데이트 원칙을 확인하고 원문 두 블록 전달, 사용자 추가 규칙 보존, 기존 조회 경로 포함 및 적용 원본 추적을 점검함. STATUS·Native 가이드·평가표만 변경해 문서 점검·`git diff --check`를 확인함. 실행 자산은 변경하지 않았고 사내 UI 갱신·행동 평가·코드 시험은 미실행.
- 2026-09-07 추가 도구 없음 보고를 기존 기능 OFF·Confluence 선택 및 S04/S05 기준과 대조함. 독립 검토로 S04를 구성 범위에서 판정하고 같은 설정·무해한 질문을 불필요하게 반복하지 않기로 함. DB 접속정보 유무는 별도 미확인으로 유지함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 UI·런타임 직접 검사와 코드 시험은 미실행.
- 2026-09-07 두 항목 OFF 보고를 직전 저장·새로고침 안내 및 앞선 Code Interpreter 상태와 대조함. 과거 ON 관찰을 보존하고 미응답인 추가 연결·접속정보 유무를 추정하지 않음. STATUS·평가표만 변경해 문서 점검·`git diff --check`를 확인함. 사내 UI·함수 목록·호출 원문 직접 검사와 코드 시험은 미실행.
- 2026-09-07 EES 기능 ON/OFF 보고를 기존 Native OFF 기준·S04/S05와 대조함. 독립 검토로 공식 v0.11.3 내장 Tool 노출의 추가 조건 및 Tools 선택과의 구분을 확인해 저장·재확인 안내를 보완함. STATUS·Native 가이드·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 기능 변경·외부 조회·명령 실행·호출 원문 검사와 코드 시험은 미실행.
- 2026-09-07 D07 정상 보고를 직전 재시작·확인 질문 안내와 대조해 반영함. 독립 검토로 남은 S04/S05 구성 확인을 다음 최소 단계로 정하고 기존 Native 가이드·모델 기능 UI 항목과 대조함. STATUS·평가표만 변경해 문서 점검·`git diff --check`를 확인함. 사내 재시작·화면·환경설정 직접 검사, S04/S05 실환경 확인·코드 시험은 미실행.
- 2026-09-07 D06의 20회 완료 보고를 기존 순차 요청 기준과 대조함. 기존 수동 기동·W04 및 D07 기준을 확인하고 독립 검토로 같은 창의 경로·환경설정 유지와 정상 종료 후 재실행 절차를 점검함. STATUS·직접 연결 가이드·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 UI·호출 원문 직접 검사, 이번 재시작·D07 및 코드 시험은 미실행.
- 2026-09-07 D05 보고를 직전 설정·새 대화 질문 안내와 대조해 해당 시험 범위로 반영함. D06의 기존 20회 기준을 수행할 최소 순차 절차를 준비하고 독립 검토로 요청 단위·실패 보존·집계 범위를 확인함. STATUS·직접 연결 가이드·평가표만 변경해 문서 점검·`git diff --check`를 확인함. 사내 UI·요청 직접 검사, D06 실행과 코드 시험은 미실행.
- 2026-09-07 D04 보고를 기존 두 메시지 절차와 대조함. 독립 검토로 직접 연결 가이드의 Memory 경로 불일치와 v0.11.3 관리자 모델 편집 경로를 확인해 보완함. STATUS·직접 연결 가이드·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. D05 설정·새 대화 시험 및 사내 화면·원본 요청 직접 검사와 코드 시험은 미실행.
- 2026-09-07 스트리밍 정상 보고를 D03의 순차 표시·완료 조건 및 직접 연결 가이드와 대조함. 이번 기반 GLM 응답만 판정하고 EES 문맥 시험·반복 안정성·재시작 결과와 구분함. STATUS·평가표만 변경해 문서 점검·`git diff --check`로 확인하며 사내 화면·원본 스트림 직접 검사와 코드 시험은 미실행.
- 2026-09-07 개인 Memory ON·빈 목록 보고를 기존 S03 질문 및 모델/개인 설정의 구분과 대조함. 독립 검토에서도 추가 질문 없이 이번 목록 관찰 범위로 판정하고 조회 오류 부재의 직접 검사·전체 DB 보장으로 확대하지 않는 것이 적절함을 확인함. 개인 전역 설정 변경을 추가 요구하지 않고 다음 기존 D03 확인으로 이어감. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 화면 직접 검사·설정 변경·코드 시험은 미실행.
- 2026-09-07 모델 Memory OFF 보고를 이전 S01 결과 및 확인한 Capabilities 제어 범위와 대조해 S02에 반영함. S03의 실제 저장소 부재와 분리하고 기존 개인 설정 안내의 목록 숨김·조회 오류 조건을 다음 단계에 적용함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 설정 변경·저장소 검사·코드 시험은 미실행.
- 2026-09-07 새 대화 재시험 보고를 이전 같은 대화·Chat History 조회 이력과 구분해 S01에 반영함. 독립 검토로 Native Memory 노출·자동 문맥 주입·응답 후 검토의 다른 조건과 개인 설정 OFF의 목록 숨김/조회 오류를 확인함. Capabilities UI·저장 경로와 대조해 기존 안내의 Memory OFF 범위를 명확히 함. Native 가이드·장애 안내·STATUS·평가표의 Markdown 4개만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 모델 기능 설정·Memory 저장소 검사·코드 시험은 미실행.
- 2026-09-07 BuiltinTools/ModelEditor의 Chat History 체크·저장과 백엔드 `builtinTools.chats`의 기본값/두 함수 노출 조건을 대조함. 독립 백엔드 검토로 현재 사용자 ID 필터와 별도 Memory 조건을 확인함. Native 가이드·장애 안내·STATUS·평가표의 Markdown 4개만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 설정 저장·재시험·Memory 저장소 검사 및 코드 시험은 미실행.
- 2026-09-07 같은 대화 응답 보고를 기존 합성 질문·S01 기준과 대조해 부분 확인으로 기록함. 다음 새 대화 질문에는 문자열을 다시 제공하지 않고, Chat History 조회·장기 Memory·다른 사용자 격리를 구분하도록 함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. GPT의 사내 화면·설정·실행 내역 검사와 코드 시험은 미실행.
- 2026-09-07 W02 사용자 보고를 netstat의 수신 행·로컬 주소 기준과 대조함. W03는 수동 기동의 경로/DB 재정의 검사, canary 검사기의 LOCALAPPDATA 고정 경로·읽기 전용 DB 조회, 기존 W04/C02 실환경 증거를 대조하고 독립 검토로 재사용 범위를 확인함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 명령·DB 검사·코드 시험을 새로 실행하지 않았고 같은 대화 문맥 시험은 대기임.
- 2026-09-07 Microsoft netstat/findstr 안내와 기존 W02 기준을 대조해 대체 명령을 준비함. 독립 검토에서 IPv6 포함·정확한 포트 필터·로컬/원격 주소 구분·출력 없음의 미판정 및 프로세스/프록시 범위를 확인함. 설치 안내·STATUS·평가표의 Markdown 3개만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 netstat 실행·포트 판정·코드 시험은 미실행.
- 2026-09-07 새 PAT 복구 보고를 C09의 세 단계 증거와 대조해 PASS로 반영함. C07 미확인 분기·전체 MVP Gate와 구분하고, 기존 W02 기준 및 설치 안내를 대조해 다음 작업을 정함. 독립 검토에서도 현재 장애 없이 수행할 수 있는 읽기 전용 W02 확인이 적절함을 확인함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 포트 확인·화면 직접 검사·코드 시험은 미실행.
- 2026-09-07 폐기 후 오류 두 필드·PAT 교체 안내 보고를 기존 C09 순서 및 `authentication_failed`의 복수 반환 경로와 대조해 반영함. C09 전체 PASS·HTTP 401 실측·Skill 로딩 확인으로 확대하지 않음. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 코드 시험과 GPT의 사내 인증·토큰 교체는 미실행.
- 2026-09-07 도구 미사용 설명과 재시도의 두 성공 필드를 이전 미호출 기록·C09 단계별 기준과 대조해 반영함. 폐기 대상은 시험용 PAT 한 건이고 WebUI에는 폐기된 값을 유지한 채 호출해야 한다는 기존 안내를 재확인함. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 코드·설정 변경, 코드 시험, GPT의 사내 인증·토큰 폐기는 미실행.
- 2026-09-07 모델의 도구 부재 설명을 실제 API 오류와 구분해 기록하고 원본 `check_access` 정의·개인 설정과 도구 선택의 구분을 기존 등록 안내와 대조함. 현재 대화의 선택 확인을 먼저 안내하며 코드·PAT 재입력·네트워크 수정으로 확대하지 않음. STATUS·평가표만 변경하고 문서 점검·`git diff --check`를 확인함. 사내 도구 목록·호출·새 PAT 인증 및 코드 시험은 미실행.
- 2026-09-07 부분 Prompt 적용 후 두 정상 질문의 사용자 보고를 기존 C04·P02·C08 및 전체 지침 개정과 구분해 반영함. C09 기준·Tool 인증/오류 처리·공식 PAT 안내를 대조하고 독립 검토를 거쳐 시험용 PAT만 폐기하는 절차를 준비함. 문서 검사와 미실행 범위는 [C09 안내 검토](../evals/confluence-offline.md#c09-procedure)에 기록함. 실환경 C09는 미실행이며 기존 업무용 PAT는 유지함.
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


<a id="mvp-plan-review"></a>

## 전체 계획 최적화 검토 — 2026-09-07

- 요청·범위: 사용자가 정책 문답보다 기능 연동·Rich UI 사용성을 우선하는 전체 계획 검토·최적화를 요청함. AGENTS·STATUS·Native 가이드·평가표·모델 운용 기준·README의 관리 경계를 대조했으며 실행 코드·공통 배포 Prompt/Skill·사내 설정 변경은 범위에 포함하지 않음.
- 발견: 평가표의 우선 검증·추가 구성 재평가·모든 호출 이력 확인 문구가 순차 전수 문답으로 확대되기 쉬웠음. 초기 2-Skill P01 기준이 현재 추가 구성과 맞지 않았고, 파일럿 최소 범위·비개발자 사용성/공유 완료 조건이 부족했음. STATUS에 이전 점검이 누적되어 현재 상태 탐색 비용이 커졌음.
- 처리: 실행 계획을 STATUS 한 곳에서 관리하고 Jira 읽기+첫 Rich UI+사용 안내를 한 단위로 묶음. Jira 정보가 지연되면 기존 Confluence를 활용하고, GitHub가 지연돼도 준비된 기능의 파일럿은 가능하도록 범위를 명시. EMS/APC/FDC·역할별 기능은 이후 수요가 확인된 업무부터 확장함.
- 검증 방식: 개인 기능 확인·공개 전 필수 확인·관련 변경/문제 진단·조건부 후속을 구분. P01 기준과 P04/S06 실행 시점을 정리하되 미확인 상태를 PASS로 변경하지 않음. 자료의 근거·실패·지시 분리와 P05/P06·계정/자원 격리·비밀 보호·읽기 제한은 유지. 모델만 바뀌었다고 인증/저장 시험을 자동 반복하지 않으며 실제 변경 영향을 기준으로 판단함.
- 사용성·진행 규칙: UX01~UX03으로 첫 사용·실제 Rich UI·팀원 Prompt/Skill 공유의 완료 조건을 추가. 실행 Tool 권한과 작성물 공유 권한은 분리함. GPT가 가능한 검사는 직접 수행하고 사내 확인은 짧게 묶어 요청하며, 단순 답변마다 호출 이름·독립 검토·재검사를 추가하지 않음.
- 보존: STATUS의 이전 최근 점검 8,394자를 위 이관 절에 그대로 보존함. 기존 날짜별 실환경 결과·과거 PASS/실패, 적용 원본 SHA, 현재 Confluence Tool·Prompt/Skill의 Git/배포 구분을 유지함. 새 문서·빈 폴더·공통 프레임워크를 추가하지 않음.
- 독립 검토: 제품 흐름·파일럿 범위와 검증 시점/항목 매핑, 변경 후 AGENTS·STATUS·Native·evals·versions의 일치를 별도로 검토함. STATUS의 P04~P10 대기 표기를 미완료로 바로잡아 P04 후속 분류와 일치시킴. 검토 범위에서 추가 차단 사항 없음. 공개 전 필수 조건과 파일럿 중 UX 확인을 구분하고 세부 HTTP 분기·성능 비교의 비차단 범위를 명시함.
- 최종 검증: Linux 사외 작업 환경에서 `python scripts/check_docs.py`는 문서 20개·내부 링크 193개, 오류 0·검토 후보 0. `git diff --check` 통과. 이전 실환경 결과 기록의 원문 불변, 이전 사외 증거 보존, 누적 점검 8,394자 전체 이관, 적용 원본 SHA 3종 유지, 변경 파일이 기존 Markdown 7개뿐임을 비교 확인함. STATUS는 15,500자에서 약 6,600자로 축소함.
- 미실행: 사내 Jira/GitHub API·WebUI Rich UI 렌더링·새 서버 배포·비개발자 사용·실제 공유 시험·모델 교체·코드 자동 시험. 이 문서 변경을 해당 기능의 구현·배포·PASS로 간주하지 않음.

<a id="rich-ui-results"></a>

## 검색·본문·근거 카드와 최적화 — 2026-09-07

- 기준 main: `028287e2ca77c3b14424b51a49871f025943554d`. 최신 AGENTS·STATUS 및 열린 PR 0개를 확인하고 기존 연동의 카드 보완만 준비함. 첫 화면·온보딩은 보류함.
- 환경: 사외 Linux / Python 3.12.13 / Pydantic 2.13.4 / Node 24.19.0. HTTP는 합성 응답이며 실제 PAT·업무 자료를 사용하지 않음. `tests/rich_ui_support.py`의 최소 DOM 모형을 공유하며 CSS 배치·실제 브라우저를 시험한 것으로 설명하지 않음.

### 변경과 확인 범위

- v0.1.3에서 검색·본문·오류 카드를 기존 Python 파일에 포함함. 성공한 검색에 검증된 `query`·실제 `selected_spaces`·`fetched_at`, 성공한 본문에 `fetched_at`만 추가함. 명시 Space → 사용자 기본 Space → 허용 Space의 실제 선택을 반영하고 실패한 입력으로 성공 범위·시각을 만들지 않음.
- 검색은 제목/ID/Space/버전/원문만 보이며 본문·요약은 미조회임을 알림. 실제 숫자 문서 ID로 선택적인 수동 초안을 만들고 입력 교체 안내·복사 질문을 제공함. 사용자가 처음부터 요약을 요청하면 get_page를 바로 이어서 사용할 수 있도록 함수 설명·Prompt를 맞춤.
- 본문은 받은 텍스트를 기본 접힘·높이 제한 영역에 표시하고 모델 context에 근거 문자열을 유지함. 잘림·매크로/첨부/표 배치 한계를 표시하고 원문 링크/문서 ID·키보드 초점을 제공함. HTML은 모델에 중복 전달하지 않고 카드/전체표 반복 지침도 정리함. 실제 모델 token·지연 개선 수치는 측정하지 않음.
- `_run`의 JSON 반환·연결 확인 JSON은 유지함. 공개 검색/get 반환부만 `(HTMLResponse, 원래 근거 데이터)`로 감싸고 표시 실패 시 JSON+안전한 `display_notice`로 복귀함. 기존 테스트는 tuple의 근거와 HTML 모두에서 본문·비밀 비노출 검사를 유지하도록 결과 추출만 갱신함.

### 실행 증거

| 명령·검토 | 실제 결과 |
|---|---|
| `python -m unittest discover -s tests -p test_confluence_ui.py -v` 최초 실행 | 새 검사 9 PASS / 2.829초, 구현/시험 실패 없음 |
| 공용 DOM helper의 초기 HTML 속성 반영 후 해당 화면 검사 | 9 PASS / 2.851초 |
| 문서 ID 접근성 이름·초안 안내 연결·본문 키보드 초점 보완 후 관련 검사 1개 | 1 PASS / 0.568초. 검색과 본문 속성을 같은 합성 검사로 확인 |
| 고유 확인 범위 | 새 9개 PASS: 검색/본문/연결 확인 반환 계약, 권한에 맞는 실제 범위/시각, PAT·본문 보존, 렌더 실패 JSON, 안전한 텍스트/링크, 정확한 ID·끝 LF/CRLF 차단, 수동 초안/복사 fallback, 빈 결과·실패·잘림, 외부 의존성 없음 |
| 호출·정적 대조 | 검색 1회, 본문은 기존 metadata 확인→본문 2회 요청 유지. Valves/UserValves·context·HTTP·상태 오류·문서 검증·check_access AST 동일. `_run` 변경은 성공 메타데이터만 추가 |
| 독립 읽기 전용 검토 | 실제 범위/본문 보존·원문·초안·오류 fallback·추가 호출/과설계 확인. 본문 필요 시 사용자 추가 클릭을 강제하던 설명을 수정하고 공통 Prompt 문구를 목록 카드로 한정함. Node 없는 환경은 DOM만 skip하도록 보완 |

최종 전체 변경에서 `python scripts/check_docs.py`는 25개 파일·421개 링크·오류 0·검토 후보 0이며 `git diff --check`도 통과함. 실제 브라우저 배치는 미실행이며 앞선 URL 보안 정책 차단을 우회하거나 반복하지 않음. 사내 API·WebUI 등록/화면·입력 반영·모델 근거 일치·사용성·Windows 복구는 미실행. C01~C09의 기존 증거와 완료한 저장·인증·토큰 폐기는 반복하지 않으며 [사내 카드 확인](../docs/04-confluence-read-tool.md#rich-ui-results)을 기존 흐름과 묶음.


<a id="search-error-guidance"></a>

## 2026-09-07 검색 조건 오류의 다음 요청 안내 — v0.1.5

- 기준 main: `f8ea51656d056b4bc17c50f17c34e6b455f23e26`. 최신 AGENTS·STATUS와 열린 PR 0개를 확인함. 사용자 요청에 따라 Rich UI 디자인은 후속으로 두고 기존 조회 실패의 다음 행동만 보완함.
- 발견: 검색 API의 HTTP 400도 `upstream_error`와 관리자 문의로만 안내하던 분기를 재현함. [Atlassian Server REST 8.9.1 공식 참조](https://docs.atlassian.com/ConfluenceServer/rest/8.9.1)는 `/rest/api/content/search`의 잘못되거나 누락된 CQL에 HTTP 400을 명시함. 이는 API 계약 참고이며 사내 9.2.21의 실제 응답을 관찰한 근거는 아님.
- 변경: 고정 API 경로를 기존 상태 오류 처리에 전달해 검색 400은 `invalid_query`와 검색어 변경·지속 실패 시 설정 확인, 비검색 400은 `invalid_request`와 요청 값·API 설정 확인을 안내함. 원인 단정·응답 원문 노출·같은 요청의 자동 재시도는 추가하지 않음. 빈 검색 결과는 정상 응답으로 유지함.
- 환경: 사외 Linux / Python 3.12.13 / Pydantic 2.13.4. 합성 HTTP 응답만 사용하며 테스트 harness가 실제 DNS·socket 접속을 차단함.

| 확인 범위 | 결과 |
|---|---|
| 코드 수정 전 새 시험 2개 | 4개 subtest FAIL. 검색의 HTTPError/상태 응답과 비검색 연결 확인/문서 조회 모두 `upstream_error`여서 기대한 구분이 없음을 재현 |
| 수정 후 새 시험 2개 + 영향받는 기존 시험 9개 | 11/11 PASS, 0.127초. 검색 400의 두 응답 경로·안내·오류 body 닫기, 비검색 400 구분, raw reason/body·PAT 비노출, 실패당 1회 요청 및 변경한 검색어의 정상 0건 응답 확인 |
| 함께 확인한 기존 9개 | 고정 검색 경로·limit, 잘못된 검색 입력/Space, CQL status 제외·문자열 처리, 본문 전 metadata 확인, 401/403/404/429/500/502/503, redirect 차단, network/timeout/TLS 안내 |
| 독립 읽기 전용 검토 | 변경 코드·시험의 경로 분리, raw 오류/PAT 비노출, HTTPError 닫기, 기존 상태 처리·호출 횟수 검토. 추가 수정이 필요한 문제 없음 |
| 문서·diff | `python scripts/check_docs.py`: 25개 파일·452개 링크·오류 0·검토 후보 0. `git diff --check` 통과 |

실행은 `PYTHONPATH=tests python -m unittest`에 `test_confluence_read.ConfluenceReadTests`의 위 11개 메서드를 지정함. 새 메서드는 `test_rejected_search_guides_query_change_without_retry_or_private_details`, `test_non_search_bad_request_is_not_a_query_or_pat_error`임. 전체 suite·UI/브라우저·완료한 사내 확인은 반복하지 않음. Skill·System Prompt·HTML/CSS·정상 조회·인증/설정·서버 실행 방식은 변경하지 않음. 사내 마지막 저장 보고는 v0.1.4이며 이번 v0.1.5는 다음 코드 적용 묶음에 포함할 준비본임. 실제 서버 400·모델의 안내 응답 성공이나 C07 전체 통과로 확대하지 않음.


<a id="plain-results"></a>

## 시험용 Rich UI 제거·일반 답변 전환 — 2026-09-09

- 기준 main: `99a9ee6584a3b23a2dd26ebb94ede079886b2831`. 사용자가 EES 프로그램 이름·로고, 기존 대화 유지와 Confluence/Jira/GitHub 조회 정상 확인 뒤 초기 기능 확인용 Rich UI 전체 제거를 요청함. 기존 등록 항목·연동·개인 설정을 유지하고 일반 답변으로 전환할 준비본이며 사내 반영 완료로 기록하지 않음.
- Confluence v0.1.6: `search_pages`·`get_page`가 `_run`의 검증·마스킹된 JSON을 직접 반환하도록 바꾸고 HTMLResponse·HTML/JavaScript/CSS 템플릿·표시 실패 분기를 제거함. 공개 함수·입력·Valves/UserValves 이름, 개인 PAT·암호화 확인·허용 Space·GET 경로·응답 제한은 유지함. 검증된 조회 범위·시각·문서 ID·원문 URL·본문·잘림·실패 코드는 일반 답변의 근거로 계속 반환함. `HTMLParser`는 저장 형식의 본문을 평문으로 추출하는 기존 역할이므로 보존함.
- 독립 HTML 참고 예제와 화면 전용 테스트를 제거함. 예제는 [당시 Git 원본](https://github.com/knadalkim-a11y/team-agent-poc/blob/99a9ee6584a3b23a2dd26ebb94ede079886b2831/agent-pack/skills/confluence-read/references/rich-ui-search-demo.html)과 위 날짜별 기록으로 보존함. UI 전용 DOM 시험은 폐기하고 유효한 검색 범위·시각·30자리 ID·원문·권한 조회 순서·실패 메타데이터 비노출 검사를 기존 `test_confluence_read.py`에 통합함. 일반 결과 helper가 모든 호출에서 문자열 JSON·PAT 비노출을 확인하므로 tuple/HTML로 되돌아가는 회귀도 검출함.
- 환경: 사외 Linux / Python 3.12.13 / Pydantic 2.13.4. 기존 런타임만 사용하며 의존성을 설치하지 않음. `python -m unittest discover -s tests -p 'test_confluence*.py' -v`: **85/85 PASS**, skip 없음, 0.362초. 최초 실행은 제거 대상 UI 테스트 파일이 남아 있어 15개 오류를 보고했으며 해당 파일 삭제를 완료한 뒤 위 결과로 재확인함. 네트워크 차단 합성 응답·합성 DB/키 검사이며 실제 사내 API·Open WebUI 저장·화면·사용자별 권한 검증은 수행하지 않음.
- 배포 안내는 기존 Tool 코드와 Skill·공통 Prompt를 같은 작업 묶음으로 교체하는 방식임. 기존 Tool ID·사용자 설정·대화 보존, 새 대화의 검색→본문·원문 확인을 명시함. 프로그램 재적용·서버 재시작·PAT 재발급·전체 권한 시험을 추가하지 않음. 새 UI 프레임워크·옵션·공통 API 동기화를 만들지 않음. 최종 공통 검수와 사내 결과는 [현재 평가표](scenarios.md#validation-timing)에서 구분함.
