# EES Agent Pack (POC)

Open WebUI의 `EES 통합 Assistant`에 등록할 Git 관리 원본입니다. 현재 파일은 모두 안전한 합성 POC 템플릿이며 공식 사내 정책이 아닙니다.

```text
agent-pack/
├─ system-prompts/
│  └─ ees-integrated-assistant.md
├─ policies/
│  └─ common-policy.md
├─ knowledge/
│  └─ poc-policy.md
└─ skills/
   ├─ policy-grounded-answer/SKILL.md
   ├─ structured-troubleshooting/SKILL.md
   └─ confluence-read/
      ├─ SKILL.md
      └─ scripts/confluence_tool.py
```

| 원본 | Open WebUI 반영 위치 |
|---|---|
| `system-prompts/*.md` | Workspace Model의 System Prompt |
| `policies/*.md` | 공통 규칙의 검토·관리 원본 |
| `knowledge/*.md` | Workspace Knowledge |
| `skills/*/SKILL.md` | Workspace Skills |
| `skills/confluence-read/scripts/confluence_tool.py` | Workspace Tools; 별도 등록 후 Assistant에 연결 |

Confluence 묶음은 **Skill 지침 + 실행 코드**를 함께 관리하는 예시입니다. Open WebUI가 폴더를 자동 설치·실행하지는 않습니다. [설치 안내](../docs/04-confluence-read-tool.md)에 따라 두 항목을 등록합니다. Tool은 기본 비활성화이며, 실제 PAT·문서·사용자 권한은 사내 검증 전입니다.

## 변경 절차

```mermaid
flowchart LR
    Edit["Git 수정"] --> Review["담당자 검토"]
    Review --> Deploy["Open WebUI 반영"]
    Deploy --> Eval["평가 시나리오"]
    Eval --> Release["POC 사용자 공개"]
```

초기에는 관리자가 수동 반영합니다. 자동 동기화, MCP, Router, A2A는 POC 범위가 아닙니다.

## 금지 사항

- 실제 API Key·사내 URL·모델 ID·자격증명 커밋
- 실제 사용자 대화나 개인 정보 커밋
- 승인 전 실제 사내 정책을 POC 템플릿에 혼합
- Prompt만으로 운영 DB 접근 금지가 강제된다고 간주

실제 운영 DB Tool과 자격증명을 연결하지 않는 것이 현재의 구조적 통제입니다.
