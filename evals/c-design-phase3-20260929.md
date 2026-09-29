# C안 3차 검수·Native 보내기·병합 준비 기록

[평가 기록 찾아보기](scenarios.md#evidence-index) · [현재 작업 상태](../docs/STATUS.md)

<a id="c-design-phase3-20260929"></a>

## C안 통합 회귀·개발환경 검수 · 2026-09-29

**원본·범위:** 같은 Draft #66의 원격/로컬 `7d9f2caaa7ef39522fd5fa3f69af732e5fcebeeb`와 main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`, 두 AGENTS/STATUS·깨끗한 checkout을 재확인했다. main의 과거 #65 병합 대기는 반복하지 않았다. [필수 경로·합격/중단 조건](../docs/mockups/ees-work/TASK.md#c-design-phase3-20260929)을 먼저 정했다. 1·2단계/세 보완과 #65를 보존하고 아래 조회 실패 보호만 수정한다. CSS·backend·인증/저장/실행기·버전 ees.12/Pack0.2.14는 그대로다. #53·Windows 작업·실계정/운영 DB는 건드리지 않는다.

**환경·경계:** 기존 단일 `.venv` Python3.11.16/187개 의존성, Node24.19.0, Chrome153.0.8010.52, 공식 Open WebUI0.11.3 wheel(`8436f9bb…fa547`)을 재사용했다. 실제 CLI 앱은 실제 Native 가입/로그인/대화·Tool/Valves/승인·모델 adapter·P 게시·EES HTTP·임시 SQLite를 사용한다. 이 앱의 외부 HTTP/OpenAI 응답만 loopback 합성이다. 별도 브라우저 fixture는 실제 패키지 frontend/EES 서비스/임시 DB이며 Native 인증/채팅·외부 전송이 합성이다. 실제 Native 계정 전환 브라우저와 실제 Users/Groups/ACL/자산 검사는 따로 집계한다.

**Figma·제품 차이:** 00:52~00:55 UTC(09:52~09:55 KST)에 지정 파일/페이지의 비교603:963과 J6/P1/T2, 총10개 context/렌더 및 원본1920×1080 PNG4개를 읽었다. 원본 쓰기 없음. 동일1920 제품을 직접 대조하고 1536×960/1366×768·긴/좁은/다크는 반응형 행동으로 확인한다(해당 크기·다크 Figma 원본은 없음). 제목30/42·결과22/34·여백32/24·선택 표현·단일 행동·독립 스크롤을 기준으로 한다. Native 계획 dialog, 기본값 실행 허용, 현재 입력/호출 snapshot, 여섯 예시 밖 실제 대기/부분/UNKNOWN 등은 의도된 차이다. 고정 집계·4초 타이머·가짜 결과를 넣지 않았다. Figma asset host 과거 차단은 반복하지 않고 지원 inline 렌더를 사용했다. SVG 원본 전체 바이트 대조는 미실행이며 아래 패키지 자산 바이트 검사와 다르다. 개발자 자체 사용성 검토를 사내 사용자 수락으로 표시하지 않는다.

### 결함과 시험 준비 오류

- **제품 재현:** baseline 실제 legacy 초안 저장→검토 자료 열기→조회 실패에서 오류 안내 뒤 dialog_open/자료 잔존/본문 자료 잔존이 모두 true였다. 현재/과거의 실패한 조회는 공통 본문을 숨기고 모든 보조 자료 창의 복사 내용을 즉시 비운다. 미저장 글은 기존 draft map에 남겨 성공 재조회 뒤 복원하며 저장 DB는 바꾸지 않는다. 과거 건 ID도 창의 대상에 포함하고 최초 과거 조회 실패의 재조회 대상을 보존한다.
- **중간 제품 회귀:** v2의 controller65 중64PASS/1FAIL은 current 실패를 별도 성공한 historical 조회에도 적용한 과도한 guard였다. 각 건의 조회 성공은 독립적으로 인정하되 실패 당시 열린 과거 자료는 그 건을 다시 읽기 전까지 숨기는 조건으로 좁혔다. 같은 단독 검사 및 v3 controller21/panel44 전체 PASS로 닫았다.
- **준비 오류:** 첫 privacy 모듈이 import된 suite까지25개를 실행한 선택 오류, 과거 진행 chat 재사용/펼침·비동기 대기 오류를 분리했다. v2 브라우저41은36PASS/고유5FAIL(서브검사 포함6실패): 접힌 상세 미열기, 사람 확인 busy 전 재개, 이미 열린 메뉴 toggle, 숨긴 본문 버튼을 찾는 옛 기대, 과거 내부 이력 미펼침이었다. 실제 클릭·대기·재조회 경로를 수정하고 같은 조건으로 재검한다. 강제 DOM 열기/JS 클릭으로 우회하지 않았다.
- **전체 앱 준비:** Valves timeout 상한, 이미 연결된 chat 재사용, Native release note 설정, 게시 id_map, 선택 완료 전 클릭을 시험에서 수정했다. 실제 worker의 `encryption_required`는 임시 환경의 Native 암호화 flag 누락을 정상 차단한 결과다. 기존 임시 WEBUI_SECRET_KEY와 ENABLE_VALVE_ENCRYPTION을 사용하며 서버 보호를 완화하지 않는다. Native 계정 fixture의 import 준비 오류와 teardown 잔여 task 경고도 별도 로그로 남긴다. 실패/중간 버전을 최종 PASS에 합산하지 않는다.

### 최종 유효 판정

**3차 개발환경 검수 통과.** 최종 동일 제품 wheel SHA256 `d35bc2bb4adc789cc93752b49550a47446461f1e54ba0015a3952e6af78ca254`, 포함 자산23개와 원본 바이트 일치/불일치0. 최종 code freeze145개를 보존했다. 후반 변경은 전체 앱 시험 준비와 fixture 종료 정리뿐이며 영향 검사만 재실행했다.

| 최종 근거 | 판정 |
|---|---|
| 실제 CLI/Native 앱 | PASS, 26개 기록 지점(단위시험26건 아님). 가입/승인·두 사용자·실제 대화 API/2메시지 저장/브라우저 재표시, legacy 저장/복원/실패/재시도, Native 고정3호출·AI1·후보 입력/명시 재개·사람 확인/재기동·이력/복귀 |
| 제품 브라우저 fixture | 41/41 PASS, skip0, 125.040초. 완료 CTA inline/dock·T 목록/초점/T→P·직접 진입/재열기, 과거 판정, 활성5상태 초안 차단, 두 탭 충돌/늦은 응답, 크기3종·긴/좁은/다크·키보드 |
| 서비스/실제 Native API·자산 | 45 PASS + 실제 Native 계정 전환 브라우저1 PASS. 권한 회수/게시 충돌·snapshot·사용자 자산/키 보존·UNKNOWN. teardown 수정 영향3+1 재검도 PASS, 잔여 task 진단0 |
| 화면/controller | Node25·panel44·controller21 PASS. 문서·구문·UTF-8·diff 검사 PASS |

전체 앱의 P는 호출 성공/4개 J 완료여도 저장 `scope_complete=false/source_scope_limited`라 과거 화면의 전체 기준 미충족을 유지한다. 실제 worker 실패는 final_validation 미기록→미판정, 사람 J는 저장 succeeded→화면 통과다. 이는 호환 실패판정 fixture와 별개다. 실제 완료 버튼·과거 메뉴·초안 차단을 다시 조작했다. 강제 종료 후 같은 run/call UNKNOWN·외부 호출1회 유지/자동 재실행0을 확인했다. 직전 패키지 Restore/재적용 뒤 Native 응답8개·대화2메시지·개인 Valves/키·실행이 같았다.

준비 오류의 추가 원인은 부분 범위를 전체 통과로 기대한 시험, 최초 관리자 생성 후 가입 비활성 설정, 타인 case의 기존 `400/case_not_found`를403으로 기대한 시험이었다. 임시 가입 설정은 검사 뒤 원복했고 타인 chat401/case400에서 자료가 없음을 확인했다. 최종 완주본만 집계하며 초기9회 중단 기록은 첨부 JSON에 보존한다. 실제 Native composer 보내기 버튼은 미실행(실제 completion·chat 저장 API와 브라우저 표시/재접속 검증), fixture 채팅 클릭과 구분한다.

**보존·재사용:** 기존 ees.10/11 wheel이 이 작업 위치에 없어 과거 버전 writer/물리 Restore를 새로 실행한 것으로 표시하지 않는다. 해당 backend/builder는 불변이므로 [#65의 TR21 및 물리 Apply/Restore 3건](scenarios.md#shared-native-runtime-20260925)과 [SA25 legacy fallback](scenarios.md#system-authoring-20260924)을 당시 버전의 유효 근거로 재사용한다. Native protocol에 구형 writer를 허용한다는 뜻이 아니다. 이번 실제 앱의 직전7d9f 패키지↔최종 패키지 교체는 같은 임시 DB/키/자산의 프로그램 호환 검사이며 DB rollback이 아니다.

**미실행·제외:** Windows·사내 설치/실서버·실 API/모델 품질·OP-01~04·비개발자 실제 사용자 수락은 미실행이다. 병합·배포·Draft 해제는 승인 범위 밖이며 하지 않는다. 09-30까지 지침대로 커밋은 `[skip ci]`, 원격 dispatch/재실행 없음. 검토용 PNG·핵심 JSON/로그·증거 ZIP은 Work 결과에 첨부하고 프로그램 wheel과 구분한다.

<a id="c-design-composer-merge-20260929"></a>

### 후속 Native 보내기 gate·병합·시험 적용 준비 · 2026-09-29

**인수·승인:** 원격 main `e995fe16e4835f2d1799c95f3d6d1b74ce381389`, Draft #66 head `a49350e31dcbbc4d1687293a0ccd8dcf0b541989`와 깨끗한 로컬이 사용자 인계 SHA와 일치했다. 두 대상 AGENTS/STATUS, 앞선 1·2·3차 기록과 dist/wheel/로그/검토 ZIP 접근을 확인했다. #53은 별도 Draft로 유지한다. 사용자가 이번 gate와 관련 보완, 조건 충족 후 Draft 해제·#66 병합, 정확한 병합본 배포 준비를 승인했다. 위의 병합 미승인 기록은 당시 경계이며 이번 승인과 다르다. 회사 PC 적용은 사용자가 실행하고 새 사내 성공 보고는 아직 없다.

**남은 필수 경로 PASS:** 기존 공식 앱 시험에 `--composer-only`를 추가했다. 같은 최종 wheel `d35bc2bb4adc789cc93752b49550a47446461f1e54ba0015a3952e6af78ca254`, 공식 CLI·실제 Native 가입/로그인·대화/EES API·새 임시 SQLite를 사용했다. 외부 모델의 SSE 응답만 loopback 합성하고 사내 모델 품질로 확대하지 않는다. 준비 단계의 빈 대화/모델·사용자 설정과 검증용 GET을 제외하고 모든 메시지는 실제 composer 입력과 보내기 클릭으로 생성·저장됐다. completion API 직접 실행이나 저장 메시지 주입은 없다.

| 실제 조작 | 최종 증거 |
|---|---|
| 업무패널을 연 기존 대화의 첫 전송 → 새로고침 → 같은 대화 두 번째 전송 | trusted 입력/클릭 각 1회, 매번 Native completion 요청/task/외부 모델 호출 각 1회, 저장 메시지 2→4개, 응답 표시 1→2개, 과거 메시지 본문/ID 보존 |
| 새 채팅 → 다른 공장(hu-a) 선택 → J 입력 저장 → 첫 보내기 | UI가 만든 미연결 진행 건이 새 대화에 1회 연결, 메시지 2개/응답 1개, 기존 us-a 대화·진행/작업 기록 불변 |
| 요청·응답·저장 대상 대조 | 기존 요청 chat_id와 반환 ID 일치; 새 첫 요청은 chat_id 없이 서버가 생성한 응답 ID를 URL/저장 메시지 ID/진행 건과 대조. 총 대화 정확히 2개, 미연결 진행 잔여0 |
| 새로고침·이동 | 두 대화의 저장 history와 복원 history 정확히 일치, 재요청0, 총 모델 호출3, API 오류0. 기존/새 제품 PNG도 직접 확인 |

**초기 준비 실패 보존:** (1) 현재 Native 요청의 `user_message`를 이전 `messages`로 기대한 오류, (2) 같은 공장/워크플로우 선택이 기존 활성 진행의 대화를 재개하는 의도된 동작을 새 진행으로 기대한 오류, (3) 새 첫 요청에 아직 없는 chat_id를 기대한 오류가 각각 중단됐다. 실제 요청/공식 서비스 계약을 확인하고 다른 공장 선택·응답 ID/저장 ID 상관 검사를 사용해 같은 버튼 경로를 재검했다. 독립 검토에서 두 번째 응답을 첫 응답 문구로 잘못 인정할 위험도 찾아 실제 렌더 응답 수와 과거 메시지 필드를 검사했다. 제품 결함은 발견되지 않았고 제품 코드 수정은 없다. 실패를 최종 PASS에 합산하지 않는다.

**명령·증거:** 기존 `.venv`/Chrome를 재사용한 아래 명령 exit0, 두 변경 Python의 compile(인코딩 경고 오류 처리)·문서 점검·`git diff --check`를 확인했다. 최종 JSON/PNG/로그는 `dist/c-phase3/composer-final/` 및 `composer-final.log`, 실패는 `composer-first/second/third`에 보존한다. 시험용 SSE는 stream 요청 분기에 한정하고 이전 non-stream 통합 검사를 새 실행으로 합산하지 않는다.

```bash
.venv/bin/python -X warn_default_encoding -W error::EncodingWarning tests/ees_work_c_phase1_app.py --composer-only --wheel dist/c-phase3/final-v3/open_webui-0.11.3+ees.12-py3-none-any.whl --chrome dist/tools/chrome-headless-shell-linux64/chrome-headless-shell --output dist/c-phase3/composer-final
```

**패키지·재사용:** 최종 `final-v3/manifest.json`의 wheel 151,959,136 bytes/SHA와 실제 파일이 일치한다. 고정 공식 wheel과 현재 builder 변환으로 전체 payload 5,916개 바이트, RECORD 5,917행·멤버 집합·중복 없음·CRC를 확인했다. 과거 `source-wheel-final.json`은 중간 산출물이며 최종 `source-wheel-final-v3.json`과 구분한다. a49350 이후 제품·backend·builder·Agent Pack 불변이므로 위의 3차 광역 및 #65/TR21·SA25 유효 증거를 재사용한다. 이번에 전체 suite나 Windows Restore를 다시 실행한 것으로 표시하지 않는다.

**문서 검사 한계와 조치:** 후속 증거 추가 시 scenarios.md가 1MiB 검사 한도를 넘어 최초 문서 검사가 실패했다. 검사 상한을 변경하지 않고 이 C안 3차 절만 날짜·과거 판정·초기 실패·본문 그대로 별도 평가 원본으로 옮겼다. 기존 두 anchor는 scenarios.md에 연결점으로 보존하고 관련 링크를 검사한다.

**Git·준비 종료 조건:** 로컬 HTTPS Git fetch는 자격증명이 없어 사용할 수 없었으나 인증된 GitHub 앱으로 조회·동일 PR 반영 경로를 사용한다. 초기 main은 unprotected/필수 status 없음, #66 clean·review/thread 없음이었다. rulesets 조회는 유료 기능 제한403으로 재호출하지 않았고 최종 원격 head/병합 가능 상태를 다시 확인한다. 09-30까지 각 커밋/병합 메시지 `[skip ci]`, 원격 dispatch/재실행 없음. 병합된 tree가 검증 제품과 같을 때만 wheel을 재사용하며 깨끗한 정확한 병합 checkout에서 기존 bundle builder로 새 ZIP의 `source_commit/source_dirty=false`·파일별 해시를 확인한다. 실제 merged 상태·병합 SHA·main과 최종 ZIP/hash는 [같은 PR #66의 병합/배포 준비 기록](https://github.com/knadalkim-a11y/team-agent-poc/pull/66)에 기록한다. 당시 준비 중 상태를 병합 완료로 추정하지 않는다.

**사내 경계:** [적용·복구 안내](../docs/03-openwebui-native-agent.md#c-design-trial-20260929)에 따라 현재 원본을 기존 Status 한 줄로 먼저 확인한다. #65→C안 Agent Pack 변경은 없고 기존 Upgrade의 자동 ApplyDemo는 지정 관리 필드 보호/불변 no-op·충돌 중단을 유지한다. 별도 초기화·재등록·사용자 전체 동기화는 하지 않는다. Stop 전 준비 검사, Stop/Backup/Apply/health, 프로그램 Restore와 DB/자산 복원을 구분한다. Windows·사내 기동/보내기/C안/업무 저장·이력, 실 API/모델·OP·실사용 수락은 결과 수신 전까지 미실행이다.
