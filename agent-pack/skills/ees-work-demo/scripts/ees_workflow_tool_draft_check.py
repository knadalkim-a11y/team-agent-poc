"""Non-executing draft diagnostics; this is neither a sandbox nor execution approval.

Only Python syntax and the supported input declarations are inspected. Result
paths are display definitions; their existence must be checked by a later trial.
"""
import ast
from copy import deepcopy
import json
import math
import re


MAX_CODE_CHARS = 200_000
MAX_FUNCTIONS = 32
MAX_ARGUMENTS = 32
MAX_ENUM_CHOICES = 64
MAX_ENUM_STRING_CHARS = 512
MAX_IDENTIFIER_CHARS = 128
MAX_SCHEMA_BYTES = 48 * 1024
MAX_RESULT_BYTES = 128 * 1024
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
_WIDGETS = {"text", "number", "boolean", "select", "multiselect"}
_ROLES = {"title", "category", "url", "id", "text"}
_MISSING = object()


class _Unsupported(ValueError):
    pass


class _Limit(_Unsupported):
    pass


def _json_size(value):
    # ASCII JSON also budgets escaped Unicode and is conservative for UTF-8 APIs.
    return len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _literal(node, depth=0):
    """Read JSON-compatible literal syntax without Python evaluation."""
    if depth > 20:
        raise _Unsupported()
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or type(value) in (str, bool, int):
            return value
        if type(value) is float and math.isfinite(value):
            return value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(item, depth + 1) for item in node.elts]
    if isinstance(node, ast.Dict):
        keys = [_literal(key, depth + 1) for key in node.keys]
        if all(isinstance(key, str) for key in keys) and len(set(keys)) == len(keys):
            return {key: _literal(value, depth + 1) for key, value in zip(keys, node.values)}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _literal(node.operand, depth + 1)
        if type(value) in (int, float):
            return -value if isinstance(node.op, ast.USub) else value
    raise _Unsupported()


def _matches(value, schema):
    if "anyOf" in schema:
        return any(_matches(value, branch) for branch in schema["anyOf"])
    kind = schema.get("type")
    valid = {"string": isinstance(value, str), "integer": type(value) is int,
             "number": type(value) is int or (type(value) is float and math.isfinite(value)),
             "boolean": type(value) is bool, "null": value is None,
             "array": isinstance(value, list)}.get(kind, False)
    if not valid:
        return False
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        return False
    return kind != "array" or all(_matches(item, schema["items"]) for item in value)


def _option_key(value):
    return "true" if value is True else "false" if value is False else str(value)


class _Bindings(ast.NodeVisitor):
    """Names bound in this scope, including conditional blocks, not nested scopes."""
    def __init__(self):
        self.names = set()
        self.star = False

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                self.names.add(root.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.names.add(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        pass

    def visit_Import(self, node):
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        self.names.update(alias.asname or alias.name for alias in node.names)
        self.star = self.star or any(alias.name == "*" for alias in node.names)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        if node.rest:
            self.names.add(node.rest)
        self.generic_visit(node)


class _Declarations:
    def __init__(self, module):
        self.aliases = {}
        self.imports = {}
        self.shadowed = set()
        self.unstable = set()
        self.dynamic_all = False
        self.schema_bytes = 0

        def bind(name):
            if name in self.shadowed:
                self.unstable.add(name)
            self.shadowed.add(name)

        for statement in module.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    name = alias.asname or alias.name.split(".")[0]
                    bind(name)
                    self.aliases.pop(name, None)
                    self.imports[name] = alias.name if alias.name == "typing" else ""
            elif isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    name = alias.asname or alias.name
                    bind(name)
                    self.dynamic_all = self.dynamic_all or alias.name == "*"
                    self.aliases.pop(name, None)
                    self.imports[name] = "typing." + alias.name if statement.module == "typing" and not statement.level else ""
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        bind(target.id)
                        self.aliases[target.id] = statement.value
                        self.imports.pop(target.id, None)
                    else:
                        bindings = _Bindings()
                        bindings.visit(target)
                        for name in bindings.names:
                            bind(name)
                            self.unstable.add(name)
                            self.aliases.pop(name, None)
                            self.imports.pop(name, None)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bind(statement.name)
                self.aliases.pop(statement.name, None)
                self.imports.pop(statement.name, None)
            else:
                bindings = _Bindings()
                bindings.visit(statement)
                self.dynamic_all = self.dynamic_all or bindings.star
                for name in bindings.names:
                    bind(name)
                    self.unstable.add(name)
                    self.aliases.pop(name, None)
                    self.imports.pop(name, None)

    def charge(self, size):
        # Charge every expansion, including the same alias in different methods.
        # Stop before accumulating schemas; a final envelope check includes the
        # selected schema copy and diagnostics as well.
        self.schema_bytes += size
        if self.schema_bytes > MAX_SCHEMA_BYTES:
            raise _Limit()

    def name(self, node):
        if isinstance(node, ast.Name):
            if node.id in self.unstable:
                return ""
            return self.imports.get(node.id, node.id if node.id not in self.shadowed else "")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id not in self.unstable and self.imports.get(node.value.id) == "typing":
                return "typing." + node.attr
        return ""

    def schema(self, node, seen=()):
        if node is None or len(seen) > 20 or self.dynamic_all:
            raise _Unsupported()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) > 2_000:
                raise _Unsupported()
            return self.schema(ast.parse(node.value, mode="eval").body, (*seen, "string"))
        if isinstance(node, ast.Name) and node.id in self.aliases:
            if node.id in seen or node.id in self.unstable:
                raise _Unsupported()
            return self.schema(self.aliases[node.id], (*seen, node.id))
        name = self.name(node)
        if name in _TYPES:
            self.charge(32)
            return {"type": _TYPES[name]}
        if not isinstance(node, ast.Subscript):
            raise _Unsupported()
        name = self.name(node.value)
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if name in ("list", "typing.List") and len(args) == 1:
            self.charge(32)
            return {"type": "array", "items": self.schema(args[0], (*seen, "list"))}
        if name == "typing.Optional" and len(args) == 1:
            self.charge(48)
            return {"anyOf": [self.schema(args[0], (*seen, "optional")), {"type": "null"}]}
        if name == "typing.Literal" and args:
            if len(args) > MAX_ENUM_CHOICES:
                raise _Limit()
            values = [_literal(arg) for arg in args]
            types = {type(value) for value in values}
            if len(types) != 1 or not types <= {str, int, bool}:
                raise _Unsupported()
            if any(isinstance(value, str) and len(value) > MAX_ENUM_STRING_CHARS for value in values):
                raise _Limit()
            self.charge(_json_size(values) + 32)
            kind = {str: "string", int: "integer", bool: "boolean"}[type(values[0])]
            if len({_option_key(value) for value in values}) != len(values):
                raise _Unsupported()
            return {"type": kind, "enum": values}
        raise _Unsupported()


def check_draft(draft):
    errors, functions = [], []

    def error(code, message, field=None, line=None):
        item = {"code": code, "message": message}
        if field is not None:
            item["field"] = field[:256]
        if line is not None:
            item["line"] = line
        if len(errors) < 100:
            errors.append(item)

    selected_schema = {"type": "object", "properties": {}, "required": []}

    def limit_result():
        return {"valid": False, "errors": [{"code": "definition_limit", "message": "함수, 입력 인자 또는 선택지 정의가 너무 큽니다. 정의를 나누거나 줄여 주세요.", "field": "code"}],
                "functions": [], "input_schema": {"type": "object", "properties": {}, "required": []}}

    if not isinstance(draft, dict):
        error("draft_format", "도구 작성 내용을 확인해 주세요.")
        return {"valid": False, "errors": errors, "functions": [], "input_schema": selected_schema}
    code = draft.get("code")
    module = None
    if not isinstance(code, str) or not code.strip():
        error("code_required", "도구가 실행할 기능 코드를 작성해 주세요.", "code")
    elif len(code) > MAX_CODE_CHARS:
        error("code_too_large", "기능 코드가 너무 깁니다.", "code")
    else:
        try:
            module = ast.parse(code)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            error("code_syntax", "Python 구문을 확인해 주세요.", "code", getattr(exc, "lineno", None))
    if module is not None:
        classes = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Tools"]
        if len(classes) != 1:
            error("tools_class_required", "Tools 클래스를 하나 작성해 주세요.", "code")
        else:
            try:
                declarations = _Declarations(module)
            except RecursionError:
                return limit_result()
            if classes[0].decorator_list or classes[0].bases or classes[0].keywords or "Tools" in declarations.unstable or declarations.dynamic_all:
                error("tools_class_dynamic", "동적으로 바뀌는 Tools 클래스는 정적으로 확인할 수 없습니다.", "code", classes[0].lineno)
            methods = [node for node in classes[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")]
            if len(methods) > MAX_FUNCTIONS or any(len(node.name) > MAX_IDENTIFIER_CHARS for node in methods):
                return limit_result()
            selected = draft.get("function")
            names = [node.name for node in methods]
            if len(set(names)) != len(names):
                error("function_duplicate", "같은 이름의 공개 함수가 두 번 정의되어 있습니다.", "code")
            rebound = set()
            for statement in classes[0].body:
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    bindings = _Bindings()
                    try:
                        bindings.visit(statement)
                    except RecursionError:
                        return limit_result()
                    rebound.update(bindings.names)
            declarations.unstable.update(rebound | set(names))
            for node in methods:
                schema = {"type": "object", "properties": {}, "required": []}
                diagnostics = []
                if node.decorator_list or node.name in rebound:
                    diagnostics.append(("function_dynamic", "동적으로 바뀌는 함수 선언은 정적으로 확인할 수 없습니다.", "code", node.lineno))
                if node.args.vararg or node.args.kwarg or node.args.posonlyargs:
                    diagnostics.append(("arguments_unsupported", "고정된 이름의 입력 인자를 선언해 주세요.", "code", node.lineno))
                args = node.args.posonlyargs + node.args.args
                if not args or args[0].arg != "self":
                    diagnostics.append(("function_receiver", "Tools 공개 함수의 첫 인자는 self로 선언해 주세요.", "code", node.lineno))
                defaults = [_MISSING] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
                pairs = list(zip(args, defaults)) + [(arg, default if default is not None else _MISSING) for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)]
                business_args = [argument for argument, _ in pairs if argument.arg != "self" and not argument.arg.startswith("__")]
                if len(business_args) > MAX_ARGUMENTS or any(len(argument.arg) > MAX_IDENTIFIER_CHARS for argument in business_args):
                    return limit_result()
                try:
                    declarations.charge(_json_size(node.name) + 96)
                except _Limit:
                    return limit_result()
                for argument, default in pairs:
                    if argument.arg == "self" or argument.arg.startswith("__"):
                        continue
                    try:
                        declarations.charge(2 * _json_size(argument.arg) + 8)
                        item = declarations.schema(argument.annotation)
                        if default is not _MISSING:
                            value = _literal(default)
                            if not _matches(value, item):
                                raise _Unsupported()
                            declarations.charge(_json_size(value) + 16)
                            item["default"] = value
                        else:
                            schema["required"].append(argument.arg)
                        schema["properties"][argument.arg] = item
                    except _Limit:
                        return limit_result()
                    except (SyntaxError, ValueError, RecursionError, TypeError):
                        diagnostics.append(("input_declaration_unsupported", "입력 형식 또는 기본값을 정적으로 확인할 수 없습니다.", "input_ui." + argument.arg, argument.lineno))
                functions.append({"name": node.name, "input_schema": schema})
                if node.name == selected:
                    selected_schema = schema
                    for diagnostic in diagnostics:
                        error(*diagnostic)
            if not methods:
                error("function_required", "Tools에 공개 함수를 작성해 주세요.", "function")
            elif not isinstance(selected, str) or selected not in names:
                error("function_selection", "작성한 공개 함수 중 사용할 함수를 선택해 주세요.", "function")

    inputs = draft.get("input_ui")
    if not isinstance(inputs, dict):
        error("input_ui_format", "입력 질문의 정의를 확인해 주세요.", "input_ui")
        inputs = {}
    properties = selected_schema["properties"]
    for name in inputs:
        if name not in properties:
            error("input_unknown", "기능에 없는 입력 질문입니다. 기능과 질문을 함께 확인해 주세요.", "input_ui." + str(name))
    for name, schema in properties.items():
        field = "input_ui." + name
        ui = inputs.get(name)
        if not isinstance(ui, dict):
            error("input_ui_missing", "이 입력의 질문과 표시 이름을 정해 주세요.", field)
            continue
        if any(not isinstance(ui.get(key), str) or not ui[key].strip() for key in ("label", "question")):
            error("input_label_required", "입력 이름과 질문 문구를 작성해 주세요.", field)
        shape = schema.get("anyOf", [schema])[0]
        kind = shape.get("type")
        widget = ui.get("widget")
        supported = {"string": {"text", "select"}, "integer": {"number", "select"}, "number": {"number", "select"},
                     "boolean": {"boolean", "select"}, "array": {"multiselect"}}.get(kind, set())
        if not isinstance(widget, str) or widget not in _WIDGETS or widget not in supported:
            error("input_widget_mismatch", "입력 형식에 맞는 입력 방식을 선택해 주세요.", field + ".widget")
        enum = shape.get("items", shape).get("enum")
        labels = ui.get("option_labels", {})
        if not isinstance(labels, dict) or any(not isinstance(value, str) or not value.strip() for value in labels.values()):
            error("input_option_labels", "선택지 표시 이름을 확인해 주세요.", field + ".option_labels")
        elif labels and (enum is None or not set(labels) <= {_option_key(value) for value in enum}):
            error("input_option_unknown", "코드의 허용 값에 없는 선택지입니다. 기능을 수정한 뒤 확인해 주세요.", field + ".option_labels")
        if widget == "select" and enum is None:
            error("input_options_required", "선택 입력의 허용 값을 기능에 Literal로 선언해 주세요.", field + ".widget")
        if "default" in ui and not _matches(ui["default"], schema):
            error("input_default_mismatch", "기본값이 기능의 입력 형식이나 허용 값과 다릅니다.", field + ".default")

    output = draft.get("output_ui")
    if not isinstance(output, dict):
        error("output_ui_format", "결과 표시 항목을 설정해 주세요.", "output_ui")
    else:
        if output.get("kind") != "list":
            error("output_kind", "문서 목록 결과 형식을 선택해 주세요.", "output_ui.kind")
        if not isinstance(output.get("path"), str) or not _PATH.fullmatch(output["path"]):
            error("output_path", "목록의 반환 경로를 확인해 주세요.", "output_ui.path")
        fields = output.get("fields")
        if not isinstance(fields, list) or not fields:
            error("output_fields", "사용자가 볼 결과 항목을 추가해 주세요.", "output_ui.fields")
        else:
            seen = set()
            for index, item in enumerate(fields):
                field = "output_ui.fields." + str(index)
                if not isinstance(item, dict):
                    error("output_field", "결과 항목의 정의를 확인해 주세요.", field)
                    continue
                path = item.get("path")
                if not isinstance(path, str) or not _PATH.fullmatch(path):
                    error("output_field_path", "결과 항목의 반환 경로를 확인해 주세요.", field + ".path")
                elif path in seen:
                    error("output_field_duplicate", "같은 반환 항목이 두 번 연결되어 있습니다.", field + ".path")
                else:
                    seen.add(path)
                if not isinstance(item.get("label"), str) or not item["label"].strip():
                    error("output_field_label", "결과 항목의 표시 이름을 작성해 주세요.", field + ".label")
                if not isinstance(item.get("role"), str) or item.get("role") not in _ROLES or type(item.get("hidden")) is not bool:
                    error("output_field_display", "결과 항목의 역할과 숨김 설정을 확인해 주세요.", field)
    result = {"valid": not errors, "errors": errors, "functions": functions, "input_schema": selected_schema}
    if _json_size(result) > MAX_RESULT_BYTES:
        return limit_result()
    result["input_schema"] = deepcopy(selected_schema)
    return result
