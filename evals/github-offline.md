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
