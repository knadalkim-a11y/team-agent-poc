# 워크 · 도구 — API 명세 관리 및 업무 연결

2026-11-13 사용자는 “이 구조대로 피그마 페이지 '워크.도구' 쪽을 사용하려고해. (…) 코드도 이 페이지 설계 기반으로 시각적으로 동일하게 구현할거야”라고 지정했다. [워크 · 도구 페이지 머리말](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=1285-1842)에서 공식 화면을 찾을 수 있다. 아래 프레임은 2026-11-13 UTC에 조회했다.

## 구현할 판

- 시각 기준은 지정 당시의 Figma 프레임이다. 목록·등록·편집 및 업무 절차 연결 상태를 PNG로 고정했다. 같은 행의 브라우저 캡처는 v11 HTML 목업의 실제 조작과 화면 구성을 재현한다. 두 렌더 사이에 차이가 있을 때 제품의 시각 목표는 Figma다.
- 동작·예시 기준은 [단일 HTML 목업 v11](../design-mock-16-api-tools.html)이다. 파일을 내려받아 브라우저에서 연다. 저장소 파일명의 `16`은 기존 목업 파일 일련번호다. 지정된 원본 파일명은 `EES_Workflow_API_Tools_Mockup.html`, 크기는 844,426바이트, SHA-256은 `d07d1ddd819b233daf782194a78fcb459cd8c6cb25763d07573e17aef0039fa1`이다.
- PR 설명의 고정 커밋에서 HTML과 PNG를 함께 연다. Figma 프레임은 이후에도 편집될 수 있다.

| 비교할 화면 | Figma 프레임 | Figma 렌더 | 브라우저 v11 |
| --- | --- | --- | --- |
| 서비스별 API 목록 | [서비스별 목록](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2405-1236) | [목록 PNG](figma-tools-list.png) | [기본 데이터 3개](01-api-catalog.png) |
| API 명세 등록 · 작성 중 | [직접 등록](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2464-1732) | [작성 중 PNG](figma-tools-create.png) | 직접 입력 후 확인 |
| API 명세 등록 · 처음 열 때 | [빈 등록 양식](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2503-21403) | [빈 등록 PNG](figma-tools-create-empty.png) | [빈 등록 양식](02-api-registration.png) |
| API 명세 편집 | [기존 API 편집](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2416-1001) | [편집 PNG](figma-tools-edit.png) | [백업 결과 조회 · GET /backups](03-api-edit.png) |

위 화면은 모두 1920 × 1080, 왼쪽 메뉴와 오른쪽 업무 도우미가 펼쳐진 상태다. 왼쪽 메뉴 256px, 가운데 업무 영역 1104px, 오른쪽 도우미 560px로 비교한다. 목록의 콘텐츠 폭은 두 렌더 모두 960px다. 등록과 편집은 가운데 페이지로 전환되며, 업무 도우미를 연 채 사용할 수 있다. 브라우저 캡처는 v11의 상태와 조작 결과를 확인하는 자료다.

| 확인한 차이 | 제품에서 따를 기준 |
| --- | --- |
| 등록·편집 폼 콘텐츠는 Figma 960px, HTML 800px | Figma의 폼 폭과 필드 배치를 따른다. |
| 편집 저장 버튼은 Figma 상단 오른쪽, HTML 하단 | 상단 오른쪽에 두고 변경·검증 상태에 맞춰 동작을 확인한다. |
| 목록 안에서 이름과 요청 경로가 나오는 순서가 다름 | Figma 목록의 표시 순서를 따른다. |
| 직접 등록은 빈 양식으로 열리고 입력하면 작성 중 상태가 됨 | 목록·도구 선택 등에서 들어오면 빈 등록 프레임을, 직접 입력한 뒤에는 작성 중 프레임을 사용한다. |

업무 절차에서 [작업에 API를 연결하기 전 Figma 화면](figma-task-connection.png)과 [입력·결과 전달을 연결한 Figma 화면](figma-task-mapped.png)도 같은 해상도로 고정했다. 해당 프레임은 [연결 전](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2484-2403)과 [결과 전달 설정](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2478-2253)이다.

## 워크플로에서 끝까지 확인할 상태

| 사용자 행동 | 구현에서 확인할 동작 | Figma |
| --- | --- | --- |
| 도구에서 API 찾기 | 서비스별 목록의 이름·용도로 후보를 찾고, 상세에서 요청 방식·주소와 요청·응답을 확인한다. | [API 상세](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2393-457) |
| 새 API 직접 등록 | 목록 상단의 등록에서 요청 방식·주소, 이름·용도, 소속 서비스를 입력한다. 새 서비스도 등록 과정에서 추가하고, 기존 서비스는 서비스 관리에서 수정한다. | [직접 등록](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2464-1732) · [서비스 관리](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2488-2230) |
| 제공자가 준 명세 가져오기 | URL을 가져오고 여러 기능이 있으면 등록할 기능을 고른다. 파일·텍스트 입력은 보조 경로다. | [명세 URL](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2474-2624) · [기능 선택](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2474-2634) |
| 기존 API 편집·갱신 | 상세에서 편집한다. 명세를 갱신해 사용 중인 결과 필드가 바뀌면 영향을 받는 작업과 항목을 보여 준다. 알람 작업의 연결을 수정하고 적용하면 목록으로 돌아간다. | [편집](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2416-1001) · [변경 영향](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2503-2582) |
| 업무 절차에서 작업 자동화 | 워크플로 → 단계 → 작업에서 API를 선택한다. API 이름·용도·서비스·주소를 함께 확인하고 해당 작업에서 쓸 입력과 결과를 연결한다. | [단계·작업](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2429-1549) · [도구 연결](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2391-299) |
| 연결된 작업 결과 확인 | 등록된 API의 결과 경로와 필드에 맞추어 작업 결과를 표시한다. 대상 공장이 필요하면 해당 API 주소나 입력 명세에서 처리한다. | [실행 결과](https://www.figma.com/design/XK2wTos6sEuxSHhIj7cqg6?node-id=2392-376) |

## 제품 구현 범위와 확인 방법

- **등록·저장** — 기존 서비스의 API를 업무 도구로 등록한다. 이름·용도·서비스·요청 방식·엔드포인트, 입력 위치와 응답 필드 매핑이 저장 뒤 다시 열었을 때 유지되어야 한다. API마다 다른 응답 구조는 명세에 맞춰 해석한다.
- **작업 연결** — 작업마다 선택한 API와 입력·결과 매핑을 저장하고 다시 열어 확인한다. 이미 사용 중인 명세를 수정할 때 기존 작업에 미칠 영향을 표시한다. 제공 API가 없는 기능은 EES Web에서 개발 요청 후 공개된 엔드포인트를 등록한다.
- **권한·실행** — 사용자·워크스페이스의 기존 편집·실행 권한과 해당 서비스가 요구하는 인증을 제품에서 적용한다. 인증 방식은 실제 서비스 계약을 따른다. 사용자는 등록 단계에서 일괄 인증 연결이나 대상 공장을 별도로 선택할 필요가 없다.
- **비교** — 같은 화면 상태·창 크기·메뉴 폭으로 실제 제품과 Figma를 대조하고, HTML의 대표 데이터로 등록 → 편집 → 작업 연결 → 결과 확인을 제품에서 재현한다. 제품 저장·권한·실제 API 호출 및 사내 확인은 구현 검증 때 기록한다.

2026-11-13 기준 이 기록의 검증 범위는 설계 프레임·파일 무결성과 세 대표 화면의 브라우저 재현이다. 나머지 프레임은 표의 위치로 찾아간다. 제품 구현·시각 일치·사내 확인은 대기 중이다.
