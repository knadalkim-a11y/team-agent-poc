# Troubleshooting

Windows 로컬 POC의 장애를 계층별로 분리합니다. 앞 단계가 실패하면 뒤 단계를 수정하지 않습니다.

```text
① 사내 vLLM API 직접 호출
        ↓
② Open WebUI → 사내 vLLM
        ↓
③ Hermes API → 사내 vLLM
        ↓
④ Open WebUI → Hermes → 사내 vLLM
```

## 안전한 진단 정보

```powershell
Get-Date
uv --version
hermes --version
hermes profile list
hermes gateway status

Get-NetTCPConnection -LocalPort 8080,8642 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

공유 전 API Key, 실제 사내 URL·IP·모델 경로, 사용자명·개인 경로, 업무 질문과 응답을 제거합니다.

## 프록시 다운로드 실패

```powershell
$proxyUrl = "http://<CORPORATE_PROXY_HOST>:<PORT>"
$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl
$env:NO_PROXY = "127.0.0.1,localhost,::1"
$env:UV_SYSTEM_CERTS = "true"

curl.exe -I --proxy $proxyUrl https://github.com
curl.exe -I --proxy $proxyUrl https://pypi.org/simple/open-webui/
curl.exe -I --proxy $proxyUrl https://huggingface.co
```

| 결과 | 의미 | 조치 |
|---|---|---|
| 200·301·302 | 경로 정상 | 같은 PowerShell에서 재시도 |
| 407 | 프록시 인증 필요 | 사내 인증·미러 방식 확인 |
| 403 | 정책 차단 가능성 | allowlist 또는 패키지 미러 요청 |
| 인증서 오류 | 사내 CA 문제 가능성 | 승인된 CA 신뢰 설정 |
| timeout | 망 경로 문제 | 프록시 주소·네트워크 확인 |

--insecure, verify=false 등 TLS 검증 해제는 사용하지 않습니다.

## Open WebUI 시작 실패

### WEBUI_SECRET_KEY 로그 뒤 잠시 출력이 없음

Open WebUI 0.11.3은 키 파일을 읽은 직후 `open_webui.main`을 import하고 서버 초기화를 계속합니다. 따라서 다음 문구가 마지막으로 보이더라도 키 파일에서 멈췄다고 단정하지 않습니다.

```text
Loading WEBUI_SECRET_KEY from <WORK_DIR>\.webui_secret_key
```

키 파일이 생성돼 있고 이후 출력이 다시 진행된다면 정상적인 최초 기동 과정입니다. 키 파일을 삭제하거나 다시 만들지 말고 다음 완료 문구를 기다립니다.

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8080
```

별도 PowerShell에서 종료 없이 상태를 확인할 수 있습니다.

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.ProcessName -match "python|uv" } |
    Select-Object Id, ProcessName, CPU, StartTime, WorkingSet64
```

8080 listener가 생기면 브라우저에서 http://127.0.0.1:8080 을 확인합니다. 출력이 계속 진행 중이면 프로세스를 중단하지 않습니다.

공식 v0.11.3 CLI 소스:
https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/__init__.py


### CORS 경고 뒤 30분 이상 정체되고 8080 listener가 없음

관찰된 증상:

```text
WARNING: CORS_ALLOW_ORIGIN IS SET TO '*' ...
8080 listener 없음
/health = HTTP 000
uv·uvx·python 프로세스는 존재
```

CORS 문구는 단순 경고입니다. v0.11.3에서는 이 시점 전후로 `open_webui.main`과 여러 router·vector DB 모듈을 동기적으로 import합니다. 30분 동안 listener가 없다면 정상적인 최초 기동 대기로 보지 않습니다.

다른 Python 프로세스를 일괄 종료하지 말고 원래 Open WebUI PowerShell에서만 `Ctrl+C`를 누릅니다. 같은 창에서 진단 변수를 설정하고 다시 실행합니다.

```powershell
$env:GLOBAL_LOG_LEVEL = "DEBUG"
$env:ENABLE_VERSION_UPDATE_CHECK = "False"
$env:CORS_ALLOW_ORIGIN = "http://127.0.0.1:8080"
$env:PYTHONPROFILEIMPORTTIME = "1"

uvx --python 3.11 open-webui@0.11.3 serve --host 127.0.0.1 --port 8080
```

- CORS_ALLOW_ORIGIN 설정은 경고를 제거할 뿐 정체 원인을 해결하는 값은 아닙니다.
- `Ctrl+C` 후 traceback 없이 프롬프트로 돌아오는 경우도 있습니다. uvx가 자식 Python을 종료하면서 traceback을 전달하지 않은 경우입니다.
- 진단 출력을 로컬 임시 로그에 함께 저장하려면 다음처럼 실행합니다.

```powershell
$debugLog = Join-Path $env:TEMP "openwebui-import.log"
uvx --python 3.11 open-webui@0.11.3 serve --host 127.0.0.1 --port 8080 2>&1 |
    Tee-Object -FilePath $debugLog
```

다시 정체되면 `Ctrl+C` 후 다음 명령으로 마지막 import 구간을 확인합니다.

```powershell
Get-Content $debugLog -Tail 40
```

- `DEBUG | aiosqlite.core ... fetchall ... completed`는 기본 메타데이터 DB인 `DATA_DIR/webui.db`에서 비동기 조회가 끝났다는 뜻입니다. 이것만으로 전체 DB 초기화가 진행 중이라고 단정하지 않습니다.
- Open WebUI는 계정·대화·설정을 저장하는 `webui.db`와 RAG용 Chroma 데이터인 `DATA_DIR/vector_db`를 별도로 사용합니다.
- 서로 다른 SQL 작업과 시각이 계속 출력되면 프로세스 활동은 있지만, 비어 있는 신규 DB에서 수십 분이 걸리는 것은 정상 성능으로 보지 않습니다.
- `/health`가 200이면 백엔드는 준비된 것입니다. DEBUG 로그가 계속 출력돼도 전경 서버의 정상 동작입니다.
- 계속 000이면 마지막 로그와 DB 파일 변화, Open WebUI 프로세스 중복 여부를 확인합니다.
- 마지막으로 출력되는 import 구간과 오류를 비식별화해 확인합니다.
- 진단 후에는 `Remove-Item Env:PYTHONPROFILEIMPORTTIME -ErrorAction SilentlyContinue`로 import timing을 해제합니다.
- ChromaDB·native ML library import에서 멈춘다면 Windows 백신·디스크 검사 영향 여부를 별도로 확인합니다.
- 배너와 `Waiting for application startup` 이후에 멈춘 경우에만 임베딩 다운로드 경로를 우선 확인합니다.

공식 v0.11.3 소스:

- https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/main.py
- https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/retrieval/vector/factory.py

### UI가 열린 뒤 Hugging Face SSL 재시도

관찰된 경고:

```text
huggingface_hub.utils._http:_http_backoff_base
[SSL: CERTIFICATE_VERIFY_FAILED]
```

`/health`가 200이고 UI 로그인까지 가능하다면 Open WebUI의 핵심 기동과 운영 DB는 정상입니다. 이 경고는 Hugging Face의 임베딩·리랭커·Whisper 같은 외부 자산 조회 또는 다운로드에서 Python 런타임이 사내 TLS 검사 프록시의 인증서 체인을 신뢰하지 못해 발생할 수 있습니다.

```text
Open WebUI·계정·사내 LLM 채팅  → 계속 검증 가능
로컬 임베딩·파일 RAG·Whisper   → 인증서 해결 전 보류
```

정확한 대상을 확인할 때는 별도 PowerShell에서 공개 URL이 포함된 앞뒤 로그만 확인합니다.

```powershell
Select-String -Path "$env:TEMP\openwebui-import.log" `
    -Pattern "huggingface|Retrying|CERTIFICATE_VERIFY_FAILED" -Context 1,1 |
    Select-Object -Last 20
```

장기 해결은 IT가 승인한 **공인 루트와 사내 Root·Intermediate CA가 함께 포함된 PEM CA bundle**을 받아 Open WebUI 시작 전에 지정하는 것입니다. CA bundle이나 사내 경로는 Git에 커밋하지 않습니다.

```powershell
$caBundle = "C:\approved-path\corp-ca-bundle.pem"
$env:SSL_CERT_FILE = $caBundle
$env:REQUESTS_CA_BUNDLE = $caBundle
```

- `SSL_CERT_FILE`은 현재 Hugging Face Hub가 사용하는 HTTPX 계열 TLS 검증에 적용됩니다.
- `UV_SYSTEM_CERTS=true`는 uv의 패키지 다운로드 인증서 설정이며, 실행된 Open WebUI의 HTTPX TLS 신뢰를 자동으로 해결한다고 간주하지 않습니다.
- `verify=false`, 빈 `CURL_CA_BUNDLE`, SSL 검증 비활성화는 사용하지 않습니다.
- fresh install에서 임베딩 캐시가 없으면 `OFFLINE_MODE=true`와 `HF_HUB_OFFLINE=1`이 `No embedding model is loaded`를 유발할 수 있으므로, 경고를 숨기기 위한 즉시 조치로 사용하지 않습니다.
- 먼저 사내 vLLM 채팅 기준선을 검증하고, 이후 승인된 CA bundle·사전 반입된 임베딩 모델·사내 임베딩 API 중 운영 방식을 선택합니다.

공식 참고:

- https://docs.openwebui.com/reference/env-configuration/
- https://docs.openwebui.com/tutorials/maintenance/offline-mode/
- https://www.python-httpx.org/environment_variables/
- https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables

### No embedding model is loaded

fresh install에서는 기본 임베딩 모델 다운로드가 필요할 수 있습니다. 캐시가 없는데 OFFLINE_MODE 또는 HF_HUB_OFFLINE을 설정하면 시작이 실패할 수 있습니다.

1. 접근 가능한 세션에서 최초 다운로드를 완료합니다.
2. 정책상 차단이면 승인된 캐시를 사전 반입합니다.
3. 또는 사내 OpenAI-compatible embeddings endpoint를 사용합니다.

### 페이지가 열리지 않음

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
```

출력이 없으면 아직 다운로드 중이거나 시작 전에 실패한 것입니다. 0.0.0.0:8080으로 열렸다면 중단하고 --host 127.0.0.1로 다시 시작합니다.

### Address already in use

```powershell
$conn = Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-Process -Id $conn.OwningProcess
```

프로세스를 확인한 뒤 종료 여부를 결정하며, 확인 없이 강제 종료하지 않습니다.

### 재시작 후 계정·대화가 사라짐

- 매번 같은 DATA_DIR과 작업 디렉터리를 사용했는지 확인합니다.
- .webui_secret_key가 유지되는지 확인합니다.
- 실행 중인 DB를 복사하지 않습니다. 백업 전에 Open WebUI를 종료합니다.

## 사내 vLLM 직접 연결 실패

### `Cannot connect to host <INTERNAL_VLLM_HOST>:443 ssl:default`

키·URL·모델 ID 검증 전에 발생하는 전송 계층 오류입니다. Open WebUI 0.11.3의 OpenAI-compatible 요청은 `aiohttp.ClientSession(trust_env=True)`를 사용하므로 실행 프로세스의 `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`를 따릅니다.

1. API Key 없이 direct와 proxy의 `/v1/models` HTTP 도달 여부를 비교합니다.
2. direct만 성공하면 호스트를 NO_PROXY에 추가합니다.
3. proxy만 성공하면 호스트를 NO_PROXY에서 제거합니다.
4. HTTP 경로는 도달하지만 인증서 오류가 이어지면 승인된 PEM CA bundle을 `AIOHTTP_CLIENT_SSL_CERT_FILE`에 지정합니다.
5. SSL 검증을 끄지 않습니다.



| 상태 | 우선 확인 |
|---|---|
| 401·403 | API Key, Bearer 인증, 권한 |
| 404 | base URL의 /v1 중복 또는 누락 |
| 422 | 실제 모델 ID와 요청 형식 |
| 429 | rate limit·동시 요청 제한 |
| 500 | vLLM·Gateway 로그, API 방식 |
| 502·504 | 중간 Gateway·vLLM 상태와 timeout |

진단 순서:

```text
/v1/models → /v1/chat/completions(stream=false)
→ Open WebUI 단일 요청 → Open WebUI streaming
```

Responses API는 사내 endpoint에서 성공을 확인하기 전에는 사용하지 않습니다. 사내 호스트의 직접·프록시 경로를 각각 확인한 뒤, 직접 경로가 검증된 경우에만 NO_PROXY에 추가하고 Open WebUI를 재시작합니다.

## Hermes 시작 실패

### Gateway stopped

```powershell
hermes --profile team-poc gateway
```

전경 로그를 확인합니다.

### aiohttp not installed

0.19.0 pip/uv 설치에서 발생할 수 있습니다. 임의로 site-packages를 수정하지 않고 공식 설치본 전환 계획으로 이동합니다.

### /health는 되지만 /v1/models가 401

Authorization: Bearer <HERMES_API_KEY> 헤더와 Open WebUI에 저장한 Key가 같은지 확인합니다.

### 8642가 외부에 열림

```powershell
Get-NetTCPConnection -LocalPort 8642 -State Listen |
    Select-Object LocalAddress, LocalPort
```

127.0.0.1이 아니면 즉시 Gateway를 중단합니다.

## 사용자·Memory 격리 실패

다음은 파일럿 중단 조건입니다.

- 새 대화에서 이전 대화의 일회성 문자열이 자동 회수됨
- 사용자 A의 정보가 사용자 B에게 노출됨
- Memory를 껐는데 장기 기억이 생성됨
- 비활성화한 Shell·파일 Tool이 실행됨

이 경우 다른 사용자를 추가하지 않고 Profile과 Open WebUI 사용자 분리를 다시 검토합니다.
