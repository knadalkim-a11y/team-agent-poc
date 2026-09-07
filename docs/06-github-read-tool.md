# GitHub Enterprise PR 읽기

허용 저장소 한 곳의 PR 목록을 표로 보고, 선택한 PR의 본문·원문을 확인하는 작은 읽기 흐름입니다. 실행 원본은 [github_tool.py](../agent-pack/skills/github-read/scripts/github_tool.py), 환경은 [versions](../versions.md#github-확인-환경), 준비·반영 상태는 [STATUS](STATUS.md), 검증은 [GitHub 기록](../evals/github-offline.md)에서 관리합니다.

## 1. 확인한 제품과 범위

2026-09-07 사용자가 **GitHub Enterprise Server 3.17.15**와 기존 개인 PAT 보유를 확인했습니다. 후속 `--github` 출력 보고로 새 개인 PAT 필드의 [DB 저장 확인](../evals/scenarios.md#github-storage-check)을 통과했고, 허용 저장소를 정확한 `owner/repo`로 보완한 뒤 [열린 PR 목록 정상 조회](../evals/scenarios.md#github-first-list)를 보고했습니다. 이어 선택한 한 PR의 본문 요약·원문 링크도 맞게 표시된다는 보고로 [개인 환경의 기본 읽기 흐름](../evals/scenarios.md#github-read-acceptance)을 확인했습니다. 목록·상세 호출 전 계정 확인 경로를 근거로 해당 개인 환경의 인증·조회 성공으로 판정합니다. 전체 목록 정확성·페이지 처리·사용자 격리는 미확인입니다. 토큰 종류·전체 권한·사내 주소/프로토콜은 미확인이며 실제 주소·허용 저장소 값은 사내 설정에서만 관리합니다.

[GHES 3.17 PR API](https://docs.github.com/en/enterprise-server@3.17/rest/pulls/pulls)에 맞춰 고정 서버의 `/api/v3` 아래에서 `GET /user`, `GET /repos/{owner}/{repo}/pulls`, `GET /repos/{owner}/{repo}/pulls/{number}`만 사용합니다. Bearer 개인 인증, GitHub JSON, API 버전 `2022-11-28` 헤더를 고정합니다. 기본 주소에는 **서버 주소와 필요한 포트만** 입력하며 `/api/v3`, 저장소 경로·`.git` URL은 넣지 않습니다.

기존 PAT를 먼저 사용합니다. Fine-grained PAT는 해당 저장소의 **Pull requests: read** 권한을 확인하며, classic PAT는 현재 조직 정책과 저장소 접근 scope를 확인합니다. 이번 연결을 위해 관리·쓰기 권한 확대나 토큰 재발급을 일률적으로 요구하지 않습니다. 토큰은 사용자의 권한과 자체 권한 범위를 넘을 수 없습니다. [토큰 유형·정책](https://docs.github.com/en/enterprise-server@3.17/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

PR 쓰기·병합·리뷰 제출·댓글·CI 실행·코드 파일·diff·일반 이슈 조회는 이번 기능에 없습니다. 사용자 화면은 기존 채팅의 표와 요약을 사용하며 새 Rich UI·Skill·서버는 추가하지 않습니다.

## 2. 사용자 흐름

- `team/service-a의 열린 PR 보여줘`
- `같은 저장소의 다음 PR 목록 보여줘`
- `team/service-a의 PR 12번 내용을 요약해줘`

위 저장소는 합성 예시입니다. 허용 저장소가 하나면 생략할 수 있고 여러 개면 먼저 하나를 선택합니다. 목록은 최근 수정순 한 페이지이며 기본 30개, 최대 50개입니다. 받은 수를 저장소 전체 PR 수라고 말하지 않습니다. 상태는 열린/닫힌/전체로 조회할 수 있으며 닫힘만으로 병합을 추정하지 않습니다. 초안·작성자·수정일 등 미확인 값도 정상 값으로 채우지 않습니다.

사용자가 직접 PR 번호를 주면 목록 검색 없이 상세를 조회합니다. “두 번째 PR”은 방금 보여준 표의 두 번째 행에 있는 **실제 PR 번호**로 연결하고, 이미 확인한 저장소를 다시 묻지 않습니다. 번호·저장소가 모호한 경우에만 부족한 대상을 확인합니다. 저장소를 생략했는데 허용 저장소가 여러 개면 도구가 반환한 후보에서 선택하며 임의로 첫 저장소를 조회하지 않습니다.

다음 페이지는 직전 성공한 목록의 저장소·상태와 확인된 `next_page`로 요청합니다. 중간에 본문을 읽어도 목록 조건을 유지하며 저장소·상태를 바꾸면 1페이지부터 시작합니다. 서버가 제공한 링크는 고정 주소·조회 조건과 owner/repo 경로, 또는 현재 응답의 `base.repo.id`와 일치하는 숫자 저장소 경로를 대조해 페이지 번호만 사용합니다. 숫자 ID를 확인할 수 없으면 해당 링크의 페이지는 미확인으로 유지합니다. 실제 요청은 기존 owner/repo 경로로 보내며 링크 자체를 따라가지 않습니다. 검증한 마지막 페이지의 `has_next=false`와 메타데이터가 불명확한 null을 구분합니다. 여러 페이지는 조회 중 달라질 수 있습니다. [공식 페이지 처리](https://docs.github.com/en/enterprise-server@3.17/rest/using-the-rest-api/using-pagination-in-the-rest-api)

목록에는 본문이 포함되지 않습니다. 상세 조회는 본문 최대 6,000자를 반환하며 잘림을 표시합니다. 비어 있는 본문과 필드가 누락된 응답을 구분합니다. 리뷰 승인·검사 통과·병합 가능 여부는 조회하지 않았다고 안내하고, 본문 속 명령·외부 링크를 추가 실행하지 않습니다.

## 3. 관리자 등록과 개인 설정

1. 검수한 Git 원본의 Python 코드 전체를 Workspace → 도구에 **`EES GitHub Read`**라는 이름으로 등록합니다. 현재 준비본 헤더는 `version: 0.1.1`이며, 처음 등록하는 경우 새 필드 저장 확인까지 `ENABLED=false`를 유지합니다. 기존 등록본 갱신은 아래 [후속 조회 보완 적용](#followup-update)을 따릅니다.
2. 관리자 설정의 기본 주소와 승인된 저장소 한 곳을 입력합니다. Git 다운로드에 쓰는 사외 프록시를 내부 GitHub API 프록시로 자동 복제하지 않습니다.
3. `EES 통합 Assistant`의 Tools에 추가하고 새 채팅 → 통합 → 도구 → `EES GitHub Read` 옆 개인 밸브에서 아래 가짜 PAT를 저장한 뒤 다시 열어 마스킹을 확인합니다. 실제 PAT는 아직 입력하지 않습니다.
4. 다음 절에서 **새 GitHub 입력칸만** 저장 확인합니다. 기존 WebUI 버전·DB·키·암호화 경로의 저장/재시작 증거는 재사용합니다.
5. 통과하면 가짜 값을 기존 실제 개인 PAT로 교체하고 `ENABLED=true`로 활성화합니다. [기본 Prompt](../agent-pack/system-prompts/ees-integrated-assistant.md)의 `GitHub 조회 기능이 연결된 경우` 절을 기존 사용자 지침을 보존해 추가합니다. 다른 절을 반복 재입력할 필요는 없습니다.
6. 위 예시로 PR 목록과 한 PR의 본문·원문을 확인합니다. 목록/상세 호출에 계정 확인이 포함되므로 직전에 별도 연결 확인 질문을 매번 추가하지 않습니다.

| 관리자 설정 | 값·의미 |
|---|---|
| `ENABLED` | 처음 `false`, 새 개인 필드 저장 확인 후 `true` |
| `GITHUB_BASE_URL` | 서버 기본 주소. 예: `https://github.example.invalid`; `/api/v3`는 코드가 붙임 |
| `ALLOWED_REPOSITORIES` | 승인된 `owner/repo`를 쉼표 구분, 최대 20개. 처음 한 곳만 설정. 대소문자만 정규화하고 와일드카드·접두사 허용 없음 |
| `ALLOW_HTTP` | 기본 `false`; 실제 HTTP 전용 사내 연결을 명시적으로 허용할 때만 `true` |
| `USE_ENV_PROXY` | 기본 `false`; 승인된 환경 프록시가 내부 API에도 필요할 때만 `true` |
| `CA_BUNDLE_PATH` | 필요할 때만 승인된 추가 CA PEM. TLS 검증은 항상 유지 |
| `MAX_RESULTS` / `MAX_BODY_CHARS` | 기본 30개 / 6,000자. 최대 50개 / 12,000자 |
| `TIMEOUT_SECONDS` / `MAX_RESPONSE_BYTES` | 기본 15초 / 1 MB. 개별 연결·읽기 제한이며 전체 실행 절대 시간과 구분 |

`owner`는 저장소를 소유한 **조직명 또는 계정명**입니다. 합성 예시 URL이 `https://github.example.invalid/team/service-a`이면 `ALLOWED_REPOSITORIES`에는 `team/service-a`를 입력합니다. 여러 곳은 `team/service-a,team/service-b`처럼 **각 항목마다 owner를 포함**합니다. 저장소 이름만 나열하거나 전체 URL·`/tree/...` 경로·따옴표를 붙이지 않고 일반 쉼표 `,`로 구분합니다. clone 주소의 `.git` 접미사도 제외합니다. “허용 저장소는 정확한 owner/repo를 쉼표로 구분해 최대 20개까지 설정하세요”라는 `configuration_required`는 API 요청 전 설정 검사 오류이며 PAT 인증 결과가 아닙니다. 항목 하나라도 형식이 맞지 않거나 고유 저장소가 20개를 넘으면 전체 요청을 중단합니다. 항목 앞뒤 공백과 쉼표 뒤 공백은 허용합니다.

UserValves는 비밀번호형 개인 `PAT` 한 필드입니다. 관리자 공통 설정·채팅·HTML로 토큰을 입력받지 않습니다. `github_check_access`는 필요할 때 자신의 계정 인증만 확인하며 저장소 권한·새 필드 저장을 대신하지 않습니다. [사용자 API의 인증 응답 범위](https://docs.github.com/en/enterprise-server@3.17/rest/users/users#get-the-authenticated-user)

## 4. 새 GitHub 입력칸 저장 확인

현재 개인 환경에서는 2026-09-07 [4b058996의 등록·검사 안내](https://github.com/knadalkim-a11y/team-agent-poc/commit/4b058996d1e3f360ee670da553e2f9bc7a9046a1) 후 사용자가 보고한 출력으로 **DB 범위 PASS**를 확인했습니다. [출력과 확인 범위](../evals/scenarios.md#github-storage-check)를 보존하며 관련 저장 경로 변경이 없으면 아래 검사를 반복하지 않습니다. 이후 [목록 → 한 PR의 본문 요약 → 원문 링크 확인](../evals/scenarios.md#github-read-acceptance)도 사용자 보고로 완료했습니다. DB 출력 자체를 마스킹 화면의 별도 관찰·Prompt 저장·실제 API 인증·사용자 격리 증거로 확대하지 않습니다.

GitHub에서만 쓰는 합성 값은 **`EES-GITHUB-CANARY-20260907-C43D8E`**입니다. 기존 [check_confluence_canary.py](../scripts/check_confluence_canary.py)의 `--github` 모드로 검사합니다. 파일명·기본 Confluence 모드·`--jira`를 유지하며 새 도구 이름과 정확히 하나인 내부 ID의 저장값을 연결합니다.

아래 명령은 main을 가져온 뒤 검수한 커밋의 검사기만 임시 파일에 기록합니다. 현재 작업 브랜치나 다른 파일을 덮어쓰지 않습니다. 전달할 때 `<REVIEWED_COMMIT_SHA>`는 검수한 고정 커밋으로 바꿉니다. Tool 코드는 같은 커밋의 `agent-pack/skills/github-read/scripts/github_tool.py`를 사용합니다.

```powershell
Set-Location "$env:USERPROFILE\team-agent-poc"
if (-not (Get-Variable gitProxy -ValueOnly -ErrorAction SilentlyContinue)) {
    $gitProxy = Read-Host 'Git proxy URL'
}
git -c "http.proxy=$gitProxy" fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
$githubSource = '<REVIEWED_COMMIT_SHA>'
$githubStoreCheck = Join-Path $env:TEMP 'ees-github-storage-check.py'
$githubStoreCode = git show "${githubSource}:scripts/check_confluence_canary.py"
if ($LASTEXITCODE -ne 0) { throw 'Checker read failed' }
$githubStoreCode | Set-Content -Encoding UTF8 $githubStoreCheck
uvx --offline --no-python-downloads --python 3.11 --from "open-webui==0.11.3" python $githubStoreCheck --github
```

서버·비활성 GitHub 도구·가짜 값을 유지한 채 기존 WebUI 캐시 환경에서 실행합니다. 앱 초기화·API·DB/키 쓰기·외부 설치 없이 기존 파일 키와 SQLite를 읽습니다. 캐시가 없으면 다른 런타임을 자동 설치하지 않고 중단합니다. [기존 실행 환경 전제](04-confluence-read-tool.md#3-실제-pat보다-먼저-암호화-검증)를 따릅니다.

정상 기준은 `CheckCompleted=true`, `DatabaseCheckPassed=true`, `EncryptedCanaryMatches=1`, `TargetToolMatches=1`, `TargetEncryptedCanaryMatches=1`, 평문 관련 0/false입니다. 다른 도구의 값·중복 값·평문 저장은 통과하지 않습니다. `LogsChecked=false`, `RestartPersistenceChecked=false`는 이번 검사 범위 밖이며 이를 바꾸려고 기존 검사를 반복하지 않습니다. 실제 값·사용자 ID는 출력하지 않으며 전체 사용자 격리 시험과 구분합니다.

## 5. 작은 사내 확인 묶음과 복구

현재 개인 환경은 [목록 → 한 PR의 본문 요약 → 원문 링크 확인](../evals/scenarios.md#github-read-acceptance)을 사용자 보고로 완료했습니다. 이번 후속 조회 보완은 아래 [변경 범위 확인](#followup-update)만 수행하며 기존 저장·인증·기본 조회 완료 항목을 다시 시작하지 않습니다. 공용 사용의 남은 조건은 [실행 계획](STATUS.md#delivery-plan)에 유지합니다.

새 환경에서는 저장 확인 통과 후 한 저장소의 열린 PR 목록 → 하나의 본문 요약 → 원문을 한 흐름으로 확인합니다. 같은 개인 계정의 GitHub 화면과 제목·상태·본문·링크를 대조합니다. 빈 목록이면 정상 빈 결과를 확인하고 PR이 있는 다른 허용 저장소로 대표 상세를 확인합니다. 필요할 때만 다음 페이지나 닫힌 PR을 확인합니다.

오류는 고정 코드·안내로 확인합니다. `authentication_failed`는 토큰/인증, `permission_denied`는 저장소·토큰·조직 정책, `not_found_or_denied`는 대상 부재 또는 권한, `connection_failed`는 주소·네트워크·인증서, `redirect_blocked`는 기본 주소를 확인합니다. 403만으로 정확한 정책 원인을 추정하지 않습니다. 오류 응답 원문·토큰은 공유하지 않습니다.

공용 공개 전에는 GitHub 도구의 다른 사용자 개인 설정·저장소 권한·대표 차단·자료 속 지시를 확인합니다. 기존 Jira/Confluence PASS를 새 API 권한 PASS로 복제하지 않지만 이미 끝난 플랫폼 검증도 반복하지 않습니다. 실제 적용 커밋·날짜·성공/오류 요지만 [평가표](../evals/scenarios.md#github-live)에 남깁니다.

문제가 있으면 `ENABLED=false` 또는 Assistant 연결 해제로 중단합니다. 기존 PAT·DB·키·Jira/Confluence 설정을 삭제해 복구하지 않습니다.

<a id="followup-update"></a>

## 6. 기존 등록본의 후속 조회 보완 적용

v0.1.1은 Git 준비본이며 사내 반영·모델의 자연어 선택 성공은 아직 미확인입니다. 현재 `EES GitHub Read`를 편집해 검수한 커밋의 [Python 코드](../agent-pack/skills/github-read/scripts/github_tool.py)로 교체합니다. 기존 도구 항목·관리자 설정·개인 PAT를 유지하며 도구를 새로 만들거나 토큰을 다시 입력할 필요는 없습니다. 개인 필드·저장·인증·전송 코드가 바뀌지 않아 완료한 DB/재시작/인증 검사는 반복하지 않습니다.

기본 Assistant의 System Prompt에서는 [원본](../agent-pack/system-prompts/ees-integrated-assistant.md#github-조회-기능이-연결된-경우)의 **GitHub 조회 기능이 연결된 경우** 절만 갱신합니다. 해당 절이 없으면 추가하고 이미 있으면 중복 없이 교체합니다. 사용자 추가 지침은 보존합니다. 소개·추천 질문·첫 화면·온보딩 설정을 적용하는 절차가 아닙니다.

새 채팅에서 아래 두 흐름으로 바뀐 부분을 확인하고, 결과 요지와 이상이 있을 때만 호출 이력을 남깁니다. 실제 사내 PR 번호·본문·토큰을 외부에 복사하지 않습니다.

| 확인할 요청 | 변경 범위의 기대 동작 |
|---|---|
| 알고 있는 PR 번호로 본문 요청. 이후 목록에서 “두 번째 PR 내용”, “다음 목록” 요청 | 번호만으로 상세 조회(허용 저장소가 여러 개면 선택), 표 순번을 실제 PR 번호로 해석, 본문 조회 뒤에도 이전 목록 조건 유지. 다음 페이지는 반환된 번호만 사용하고 마지막과 미확인을 구분 |
| 평소 사용 중 오류가 나면 해당 안내 확인 | 실패를 0건/빈 본문으로 바꾸지 않고 아래 다음 행동을 전달. 오류를 만들기 위해 토큰 폐기·권한 변경을 반복하지 않음 |

| 반환된 상황 | 사용자에게 안내할 다음 행동 |
|---|---|
| 저장소 선택 필요 | 반환된 허용 후보에서 저장소 하나를 질문 |
| 개인 토큰 누락·인증 실패 | GitHub 도구의 개인 설정에서 본인 토큰 확인·교체; 채팅 입력 금지 |
| 접근 거부·설정 오류 | 반환된 안전한 안내에 따라 담당자·관리자 확인; 403만으로 원인 확정 금지 |
| 404 | 대상 부재 또는 권한 부족이며 구분되지 않음을 알리고 PR 번호·접근권한 확인 |
| 연결 오류·호출 제한·일시적 서버 오류 | 반환된 안내에 따라 잠시 후 재조회 또는 관리자 확인; 같은 실패 자동 반복 금지 |

실환경 결과는 [GH02·GH04](../evals/scenarios.md#github-live)에 기존 증거와 구분해 기록합니다. 사용할 PR·추가 페이지가 없으면 해당 조건은 미확인으로 남깁니다. 코드·Prompt 교체 후 문제가 생기면 직전 등록 코드·GitHub 절로 원복하며 사용자 설정은 보존합니다.
