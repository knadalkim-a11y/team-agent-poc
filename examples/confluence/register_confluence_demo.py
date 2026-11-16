"""Register the two read-only API specs and their test workflow. Python 3, stdlib only."""
import argparse
import copy
import getpass
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

TITLE = "Confluence 기준 문서와 하위 문서 확인 (시험)"
WORKING_TITLE = TITLE + " · 등록 중"
PAGE = "getConfluencePage"
CHILDREN = "listConfluenceChildPages"
EXPECTED = {PAGE: "/content/{id}", CHILDREN: "/content/{id}/child/page"}


class SetupError(Exception):
    pass


def make_definition(draft, apis):
    definition = copy.deepcopy(draft)
    nodes = definition["nodes"]
    root = next(n["id"] for n in nodes.values() if n["type"] == "p")
    definition.update(name=TITLE, execution_scope="system")
    nodes[root].update(name=TITLE, children=["documents"])
    nodes["documents"] = {"id": "documents", "type": "t", "parent": root,
                          "name": "문서 구조 확인", "children": ["page", "children"], "deps": []}
    for key, operation, result_block in (("page", apis[PAGE], "human_confirm"),
                                         ("children", apis[CHILDREN], "list_confirm")):
        nodes[key] = {"id": key, "type": "j", "parent": "documents", "name": operation["name"],
                      "children": [], "deps": [], "mode": "tool", "result_block": result_block, "human_confirmation": True,
                      "api_binding": {"operation_id": operation["id"], "version": operation["version"],
                                      "inputs": {}, "outputs": ["title", "id", "type"]}}
    nodes["page"]["inputs"] = [{"id": "page-id", "name": "페이지 ID", "type": "text",
                                "scope": "run", "required": True, "source": {"api_operation_id": apis[PAGE]["id"]}}]
    nodes["page"]["api_binding"]["inputs"] = {"id": {"input": "page-id"}}
    nodes["children"].update(deps=["page"], api_generated_deps=["page"])
    nodes["children"]["api_binding"]["inputs"] = {
        "id": {"result": {"confirmed": True, "job_id": "page", "field": "id"}},
        "limit": {"constant": 5}}
    return definition


def provision(call, spec_text, system):
    def post(route, action, fixed=False, **payload):
        request = {"action": action, "expected_revision": 0, **payload}
        key = json.dumps(request, ensure_ascii=False, sort_keys=True)
        request["request_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "ees-confluence-demo-v1:" + key)
                                    if fixed else uuid.uuid4())
        return call(route, request)

    state = call("workspace", query={"system_id": system})
    if not state.get("capabilities", {}).get("is_admin"):
        raise SetupError("API 명세 등록은 EES Workflow 관리자 계정으로 로그인하세요.")
    if state.get("confluence_guide"):
        guide = call("workspace", query={"workflow_id": "guide-confluence-documents"})["workflow"]
        return {"workflow_id": guide["id"], "system_id": guide["system_id"], "status": "built_in",
                "published_version": guide.get("published_version")}
    if system not in state["capabilities"]["managed_systems"]:
        raise SetupError("선택한 시스템에 업무 절차를 등록할 권한이 없습니다.")
    existing = [wf for wf in state["workflows"] if wf["name"] == TITLE and wf["system_id"] == system]
    if len(existing) > 1:
        raise SetupError("같은 이름의 절차가 여러 개 있습니다. 워크 · 업무 절차에서 확인하세요.")

    preview = post("operations", "api_import_preview", source_text=spec_text)
    rows = {row.get("operation_key"): row for row in preview["operations"]}
    if len(preview["operations"]) != 2 or set(rows) != set(EXPECTED):
        raise SetupError("이 예제의 원본 읽기 API 두 개만 등록할 수 있습니다. 기존 서비스에 다른 명세가 있는지도 확인하세요.")
    for key, path in EXPECTED.items():
        row = rows[key]
        if (row.get("mode") not in ("new", "same") or row.get("method") != "GET"
                or row.get("source_path") != path or row.get("state") != "active"):
            raise SetupError("기존 API와 명세가 다릅니다. 기존 설정을 보존했습니다. 워크 · 도구에서 차이를 확인하세요.")
    selections = [{"key": row["key"], "expected_revision": 0} for row in rows.values() if row["mode"] == "new"]
    if existing:
        wf = existing[0]
        published = wf.get("published") or {}
        nodes = published.get("nodes", {})
        roots = [n for n in nodes.values() if n.get("type") == "p"]
        if not selections and len(roots) == 1:
            root = roots[0]["id"]
            expected = make_definition({"id": wf["id"], "name": WORKING_TITLE, "system_id": system,
                                        "category": "ops", "nodes": {root: {"id": root, "name": WORKING_TITLE,
                                        "type": "p", "parent": None, "children": [], "deps": []}}}, rows)
            # Publication adds its frozen external-resource inventory to the stored snapshot.
            authored = {key: value for key, value in published.items() if key != "resource_versions"}
            if authored == expected and wf.get("draft") == expected and wf.get("published_version"):
                return {"workflow_id": wf["id"], "status": "existing", "published_version": wf["published_version"]}
        raise SetupError("같은 이름으로 다른 절차 또는 미게시 초안이 있습니다. 기존 절차를 보존하고 중단했습니다.")
    if selections:
        applied = post("operations", "api_import_apply", source_text=spec_text, selections=selections,
                       document_hash=preview["document_hash"])
        rows.update({row["operation_key"]: row for row in applied["apis"]})

    created = post("workspace/command", "create_workflow", fixed=True, system_id=system, name=WORKING_TITLE,
                   execution_scope="system", category="ops")
    workflow_id = created["workflow_id"]
    current = call("workspace", query={"system_id": system, "workflow_id": workflow_id})["workflow"]
    if current["revision"] != 1 or current["name"] != WORKING_TITLE or current["published_version"] is not None:
        raise SetupError("이전에 생성한 시험 절차가 편집되었습니다. 기존 절차를 확인하세요.")
    definition = make_definition(current["draft"], rows)
    saved = post("workspace/command", "save_draft", fixed=True, workflow_id=workflow_id,
                 expected_revision=1, definition=definition, publication_state="published")
    return {"workflow_id": workflow_id, "status": "created", "published_version": saved["published_version"]}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def session(url, email):
    target = urlsplit(url)
    local = target.hostname in ("localhost", "127.0.0.1", "::1")
    if (target.scheme not in ("https", "http") or (target.scheme == "http" and not local)
            or not target.hostname or target.username is not None or target.password is not None
            or target.query or target.fragment):
        raise SetupError("EES Workflow의 HTTPS 주소 또는 이 PC의 http://127.0.0.1:포트 를 입력하세요.")
    opener = build_opener(NoRedirect())
    base = url.rstrip("/")

    def request(path, data=None, token=None, query=None):
        full = base + path + ("?" + urlencode(query) if query else "")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request(full, data=json.dumps(data).encode("utf-8") if data is not None else None, headers=headers)
        try:
            with opener.open(req, timeout=45) as response:
                result = json.load(response)
        except HTTPError as exc:
            reason = ""
            try:
                err = json.loads(exc.read(16000)).get("error", {})
                reason = " · " + str(err.get("code", "")) + " " + str(err.get("message", ""))
            except (ValueError, AttributeError):
                pass
            raise SetupError(f"EES Workflow HTTP {exc.code}{reason}") from None
        if not isinstance(result, dict):
            raise SetupError("EES Workflow의 JSON 응답 형식을 확인하세요.")
        if result.get("ok") is False:
            err = result.get("error", {})
            raise SetupError(f"{err.get('code', '오류')} · {err.get('message', '')}")
        return result

    if email:
        secret = getpass.getpass("EES Workflow 로그인 비밀번호: ")
        identity = request("/api/v1/auths/signin", {"email": email, "password": secret})
        token = identity.get("token")
        del secret
    else:
        token = getpass.getpass("EES Workflow 관리자 API 키 (Confluence PAT와 별도): ").strip()
        # An API key can have endpoint restrictions. Identification is optional here.
        try:
            identity = request("/api/v1/auths/", token=token) if token else {}
        except SetupError:
            identity = {}
    if not token:
        raise SetupError("EES Workflow 인증값을 확인하세요.")
    if identity.get("id"):
        print("현재 EES 계정 ID:", identity["id"])
    return lambda route, data=None, query=None: request("/api/ees-work/" + route, data, token, query)


def main():
    parser = argparse.ArgumentParser(description="시험용 읽기 API 2개와 실행 가능한 업무 절차 1개를 EES Workflow에 등록합니다.")
    parser.add_argument("--ees-url", required=True, help="EES Workflow 주소 (Confluence 주소와 별도)")
    parser.add_argument("--system", required=True, help="시험 절차를 둘 시스템 ID (예: EMS)")
    parser.add_argument("--email", help="Native 로그인을 사용할 EES 관리자 이메일. 생략하면 EES API 키를 입력합니다.")
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("confluence-readonly.openapi.json"))
    args = parser.parse_args()
    print(f"EES Workflow {args.ees_url}  |  시스템 {args.system}  |  게시할 절차 {TITLE}")
    spec = args.spec.read_text(encoding="utf-8-sig")
    out = provision(session(args.ees_url, args.email), spec, args.system)
    if out["status"] == "built_in":
        print(f"{out['system_id']} 시스템에 기본 Confluence 가이드가 있습니다. 업무 → 운영에서 열 수 있습니다.")
    elif out["status"] == "existing":
        print("같은 구성이 이미 게시되어 있습니다. 변경하지 않았습니다.")
    else:
        print("시험 절차를 게시했습니다. 업무 · 운영에서 페이지 ID를 입력하고 시작하세요.")
    print(f"절차 ID {out['workflow_id']}  |  게시 버전 {out['published_version'] or '미게시'}")


if __name__ == "__main__":
    try:
        main()
    except (SetupError, ValueError, KeyError, OSError, EOFError, URLError) as exc:
        sys.exit("등록 중단 · " + str(exc))
