"""Repack the pinned official wheel with reviewed EES branding, without installing it.

Requires only Python's standard library. No network, credentials, runtime data,
dependency resolution, or upstream code execution is involved. Branding use must
meet the upstream license; this builder preserves every bundled license notice.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


UPSTREAM_VERSION = "0.11.3"
VERSION = "0.11.3+ees.8"
PROGRAM_FRONTENDS = {"0.11.3+ees.1": "_ees1", "0.11.3+ees.2": "_ees2", "0.11.3+ees.3": "_ees3", "0.11.3+ees.4": "_ees4", "0.11.3+ees.5": "_ees5", "0.11.3+ees.6": "_ees6", "0.11.3+ees.7": "_ees7", "0.11.3+ees.8": "_ees8"}
SOURCE_FILENAME = "open_webui-0.11.3-py3-none-any.whl"
SOURCE_SHA256 = "8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547"
WHEEL_FILENAME = f"open_webui-{VERSION}-py3-none-any.whl"
SOURCE_INFO = f"open_webui-{UPSTREAM_VERSION}.dist-info/"
TARGET_INFO = f"open_webui-{VERSION}.dist-info/"
SOURCE_APP = "open_webui/frontend/_app/"
TARGET_APP = "open_webui/frontend/_ees8/"
ASSET_DIR = Path(__file__).resolve().parents[1] / "branding" / "ees" / "assets"
UI_DIR = ASSET_DIR.parent / "ui"
ASSET_NAMES = (
    "favicon.svg", "favicon.png", "favicon-96x96.png", "favicon.ico",
    "apple-touch-icon.png", "logo.png", "splash.png", "splash-dark.png",
)
UI_FILES = {"chat-theme.css": "chat-theme.css", "font-licenses.txt": "fonts/LICENSE.txt",
            "ees-work-launcher.js": "ees-work-launcher.js", "ees-work-launcher.css": "ees-work-launcher.css"}
WORK_DIR = ASSET_DIR.parents[2] / "agent-pack" / "skills" / "ees-work-demo"
WORK_ASSETS = {"scripts/ees_work_demo.py": "open_webui/ees_work_demo.py",
               **{"ui/" + name: "open_webui/ees_work_demo_ui/" + name
                  for name in ("index.html", "ees-work.css", "ees-work.js")}}
LEGACY_WORK_FILES = tuple(WORK_ASSETS.values()) + tuple("open_webui/frontend/_ees5/" + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
WORK_ASSETS.update({"scripts/ees_workflow.py": "open_webui/ees_workflow.py",
                    "scripts/workflow_seed.json": "open_webui/workflow_seed.json"})
WORK_BOOTSTRAP = WORK_DIR.parent / "cross-system-analysis" / "ui" / "work-panel.js"
WORK_BOOTSTRAP_TARGET = TARGET_APP + "ees-work-panel.js"
WORK_FILES = (WORK_BOOTSTRAP_TARGET,) + tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
# Copy these already bundled upstream fonts byte-for-byte into the new cache
# namespace; no font download, transformation, or runtime dependency is needed.
FONT_SOURCES = {
    "Inter-Variable.ttf": ("open_webui/frontend/assets/fonts/Inter-Variable.ttf",
                           "cf3cb43b0366e2dc6df60e1132b1c9a4c15777f0cd8e5a53e0c15124003e9ed4"),
    "NotoSansKR-Variable.ttf": ("open_webui/static/fonts/NotoSansKR-Variable.ttf",
                                "2d2267a83d089cb1a517a4f901676d05d283346e650d1b1845d601cbd696a98e"),
}
THEME_FILES = ("chat-theme.css", "fonts/LICENSE.txt") + tuple("fonts/" + name for name in FONT_SOURCES)
THEME_LINK = b'<link rel="stylesheet" href="/_ees8/chat-theme.css" crossorigin="use-credentials" />'
WORK_LINK = (b'<link rel="stylesheet" href="/_ees8/ees-work-launcher.css" />'
             b'<script defer src="/_ees8/ees-work-panel.js"></script>'
             b'<script defer src="/_ees8/ees-work-launcher.js"></script>')

# The pinned Chat component already owns draft serialization, editor updates,
# file/tool selections and debounced native sessionStorage writes. Expose only
# those operations so switching work scopes can flush the last keystroke and
# restore a root-chat draft without reproducing or mutating editor DOM.
# A note/embedded Chat must not replace the main Chat's hook. Its owner removes
# the hook on unmount, and callers wait for the native editor to finish loading.
# Tool approval mode is a user/chat setting, not work-scope draft content. The
# native import applies it through Ci(), which may approve pending tool calls;
# therefore never export, persist or import that field through this hook.
NATIVE_DRAFT_MOUNT = b'ii(()=>{var Ne,Pe,me,Ve,vt;c(ce,!0),window.addEventListener("message",Uo)'
NATIVE_DRAFT_UNMOUNT = b'()=>{var Ie,ct;try{clearTimeout(r(Ii)),sr(),G()&&!g()&&Yi(G()),$(),K(),ie()'
NATIVE_DRAFT_LOAD_DECLARATION = b'let Ii=P();const ro=async()=>{var K,ie;'
NATIVE_DRAFT_LOAD_GUARD = (
    b'let eesNativeDraftLoads=0;const eesNativeDraftLoad=async load=>{'
    b'eesNativeDraftLoads++;try{return await load();}finally{eesNativeDraftLoads--;}};'
)
NATIVE_COMPLETION_CREATE_BEGIN = b'Tt=!ue||g()||la(ue),Ot=await Qm('
NATIVE_COMPLETION_CREATE_END = b'!g()&&!j()&&(window.history.replaceState(r(Ae).state,"",`/c/${Ot.chat_id}`)'
NATIVE_COMPLETION_CAPTURE = (
    b'eesCompletionOwner=window.__eesNativeWorkV1,eesCompletionCreation=(()=>{'
    b'try{return!j()&&!g()?eesCompletionOwner?.beginChatCreation?.():null;}catch{return null;}})(),'
)
NATIVE_COMPLETION_NOTIFY = (
    b'(()=>{try{if(eesCompletionCreation)eesCompletionOwner?.finishChatCreation?.(eesCompletionCreation,Ot.chat_id);}catch{}})(),'
)
NATIVE_CHAT_CREATE_BEGIN = b'kt=async x=>{var ie,ue,Te;let $=d();const K='
NATIVE_CHAT_CREATE_END = b'$=r(Br).id,await xi.set($),j()||window.history.replaceState(x.state,"",`/c/${$}`)'
NATIVE_CHAT_CREATE_CAPTURE = (
    b'let eesCreation=null;const eesWorkOwner=window.__eesNativeWorkV1;'
    b'try{if(!j()&&!g())eesCreation=eesWorkOwner?.beginChatCreation?.();}catch{}'
)
NATIVE_CHAT_CREATE_NOTIFY = (
    b'(()=>{try{if(eesCreation)eesWorkOwner?.finishChatCreation?.(eesCreation,$);}catch{}})(),'
)
NATIVE_DRAFT_HOOK = (
    b'const eesNativeDraftApi={ready:()=>{'
    b'if(j()||g()||r(ce)||!r(le)||eesNativeDraftLoads)return!1;'
    br'const path=window.location.pathname,match=path.match(/^\/c\/([^/]+)\/?$/);'
    b'let expected;try{expected=match?decodeURIComponent(match[1]):path==="/"?"":null;}catch{return!1;}'
    b'return expected!==null&&(G()||"")===expected&&(d()||"")===expected;},'
    b'read:()=>{if(!eesNativeDraftApi.ready())return null;'
    b'const snapshot={...us()};delete snapshot.toolApprovalMode;return snapshot;},'
    b'flush:()=>{const snapshot=eesNativeDraftApi.read();return snapshot?Ps(snapshot,Fr(),!1):!1;},'
    b'restore:async serialized=>{if(!eesNativeDraftApi.ready()||typeof serialized!=="string")return!1;'
    b'let snapshot;try{snapshot=JSON.parse(serialized);'
    b'if(!snapshot||typeof snapshot!=="object"||Array.isArray(snapshot))return!1;'
    b'delete snapshot.toolApprovalMode;}catch{return!1;}'
    b'_r&&clearTimeout(_r);const restored=await qi(JSON.stringify(snapshot));'
    b'if(restored)await eesNativeDraftApi.flush();return restored;}};'
    b'if(!j())window.__eesNativeDraftV1=eesNativeDraftApi;'
)

# Every replacement is pinned to one reviewed upstream file and occurrence count.
# Upstream comments, attribution strings, documentation, and source maps remain.
PATCHES = {
    "open_webui/main.py": [(
        b"if os.path.exists(FRONTEND_BUILD_DIR):",
        b"from open_webui.ees_work_demo import install as install_ees_work_demo\n"
        b"install_ees_work_demo(app, get_verified_user)\n"
        b"from open_webui.ees_workflow import install as install_ees_workflow\n"
        b"install_ees_workflow(app, get_verified_user)\n\n"
        b"if os.path.exists(FRONTEND_BUILD_DIR):", 1,
    )],
    "open_webui/env.py": [(
        b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
        b"if WEBUI_NAME != 'Open WebUI':\n    WEBUI_NAME += ' (Open WebUI)'",
        b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'EES Work')\n"
        b"if WEBUI_NAME in {'EES Assistant', 'EES Portal'}:\n    WEBUI_NAME = 'EES Work'", 1,
    )],
    "open_webui/frontend/index.html": [
        (b"<title>Open WebUI</title>", b"<title>EES Work</title>", 1),
        (b"/_app/", b"/_ees8/", 49),
        (b"</head>", THEME_LINK + WORK_LINK + b"\n\t</head>", 1),
    ],
    SOURCE_APP + "immutable/chunks/CHq18Uto.js": [
        (b'const ca="Open WebUI"', b'const ca="EES Work"', 1),
    ],
    SOURCE_APP + "immutable/nodes/0.CvnwnD8l.js": [
        (b" / Open WebUI`", b" / EES Work`", 3),
    ],
    SOURCE_APP + "immutable/nodes/26.Ck8JdNW5.js": [
        (b" / Open WebUI`", b" / EES Work`", 2),
    ],
    SOURCE_APP + "immutable/chunks/DKj2ZiCb.js": [
        (b"/_app/version.json", b"/_ees8/version.json", 1),
        (b'an="0.11.3"', b'an="0.11.3+ees.8"', 1),
    ],
    SOURCE_APP + "immutable/chunks/zKJlHFgk.js": [
        # Loading may turn its spinner off before native cached drafts finish
        # restoring. Count all overlapping native draft loads in Chat's scope;
        # workflow restoration waits until each completes and route IDs match.
        (NATIVE_DRAFT_LOAD_DECLARATION,
         NATIVE_DRAFT_LOAD_GUARD + b'let Ii=P();const ro=()=>eesNativeDraftLoad(async()=>{var K,ie;', 1),
        (b')):await To("/")},li=async()=>{var x,$;',
         b')):await To("/")}),li=()=>eesNativeDraftLoad(async()=>{var x,$;', 1),
        (b'($=r(le))==null||$.focus({preventScroll:!0})},yo=async x=>',
         b'($=r(le))==null||$.focus({preventScroll:!0})}),yo=async x=>', 1),
        (b',ns=async()=>{var ue,Te,Ne,Pe,me,Ve,vt,Ie,ct,tt,Qe,Pt,_t,ot,Mt,Tt,Ot,It,Dt,lr,Vt,Mr,ss,rr,Lr;',
         b',ns=()=>eesNativeDraftLoad(async()=>{var ue,Te,Ne,Pe,me,Ve,vt,Ie,ct,tt,Qe,Pt,_t,ot,Mt,Tt,Ot,It,Dt,lr,Vt,Mr,ss,rr,Lr;', 1),
        (b'(Lr=r(le))==null||Lr.focus({preventScroll:!0})},ts=async()=>',
         b'(Lr=r(le))==null||Lr.focus({preventScroll:!0})}),ts=async()=>', 1),
        (b'return(async()=>{var Ie,ct;G()||(c(ce,!1),await Ft()),ue&&',
         b'return eesNativeDraftLoad(async()=>{var Ie,ct;G()||(c(ce,!1),await Ft()),ue&&', 1),
        (b'(ct=r(le))==null||ct.focus({preventScroll:!0})})(),()=>{var Ie,ct;try{',
         b'(ct=r(le))==null||ct.focus({preventScroll:!0})}),()=>{var Ie,ct;try{', 1),
        (NATIVE_DRAFT_MOUNT,
         b'ii(()=>{var Ne,Pe,me,Ve,vt;' + NATIVE_DRAFT_HOOK +
         b'c(ce,!0),window.addEventListener("message",Uo)', 1),
        (NATIVE_DRAFT_UNMOUNT,
         b'()=>{var Ie,ct;if(window.__eesNativeDraftV1===eesNativeDraftApi)delete window.__eesNativeDraftV1;'
         b'try{clearTimeout(r(Ii)),sr(),G()&&!g()&&Yi(G()),$(),K(),ie()', 1),
        # Only the main Chat's first successful server creation can bind a work
        # case. A submit gesture or an unrelated API chat import is not proof.
        (NATIVE_CHAT_CREATE_BEGIN,
         b'kt=async x=>{var ie,ue,Te;let $=d();' + NATIVE_CHAT_CREATE_CAPTURE + b'const K=', 1),
        (NATIVE_CHAT_CREATE_END,
         b'$=r(Br).id,' + NATIVE_CHAT_CREATE_NOTIFY +
         b'await xi.set($),j()||window.history.replaceState(x.state,"",`/c/${$}`)', 1),
        # Normal first prompts create their chat through the completions API;
        # kt above covers the native explicit-message creation path as well.
        (NATIVE_COMPLETION_CREATE_BEGIN,
         b'Tt=!ue||g()||la(ue),' + NATIVE_COMPLETION_CAPTURE + b'Ot=await Qm(', 1),
        (NATIVE_COMPLETION_CREATE_END,
         b'!g()&&!j()&&(' + NATIVE_COMPLETION_NOTIFY +
         b'window.history.replaceState(r(Ae).state,"",`/c/${Ot.chat_id}`)', 1),
    ],
    SOURCE_APP + "version.json": [
        (b'{"version":"0.11.3"}', b'{"version":"0.11.3+ees.8"}', 1),
    ],
    SOURCE_INFO + "METADATA": [
        (b"\nVersion: 0.11.3\n", b"\nVersion: 0.11.3+ees.8\n", 1),
    ],
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_name(name):
    if name.startswith(SOURCE_INFO):
        return TARGET_INFO + name[len(SOURCE_INFO):]
    if name.startswith(SOURCE_APP):
        return TARGET_APP + name[len(SOURCE_APP):]
    return name


def prepare_replacements(source, asset_dir):
    """Validate every precondition before creating any output file."""
    names = source.namelist()
    if len(names) != len(set(names)):
        raise ValueError("The source wheel contains duplicate entries.")
    targets = [target_name(name) for name in names]
    if len(targets) != len(set(targets)):
        raise ValueError("The target wheel would contain duplicate entries.")
    if any(name.endswith(("/RECORD.jws", "/RECORD.p7s")) for name in names):
        raise ValueError("Signed wheels cannot be repacked by this builder.")
    required = set(PATCHES) | {SOURCE_INFO + "RECORD", SOURCE_INFO + "WHEEL"}
    asset_targets = {
        prefix + name: name
        for prefix in ("open_webui/static/", "open_webui/frontend/static/")
        for name in ASSET_NAMES
    }
    asset_targets["open_webui/frontend/favicon.png"] = "favicon.png"
    required.update(asset_targets)
    missing = required - set(names)
    if missing:
        raise ValueError("Missing wheel entries: " + ", ".join(sorted(missing)))

    replacements = {}
    for name, patches in PATCHES.items():
        content = source.read(name)
        for old, new, expected in patches:
            actual = content.count(old)
            if actual != expected:
                raise ValueError(f"Patch precondition failed: {name}: expected {expected}, got {actual}.")
            content = content.replace(old, new)
        replacements[name] = content
    assets = {}
    for name in ASSET_NAMES:
        path = Path(asset_dir) / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty branding asset: {name}")
        assets[name] = path.read_bytes()
    replacements.update({name: assets[asset] for name, asset in asset_targets.items()})
    return replacements


def zip_entry(name, attributes=0o100644 << 16):
    entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = attributes
    entry.compress_type = ZIP_DEFLATED
    return entry


def prepare_additions(source, ui_dir, work_dir=WORK_DIR):
    additions = {}
    for filename, relative in UI_FILES.items():
        path = Path(ui_dir) / filename
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing, empty, or linked EES UI asset: {filename}")
        additions[TARGET_APP + relative] = path.read_bytes()
    for relative, target in WORK_ASSETS.items():
        path = Path(work_dir) / relative
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing, empty, or linked EES Work asset: {relative}")
        additions[target] = path.read_bytes()
    if WORK_BOOTSTRAP.is_symlink() or not WORK_BOOTSTRAP.is_file():
        raise ValueError("Missing EES work panel bootstrap.")
    additions[WORK_BOOTSTRAP_TARGET] = WORK_BOOTSTRAP.read_bytes()
    for filename, (origin, expected) in FONT_SOURCES.items():
        if origin not in source.namelist():
            raise ValueError(f"Missing pinned upstream font: {filename}")
        content = source.read(origin)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Pinned upstream font hash differs: {filename}")
        additions[TARGET_APP + "fonts/" + filename] = content
    if set(additions) & {target_name(name) for name in source.namelist()}:
        raise ValueError("The source wheel already contains an EES UI target.")
    return additions


def build(wheel, output_dir, asset_dir=ASSET_DIR, ui_dir=UI_DIR):
    wheel, output_dir = Path(wheel), Path(output_dir)
    if wheel.name != SOURCE_FILENAME or sha256_file(wheel) != SOURCE_SHA256:
        raise ValueError("Expected the unchanged, pinned official Open WebUI 0.11.3 wheel.")
    wheel_target = output_dir / WHEEL_FILENAME
    manifest_target = output_dir / "manifest.json"
    if any(path.exists() or path.is_symlink() for path in (wheel_target, manifest_target)):
        raise ValueError("Output already exists; choose an empty release destination.")

    with ZipFile(wheel) as source:
        replacements = prepare_replacements(source, asset_dir)
        additions = prepare_additions(source, ui_dir)
        entries = sorted(source.infolist(), key=lambda entry: target_name(entry.filename))
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ees-build-", dir=output_dir) as temporary:
            built = Path(temporary) / WHEEL_FILENAME
            record = []
            with ZipFile(built, "w", compression=ZIP_DEFLATED, compresslevel=6) as destination:
                for entry in entries:
                    if entry.filename == SOURCE_INFO + "RECORD":
                        continue
                    name = target_name(entry.filename)
                    content = replacements.get(entry.filename)
                    if content is None:
                        content = source.read(entry)
                    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                    destination.writestr(zip_entry(name, entry.external_attr), content, compresslevel=6)
                    record.append((name, "sha256=" + digest, str(len(content))))
                for name, content in sorted(additions.items()):
                    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                    destination.writestr(zip_entry(name), content, compresslevel=6)
                    record.append((name, "sha256=" + digest, str(len(content))))
                record_name = TARGET_INFO + "RECORD"
                record.append((record_name, "", ""))
                csv_text = io.StringIO(newline="")
                csv.writer(csv_text, lineterminator="\n").writerows(record)
                destination.writestr(zip_entry(record_name), csv_text.getvalue().encode(), compresslevel=6)

            manifest = {
                "schema_version": 1,
                "upstream_version": UPSTREAM_VERSION,
                "version": VERSION,
                "source": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256},
                "wheel": {"filename": WHEEL_FILENAME, "sha256": sha256_file(built), "size": built.stat().st_size},
                "changed_files": sorted([target_name(name) for name in replacements] + list(additions) + [record_name]),
                "relocated_frontend": {
                    "from": SOURCE_APP, "to": TARGET_APP,
                    "file_count": sum(entry.filename.startswith(SOURCE_APP) for entry in entries),
                },
            }
            manifest_file = Path(temporary) / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            # Hard links publish complete files without overwriting a racing build.
            os.link(built, wheel_target)
            try:
                os.link(manifest_file, manifest_target)
            except OSError:
                wheel_target.unlink()
                raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = build(args.wheel, args.output_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build stopped: {error}\n")
    print(f"Prepared {manifest['wheel']['filename']}")
    print(f"SHA256={manifest['wheel']['sha256']}")
    print("No runtime installation or server changes were performed.")


if __name__ == "__main__":
    main()
