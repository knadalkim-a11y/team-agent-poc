# Troubleshooting

Windows 로컬 POC의 장애를 계층별로 분리합니다. 실제 구성한 경로에서 앞 단계가 실패하면 뒤 단계를 수정하지 않습니다. 최신 적용 경로는 [STATUS](STATUS.md), 실행 환경은 [versions](../versions.md)를 확인합니다. 아래 ③·④는 Hermes 비교를 선택해 연동한 경우에만 진단하며 Native MVP의 필수 단계가 아닙니다.

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

<a id="user-model-not-found"></a>

## 일반 사용자만 Model not found

관리자 A는 Workspace Assistant를 사용할 수 있지만 일반 사용자 B는 `Model not found`를 받는다면, Assistant 자체와 연결된 **기반 모델의 읽기 권한**을 각각 확인합니다. v0.11.3은 목록에 Assistant를 표시할 때와 실제 채팅을 실행할 때의 검사가 다릅니다. 채팅에서는 기반 모델의 권한도 검사하므로 목록에 보이는 것만으로 실행 가능하다고 판단하지 않습니다. 기반 모델 ID가 없거나 오래된 경우에도 같은 문구가 가능하므로 오류만으로 원인을 확정하지 않습니다. [모델 접근 검사](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/models.py), [기반 모델 체인 검사](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/access_control/__init__.py)

1. A의 **Workspace → 모델 → EES 통합 Assistant 편집**에서 `Base Model (From)`에 지정된 정확한 기반 모델을 확인합니다. Assistant의 **접근**에 B의 읽기 권한이 등록돼 있고 화면 하단 **저장 및 업데이트**까지 눌렀는지도 확인합니다. 실제 모델 ID·주소는 사내 화면에서만 확인합니다.
2. A의 **관리자 패널 → 설정 → 모델**에서 그 기반 모델을 찾아 **편집(연필) → 접근 → 접근 권한 추가**로 B 또는 승인된 시험 그룹에 **읽기**를 부여하고 **저장 및 업데이트**합니다. 다른 preset을 기반으로 사용하는 구성이라면 그 아래 기반 모델까지 접근 권한을 확인합니다. 기존 사용자의 권한과 모델 연결 설정을 보존합니다.
3. 기반 모델의 `Hide`는 UI 표시 정리이며 읽기 권한과 별개입니다. 숨김만 해제하는 것으로 권한 문제를 해결하지 않습니다. B에게 필요한 모델의 읽기 권한만 설정하며 관리자 승격·전체 공개·접근 검사 우회는 필요하지 않습니다.
4. B 화면을 새로고침하고 새 대화에서 `EES 통합 Assistant`를 다시 선택해 “안녕. 한 문장으로 답해줘.”처럼 도구가 필요 없는 질문을 보냅니다. 정상 답변을 확인한 후에만 Confluence 공통 문서 조회와 C05를 이어갑니다. 이 단계에서 PAT·HTTP·프록시·인증서 설정을 변경하지 않습니다.

기반 모델 편집·권한 저장 경로는 [관리자 모델 설정](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/admin/Settings/Models.svelte)과 [공통 모델 편집기](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/ModelEditor.svelte)를 기준으로 확인했습니다. 저장 후에도 실패하면 실제 선택 ID와 preset의 Base Model 유효성을 사내에서 대조하고, 실패 요청의 경로·HTTP 상태·비식별 오류 `detail`만 확인합니다. 일반 채팅 경로는 권한 오류도 HTTP 400으로 감쌀 수 있어 403 여부만으로 판정하지 않습니다. 실제 사내 원인·해결 여부는 별도 결과가 있어야 확정합니다.

<a id="windows-accept-winerror64"></a>

## Windows WinError 64와 accept_coro

`Task exception was never retrieved`에 `IocpProactor.accept.<locals>.accept_coro()`가 함께 있으면 들어오는 연결을 수락하는 Windows asyncio 경로에서 난 예외입니다. CPython 3.11의 Proactor 서버는 이 과정의 `OSError`에서 listener를 닫는 경로가 있습니다. 사용자에게서 받은 두 로그만으로 실제 listener 종료·끊긴 상대·발생 동작이나 Jira/GitHub 변경과의 인과관계는 확정하지 않습니다. [CPython 보고](https://github.com/python/cpython/issues/93821), [수락 예외 처리](https://github.com/python/cpython/blob/3.11/Lib/asyncio/proactor_events.py).

사내 PC에 접근할 수 없다면 Git의 준비 작업과 실제 복구를 구분합니다. 다음 접속 때 기존 기본 주소의 `/health`를 한 번 확인합니다. 정상 응답이면 곧바로 실행 방식을 바꾸지 않고 보류했던 후속 조회를 이어갑니다. 응답이 없으면 실행 PC에서도 같은 수신 주소·포트로 확인해 로컬 서버와 팀원 접속 경로를 구분하고, 같은 시점의 `Accept failed on a socket` 유무만 확인합니다. 연결 대상 IP·전체 로그·토큰은 외부에 전달하지 않습니다.

### 재발 시 선택할 기동 준비본

기존 서버의 수락 오류와 접속 중단이 함께 확인되면 [Windows 선택 실행 파일](../scripts/serve_openwebui_windows.py)로 Proactor 수락 경로를 피하는 방안을 검토할 수 있습니다. 실행 파일은 `WindowsSelectorEventLoopPolicy`를 설정한 뒤 원래 `open_webui.serve()`를 호출합니다. v0.11.3의 Windows `serve()`는 `loop='none'`을 사용하므로 이 정책을 유지합니다. WebUI·Python 설치 파일을 수정하거나 오류 로그를 숨기는 방식이 아닙니다. [WebUI 기동 소스](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/__init__.py), [Uvicorn 0.51.0 loop 선택](https://github.com/Kludex/uvicorn/blob/0.51.0/uvicorn/config.py).

지원 범위는 **Windows·Python 3.11·WebUI 0.11.3·Uvicorn 0.51.0·기존 SQLite·단일 worker**입니다. Windows Selector는 asyncio subprocess/pipe를 지원하지 않고 소켓 512개 제한이 있어, 현재 읽기 API 중심의 작은 구성에 한정한 선택지입니다. 로컬 프로세스 실행 기능·여러 worker·확장 운영은 별도 검토합니다. [Python 제한](https://docs.python.org/3.11/library/asyncio-platforms.html). 사내 기동·복구·모델 스트리밍은 아직 미확인입니다.

검수한 커밋에서 실행 파일을 사내 Git 작업 폴더로 가져온 후, **원래 WebUI 기동 PowerShell의 작업 위치와 환경**에서 아래 사전검사만 먼저 실행합니다. 새 창이라면 기존 기동 때의 `DATA_DIR`·키 설정·암호화·프록시·사내 API 설정을 그대로 복원합니다. 저장소 폴더로 작업 위치를 바꾸면 기존 키 파일을 찾지 못할 수 있습니다.

```powershell
$eesWin64Launcher = Join-Path $env:USERPROFILE 'team-agent-poc\scripts\serve_openwebui_windows.py'
uvx --offline --no-python-downloads --python 3.11 --from 'open-webui==0.11.3' python $eesWin64Launcher --check
if ($LASTEXITCODE -ne 0) { throw '기존 실행 환경 확인 실패. 현재 설정을 유지하고 안내를 확인하세요.' }
```

`--check`는 서버·모델·API·DB 접속과 WebUI import 없이 패키지 버전 및 기존 파일의 존재/크기만 확인합니다. 키·DB 내용은 읽거나 출력하지 않고 파일도 만들지 않습니다. `PreflightPassed=true`는 이 사전조건만 뜻하며 `/health` 성공이나 저장 암호화 검증이 아닙니다. `DATABASE_URL` 등 별도 DB 설정·패키지가 읽는 `.env`·여러 worker가 있으면 중단합니다. 통과시키려고 해당 설정을 지우지 않습니다. 캐시가 없으면 중단하며 새 패키지·Python을 내려받지 않습니다.

선택 기동을 적용할 때만 원래 서버 창에서 `Ctrl+C`로 해당 WebUI를 종료하고, 같은 작업 폴더·환경에서 **기존에 사용하던 수신 IP와 포트**를 전달합니다. 접속 범위를 자동으로 바꾸지 않으며 다른 Python/Hermes 프로세스를 일괄 종료하지 않습니다.

```powershell
$eesListenAddress = Read-Host '기존 WebUI --host 값'
$eesListenPort = [int](Read-Host '기존 WebUI --port 값')
uvx --offline --no-python-downloads --python 3.11 --from 'open-webui==0.11.3' python $eesWin64Launcher --host $eesListenAddress --port $eesListenPort
if ($LASTEXITCODE -ne 0) { throw '선택 기동 실패. 해당 오류를 확인하고 기존 기동 명령으로 복구하세요.' }
```

기동 후 필요한 확인은 `/health`와 일반 채팅 한 건의 스트리밍·정상 완료입니다. 정상일 때 보류한 GitHub 후속 조회를 이어갑니다. 완료한 PAT·DB 저장·20회 검사를 자동 반복하지 않습니다. 원복은 해당 서버를 종료한 뒤 동일 환경에서 기존 `uvx --python 3.11 open-webui@0.11.3 serve --host ... --port ...` 명령으로 기동하는 것입니다. 별도 재설치·DB/키 재생성·방화벽 변경은 이 대응에 포함되지 않습니다. [준비와 검증 범위](../evals/scenarios.md#windows-accept-preparation).


<a id="chat-visible-after-refresh"></a>

## 채팅 답변이 새로고침한 뒤에만 보임

`/health`는 정상이지만 새 대화의 짧은 질문이 멈춰 보이고 새로고침하면 답변이 나타나는 경우, 답변 생성/저장과 실시간 전달/화면 반영을 분리해서 진단합니다. 이 현상만으로 모델 정지·새 Tool 오류·Windows 수락 오류 재발을 확정하지 않습니다.

Open WebUI v0.11.3의 [응답 처리](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/middleware.py)는 저장 대화의 최종 출력을 DB에 반영하고 `chat:completion` 이벤트를 보냅니다. [Socket.IO 서버](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/socket/main.py)와 [브라우저 갱신](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/chat/Chat.svelte)은 별도 경로입니다. [공식 연결 오류 안내](https://docs.openwebui.com/troubleshooting/connection-error/)도 브라우저 WebSocket·CORS 오류 확인을 권고합니다.

loopback에서 사내 IP로 접속 주소를 바꾼 뒤부터라는 단서가 있으면 현재 WebUI 서버 PowerShell 로그의 `is not an accepted origin` 유무부터 확인합니다. 해당 문구가 없다는 것만으로 CORS 정상이라고 판정하지 않습니다.

브라우저 쪽 정보를 확인할 때는 같은 접속 주소에서 **F12 → Console(콘솔)**을 열고 새 대화에 `안녕`을 한 번만 보냅니다. 답변이 멈춰 보이면 그 상태에서 `WebSocket`, `socket.io`, `connect_error`, `CORS`, `TypeError` 관련 문구 1~2줄을 확인합니다. [클라이언트 연결 처리](https://github.com/open-webui/open-webui/blob/v0.11.3/src/routes/%2Blayout.svelte)는 `connect_error`를 일반 로그로 기록하므로 빨간 오류에만 한정하지 않습니다. 실제 주소·토큰·세션 값은 가리고 전체 콘솔/HAR·요청 헤더는 전달하지 않습니다. 개발자 도구가 사내 정책으로 제한되면 우회하지 않고 그 제한을 알립니다.

- 허용되지 않은 origin·CORS 오류가 있으면 실제 브라우저 접속 origin과 **현재 서버 프로세스가 사용하는** `CORS_ALLOW_ORIGIN`을 대조하고 [허용 주소 보완](#cors-origin-update)을 적용합니다. 과거 초기 진단의 `http://127.0.0.1:8080`만 남은 경우와 현재 사내 IP 접속이 다른 경우를 구분합니다. 새 PowerShell의 빈 환경변수를 실행 중 서버 설정으로 해석하지 않습니다.
- WebSocket 연결 실패 문구이면 실패 상태/사유와 승인된 접속 경로를 확인합니다. `ENABLE_WEBSOCKET_SUPPORT=true`일 때 v0.11.3은 WebSocket 전송만 사용하므로 자동 polling/SSE 복구를 가정하지 않습니다. 오류 증거 없이 해당 설정을 끄거나 단일 PC에 Redis·새 프록시를 추가하지 않습니다.
- `TypeError` 등 화면 처리 오류가 있으면 해당 오류의 파일명과 첫 호출 위치로 범위를 좁힙니다. 콘솔 정보가 없으면 다음 단계에서 Network의 실시간 연결 상태를 확인합니다.

먼저 원인을 좁히고 해당 설정/경로만 보완합니다. 최초 진단에서 코드·Prompt 재입력, 재설치·업그레이드·재시작·토큰/DB 검증을 일괄 반복하지 않습니다. 수정 뒤 같은 짧은 대화의 실시간 표시·정상 완료를 확인하고 보류한 카드 확인으로 돌아갑니다. 현재 관찰과 판정은 [결과 기록](../evals/scenarios.md#chat-live-update-observation)에 남깁니다.

<a id="cors-origin-update"></a>

### 현재 브라우저 주소를 허용 목록에 영구 저장

`is not an accepted origin`이 확인됐거나 승인된 브라우저 접속 주소를 변경할 때 사용합니다. 서버가 수신하는 `--host`와 브라우저 origin 허용 설정은 별개입니다. v0.11.3의 [CORS 설정](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/config.py)은 주소를 세미콜론으로 나누며, 빈 항목이나 `*;주소` 혼합은 기동 오류를 낼 수 있습니다.

1. **현재 WebUI 서버를 실행한 원래 PowerShell**에서 `Ctrl+C`를 누르고 입력 가능한 상태가 될 때까지 기다립니다. 같은 창·기존 폴더를 유지합니다.
2. 아래 블록 전체를 한 번 실행하고 주소를 물으면 현재 브라우저 주소를 `http://` 또는 `https://`부터 입력합니다. 대화 경로는 자동으로 제외합니다. 현재 창과 Windows 사용자 설정에 명시한 주소를 합치고 이전 loopback 주소와 현재 주소를 추가합니다. 기존 값이 비었거나 `*`뿐이면 이 두 주소를 명시적으로 허용합니다. 허용 목록을 **이 PC의 현재 Windows 사용자 환경변수에 영구 저장**하고 현재 창에도 적용합니다.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $eesUrl = [uri](Read-Host '현재 WebUI 브라우저 주소 전체')
    if (-not $eesUrl.IsAbsoluteUri -or $eesUrl.Scheme -notin @('http', 'https') -or -not $eesUrl.Host -or $eesUrl.UserInfo) {
        throw '브라우저 주소를 http:// 또는 https://부터 입력하세요.'
    }
    $eesOrigin = $eesUrl.GetLeftPart([System.UriPartial]::Authority)
    $eesStored = [Environment]::GetEnvironmentVariable('CORS_ALLOW_ORIGIN', 'User')
    $eesOrigins = @((@($env:CORS_ALLOW_ORIGIN, $eesStored) -join ';') -split ';' |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and $_ -ne '*' })
    $eesCors = (@($eesOrigins + 'http://127.0.0.1:8080' + $eesOrigin) |
        Select-Object -Unique) -join ';'
    [Environment]::SetEnvironmentVariable('CORS_ALLOW_ORIGIN', $eesCors, 'User')
    if ([Environment]::GetEnvironmentVariable('CORS_ALLOW_ORIGIN', 'User') -cne $eesCors) {
        throw '사용자 설정 저장을 확인하지 못했습니다.'
    }
    $env:CORS_ALLOW_ORIGIN = $eesCors
    Write-Host '영구 저장 및 현재 창 적용 완료'
}
```

3. `영구 저장 및 현재 창 적용 완료`가 나오면 **같은 창에서 직전에 사용한 기존 기동 명령**을 다시 실행합니다. 입력 오류가 나면 올바른 주소로 블록을 다시 실행합니다. 저장 권한 오류면 오류 내용을 확인하고 강제로 관리자/시스템 범위로 바꾸지 않습니다. 데이터·키·모델·패키지와 수신 주소는 이 블록이 변경하지 않습니다.
4. 정상 기동 후 브라우저를 한 번 새로고침해 연결을 맺고, 새 대화에 `안녕`을 한 번 보냅니다. 그 뒤 새로고침 없이 답변이 표시되고 완료되는지 확인합니다. 실패하면 현재 서버에 같은 origin 거부가 다시 나오는지 확인하고, 다른 오류라면 위 진단으로 범위를 좁힙니다.

User 범위는 **같은 Windows 계정에서 재부팅 후에도 유지**됩니다. 평소 기동 시 주소를 다시 입력할 필요가 없습니다. 기존 기동 절차에 `$env:CORS_ALLOW_ORIGIN`을 예전 loopback 값으로 다시 지정하는 줄이 있으면 제거해야 저장된 목록을 덮어쓰지 않습니다. IP·포트·HTTP/HTTPS가 바뀔 때만 새 주소를 추가합니다. 다른 Windows 계정·서비스·서버로 옮길 때는 해당 실행 환경에 다시 설정합니다.

이미 열려 있던 다른 Terminal·VS Code·PowerShell은 이전 환경을 보유할 수 있습니다. 이번 원래 창은 위 명령이 즉시 갱신합니다. 다른 기존 창을 꼭 사용해야 할 때만 기동 전에 아래 한 줄로 저장값을 읽습니다. 모든 새 탭이 즉시 최신 환경을 물려받는다고 가정하지 않습니다. [Microsoft 환경변수 안내](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables?view=powershell-5.1), [User 저장과 새 프로세스 상속](https://learn.microsoft.com/en-us/dotnet/api/system.environment.setenvironmentvariable?view=netframework-4.8.1).

```powershell
$env:CORS_ALLOW_ORIGIN = [Environment]::GetEnvironmentVariable('CORS_ALLOW_ORIGIN', 'User')
```

사용자 환경변수는 해당 계정에서 실행하는 다른 인스턴스에도 상속될 수 있습니다. 현재 단일 PC·계정의 수동 기동에 적용하며 별도 파일/로더·서비스는 추가하지 않습니다. 사내 IP·주소는 Git이나 채팅에 보내지 않습니다. 복사 블록은 각각 2,500자 이내이며 실제 Windows 저장·재기동·복구 판정은 사용자 확인이 필요합니다.

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
$env:PYTHONPROFILEIMPORTTIME = "1"

uvx --python 3.11 open-webui@0.11.3 serve --host 127.0.0.1 --port 8080
```

- 이 import 정체 진단 때문에 `CORS_ALLOW_ORIGIN`을 loopback만 허용하도록 덮어쓰지 않습니다. 기존 허용 목록을 유지하고 실제 origin 거부 오류가 있을 때 [주소 설정](#cors-origin-update)을 보완합니다.
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

`/health`가 200이고 UI 로그인까지 가능하다면 기본 서버 응답과 로그인을 확인한 상태입니다. 사내 모델·검색·재시작·전체 데이터 저장 상태까지 정상이라고 판정하지는 않습니다. 이 경고는 Hugging Face의 임베딩·리랭커·Whisper 같은 외부 자산 조회 또는 다운로드에서 Python 런타임이 사내 TLS 검사 프록시의 인증서 체인을 신뢰하지 못해 발생할 수 있습니다.

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

<a id="native-knowledge-embedding"></a>

### Native query_knowledge_files에서 임베딩 오류

Confluence `get_page`와 `query_knowledge_files`는 별도 경로입니다. 저장소의 Confluence Tool은 고정된 읽기 API를 호출하고, Open WebUI의 내장 `query_knowledge_files`는 Workspace Knowledge를 의미 검색하며 임베딩 함수를 사용합니다. v0.11.3에서 문서 설정의 임베딩 우회는 이 내장 검색 함수에 적용되지 않습니다. [의미 검색 구현](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/tools/builtin.py#L3138-L3306), [소스 본문 처리의 우회 분기](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/retrieval/utils.py#L1334-L1573)

`embedding model`이 없다는 오류만으로 정확한 엔진·모델 경로·캐시·설정을 확정하지 않습니다. 같은 시험에서 Confluence 본문·답변·링크가 정상이면 그 성공은 보존하고 내장 검색의 실패를 별도로 기록합니다. 문서의 공격 지시를 따랐다는 근거 없이 다른 검색 호출 자체를 prompt injection 실패로 분류하지 않습니다.

작은 POC의 최소 보완:

1. A의 **Workspace → 모델 → EES 통합 Assistant 편집 → System Prompt**에서 기존 내용 끝에 [현재 POC의 자료 조회 경로](../agent-pack/system-prompts/ees-integrated-assistant.md#현재-poc의-자료-조회-경로) 섹션만 추가하고 **저장 및 업데이트**합니다. 같은 섹션이 있으면 중복 추가하지 않습니다. 이번 부분 적용을 과거 Prompt·정책 개정 전체의 배포 완료로 기록하지 않습니다.
2. 기존 Knowledge와 Skill 연결은 유지합니다. v0.11.3의 내장 도구 UI는 `Knowledge Base` 그룹을 제어하며, 전체 OFF 시 목록·파일명 검색·본문 읽기도 함께 제거됩니다. `query_knowledge_files`만 끄는 개별 UI 토글은 제공하지 않습니다. [도구 주입 조건](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/tools.py#L538-L643), [내장 도구 UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/BuiltinTools.svelte)
3. 새 대화에서 기존 합성 공통 Confluence 문서의 ID로 조회·요약·링크를 요청합니다. 다른 새 대화에서는 `POC-POL-001에서 운영 DB 직접 조회가 허용되는지 문서 ID·버전·관련 절을 근거로 알려줘.`라고 질문합니다. 전자는 Confluence Tool, 후자는 필요한 목록/파일명 검색과 `view_knowledge_file`로 정상 답변하는지, 임베딩 검색 오류가 재발하는지 확인합니다. 이는 새 Prompt 부분 적용의 C04·P02 회귀 확인이며 완료된 권한·쓰기·injection 시험 전체를 반복하는 절차가 아닙니다.

지침은 함수 노출을 강제로 차단하지 않으므로 임베딩 검색 자체가 복구됐다고 기록하지 않습니다. 재발하면 실패 함수·선택 경로와 적용 여부를 확인합니다. 의미 검색이 실제로 필요해지면 승인된 사내 임베딩 API 또는 반입 모델을 별도로 구성하고 검색을 검증합니다. 이번 보완으로 모델 다운로드·TLS 우회·DB 재생성·기존 PAT 변경을 수행하지 않습니다.

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

[직접 연결 가이드](02-vllm-direct-test.md)에 따라 인증을 포함한 실제 API 요청의 직접·프록시 경로를 비교합니다. 비인증 401·403이나 프록시 CONNECT의 200만으로 정상 경로를 정하지 않습니다. 검증된 경로에 맞춰 `NO_PROXY`를 설정하며, `/models`가 제한되면 승인된 모델 ID로 Chat Completions를 확인합니다. 인증서 오류가 이어지면 승인된 PEM CA bundle을 `AIOHTTP_CLIENT_SSL_CERT_FILE`에 지정하고 TLS 검증은 유지합니다.

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

0.19.0 pip/uv 설치에서 발생할 수 있습니다. 임의로 site-packages를 수정하지 않습니다. Hermes 비교를 실제로 선택한 경우에만 [호환성 확인 절차](03-hermes-integration.md)에 따라 설치 방식·버전 변경 필요를 검토하고 승인 후 재검증합니다.

### /health는 되지만 /v1/models가 401

Authorization: Bearer <HERMES_API_KEY> 헤더와 Open WebUI에 저장한 Key가 같은지 확인합니다.

### 8642가 외부에 열림

```powershell
Get-NetTCPConnection -LocalPort 8642 -State Listen |
    Select-Object LocalAddress, LocalPort
```

127.0.0.1이 아니면 즉시 Gateway를 중단합니다.

## 사용자·Memory 격리 실패

<a id="native-chat-history"></a>

### 새 대화에서 search_chats·view_chat으로 과거 내용을 찾음

같은 계정의 새 대화에서 이 두 함수로 이전 문자열을 찾았다면 **Chat History 조회**를 먼저 확인합니다. Memory 저장이나 다른 사용자 정보 노출을 뜻하지 않습니다. v0.11.3의 `search_chats`는 현재 사용자 ID로 검색하고 `view_chat`은 대화 ID와 현재 사용자 ID로 조회합니다. [조회 함수](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/tools/builtin.py#L1530-L1624)

초기 MVP는 현재 대화 범위로 시작하므로 아래처럼 설정합니다.

1. 관리자 A의 **Workspace → 모델 → EES 통합 Assistant 편집**을 엽니다.
2. 화면 아래 **Builtin Tools / 내장 도구**에서 **Chat History / 대화 기록**을 해제합니다. **Memory**는 아래 [제어 범위](#native-memory-controls)에 따라 **Capabilities와 Builtin Tools 양쪽에서 OFF**인지 확인합니다. Builtin Tools 기능 자체는 켜 두고 Knowledge Base·Confluence 도구·Skill 연결을 유지합니다.
3. **저장 및 업데이트**를 누르고 화면을 새로고침합니다. 이 선택은 UI에서 `meta.builtinTools.chats=false`로 저장되며, 기본값은 true입니다. false이면 Native 함수 목록에 `search_chats`·`view_chat`을 추가하지 않습니다. Memory는 별도 조건으로 제어됩니다. [내장 도구 UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/BuiltinTools.svelte), [모델 저장](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/ModelEditor.svelte#L331-L336), [함수 노출 조건](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/tools.py#L538-L663)
4. 같은 계정으로 **새 대화**를 만들고 같은 Assistant에서 `다른 대화에서 내가 말한 테스트 문자열이 뭐였지?`라고 묻습니다. 문자열·이전 대화 본문을 새 질문에 붙이지 않습니다. 과거 대화 조회 호출 없이 확인할 수 없다고 답하는지 확인합니다. 같은 대화 회수 시험이나 토큰 검사는 반복하지 않습니다.

설정 후에도 회수하면 실제 선택한 Assistant·저장 여부·조회 함수·다른 컨텍스트 유입을 확인합니다. 기존 대화 목록이나 Memory를 삭제해 시험을 통과시키지 않습니다. Chat History OFF는 모델의 해당 내장 조회 경로를 제한하는 것이며, 사용자가 자신의 저장된 대화를 직접 여는 기능을 없애거나 기존 대화를 삭제하지 않습니다. 새 대화에서 모른다고 답한 것만으로 S02·S03의 실제 Memory 설정·저장소까지 확인된 것으로 기록하지 않습니다.

<a id="native-memory-controls"></a>

### Memory 도구와 모델 기능의 차이

v0.11.3의 아래 제어는 서로 다릅니다. 새 대화에서 이전 문자열을 모른다고 답해도 모든 Memory 경로가 꺼졌거나 저장소에 문자열이 없음을 증명하지는 않습니다.

| 설정 | 확인한 제어 범위 | 초기 MVP |
|---|---|---|
| 모델 Capabilities → Memory | 내장 Memory 함수·저장 Memory의 문맥 주입·응답 후 자동 Memory 검토가 공통으로 검사하는 모델 조건 | OFF |
| 모델 Builtin Tools → Memory | Native Memory 함수 목록의 노출; 자동 문맥 주입·응답 후 검토는 이 값만으로 차단되지 않음 | OFF |
| 개인 설정 → 개인화 → Memory | 사용자별 설정 및 Saved Memories 화면 노출; OFF이면 목록·검색도 숨겨짐 | 저장소 확인과 설정 확인을 구분 |

관리자 A가 **Workspace → 모델 → EES 통합 Assistant 편집 → Capabilities / 기능 → Memory**를 확인합니다. 켜져 있으면 해제하고 **저장 및 업데이트**합니다. 이미 OFF이면 유지하고 완료한 S01 질문을 반복하지 않습니다. 모델 편집기의 **Builtin Tools → Memory·Chat History**도 OFF를 유지하며, 기존 Knowledge·Confluence 도구·Skill 연결은 보존합니다. 이 작업은 모델 설정 확인이며 Prompt나 도구 코드를 교체하지 않습니다.

공식 구현은 [Capabilities UI](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/Capabilities.svelte#L56-L58), [모델 설정 저장](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/workspace/Models/ModelEditor.svelte#L264-L267), [Native Memory 조건](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/tools.py#L657-L675), [자동 문맥 주입 조건](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/memory.py#L285-L291), [응답 후 검토 조건](https://github.com/open-webui/open-webui/blob/v0.11.3/backend/open_webui/utils/memory.py#L409-L444)을 대조했습니다. 모델 기능 OFF는 기존에 저장된 Memory를 삭제하는 작업이 아닙니다.

S03의 저장소 확인은 별도입니다. **설정 → 개인화 → Memory**에서 목록이 원래 보이는 경우에만 시험 문자열을 검색할 수 있습니다. 개인 Memory가 OFF라 목록이 숨겨져 있거나 개인화 탭이 없으면 확인 목적으로 켜지 않습니다. 목록 조회 오류가 있어도 빈 목록으로 표시될 수 있으므로 오류 상태의 검색 결과 없음은 저장 부재로 판정하지 않습니다. [개인 설정과 목록 표시](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/chat/Settings/Personalization.svelte#L99-L147), [목록 조회 오류 처리](https://github.com/open-webui/open-webui/blob/v0.11.3/src/lib/components/chat/Settings/Personalization.svelte#L51-L58)

### 실제 격리·비활성화 위반

다음은 파일럿 중단 조건입니다.

- Chat History·Memory OFF를 확인한 초기 구성에서 다른 경로로 이전 대화 정보가 회수되며 원인이 확인되지 않음
- 사용자 A의 비공개 정보가 권한 없는 사용자 B에게 노출됨
- Memory를 껐는데 장기 기억이 생성됨
- 비활성화한 Shell·파일 Tool이 실행됨

이 경우 다른 사용자를 추가하지 않고 실제 조회 경로·권한·설정을 확인합니다. 허용된 같은 계정의 과거 대화 조회와 다른 사용자 격리 실패를 혼동하지 않습니다.
