# EES Agent Pack (POC)

Open WebUI의 `EES 통합 Assistant`에 등록할 Git 관리 원본입니다. 현재 파일은 모두 안전한 합성 POC 템플릿이며 공식 사내 정책이 아닙니다.

이 폴더는 담당자가 관리하는 공통 배포 자산의 원본입니다. 팀원 작성물과의 구분은 [관리 경계](../README.md#원본과-배포본)를 따릅니다. 프로젝트를 코딩하는 GPT의 규칙은 [AGENTS.md](../AGENTS.md), Git 준비·WebUI 반영·다음 작업은 [STATUS](../docs/STATUS.md)를 확인합니다. 아래 파일 목록은 Git 원본이며 실제 배포 상태표가 아닙니다.

```text
agent-pack/
├─ ees-prompt-suggestions.json
├─ system-prompts/
│  └─ ees-integrated-assistant.md
├─ policies/
│  └─ common-policy.md
├─ knowledge/
│  └─ poc-policy.md
└─ skills/
   ├─ policy-grounded-answer/SKILL.md
   ├─ structured-troubleshooting/SKILL.md
   ├─ confluence-read/
   │  ├─ SKILL.md
   │  ├─ scripts/confluence_tool.py
   │  └─ references/rich-ui-search-demo.html
   ├─ jira-read/
   │  └─ scripts/jira_tool.py
   └─ github-read/
      └─ scripts/github_tool.py
```

| 원본 | Open WebUI 반영 위치 |
|---|---|
| `ees-prompt-suggestions.json` | 기존 Workspace Model 편집의 Prompts → Import; [첫 화면 적용](../docs/03-openwebui-native-agent.md#first-use-entry) |
| `system-prompts/*.md` | Workspace Model의 System Prompt |
| `policies/*.md` | 공통 규칙의 검토·관리 원본 |
| `knowledge/*.md` | Workspace Knowledge |
| `skills/*/SKILL.md` | Workspace Skills |
| `skills/confluence-read/scripts/confluence_tool.py` | Workspace Tools; 별도 등록 후 Assistant에 연결 |
| `skills/jira-read/scripts/jira_tool.py` | Workspace Tools; 프로젝트별 현황 화면을 코드에 포함 |
| `skills/github-read/scripts/github_tool.py` | Workspace Tools; GHES의 개인 PAT 기반 PR 목록·본문 읽기 |

Confluence 묶음은 **Skill 지침 + 실행 코드**를 함께 관리하는 예시입니다. Open WebUI가 폴더를 자동 설치·실행하지는 않습니다. [설치 안내](../docs/04-confluence-read-tool.md)에 따라 두 항목을 등록합니다. 코드 기본값은 비활성화이며 실제 준비·배포 상태는 [STATUS](../docs/STATUS.md), 실환경 판정은 [평가표](../evals/scenarios.md#confluence-live)에만 기록합니다.

Jira는 작은 고정 조회 흐름으로 시작하며 별도 Skill을 추가하지 않습니다. 기존 System Prompt의 조건부 조회 안내와 함수 설명을 사용하고 [Jira 안내](../docs/05-jira-read-tool.md)에 따라 Python Tool만 추가합니다. 화면은 같은 파일 안에 있어 별도 HTML 복사·빌드가 필요하지 않습니다. 확인한 인증·적용 원본은 STATUS에서 관리하며 다른 환경으로 옮길 때 필요한 조건만 확인합니다.

GitHub도 별도 Skill 없이 조건부 Prompt·작은 함수 설명과 기존 채팅 표로 시작합니다. [GitHub 안내](../docs/06-github-read-tool.md)에 따라 도구를 등록하고 새 개인 입력칸의 저장을 확인합니다. PR 목록·본문만 읽으며 GitHub.com의 개발용 연결과 사내 GHES 연결은 별개입니다.

대화 시작 예시는 기존 모델의 화면용 메타데이터입니다. 새 Skill·Tool이나 모델 전체 가져오기 파일이 아니며 System Prompt를 교체하지 않습니다. 질문 버튼은 클릭 즉시 전송될 수 있으므로 실제로 보낼 수 있는 문장으로 작성하고 부족한 대상은 대화에서 확인합니다. [팀원용 시작 안내](../docs/07-team-quickstart.md)는 사용자가 읽는 문서이고 개발·평가 이력을 포함하지 않습니다.

## 변경 절차

Confluence의 [Rich UI 예제](../docs/04-confluence-read-tool.md#rich-ui-demo)는 합성 데이터 개발 참고자료입니다. Skill·Tool과 함께 자동 배포되는 파일은 아닙니다.

```mermaid
flowchart LR
    Edit["Git 수정"] --> Review["담당자 검토"]
    Review --> Deploy["Open WebUI 반영"]
    Deploy --> Eval["평가 시나리오"]
    Eval --> Release["POC 사용자 공개"]
```

초기에는 관리자가 수동 반영합니다. 자동 동기화, MCP, Router, A2A는 POC 범위가 아닙니다.

이 변경 절차와 공통 정책의 변경 관리 규칙은 이 폴더에서 관리하는 공통 배포 자산에 적용합니다. 변경은 Git 원본에서 검토한 뒤 반영하며, 해당 배포본을 UI에서 먼저 수정했다면 검토 후 Git 원본과 일치시킵니다. STATUS에는 실제 반영한 원본 커밋과 검증 증거를 남기며, 모르는 적용 버전은 미확인으로 둡니다. Skill 내부 `scripts/`는 기능 실행 코드이고, 저장소 최상위 `scripts/`는 개발·운영자용 실행 스크립트입니다.

## 금지 사항

- 실제 API Key·사내 URL·모델 ID·자격증명 커밋
- 실제 사용자 대화나 개인 정보 커밋
- 승인 전 실제 사내 정책을 POC 템플릿에 혼합
- Prompt만으로 운영 DB 접근 금지가 강제된다고 간주

실제 운영 DB Tool과 자격증명을 연결하지 않는 것이 현재의 구조적 통제입니다.
