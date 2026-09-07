# 01. Open WebUI 설치 및 기동

> 문서 역할: Windows 최초 설치·기동 절차
>
> 목표: Docker를 사용하지 않는 Windows PC에서 Open WebUI 0.11.3의 로그인 화면까지 확인한다.

최신 적용 상태는 [STATUS](STATUS.md), 환경값은 [versions](../versions.md), 기동 판정은 [평가표 A](../evals/scenarios.md)에서 관리합니다.

이 단계에서는 사내 vLLM과 Hermes를 아직 연결하지 않습니다.

## 초기 설치 기록 (2026-09-03)

사용자 보고로 uv 설치, GitHub·PyPI·Hugging Face 프록시 접근 HTTP 200, Open WebUI 실행 명령 입력을 확인했습니다. 이 기록은 최초 설치 과정의 관찰이며 최신 기동 상태를 대신하지 않습니다.

## 1. PowerShell 세션 설정

실제 프록시와 내부 호스트는 Git에 저장하지 않습니다.

```powershell
$proxyUrl = "http://<CORPORATE_PROXY_HOST>:<PORT>"

$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl
$env:NO_PROXY = "127.0.0.1,localhost,::1"
$env:UV_SYSTEM_CERTS = "true"
```

- 프록시 계정이나 비밀번호를 URL에 넣지 않습니다.
- 인증서 오류가 발생해도 TLS 검증을 끄지 않습니다.
- PowerShell을 새로 열면 세션 설정을 다시 적용합니다.
- 사내 모델 호스트는 [인증 포함 경로 확인](02-vllm-direct-test.md) 후 직접 연결이 검증된 경우에만 `NO_PROXY`에 추가합니다.

연결 확인:

```powershell
curl.exe -I --proxy $proxyUrl https://github.com
curl.exe -I --proxy $proxyUrl https://pypi.org/simple/open-webui/
curl.exe -I --proxy $proxyUrl https://huggingface.co
```

2026-09-03 초기 연결 시험에서는 세 주소 모두 HTTP 200을 확인했습니다. 이후 다른 PC·망에서 설치할 때는 다시 확인합니다.

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

## 3. 표시 이름 설정

Community 버전의 공식 `WEBUI_NAME` 환경 변수를 사용합니다.

```powershell
$env:WEBUI_NAME = "EES Assistant"
```

Open WebUI 0.11.3은 Community 라이선스에서 다음처럼 원본 프로젝트명을 덧붙입니다.

```text
EES Assistant (Open WebUI)
```

`Open WebUI` 표기까지 완전히 제거하는 로고·화이트라벨 변경은 Enterprise 라이선스 영역이므로 소스 파일을 직접 수정하지 않습니다. 사내망에서 외부 메타데이터를 조회하는 legacy `CUSTOM_NAME`도 사용하지 않습니다.

저장소의 `start-openwebui.ps1`는 위 값을 기본 적용합니다. 다른 이름으로 시험하려면 다음처럼 실행할 수 있습니다.

```powershell
.\scripts\start-openwebui.ps1 -WebUiName "<DISPLAY_NAME>"
```

이 값은 프로세스 시작 시 읽습니다. 이미 실행 중이라면 원래 창에서 `Ctrl+C`로 종료하고 다시 시작한 뒤 브라우저를 새로고침합니다. 데이터 디렉터리나 DB를 삭제할 필요는 없습니다.

공식 참고: https://docs.openwebui.com/reference/env-configuration/#webui_name

## 4. 고정 버전 실행

수동 실행:

```powershell
uvx --python 3.11 open-webui@0.11.3 serve --host 127.0.0.1 --port 8080
```

또는 저장소 스크립트:

```powershell
$env:CORP_PROXY_URL = "http://<CORPORATE_PROXY_HOST>:<PORT>"
$env:CORP_NO_PROXY = "127.0.0.1,localhost,::1"
.\scripts\start-openwebui.ps1
```

첫 실행에는 Python 패키지와 임베딩 모델 다운로드로 시간이 걸릴 수 있습니다. 모델 캐시가 없는 최초 실행에서는 OFFLINE_MODE나 HF_HUB_OFFLINE을 먼저 설정하지 않습니다.

## 5. 기동 확인

다음과 유사한 문구를 확인합니다.

```text
Uvicorn running on http://127.0.0.1:8080
```

브라우저에서 http://127.0.0.1:8080 을 엽니다. 별도 PowerShell에서는 다음 smoke test를 실행할 수 있습니다.

```powershell
.\scripts\smoke-test.ps1
```

이 점검은 지정한 loopback 주소의 응답만 확인하고 리디렉션은 따라가지 않습니다. HTTP 3xx는 실패로 처리하므로 기본 주소·경로와 로컬 서비스 응답을 확인합니다. 성공해도 사내 모델·Confluence 연결이나 사용자 권한 검증을 대신하지 않습니다.

첫 계정은 관리자 권한을 갖게 될 수 있으므로 POC 관리자 계정으로 생성하고, 비밀번호는 문서에 기록하지 않습니다.

## 6. 통과 조건

아래 체크 표시는 2026-09-03 초기 설치의 사용자 보고입니다. 최신 판정과 남은 시험은 [평가표 A](../evals/scenarios.md)에서 확인합니다.

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

`Get-NetTCPConnection`이 인식되지 않으면 WebUI 실행창을 유지하고 별도 PowerShell에서 아래 한 줄로 확인합니다. 모듈 설치·설정 변경·재시작은 필요하지 않습니다.

```powershell
netstat.exe -ano | findstr.exe LISTENING | findstr.exe /C:":8080 "
```

출력의 **왼쪽 로컬 주소**가 `127.0.0.1:8080`인 수신 행만 있어야 W02 기준에 맞습니다. 오른쪽 원격 주소의 `0.0.0.0:0`은 수신 주소 판정에 사용하지 않습니다. 다른 로컬 주소가 있거나 출력 없음·명령 오류면 해당 상태만 확인하며, 실제 사내 주소·전체 연결 목록은 공유하지 않습니다. `::1`은 IPv6 루프백이므로 다른 주소라는 이유만으로 외부 공개를 단정하지 않습니다. `-p tcp`로 IPv6 행을 제외하지 않고, 포트 뒤 공백까지 일치시켜 다른 포트를 섞지 않습니다. 이는 현재 8080 수신 주소의 확인이며 프로세스 소유·별도 프록시 구성까지 검증하는 것은 아닙니다. 옵션과 열 구분은 [Microsoft netstat](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netstat), 문자열 필터는 [Microsoft findstr](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/findstr)를 따릅니다.

## 7. 포트와 프록시

로컬 Open WebUI의 127.0.0.1:8080과 원격 사내 프록시의 8080은 충돌하지 않습니다.

```text
Open WebUI  = 내 PC의 127.0.0.1:8080에서 수신
사내 프록시 = 원격 <CORPORATE_PROXY_HOST>:8080으로 접속
```

## 다음 단계

위 통과 조건을 확인한 후 [02. 사내 vLLM 직접 연결](02-vllm-direct-test.md)로 진행합니다. 실패하면 Hermes를 건드리지 않고 [Troubleshooting](troubleshooting.md)에서 Open WebUI 문제부터 분리합니다.
