# 01. Open WebUI 설치 및 기동

> 문서 역할: Windows 최초 설치·기동 및 기존 PC 팀 파일럿 절차
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

<a id="local-pc-pilot"></a>

## 8. 현재 Windows PC에서 소규모 팀 파일럿

2026-09-07 사용자가 현재 설치해 사용하는 Windows PC를 팀원도 접속할 호스트로 선택했습니다. 위 최초 설치를 다시 실행하지 않습니다. 같은 작업 폴더·`DATA_DIR`·DB·키·버전·수동 기동과 확인한 Tool을 유지합니다. 전용 서버 이전·서비스 등록·자동 시작은 이후 운영 필요에 따라 정합니다. 이번 선택은 기존의 새 서버 우선 계획을 대체하며 [현재 단계와 증거](../evals/scenarios.md#local-pc-pilot-plan)를 따릅니다.

### 먼저 계정과 접속 경로 준비

기존 로컬 화면에서 관리자 설정 → Authentication → **New Sign Ups를 OFF**로 저장합니다. 팀원 계정은 관리자 Users → Add User에서 역할 **user**로 준비합니다. 기존 일반 테스트 계정 B가 있으면 첫 확인에 재사용하고, 관리자의 계정·PAT를 공유하지 않습니다. 비밀번호는 사내 전달 수단을 사용합니다. 각 팀원은 자신의 개인 PAT를 입력합니다. 공개 가입 OFF와 관리자 계정 추가는 별도 경로입니다. [v0.11.3 설정 UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/admin/Settings/Authentication.svelte), [계정 추가 UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/admin/Users/UserList/AddUserModal.svelte)

Assistant·기반 모델·연결된 Tool/Skill/Knowledge의 읽기 권한은 파일럿 계정/그룹에 맞춥니다. 기존 [Model not found 복구](troubleshooting.md#user-model-not-found)를 반복하지 않고 새로 연결한 Jira/GitHub를 포함한 실제 공개 구성을 확인합니다. 일반 사용자에게 Python Tool 등록·수정 권한을 함께 열지 않습니다.

현재 PC는 사용자 보고로 **Public 프로필**이며 우선 IP·포트 직접 접속을 선택했습니다. [확인 기록](../evals/scenarios.md#local-pc-public-access)을 따르며 아래 프로필 확인을 반복하거나 Private으로 바꾸지 않습니다. Public은 Windows 네트워크 프로필 이름이며 인터넷 공개 여부나 공인 IP를 뜻하지 않습니다.

다른 환경에서는 WebUI를 실행한 창을 유지하고 **별도 PowerShell**에서 다음 읽기 전용 명령으로 사내 연결의 네트워크 프로필을 확인합니다. 어댑터가 여러 개라면 실제 사내망 연결을 골라 확인하며 VPN·가상 어댑터를 자동 선택하지 않습니다. 공유할 정보는 해당 연결의 `NetworkCategory`뿐입니다.

```powershell
Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory
```

사내 접속용 PC 주소와 허용할 팀원 PC 주소는 그 PC에서만 관리합니다. DHCP 주소가 바뀌면 바인딩·규칙·접속 주소도 함께 조정해야 하며, 임의 고정 IP를 먼저 설정하지 않습니다. 도구가 없거나 회사 정책으로 제한되면 오류 종류를 확인하고 프로필·방화벽을 우회하지 않습니다.

### 브라우저 접속과 전송 보호

`127.0.0.1`은 접속하는 사람 자신의 PC이므로 팀원용 주소로 배포하지 않습니다. 현재 초기 접속은 사용자 선택에 따라 `http://<PC_LAN_IPV4>:8080`을 사용합니다. 사내 HTTPS 경로·인증서 보유 여부는 별도 미확인으로 남기며 이 초기 연결 단계의 선행조건으로 요구하지 않습니다. 이후 같은 PC의 HTTPS 앞단을 사용할 경우 WebUI는 loopback을 유지할 수 있습니다.

현재 `open-webui serve`에는 `--host`·`--port`가 있지만 `--ssl-certfile`·`--ssl-keyfile` 옵션은 없습니다. 옵션만 붙여 HTTPS가 된다고 안내하지 않습니다. HTTPS가 필요하면 앞단에서 TLS를 처리하며 기존에 승인된 경로가 있는지부터 확인합니다. [v0.11.3 CLI 소스](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/__init__.py), [공식 HTTPS 안내](https://docs.openwebui.com/getting-started/advanced-topics/hardening/#https-and-tls)

직접 HTTP로 열면 로그인 비밀번호·세션·개인 PAT의 브라우저 전송이 암호화되지 않습니다. 기존 DB 암호화 PASS나 좁은 방화벽 규칙은 전송 보호를 대신하지 않습니다. 이 한계를 안내하고 첫 확인은 팀원 PC의 로그인 화면 도달성까지 진행합니다. 초기 HTTP 접속 성공을 전송 보호·공용 사용 전체 검증 완료로 처리하지 않습니다. 이 확인을 위해 인증을 끄거나 `WEBUI_AUTH=false`를 설정하지 않습니다.

### LAN 직접 수신이 필요한 경우의 적용 예시

현재 Public 프로필을 유지하고 **관리자 권한 PowerShell**에서 TCP 8080의 로컬 주소·첫 팀원 원격 주소를 지정합니다. 두 PC의 `ipconfig`에서 실제 사내망 어댑터의 IPv4를 확인해 아래 placeholder만 바꾸며, 실제 주소는 외부로 보내지 않습니다. `LocalSubnet`·`Any`·전체 대역으로 넓히지 않습니다. 아직 실제 적용은 보고되지 않았으며 다음은 준비한 규칙입니다.

```powershell
New-NetFirewallRule -Name "EES-POC-Pilot-8080-Public" -DisplayName "EES POC pilot 8080 Public" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -LocalAddress "<PC_LAN_IPV4>" -RemoteAddress "<TEAMMATE_IPV4>" -Profile Public
```

이름이 같은 규칙이 이미 있으면 신규 명령을 반복하지 않고 해당 규칙의 주소·포트·프로필부터 확인합니다. 기존 Python/8080의 넓은 허용 규칙이 있으면 좁은 규칙을 추가해도 그 허용 범위가 사라지지 않습니다. 기존 유효 규칙을 확인한 뒤 해당 범위만 조정하며, 방화벽 전체 해제·모든 Python 프로세스 허용으로 해결하지 않습니다. 로컬 규칙 적용을 막는 회사 정책은 이 명령으로 우회하지 않습니다. 다른 환경의 프로필은 실제 값에 맞추며 `DomainAuthenticated`는 규칙에서 `Domain`을 사용합니다. [규칙 인자](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule?view=windowsserver2025-ps), [규칙·정책 병합](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules)

이후 **원래 WebUI 실행 창**에서 `Ctrl+C`로 종료하고 기존 환경변수를 유지한 채 수신 주소를 바꿉니다. 아래는 확인했던 기존 경로·uvx 캐시를 사용하는 예시이며 캐시가 없으면 설치·업그레이드 대신 중단합니다. 저장소 시작 스크립트는 종료 시 `Pop-Location`하므로 같은 창이어도 폴더가 바뀔 수 있습니다. 기존 `DATA_DIR`와 비어 있지 않은 키 파일을 확인한 뒤 해당 폴더로 이동합니다. 경로가 다르면 이 예제로 강제 실행하지 않고 실제 기존 위치에 맞춥니다. `DATA_DIR`, `WEBUI_SECRET_KEY`, `ENABLE_VALVE_ENCRYPTION`, 모델/프록시 설정을 재설정하지 않습니다.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $eesRoot = Join-Path $env:LOCALAPPDATA "EES-Agent-POC\open-webui"
    $eesKey = Join-Path $eesRoot ".webui_secret_key"
    if ($env:DATA_DIR -ne (Join-Path $eesRoot "data") -or -not (Test-Path -LiteralPath $eesKey -PathType Leaf)) {
        throw "기존 데이터 경로·키를 확인할 수 없습니다. 원래 실행 창과 설치 위치를 확인하세요."
    }
    if ((Get-Item -LiteralPath $eesKey).Length -eq 0) { throw "기존 키 파일이 비어 있습니다." }
    Set-Location -LiteralPath $eesRoot
    uvx --offline --no-python-downloads --python 3.11 open-webui@0.11.3 serve --host "<PC_LAN_IPV4>" --port 8080
}
```

특정 사내 IP로만 수신하면 기존 loopback URL은 열리지 않으므로 본인과 팀원 모두 `http://<PC_LAN_IPV4>:8080`을 사용합니다. 이번에는 팀원 PC의 익명 로그인 화면 도달성만 확인합니다. HTTPS 앞단 경로를 선택했다면 위 직접 HTTP 수신 변경을 그대로 적용하지 않고 그 경로의 바인딩·포트를 사용합니다. `0.0.0.0`은 접속 URL이 아니며 모든 인터페이스 수신을 기본안으로 사용하지 않습니다.

연결이 막히면 **호스트 수신 → 실제 방화벽 규칙/네트워크 정책 → 팀원 PC 경로** 순서로 범위를 좁힙니다. Git 프록시를 팀원 브라우저나 내부 API 설정으로 복제하지 않습니다. 이번 보고는 팀원 PC의 로그인 화면 표시 여부 또는 비식별 오류만 받습니다. 일반 사용자 로그인·EES Assistant 접근·개인 PAT/조회 권한과 HTTP 전송 보호 한계는 후속 공개 구성에 맞춰 확인합니다.

### 파일럿 운영과 원복

- 처음에는 소수 팀원이 대표 조회를 사용합니다. 도구 실행은 이 Windows PC에서 이루어지고 LLM 요청은 기존 사내 서빙 경로로 전달됩니다. 사용 인원이 늘어났을 때의 동시 처리·응답 시간은 아직 측정하지 않았습니다.
- PC·WebUI 프로세스가 켜져 있고 사내망이 연결된 동안 사용할 수 있습니다. 화면 잠금과 절전은 구분하며 전원 정책 전체를 바꾸지 않고 이용 시간·재시작 시간을 팀 내에서 정합니다.
- 같은 DB·키의 완료한 저장/복구 시험은 반복하지 않습니다. 기존 백업 절차를 유지하고, 새 접속 경로와 일반 계정의 대화·파일·개인 PAT·조회 권한을 [공개 전 기준](03-openwebui-native-agent.md#4-공개-전-검증)에 맞춰 확인합니다. 파일럿 참여자 간 비공개 자산이 공유되지 않는지와 처음 쓰는 사람이 결과·오류·원문을 이해하는지 함께 봅니다.
- 직접 LAN 수신을 중단할 때는 원래 창에서 종료 후 기존 명령의 `--host 127.0.0.1 --port 8080`으로 되돌립니다. 이번에 만든 `EES-POC-Pilot-8080-Public` 규칙만 비활성화하고 팀원용 앞단 경로가 있다면 그 연결도 중단합니다. DB·키·계정·PAT를 삭제하지 않습니다.

이 절은 적용 준비 절차입니다. 실제 방화벽·수신 주소·HTTPS·팀원 접속·격리를 사외에서 실행하거나 통과 처리하지 않았습니다.
