# 01. Open WebUI 설치 및 기동

> 상태: **진행 중**  
> 목표: Docker를 사용하지 않는 Windows PC에서 Open WebUI 0.11.3의 로그인 화면까지 확인한다.

이 단계에서는 사내 vLLM과 Hermes를 아직 연결하지 않습니다.

## 현재 확인 결과

| 항목 | 결과 |
|---|---|
| uv 설치 | 0.12.7 확인 |
| GitHub 접근 | 프록시 경유 HTTP 200 |
| PyPI 접근 | 프록시 경유 HTTP 200 |
| Hugging Face 접근 | 프록시 경유 HTTP 200 |
| Open WebUI 실행 명령 | 입력 완료 |
| 기동·로그인 화면 | 확인 필요 |

## 1. PowerShell 세션 설정

실제 프록시와 내부 호스트는 Git에 저장하지 않습니다.

```powershell
$proxyUrl = "http://<CORPORATE_PROXY_HOST>:<PORT>"

$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl
$env:NO_PROXY = "127.0.0.1,localhost,<INTERNAL_VLLM_HOST>"
$env:UV_SYSTEM_CERTS = "true"
```

- 프록시 계정이나 비밀번호를 URL에 넣지 않습니다.
- 인증서 오류가 발생해도 TLS 검증을 끄지 않습니다.
- PowerShell을 새로 열면 세션 설정을 다시 적용합니다.

연결 확인:

```powershell
curl.exe -I --proxy $proxyUrl https://github.com
curl.exe -I --proxy $proxyUrl https://pypi.org/simple/open-webui/
curl.exe -I --proxy $proxyUrl https://huggingface.co
```

현재 환경에서는 세 주소 모두 HTTP 200을 확인했습니다.

## 2. 데이터 위치 고정

```powershell
$owuiRoot = Join-Path $env:LOCALAPPDATA "EES-Agent-POC\open-webui"
$owuiData = Join-Path $owuiRoot "data"

New-Item -ItemType Directory -Force -Path $owuiData | Out-Null
Set-Location $owuiRoot

$env:DATA_DIR = $owuiData
$env:ENABLE_OLLAMA_API = "False"
```

예상 위치:

```text
%LOCALAPPDATA%\EES-Agent-POC\open-webui\
├─ data\
└─ .webui_secret_key
```

data에는 계정·대화·첨부파일 등 민감한 상태가 저장될 수 있습니다. data와 .webui_secret_key는 Git에 올리지 않습니다. 같은 작업 디렉터리를 계속 사용해야 생성된 secret key가 유지됩니다.

## 3. 고정 버전 실행

수동 실행:

```powershell
uvx --python 3.11 open-webui@0.11.3 serve --host 127.0.0.1 --port 8080
```

또는 저장소 스크립트:

```powershell
$env:CORP_PROXY_URL = "http://<CORPORATE_PROXY_HOST>:<PORT>"
$env:CORP_NO_PROXY = "127.0.0.1,localhost,<INTERNAL_VLLM_HOST>"
.\scripts\start-openwebui.ps1
```

첫 실행에는 Python 패키지와 임베딩 모델 다운로드로 시간이 걸릴 수 있습니다. 모델 캐시가 없는 최초 실행에서는 OFFLINE_MODE나 HF_HUB_OFFLINE을 먼저 설정하지 않습니다.

## 4. 기동 확인

다음과 유사한 문구를 확인합니다.

```text
Uvicorn running on http://127.0.0.1:8080
```

브라우저에서 http://127.0.0.1:8080 을 엽니다. 별도 PowerShell에서는 다음 smoke test를 실행할 수 있습니다.

```powershell
.\scripts\smoke-test.ps1
```

첫 계정은 관리자 권한을 갖게 될 수 있으므로 POC 관리자 계정으로 생성하고, 비밀번호는 문서에 기록하지 않습니다.

## 5. 통과 조건

- [x] 프로세스가 오류 없이 유지된다.
- [x] http://127.0.0.1:8080 이 열린다.
- [x] 가입 또는 로그인 화면이 표시된다.
- [x] 관리자 계정을 생성할 수 있다.
- [ ] listener가 127.0.0.1:8080에만 열린다.
- [ ] 재시작 후 계정이 유지된다.

listener 확인:

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

## 6. 포트와 프록시

로컬 Open WebUI의 127.0.0.1:8080과 원격 사내 프록시의 8080은 충돌하지 않습니다.

```text
Open WebUI  = 내 PC의 127.0.0.1:8080에서 수신
사내 프록시 = 원격 <CORPORATE_PROXY_HOST>:8080으로 접속
```

## 다음 단계

위 통과 조건을 확인한 후 [02. 사내 vLLM 직접 연결](02-vllm-direct-test.md)로 진행합니다. 실패하면 Hermes를 건드리지 않고 [Troubleshooting](troubleshooting.md)에서 Open WebUI 문제부터 분리합니다.
