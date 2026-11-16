"""Verify and scope a Confluence connection for the optional built-in guide."""
from getpass import getpass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
import json
import os
import re
import ssl
import sys
from urllib.parse import urlsplit


REGISTRY = "EES_WORK_API_SERVICES"
PILOT = "confluence-readonly-pilot"
AUTH = "EES_CONFLUENCE_PILOT_AUTHORIZATION"
LIMIT = 1024 * 1024


class GuideConnectionError(ValueError):
    pass


def normalized_base(address):
    # Only the supplied HTTPS origin and REST context will receive the PAT.
    # Validate before printing it or asking for secrets.
    message = "Confluence HTTPS 주소와 /rest/api까지의 경로를 확인하세요."
    if not isinstance(address, str) or not address.isascii() or re.search(r"[\x00-\x20\x7f\\?#%]", address):
        raise GuideConnectionError(message)
    try:
        url = urlsplit(address)
        if (url.scheme != "https" or not url.hostname or url.port == 0
                or url.username is not None or url.password is not None
                or not re.fullmatch(r"(?:[a-z0-9.-]+|\[[a-f0-9:.]+\])(?::[0-9]+)?", url.netloc.lower())
                or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/rest/api/?", url.path)):
            raise ValueError()
    except ValueError:
        raise GuideConnectionError(message) from None
    return "https://" + url.netloc.lower() + url.path.rstrip("/")


def registry_entry(current, base, actor):
    if not re.fullmatch(r"[A-Za-z0-9._@-]{1,160}", actor):
        raise GuideConnectionError("이 가이드를 실행할 EES 사용자 ID를 확인하세요.")
    try:
        entries = json.loads(current)
        if not isinstance(entries, dict) or not all(isinstance(v, dict) for v in entries.values()):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise GuideConnectionError("기존 EES_WORK_API_SERVICES 형식을 확인하세요.") from None
    content = base + "/content"
    proposed = {"base_url": content, "actor_ids": [actor],
                "user_credential_headers": {actor: {"Authorization": AUTH}}}
    target = urlsplit(content)
    for key, entry in entries.items():
        if key == PILOT and entry == proposed:
            continue
        if key == PILOT or AUTH in json.dumps(entry).upper():
            raise GuideConnectionError("이미 연결된 서비스나 인증이 있습니다. 기존 연결로 배포하세요.")
        try:
            other = urlsplit(entry["base_url"])
            same_origin = (other.scheme == target.scheme and other.hostname == target.hostname
                           and (other.port or 443) == (target.port or 443))
            path = other.path.rstrip("/")
        except (KeyError, ValueError, TypeError, AttributeError):
            raise GuideConnectionError("기존 서비스의 base_url을 확인하세요.") from None
        if same_origin and (path == target.path or target.path.startswith(path + "/") or path.startswith(target.path + "/")):
            raise GuideConnectionError("기존 서비스가 같은 Confluence 경로를 사용합니다. 기존 연결로 배포하세요.")
    return json.dumps({**entries, PILOT: proposed}, ensure_ascii=False, separators=(",", ":"))


def login_actor(settings):
    host = "::1" if settings.get("host") in ("::", "::1") else "127.0.0.1"
    port = settings.get("port")
    if type(port) is not int or not 0 < port <= 65535:
        raise GuideConnectionError("설치 설정에서 EES 서비스 포트를 확인하세요.")
    email = input("로컬 EES 계정 이메일: ").strip()
    password = getpass("로컬 EES 계정 비밀번호 (숨김): ")
    conn = HTTPConnection(host, port, timeout=12)
    try:
        payload = json.dumps({"email": email, "password": password}).encode()
        conn.request("POST", "/api/v1/auths/signin", payload, {"Content-Type": "application/json", "Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise GuideConnectionError("로컬 EES 로그인에 실패했습니다. SSO 계정은 사용자 ID를 직접 입력하세요.")
        raw = response.read(65537)
        identity = json.loads(raw) if len(raw) <= 65536 else {}
        actor = identity.get("id") if isinstance(identity, dict) else None
        if not isinstance(actor, str) or not actor:
            raise GuideConnectionError("사용자 ID를 읽을 수 없습니다. EES 사용자 ID를 직접 입력하세요.")
        return actor
    except (OSError, HTTPException, UnicodeError, json.JSONDecodeError, RecursionError):
        raise GuideConnectionError("로컬 EES 계정 조회에 실패했습니다. EES 사용자 ID를 직접 입력하세요.") from None
    finally:
        conn.close()


def fetch_page(url, path, authorization, context):
    conn = HTTPSConnection(url.hostname, url.port or 443, timeout=12, context=context)
    try:
        conn.request("GET", path, headers={"Authorization": authorization, "Accept": "application/json", "Accept-Encoding": "identity"})
        response = conn.getresponse()
        if response.status != 200:
            hints = {401: "토큰 및 만료 시각", 403: "계정의 공간·페이지 열람 권한", 404: "페이지 ID·열람 권한·서버 경로"}
            hint = "최종 HTTPS 주소와 SSO 설정" if 300 <= response.status < 400 else hints.get(response.status, "Confluence 서비스 상태")
            raise GuideConnectionError(f"HTTP {response.status} · {hint}을 확인하세요.")
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise GuideConnectionError("응답이 업무 도구의 크기 제한인 1 MiB를 넘었습니다.")
        return json.loads(raw)
    except (OSError, HTTPException):
        raise GuideConnectionError("Confluence HTTPS 연결에 실패했습니다. 서버 경로·DNS·인증서 신뢰를 확인하세요.") from None
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise GuideConnectionError("Confluence의 JSON 응답을 확인하세요.") from None
    finally:
        conn.close()


def valid_page(page):
    return (isinstance(page, dict) and page.get("type") == "page" and isinstance(page.get("title"), str)
            and bool(page["title"].strip()) and isinstance(page.get("id"), str) and re.fullmatch(r"[0-9]+", page["id"]))


def probe(base, page_id, authorization):
    url = urlsplit(base)
    context = ssl.create_default_context()
    path = url.path + "/content/" + page_id
    page = fetch_page(url, path, authorization, context)
    if not valid_page(page) or page["id"] != page_id:
        raise GuideConnectionError("기준 문서의 ID·제목·유형을 확인할 수 없습니다.")
    listing = fetch_page(url, path + "/child/page?limit=5", authorization, context)
    rows = listing.get("results") if isinstance(listing, dict) else None
    if not isinstance(rows, list) or len(rows) > 5 or not all(valid_page(row) for row in rows):
        raise GuideConnectionError("하위 문서 목록의 ID·제목·유형을 확인할 수 없습니다.")
    return len(rows)


def connect(base, settings):
    """Prepare the child process environment after testing both real GETs."""
    base = normalized_base(base)
    names = settings.get("env_names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise GuideConnectionError("등록된 EES 설치 설정을 확인하세요.")
    if {REGISTRY, AUTH}.intersection(name.upper() for name in names):
        raise GuideConnectionError("관리자가 저장한 API 설정이 있습니다. 기존 연결로 배포하세요.")
    if not sys.stdin.isatty():
        raise GuideConnectionError("읽기 계정 PAT를 숨겨 입력할 수 있도록 대화형 PowerShell에서 실행하세요.")
    print(f"Confluence 연결 대상 · {base}")
    page = input("기준 문서의 숫자 페이지 ID: ").strip()
    if not re.fullmatch(r"[0-9]{1,32}", page):
        raise GuideConnectionError("Confluence 페이지 정보에 표시되는 숫자 ID를 입력하세요.")
    actor = input("실행할 EES 사용자 ID (모르면 Enter로 로컬 계정 로그인): ").strip() or login_actor(settings)
    env = dict(os.environ)
    env[REGISTRY] = registry_entry(env.get(REGISTRY, "{}"), base, actor)
    pat = getpass(f"{urlsplit(base).netloc}의 Confluence 읽기 계정 PAT (숨김): ")
    if not re.fullmatch(r"[!-~]{1,11993}", pat):
        raise GuideConnectionError("Bearer 접두어 없이 발급받은 토큰 값만 입력하세요.")
    auth = "Bearer " + pat
    if AUTH in env and env[AUTH] != auth:
        raise GuideConnectionError("현재 환경에 다른 가이드 인증이 있습니다. 기존 연결로 배포하세요.")
    count = probe(base, page, auth)
    print(f"기준 문서 1건 · 하위 문서 {count}건 확인 (최대 5건, 두 API 모두 HTTP 200)")
    env[AUTH] = auth
    return env
