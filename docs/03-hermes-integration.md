# 03. Open WebUI ↔ Hermes 연동

> 문서 역할: 선택적 Hermes 비교 절차
>
> 선행 조건: Open WebUI Native `EES 통합 Assistant` 평가에서 외부 Agent 엔진이 필요한 구체적 실패 사례가 확인되어야 한다.

Native MVP의 필수 절차가 아닙니다. 아래 내용은 추후 비교를 위해 보존합니다. 최신 착수·보류 상태는 [STATUS](STATUS.md), 환경은 [versions](../versions.md), 실제 시험 판정은 [평가표 G](../evals/scenarios.md)를 확인합니다.

## 목표

```text
직접 기준선:   브라우저 → Open WebUI → 사내 vLLM
에이전트 경로: 브라우저 → Open WebUI → Hermes → 사내 vLLM
```

두 연결을 함께 유지해 문제가 Open WebUI, Hermes, 모델 중 어디에서 발생하는지 비교합니다.

## Open WebUI 기능과 Hermes의 경계

Open WebUI의 UI·계정·대화 저장 기능은 Hermes 모델을 선택해도 그대로 사용합니다. 그러나 Open WebUI가 일반 모델에 제공하는 Builtin Tool은 Hermes v0.19.0에 자동 승계되지 않습니다.

| 기능 | Hermes 모델 선택 시 |
|---|---|
| 로그인·사용자 계정 | 유지 |
| 대화 목록·현재 대화 저장 | 유지 |
| 현재 대화의 전체 메시지 전달 | 유지 |
| `search_chats`·`view_chat` | 자동 승계되지 않음 |
| Open WebUI Memory·Notes·Knowledge Tool | 자동 승계되지 않음 |
| Hermes Skill·Memory·Tool | Hermes API 서버에서 실행 |

Open WebUI는 Builtin Tool 명세를 OpenAI 형식 `tools`로 upstream에 보낼 수 있지만, Hermes v0.19.0 API 서버는 이를 Hermes Tool로 등록하지 않습니다. Hermes 도구는 Profile의 `api_server` toolset에서 별도로 결정됩니다.

따라서 MVP 구성은 다음과 같습니다.

- 직접 GLM·Gemma: 필요한 Open WebUI Builtin Tools 사용
- Hermes Agent POC: Open WebUI `Builtin Tools OFF`, Hermes가 에이전트 실행 전담
- 두 경로를 함께 유지해 사용자 경험과 품질을 비교
- 단일 Agent에서 양쪽 기능이 모두 필요하다는 증거가 생긴 뒤에만 사용자 인식형 MCP/API 브리지를 검토

### 모델 선택기 운영 단계

POC에서는 실제 모델과 Hermes 경로를 모두 노출해 같은 질문을 비교합니다.

```text
POC 모델 선택기
├─ 사내 GLM (Direct)
├─ 사내 Gemma (Direct)
└─ EES Hermes Agent
```

파일럿에서는 비개발자가 구현 세부사항을 선택하지 않도록 Workspace Model preset으로 역할 중심 이름을 제공합니다.

```text
일반 사용자 모델 선택기
├─ EES 기본 Assistant
└─ EES Hermes Agent

개발자·관리자 선택기
├─ EES 기본 Assistant
├─ EES Hermes Agent
├─ 사내 GLM (Direct)
└─ 사내 Gemma (Direct)
```

`EES 기본 Assistant`는 별도 물리 모델이 아니라 승인된 Direct 모델 하나를 감싸는 Open WebUI preset입니다. `EES Hermes Agent`는 Hermes API가 광고하는 논리 모델이며, 실제 기반 모델은 Hermes Profile에서 설정합니다. POC 결과가 나오기 전에는 기본 모델 자동 라우팅이나 여러 preset을 추가하지 않습니다.

특히 Open WebUI의 Tool Approval은 Hermes 내부 Tool 실행을 승인·차단하지 못하므로 Hermes 자체 toolset과 승인 정책을 별도로 제한해야 합니다.

## 진입 Gate — 10분 이내 최소 점검

Hermes 연결 전에 직접 경로의 모든 장기 시험을 끝낼 필요는 없습니다. 다음 세 가지만 확인합니다.

| 항목 | 통과 조건 |
|---|---|
| 모델 allowlist | GLM·Gemma 등 승인된 Chat 모델만 picker에 보이고 Embedding·Reranker는 숨겨짐 |
| 대화 문맥 | 같은 대화에서는 일회성 문자열을 기억함 |
| 새 대화 분리 | Open WebUI Chat History·Memory 도구를 끈 새 대화에서는 그 문자열을 알 수 없다고 답함 |

20회 반복, 장시간 대화, 성능 비교는 Hermes 연결 후 직접 경로와 Hermes 경로에 같은 질문으로 실행합니다. 이 단계에서는 비교 기준을 흐리지 않도록 Direct 기준선용 Model preset의 Open WebUI Builtin Tools·Memory·RAG를 비활성화합니다. 같은 사용자의 Chat History 검색은 자동 문맥 주입이나 장기 Memory 실패로 판정하지 않습니다.

## 환경 및 호환성 확인

설치 버전·방식·Python·Profile은 [versions](../versions.md)에서 관리합니다. 이 문서의 명령 예시는 2026-09-03에 기록한 Hermes 0.19.0 환경을 기준으로 하며, 다른 버전에는 확인 없이 적용하지 않습니다.

0.19.0은 필요한 OpenAI-compatible API를 제공하지만 pip/uv 설치에는 API 서버용 aiohttp가 없을 수 있습니다. 이 예시는 동일 PC의 localhost smoke test까지만 대상으로 합니다. Hermes 비교를 실제로 선택하고 의존성·Windows 호환성 점검에서 변경 필요가 확인되면, 승인된 설치 방식·버전을 정한 뒤 재검증합니다. Native MVP 진행을 위해 Hermes를 미리 업그레이드하지 않습니다.

## 1. 별도 Profile 생성

정상 동작 중인 default를 직접 수정하지 않습니다.

```powershell
hermes profile list
hermes profile create team-poc --clone-from default
hermes profile show team-poc
```

복제된 Profile에는 .env와 사내 인증정보가 포함될 수 있으므로 Profile 디렉터리를 Git에 올리지 않습니다.

## 2. API 설정

기본 Profile을 바꾸지 않기 위해 모든 명령에 --profile team-poc를 지정합니다.

```powershell
hermes --profile team-poc config set API_SERVER_ENABLED true
hermes --profile team-poc config set API_SERVER_HOST 127.0.0.1
hermes --profile team-poc config set API_SERVER_PORT 8642

$secureKey = Read-Host "New Hermes API key (16+ chars)" -AsSecureString
$plainKey = [System.Net.NetworkCredential]::new("", $secureKey).Password
hermes --profile team-poc config set API_SERVER_KEY $plainKey
```

API_SERVER_KEY는 16자 이상의 별도 난수 값을 사용하고 Git·문서·캡처에 남기지 않습니다. API를 끌 때는 API_SERVER_ENABLED뿐 아니라 Key가 남아 있는지도 확인합니다.

## 3. 안전 Gate

Docker sandbox가 없는 Windows POC이므로 Gateway를 시작하기 전에 설치된 버전의 도움말·설정에서 다음 상태를 확인합니다. 버전별 설정 키를 추정해 넣지 않습니다.

| 기능 | POC 요구 상태 |
|---|---|
| 개인 Memory | OFF |
| Background memory review | OFF |
| Terminal·Shell | OFF |
| 파일 쓰기 | OFF |
| 브라우저·코드 실행 | OFF |
| Cron·Delegation | OFF |
| MCP | 없음 |

설정 이름과 비활성화 결과가 확인되기 전에는 다른 사용자에게 공개하지 않습니다.

## 4. Gateway 전경 실행

별도 PowerShell에서 실행합니다.

```powershell
hermes --profile team-poc gateway
```

POC에서는 Windows Service나 예약 작업으로 등록하지 않습니다. 다음 오류가 나오면 임의로 site-packages를 수정하지 않고 중단합니다.

```text
aiohttp not installed
```

이 경우 임의로 설치를 교체하지 않습니다. 위 호환성 확인 절차에 따라 변경 필요와 승인된 설치 방식을 정한 뒤 전체 단계를 다시 검증합니다.

## 5. API 점검

다른 PowerShell에서:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8642/health" -Method Get

$headers = @{ Authorization = "Bearer $plainKey" }
$models = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8642/v1/models" `
    -Method Get `
    -Headers $headers

$models.data
```

Chat Completions는 /v1/models가 반환한 실제 모델 ID로 점검합니다.

```powershell
$hermesModel = $models.data[0].id
$body = @{
    model = $hermesModel
    messages = @(
        @{ role = "user"; content = "HERMES_OK라고만 답하세요." }
    )
    stream = $false
} | ConvertTo-Json -Depth 6

$response = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8642/v1/chat/completions" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

$response.choices[0].message.content
$plainKey = $null
$secureKey = $null
```

listener가 loopback인지 확인합니다.

```powershell
Get-NetTCPConnection -LocalPort 8642 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

LocalAddress는 127.0.0.1이어야 합니다. 0.0.0.0 또는 외부 NIC 주소이면 Gateway를 중단합니다.

## 6. Open WebUI 연결

Admin Panel의 Connections에서 두 번째 OpenAI-compatible 연결을 추가합니다.

| 설정 | 값 |
|---|---|
| 이름 | Hermes Agent POC |
| Base URL | http://127.0.0.1:8642/v1 |
| API Key | team-poc의 API_SERVER_KEY |
| 모델 | /v1/models가 반환한 모델 |
| API 방식 | Chat Completions |

## 7. 통과 조건

- [ ] /health와 인증된 /v1/models가 정상 응답한다.
- [ ] 8642가 127.0.0.1에만 열린다.
- [ ] 직접 vLLM과 Hermes 모델을 각각 선택할 수 있다.
- [ ] Hermes가 사내 vLLM을 통해 답한다.
- [ ] Open WebUI Chat History·Memory 도구를 끈 새 대화에서 이전 테스트 문자열을 자동 회수하지 않는다.
- [ ] Memory와 위험 Tool이 비활성화돼 있다.
- [ ] 20회 반복 요청에 오류가 없다.
- [ ] Hermes 중단 시 직접 vLLM 연결은 계속 동작한다.

하나라도 사용자 격리 또는 Tool 안전성에 실패하면 파일럿을 중단합니다.

## 공식 참고자료

- https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui
- https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.20
- https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/gateway/platforms/api_server.py
