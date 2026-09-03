# 02. Open WebUI → 사내 vLLM 직접 연결

> 상태: **대기 / 미검증**  
> 선행 조건: Open WebUI 기동 Gate가 PASS여야 한다.

## 목적

Hermes를 거치기 전에 Open WebUI와 사내 vLLM 사이의 기준선을 만듭니다.

```text
브라우저 → Open WebUI (127.0.0.1:8080) → <INTERNAL_VLLM_BASE_URL>
```

이 단계에서는 Hermes, MCP, RAG, 파일 첨부, Shell·Python Tool을 사용하지 않습니다. Hermes gateway가 중지된 상태에서도 응답해야 직접 경로가 검증된 것입니다.

## 현재 관찰된 기본 OpenAI 연결 오류

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

실제 값은 이 저장소에 기록하지 않습니다. 사내 호스트는 프록시를 우회하도록 Open WebUI 시작 전에 설정합니다.

```powershell
$env:CORP_NO_PROXY = "127.0.0.1,localhost,<INTERNAL_VLLM_HOST>"
```

환경변수를 바꿨다면 Open WebUI를 재시작합니다.

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

## 3. Open WebUI 연결 추가

Open WebUI 버전에 따라 메뉴 이름이 조금 다를 수 있습니다.

1. 관리자 계정으로 로그인합니다.
2. 프로필 메뉴 → Admin Panel → Settings → Connections로 이동합니다.
3. Manage OpenAI API Connections에서 `https://api.openai.com/v1` 기본 연결을 삭제하지 않고 토글로 비활성화합니다.
4. `+` Add Connection을 눌러 Provider는 OpenAI, Standard / Compatible을 선택합니다.
5. API Type은 **Chat Completions**를 선택하고 Responses는 활성화하지 않습니다.
6. URL에 <INTERNAL_VLLM_BASE_URL>을 입력합니다.
7. API Key는 UI에 직접 입력합니다. 인증이 없는 endpoint만 담당자 안내에 따라 `none` 또는 빈 값을 사용합니다.
8. Model IDs (Filter)에 허용할 <INTERNAL_MODEL_ID>만 추가합니다. `/models` 자동 조회가 정상이고 전체 노출이 허용될 때만 비워 둡니다.
9. Verify Connection과 Save 후 새 대화에서 해당 모델을 선택합니다.

주의:

- /v1을 중복 입력해 /v1/v1이 되지 않게 합니다.
- 연결 정보가 저장되는 data 디렉터리와 webui.db는 Git에 올리지 않습니다.
- 화면이나 로그 공유 시 URL과 Key를 가립니다.

## 4. 최소 테스트

| ID | 테스트 | 통과 조건 | 상태 |
|---|---|---|---|
| D01 | 모델 목록 | 허용된 사내 모델을 선택할 수 있다 | 대기 |
| D02 | 단일 응답 | 오류 없이 답변이 생성된다 | 대기 |
| D03 | 스트리밍 | 응답이 중단 없이 순차 표시된다 | 대기 |
| D04 | 같은 대화 맥락 | 두 번째 질문이 첫 문자열을 기억한다 | 대기 |
| D05 | 새 대화 분리 | 새 대화가 이전 문자열을 자동 회수하지 않는다 | 대기 |
| D06 | 재시작 | 재시작 후 연결과 허용된 대화가 유지된다 | 대기 |
| D07 | 반복 호출 | 비식별 질문 20회에 요청 실패가 없다 | 대기 |

맥락 테스트에는 업무정보 대신 일회성 문자열을 사용합니다.

```text
1차: 이 대화에서만 테스트 문자열은 OWUI-DIRECT-7319야.
2차: 방금 테스트 문자열이 뭐였지?
새 대화: 내가 이전 대화에서 말한 문자열이 뭐였지?
```

## 통과 판정

단일 응답·스트리밍·대화 분리·재시작·20회 호출을 모두 확인하고, Hermes가 중지된 상태에서도 동작해야 다음 단계로 넘어갑니다.
