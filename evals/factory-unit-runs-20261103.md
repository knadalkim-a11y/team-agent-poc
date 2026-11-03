# 진행 건 공동화 1단계 검증

<a id="factory-unit-runs-20261103"></a>

## 범위와 기준

- 날짜: 2026-11-03. 기준 main `253cb3c6a16880aeb8be7113ecb7006a6f15585c`(#115 병합). 브랜치 `feat/factory-unit-runs-20261103`.
- [사용자 결정 원문·구현 단계·명세 밖 결정](../docs/mockups/ees-work/TASK.md#factory-unit-runs-20261102), [공용 도구 규칙](../docs/specs/shared-tools.md). 1단계는 진행 건 접근만 바꾸며 도구 인증과 근거 공개는 2단계다.
- 공장·시스템의 viewer 읽기, participant 처리. owner/sharing 기존 값 보존, 새 시작 공유 인자 무시. 같은 업무·실제 단위의 중복 검사, 장애대응/이전 periodic/emergency 예외, 예전 중복 목록 보존. 내 업무 담당 충돌 보호, 종료·취소 기존 거부 조건 유지.
- 저장 형식/이관 없음. 구프로그램은 owner/sharing 권한을 다시 적용하므로 새 공동 진행 정책을 지원하지 않는다. 사용자 대화·UI·개인 PAT 근거·예약 권한·옛 cases는 변경하지 않는다. frontend 패치 변경 없음.

## 환경과 명령

Linux 격리 작업 사본, Python 3.11.17 `.venv`, Node 22.22.0. Python 의존성은 `.github/workflows/ees-delivery.yml` 고정 목록을 설치했다. CI의 Node 22.16.0과 다르다. 실제 Native wheel·Chrome·Windows가 이 로컬에 없어 관련 시험은 CI에서 실행한다.

| 명령 | 결과 |
|---|---|
| `.venv/bin/python tests/ees_delivery_suite.py --suite services --output /tmp/unit-runs-services` | Python 505통과·실패0·3건너뜀. 포함된 Node 스크립트 전부 성공 |
| `node --test tests/*.cjs` | 672/672 통과 |
| `.venv/bin/python tests/ees_delivery_suite.py --suite contracts --output /tmp/unit-runs-contracts` | 58통과·실패0·52건너뜀(Native wheel 등 필요) |
| `.venv/bin/python tests/ees_delivery_suite.py --suite platform --output /tmp/unit-runs-platform` | 639통과·실패0·97건너뜀(Native/Windows/patched source 등 필요) |
| `.venv/bin/python -m unittest discover -s tests -p 'test_ees_work_workspace.py'` | 경계 검사 추가 후 81/81 통과 |
| `.venv/bin/python -m unittest discover -s tests -p 'test_ees_work_figma_contracts.py'` | 비공개 근거 보강 후 24/24 통과 |

`python scripts/check_docs.py`: 29파일·오류0·검토 후보0. `python tests/ees_delivery_suite.py --audit --output /tmp/unit-runs-audit`: 기존1332/현재1591·오류0. `git diff --check` 통과.

로컬 건너뜀은 성공으로 계산하지 않는다. 최종 커밋의 전체 필수 CI·Native 화면 검증 결과는 PR에서 기록한다. 사내 배포·실제 사용자 검수는 미실행이다.

## 확인한 동작과 기존 시험 수정

- A가 공장 A의 준비·배포 두 단계를 완료하면 B의 목록/내 업무/진행 상세가 같은 ID·2단계 완료를 보이고 B가 후속 단계를 완료·종료한다. viewer는 읽기만 가능하며 claim/확정/종료/취소는 거부된다.
- 공장 시작과 시스템 시작 경쟁은 하나만 성공한다. 명시적인 시스템 공통은 공장을 골라도 공장 ID 없이 중복 검사한다. 범위 미지정 기존 절차도 실제 시작 단위로 검사한다. 장애대응과 saved periodic/emergency는 시스템과 공장 모두 동시 진행을 유지한다.
- 예전 owner/sharing을 합성 DB에 남기고 재시작해도 같은 범위에서 접근된다. 예전 중복을 지우거나 합치지 않는다. Native 그룹 탈퇴 뒤에도 명시적 사용자 범위 권한은 유효하며 실제 범위 권한을 거두면 차단한다.
- 시작 화면의 이전 그룹 UI·payload·저장을 제거했다. 게시본의 수행 범위를 사용하며 작성 초안 범위에 영향을 받지 않는다. 평상/장애 진행 선택, 공장 분리, 시스템 공통, 여러 건 선택, 자동 실행 없음, 입력 보존을 Node로 검사한다.
- 기존 시험 ID를 삭제·건너뛰거나 교체하지 않았다. 개인 진행 건 격리 시험의 기대를 공동 진행+개인 대화/UI 비공개로 바꿨다. export도 같은 범위에서 허용하지만 대화 링크·개인 초안을 포함하지 않는다. Native await 후 권한 재판정은 관리자 fixture를 일반 사용자/범위 그룹으로 바꾸어 실제 철회를 확인한다.
- 개인 PAT 근거의 결과·검토 초안은 B의 그룹 소속과 무관하게 비공개다. 공용 도구 Native 시험도 관리자가 시작한 진행 건을 참여자가 보되 도구 그룹 밖에서는 실행하지 못하는지 확인하도록 보강한다.
- Native 도구의 두 활성 버전 비교는 서로 다른 실제 단위를 사용한다. 본문 크기·제외 작업 재시작 시험은 앞 진행 건을 정상 종료/취소한 뒤 새로 시작한다. 시험 목적·기존 단언을 유지하며 새 중복 제한을 우회하는 제품 코드는 넣지 않았다.
- 최초 로컬 회귀에서 workspace 기존 개인 접근 기대 3건, 시작 UI 그룹/중복 안내 기대 3건이 실패했다. 사용자 결정에 맞춰 기존 시험을 고쳤으며 제품 오류를 숨기기 위해 시험을 삭제/생략하지 않았다.

## Figma

- `figma-use`와 `figma-generate-design` 절차로 기존 파일/운영 화면/공통 부품을 조회했다. 연결 라이브러리에 EES 대체 부품이 없어 파일 안의 Button v4, Noto Sans KR와 EES 변수·기존 개요 행을 재사용했다. Code Connect 파일 없음.
- 운영 헤더 `1284:3107`: 33→34판. 기존 화면은 유지하고 공동 진행 상태 `1991:270`, 시작 창 `1991:275`, 2단계 완료 개요 `1991:287`를 추가했다. 이전 그룹 선택 화면은 이 페이지에 존재하지 않아 그룹 없는 실제 시작 창을 명시적으로 그렸다. 별도 HTML은 만들지 않았다.
- 변경 전 운영 페이지를 B068(`1989:270`)로 백업했다. #115 병합 후 그 PR 백업 B067(`1970:3017`)만 정리했다. 다른 백업은 손대지 않았다. 변경 기록 C134(`1993:274`)는 PR 생성 후 번호를 연결한다.
- 편집 가능한 자식57개(TEXT20/FRAME27/INSTANCE3/RECTANGLE4/VECTOR3), 전체 UI 이미지0, 글꼴 Noto Sans KR 확인. 시작 창 첫 캡처 후 제품 CSS의 700px 폭·24px 여백·10px 모서리·12px 안내 글로 맞춰 재캡처했고 잘림/겹침 없음. 기존 개요 부품의 배치·완료 표시를 유지한다. 제품의 실제 Native 캡처는 최종 CI로 별도 판정한다. Native 시험에 다른 사용자가 준비·배포를 완료한 공장 A 진행 건을 업무 메뉴에서 열어 같은 ID와 완료 2단계를 확인하고 후속 점검을 직접 확정하는 흐름을 추가했다.
- `scripts/figma_check.js` 원문을 Figma에서 실행: 오류0. 기존 작성 페이지의 크기 경고는 이번 범위 밖이며 유지한다. 새 B068 기록 없음 경고는 점검 후 C134 한 줄 기록으로 연결했다. PR 생성 전 임시 `PR 없음` 표기를 실제 PR 번호로 바꾼다.

## 다음 단계와 미확인

1단계 최종 PR CI·검토 후 병합 가능한 상태로 전달한다. 2단계 공용 토큰/공유 근거는 1단계 병합 뒤 최신 main에서 시작한다. 실제 시스템 토큰 발급·권한 범위, 사내 암호화 설정과 서비스 호출은 미확인이다.
