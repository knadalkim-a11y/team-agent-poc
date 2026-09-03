# 03. Open WebUI ↔ Hermes 연동

> 상태: **다음 단계 / 미검증**  
> 선행 조건: 직접 경로의 기본 응답이 PASS이고, 모델 노출·대화 분리 최소 점검을 마쳐야 한다. 반복 안정성 검증은 Hermes 연결 후 두 경로에 함께 수행한다.

## 목표

```text
직접 기준선:   브라우저 → Open WebUI → 사내 vLLM
에이전트 경로: 브라우저 → Open WebUI → Hermes → 사내 vLLM
```

두 연결을 함께 유지해 문제가 Open WebUI, Hermes, 모델 중 어디에서 발생하는지 비교합니다.

## 진입 Gate — 10분 이내 최소 점검

Hermes 연결 전에 직접 경로의 모든 장기 시험을 끝낼 필요는 없습니다. 다음 세 가지만 확인합니다.

| 항목 | 통과 조건 |
|---|---|
| 모델 allowlist | GLM·Gemma 등 승인된 Chat 모델만 picker에 보이고 Embedding·Reranker는 숨겨짐 |
| 대화 문맥 | 같은 대화에서는 일회성 문자열을 기억함 |
| 새 대화 분리 | 새 대화에서는 그 문자열을 알 수 없다고 답함 |

20회 반복, 장시간 대화, 성능 비교는 Hermes 연결 후 직접 경로와 Hermes 경로에 같은 질문으로 실행합니다. 이 단계에서는 비교 기준을 흐리지 않도록 Open WebUI 자체 Tool·Memory·RAG는 활성화하지 않습니다.

## 현재 환경

| 항목 | 상태 |
|---|---|
| Hermes | 0.19.0 (v2026.7.20) |
| 설치 | uv tool / pip |
| Python | 3.12.10 |
| 현재 Profile | default |
| Gateway | stopped |
| Hermes API | 미검증 |

0.19.0은 필요한 OpenAI-compatible API를 제공하지만 현재 pip/uv 설치에는 API 서버용 aiohttp가 없을 수 있습니다. 이 버전은 동일 PC의 localhost smoke test까지만 사용하고, 팀 POC 전에 공식 Windows 설치본으로 전환한 뒤 재검증합니다.

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

이 경우 공식 Windows 설치본으로 전환한 뒤 전체 단계를 다시 검증합니다.

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
- [ ] 새 대화에서 이전 테스트 문자열을 자동 회수하지 않는다.
- [ ] Memory와 위험 Tool이 비활성화돼 있다.
- [ ] 20회 반복 요청에 오류가 없다.
- [ ] Hermes 중단 시 직접 vLLM 연결은 계속 동작한다.

하나라도 사용자 격리 또는 Tool 안전성에 실패하면 파일럿을 중단합니다.

## 공식 참고자료

- https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui
- https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.20
- https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/gateway/platforms/api_server.py
