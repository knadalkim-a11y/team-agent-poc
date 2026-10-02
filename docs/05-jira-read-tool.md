# Jira 읽기·CR 목록·첨부 확인

2026-10-02 원본 **v0.2.0**은 기존 읽기 기능에 실제 프로젝트·상태·날짜 필드 조회, 조건이 제한된 CR 목록, 필수 첨부 존재·접근 확인을 추가합니다. 기존 Native 도구 ID·ACL·개인 PAT를 사용하며 별도 도구나 전문 Assistant를 만들지 않습니다. Git 변경은 사내 등록 코드 적용을 뜻하지 않습니다. 실제 적용 여부는 [STATUS](STATUS.md)를 따릅니다.

Jira 프로젝트를 시스템 구분으로 사용해 전체·미완료 건수를 비교하고, 최근 이슈를 좁혀 본 뒤 상세 내용과 원문을 확인합니다. 실행 원본은 [jira_tool.py](../agent-pack/skills/jira-read/scripts/jira_tool.py), 검증 근거는 [Jira 검증 기록](../evals/jira-offline.md), 실제 적용 여부는 [STATUS](STATUS.md)에서 관리합니다.

## 1. 기존 환경·인증 확인 이력

사용자 보고 제품은 **Jira 8.5.12, build 805012, sha1:156decd**입니다. 2026-09-07 기존 개인 토큰으로 HTTP 계정 확인을 실행한 뒤 `HTTPStatus=200`, `BearerAuthenticated=True`를 보고받아 **해당 PC의 Bearer 인증 호환성을 확인**했습니다. Server/Data Center 구분과 토큰 발급 구현은 미확인입니다. 공식 내장 PAT의 지원 시작 버전과 현재 환경의 실제 성공을 구분합니다. [Atlassian PAT 안내](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html)

2026-09-07 이후 기존 보고에서는 [등록·마스킹](../evals/scenarios.md#jira-registration)에 이어 [새 필드 DB 저장 검사와 실제 토큰으로 첫 대시보드 표시](../evals/scenarios.md#jira-first-dashboard)까지 확인됐습니다. 완료한 인증·등록·저장 확인은 반복하지 않고 전체 시스템 비교 흐름으로 진행합니다. 아래 비활성 등록·저장 절차는 새 환경을 준비할 때 사용하며 배포 원본의 기본값은 비활성입니다. 실제 토큰값·내부 주소·프로젝트명은 채팅이나 Git에 기록하지 않습니다. 인증 확인 때문에 업무용 토큰을 폐기·재발급하거나 Jira를 업그레이드하지 않습니다.

### 기존 토큰으로 한 번 연결 확인

현재 사용자 환경에서는 완료한 절차입니다. 아래 명령은 다른 환경에서 처음 확인하거나 인증 경로가 달라졌을 때만 사용합니다.

[check-jira-auth.ps1](../scripts/check-jira-auth.ps1)은 Windows PowerShell 5.1 이상에서 실행하는 읽기 확인입니다. Jira 기본 주소와 개인 토큰을 실행 시 입력하며 토큰 입력은 숨깁니다. `GET /rest/api/2/myself` 한 곳만 호출하고, 리디렉션·쿠키·Windows 기본 인증·자동 재시도를 사용하지 않습니다. WebUI·DB·설정을 변경하거나 토큰을 파일에 저장하지 않습니다. .NET 기본 TLS 검증을 유지하고 응답은 64 KiB·시간은 15초로 제한합니다.

최초 구현은 [PR #2](https://github.com/knadalkim-a11y/team-agent-poc/pull/2)에서 관리했습니다. 배포할 때는 검수한 main 커밋을 사용합니다. 기존 저장소에서 fetch 후 확인 스크립트만 임시 파일로 꺼내면 작업 브랜치나 기존 파일을 바꿀 필요가 없습니다. 아래 `git show`의 커밋은 전달 시 검수한 원본 SHA로 고정합니다.

```powershell
Set-Location "$env:USERPROFILE\team-agent-poc"
# 새 창이면 기존 사내 Git 프록시 값만 이 창에 입력
$gitProxy = Read-Host 'Git proxy URL'
git -c "http.proxy=$gitProxy" fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
$jiraSource = '<REVIEWED_COMMIT_SHA>'
$jiraCheck = Join-Path $env:TEMP 'ees-check-jira-auth.ps1'
$jiraScript = git show "${jiraSource}:scripts/check-jira-auth.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Script read failed' }
$jiraScript | Set-Content -Encoding UTF8 $jiraCheck
& $jiraCheck
```

기존 창에 `$gitProxy`가 있으면 재입력 줄은 생략합니다. Jira 기본 주소는 필요한 컨텍스트 경로까지만 입력하고 `/rest/api/2`는 붙이지 않습니다. Jira가 승인된 `http://` 전용 주소라면 마지막 실행을 `& $jiraCheck -AllowHttp`로 바꿉니다. 네트워크상 Windows 시스템 프록시가 필요한 경우에만 `-UseSystemProxy`를 추가합니다. Git 프록시를 Jira에 자동 재사용하지 않으며 실행 정책이 차단하면 정책을 우회하지 않고 사내 승인 실행 방식으로 진행합니다.

성공 출력은 `HTTPStatus=200`과 `BearerAuthenticated=True`입니다. 실패하면 `HTTPStatus`(받은 경우)·`BearerAuthenticated=False`·`CheckStage`만 보고 원인에 맞춰 다음 단계를 정합니다. 예외·응답 본문·사용자 식별자·주소·토큰은 출력하지 않습니다. 성공은 **해당 PC의 Bearer 계정 확인**만 뜻하며 프로젝트 권한·WebUI 네트워크/저장·실제 조회 성공은 이후 흐름에서 확인합니다.

## 2. 사용할 수 있는 업무

| 화면·질문 | 제공 범위 |
|---|---|
| “시스템별 Jira 이슈 현황 보여줘” | 관리자가 허용한 프로젝트별 전체·미완료 건수와 최근 이슈 목록 |
| “SYSA 프로젝트 이슈만 보여줘” | 지정한 허용 프로젝트의 현황·최근 목록을 새로 조회 |
| “SYSA-123의 상세 내용과 원문 보여줘” | 해당 이슈의 설명·상태·담당자 등과 Jira 원문 링크 |

위 키는 합성 예시입니다. Assistant가 조회 결과의 프로젝트별 집계와 최근 이슈 목록을 일반 답변·표로 설명하고 이슈 키·제목·원문 링크를 제공합니다. 다른 프로젝트·다음 페이지·이슈 본문은 같은 대화에서 요청합니다. 목록의 상태·담당자 분포는 받은 페이지에만 해당하며 전체 집계로 확대하지 않습니다.

프로젝트별 건수는 검색 API의 `total`을 사용하며, 미완료는 `statusCategory != Done` 기준입니다. 처음 적용할 때 사내 워크플로의 완료 구분과 맞는지 한 번 비교합니다. 최근 이슈는 수정일 내림차순·키 오름차순이며 기본 30건, 최대 50건씩 가져옵니다. 목록에서 보이는 상태·담당자 분포를 프로젝트 전체 분포로 설명하지 않습니다.

모든 결과는 **조회한 개인 계정이 볼 수 있는 범위**입니다. 관리자라는 업무 역할만으로 다른 계정이 볼 수 없는 이슈까지 집계하지 않습니다. 프로젝트·이슈 권한에 따라 결과가 달라지며, 집계 실패는 `0건`이 아닌 미확인으로 표시합니다. 여러 API 결과는 동시점의 고정 스냅샷이 아니므로 조회 중 변경으로 수치·페이지가 달라질 수 있습니다.

## 3. 관리자 등록과 개인 설정

1. 기존 `EES Jira Read`가 있으면 `Native 모델·도구 관리` → 도구에서 같은 ID의 코드를 검수한 [현재 Python 원본](../agent-pack/skills/jira-read/scripts/jira_tool.py)으로 갱신하는 적용안을 준비합니다. 신규 환경에서 도구가 없을 때만 등록하고, 새 개인 설정 확인까지 `ENABLED=false`로 유지합니다. 실제 사내 반영은 별도 승인 대상이며 Git 갱신만으로 WebUI에 적용되지 않습니다. 최초 등록·표시를 확인한 원본은 [ce982de5의 Tool](https://github.com/knadalkim-a11y/team-agent-poc/blob/ce982de5e83a26421297e502e7f780365d7a18d3/agent-pack/skills/jira-read/scripts/jira_tool.py)입니다.
2. 아래 관리자 설정에 계정 확인에 성공한 사내 기본 주소와 **정확한 프로젝트 키 목록**을 입력합니다. HTTPS 인증서 검증을 유지하며 승인된 기존 접속 설정을 재사용합니다. `ALLOW_HTTP`는 기본 `false`이고, 별도로 승인된 HTTP 전용 환경에만 해당합니다. 키 접두사나 와일드카드로 프로젝트를 자동 허용하지 않습니다.
3. 기존 WebUI의 버전·키·DB·암호화 경로가 같다면 이미 확인한 저장·재시작 증거를 재사용합니다. 새 Jira 개인 PAT 필드는 가짜 값으로 마스킹과 해당 Tool의 개인 설정 한 건의 암호화 저장을 확인합니다. 아래 [Jira 전용 확인](#새-jira-개인-입력칸-저장-확인)을 사용하고 기본 Confluence 모드의 결과를 Jira 검증으로 간주하지 않습니다. 저장 경로나 키가 바뀌었다면 영향받는 검증만 추가합니다. [기존 저장 검증 원칙](04-confluence-read-tool.md#3-실제-pat보다-먼저-암호화-검증)
4. 확인 후 각 사용자가 Jira 도구의 **개인 설정**에 본인 토큰을 입력합니다. 관리자 공통 설정·채팅·HTML에 넣지 않습니다. 기존 Confluence PAT 설정은 그대로 유지합니다.
5. 승인된 사용자에게 기존 Native 도구의 읽기 권한을 지정합니다. 일반 대화에서는 허용된 모델·도구를 선택하며 전문 Assistant 프리셋이 필요하지 않습니다. 업무 자동 조회는 워크스페이스의 도구 계약과 현재 Native 읽기 승인을 확인합니다. 함수 코드·설정·계약이 바뀌면 기존 승인을 그대로 사용하지 않습니다.
6. 위 조건이 충족되면 `ENABLED=true`로 저장하고 평소 접근하는 프로젝트 하나의 현황을 요청합니다. 대시보드 조회에 사용자 인증 확인이 포함되므로 별도 연결 확인 질문을 직전에 반복하지 않습니다. 실패하면 오류 코드·메시지만 확인하며 토큰이나 응답 원문을 공유하지 않습니다.

새 개인 설정은 새 채팅 → 통합 → 도구 → `EES Jira Read` 옆 밸브에서 엽니다. `PAT`에 Jira에서만 쓸 가짜 값 `EES-JIRA-CANARY-20260907-B92F6A`를 저장하고 다시 열어 마스킹을 확인합니다. 현재 사용자 환경에서는 이 등록·마스킹까지 완료 보고가 있으므로 반복하지 않습니다. 실제 토큰 입력 전 새 필드의 저장 확인만 진행하며 기존 Confluence canary·재시작·키 백업을 반복하지 않습니다.

| 관리자 Valves | 기본값·의미 |
|---|---|
| `ENABLED` | `false`; 인증·저장 조건을 확인한 뒤 활성화 |
| `JIRA_BASE_URL` | 빈 값; 필요한 context path까지의 기본 주소. `/rest/api/2`나 이슈 URL은 제외 |
| `ALLOWED_PROJECTS` | 빈 값이면 차단; 승인된 정확한 키를 최대 20개까지 쉼표로 구분. 예: `SYSA,SYSB` |
| `ALLOW_HTTP` | `false`; 승인된 HTTP 전용 환경에서만 명시적으로 허용. 전송 암호화는 제공되지 않음 |
| `MAX_RESULTS` | `30`; 목록 한 페이지 최대 `50`건 |
| `MAX_CR_PAGES` | `10`; CR 조회 한 번의 페이지 상한 `1~20`. 초과 시 부분 결과 |
| `MAX_ATTACHMENTS` | `50`; `1~100`. 단일 이슈 첨부 상한이자 CR 배치 한 번의 전체 접근 확인 예산 |
| `TIMEOUT_SECONDS` | `15`; 개별 연결·읽기 제한이며 전체 조회의 절대 시간 제한과 다름 |
| `USE_ENV_PROXY` | `false`; 확인된 환경 프록시 경로가 필요할 때만 활성화 |
| `CA_BUNDLE_PATH` | 빈 값; 필요한 경우 승인된 추가 CA 파일. HTTPS 인증서 검증은 유지 |
| `MAX_RESPONSE_BYTES` / `MAX_DESCRIPTION_CHARS` | 응답 기본 1 MB·본문 6,000자. 크기 초과와 본문 잘림은 구분해 표시 |

사용자 UserValves의 `PAT`는 비밀번호형 개인 입력란입니다. 비밀번호형 표시만으로 저장 암호화가 입증되지는 않습니다. Tool의 암호화 활성화·키 검사도 실제 저장 증거를 대신하지 않습니다. 기존 DB나 키를 재생성하지 않습니다.

### 새 Jira 개인 입력칸 저장 확인

현재 사용자 환경에서는 이 검사 통과와 실제 토큰 적용 후 대시보드 표시를 확인했습니다. 아래 절차를 반복하지 않으며 원본·출력·앞선 인증 실패 안내는 [실환경 기록](../evals/scenarios.md#jira-first-dashboard)에 보존합니다.

기존 [check_confluence_canary.py](../scripts/check_confluence_canary.py)에 `--jira`를 붙여 새 Jira 가짜 값만 검사합니다. 기존 파일명·기본 Confluence 동작을 유지하며 별도 검사기·암호화 구현을 만들지 않습니다. 도구 이름 `EES Jira Read`와 일치하는 항목이 정확히 하나일 때 그 내부 ID의 개인 설정에 저장된 가짜 값을 확인합니다. 다른 도구에만 저장되거나 중복된 값·도구, 평문 저장은 통과하지 않습니다. 사용자 ID나 실제 저장값을 출력하지 않으며 특정 사용자 계정의 식별·전체 계정 격리 시험을 대신하지 않습니다.

서버·비활성 Jira Tool·저장한 가짜 값을 유지한 채 Git 저장소 폴더의 PowerShell에서 실행합니다. 기존 창의 `$gitProxy`를 재사용하고, 새 창이면 같은 사내 Git 프록시만 입력합니다. 아래 원본 SHA는 전달 시 검수한 커밋으로 고정합니다.

```powershell
Set-Location "$env:USERPROFILE\team-agent-poc"
if (-not (Get-Variable gitProxy -ValueOnly -ErrorAction SilentlyContinue)) {
    $gitProxy = Read-Host 'Git proxy URL'
}
git -c "http.proxy=$gitProxy" fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
$jiraCheckSource = '<REVIEWED_COMMIT_SHA>'
$jiraStoreCheck = Join-Path $env:TEMP 'ees-jira-storage-check.py'
$jiraStoreCode = git show "${jiraCheckSource}:scripts/check_confluence_canary.py"
if ($LASTEXITCODE -ne 0) { throw 'Checker read failed' }
$jiraStoreCode | Set-Content -Encoding UTF8 $jiraStoreCheck
uvx --offline --no-python-downloads --python 3.11 --from "open-webui==0.11.3" python $jiraStoreCheck --jira
```

이 명령은 기존 캐시의 고정 WebUI Python 환경을 사용합니다. 네트워크·앱 초기화·DB/키 쓰기 없이 기존 파일 키와 SQLite를 읽습니다. 캐시가 없어 실패하면 외부 다운로드나 다른 버전 설치로 진행하지 않고 오류 코드로 실행 환경을 확인합니다. 파일 키·DB 위치 등 기존 환경 전제는 [Confluence 저장 확인](04-confluence-read-tool.md#3-실제-pat보다-먼저-암호화-검증)과 같습니다.

정상 기준은 `CheckCompleted=true`, `TargetToolMatches=1`, `TargetEncryptedCanaryMatches=1`, `EncryptedCanaryMatches=1`, `PlaintextCanaryMatches=0`, `PlaintextInDatabaseFiles=false`, `DatabaseCheckPassed=true`입니다. DB·존재하는 WAL/journal의 읽기 시점 범위이며 `DatabaseFilesChecked`는 존재하는 파일 수에 따라 다릅니다. `LogsChecked=false`, `RestartPersistenceChecked=false`는 이번 명령의 범위 밖이라는 표시입니다. 동일 구성의 기존 플랫폼 검증을 재사용하며 이 값을 바꾸기 위해 과거 시험을 반복하지 않습니다.

출력 결과를 확인한 뒤 개인 PAT의 가짜 값을 기존 실제 토큰으로 교체하고 `ENABLED=true`로 활성화합니다. 실패 결과에서는 실제 토큰을 넣지 않고 비식별 결과만 확인합니다. 이후 평소 접근하는 프로젝트 한 곳의 현황 조회에 인증·집계·목록·화면 확인을 묶습니다.

## 4. 작은 사내 확인 묶음

첫 대시보드 표시를 확인한 현재 환경에서는 “허용된 전체 Jira 프로젝트의 전체 이슈와 미완료 이슈 건수를 시스템별로 비교하는 대시보드를 보여줘”로 진행합니다. 등록한 시스템이 모두 표시되는지와 `집계 실패`·`전체 집계 미완료` 안내 유무를 먼저 확인합니다. 표시 성공을 전체 건수 정확성·필터/펼치기/원문 조작 성공으로 확대하지 않습니다.

인증 형식을 확인한 뒤 **평소 접근하는 프로젝트 하나**에서 연결 → 건수 비교 → 목록 → 상세·원문을 한 번의 흐름으로 확인합니다. 같은 계정·같은 조회 조건으로 Jira 검색 화면과 전체·미완료 건수를 비교하고, 차이가 있으면 조회 시각·완료 정의·권한부터 확인합니다. 필요한 경우 같은 대화에서 특정 이슈 본문 또는 다음 목록을 요청합니다.

정상 흐름이 된 뒤 허용되지 않은 프로젝트나 접근할 수 없는 이슈 하나로 차단·다음 행동 안내를 확인합니다. 장애를 만들거나 정상 토큰을 폐기하지 않습니다. 일반 사용자 공개 전에는 해당 Jira 도구의 권한·개인 설정 분리와 비개발자 한 명의 시작·필터·오류 이해를 확인합니다. 이전 W/D/Confluence PASS는 관련 변경이 없으면 반복하지 않습니다.

기록은 적용 원본 커밋·날짜, 정상/부분/실패, 집계 일치 여부, 화면 동작, 민감값 없는 오류 코드, 체감 지연만 남깁니다. 코드·합성 시험 통과와 사내 API·실제 WebUI·사용성 성공은 구분합니다.

## 5. 현재 읽기 계약과 업무 연결

| 함수 | 입력·결과와 제한 |
|---|---|
| `jira_check_access()` | 본인 저장 토큰의 인증 확인. 업무 입력으로 자격증명을 받지 않음 |
| `jira_dashboard(project_key='', start_at=0)` | 기존 전체/미완료 집계와 최근 목록 한 페이지. 빈 프로젝트는 허용된 프로젝트 범위 |
| `jira_get_issue(issue_key)` | 허용 프로젝트의 실제 이슈 본문과 원문 링크 |
| `jira_project_metadata(project_key='')` | 현재 사용자에게 보이고 관리자 허용 목록에 있는 프로젝트. 선택 프로젝트의 실제 상태 ID와 조회 가능한 날짜 필드 |
| `jira_search_crs(project_key, status_ids, date_field, start_date, end_date, start_at=0)` | 실제 프로젝트·상태 ID·날짜 필드에 대한 제한된 조회. 날짜는 양 끝 포함 `YYYY-MM-DD`, 최대 366일. 시작 0에서 모든 페이지를 확인한 경우만 완전 목록 |
| `jira_issue_attachments(issue_key)` | 한 이슈의 첨부 메타데이터와 같은 호스트의 제한된 읽기 접근 확인 |
| `jira_cr_attachments(issue_keys, required_filenames)` | 확정 CR 키 1~50개, 중복 없는 정확한 필수 파일 이름 1~20개. CR별 존재·누락·중복 이름·접근 미확인 결과를 보존 |

CR 입력 선언은 같은 작업의 실제 선택지 조회와 도구 인자에 연결합니다. 상태는 임의 표시 이름이 아닌 현재 프로젝트의 ID, 날짜 필드는 실제 날짜형/날짜시각형 필드에서 선택합니다. `EMS` 같은 시스템 이름을 Jira 프로젝트 키로 자동 변환하지 않습니다. 날짜 경계는 Jira 계정의 시간대 해석을 따르며 여러 페이지는 원자적 DB snapshot이 아닙니다.

CR 검색은 코드가 고정한 JQL만 생성합니다. 임의 JQL·URL·HTTP 메서드는 받지 않습니다. 페이지 커서·총수 변화·중복·누락·권한 실패는 부분 또는 실패 결과이며, 상한에 도달해도 전체 성공으로 바꾸지 않습니다. 후속 위치에서 시작한 결과도 전체 목록으로 간주하지 않습니다. 기존 `jira_dashboard`의 집계/한 페이지 계약은 유지합니다.

업무 배치 첨부 조회는 **완전히 조회하고 사람이 확정한 현재 목록**의 ID를 사용합니다. 실행 시 원본 작업·시도·결과 revision·목록 ID·결과 지문을 보존합니다. 명시적으로 제외한 항목은 전달하지 않으며, 목록을 변경하면 후속 작업의 근거를 재확인합니다. 부분 목록은 배치 실행을 승인하지 않습니다.

첨부 확인은 정확한 파일 이름의 대소문자를 구분합니다. 존재·이름 중복·접근 여부와 내용 적정성은 별개입니다. 파일 전체를 저장하거나 해석하지 않으며 `content_reviewed=false`를 유지합니다. 메타데이터가 가리키는 동일 scheme/host/context의 고정 첨부 경로에만 `Range: bytes=0-0` 읽기를 요청하고 최대 1바이트를 확인합니다. 리디렉션·다른 호스트·HTML 로그인 응답·경로 우회는 성공으로 처리하지 않습니다. 배치 예산이 소진되어 확인하지 못한 CR도 결과에서 사라지지 않습니다.

고정 REST v2의 읽기 경로 `/myself`, `/project`, `/project/{key}/statuses`, `/field`, `/search`, `/issue/{key}`, `/attachment/{id}`를 사용합니다. 메타데이터 계약은 [Jira 8.5.12 공식 REST 문서](https://docs.atlassian.com/software/jira/docs/api/REST/8.5.12/)와 대조했으며 실제 사내 신규 함수 호출 성공을 뜻하지 않습니다. 기존 TLS·추가 CA·개인 PAT·프로젝트 허용 목록 검사는 모든 새 함수에도 적용됩니다.

검증은 [기존 Jira 시험](../tests/test_jira_read.py), [합성 서버 실제 HTTP 계약 시험](../tests/test_jira_work_contract.py), [작성부터 결과 기록까지의 통합 시험](../tests/test_ees_delivery_artifacts.py)을 구분합니다. 마지막 시험은 임시 DB와 합성 Jira HTTP·모델을 사용하며 사내 서비스 검증이 아닙니다. [시험 전용 미게시 절차 원본](../tests/ees_delivery_artifacts_fixture.py)은 실제 작성 명령으로만 사용하고 운영 기본 데이터로 등록하지 않습니다.

기존 등록 도구의 업데이트·승인·검수는 별도 사내 적용 승인 후 진행합니다. 오류가 나면 해당 도구/계약을 사용 중지할 수 있지만 개인 설정이나 과거 기록을 삭제해 복구하지 않습니다. 쓰기·공용 PAT·운영 DB 우회는 제공하지 않습니다.

<a id="6-사용자-친화적인-화면과-유연성--개선-검토"></a>

## 6. 2026-09-09 일반 답변 전환 이력

2026-09-09 사용자 요청에 따라 초기에 기능 확인용으로 만든 Rich UI를 제거했습니다. 프로젝트 차트·로컬 필터·펼치기·질문 넣기 버튼을 제공하지 않으며, `jira_dashboard` 함수 이름과 조회 인자는 기존 연결 호환성을 위해 유지합니다. 향후 필요한 업무 화면을 하나씩 별도로 설계하고 검토합니다.

당시 v0.1.6 전환 절차는 기존 `EES Jira Read`의 코드 전체를 검수한 [jira_tool.py](../agent-pack/skills/jira-read/scripts/jira_tool.py)로 교체하고 `version: 0.1.6`을 확인하는 방식이었습니다. 현재 업데이트 대상은 상단 v0.2.0 계약이며 아래 당시 Prompt 반영 지시는 새로운 전문 Assistant 등록 지시가 아닙니다. 기존 도구 ID·관리자 Valves·개인 PAT·Assistant 연결을 유지하며 도구를 삭제하거나 재생성하지 않습니다. [공통 Prompt](https://github.com/knadalkim-a11y/team-agent-poc/blob/b41e23917273e1d2d0ead1ddadfea75b2dda1e32/agent-pack/system-prompts/ees-integrated-assistant.md)의 카드/버튼 전제를 제거한 답변·Jira 조회 안내도 반영합니다. 기존 사내 지침을 보존하며 Git 갱신만으로 등록 코드/Prompt가 바뀌지는 않습니다.

저장 뒤 새 대화에서 평소 쓰는 프로젝트 현황을 한 번 요청해 일반 답변·표·원문 링크가 나오고 시험용 카드가 없는지만 확인합니다. 이전 대화에 저장된 카드나 대화 데이터를 삭제하지 않습니다. 기존 인증·암호화·전체 집계/계정 격리 검사를 반복하지 않으며, Open WebUI 프로그램 Apply·서버 재시작도 필요하지 않습니다. [이번 변경 검증](../evals/jira-offline.md#rich-ui-removed), [실제 적용 상태](STATUS.md).

<a id="failure-followup-update"></a>

### 목록 실패·페이지 범위

목록 조회 실패 시 안전한 오류와 성공한 프로젝트 집계를 함께 반환합니다. 부분 실패는 0건이나 전체 합계로 바꾸지 않습니다. 일부 프로젝트 집계에 실패한 첫 페이지는 받은 목록만 제공하고 다음 위치는 제공하지 않습니다. 후속 페이지에서 프로젝트 범위가 달라지면 목록 요청 전에 중단합니다. 다음 페이지는 반환된 위치와 원래 프로젝트 범위를 사용하고, 프로젝트가 바뀌면 처음부터 조회합니다. 이 API 동작은 화면 제거 뒤에도 유지합니다. [v0.1.2 당시 검증](../evals/jira-offline.md#merge-review-fixes).

<a id="jira-followup-actions"></a>
<a id="jira-mvp-usability"></a>

### 제거한 시험용 화면의 이력

v0.1.1~0.1.5의 차트·카드·필터·질문 버튼은 당시 기능 확인용 구현이었으며 현재 적용 대상에서 제거했습니다. 과거 사용·검증 결과는 [대시보드 디자인](../evals/jira-offline.md#dashboard-design), [질문 버튼](../evals/jira-offline.md#followup-actions), [사용성 보완](../evals/jira-offline.md#mvp-usability)에 보존합니다. 당시 화면 코드는 [제거 전 원본](https://github.com/knadalkim-a11y/team-agent-poc/blob/99a9ee6584a3b23a2dd26ebb94ede079886b2831/agent-pack/skills/jira-read/scripts/jira_tool.py)에서 확인할 수 있습니다. 과거 버튼/화면 시험을 현재 사내 실행 목록으로 재사용하지 않습니다.
