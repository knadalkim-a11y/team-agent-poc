# GitHub PR 읽기 사외 검증

이 문서는 코드·합성 데이터 검증 기록입니다. 실제 사내 GitHub API·WebUI 등록·개인 PAT 저장·사용성 판정은 [실환경 평가](scenarios.md#github-live)에 별도로 둡니다. 제품·버전·토큰 보유는 사용자 보고이며 실제 주소·저장소·토큰은 수집하지 않습니다.

<a id="initial-implementation"></a>

## 최초 구현 — 2026-09-07

### 범위와 기준

- 사용자 보고 GHES 3.17.15·기존 개인 PAT를 기준으로 허용 저장소 한 곳의 PR 목록 → 본문·원문을 구현함. main `9dcdbf60a98124506140b0dca315d50223cfa0ed`와 Jira PR #2 head `29e27c87b3f18538ae610fc335342dabf44b3894`를 확인하고, 해당 준비본 위 별도 GitHub 작업 브랜치에서 변경함. main 병합·기존 PR 덮어쓰기·사내 배포는 하지 않음.
- [GHES 3.17 PR API](https://docs.github.com/en/enterprise-server@3.17/rest/pulls/pulls)의 GET 목록/상세, 상태·최근 수정순·페이지 인자, 개인 Bearer·GitHub JSON·API 버전 헤더를 확인함. [사용자 API](https://docs.github.com/en/enterprise-server@3.17/rest/users/users#get-the-authenticated-user)의 공개 계정 응답으로 인증을 확인하며 불필요한 private 사용자 scope를 요구하지 않음. [페이지 문서](https://docs.github.com/en/enterprise-server@3.17/rest/using-the-rest-api/using-pagination-in-the-rest-api)와 [PAT 문서](https://docs.github.com/en/enterprise-server@3.17/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)를 가이드에 연결함.
- 새 실행 코드는 단일 `github_tool.py`, 작은 조건부 Prompt, 기존 채팅의 목록 표·요약임. 별도 Skill·Rich UI·공통 인증 계층·서버·패키지 의존성을 추가하지 않음. 수동 등록하는 단일 Tool 안에 필요한 경계를 유지하며 기존 Jira/Confluence 구현을 리팩터링하지 않음.

### 실행 증거

사외 Linux·Python 3.12.13·Pydantic 2.13.4·cryptography 46.0.0에서 수행함. 기존 WebUI 설치나 사내 의존성은 변경하지 않음.

| 확인 | 명령·범위 | 결과 |
|---|---|---|
| 새 GitHub Tool | `python -m unittest discover -s tests -p 'test_github_tool.py' -v` | 27/27 PASS, 0.273초. DNS/socket 차단 및 합성 HTTP 응답만 사용 |
| 변경한 저장 검사기 | `python -m unittest discover -s tests -p 'test_confluence_canary.py' -v` | 34/34 PASS, 0.074초. 기존 21개 + GitHub/충돌 13개 |
| 구문·변경 검토 | 새 Tool Python 구문, 코드·Prompt·가이드·설정/함수 스키마 대조 | 구문 통과. 아래 발견 1건 수정 후 관련 시험 통과 |
| 문서·참조 | `python scripts/check_docs.py` | 문서 24개·내부 링크 275개, 오류 0·검토 후보 0 |
| 변경 공백 | `git diff --check` 및 staged 검사 | PASS |

최초 GitHub 시험 실행 요청은 실행 서버 연결 오류로 프로세스 생성 전에 실패했고 재요청에서 정상 실행됨. 시험 실패나 제품 결함으로 세지 않음. 27개 통과 뒤 선택적 시험 확대·동일 suite 반복은 하지 않음.

### 검토 발견·처리

- 열린 PR 요청에 닫힌 PR이 섞인 응답을 성공으로 반환할 수 있는 조건을 검토 중 발견함. 요청 상태와 각 응답 상태를 대조해 불일치를 오류로 처리하고 관련 합성 검사를 통과함.
- 입력 단계와 전송 단계에서 허용 저장소·고정 origin·GET 경로/쿼리를 확인함. 개인 PAT·설정은 호출마다 분리하고 리디렉션·환경 프록시 기본값·TLS·응답 크기·고정 오류를 대조함. 원문은 설정 주소와 확인한 저장소/번호로 구성하며 서버가 반환한 URL·fork 저장소로 추가 요청하지 않음.
- PR base 저장소·번호·상태, 중복 번호, 제목 누락·비정상 구조를 검사함. 병합은 명시적 정보로만 판단하고 미확인은 null로 유지함. fork의 head 저장소가 삭제됐거나 허용 범위 밖이어도 반환받은 branch 메타데이터만 쓰며 head 저장소를 조회하지 않음. 상세 본문 누락은 오류, null은 빈 본문, 길이 초과는 잘림으로 구분함.
- 목록은 한 페이지이며 전체 PR 수를 만들지 않음. 다음 Link는 고정 origin·API 경로·조건·다음 번호를 확인해 정수만 반환함. 불명확하거나 악성인 링크는 따르지 않고 다음 페이지 미확인으로 남김. PAT 반사·예외·오류 응답의 값 비노출을 확인함.
- 기존 저장 검사기에 고정 `--github`를 추가함. 새 합성 값 `EES-GITHUB-CANARY-20260907-C43D8E`, 정확히 하나인 `EES GitHub Read`의 내부 ID, 전역/대상 암호문 각 1건과 DB/WAL/journal 평문 부재를 함께 확인함. 기본 Confluence·`--jira` 동작과 CLI 출력 필드는 유지됨. 옵션 충돌·다른 Tool/marker·이름 누락/대소문자/중복·중복 저장·물리 평문·실패 출력 조건을 확인함. 임의 토큰/대상 인자·DB/키 쓰기·앱 import·API 호출은 없음.

### 재사용과 미실행

- 저장 검사기의 공통 대상 선택 경로가 바뀌었으므로 해당 파일의 기존 사례까지 재검증함. Jira/Confluence 업무 Tool·화면·플랫폼 인증·재시작 시험은 변경 영향이 없어 반복하지 않음. 기존 Jira v0.1.1 사용자 확인은 유지함.
- 실제 GHES 인증·토큰 scope/조직 정책·접근 가능한 저장소·PR 정확성·권한 격리·새 GitHub 필드의 DB 저장·WebUI 모델 호출·비개발자 사용성·사내 성능은 **미실행**임. PowerShell/uvx 전달 명령은 사외에서 실행하지 않음. 외부 GitHub.com 개발 연결을 내부 API 성공으로 간주하지 않음.
- 정상 요청 예상은 연결 확인 1회, 목록 또는 상세 한 작업당 계정 확인 1회 + PR API 1회임. 실제 지연·호출 수는 미측정이며 자동 재시도·전체 페이지 수집·CI/리뷰 추가 조회는 하지 않음.
- 다음은 [등록·새 필드 저장·대표 PR 확인](../docs/06-github-read-tool.md)임. 신규 필드 확인과 기존 플랫폼 전수 검증을 구분하며, 저장 확인 통과 후 기존 실제 PAT를 입력하도록 안내함.

<a id="storage-success-followup"></a>

## 새 개인 필드 저장 확인 후속 — 2026-09-07

- [4b058996](https://github.com/knadalkim-a11y/team-agent-poc/commit/4b058996d1e3f360ee670da553e2f9bc7a9046a1)의 등록·검사 안내 뒤 받은 사용자 출력 10개를 `--github` 필드 순서와 대조함. 새 개인 PAT 필드의 DB 범위 PASS를 [실환경 증거](scenarios.md#github-storage-check)에 기록하고 STATUS·가이드·환경 기준의 다음 작업을 실제 PAT 적용·PR 조회로 갱신함. 최초 구현 당시의 미실행 기록은 당시 상태로 보존함.
- 이번 변경은 문서뿐이며 Tool·Prompt·저장 검사기는 그대로임. 문서·내부 링크 및 diff만 점검하고 기존 GitHub 27개·저장 검사기 34개 시험과 사내 저장/재시작·Jira/Confluence 검증은 반복하지 않음.
- 실제 GHES API 인증·PR 정확성·사용자 격리·Prompt UI 저장은 아직 미확인. DB 출력의 로그/재시작 미검사를 실패로 해석하거나 GH01 전체 PASS로 확대하지 않음. 다음 한 저장소의 목록/상세 조회 자체가 인증을 포함하므로 별도 연결 사전검사를 추가하지 않음.

<a id="followup-flow"></a>

## 직접 본문·후속 목록·오류 안내 보완 — 2026-09-07

### 기준·실제 발견

- main `9dcdbf60a98124506140b0dca315d50223cfa0ed`와 열린 draft PR #2/#3/#4를 확인하고, 요청에 따라 PR #4 head `4645f21488cceecd97d649a687dd2fd3d29de399`의 AGENTS·STATUS에서 이어감. main·PR #4의 AGENTS는 같은 blob이며 main에 없는 Jira/GitHub 준비·사용자 확인 기록을 보존함.
- Git 직접 인증은 불가했으나 승인된 GitHub 연결로 읽은 43개 파일을 로컬 시험용으로 준비하고 모든 Git blob SHA를 대조함. 로컬 비교용 baseline은 upstream 커밋이 아닌 임시 snapshot이며 게시 커밋은 실제 PR #4 head를 부모로 생성함.
- 가이드는 허용 저장소 하나의 생략과 사용자가 지정한 PR 번호의 직접 상세 조회를 지원하지만 공개 함수는 repository를 필수로 요구하고 이전 목록 번호만 사용하도록 설명했음. 함수의 number 필수·repository 기본값과 설명을 실제 동작에 맞춤. Tool은 이름으로 인자를 전달하며 직접 Python 위치 인자를 쓰는 별도 호출자는 새 순서 `number, repository`를 따라야 함. 저장소 선택·권한·번호 검사는 API 요청 전에 유지함.
- 기존 `_pagination`은 owner/repo 경로의 next 하나만 인정해 숫자 저장소 경로를 거부하고 정상 마지막 페이지의 first/prev만 있는 Link도 미확인으로 처리했음. [GHES 3.17 페이지 공식 문서](https://docs.github.com/en/enterprise-server@3.17/rest/using-the-rest-api/using-pagination-in-the-rest-api)는 숫자 `/repositories/{id}` 링크와 next 소멸에 따른 종료를 설명함. 사내에서 이 문제가 실제 발생했다는 증거는 아니며 기존 합성 fixture가 해당 형식을 다루지 못한 코드상 차이임.

### 변경·검토 범위

- GitHub Tool v0.1.1의 직접 본문 입력·번호 안내, 페이지 메타데이터 처리와 관련 시험만 변경함. 현재 페이지의 모든 PR이 확인된 base 저장소와 같은 양의 정수 저장소 ID를 갖는 경우에만 그 ID의 숫자 경로를 인정함. ID 누락/불일치/잘못된 형식·빈 결과의 숫자 링크는 미확인으로 유지함.
- first/prev/next/last 모든 링크의 origin·경로·조회 조건·중복·관계·번호 범위를 대조함. 정상 마지막은 false, 불명확한 메타데이터는 null로 유지하며 번호만 반환함. 링크 URL을 호출하지 않고 기존 고정 owner/repo GET 요청을 사용함. 전체 건수·자동 다음 페이지 수집·캐시·추가 서버/의존성을 만들지 않음.
- GitHub Prompt 절에 직접 번호·현재 대화의 실제 PR 선택·본문 뒤 목록 조건 재사용·상태 변경 시 첫 페이지·실패 후 행동을 명시함. 범용 작성에 불필요한 조회를 붙이지 않고, 반환된 오류를 빈 목록/본문으로 바꾸거나 자동 반복하지 않음. 기존 Prompt의 다른 절과 Skill은 유지함.
- 변경한 코드·시험·Prompt·가이드의 독립 검토에서 수정 필수 문제는 없었음. 안전한 링크 검증과 응답 원문 미실행, 실패·404의 불확실성·목록 맥락 유지 범위를 대조했으며 실제 모델 동작 검증으로 간주하지 않음.

### 실행 증거

사외 Linux / Python 3.12.13 / Pydantic 2.13.4에서 변경 범위의 **13개 시험 PASS, 0.365초**. 신규 7개와 영향받는 기존 페이지/입력 6개이며 HTTP를 합성 응답으로 대체하고 DNS·소켓 연결을 차단한 시험임. 전체 GitHub suite·인증/저장 시험은 반복하지 않음.

실행 위치는 저장소 `tests/`이며 다음 선택 목록을 `python -m unittest -v` 뒤에 지정함.

```text
test_github_tool.GitHubReadTests.test_direct_detail_omits_single_repository_without_list_preflight
test_github_tool.GitHubReadTests.test_direct_detail_omitted_repository_requires_choice_before_network
test_github_tool.GitHubReadTests.test_canonical_next_and_final_links_keep_requests_on_owner_path
test_github_tool.GitHubReadTests.test_canonical_links_need_consistent_positive_repository_id
test_github_tool.GitHubReadTests.test_last_page_owner_links_work_for_full_short_and_empty_results
test_github_tool.GitHubReadTests.test_all_page_links_must_match_scope_filters_and_relations
test_github_tool.GitHubReadTests.test_contradictory_last_and_out_of_range_next_remain_unknown
test_github_tool.GitHubReadTests.test_list_does_not_invent_total_or_fetch_next_page
test_github_tool.GitHubReadTests.test_full_page_without_confirmed_next_is_unknown
test_github_tool.GitHubReadTests.test_short_page_with_invalid_next_and_maximum_page_remain_unconfirmed
test_github_tool.GitHubReadTests.test_unsafe_or_inconsistent_next_links_are_not_followed_or_trusted
test_github_tool.GitHubReadTests.test_invalid_state_page_and_number_stop_before_network
test_github_tool.GitHubReadTests.test_case_insensitive_repository_and_single_default_are_resolved
```

`python scripts/check_docs.py`: 문서 25개·내부 링크 356개·오류 0·검토 후보 0. `git diff --check`: PASS. 인증·개인 설정·저장 전제·전송·오류 매핑 관련 12개 정의의 AST가 기준본과 같음을 대조함. GitHub Prompt 부분 교체 분량은 1,336자로 2,500자 이내이며 별도 Prompt·핸드오프 파일은 생성하지 않음.

### 미실행·후속

- WebUI 수동 코드·GitHub Prompt 절 적용, 사내 모델의 직접 번호/“두 번째 PR”/“다음 목록” 선택, 실제 페이지 정확성·오류 안내 사용성은 미확인. 사내 적용은 [기존 항목 갱신 안내](../docs/06-github-read-tool.md#followup-update)의 변경 범위만 확인함. 전체 System Prompt 교체·온보딩 적용을 요구하지 않음.
- 인증·개인 필드·저장·전송·Jira/Confluence·화면·시작 스크립트는 변경하지 않음. 완료한 저장/재시작/인증·기본 조회·20회 안정성 검사는 반복하지 않음. 기존 성공·실패·미확인 판정은 [실환경 평가](scenarios.md#github-live)에 보존함.
- 별도 Jira 검토에서 목록 오류의 안전한 `listing.error.message`를 화면이 버리고 재조회만 안내하는 점, 부분 프로젝트 실패의 회복에 따라 다음 목록 범위가 바뀔 수 있는 점을 확인함. 이번 GitHub 흐름에는 섞지 않고 [다음 작업](../docs/STATUS.md)에 남김. Jira 코드·시험은 수정·실행하지 않음.
