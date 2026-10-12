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
let chat=null,approvalCalls=0,failCreation=false,beginCalls=0,saveDraftTimeout=null;
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
        for name in ("src/lib/components/chat/Placeholder.svelte", "src/lib/components/chat/Navbar.svelte"):
            original = subprocess.check_output(["git", "show", config["commit"] + ":" + name], cwd=root)
            current = (root / name).read_bytes()
            stripped = re.sub(rb"[ \t]*data-ees-native-[a-z-]+(?:\n)?", b"", current)
            # Inline attributes retain their following space; multiline nav
            # attributes remove only their complete newly added source line.
            if name.endswith("Placeholder.svelte"):
                stripped = re.sub(rb" data-ees-native-[a-z-]+", b"", current)
            else:
                stripped = current.replace(b"\tdata-ees-native-toolbar\n", b"")
            self.assertEqual(stripped, original, name)
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
                      app + "/immutable/entry/start.js": b"__eesNativeDraftV1 __eesNativeWorkV1 ees_work_reference beginChatCreation finishChatCreation data-ees-native-sidebar"}
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


if __name__ == "__main__":
    unittest.main()
