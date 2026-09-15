"""Pure display state derived from a saved workflow case."""

from copy import deepcopy

from .ees_workflow_definition import SYSTEMS, _ancestors, _dependencies, _leaves


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


def _view(case):
    """Derive displayed parent state without persisting a second truth."""
    if case is None:
        return None
    case = deepcopy(case)
    case.pop("_skill_snapshots", None)
    nodes = case["definition"]["nodes"]
    node_states = {}
    for node_id in nodes:
        leaves = _leaves(nodes, node_id)
        relevant = [leaf for leaf in leaves if _applicable(case, leaf)]
        statuses = [case["jobs"][leaf]["status"] for leaf in relevant]
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
                                "excluded_count": len(leaves) - len(relevant)}
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
