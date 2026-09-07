# Jira 읽기와 시스템별 현황

Jira 프로젝트를 시스템 구분으로 사용해 전체·미완료 건수를 비교하고, 최근 이슈를 좁혀 본 뒤 상세 내용과 원문을 확인합니다. 실행 원본은 [jira_tool.py](../agent-pack/skills/jira-read/scripts/jira_tool.py), 검증 근거는 [Jira 검증 기록](../evals/jira-offline.md), 실제 적용 여부는 [STATUS](STATUS.md)에서 관리합니다.

## 1. 확인된 환경과 인증 조건

사용자 보고 제품은 **Jira 8.5.12, build 805012, sha1:156decd**입니다. 2026-09-07 기존 개인 토큰으로 HTTP 계정 확인을 실행한 뒤 `HTTPStatus=200`, `BearerAuthenticated=True`를 보고받아 **해당 PC의 Bearer 인증 호환성을 확인**했습니다. Server/Data Center 구분과 토큰 발급 구현은 미확인입니다. 공식 내장 PAT의 지원 시작 버전과 현재 환경의 실제 성공을 구분합니다. [Atlassian PAT 안내](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html)

현재 사용자 환경에서는 [등록·마스킹](../evals/scenarios.md#jira-registration)에 이어 [새 필드 DB 저장 검사와 실제 토큰으로 첫 대시보드 표시](../evals/scenarios.md#jira-first-dashboard)까지 확인됐습니다. 완료한 인증·등록·저장 확인은 반복하지 않고 전체 시스템 비교 흐름으로 진행합니다. 아래 비활성 등록·저장 절차는 새 환경을 준비할 때 사용하며 배포 원본의 기본값은 비활성입니다. 실제 토큰값·내부 주소·프로젝트명은 채팅이나 Git에 기록하지 않습니다. 인증 확인 때문에 업무용 토큰을 폐기·재발급하거나 Jira를 업그레이드하지 않습니다.

### 기존 토큰으로 한 번 연결 확인

현재 사용자 환경에서는 완료한 절차입니다. 아래 명령은 다른 환경에서 처음 확인하거나 인증 경로가 달라졌을 때만 사용합니다.

[check-jira-auth.ps1](../scripts/check-jira-auth.ps1)은 Windows PowerShell 5.1 이상에서 실행하는 읽기 확인입니다. Jira 기본 주소와 개인 토큰을 실행 시 입력하며 토큰 입력은 숨깁니다. `GET /rest/api/2/myself` 한 곳만 호출하고, 리디렉션·쿠키·Windows 기본 인증·자동 재시도를 사용하지 않습니다. WebUI·DB·설정을 변경하거나 토큰을 파일에 저장하지 않습니다. .NET 기본 TLS 검증을 유지하고 응답은 64 KiB·시간은 15초로 제한합니다.

현재 원본은 main 미병합 [PR #2](https://github.com/knadalkim-a11y/team-agent-poc/pull/2)에 있습니다. 기존 저장소에서 PR을 fetch해 확인 스크립트만 임시 파일로 꺼내면 작업 브랜치나 기존 파일을 바꿀 필요가 없습니다. 아래 `git show`의 커밋은 전달 시 검수한 원본 SHA로 고정합니다.

```powershell
Set-Location "$env:USERPROFILE\team-agent-poc"
# 새 창이면 기존 사내 Git 프록시 값만 이 창에 입력
$gitProxy = Read-Host 'Git proxy URL'
git -c "http.proxy=$gitProxy" fetch origin refs/pull/2/head
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
$jiraSource = '<REVIEWED_PR_COMMIT_SHA>'
$jiraCheck = Join-Path $env:TEMP 'ees-check-jira-auth.ps1'
$jiraScript = git show "${jiraSource}:scripts/check-jira-auth.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Script read failed' }
$jiraScript | Set-Content -Encoding UTF8 $jiraCheck
& $jiraCheck
```

기존 창에 `$gitProxy`가 있으면 재입력 줄은 생략합니다. Jira 기본 주소는 필요한 컨텍스트 경로까지만 입력하고 `/rest/api/2`는 붙이지 않습니다. Jira가 승인된 `http://` 전용 주소라면 마지막 실행을 `& $jiraCheck -AllowHttp`로 바꿉니다. 네트워크상 Windows 시스템 프록시가 필요한 경우에만 `-UseSystemProxy`를 추가합니다. Git 프록시를 Jira에 자동 재사용하지 않으며 실행 정책이 차단하면 정책을 우회하지 않고 사내 승인 실행 방식으로 진행합니다.

성공 출력은 `HTTPStatus=200`과 `BearerAuthenticated=True`입니다. 실패하면 `HTTPStatus`(받은 경우)·`BearerAuthenticated=False`·`CheckStage`만 보고 원인에 맞춰 다음 단계를 정합니다. 예외·응답 본문·사용자 식별자·주소·토큰은 출력하지 않습니다. 성공은 **해당 PC의 Bearer 계정 확인**만 뜻하며 프로젝트 권한·WebUI 네트워크/저장·Rich UI 성공은 이후 흐름에서 확인합니다.

## 2. 사용할 수 있는 업무

| 화면·질문 | 제공 범위 |
|---|---|
| “시스템별 Jira 이슈 현황 보여줘” | 관리자가 허용한 프로젝트별 전체·미완료 건수와 최근 이슈 목록 |
| “SYSA 프로젝트 이슈만 보여줘” | 지정한 허용 프로젝트의 현황·최근 목록을 새로 조회 |
| “SYSA-123의 상세 내용과 원문 보여줘” | 해당 이슈의 설명·상태·담당자 등과 Jira 원문 링크 |

위 키는 합성 예시입니다. 화면에서는 받은 목록의 프로젝트·상태·담당자를 바꾸고 항목을 펼칠 수 있습니다. 시스템 막대를 눌렀을 때는 **이미 받은 목록만** 좁혀집니다. 특정 시스템의 이슈를 더 받거나 다음 페이지를 보려면 채팅으로 요청합니다. 화면 선택이 새 API 조회나 전체 집계 재계산을 뜻하지 않습니다.

프로젝트별 건수는 검색 API의 `total`을 사용하며, 미완료는 `statusCategory != Done` 기준입니다. 처음 적용할 때 사내 워크플로의 완료 구분과 맞는지 한 번 비교합니다. 최근 이슈는 수정일 내림차순·키 오름차순이며 기본 30건, 최대 50건씩 가져옵니다. 목록에서 보이는 상태·담당자 분포를 프로젝트 전체 분포로 설명하지 않습니다.

모든 결과는 **조회한 개인 계정이 볼 수 있는 범위**입니다. 관리자라는 업무 역할만으로 다른 계정이 볼 수 없는 이슈까지 집계하지 않습니다. 프로젝트·이슈 권한에 따라 결과가 달라지며, 집계 실패는 `0건`이 아닌 미확인으로 표시합니다. 여러 API 결과는 동시점의 고정 스냅샷이 아니므로 조회 중 변경으로 수치·페이지가 달라질 수 있습니다.

## 3. 관리자 등록과 개인 설정

1. Workspace → 도구에서 `EES Jira Read`를 만들고 Python 원본 전체를 등록합니다. 새 개인 설정 확인까지 `ENABLED=false`로 유지합니다. Git 갱신만으로 WebUI에 반영되지 않습니다. 최초 등록·표시를 확인한 원본은 [ce982de5의 Tool](https://github.com/knadalkim-a11y/team-agent-poc/blob/ce982de5e83a26421297e502e7f780365d7a18d3/agent-pack/skills/jira-read/scripts/jira_tool.py)입니다.
2. 아래 관리자 설정에 계정 확인에 성공한 사내 기본 주소와 **정확한 프로젝트 키 목록**을 입력합니다. 현재 확인한 HTTP 환경은 `ALLOW_HTTP=true`로 설정하고 다른 값은 기본값을 유지합니다. 키 접두사나 와일드카드로 프로젝트를 자동 허용하지 않습니다.
3. 기존 WebUI의 버전·키·DB·암호화 경로가 같다면 이미 확인한 저장·재시작 증거를 재사용합니다. 새 Jira 개인 PAT 필드는 가짜 값으로 마스킹과 해당 Tool의 개인 설정 한 건의 암호화 저장을 확인합니다. 아래 [Jira 전용 확인](#새-jira-개인-입력칸-저장-확인)을 사용하고 기본 Confluence 모드의 결과를 Jira 검증으로 간주하지 않습니다. 저장 경로나 키가 바뀌었다면 영향받는 검증만 추가합니다. [기존 저장 검증 원칙](04-confluence-read-tool.md#3-실제-pat보다-먼저-암호화-검증)
4. 확인 후 각 사용자가 Jira 도구의 **개인 설정**에 본인 토큰을 입력합니다. 관리자 공통 설정·채팅·HTML에 넣지 않습니다. 기존 Confluence PAT 설정은 그대로 유지합니다.
5. 승인된 사용자에게 도구 읽기 권한을 주고 `EES 통합 Assistant`의 Tools에 연결합니다. 기존 사용자 지침을 보존하면서 [기본 Prompt](../agent-pack/system-prompts/ees-integrated-assistant.md)의 Jira 조회 안내를 반영합니다. 공용 공개 전에는 새 도구의 접근 권한과 다른 사용자의 빈 개인 설정도 확인합니다.
6. 위 조건이 충족되면 `ENABLED=true`로 저장하고 평소 접근하는 프로젝트 하나의 현황을 요청합니다. 대시보드 조회에 사용자 인증 확인이 포함되므로 별도 연결 확인 질문을 직전에 반복하지 않습니다. 실패하면 오류 코드·메시지만 확인하며 토큰이나 응답 원문을 공유하지 않습니다.

새 개인 설정은 새 채팅 → 통합 → 도구 → `EES Jira Read` 옆 밸브에서 엽니다. `PAT`에 Jira에서만 쓸 가짜 값 `EES-JIRA-CANARY-20260907-B92F6A`를 저장하고 다시 열어 마스킹을 확인합니다. 현재 사용자 환경에서는 이 등록·마스킹까지 완료 보고가 있으므로 반복하지 않습니다. 실제 토큰 입력 전 새 필드의 저장 확인만 진행하며 기존 Confluence canary·재시작·키 백업을 반복하지 않습니다.

| 관리자 Valves | 기본값·의미 |
|---|---|
| `ENABLED` | `false`; 인증·저장 조건을 확인한 뒤 활성화 |
| `JIRA_BASE_URL` | 빈 값; 필요한 context path까지의 기본 주소. `/rest/api/2`나 이슈 URL은 제외 |
| `ALLOWED_PROJECTS` | 빈 값이면 차단; 승인된 정확한 키를 최대 20개까지 쉼표로 구분. 예: `SYSA,SYSB` |
| `ALLOW_HTTP` | `false`; 승인된 HTTP 전용 환경에서만 명시적으로 허용. 전송 암호화는 제공되지 않음 |
| `MAX_RESULTS` | `30`; 최근 목록 한 페이지 최대 `50`건 |
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
git -c "http.proxy=$gitProxy" fetch origin refs/pull/2/head
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
$jiraCheckSource = '<REVIEWED_PR_COMMIT_SHA>'
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

인증 형식을 확인한 뒤 **평소 접근하는 프로젝트 하나**에서 연결 → 건수 비교 → 목록 → 상세·원문을 한 번의 흐름으로 확인합니다. 같은 계정·같은 조회 조건으로 Jira 검색 화면과 전체·미완료 건수를 비교하고, 차이가 있으면 조회 시각·완료 정의·권한부터 확인합니다. 그다음 전체 프로젝트 현황에서 선택·필터·펼치기가 동작하는지 확인합니다.

정상 흐름이 된 뒤 허용되지 않은 프로젝트나 접근할 수 없는 이슈 하나로 차단·다음 행동 안내를 확인합니다. 장애를 만들거나 정상 토큰을 폐기하지 않습니다. 일반 사용자 공개 전에는 해당 Jira 도구의 권한·개인 설정 분리와 비개발자 한 명의 시작·필터·오류 이해를 확인합니다. 이전 W/D/Confluence PASS는 관련 변경이 없으면 반복하지 않습니다.

기록은 적용 원본 커밋·날짜, 정상/부분/실패, 집계 일치 여부, 화면 동작, 민감값 없는 오류 코드, 체감 지연만 남깁니다. 코드·합성 시험 통과와 사내 API·실제 WebUI·사용성 성공은 구분합니다.

## 5. 구현 경계와 운영

- 모델에 노출하는 기능은 `jira_check_access()`, `jira_dashboard(project_key='', start_at=0)`, `jira_get_issue(issue_key)`입니다. 임의 JQL·URL·HTTP 메서드는 입력받지 않습니다.
- API는 고정 기본 주소의 `GET /rest/api/2/myself`, `/search`, `/issue/{key}`만 사용합니다. 응답의 프로젝트도 허용목록과 대조하며 이슈 이동·권한 때문에 확인하지 못한 경우를 성공으로 바꾸지 않습니다. [Jira 8.5.12 REST 문서](https://docs.atlassian.com/software/jira/docs/api/REST/8.5.12/)
- 프로젝트 P개 현황의 정상 경로는 인증 1회 + 집계 2P회 + 목록 1회입니다. 집계 동시 실행은 최대 4개이며 무제한 병렬 요청·자동 전체 페이지 수집·주기 새로고침은 하지 않습니다. 실제 호출 수·지연은 사내 실측 전까지 미측정으로 둡니다.
- 화면은 고정 HTML에 받은 데이터를 안전한 텍스트로 삽입하며 외부 스크립트·Jira 직접 호출·PAT 저장을 사용하지 않습니다. 새 조회는 사용자별 검사를 거치는 도구 호출로 진행합니다. `HTMLResponse`와 모델용 결과를 함께 반환하는 [Open WebUI Rich UI 방식](https://docs.openwebui.com/features/extensibility/plugin/development/rich-ui/)은 [v0.11.3 처리 코드](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/middleware.py)에서 확인했습니다. 실제 화면은 사내 확인이 필요하며 화면 반환이 실패하면 조회 데이터와 표시 실패 안내를 반환합니다.
- 오류 시 도구를 비활성화하거나 Assistant 연결을 해제할 수 있습니다. 이전 도구·개인 설정을 삭제해 복구하지 않습니다. 기능 확대·쓰기·공용 PAT·관리자 권한 대체는 이번 범위에 포함하지 않습니다.

<a id="6-사용자-친화적인-화면과-유연성--개선-검토"></a>

## 6. 사용자 친화적인 화면과 유연성

사용자는 디자인·가독성·사용성과 유연성을 요청했고 이모지는 사용하지 않도록 정했습니다. v0.1.1은 차분한 색상, 충분한 여백, 큰 집계 숫자와 읽기 쉬운 목록으로 개선했습니다. 프로젝트 수·반환 데이터에 따라 변하며, 조회 인자는 프로젝트 키와 페이지 위치를 유지합니다. 2026-09-07 개편본 v0.1.1 적용과 기본 업무 흐름이 정상이라는 [사용자 확인](../evals/scenarios.md#jira-dashboard-acceptance)을 받았습니다. 현재 디자인으로 진행하며 추가 디자인 수정은 후속으로 둡니다.

| 상태 | 개선 내용 | 범위 |
|---|---|---|
| v0.1.1 구현 | 미완료 기준 기본 비교, 전체/미완료 선택에 따른 내림차순 정렬·막대 축척 | 모든 프로젝트의 두 건수를 함께 표시. 집계 실패와 0건을 구분하고 전체 집계·이번 목록의 범위를 명시 |
| v0.1.1 구현 | 제목·상태·담당자·수정일을 펼치기 전에 표시, 좁은 화면에서는 줄을 나눠 배치 | 우선순위·기한·정확한 수정 시각·원문은 펼쳐 확인. 필터를 바꿨다가 돌아와도 펼침 상태 유지. 이모지·장식 아이콘 없음 |
| 후속 검토 | 시스템 새 조회·다음 목록·다시 조회 버튼, 필요한 범위/기간/상태의 실제 조회 조건 | 전체 범위 상태/담당자/기간 필터는 검색 조건 확장이 필요. 별칭도 관리자가 확인한 이름 연결이 필요하며 이번 개편에는 미포함 |

기본값은 관리자에게 필요한 미완료 현황을 바로 보여주고 일반 조회 설명은 필요할 때 펼칩니다. 부분 실패·조회 중 건수 변동은 눈에 보이는 안내로 유지합니다. 키보드 포커스·기본 버튼/펼치기·숫자 병기·좁은 화면/다크 모드 대응을 보존했습니다. [합성 검사](../evals/jira-offline.md#dashboard-design)는 실제 브라우저의 배치·대비·조작성 확인과 구분합니다.

### 기존 화면 개편본 반영

PR #2의 검수한 원본에서 [jira_tool.py](../agent-pack/skills/jira-read/scripts/jira_tool.py) 전체를 가져와 헤더 `version: 0.1.1`을 확인한 뒤 Workspace → 도구 → 기존 `EES Jira Read`의 코드만 교체합니다. 도구 ID·관리자 설정·개인 설정·Assistant 연결을 유지하며 새 도구 생성이나 PAT 재입력은 필요하지 않습니다. Git 변경은 WebUI에 자동 반영되지 않습니다.

저장 후 새 대시보드를 한 번 요청해 비교 기준 변경 → 프로젝트/상태 선택 → 상세 펼치기·원문 열기를 확인합니다. 전체 시스템 표시와 대표 프로젝트 한 곳의 건수 대조도 이 흐름에 묶습니다. 이미 통과한 인증·DB 저장·재시작 검사는 관련 변경이 없으므로 반복하지 않습니다. 문제가 있으면 같은 도구에 앞서 표시를 확인한 ce982de5 원본 코드를 되돌리며 개인 설정은 삭제하지 않습니다.

### 후속 조회 연결 검토

현재 v0.11.3의 [Chat.svelte](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/chat/Chat.svelte)와 [FullHeightIframe.svelte](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/common/FullHeightIframe.svelte), [공식 Rich UI 안내](https://docs.openwebui.com/features/extensibility/plugin/development/rich-ui/#prompt-submission)에서 `input:prompt`로 입력란 채우기, `input:prompt:submit`으로 확인 창을 거친 후속 채팅 전송을 확인했습니다. 이를 쓰면 PAT를 HTML에 넘기거나 WebUI 코어를 수정할 필요가 없습니다. 결과는 새 채팅 메시지에 표시되며 같은 카드의 즉시 갱신이나 특정 Tool 직접 실행을 확인한 것은 아닙니다. 성공/취소 응답이 없는 이 경로에서 클릭만으로 조회 완료를 표시하거나 무기한 로딩을 시작하지 않습니다. 사내 버튼 동작은 아직 미실행입니다.
