"""Pure procedure planning and saved workflow case views."""

from copy import deepcopy

from .ees_workflow_definition import SYSTEMS, _ancestors, _dependencies, _leaves


def _workflow(definition, process_id, assets, *, case_id="", snapshots=None):
    """Project one procedure for planning without creating/selecting an execution.

    Published procedures use currently accessible Skill content. An execution
    instead uses its frozen content, and only while current access remains.
    Never include the registry or raw snapshot map in the returned definition.
    """
    nodes = definition["nodes"]
    included = {node_id for node_id in nodes
                if _ancestors(nodes, node_id)[0]["id"] == process_id}
    tool_ids = {tool for node_id in included for tool in nodes[node_id]["tools"]}
    skill_ids = {"common", *(skill for node_id in included for skill in nodes[node_id]["skills"])}
    projected = {
        "systems": deepcopy(definition["systems"]),
        "sites": deepcopy(definition["sites"]),
        "roots": {category: [process_id] if process_id in roots else []
                  for category, roots in definition["roots"].items()},
        "nodes": {key: deepcopy(value) for key, value in nodes.items() if key in included},
        "tools": {key: deepcopy(value) for key, value in definition["tools"].items() if key in tool_ids},
        "skills": {key: deepcopy(value) for key, value in definition["skills"].items() if key in skill_ids},
    }
    available_tools = {tool["id"] for tool in assets.get("tools", [])}
    for tool in projected["tools"].values():
        external = tool.get("source") == "open_webui"
        tool["available"] = tool.get("reference") in available_tools if external else tool.get("enabled", True)
        tool["simulation"] = not external and tool.get("adapter") == "mock"
        tool["executable"] = bool(tool["simulation"] and tool.get("enabled", True))
        if not tool["executable"]:
            tool["message"] = ("사용 중지된 점검은 수행할 수 없습니다." if not tool.get("enabled", True)
                               else "현재 업무 실행 연결이 없어 수행할 수 없습니다.")
    bodies, versions = assets.get("skill_bodies", {}), assets.get("skill_versions", {})
    for skill in projected["skills"].values():
        if skill.get("source") != "open_webui":
            continue
        reference = skill.get("reference")
        available = reference in bodies and (not case_id or reference in (snapshots or {}))
        skill["available"] = available
        skill["body"] = (snapshots[reference]["body"] if case_id else bodies[reference]) if available else ""
        if available:
            if case_id:
                skill["snapshot_updated_at"] = snapshots[reference].get("updated_at")
            else:
                skill["updated_at"] = versions.get(reference)
        else:
            skill["message"] = "이 스킬을 현재 계정으로 사용할 수 없습니다. 권한·사용 여부를 확인해 주세요."
    result = {"source": "case" if case_id else "published", "process_id": process_id,
              "version": definition["version"], "definition": projected}
    if case_id:
        result["case_id"] = case_id
    return result


def _applicable(case, node_id):
    site = case["site"]
    for node in _ancestors(case["definition"]["nodes"], node_id):
        condition = node.get("condition", "all")
        if not node.get("enabled", True) or case["system"] not in node.get("systems", SYSTEMS):
            return False
        if condition == "interface" and not site["interface"]:
            return False
        if condition == "reuse" and not site["reuse"]:
            return False
        if condition == "new-infra" and site["reuse"]:
            return False
        for prefix, key in (("country:", "country"), ("factory:", "id"), ("line:", "line")):
            if condition.startswith(prefix) and condition[len(prefix):] != site[key]:
                return False
    return True


def _finished(case, node_id):
    return all(not _applicable(case, leaf) or case["jobs"][leaf]["status"] == "passed"
               for leaf in _leaves(case["definition"]["nodes"], node_id))


def _missing(case, node_id):
    return [dep for dep in _dependencies(case["definition"]["nodes"], node_id)
            if not _finished(case, dep)]


def _inputs(case, job):
    """Use the same effective public inputs for execution and readiness."""
    site = case["site"]
    values = {"db": site["db"], "ap": site["ap"], "site": f"{site['country']} · {site['name']} · {site['line']}",
              "interface": f"{case['system']} · {site['name']} 시스템 간 연계 · 예시" if site["interface"] else ""}
    values.update(job["inputs"])
    return values


def _job_readiness(case, node_id, assets):
    node, job = case["definition"]["nodes"][node_id], case["jobs"][node_id]
    applicable = _applicable(case, node_id)
    missing = _missing(case, node_id)
    active = applicable and job["status"] != "passed"
    reason = ""
    if active:
        skills = [case["definition"]["skills"][skill_id]
                  for ancestor in _ancestors(case["definition"]["nodes"], node_id)
                  for skill_id in ancestor["skills"]]
        tools = [case["definition"]["tools"][tool_id] for tool_id in node["tools"]]
        values = _inputs(case, job)
        if any(skill.get("source") == "open_webui" and (
                skill["reference"] not in assets.get("skill_bodies", {})
                or skill["reference"] not in case.get("_skill_snapshots", {})) for skill in skills):
            reason = "skill_unavailable"
        elif node["mode"] == "tool" and any(tool.get("adapter") != "mock"
                or tool.get("source") == "open_webui" or not tool.get("enabled", True) for tool in tools):
            reason = "connection_required"
        elif node["mode"] == "tool" and any(not str(values.get(
                node["bindings"].get(tool["id"], tool["input"]), "")).strip() for tool in tools):
            reason = "input_required"
        elif missing:
            reason = "prerequisite_required"
    attention = active and (job["status"] in {"failed", "blocked"} or reason not in ("", "prerequisite_required"))
    return {"attention": attention, "block_reason": reason,
            "ready_for_run": bool(active and node["mode"] == "tool" and not missing and not reason
                                  and job["status"] not in {"failed", "running"})}


def _view(case, assets=None):
    """Derive displayed parent state without persisting a second truth."""
    if case is None:
        return None
    case = deepcopy(case)
    nodes = case["definition"]["nodes"]
    readiness = {node_id: _job_readiness(case, node_id, assets or {}) for node_id in case["jobs"]}
    case.pop("_skill_snapshots", None)
    node_states = {}
    for node_id in nodes:
        leaves = _leaves(nodes, node_id)
        relevant = [leaf for leaf in leaves if _applicable(case, leaf)]
        statuses = ["blocked" if case["jobs"][leaf]["status"] == "pending"
                    and readiness[leaf]["block_reason"] not in ("", "prerequisite_required")
                    else case["jobs"][leaf]["status"] for leaf in relevant]
        done = sum(status == "passed" for status in statuses)
        missing = _missing(case, node_id)
        if not relevant:
            status = "skipped"
        elif done == len(relevant):
            status = "passed"
        elif "failed" in statuses:
            status = "failed"
        elif "review" in statuses:
            status = "review"
        elif "blocked" in statuses or all(_missing(case, leaf) for leaf in relevant):
            status = "blocked"
        elif "running" in statuses:
            status = "running"
        elif nodes[node_id]["type"] != "j" and (
                done or any(case["jobs"][leaf]["attempt"] or case["jobs"][leaf]["history"] for leaf in relevant)):
            status = "in_progress"
        else:
            status = "pending"
        node_states[node_id] = {"status": status, "applicable": _applicable(case, node_id),
                                "missing": missing, "progress": {"done": done, "total": len(relevant)},
                                "failed_count": statuses.count("failed"),
                                "excluded_count": len(leaves) - len(relevant),
                                "incomplete_count": len(relevant) - done,
                                "review_count": statuses.count("review"),
                                "blocked_count": sum(case["jobs"][leaf]["status"] == "blocked"
                                                     or bool(readiness[leaf]["block_reason"]) for leaf in relevant),
                                "attention_count": sum(readiness[leaf]["attention"] for leaf in relevant),
                                "ready_count": sum(readiness[leaf]["ready_for_run"] for leaf in relevant),
                                "waiting_count": sum(readiness[leaf]["block_reason"] == "prerequisite_required" for leaf in relevant)}
        unfinished = [leaf for leaf in relevant if case["jobs"][leaf]["status"] != "passed"]
        next_jobs = [leaf for leaf in unfinished if not _missing(case, leaf)] or unfinished
        node_states[node_id]["next_node_id"] = next_jobs[0] if next_jobs else ""
        if nodes[node_id]["type"] == "j":
            node_states[node_id].update(readiness[node_id])
    case["node_states"] = node_states
    case["status"] = node_states[case["process_id"]]["status"]
    case["progress"] = node_states[case["process_id"]]["progress"]
    case["process_name"] = nodes[case["process_id"]]["name"]
    case["category"] = nodes[case["process_id"]]["category"]
    # Older saved executions did not record their creation time. Keep that
    # unknown instead of relabelling their last selection/edit as creation.
    case.setdefault("created_at", None)
    selected = _ancestors(nodes, case["selected_id"])
    skill_ids = list(dict.fromkeys(["common", *(skill for node in selected for skill in node["skills"])]))
    case["context"] = {
        "breadcrumb": [{"id": node["id"], "name": node["name"], "type": node["type"]} for node in selected],
        "skills": [deepcopy(case["definition"]["skills"][key]) for key in skill_ids],
        "instructions": [node.get("instructions", "") for node in selected if node.get("instructions")],
        "simulation": True,
    }
    return case
