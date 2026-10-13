"""Source build provenance and Native draft/creation preservation boundaries."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts import build_ees_frontend as frontend


def _added_source():
    config = frontend.configuration()
    return "\n".join(line[1:] for entry in config["patches"]
                     for line in (frontend.SOURCE_CONFIG.parent / entry["path"]).read_text(encoding="utf-8").splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


def _between(text, start, end):
    at = text.index(start)
    return text[at:text.index(end, at)]


def _hook_source():
    added = _added_source()
    load = _between(added, "let eesNativeDraftLoads = 0;", "const eesNativeDraftApi =")
    # Added unrelated hunks can precede the complete hook; the load helper ends
    # at its first closing semicolon and has no dependency on generated names.
    load = load[:load.index("\n\t};") + len("\n\t};")]
    hook = _between(added, "const eesNativeDraftApi =", "if (!embedded) window.__eesNativeDraftV1 = eesNativeDraftApi;")
    hook += "if (!embedded) window.__eesNativeDraftV1 = eesNativeDraftApi;"
    return (load + "\n" + hook).replace("(message: any)", "(message)")


@unittest.skipUnless(shutil.which("node"), "Node is required for Native source probes.")
class NativeDraftHookTests(unittest.TestCase):
    def run_node(self, source):
        result = subprocess.run([shutil.which("node"), "-e", source], capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_exact_source_hook_preserves_approval_and_waits_for_all_native_loads(self):
        probe = r'''
const assert = require('node:assert/strict');
let current = {prompt:'original',selectedToolIds:['existing'],toolApprovalMode:'ask'};
let approvalCalls=0, imported=[], persisted=[], saveDraftTimeout=null;
let embedded=false,$temporaryChatEnabled=false,loading=false,messageInput={},chatIdProp='', $chatId='';
let prompt='',files=[];
const history={messages:{u:{id:'u',role:'user'},a:{id:'a',role:'assistant'}}};
const window={location:{pathname:'/'}};
const getChatInputDraft=()=>current, getDraftChatId=()=>'native-chat';
const saveDraft=async(draft,chatId,debounce)=>persisted.push({draft,chatId,debounce});
const restoreChatInput=async serialized=>{
  const incoming=JSON.parse(serialized);imported.push(incoming);
  if(incoming.toolApprovalMode){approvalCalls++;current.toolApprovalMode=incoming.toolApprovalMode;}
  current={...current,...incoming};return true;
};
''' + _hook_source() + r'''
(async()=>{
 const hook=window.__eesNativeDraftV1;
 let finishFirst,finishSecond;
 const first=eesNativeDraftLoad(()=>new Promise(resolve=>finishFirst=resolve));
 const second=eesNativeDraftLoad(()=>new Promise(resolve=>finishSecond=resolve));
 assert.equal(hook.ready(),false);finishFirst();await first;assert.equal(hook.ready(),false);
 finishSecond();await second;assert.equal(hook.ready(),true);
 await assert.rejects( eesNativeDraftLoad(async()=>{throw Error('failed native load');}),/failed native load/);
 assert.equal(hook.ready(),true,'Rejected native loads also release only their own count');
 assert.deepEqual(hook.workMessageIds(),['a']);
 window.location.pathname='/c/other';assert.equal(hook.ready(),false);assert.deepEqual(hook.workMessageIds(),[]);
 chatIdProp='other';$chatId='other';assert.equal(hook.ready(),true);
 loading=true;assert.equal(hook.ready(),false);loading=false;
 window.location.pathname='/';chatIdProp='';$chatId='';
 assert.equal(Object.hasOwn(hook.read(),'toolApprovalMode'),false);
 await hook.flush();
 assert.equal(await hook.restore(JSON.stringify({prompt:'restored',selectedToolIds:['kept'],toolApprovalMode:'full'})),true);
 assert.equal(current.prompt,'restored');assert.deepEqual(current.selectedToolIds,['kept']);
 assert.equal(current.toolApprovalMode,'ask');assert.equal(approvalCalls,0);
 assert.equal(imported.length,1);assert.equal(Object.hasOwn(imported[0],'toolApprovalMode'),false);
 assert.equal(persisted.length,2);
 assert.equal(persisted.every(x=>!Object.hasOwn(x.draft,'toolApprovalMode')&&x.chatId==='native-chat'&&x.debounce===false),true);
 for(const invalid of ['{','null','[]','"text"','false'])assert.equal(await hook.restore(invalid),false);
 assert.equal(imported.length,1);
 prompt='live keystroke';assert.equal(hook.hasPendingContent(),true);
 prompt='';files=[{id:'pending-upload'}];assert.equal(hook.hasPendingContent(),true);
 files=[];assert.equal(hook.hasPendingContent(),false);
 embedded=true;assert.equal(hook.ready(),false);embedded=false;
 $temporaryChatEnabled=true;assert.equal(hook.ready(),false);
 console.log('native_source_draft=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "native_source_draft=pass")

    def test_source_owner_cleanup_and_all_four_load_boundaries_are_present(self):
        source = _added_source()
        self.assertIn("if (window.__eesNativeDraftV1 === eesNativeDraftApi) delete window.__eesNativeDraftV1", source)
        for name in ("navigateHandler", "initEmbeddedDraft", "initNewChat", "init"):
            self.assertIn("const " + name + " = () => eesNativeDraftLoad(async () => {", source)


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR") and shutil.which("node"),
                     "The CI patched source checkout is required for full Native function probes.")
class NativeSourceHookTests(unittest.TestCase):
    run_node = NativeDraftHookTests.run_node
    def test_real_native_restore_creation_and_late_completion_boundaries(self):
        source = (Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]) /
                  "src/lib/components/chat/Chat.svelte").read_text(encoding="utf-8")
        restore = _between(source, "const restoreChatInput =", "\n\tconst withSelectedText")
        restore = restore.replace("storageChatInput: string | null", "storageChatInput")
        draft = _between(source, "const getChatInputDraft =", "\n\tconst saveDraft =")
        create = _between(source, "const initChatHandler =", "\n\tconst saveChatHandler =")
        capture = _between(source, "const eesCompletionOwner =", "\n\t\tconst res = await generateOpenAIChatCompletion")
        response_at = source.index("\n\t\tif (res) {", source.index("const eesCompletionOwner ="))
        response = source[response_at:source.index("\n\t};\n\n\tconst handleOpenAIError", response_at)]
        completion = "const probeCompletion=async response=>{const _chatId=$chatId,responseMessage={};" + capture + "\nconst res=await response;" + response + "};"
        reference = _between(source, "user_message: userMessage ? {", "\n\t\t\t\t...(regenerationPrompt")
        reference = "const referenceMessage=(_chatId,responseMessageId,userMessage)=>({" + reference + "});"
        probe = r'''
const assert=require('node:assert/strict');
let embedded=false,$temporaryChatEnabled=false,$chatId='',chatIdProp='',loading=false,prompt='',files=[];
let selectedToolIds=[],selectedSkillIds=[],selectedFilterIds=[],webSearchEnabled=false,imageGenerationEnabled=false,codeInterpreterEnabled=false,toolApprovalMode='ask';
let chat=null,approvalCalls=0,failCreation=false,beginCalls=0,saveDraftTimeout=null,loadedChatIdProp='';
const notifications=[],persisted=[],selectedModels=['model'],params={},chatVariables={},$settings={},$socket={id:'socket'};
const $selectedFolder=null,$i18n={t:x=>x};
const messageInput={setText(value){prompt=value;}},history={messages:{}};
const localStorage={token:'synthetic'};
const handleToolApprovalModeChange=async value=>{approvalCalls++;toolApprovalMode=value;};
const chatId={set:async value=>{$chatId=value;chatIdProp=value;}},selectedFolder={set(){}},tick=async()=>{};
const refreshChatList=async()=>{},refreshFolderChatLists=async()=>{},createMessagesList=()=>[],createTemporaryChatId=()=> 'temporary';
const getDraftChatId=()=>chatIdProp||null,saveDraft=async(value)=>persisted.push(value);
const chatRequestQueues={update:callback=>callback({})},onToolCallResolved=()=>{},handleOpenAIError=async()=>{},updateChatById=async()=>{};
const shouldAutoScrollResponse=()=>false,scrollToBottom=()=>{};
const window={location:{pathname:'/'},history:{replaceState(state,title,path){window.location.pathname=path;}},__eesNativeWorkV1:{
 beginChatCreation(){if(window.location.pathname!=='/')return null;return {sequence:++beginCalls};},
 finishChatCreation(ticket,id){notifications.push({ticket,id});},
 captureReference(){return {kind:'work',workflow_id:'captured-work'};}
}};
const createNewChat=async()=>{if(failCreation)throw Error('synthetic creation failure');return {id:'server-created'};};
''' + restore + draft + create + completion + reference + _hook_source() + r'''
(async()=>{
 assert.equal(await window.__eesNativeDraftV1.restore(JSON.stringify({prompt:'restored',selectedToolIds:['kept'],toolApprovalMode:'full'})),true);
 assert.equal(prompt,'restored');assert.deepEqual(selectedToolIds,['kept']);assert.equal(toolApprovalMode,'ask');assert.equal(approvalCalls,0);
 files=[{type:'image',url:'private-image'},{type:'file',id:'doc',user:{private:true},access_grants:['private']}];
 const snapshot=window.__eesNativeDraftV1.read();assert.equal(snapshot.files.length,1);assert.equal(snapshot.files[0].user,undefined);
 assert.equal(snapshot.files[0].access_grants,undefined);assert.equal(Object.hasOwn(snapshot,'toolApprovalMode'),false);
 $chatId='provisional';failCreation=true;await assert.rejects(initChatHandler({state:{}}),/synthetic creation failure/);
 assert.equal(notifications.length,0);failCreation=false;await initChatHandler({state:{}});
 assert.equal(notifications.length,1);assert.equal(notifications[0].id,'server-created');
 await initChatHandler({state:{}});assert.equal(notifications.length,1);
 $chatId='';$temporaryChatEnabled=true;await initChatHandler({state:{}});assert.equal(notifications.length,1);
 $temporaryChatEnabled=false;embedded=true;await initChatHandler({state:{}});assert.equal(notifications.length,1);
 embedded=false;$chatId='provisional2';window.location.pathname='/';await probeCompletion({chat_id:'completion-created'});
 assert.equal(notifications.length,2);assert.equal(notifications[1].id,'completion-created');
 $chatId='provisional3';window.location.pathname='/';await probeCompletion({error:'failed',chat_id:'must-not-bind'});await probeCompletion(null);
 assert.equal(notifications.length,2);$temporaryChatEnabled=true;await probeCompletion({chat_id:'temporary'});
 $temporaryChatEnabled=false;embedded=true;await probeCompletion({chat_id:'embedded'});assert.equal(notifications.length,2);
 embedded=false;$chatId='provisional4';window.location.pathname='/';let finish;
 const pending=probeCompletion(new Promise(resolve=>finish=resolve));$chatId='other';window.location.pathname='/c/other';
 finish({chat_id:'late-result'});await pending;assert.equal(notifications.length,2);
 // Native creation must update the source route and loaded prop together,
 // without the linked-chat loader resetting the live composer.
 embedded=false;$temporaryChatEnabled=false;$chatId='provisional5';chatIdProp='';loadedChatIdProp='';window.location.pathname='/';
 let adopted=0;
 window.__eesSourceShellV1={adoptChat:async id=>{assert.equal(loadedChatIdProp,id);adopted++;chatIdProp=id;window.location.pathname='/c/'+id;}};
 files=[{type:'image',url:'live-image'}];prompt='keep draft';
 await initChatHandler({state:{}});assert.equal(adopted,1);assert.equal(window.__eesNativeDraftV1.ready(),true);
 assert.equal(files[0].url,'live-image');assert.equal(prompt,'keep draft');
 $chatId='provisional6';chatIdProp='';loadedChatIdProp='';window.location.pathname='/';
 await probeCompletion({chat_id:'second-created'});assert.equal(adopted,2);assert.equal(window.__eesNativeDraftV1.ready(),true);
 const original={id:'message',meta:{kept:true}};const recorded=referenceMessage('chat','response',original).user_message;
 window.__eesNativeWorkV1.captureReference=()=>({kind:'work',workflow_id:'later-work'});
 assert.equal(recorded.meta.ees_work_reference.workflow_id,'captured-work');assert.equal(recorded.meta.kept,true);
 assert.equal(original.meta.ees_work_reference,undefined);embedded=true;
 assert.deepEqual(referenceMessage('chat','response',original).user_message.meta.ees_work_reference,{kind:'none'});
 console.log('native_source_functions=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "native_source_functions=pass")


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR"),
                     "The CI patched source checkout is required for source comparison.")
class SourcePatchTests(unittest.TestCase):
    def test_layout_hooks_preserve_native_elements_and_reject_source_drift(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"])
        config = frontend.configuration()
        for name in ("src/app.html", "src/lib/constants.ts", "src/routes/+layout.svelte",
                     "src/lib/components/channel/Channel.svelte"):
            current = (root / name).read_text(encoding="utf-8")
            self.assertIn("EES Workflow", current, name)
            self.assertNotRegex(current, r"EES Work(?!flow)", name)
        # Stage 2 owns layout in source. Preserve Native input and action
        # implementations, not the old greeting/toolbar geometry or DOM hooks.
        for name, pattern in (
            ("src/lib/components/chat/Placeholder.svelte", rb"<MessageInput\b[\s\S]*?\n\s*/>"),
            ("src/lib/components/chat/Navbar.svelte", rb"<Menu\b[\s\S]*?</Menu>"),
        ):
            original = subprocess.check_output(["git", "show", config["commit"] + ":" + name], cwd=root)
            current = (root / name).read_bytes()
            self.assertEqual(re.search(pattern, current).group(), re.search(pattern, original).group(), name)
        shell = (root / "src/lib/components/ees/EesShell.svelte").read_text(encoding="utf-8")
        for marker in ("data-ees-source-shell", "data-ees-source-slot", "hidden={nativeRoute || !folderReady}", "inert={nativeRoute || !folderReady}"):
            self.assertIn(marker, shell)
        self.assertIn("<Chat chatIdProp={retainedChatId}", shell)
        for name in ("src/routes/(app)/+page.svelte", "src/routes/(app)/c/[id]/+page.svelte", "src/routes/(app)/folders/[folderId]/+page.svelte"):
            self.assertNotIn("<Chat", (root / name).read_text(encoding="utf-8"))
        # The newly exported R7 icon is a Vite source input, so prior installed
        # program/Restore asset inventories do not change.
        icon_name = "src/lib/components/ees/icons/5bc95.svg"
        icon = (root / icon_name).read_bytes()
        self.assertTrue(icon.startswith(b"<svg"))
        self.assertEqual(frontend._sha(icon), "3768ff838f3b7cf08a02413d1cca7a7e3d330e42303398a379eec0043ab149d7")
        self.assertEqual(config["patched_files"][icon_name], frontend._sha(icon))
        self.assertNotIn(icon_name, config["source_files"])
        self.assertIn("import connectionsIcon from './icons/5bc95.svg'", (root / "src/lib/components/ees/EesIcon.svelte").read_text(encoding="utf-8"))
        app = (root / "src/app.html").read_text(encoding="utf-8")
        self.assertNotIn("ees-startup-gate", app)
        for name in ("src/lib/components/ees/EesShell.svelte", "src/lib/components/ees/EesNavigation.svelte"):
            self.assertNotIn("MutationObserver", (root / name).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "src/app.html"
            path.parent.mkdir()
            path.write_text("modified source", encoding="utf-8")
            check = {**config, "source_files": {"src/app.html": config["source_files"]["src/app.html"]},
                     "license_files": {}}
            with patch.object(frontend, "_run", side_effect=[config["commit"], ""]):
                with self.assertRaisesRegex(ValueError, "source file differs"):
                    frontend._verify_source(Path(temporary), check)


class FrontendProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.config = frontend.configuration()
        self.config = {**self.config, "pyodide_files": {"fixture.js": frontend._sha(b"pinned pyodide")}}
        config_patch = patch.object(frontend, "configuration", return_value=self.config)
        config_patch.start()
        self.addCleanup(config_patch.stop)
        app = self.config["app_dir"]
        self.files = {"index.html": b"<html>source built</html>", "pyodide/fixture.js": b"pinned pyodide",
                      app + "/version.json": json.dumps({"version": self.config["version"]}).encode("utf-8"),
                      app + "/immutable/entry/start.js": b"__eesNativeDraftV1 __eesNativeWorkV1 ees_work_reference beginChatCreation finishChatCreation __eesSourceShellV1 data-ees-source-sidebar data-ees-source-shell"}
        for name, content in self.files.items():
            path = self.build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.manifest = {"schema": 1, "mode": "ees", "upstream_commit": self.config["commit"],
                         "lock_sha256": self.config["lock_sha256"], "license_sha256": self.config["license_sha256"],
                         "version": self.config["version"], "app_dir": app,
                         "node": self.config["node"], "npm": self.config["npm"],
                         "source_inputs": frontend._source_inputs(), "source_files": self.config["patched_files"],
                         "compiled_source_files": self.config["patched_files"],
                         "compiler_environment": {"npm_package_version": "0.11.3"},
                         "pyodide_files": self.config["pyodide_files"],
                         "files": frontend._digest_map(self.files)}
        self.save()

    def save(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_validated_payload_is_exact_and_rejects_added_missing_or_altered_files(self):
        self.assertEqual(frontend.validate_frontend(self.root), self.files)
        for mutation in ("altered", "missing", "extra"):
            with self.subTest(mutation=mutation):
                path = self.build / "index.html"
                if mutation == "altered":
                    path.write_bytes(b"changed")
                elif mutation == "missing":
                    path.unlink()
                else:
                    (self.build / "injected.js").write_bytes(b"extra")
                with self.assertRaisesRegex(ValueError, "inventory or hash"):
                    frontend.validate_frontend(self.root)
                path.write_bytes(self.files["index.html"])

    def test_mismatched_source_lock_patch_version_or_mode_is_rejected(self):
        for key in ("mode", "upstream_commit", "lock_sha256", "version", "source_files"):
            with self.subTest(key=key):
                original = self.manifest[key]
                self.manifest[key] = "wrong"
                self.save()
                with self.assertRaisesRegex(ValueError, "provenance"):
                    frontend.validate_frontend(self.root)
                self.manifest[key] = original
        self.manifest["source_inputs"] = {}
        self.save()
        with self.assertRaisesRegex(ValueError, "inputs differ"):
            frontend.validate_frontend(self.root)

    def test_forged_rehash_cannot_hide_missing_native_hooks_or_old_namespace(self):
        name = self.config["app_dir"] + "/immutable/entry/start.js"
        self.files[name] = b"unrelated runtime"
        (self.build / name).write_bytes(self.files[name])
        self.manifest["files"] = frontend._digest_map(self.files)
        self.save()
        with self.assertRaisesRegex(ValueError, "Native integration hook"):
            frontend.validate_frontend(self.root)

    def test_rehash_cannot_hide_pyodide_or_compiled_source_drift(self):
        name = "pyodide/fixture.js"
        self.files[name] = b"moving downloaded dependency"
        (self.build / name).write_bytes(self.files[name])
        self.manifest["files"] = frontend._digest_map(self.files)
        self.save()
        with self.assertRaisesRegex(ValueError, "Pyodide payload"):
            frontend.validate_frontend(self.root)
        self.manifest["compiled_source_files"] = {}
        self.save()
        with self.assertRaisesRegex(ValueError, "source fingerprints"):
            frontend.validate_frontend(self.root)

    def test_program_version_keeps_existing_apply_and_restore_contract(self):
        name = self.config["app_dir"] + "/version.json"
        self.files[name] = json.dumps({"version": self.config["version"] + ".unexpected-revision"}).encode("utf-8")
        (self.build / name).write_bytes(self.files[name])
        self.manifest["files"] = frontend._digest_map(self.files)
        self.save()
        with self.assertRaisesRegex(ValueError, "Apply/Restore contract"):
            frontend.validate_frontend(self.root)

    def test_manifest_duplicate_keys_and_symlinked_build_content_are_rejected(self):
        path = self.root / "manifest.json"
        path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            frontend.validate_frontend(self.root)
        self.save()
        target = self.root / "outside.js"
        target.write_bytes(b"outside")
        try:
            (self.build / "linked.js").symlink_to(target)
        except OSError:
            self.skipTest("Creating symlinks is not permitted in this environment.")
        with self.assertRaisesRegex(ValueError, "Linked"):
            frontend.validate_frontend(self.root)

    def test_unsafe_archive_names_are_rejected(self):
        for name in ("../outside", "/absolute", "a/../b", "a\\b", "C:/file", "a//b"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe"):
                frontend._relative(name)

    def test_dirty_source_is_refused_before_any_build_or_output(self):
        with patch.object(frontend, "_run", side_effect=[self.config["commit"], " M src/app.html"]):
            with self.assertRaisesRegex(ValueError, "not clean"):
                frontend._verify_source(self.root, self.config)


class FrontendManifestBudgetTests(unittest.TestCase):
    def test_manifest_exact_limit_keeps_all_hashes_and_overflow_preserves_build(self):
        from scripts import ees_deploy_release as release
        self.assertEqual(frontend.MAX_MANIFEST_BYTES, release.MAX_JSON_BYTES)
        self.assertEqual(frontend.MAX_MANIFEST_BYTES, 1024 * 1024)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "package.json").write_text('{"version":"0.11.3"}', encoding="utf-8")
            added_source = source / "NewShell.svelte"
            added_source.write_bytes(b"<main>source component</main>")
            lock = source / "static/pyodide/pyodide-lock.json"
            lock.parent.mkdir(parents=True)
            lock.write_bytes(b"{}")
            inputs = {"synthetic-budget-input": "x" * 1000000}
            config = {**frontend.configuration(), "source_files": {"package.json": "f" * 64},
                      "patched_files": {"package.json": "f" * 64, "NewShell.svelte": frontend._sha(added_source.read_bytes())},
                      "pyodide_files": {}}

            def build(label, *, source_drift=False):
                # Isolate manifest publication; compiler/provenance behavior is
                # covered by the actual source CI and adjacent validator tests.
                (source / "build").mkdir()
                (source / "build/index.html").write_bytes(b"synthetic compiled bytes")
                with (patch.object(frontend, "configuration", return_value=config),
                      patch.object(frontend, "_verify_source"),
                      patch.object(frontend, "_source_inputs", side_effect=lambda *_: dict(inputs)),
                      patch.object(frontend, "_copy_official_pyodide", return_value=({}, b"{}")),
                      patch.object(frontend, "_apply_ees"),
                      patch.object(frontend, "_run", side_effect=lambda *_args, **_kwargs:
                                   added_source.write_bytes(b"unreviewed source drift") if source_drift else None),
                      patch.object(frontend, "_verify_output"), patch.object(frontend, "validate_frontend")):
                    return frontend.build(source, root / "fixture.whl", root / label)

            measured = build("measure")
            size = (root / "measure/manifest.json").stat().st_size
            inputs["synthetic-budget-input"] += "x" * (frontend.MAX_MANIFEST_BYTES - size)
            expected = build("boundary")
            raw = (root / "boundary/manifest.json").read_bytes()
            self.assertEqual(len(raw), frontend.MAX_MANIFEST_BYTES)
            self.assertEqual(release._json(raw), expected)
            self.assertEqual(expected["files"], measured["files"])
            self.assertEqual(expected["source_inputs"], inputs)
            self.assertEqual(set(expected["compiled_source_files"]), set(config["patched_files"]))
            self.assertEqual(expected["compiled_source_files"]["NewShell.svelte"], config["patched_files"]["NewShell.svelte"])
            inputs["synthetic-budget-input"] += "x"
            with self.assertRaisesRegex(ValueError, "Frontend manifest exceeds"):
                build("over")
            self.assertFalse((root / "over").exists())
            self.assertEqual((source / "build/index.html").read_bytes(), b"synthetic compiled bytes")
            shutil.rmtree(source / "build")
            with self.assertRaisesRegex(ValueError, "inputs changed while building"):
                build("source-drift", source_drift=True)
            self.assertFalse((root / "source-drift").exists())


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR") and shutil.which("node"),
                     "The CI patched source checkout is required for source lifecycle probes.")
class SourceShellLifecycleTests(unittest.TestCase):
    run_node = NativeDraftHookTests.run_node

    def test_pending_native_draft_callbacks_cannot_cross_account_or_destroyed_owner(self):
        source = (Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]) /
                  "src/lib/components/chat/Chat.svelte").read_text(encoding="utf-8")
        lifecycle = _between(source, "const eesDraftOwner =", "\n\tconst oauthRedirectHandler")
        clear = _between(source, "const clearDraft =", "\n\tconst moveChatHandler")
        code = (lifecycle + clear).replace("let saveDraftTimeout: ReturnType<typeof setTimeout> | null", "let saveDraftTimeout")
        code = code.replace("draft: any", "draft").replace("chatId: string | null", "chatId")
        probe = r'''
const assert=require('node:assert/strict');
let $user={id:'first'}, cleanup, next=1;
const timers=new Map(), cancelled=[];
const setTimeout=callback=>{const id=next++;timers.set(id,callback);return id;};
const clearTimeout=id=>cancelled.push(id);
const onDestroy=callback=>cleanup=callback;
const values=new Map([['unrelated','preserved']]);
const sessionStorage={setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
''' + code + r'''
(async()=>{
 await saveDraft({prompt:'first'},null,true);timers.get(1)();
 assert.equal(JSON.parse(values.get('chat-input')).prompt,'first');
 await saveDraft({prompt:'late old draft'},null,true);
 $user={id:'second'};values.set('chat-input','new account draft');
 timers.get(2)();assert.equal(values.get('chat-input'),'new account draft');
 await saveDraft({prompt:'x'.repeat(5001)},null,false);
 assert.equal(values.get('chat-input'),'new account draft','Old oversized draft must not delete the next account draft');
 await clearDraft();assert.equal(values.get('chat-input'),'new account draft');
 $user={id:'first'};cleanup();
 await saveDraft({prompt:'destroyed'},null,false);
 await clearDraft();assert.equal(values.get('chat-input'),'new account draft');
 assert.equal(values.get('unrelated'),'preserved');assert.equal(cancelled.length>0,true);
 console.log('native_draft_owner=pass');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "native_draft_owner=pass")


    def test_source_chat_route_creation_folder_return_and_same_chat_reopen(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"])
        shell = (root / "src/lib/components/ees/EesShell.svelte").read_text(encoding="utf-8")
        chat = (root / "src/lib/components/chat/Chat.svelte").read_text(encoding="utf-8")
        bridge = _between(shell, "const bridge = {", "\n\tif (typeof window")
        reset = _between(chat, "const initNewChat = () => eesNativeDraftLoad(async () => {", "\n\t\tconsole.log('initNewChat')") + "\n});"
        linked = _between(chat, "$: if (chatIdProp && chatIdProp !== loadedChatIdProp)", "\n\t$: if (embedded")
        probe = r"""
const assert=require('node:assert/strict');
let nativeRoute=false,admin=false,chatRoute=true,folderReady=true,retainedChatId='old',lastChatPath='/c/old';
let activeId='new',chatIdProp='old',loadedChatIdProp='old',embedded=false,loads=0;
let panel={},overlays={},eesRequest=()=>{},user={id:'actor'},selectedFolder={id:'folder-a',set() {}};
const get=value=>value,eesSnapshot={set(){}},eesCompact={set(){}},showSettings={set(){}},showSearch={set(){}},eesReferenceHosts=new Map();
const window={__eesNativeDraftV1:{activeChatId:()=>activeId,ready:()=>true},__eesNativeWorkV1:{chatCreated:id=>created.push(id)}};
const created=[],navigations=[],$page={url:{pathname:'/c/old'}};
const location={pathname:'/c/old',search:''};
const tick=async()=>{},eesSync=()=>{},navigate=()=>{},newChat=()=>{},noteChatDebug=()=>{};
const eesNativeDraftLoad=async fn=>fn(),navigateHandler=()=>{loads++;};
const goto=async(path,options)=>{navigations.push({path,options});location.pathname=path;$page.url.pathname=path;chatIdProp=path.startsWith('/c/')?path.slice(3):'';};
""" + bridge + reset + "\nconst linkedUpdate=()=>{" + linked.replace("$: ", "", 1) + "};\n" + r"""
(async()=>{
 window.__eesSourceShellV1=bridge;
 await initNewChat();assert.equal(loadedChatIdProp,'');assert.equal(chatIdProp,'');assert.equal(lastChatPath,'/');
 chatIdProp='old';linkedUpdate();assert.equal(loads,1);assert.equal(loadedChatIdProp,'old');
 await bridge.adoptChat('new');assert.equal(retainedChatId,'new');assert.equal(location.pathname,'/c/new');assert.equal(navigations.at(-1).options.replaceState,true);
 nativeRoute=true;location.pathname='/workspace/models';activeId='late';const before=navigations.length;
 await bridge.adoptChat('late');assert.equal(navigations.length,before);assert.equal(location.pathname,'/workspace/models');assert.equal(retainedChatId,'late');assert.equal(created.at(-1),'late');
 await bridge.adoptChat('wrong-owner-chat');assert.equal(retainedChatId,'late');
 nativeRoute=false;lastChatPath='/c/late';
 selectedFolder={id:'other'};assert.equal(bridge.shouldInitChat('/folders/folder-a'),false);
 selectedFolder={id:'folder-a'};assert.equal(bridge.shouldInitChat('/folders/folder-a'),true);
 assert.equal(bridge.shouldInitChat('/folders/folder-a'),false,'Returning from Native must preserve the live folder draft');
 selectedFolder={id:'folder-b'};assert.equal(bridge.shouldInitChat('/folders/folder-b'),true);
 console.log('source_routes=pass');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result = subprocess.run([shutil.which("node"), "-e", probe], capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "source_routes=pass")

    def test_pending_native_control_save_cannot_write_or_apply_across_owner_change(self):
        source = (Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]) /
                  "src/lib/components/chat/Chat.svelte").read_text(encoding="utf-8")
        controls = _between(source, "const saveControls =", "\n\tconst eesDraftOwner")
        owner = _between(source, "const eesDraftOwner =", "\n\tconst MAX_DRAFT_LENGTH")
        probe = r'''
const assert=require('node:assert/strict');
let $user={id:'first'},$chatId='chat-first',$temporaryChatEnabled=false,cleanup,saveDraftTimeout=null;
let chat={chat:{params:{original:true}}},params={edited:true},chatFiles=[];
const onDestroy=callback=>cleanup=callback;
const localStorage={token:'first-token'},calls=[];
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
let settle;
const updateChatById=(token,id,body)=>{calls.push({token,id,body});return new Promise(resolve=>settle=resolve);};
''' + owner + controls + r'''
(async()=>{
 const pending=saveControls();assert.equal(calls.length,1);
 $user={id:'second'};$chatId='chat-second';localStorage.token='second-token';
 const baseline=chat;settle({chat:{params:{late:true}}});await pending;
 assert.equal(chat,baseline,'An old response cannot replace the current actor baseline');
 await saveControls();assert.equal(calls.length,1);
 $user={id:'first'};cleanup();await saveControls();assert.equal(calls.length,1);
 assert.equal(calls[0].token,'first-token');assert.equal(calls[0].id,'chat-first');
 console.log('native_controls_owner=pass');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "native_controls_owner=pass")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR") and shutil.which("node"),
                     "Patched source and Node are required for common API probes.")
class SourceApiTests(unittest.TestCase):
    def test_current_native_session_response_guard_errors_and_abort_signal(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
        source = (root / "src/lib/apis/ees-work.ts").read_text(encoding="utf-8")
        prelude = "const ts=require(" + json.dumps(str(root / "node_modules/typescript")) + ");\n"
        prelude += "const source=" + json.dumps(source) + ";\n"
        probe = prelude + r"""
const assert=require('node:assert/strict');
let actor={id:'actor-a'};global.localStorage={token:'token-a'};
let response={ok:true,status:200,json:async()=>({ok:true,kept:'result'})},calls=[];
global.fetch=async(url,options)=>{calls.push({url,options});return response;};
const moduleValue={exports:{}};
const requireStub=name=>name==='svelte/store'?{get:()=>actor}:name==='$lib/stores'?{user:{}}:{default:{t:(key,options)=>options.defaultValue}};
new Function('require','module','exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText)(requireStub,moduleValue,moduleValue.exports);
const request=moduleValue.exports.eesRequest;
(async()=>{
 const controller=new AbortController();
 assert.equal((await request('state',undefined,controller.signal)).kept,'result');
 assert.equal(calls[0].url,'/api/ees-work/state');assert.equal(calls[0].options.method,'GET');
 assert.equal(calls[0].options.headers.Authorization,'Bearer token-a');assert.equal(calls[0].options.credentials,'same-origin');
 assert.equal(calls[0].options.cache,'no-store');assert.equal(calls[0].options.signal,controller.signal);
 await request('command',{expected_revision:4});assert.equal(calls[1].options.method,'POST');assert.equal(calls[1].options.body,'{"expected_revision":4}');
 const denied={ok:false,error:{code:'scope_forbidden',message:'denied'}};
 response={ok:false,status:403,json:async()=>denied};await assert.rejects(request('state'),e=>e.status===403&&e.code==='scope_forbidden'&&e.result===denied);
 response={ok:true,status:200,json:async()=>{throw Error('invalid JSON')}};
 await assert.rejects(request('state'),e=>e.status===200&&e.message.includes('response'));
 response={ok:true,status:200,json:async()=>{actor={id:'actor-b'};return {private:true}}};
 await assert.rejects(request('state'),e=>e.status===409&&e.code==='context_changed'&&!e.result);
 actor={id:'actor-a'};response={ok:true,status:200,json:async()=>{localStorage.token='token-b';return {private:true}}};
 await assert.rejects(request('state'),e=>e.code==='context_changed'&&!e.result);
 actor=null;const before=calls.length;await assert.rejects(request('state'),e=>e.status===401);assert.equal(calls.length,before);
 actor={id:'actor-a'};global.fetch=async(url,options)=>{assert.equal(options.signal,controller.signal);throw Object.assign(Error('aborted'),{name:'AbortError'})};
 await assert.rejects(request('state',undefined,controller.signal),e=>e.name==='AbortError');
 console.log('source_api=pass');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result = subprocess.run([shutil.which("node"), "-e", probe], capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "source_api=pass")
