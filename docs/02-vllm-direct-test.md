# 02. Open WebUI → 사내 vLLM 직접 연결

> 문서 역할: 사내 모델 직접 연결·기준선 시험 절차
>
> 선행 조건: Open WebUI 기동 Gate가 PASS여야 한다.

최신 적용 상태는 [STATUS](STATUS.md), 시험 ID·판정·근거는 [평가표 B](../evals/scenarios.md)에서 관리합니다.

## 목적

Hermes를 거치기 전에 Open WebUI와 사내 vLLM 사이의 기준선을 만듭니다.

```text
브라우저 → Open WebUI (127.0.0.1:8080) → <INTERNAL_VLLM_BASE_URL>
```

이 단계에서는 Hermes, MCP, RAG, 파일 첨부, Shell·Python Tool을 사용하지 않습니다. Hermes gateway가 중지된 상태에서도 응답해야 직접 경로가 검증된 것입니다.

## 초기 기본 OpenAI 연결 오류 (2026-09-03 관찰)

초기 UI에서 다음 오류가 보일 수 있습니다.

```text
403
Attempt to decode JSON with unexpected mimetype: text/html
https://api.openai.com/v1/models
```

이는 Open WebUI가 기본 OpenAI 연결의 모델 목록을 조회했지만 사내 보안망이 JSON 대신 차단 안내 HTML을 반환했다는 뜻입니다. UI와 `/health`가 정상이라면 Open WebUI 기동 오류가 아닙니다. 외부 OpenAI 연결은 토글로 비활성화하고 사내 vLLM 연결만 활성화합니다.

## 1. 준비

승인된 경로에서 다음 값을 확보합니다.

- <INTERNAL_VLLM_BASE_URL>: 일반적으로 /v1까지 포함한 OpenAI-compatible URL
- <INTERNAL_MODEL_ID>
- API Key 또는 사내 인증 방식

실제 값은 이 저장소에 기록하지 않습니다. 사내 호스트가 직접 연결 대상인지 프록시 경유 대상인지는 환경마다 다르므로 먼저 경로를 비교합니다. 내부 주소라는 이유만으로 `NO_PROXY`에 넣지 않습니다.

```powershell
$targetUrl = "https://<INTERNAL_VLLM_HOST>/v1/models"
$proxyUrl = "http://<CORPORATE_PROXY_HOST>:<PORT>"

curl.exe -sS -o NUL -w "DIRECT http=%{http_code}\n" --connect-timeout 10 --noproxy "*" $targetUrl
curl.exe -sS -o NUL -w "PROXY  http=%{http_code}\n" --connect-timeout 10 --proxy $proxyUrl $targetUrl
```

API Key 없이 실행하므로 `401` 또는 `403`도 TCP·TLS·HTTP 경로 자체가 연결됐다는 증거가 될 수 있지만, Key+IP 허용 경로 판정에는 사용할 수 없습니다. `000` 또는 connect error는 해당 경로가 실패한 것입니다. 프록시 출력에 HTTP 상태가 두 줄이면 첫 `200 Connection established`가 아니라 마지막 API 응답을 판정합니다.

- 인증을 포함한 실제 API 요청이 직접 경로에서 검증됨: <INTERNAL_VLLM_HOST>를 `CORP_NO_PROXY`에 추가합니다.
- 인증을 포함한 실제 API 요청이 프록시 경로에서 검증됨: <INTERNAL_VLLM_HOST>를 `CORP_NO_PROXY`에 추가하지 않습니다.
- 둘 다 실패: DNS·방화벽·사내 CA 문제를 먼저 해결합니다.

기본값은 loopback만 우회합니다.

```powershell
$env:CORP_NO_PROXY = "127.0.0.1,localhost,::1"
```

환경변수를 바꿨다면 Open WebUI를 재시작합니다.

## 과거 네트워크 경로 관찰 — 2026-09-03

2026-09-03 최초 비인증 비교에서 직접 경로는 403 HTML, 프록시 경로에서는 200이 관찰됐습니다. 그러나 Gateway가 Key와 발신 IP를 함께 검증하므로 비인증 결과만으로 정상 경로를 확정할 수 없습니다. 또한 HTTP 프록시의 `200 Connection established`는 TLS 터널 생성 성공일 뿐 최종 `/v1/models` 응답 200이 아닐 수 있습니다.

따라서 **유효한 Key를 헤더로 넣고 최종 HTTP 응답과 Content-Type까지 직접·프록시 양쪽에서 재검증한 뒤** NO_PROXY를 결정합니다. 실제 호스트·프록시 주소·Key는 저장하지 않습니다.

### 인증 포함 경로 재검증 결과

| 경로 | 최종 응답 | 판정 |
|---|---|---|
| Direct | HTTP 403, `text/html` | 정상 모델 API JSON에 도달하지 못함 |
| Explicit proxy | HTTP 000, Content-Type 없음 | 최종 HTTP 응답 전 연결 실패 |

유효 Key를 포함해도 정상 JSON이 없었으므로 아직 NO_PROXY 경로를 확정하지 않습니다. Proxy 쪽 curl 종료 코드와 오류 메시지로 CONNECT·timeout·TLS 인증서 실패를 구분하고, 기존에 성공한 클라이언트의 인증 헤더 이름과 네트워크 경로를 비교합니다.

## 2. 선택적 API 직접 점검

```powershell
$baseUrl = "<INTERNAL_VLLM_BASE_URL>".TrimEnd("/")
$secureKey = Read-Host "Internal LLM API key" -AsSecureString
$plainKey = [System.Net.NetworkCredential]::new("", $secureKey).Password
$headers = @{ Authorization = "Bearer $plainKey" }

Invoke-RestMethod -Uri "$baseUrl/models" -Method Get -Headers $headers
```

Chat Completions:

```powershell
$body = @{
    model = "<INTERNAL_MODEL_ID>"
    messages = @(
        @{ role = "user"; content = "DIRECT_OK라고만 답하세요." }
    )
    stream = $false
    max_tokens = 32
} | ConvertTo-Json -Depth 6

$response = Invoke-RestMethod `
    -Uri "$baseUrl/chat/completions" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

$response.choices[0].message.content
$plainKey = $null
$secureKey = $null
```

인증이 없는 사내 엔드포인트라면 담당자가 안내한 방식을 따릅니다. 현재 기준선은 Chat Completions이며, 별도로 검증하기 전에는 Responses API를 활성화하지 않습니다.

### Explicit proxy timeout과 `/models` 제한 후보

2026-09-03 인증 포함 재검증 후 explicit proxy 경로는 curl exit 28 timeout이었고, 같은 PC의 기존 Agent는 정상 동작했습니다. 당시에는 고정 프록시 대신 direct 경로에서 실제 Chat Completions를 검증하기로 했습니다. 이 과거 관찰을 새 환경의 프록시 금지나 직접 경로 성공 근거로 재사용하지 않습니다.

사내 Gateway가 `/v1/models`를 차단하면서 `/v1/chat/completions`만 허용할 수 있습니다. 이 경우 Open WebUI의 Verify Connection은 실패해도 연결의 Model IDs (Filter)에 정확한 ID를 `+`로 추가하면 자동 모델 조회를 생략하고 picker에 표시할 수 있습니다. Verify 결과가 아니라 실제 Chat Completions 성공으로 연결을 판정합니다.

## 3. Open WebUI 연결 추가

Open WebUI 버전에 따라 메뉴 이름이 조금 다를 수 있습니다.

1. 관리자 계정으로 로그인합니다.
2. 프로필 메뉴 → Admin Panel → Settings → Connections로 이동합니다.
3. 상단 `OpenAI API` 전체 스위치는 **ON**으로 유지합니다. 사내 vLLM도 이 OpenAI-compatible 어댑터를 사용합니다.
4. Manage OpenAI API Connections에서 `https://api.openai.com/v1` 행의 개별 토글만 **OFF**로 바꿉니다.
5. 같은 섹션의 `+` Add Connection으로 사내 vLLM 연결을 추가합니다.
6. Provider는 `Default`, API Type은 **Chat Completions**를 선택하고 Responses는 활성화하지 않습니다.
7. URL에 <INTERNAL_VLLM_BASE_URL>을 입력합니다. 끝은 일반적으로 `/v1`이며 `/models`나 `/chat/completions`는 붙이지 않습니다.
8. 사내 Gateway가 Key를 요구하면 Auth는 Bearer로 두고 API Key를 UI에 직접 입력합니다. 인증이 없으면 담당자 안내에 따라 Auth를 None으로 둡니다.
9. Model IDs (Filter)에 허용할 <INTERNAL_MODEL_ID>만 추가합니다. `/models` 자동 조회가 정상이고 전체 노출이 허용될 때만 비워 둡니다.
10. Model ID가 입력란에만 남아 있지 않고 `+`로 목록 항목에 추가됐는지 확인한 뒤 Save합니다.
11. Verify Connection은 `/models` 정책 때문에 실패할 수 있으므로, 수동 Model ID가 picker에 표시되고 실제 Chat Completions가 성공하는지로 판정합니다.
12. 사용자별 외부 연결을 받지 않는 중앙관리형 POC이므로 Direct Connections는 OFF로 유지합니다.

### 모델 선택기 노출 제한

사내 `/models`가 Chat·Embedding·Reranker 모델을 한 목록으로 반환하면 Open WebUI 모델 선택기에 모두 나타날 수 있습니다. 사용자가 대화에 쓸 수 있는 모델과 백엔드용 모델을 구분하기 위해 연결 단위 allowlist를 사용합니다.

```text
사내 /models 전체 목록
        ↓
Model IDs (Filter): 승인된 Chat 모델만
        ↓
사용자 모델 선택기: 승인된 Chat 모델만 표시
```

- `Admin Panel → Settings → Connections → 사내 vLLM 연결 편집`
- `Model IDs (Filter)`에 승인된 Chat 모델 ID만 정확히 추가합니다.
- 각 ID는 입력만 하지 말고 `+`를 눌러 목록 항목으로 만든 뒤 저장합니다.
- Embedding·Reranker 모델 ID는 추가하지 않습니다.
- 저장 후 브라우저를 새로고침하고 일반 사용자 모델 선택기에서도 확인합니다.
- 모델별 사용자·그룹 권한은 이 연결 allowlist 다음 단계의 별도 통제입니다.

### “오늘 날짜” 응답의 해석

Open WebUI는 현재 날짜·시간·요일 정보를 시스템 컨텍스트에 넣을 수 있습니다. 따라서 모델이 오늘 날짜를 맞혀도 Tool이나 Function을 호출했다는 증거는 아닙니다. Tool 호출 검증은 호출 표시나 서버 로그에서 실제 tool call과 결과가 있었는지 별도로 확인해야 합니다.

### 새 대화 분리와 과거 대화 검색의 차이

Native Function Calling에서 Builtin Tools가 활성화돼 있으면 `Chat History` 범주의 `search_chats`와 `view_chat`을 모델이 호출할 수 있습니다. 따라서 새 대화에서 “아까 내가 무엇을 물었나?”처럼 과거 대화를 명시적으로 요구하면 같은 사용자의 저장된 채팅을 검색해 답하는 것이 정상입니다.

이것은 이전 메시지가 새 대화에 자동으로 주입된 것이 아니며 Open WebUI Memory나 Hermes Memory와도 구분합니다. 순수한 새 대화 문맥 분리는 **관리자 패널 → 설정 → 모델 → 이번에 시험하는 기반 GLM 편집**에서 `Capabilities → Memory`와 `Builtin Tools → Memory·Chat History`가 각각 OFF인 상태로 검사합니다. EES 통합 Assistant에서 확인한 설정이 기반 모델에도 적용됐다고 가정하지 않습니다. [Memory 제어 범위](troubleshooting.md#native-memory-controls)에 따라 모델 설정을 확인하고, 필요한 항목만 해제해 저장한 뒤 화면을 새로고침합니다. 메뉴가 보이지 않으면 확인 목적으로 기능을 켜거나 새 모델을 만들지 말고 해당 상태를 보고합니다. 사용자 격리는 별도 계정 B가 계정 A의 문자열을 검색할 수 없는지로 검사합니다. 기반 모델은 관리자 모델 목록에서 공통 편집기로 열립니다. [v0.11.3 관리자 모델 UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/admin/Settings/Models.svelte)

Open WebUI v0.11.3의 내장 구현은 `search_chats`와 `view_chat` 조회에 현재 사용자의 ID를 사용하지만, 서버 파일럿 전에는 두 계정으로 실제 검증합니다.

주의:

- /v1을 중복 입력해 /v1/v1이 되지 않게 합니다.
- 연결 정보가 저장되는 data 디렉터리와 webui.db는 Git에 올리지 않습니다.
- 화면이나 로그 공유 시 URL과 Key를 가립니다.

## 4. 최소 테스트

D01~D07의 시험 정의와 판정은 [평가표 B](../evals/scenarios.md)를 사용하며 이 문서에는 상태표를 중복 작성하지 않습니다. D06은 반복 안정성, D07은 재시작 시험입니다.

2026-09-03 사용자 보고로 승인된 Chat 모델 2종의 기본 응답을 확인했습니다. 실제 모델 ID·URL·Key는 기록하지 않습니다.

맥락 테스트에는 업무정보 대신 일회성 문자열을 사용합니다.

```text
1차: 이 대화에서만 테스트 문자열은 OWUI-DIRECT-7319야.
2차: 방금 테스트 문자열이 뭐였지?
새 대화(먼저 모델 Memory 기능과 Chat History·Memory 도구 OFF): 내가 이전 대화에서 말한 문자열이 뭐였지?
```

완료한 같은 대화 시험(D04)은 반복하지 않습니다. 설정을 확인한 뒤 같은 기반 모델로 새 대화를 만들고 위 마지막 질문만 입력하며 시험 문자열·이전 답변을 붙이지 않습니다. 문자열을 알 수 없다는 답변인지와 과거 대화·Memory 조회 호출이 없는지 확인합니다. 기존 대화나 Saved Memories를 삭제하지 않습니다. Chat History 도구가 켜진 상태에서 같은 질문으로 과거 대화를 찾는 것은 별도의 정상 기능이며 D05 실패로 판정하지 않습니다.

## 통과 판정

직접 경로 전체를 PASS로 판정하려면 단일 응답·스트리밍·대화 분리·재시작·20회 호출을 모두 확인하고, Hermes가 중지된 상태에서도 동작해야 합니다. 일부 기본 응답 성공만으로 팀 파일럿의 안정성·격리 검증이 끝났다고 보지 않습니다. 로컬 기능 준비는 [Native Assistant 절차](03-openwebui-native-agent.md)로 이어가되, 공개·배포 전에는 [평가표](../evals/scenarios.md)의 해당 Gate를 별도로 충족합니다.
