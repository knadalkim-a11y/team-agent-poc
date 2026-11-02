# 탐색·패널 시안 2 제품 검증

<a id="navigation-motion-product-20261102"></a>

## 2026-11-02 · 탐색·패널 시안 2 제품 반영

- **기준/환경:** main `745e5ef`, 시안2 `aecff7a`, Open WebUI0.11.3 소스 `2a960a5`, 고정 Node22.16.0/npm10.9.2. Figma C3 `1443:137` 현재 렌더를 읽고, 종전 페이드/패널16px/즉시 공간 변경과 승인2판의 차이를 TASK에 기록했다. 시안 HTML은 그대로 보존한다.
- **수정/검증 경계:** Svelte 탐색·범위·패널 및 공통 motion/CSS, 전역 기존 도구 목록·소속별 편집 권한을 구현한다. 새로운 도구 저장 형식·운영 요청·실제 사용자 자산 변경은 없다. Native 브라우저는 실제 제품과 업무 서비스/임시 SQLite를 쓰며 계정·대화 응답·외부 전송은 명시적 합성 fixture다.
- **첫 검사와 수정:** 기존 시험의 붙은 패널 내용 페이드/즉시 닫기 및 breakpoint에서 exit 취소 기대를 승인된 동일 표면 슬라이드로 갱신했다. 기존 도구 fixture의 누락된 필수 system_id와 명시적 담당 시스템 선택/비동기 담당자 조회를 보완했다. UI Node307/307, 운영 계약52/52를 통과했다. 전역 목록의 권한 회수·업무용 목록 범위, 다른 시스템 계약 저장·읽기 전용·늦은 응답을 포함한다.
- **첫 빌드 실패:** Svelte 빌드 중 도구/스타일 원본이 변경되어 provenance 검사 `Frontend inputs changed while building`이 산출물 채택을 차단했다. 실패 checkout/log는 보존하고 같은 고정 commit의 새 checkout으로 최종 원본을 다시 빌드한다. 실패 산출물을 제품 검수 통과로 사용하지 않는다.
- **첫 실제 제품 검사:** 고정 소스 빌드/패키지 후 Chromium133에서9개 Native 시험을 수행했다. 붙은 패널·범위 빠른 왕복/응답 역전·접힌1920/480 목록·키보드 패널/초안5개가 통과했다. 새 기하 측정은 메뉴 전환 중 사라진 카테고리 값을 처리하지 못했고, 기존 시험은 펼침 중 보이지 않는 패널 단추/범위 휠 지점과 새 담당 시스템 선택 단계를 고려하지 않아 실패했다. 실제 일반 패널의 닫기 아이콘 HTML이 이스케이프돼 문자열로 보이는 결함도 발견해 명시적 버튼 렌더로 수정했다. 범위 닫기의 clip-path 기준값과 라벨 flex 크기 때문에 생길 즉시 전환도 보완한다. Svelte의 새 self-closing div 경고를 제거했고 원본 검토 후 새 checkout에서 다시 빌드한다. 이 과정의 두 번째 inputs-changed 차단도 보존한다.
- **추가 자동 검사:** 전체 Node665/665, 실제 patched checkout을 쓰는 frontend32/32, 목업 빌드 계약6/6 통과.
- **진행 중:** 보완한 실제 Native 브라우저 검사, 최종 push·PR·CI. 사내 사용자 확인·병합·실제 적용은 미실행이다.

- **후속 검수:** 새 패키지14개 Native 검사에서10개가 통과했다. 이전 순간 전환을 전제로 한 overlay 폭 측정/아직 펼쳐지는 목록 클릭/도구에서 숨겨진 작업 위치 선택을 새 동작에 맞춰 보완했으며 해당3개는 후속 검사에서 통과했다. 모드 글자의 max-width가 inline span에 적용되지 않는 실제 결함을 중간 프레임 검사로 찾아 모드 단추를 flex로 바로잡았다. 이 CSS 보완본을 새 고정 checkout에서 빌드해 최종 검수한다. 기존 담당 시스템을 명시하는 도구 작성·공용 도구 스타일·Native 화면 왕복의 미저장 절차/도구 초안은 실제 제품에서 통과했다.
- **공용 도구 보존:** Python3.12의 격리된 로컬 시험 환경에서 `test_ees_shared_tools_native.py`43/43 통과. 실제 Native 자산/개인 PAT/ACL 및 임시 SQLite를 사용하며 외부 응답은 합성이다. CI의 Python3.11·Windows 검사는 별도다.


### 최종 로컬 결과

- 고정 소스 빌드와 실제 wheel 패키지를 완료했다. wheel SHA-256 `fd76a30d52f455d23338e702177f117c5e069395c665a69e80b49d3e0034ceaf`, 프런트엔드5582파일이다. 원본 지문 검사를 우회하지 않았다. EesShell의 기존 root/resize 접근성 경고3종은 남으며 새 코드의 self-closing 경고는 제거했다.
- 최종 패키지의 Native14개 대상은 모두 통과했다. 최종 묶음은13통과/1실패였고, Native 왕복 시험 준비 중 모드의 실제 조회와 목록 클릭이 겹친1건은 조회 완료 후 초안을 준비하도록 보완하여 재검 통과했다. 해당 왕복과 기하/정지 스크린샷2개 재검도 통과했다. 단순 정지 캡처를 애니메이션 검증으로 대체하지 않았다.
- 실제 프레임에서 사이드바56~256px(21개 관측값), 카테고리0~36px(27개), 작업 위치0~127px(35개), 모드 라벨0~65.75px(5개), 라벨 투명도 항상1을 확인했다. 범위 메뉴는 실제 clip-path 중간값과4px 이동, 패널은 불투명 전체 폭 슬라이드/대화 공간 전환을 확인했다. 승인2판의 동작·크기 기준과 대조한 범위이며 기존 대화/업무 본문 전체의 픽셀 동일성을 주장하지 않는다.
- 1920/1366에서 붙은 패널,1095의 겹친 패널,1920/480의 접힌 공장/시스템 목록을 검사했다. 빠른 왕복·중간 반전·동작 줄이기·메뉴 교체·응답 순서 역전·권한 회수/없음·검색·키보드/초점·대화와 업무 초안·기존 도구 작성 및 Native 화면 왕복을 포함한다. 전역 화면은 EMS/FDC 두 시스템의 실제 저장된 합성 도구를 동시에 보이고, 업무로 돌아오면 위치/카테고리 접힘/대화 초안을 유지했다.
- 재현 진입점: `node --test tests/*.cjs`665/665, `test_ees_frontend_build.py`32/32(`EES_TEST_FRONTEND_SOURCE_DIR`는 고정 patched checkout), `test_ees_work_operations.py`52/52, `test_ees_shared_tools_native.py`43/43, `test_build_design_mock.py`6/6. 실제 브라우저는 `EES_TEST_CHROME`, `EES_TEST_BRANDING_DIR`, `EES_TEST_SCREENSHOT_DIR`를 지정한 `test_ees_motion_native`6개와 SourceShell4개/작성3개/HelperChat1개를 사용했다. 로컬 원본 로그는 `scope-qa/*release*.log`, 프레임/스크린샷은 `dist/navigation-motion-product-release/`다.
- `python scripts/check_docs.py`, `git diff --check` 통과. 누적 v4 기록이1MiB 점검 한계에 닿아 **이번 기록만** 이 문서로 연결했고 기존 날짜별 근거/앵커는 보존했다. 승인된 시안2 HTML/편집 원본은 변경하지 않았다.
- 로컬 완성 뒤 같은 브랜치의 push·PR·CI를 수행한다. 원격 결과는 PR의 검사/증거로 확인하며, 실제 사내 사용자 확인·병합·적용은 수행하지 않았다.

### 원격 게시 원본 연결

로컬 Git의 HTTPS 인증 정보가 없어 직접 push가 실패했고, 이미 연결된 GitHub의 Git 객체 API로 같은 파일·부모 순서를 게시했다. 각 파일의 Git blob SHA와 각 커밋의 root tree SHA를 로컬과 대조해 모두 일치했다. 게시 시각/작성자 메타데이터가 달라 커밋 ID는 바뀌며, 기존 로컬 이력도 보존한다. 승인된 시안2는 아래 `aecff7a`에 대응하는 원격 `39d4739`에서 읽을 수 있고 HTML SHA-256은 TASK의 승인값 그대로다.

| 로컬 원본 커밋 | 원격 대응 커밋 | 동일한 root tree |
|---|---|---|
| `c8934f587a028ff244dfabe5ef3f1b4852e5a209` | [`dd76347`](https://github.com/knadalkim-a11y/team-agent-poc/commit/dd76347bd061fa877801df7ce9c487a5f60ebd86) | `1cea6f65daf28484379eaf52c44f62eca20b6e78` |
| `3d47e6b4edeff9ec48fdb9f1c3e81e26e2f034e7` | [`b3e91f7`](https://github.com/knadalkim-a11y/team-agent-poc/commit/b3e91f773342b8413b48aaae8985f697eb8ca2ed) | `458c3fef43893596fb871eea4ab4503c25023088` |
| `f0fe99e65a75cb07959f5daadd99d1293260f7fe` | [`0389e16`](https://github.com/knadalkim-a11y/team-agent-poc/commit/0389e16cf18e139d2799747dbdb0b17171f786fd) | `ae0dfa8eb76f10c6aca0f4288850756cad68b64c` |
| `aecff7a3ae41a3031eff8cffeb5252f5a7bd86af` | [`39d4739`](https://github.com/knadalkim-a11y/team-agent-poc/commit/39d473919a4457b6c50b61800c683d9f19e2a382) | `68bbac1825a5d3016b3348755d6b3d25cc099a68` |
| `93154e211a6b99e6607db6823c671d9f3f9792ba` | [`24c2869`](https://github.com/knadalkim-a11y/team-agent-poc/commit/24c28699bdbdd92c064ad37aa981ec526a158d5d) | `c20e2b9cd0dfdc7b84c69762500e611e0a88b7b9` |

이 대응 기록은 원격 게시 방식과 원본 동일성에 대한 증거다. PR·CI 최종 판정은 해당 PR의 head/Checks를 따르며, 병합·사내 적용을 뜻하지 않는다.
