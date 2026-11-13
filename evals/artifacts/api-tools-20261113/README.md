# 워크 · 도구 API 명세 v11 제품 비교

[지정 설계](../../../docs/mockups/ees-work/api-tools-20261113/README.md)의 Figma 원본과 개발 환경에서 촬영한 제품 원본을 같은 창 크기와 상태로 대조했다. 모든 캡처는 1920 × 1080, DPR 1이며 왼쪽 메뉴와 오른쪽 업무 도우미가 펼쳐져 있다.

| 상태 | 지정 Figma | 제품 | 측정값 |
| --- | --- | --- | --- |
| 서비스별 API 목록 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-tools-list.png) | [제품 PNG](api-v11-tools-list.png) | [DOM 실측](api-v11-tools-list.json) |
| 등록 초기 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-tools-create-empty.png) | [제품 PNG](api-v11-tools-create-empty.png) | [DOM 실측](api-v11-tools-create-empty.json) |
| 등록 작성 중 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-tools-create.png) | [제품 PNG](api-v11-tools-create.png) | [DOM 실측](api-v11-tools-create.json) |
| 기존 API 편집 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-tools-edit.png) | [제품 PNG](api-v11-tools-edit.png) | [DOM 실측](api-v11-tools-edit.json) |
| 작업 연결 전 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-task-connection.png) | [제품 PNG](api-v11-task-connection.png) | [DOM 실측](api-v11-task-connection.json) |
| 입력·결과 연결 후 | [기준 PNG](../../../docs/mockups/ees-work/api-tools-20261113/figma-task-mapped.png) | [제품 PNG](api-v11-task-mapped.png) | [DOM 실측](api-v11-task-mapped.json) |

## 화면 경계

모든 상태에서 브라우저가 보고한 왼쪽 메뉴·가운데 업무·오른쪽 도우미 너비는 각각 256·1104·560 CSS px였다. 목록과 등록·편집 본문 위치는 x=328, 너비는 960이었다. 편집 저장 버튼은 업무 영역 위쪽 오른편 x=1232, y=120에 있다.

아래 좌표는 전체 PNG 원본의 x=1054에서 각 컨트롤 또는 카드가 흰색으로 렌더된 첫 픽셀과 마지막 픽셀 다음 좌표를 읽은 결과다. DOM JSON에는 테두리를 포함한 CSS 사각형을 별도로 기록했다.

| 세로 경계 (px) | Figma | 제품 |
| --- | --- | --- |
| 목록 검색 입력 | 150–195 | 149–194 |
| 등록 초기·작성 중의 주소, 서비스, 용도 입력 | 238–283 / 326–371 / 414–459 | 238–283 / 326–371 / 414–459 |
| 편집의 주소, API 이름, 용도 입력 | 198–243 / 289–334 / 380–425 | 198–243 / 289–334 / 380–425 |
| 연결 전 단계 헤더 및 작업 두 행 | 235–287 / 288–346 / 347–405 | 235–287 / 288–346 / 347–404 |
| 연결 후 단계 헤더 및 작업 두 행 | 235–287 / 288–412 / 413–537 | 235–287 / 288–412 / 413–536 |

표에 실은 경계의 차이는 0–1px였다. 계정 이름, 왼쪽 메뉴의 최근 항목, 도우미 내용, 포커스·저장 상태 표시는 캡처 환경과 현재 데이터에 따라 달라진다. 전체 화면의 시각 차이는 원본 두 장에서 확인할 수 있다.

## 실행 환경과 범위

기존 Open WebUI 0.11.3+ees.14에서 빌드한 Svelte 셸에 이번 제품의 조립된 JS·CSS와 현재 Python 서비스 코드를 사용했다. Headless Chromium 153으로 제품 메뉴를 조작했고, 테스트 계정과 격리된 SQLite DB를 사용했다. 전체 소스에서 다시 빌드한 셸과 배포 wheel의 검증은 해당 커밋 EES delivery의 Native 결과에서 확인한다. 사내 서비스 인증·호출 및 사내 설치 결과는 미확인이다.

[Native 테스트](../../../tests/test_ees_api_catalog_native.py)는 위 여섯 화면과 DOM을 촬영하고, API 등록·편집·재열기, 작업 입력·결과 매핑, 실 HTTP 테스트 서비스의 응답 표시 및 회차 이력 재열기를 검사한다. CI의 `ees-work-browser-evidence-native-compose` 아티팩트에서 `ees-results/api-v11/index.html`을 열면 해당 실행의 Figma와 제품 원본을 나란히 비교할 수 있다.
