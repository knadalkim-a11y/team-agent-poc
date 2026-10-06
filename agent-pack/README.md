# EES Work 관리 원본

현재 기준은 [통합 구현 계약](../docs/mockups/ees-work/TASK.md#integrated-work-20261002)이다. 새 설치에는 데모 절차·전문 Assistant·등록 Skill 콘텐츠가 없다. 콘텐츠 제거와 Native 도구/모델/Skill 관리 기능 제거를 구분한다.

| 원본 | 역할 |
|---|---|
| [GitHub Tool](skills/github-read/scripts/github_tool.py) | 기존 Native ACL·개인 설정으로 PR 조회 |
| [Jira Tool](skills/jira-read/scripts/jira_tool.py) | 기존 Native ACL·개인 설정으로 업무 조회 |
| [Confluence Tool](skills/confluence-read/scripts/confluence_tool.py) | 기존 Native ACL·개인 설정으로 문서 조회 |
| [업무 공개 서비스](skills/ees-work-demo/scripts/ees_workflow.py) | 같은 Native 서버의 인증된 업무 API와 기록 조회 |
| [Workspace](skills/ees-work-demo/scripts/ees_workflow_workspace.py) | 초안/게시본/진행/설정/판정/개인 상태 |
| [Operations](skills/ees-work-demo/scripts/ees_workflow_operations.py) | 승인된 호출/예약/도구 검토/요청과 효과 추적 |
| [AI Tool](skills/ees-work-demo/scripts/workflow_tool.py) | 조회·초안 제안·화면 안내만 노출; 저장/게시/실행/확정 없음 |
| [공통 도움말](skills/ees-work-demo/scripts/workflow_help.json) | UI와 대화 조회가 함께 읽는 용어·예시·근거 지침의 단일 원본 |
| [도구 시작 예시](skills/ees-work-demo/scripts/workflow_tool_examples.json) | 새 초안의 합성 이름·설명; 실제 연결은 현재 등록 기능에서 확인하며 자동 등록/실행 없음 |
| [공통 정책](policies/common-policy.md) | 권한·비밀정보·미수행/실패 보호의 관리 근거; 자동 Skill 등록 아님 |
| [관리 범위](ees-demo.json) | 빈 기본 등록 목록, 폐기 ID·보존 경계 |

`skills/ees-work-demo/scripts/`는 현재 공통 서버 코드가 있는 기존 설치 원본 경로다. 폴더명 때문에 통째로 삭제하거나 별도 서버로 복제하지 않는다. 실제 PAT·모델 연결·사용자 Skill/Tool/대화는 Native 저장소에 남으며 Git에 복사하지 않는다.

## 변경과 적용

Git 원본의 코드 변경과 이미 등록된 사내 자산 변경은 다르다. `ApplyDemo`는 폐기 안내로 종료하며 기존 명령을 삭제 명령으로 바꾸지 않는다. 실제 자산 정리는 [운영 안내](../docs/03-openwebui-native-agent.md#integrated-work-install-20261002)의 preview → 비공개 백업 → 계획 지문 확인 → 명시적 적용을 별도 승인 뒤 수행한다. 사용자 수정·참조 존재·출처 불명 항목은 자동 삭제하지 않는다.

세 도구의 설치/개인 설정은 [Confluence](../docs/04-confluence-read-tool.md), [Jira](../docs/05-jira-read-tool.md), [GitHub](../docs/06-github-read-tool.md)를 따른다. 등록 Skill 지침이나 전문 모델 preset 없이 실제 도구와 기반 모델을 재사용할 수 있다. 새 업무의 J는 Native 함수·승인된 revision/hash·입력/결과 계약을 참조한다.

이전 시연·배포·실패는 [기존 평가](../evals/scenarios.md)에 보존한다. 프로그램 Restore는 사용자 DB나 삭제한 자산을 복구하지 않는다. 실제 환경 변경·실행 결과는 [STATUS](../docs/STATUS.md)에서 코드/합성 시험과 구분한다.
