# Jira 읽기·시스템별 현황 검증 기록

이 파일은 Jira 기능의 사외 검사 근거를 보존합니다. 현재 실환경 판정은 [평가표](scenarios.md), 적용 여부는 [STATUS](../docs/STATUS.md), 설치·사용은 [Jira 가이드](../docs/05-jira-read-tool.md)가 원본입니다. 코드·합성 데이터 시험은 실제 Jira 접속·WebUI 렌더링·사용자 권한의 성공을 뜻하지 않습니다.

<a id="initial-implementation"></a>

## 첫 구현 — 2026-09-07

### 범위와 완료 조건

프로젝트별 전체·미완료 현황 → 받은 최근 목록의 프로젝트/상태/담당자 필터·펼치기 → 이슈 상세·원문 열기를 한 업무 흐름으로 구현합니다. 사용자 제공 실제 프로젝트 키·내부 주소·토큰을 코드·문서·합성 시험에 넣지 않습니다. 초기 인증 후보는 Bearer이며 사용자가 보고한 Jira 8.5.12의 실제 인증 형식과 호환성은 미확인입니다. 기본 비활성 상태를 유지합니다.

사외 완료 조건은 정확한 프로젝트 허용목록·고정 GET 경로·개인 토큰 경계, 집계와 목록 범위 구분, 부분 실패·누락 필드·페이지 처리, HTML의 텍스트 처리와 사내 등록 안내가 서로 일치하는 것입니다. 실제 적용의 완료 조건과 분리합니다.

### 변경 영향에 따른 확인 범위

| 범위 | 중요한 조건 |
|---|---|
| 설정·자격증명 | 비활성/주소·목록 누락/암호화 미준비에서 요청 차단; 개인 토큰 사용·공통 상태에 토큰 미보관 |
| 조회 경계 | 허용 키 정확 일치; 임의 URL/JQL/메서드 미노출; 리디렉션 차단; 응답 이슈의 실제 프로젝트 검사 |
| 인증·실패 | 익명 성공 오인 방지; 인증·권한·미존재·timeout·잘못된 응답 구분; 토큰·상류 응답 원문 비노출 |
| 집계·페이징 | 검색 `total`로 집계; 미완료 정의 표시; 최근 페이지와 전체 수치 분리; 실패·누락을 0으로 치환하지 않음 |
| 화면·문맥 | 받은 목록만 필터; 페이지 추가는 새 대화 호출; 외부 데이터의 HTML/스크립트 실행 방지; 모델에도 조회 범위·부분 결과 전달 |
| 안내·운영 | 인증 미확인·비활성 기본값; 정확한 사내 허용키 설정; 새 Jira 필드 저장 확인; 실제 화면 미실행 표시 |

### 실행 증거

2026-09-07 사외 Linux·Python 3.12.13·Pydantic 2.13.4·Node 24.19.0에서 실행했습니다. 기존 Open WebUI 설치나 의존성은 변경하지 않았습니다.

| 확인 | 환경·명령 | 결과 |
|---|---|---|
| Jira 관련 자동 시험 | `python -m unittest discover -s tests -p 'test_jira*.py' -v` | 31/31 PASS (0.924초): API 계약/격리 21개, HTML 안전 처리·DOM 동작 10개 |
| 문서·내부 링크 | `python scripts/check_docs.py` | 문서 22개·내부 링크 216개, 오류 0·검토 후보 0 |
| 변경 공백 검사 | `git diff --check`와 새 파일 포함 staged diff 확인 | PASS |
| 코드·가이드·평가기준 대조 | 신규 Jira Tool·Prompt 조회 절·등록 안내·J01~J05·STATUS·버전 기준 | 아래 발견 2건 수정 후 관련 시험 통과. 실제 적용은 미확인 |

### 검토 발견과 처리

- 기준 원본: main `9dcdbf60a98124506140b0dca315d50223cfa0ed`. 시작 시 열린 PR 없음. 원격 31개 파일을 해당 커밋의 Git blob SHA와 대조한 독립 작업 폴더에서 구현했으며 기존 작업 폴더의 미완료 변경은 보존함. 직접 Git fetch는 인증 불가였고 연결된 GitHub 읽기 경로로 원본을 확보함.
- 독립 검토에서 동명이인 담당자가 표시 이름 기준으로 합쳐지는 문제를 발견함. 응답의 Jira `key/name`을 `assignee_id`로 보존하고, 필터도 식별자를 사용하며 중복 이름에 식별자를 함께 표시하도록 수정함. 두 사용자 합성 회귀시험으로 분리를 확인함.
- 요청한 본문 필드가 누락되어도 빈 본문으로 성공 처리하던 문제를 발견함. 본문 키 누락을 오류로 바꾸고, 명시적 `null`만 빈 본문으로 처리함. 담당자·우선순위·기한도 누락/잘못된 값은 미확인, 명시적 빈 값은 없음으로 구분하는 시험을 추가함.
- 집계와 목록의 건수가 조회 중 달라지면 전체 합계를 미확정으로 표시함. 개별 조회값을 동시점 스냅샷으로 간주하지 않음. 이슈 이동은 메타데이터 확인 전후로 허용 프로젝트와 키를 재검사함.
- 고정 GET·프로젝트 허용목록·사용자별 요청 상태·부분 실패·JSON 스크립트 이스케이프·`textContent`·원문 URL 경계를 검토함. Jira 전용 Tool과 화면을 단일 파일로 유지하고 별도 Skill·서버·UI 빌드 계층은 추가하지 않음.
- [Open WebUI v0.11.3 middleware](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/middleware.py)의 `process_tool_result`에서 `(HTMLResponse, dict)` 문맥 반환을 확인함. 사외 환경에는 FastAPI와 실행 가능한 Chromium이 없어 실제 WebUI/브라우저 렌더링 시험은 미실행. Node 검사는 경량 DOM 모형의 텍스트·이벤트 동작이며 실제 레이아웃·브라우저 격리 증거가 아님. 테스트용 대체 환경을 사내 호환성 PASS로 세지 않음.

### 재사용과 미실행

- 기존 W/D/Confluence와 정책 시험은 변경 영향을 받지 않는 PASS·과거 실패 증거를 재사용하며 전수 반복하지 않습니다. 새 Jira 도구의 인증·권한·저장 필드·화면은 해당 증거만으로 통과 처리하지 않습니다.
- **미실행:** Jira 8.5.12의 실제 Bearer 호환성, 사내 GET API·건수 일치·이슈 권한, 새 Jira 개인 설정의 실제 암호화 저장/계정 분리, WebUI v0.11.3 Rich UI 렌더링, 비개발자 사용성, 공용 배포.
- 호출 수·지연은 **미측정**입니다. 프로젝트 P개의 정상 경로 예상은 인증 1회 + 집계 2P회 + 목록 1회, 집계 동시 실행 최대 4개입니다. 합성 응답 처리 속도를 사내 성능으로 보고하지 않습니다.
- 각 수치는 호출 시점의 현재 사용자 가시 범위입니다. 여러 검색 응답의 시각 차이, 갱신 중 페이지 변화, 서버가 숨긴 이슈의 존재 여부를 추정하지 않습니다.

사내 확인은 [가이드의 짧은 확인 묶음](../docs/05-jira-read-tool.md#4-작은-사내-확인-묶음)에 따라 인증 형식 → 정상 프로젝트 한 흐름 → 대표 차단·실제 화면 순으로 진행합니다. 기존 업무용 토큰 폐기·재발급이나 관련 없는 저장·재시작 검사를 선행조건으로 추가하지 않습니다.

<a id="bearer-check-preparation"></a>

## Bearer 일회 확인 준비 — 2026-09-07

- 사용자 설명: Jira가 Confluence와 같은 인증 방식일 것이라는 추정. 실제 헤더나 성공 결과를 받은 것은 아니므로 Bearer 가정·미확인 상태를 유지함. 추가 메뉴 질문 대신 기존 토큰의 계정 확인 1회로 진행하도록 안내를 구체화함.
- 변경 범위: [check-jira-auth.ps1](../scripts/check-jira-auth.ps1), Jira 가이드·STATUS·versions·J01 안내·CHANGELOG. Jira Tool·화면·기존 기능 시험 코드는 변경하지 않음.
- 정적 검토: PowerShell 5.1 문법과 .NET HttpClient 호출, 고정 GET `/rest/api/2/myself`, 15초·64 KiB 제한, 자동 리디렉션/쿠키/기본 자격증명 비활성, HTTP/시스템 프록시 명시적 선택, 활성 사용자 응답 검사와 출력 제한을 대조함. 출력은 HTTP 상태·불리언·고정 단계 코드이며 토큰·주소·사용자·응답 본문·예외 내용을 출력하지 않음. 자원·보안 문자열·BSTR 정리와 실제 DB/파일 쓰기·토큰 폐기·자동 재시도 경로 부재를 확인함. 독립 정적 검토에서도 확정 결함 없음.
- 검증: 문서 점검과 새 파일 포함 diff 점검을 수행함. 기존 Jira 31개 합성 시험은 실행 코드 변경이 없어 재실행하지 않았으며 Confluence·서빙·저장·재시작 시험도 반복하지 않음.
- 미실행: 사외 작업 환경에 PowerShell/.NET 실행기가 없어 Windows 실행·통신·실제 Bearer 인증은 미실행. 정적 검토를 실행 성공으로 표시하지 않음. 향후 이 스크립트가 성공해도 해당 PC의 계정 확인만 인정하고, WebUI 저장·실행 네트워크·프로젝트 권한·화면 성공과 구분함.
- 전달: main 미병합 PR #2의 검수한 커밋에서 확인 스크립트만 임시 파일로 추출하도록 안내. 사용자의 기존 작업 브랜치·파일을 바꾸지 않으며 실행 정책을 우회하지 않음.

<a id="bearer-success-followup"></a>

## 인증 성공 반영과 등록 안내 — 2026-09-07

- 변경 범위: STATUS·Jira 가이드·versions·J01/실환경 증거·이 기록만 갱신함. 사용자 보고 `200 / True`의 판정 원본은 [계정 확인 기록](scenarios.md#jira-bearer-check)이며 당시 사외 검사·미실행 기록은 보존함.
- 대조: Jira의 실제 관리자/개인 설정 필드·대시보드 내 인증 호출, 기존 Confluence 저장 검사기의 고정 canary와 전체 사용자/Tool 순회, 완료한 플랫폼 증거의 재사용 범위를 확인함. 독립 검토에서도 기존 검사기를 그대로 실행하면 새 Jira 필드의 증거가 되지 않음을 확인해 안내에 반영함. 새 Jira 필드 저장 확인은 후속 등록 흐름에 남김.
- 검증: 문서 점검·diff 검사와 변경 파일 범위를 확인함. 인증 스크립트·Jira Tool·화면·자동 시험은 바뀌지 않아 기존 Jira 31개와 Confluence·저장·재시작 시험을 반복하지 않음.
- 미실행: GPT의 사내 API/PC 직접 검사·WebUI 등록·개인 설정·프로젝트 조회·화면 검증. 사용자 보고 성공을 해당 PC 계정 확인 이외의 완료로 확대하지 않음.

<a id="jira-storage-check"></a>

## 새 Jira 입력칸의 저장 확인 준비 — 2026-09-07

- 사용자 보고: Tool 등록·관리자 설정·Assistant 연결·합성 개인 PAT 저장/마스킹 완료. [실환경 관찰 원본](scenarios.md#jira-registration)을 갱신하며 DB 암호화 성공으로 확대하지 않음.
- 사외 환경: Linux, Python 3.12.13, cryptography 46.0.0. Windows용 전달 명령과 실제 사내 DB는 실행하지 않음.
- 변경: 기존 [check_confluence_canary.py](../scripts/check_confluence_canary.py)에 고정 `--jira` 모드와 관련 시험을 추가함. 기본 Confluence 동작·출력은 유지함. Jira 모드는 새 합성 값만 검사하고 정확히 하나인 `EES Jira Read`의 ID와 개인 설정 저장 키를 연결함. 전체 암호문 일치 1건·해당 Tool의 일치 1건·평문 부재가 함께 충족돼야 통과함.
- 소스·검토: [Open WebUI v0.11.3 tools.py](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/models/tools.py)의 `tool.id`·`tool.name`과 `user.settings.tools.valves` 구조를 확인함. Tool 선택과 설정 순회는 같은 읽기 트랜잭션을 사용함. 기존 파일 키·읽기 전용 SQLite와 WAL/journal 검사를 재사용하고 앱 초기화·API·DB/키 쓰기·값/ID/예외 출력 경로를 추가하지 않음. 구현 후 독립 diff 대조에서도 확정 결함 없음.
- 관련 합성 시험: `python -m unittest discover -s tests -p 'test_confluence_canary.py' -v`에서 21/21 PASS, 0.054초, 종료 코드 0. 새 값 정상/다른 Tool/이전 값/이름 누락·대소문자·중복/중복 저장/평문·WAL·journal/버전/출력 비노출과 기존 기본 동작을 확인함. 첫 실행의 시험 fixture에서 VACUUM 전 트랜잭션 종료 누락을 수정한 뒤 통과했으며 운영 코드 결함으로 기록하지 않음. Jira 업무 코드·화면 31개, Confluence 조회, 사내 인증·등록·재시작 검사는 변경 영향이 없어 반복하지 않음.
- 문서·범위: Jira 가이드·STATUS·versions·J01/등록 보고·CHANGELOG와 검사 코드/시험을 대조하고 문서 점검·diff 검사를 수행함. 추가 검사기 파일·의존 패키지·업무 Tool 갱신 없이 기존 검사기를 확장함.
- 미실행: 실제 사내 DB·키·Windows/uvx 실행, 새 필드 암호화·로그·사용자 격리·Jira 조회·화면. 통과 기준과 전달 명령은 [Jira 저장 확인](../docs/05-jira-read-tool.md#새-jira-개인-입력칸-저장-확인)을 따름. DB 검사 성공도 로그인 사용자 식별·모든 계정의 접근 격리나 물리 파일의 고정 시점 전체 스냅샷을 뜻하지 않음.

<a id="first-dashboard-followup"></a>

## 저장 통과·첫 화면 성공 반영 — 2026-09-07

- 변경 범위: Jira 가이드·STATUS·versions·J01/J02/J04/J05/UX02·실환경 기록·이 문서. 실행 코드·시험·사내 설정을 변경하지 않음.
- 대조: 사용자 보고 10개 출력값을 d24b47d 검사기의 딕셔너리 삽입 순서와 대조해 새 Jira 값의 DB/Tool 대상 검사 PASS를 확인함. 인증 실패 안내 후 실제 PAT로 정상 화면이 나왔다는 후속 보고를 반영함. [판정 원본](scenarios.md#jira-first-dashboard)은 사용자 보고 범위이며 GPT 직접 사내 실행이 아님.
- 검토: 독립 검토에서도 로그/재시작 false를 재시험 사유로 삼지 않고, 실제 대시보드 표시와 전체 집계·건수 일치·화면 조작·계정 격리를 구분함. 개별 `jira_check_access` 재성공이나 HTTP 401을 추정하지 않음. 해결된 인증 오류의 진단은 종료함.
- 사용자 화면 요구 검토: 현재 렌더러의 11~12px 보조 텍스트, 누적 전체 건수로 고정된 비교 축, 주요 목록 필드가 펼치기 뒤에 있는 구성, 받은 페이지 안의 필터·채팅으로만 새 조회하는 동선을 대조함. 기본 접근성 장치와 반응형/다크 대응의 존재를 확인하고 실제 접근성 측정 성공/실패로 확대하지 않음. [검토 방향과 v0.11.3 공식 근거](../docs/05-jira-read-tool.md#6-사용자-친화적인-화면과-유연성--개선-검토)에 현재 데이터만으로 가능한 개선과 Tool 검색 확장이 필요한 유연성을 구분함. 후속 채팅 이벤트는 확인 창·새 결과 메시지·완료 응답 부재라는 경계를 기록했으며 UI 코드는 변경하지 않음.
- 검증: 관련 문서 점검·diff 검사와 변경 파일 범위를 확인함. 기존 Jira 업무/화면 31개·저장 검사기 21개·Confluence/재시작 시험은 관련 코드 변경이 없어 반복하지 않음. 전체 시스템 비교·값 대조·화면 조작·비개발자 사용성·공용 배포는 미확인으로 유지함.

<a id="dashboard-design"></a>

## 대시보드 디자인·가독성 개편 — 2026-09-07

- 범위: Jira Tool v0.1.1의 `_render_dashboard`와 버전 표기, 관련 화면 시험·가이드·상태·평가기준. 버전 문자열을 제외한 렌더러 앞부분이 이전 원본과 정확히 같음을 비교하고 Python 구문을 확인함. API·인증·설정·응답 스키마·저장·Confluence 코드는 변경하지 않음.
- 구현: 이모지·장식 아이콘 없이 큰 집계 숫자·14px 본문/13px 보조 정보·차분한 명암과 여백을 적용함. 기본 미완료 비교와 전체 기준 전환에 맞춰 내림차순 정렬·축척을 함께 바꾸고 숫자를 병기함. 실패와 0건, 전체 집계와 받은 목록을 구분하고 부분 실패·건수 변동 경고를 보존함. 주요 목록 정보를 펼치기 전에 표시하며 필터 후 상세 펼침 상태를 유지함.
- 검토 발견·처리: 정확한 수정 시각이 hover에만 있어 터치에서 접근하기 어려운 부분을 발견해 펼친 상세에 추가하고 title 속성을 제거함. 상태·담당자·수정일은 기본 목록에서 확인함. 원문 URL 허용과 안전한 JSON/텍스트 삽입, 높이 알림 외 화면 통신 부재를 유지함.
- 환경: 사외 Linux, Python 3.12.13, Pydantic 2.13.4, Node 24.19.0. `python -m unittest discover -s tests -p 'test_jira_dashboard_ui.py' -v` **15/15 PASS, 1.520초**. 첫 실행에서 검사 변수명이 렌더러의 scope와 충돌한 시험 코드만 수정한 뒤 통과함. 제품 결함으로 세지 않음.
- 추가 범위: 명시적 건수 변동 경고를 보완한 뒤 `python -m unittest discover -s tests -p 'test_jira_dashboard_ui.py' -k count_drift -v` **1/1 PASS, 0.115초**. 220/221 합계 차이에서 전체 미완료·확인된 값·경고를 함께 유지함. 전체 15개를 다시 반복하지 않았으며 현재 파일의 시험 수는 16개임.
- 수정 시각 보완 후 기존 메타데이터 검사만 강화해 `python -m unittest discover -s tests -p 'test_jira_dashboard_ui.py' -k compact_summary -v` **1/1 PASS, 0.105초**. 접힌 주요 정보·펼친 분/초·title 없이 시각 제공을 확인했고 전체 검사는 반복하지 않음.
- 미리보기: 실제 개편 렌더러에 합성 프로젝트 8개·이슈 6개를 넣어 생성함. 대화 안의 표시에는 ID/CSS 범위와 테마를 맞추고 WebUI 높이 알림만 제거함. 실제 사내 주소·키·토큰은 넣지 않음. 엄격한 ID 조회를 둔 Node DOM 모형에서 미완료/전체 정렬 전환·프로젝트 선택·초기화·집계 값·외부 메시지 부재를 확인함. 스크린샷이나 실제 브라우저 검사로 간주하지 않음.
- 문서·재사용: 변경 안내·버전·실제 적용 원본과 평가표의 미확인을 대조하고 문서 점검·diff 검사를 수행함. 기존 API 21개·저장 검사기 21개·Confluence·사내 인증/DB/재시작 검사는 변경 영향이 없어 반복하지 않음. [기존 사내 v0.1.0 성공 보고](scenarios.md#jira-first-dashboard)는 유지함.
- 미확인: 실행 가능한 브라우저가 없어 320/736/1024px 실제 배치·다크/밝은 화면·키보드/터치·iframe 호환성은 미실행. v0.1.1 사내 WebUI 반영·집계 대조·실제 사용자 조작성·공용 배포도 미확인. 합성 DOM 검사를 사용성 PASS로 확대하지 않음.

<a id="dashboard-acceptance-followup"></a>

## 개편본 사내 확인 반영·다음 연동 준비 — 2026-09-07

- [사용자 확인 원본](scenarios.md#jira-dashboard-acceptance)을 직전 적용 안내 SHA와 전체 표시·대표 건수 대조·화면 조작 세 항목에 연결함. 기본 흐름 정상 보고를 받아 디자인/반복 확인을 종료하고 다음 Git 읽기 준비로 이동함. 모든 권한·본문·오류·공용 사용성 완료로 확대하지 않음.
- 변경은 Jira 가이드·STATUS·versions·평가/증거 문서에 한정함. 코드·설정·시험은 변경하지 않음. 문서 점검·diff 검사와 현재/과거 적용 원본 표현을 대조하며 기능·인증·저장·사내 검사는 반복하지 않음.
- 사내 Git 제품·버전·개인 인증·허용 저장소는 아직 미확인임. 개발 원본 저장소의 GitHub.com 연결을 사내 서비스로 가정하지 않으며 제품 확인 후 작은 PR/이슈 읽기 흐름을 정함. 신규 연동 코드·사내 통신은 미실행.

<a id="merge-review-fixes"></a>

## PR 통합 검토의 목록 오류·부분 범위 보완 — 2026-09-07

사용자가 열린 PR 전체 검토·병합을 요청함. PR #2 `29e27c87b3f18538ae610fc335342dabf44b3894`의 AGENTS·STATUS와 최신 누적 원본 PR #5 `abee68fb9cd0a161064026a784ef65b4118423c2`를 대조함. Jira 원본은 두 커밋에서 같은 blob이며 새 PR을 만들지 않고 기존 PR #5에서 수정함.

### 발견과 처리

- `_dashboard`는 목록 실패에 안전한 `listing.error.message`를 반환하지만 화면은 이를 버리고 “다시 조회”만 표시했음. v0.1.2는 메시지를 textContent로 표시하고 실패한 목록·정상 빈 목록·성공한 집계를 구분함. 인증·권한·호출 제한·페이지 범위 오류에 맞는 다음 행동을 보존함.
- 일부 프로젝트 집계 실패 시 성공한 프로젝트만으로 목록을 만든 뒤 next_start_at을 제공했음. 다음 호출에서 실패 프로젝트가 회복되면 같은 위치가 다른 목록 범위에 적용돼 누락/중복될 수 있었음. 부분 실패 첫 페이지는 받은 행과 성공 집계를 유지하되 다음 위치를 제공하지 않음. 정상 페이지의 후속 요청에서 일부 집계가 실패하면 목록 GET 전에 page_scope_changed로 중단하고 첫 페이지 재조회를 안내함.
- 화면은 부분 실패의 오래된 다음 위치도 표시하지 않음. 회복 후 첫 페이지 재조회에서 정상 다음 위치를 반환함. 기존 요청 스키마·개인 설정·인증·전송·읽기 제한은 유지하며 캐시·새 함수·상태 저장은 추가하지 않음. Jira Prompt와 가이드의 후속 조회 설명도 맞춤.

### 검증

Linux / Python 3.12.13 / Pydantic 2.13.4 / Node 24.19.0. 기존 합성 HTTP·DOM 모형에서 변경 범위 **7/7 PASS, 0.838초**. 신규 4개와 영향받는 기존 3개이며 실행 명령은 다음과 같음.

```text
python -m unittest discover -s tests -p 'test_jira*.py' -k partial_scope -k later_page_failure -k page_limit_and_next_page -k listing_error_guidance -k listing_failure_is_distinct -k exact_project_counts_are_independent -v
```

확인 범위: 오류별 텍스트 안내·HTML처럼 보이는 오류 문자열의 비실행·정상 집계 보존, 부분 첫 페이지의 다음 위치 제거, 후속 페이지의 줄어든 범위 요청 차단, 회복 후 처음부터 조회, 정상 페이지 이동. 변경 코드·시험·Prompt·가이드 diff를 대조하고 공백 검사를 통과함.

기존 전체 UI/기능 suite·인증·DB 저장·재시작·20회 안정성·Confluence·GitHub 검사를 반복하지 않음. 실제 사내 v0.1.2 등록·모델 선택·브라우저 표시·부분 실패는 미확인. 이전 v0.1.1 사용자 확인을 새 버전 성공으로 바꾸지 않음. [적용 범위](../docs/05-jira-read-tool.md#failure-followup-update), [통합 검토](scenarios.md#pr-stack-review).


<a id="followup-actions"></a>

## 후속 질문 넣기 — 2026-09-07

### 범위와 근거

사내 PC 접근을 기다리는 동안 준비할 개발 요청에 따라, 최신 main `b36cebcc9aed0deb6caa6ef7c6442d6da6f263c5`·열린 PR 0개와 AGENTS·STATUS를 확인하고 Jira 결과의 후속 질문 한 흐름을 선택함. 원본 WebUI·첫 화면/온보딩·추가 서버는 변경하지 않음. Windows 오류의 사내 영향·복구는 계속 미확인으로 유지함.

- v0.1.3 renderer에 본문 요약, 선택 시스템의 첫 목록, 원래 범위의 다음 목록 질문 넣기 버튼을 추가함. 기존 집계·필터·원문·펼치기 디자인을 유지하고 결과의 실제 키·확인한 cursor만 고정 질문에 사용함. 제목·본문·담당자·오류·URL을 요청문에 합성하지 않음.
- [WebUI v0.11.3 Chat](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/chat/Chat.svelte)에서 `input:prompt`는 입력창 `setText`만 수행하고 `input:prompt:submit`은 origin에 따라 즉시 제출할 수 있음을 대조함. [FullHeightIframe](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/common/FullHeightIframe.svelte)의 등록된 frame 메시지 경로를 사용하며 `window.args`·same-origin 허용·추가 API를 사용하지 않음. 공식 [Rich UI 설명](https://docs.openwebui.com/features/extensibility/plugin/development/rich-ui/#prompt-submission)보다 해당 태그의 코드 계약을 우선함.
- 기존 초안이 교체된다는 안내와 직접 보내기 절차를 버튼 주변에 표시함. 수신/성공 응답이 없는 경로이므로 입력 완료·조회 중·조회 성공으로 표시하지 않으며, 독립 HTML이나 메시지 예외에서도 복사 가능한 readonly 질문을 남김. 클릭·필터만으로 자동 전송하지 않음.
- 다음 목록은 원래 scope와 listing scope가 일치하고 프로젝트 집계 실패가 없으며, 다음 위치가 정수·허용 범위·반환 행 수·전체 건수와 일치할 때만 준비함. 화면의 시스템/상태/담당자 필터를 다음 API 범위로 바꾸지 않음. 새 프로젝트는 처음부터 조회하고 부분 실패·위치 미확인은 다음 버튼을 비활성화함. 마지막은 null과 받은 건수로 확인한 경우에만 안내함.
- Jira Prompt에 직접 지정 키로 상세 조회, 표시 순번을 실제 이슈 키로 해석, 상세 뒤에도 직전 성공 목록의 범위·위치를 유지하는 절차를 반영함. 입력 초안은 조회 결과가 아니며 실제 실행 시 기존 Tool의 권한 검사를 그대로 거침.

### 검사·검토 결과

Linux / Python 3.12.13 / Pydantic 2.13.4 / Node 24.19.0의 합성 HTML·DOM stub 검사임. 실제 iframe sandbox·WebUI 입력창·모델의 도구 선택·Jira 서버는 실행하지 않음.

| 검사 | 결과 |
|---|---|
| 새 후속 질문 7개 + 기존 HTML 안전 2개 + 영향받는 기존 6개 | 고유 **15개 PASS**, 3.750초. 실제 이슈 키·선택 프로젝트 첫 조회·단일/전체 원래 범위 next·실패/cursor/범위 불일치·standalone/bridge 예외·악성 키 확인 |
| 키 검증 보완 후 관련 2개 | **2개 PASS**, 1.072초. JS 정규식의 `$`가 마지막 개행 앞에도 일치하는 경계를 발견해 `trim()` 결과와 원본이 같은지 검사하고 LF/CRLF를 거부함 |
| HTTP·인증·설정·저장 경로 | 이전 main과 `_render_dashboard`·모듈 버전 설명을 제외한 AST가 동일. 기존 Jira API/인증/암호화 검사 증거 재사용, 해당 시험 재실행 없음 |
| 독립 코드·지침 검토 | 초안 메시지 종류·대상 키·페이지 범위·오류/빈 결과·수신 미확인 안내·과설계를 검토한 범위에서 중대한 문제 없음 |
| 문서·diff 검사 | 문서 25개·내부 링크 396개·오류 0·검토 후보 0, `git diff --check` PASS. 기존 문서만 갱신 |

선택 시험 준비 중 전체 범위 질문의 기대 문구·DOM 시험 변수 충돌을 정리하고 listing scope 불일치 차단을 보완한 뒤 위 결과를 얻음. 실제 사용자 실패 보고를 새 합성 PASS로 바꾸지 않음.

재현 시 `tests`를 import 경로로 두고 `test_jira_dashboard_ui`의 `JiraDashboardSafetyTests` 2개와 다음 DOM 메서드만 선택한다. 매 변경마다 전체 시험을 반복하는 목록이 아니다.

- 신규: `test_issue_question_uses_actual_row_key_without_untrusted_descriptions`, `test_project_question_starts_selected_project_even_without_local_rows`, `test_next_question_keeps_original_scope_and_cursor_after_local_filters`, `test_next_question_is_disabled_for_inconsistent_or_failed_page`, `test_question_remains_copyable_without_embed_or_after_bridge_exception`, `test_malformed_or_out_of_scope_issue_key_has_no_usable_question`, `test_malformed_project_key_cannot_become_a_chat_question`.
- 영향받는 기존: `test_exact_project_counts_are_independent_of_received_list`, `test_project_filter_does_not_claim_unloaded_project_is_empty`, `test_status_assignee_filters_and_reset_use_only_received_data`, `test_rendered_source_links_are_safe_and_frame_messages_only_resize`, `test_listing_error_guidance_is_visible_as_safe_text_without_retry_hint`, `test_partial_scope_keeps_rows_and_replaces_stale_next_hint_with_restart`.

### 적용 경계

현재 사내 저장 보고는 v0.1.2·이전 Jira 지침까지이며 v0.1.3·이번 지침은 Git 준비본이다. 사내 접속 복구 후 기존 Tool 코드·Jira 절을 한 번에 반영하고 [변경된 흐름](../docs/05-jira-read-tool.md#jira-followup-actions)만 확인한다. 키·DB·연동 설정·완료한 기본 화면/조회·20회 검사는 반복하지 않는다. 실제 입력 반영과 보내기 후 모델의 후속 조회는 **미실행**으로 남긴다.


<a id="mvp-usability"></a>

## MVP 조회 카드 보완 — 2026-09-07

### 범위와 검토

최신 main `f71c737be8b1037fda48a490bde581e14c390d6a`의 AGENTS·STATUS와 열린 PR 0개를 확인함. 사용자가 레퍼런스 활용을 승인하면서 유지보수·MVP를 우선하도록 요청함. 현재 실제 Rich UI가 있는 Jira 한 흐름만 선택하고, 이미 있는 반응형 카드·테마·집계·후속 질문은 유지함. 새 프레임워크·라이브러리·빌드·추가 서버·모델 호출은 도입하지 않음. 참고한 디자인 출처와 적용 방법은 [사용 가이드](../docs/05-jira-read-tool.md#jira-mvp-usability)에 함께 둠.

- Jira v0.1.4: 원문 링크와 질문 버튼의 스타일·이슈별 접근성 이름, 잘못된 링크 안내, 빈 필터 결과 안의 초기화·초점 복귀, 실패 프로젝트와 오류 설명의 연결을 보완함. 목록 실패의 빈 상태 색과 조회 시각·자동 갱신 안 됨 안내도 적용함.
- 원문은 상세 영역 안의 기존 위치에 두고, 필터 초기화는 하나의 `resetFilters` 함수를 재사용함. 새로운 조회나 입력 초안 발송을 추가하지 않음. 소스상 최소 높이는 44px이며 실제 터치 영역 실측과 구분함.
- 독립 검토는 실제 renderer·관련 시험 diff의 회귀·접근성 속성·URL 처리·과설계에 한정함. 범위 내 주요 결함을 발견하지 못함. `jira_tool.py`는 모듈 버전·renderer를 제외한 AST가 작업 시작 HEAD와 동일함. HTTP·인증·권한·저장·도구 스키마·Prompt는 불변이며 완료한 해당 검사는 재실행하지 않음.

### 변경 범위 검증

환경: Linux, Python 3.12.13, Pydantic 2.13.4, Node v24.19.0. 기존 DOM harness에 초점 추적만 추가하고 기존 시험 6개를 확장함. 새 시험 메서드는 만들지 않음.

| 검사 | 결과와 범위 |
|---|---|
| 아래 관련 기존 시험 7개 | **7개 PASS, 3.505초, 첫 실행**. 로컬 필터 복구 후 두 행·펼친 상세 보존, 집계 불변, 상태 초점 복귀·draft 미발송. 실제 0건/실패의 빈 영역은 초기화 없음. 미수신 프로젝트 안내·원문 안전 속성/접근성 이름·실패행 오류 연결·조회 시각 문구 확인 |
| 문서·diff | `python scripts/check_docs.py`: 25개 파일·405개 링크, 오류 0·검토 후보 0. `git diff --check` PASS |
| 브라우저 합성 화면 | **미실행**. Cloud Browser 연결 후 합성 로컬 HTML 탐색을 시도했으나 URL 보안 정책이 차단함. 우회·별도 브라우저 실행은 하지 않음. CSS 배치·높이 실측·실제 키보드/보조기술 동작은 확인하지 못함 |
| 사내 WebUI·Jira·모델·Windows | **미실행**. 사내 PC 접근 불가. 신규 v0.1.4 적용 성공·실사용성·장애 복구로 판정하지 않음 |

검사 범위 재현 명령(재실행 요구가 아님):

```bash
PYTHONPATH=tests python -m unittest -v \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_rendered_source_links_are_safe_and_frame_messages_only_resize \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_link_protocol_and_url_credentials_are_rejected \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_status_assignee_filters_and_reset_use_only_received_data \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_project_filter_does_not_claim_unloaded_project_is_empty \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_listing_error_guidance_is_visible_as_safe_text_without_retry_hint \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_failed_project_is_not_zero_or_complete_total \
  test_jira_dashboard_ui.JiraDashboardDOMTests.test_zero_counts_and_failures_have_stable_distinct_comparison_rows
```

사내 마지막 저장 보고는 v0.1.2·이전 Jira 지침임. 이번 v0.1.4는 앞선 v0.1.3 후속 질문 준비와 함께 한 번에 적용하며, 실제 확인은 [변경 조작](../docs/05-jira-read-tool.md#jira-mvp-usability)에 묶음. 이전 기록·실환경 판정은 유지하고 별도 검수 문서나 PR은 추가하지 않음.


<a id="rich-ui-removed"></a>

## 시험용 Rich UI 제거 — 2026-09-09

- 사용자 요청: 기존 기능 확인용 UI를 모두 제거하고 향후 업무별로 하나씩 새로 설계함. Jira API·기존 개인 PAT/관리자 설정·도구 ID/함수 인자는 유지하며 현재 조회 성공을 제거본의 사내 적용 성공으로 바꾸지 않음.
- 변경: v0.1.6에서 jira_dashboard의 HTMLResponse/표시 실패 분기·전체 HTML/CSS/JavaScript 차트/필터/질문 버튼을 제거하고 기존 마스킹 JSON 문자열을 반환함. _dashboard의 화면 필터 안내를 받은 페이지의 범위 설명으로 바꾸며 집계/페이지/본문/권한/네트워크 계약은 유지함. 기존 사용 지침은 일반 답변·표·원문 링크로 정리하고 과거 화면/검증 이력 링크를 보존함.
- 검사: Linux/Python 3.12.13/Pydantic 2.13.4에서 `python -B -m unittest discover -s tests -p test_jira_read.py -v` 25/25 PASS. 기존 API/권한/개인 토큰/HTTPS/페이지/오류 23개와 공개 jira_dashboard의 정상 집계/조회 범위/원문/다음 페이지 및 부분 실패/미확정 수치/안전한 오류 JSON 2개를 확인함. 실제 사내 등록/새 대화 출력은 아직 미실행임.
- 정리: 삭제한 test_jira_dashboard_ui.py의 DOM/차트 시험은 제거한 구현 전용이며 현재 회귀 대상에서 제외함. 과거 결과는 이 기록과 Git 원본에 유지함. 새 테스트 파일·UI 대체 계층·표시 토글·서비스·회사 환경 의존성 설치를 추가하지 않음.

- Windows/Linux CI 2차 [34308547669](https://github.com/knadalkim-a11y/team-agent-poc/actions/runs/34308547669), 원본 `c6dcffc1dfdcaeb45f938ac60713aac7dd10c02c`: Confluence 85개는 Windows에서도 통과했으나 Jira 25개 중 공개 async 반환 검사 3개가 실패함. 시험의 socket.connect 차단을 건 뒤 asyncio.run이 Windows 이벤트 루프의 내부 socketpair를 만들려다 차단됐으며 실제 Jira 요청 실패가 아님. 테스트 setUp에서 네트워크 차단 전에 기존 asyncio.Runner/루프를 만들고 같은 Runner로 호출하도록 고침. 시험 동안 DNS/socket 가드와 전송 가로채기를 유지하고 종료 cleanup을 보장함. 생산 코드·이벤트 루프 정책은 변경하지 않음. Linux Python3.12.13에서 Jira 25/25 재검사 PASS, 0.164초. 같은 구조의 GitHub 시험도 한 번에 보완하며 수정 후 Windows CI로 확인함.
