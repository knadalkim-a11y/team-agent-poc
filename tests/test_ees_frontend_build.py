"""Source build provenance and Native draft/creation preservation boundaries."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
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


class NativeBaselineWaitTests(unittest.TestCase):
    def setUp(self):
        if __package__:
            from . import ees_frontend_native_baseline as baseline
        else:
            import ees_frontend_native_baseline as baseline
        self.baseline = baseline
        self.now = 100.0
        clock = patch.object(baseline.time, "monotonic", side_effect=lambda: self.now)
        sleep = patch.object(baseline.time, "sleep", side_effect=self.advance)
        clock.start()
        sleep.start()
        self.addCleanup(clock.stop)
        self.addCleanup(sleep.stop)

    def advance(self, seconds):
        self.now += seconds

    def navigation_error(self):
        return AssertionError("Runtime.evaluate: {'code': -32000, 'message': 'Inspected target navigated or closed'}")

    def test_reload_retries_destroyed_context_then_requires_new_complete_document(self):
        browser = Mock()
        browser.evaluate.side_effect = [42, self.navigation_error(), False, True]
        self.baseline.reload_page(browser)
        browser.call.assert_called_once_with("Page.reload", {"ignoreCache": True})
        evaluations = browser.evaluate.call_args_list[1:]
        for invocation in evaluations:
            self.assertEqual(invocation.args, ("performance.timeOrigin !== 42 && document.readyState === 'complete'",))
        self.assertEqual(len(evaluations), 3)
        for invocation, budget in zip(evaluations, (15, 14.95, 14.9)):
            self.assertAlmostEqual(invocation.kwargs["timeout"], budget)

    def test_persistent_navigation_failure_exhausts_one_original_deadline(self):
        browser = Mock()
        browser.evaluate.side_effect = self.navigation_error()
        with self.assertRaisesRegex(AssertionError, "Native baseline condition timed out"):
            self.baseline.wait(browser, "ready", seconds=0.12, retry_navigation=True)
        self.assertAlmostEqual(self.now, 100.12)
        self.assertEqual(browser.evaluate.call_count, 3)
        for invocation, budget in zip(browser.evaluate.call_args_list, (0.12, 0.07, 0.02)):
            self.assertAlmostEqual(invocation.kwargs["timeout"], budget)

    def test_non_navigation_failures_and_navigation_outside_reload_propagate(self):
        for error, retry in ((AssertionError("Runtime.evaluate: {'code': -32601, 'message': 'Method not found'}"), True),
                             (AssertionError("JavaScript assertion: Inspected target navigated or closed"), True),
                             (AssertionError("Chrome DevTools response timed out."), True),
                             (OSError("Chrome pipe closed"), True),
                             (self.navigation_error(), False)):
            with self.subTest(error=str(error), retry=retry):
                browser = Mock()
                browser.evaluate.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    self.baseline.wait(browser, "ready", seconds=1, retry_navigation=retry)
                self.assertIs(raised.exception, error)
                browser.evaluate.assert_called_once()
                self.assertEqual(self.now, 100)

    def test_true_result_arriving_at_deadline_is_not_success(self):
        browser = Mock()
        def evaluate(*args, **kwargs):
            self.advance(kwargs["timeout"])
            return True
        browser.evaluate.side_effect = evaluate
        with self.assertRaisesRegex(AssertionError, "Native baseline condition timed out"):
            self.baseline.wait(browser, "ready", seconds=1, retry_navigation=True)
        browser.evaluate.assert_called_once()

    def test_chrome_evaluation_passes_remaining_budget_to_cdp(self):
        browser = Mock()
        browser.call.return_value = {"result": {"value": True}}
        self.assertTrue(self.baseline.ChromePipe.evaluate(browser, "ready", timeout=0.25))
        browser.call.assert_called_once_with("Runtime.evaluate", {
            "expression": "ready", "returnByValue": True, "awaitPromise": True}, timeout=0.25)


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


class BuildExecutableTests(unittest.TestCase):
    def test_command_resolution_preserves_arguments_and_environment(self):
        environment = {"PATH": "pinned-node"}
        with patch.object(frontend.shutil, "which", return_value="C:/Node Tools/npm.cmd") as resolve:
            with patch.object(frontend.subprocess, "run") as execute:
                execute.return_value.stdout = "10.9.2\n"
                self.assertEqual(frontend._run(["npm", "--version"], "source", env=environment), "10.9.2")
        resolve.assert_called_once_with("npm", path="pinned-node")
        self.assertEqual(execute.call_args.args[0], ["C:/Node Tools/npm.cmd", "--version"])
        self.assertIs(execute.call_args.kwargs["env"], environment)
        self.assertNotIn("shell", execute.call_args.kwargs)

    def test_missing_executable_stops_before_launch(self):
        with patch.object(frontend.shutil, "which", return_value=None):
            with patch.object(frontend.subprocess, "run") as execute:
                with self.assertRaisesRegex(FileNotFoundError, "Required build executable"):
                    frontend._run(["npm", "--version"], "source")
        execute.assert_not_called()

    def test_patches_keep_lf_with_windows_autocrlf_enabled(self):
        from scripts import build_ees_webui as builder
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            frontend._run(["git", "init"], source)
            frontend._run(["git", "config", "core.autocrlf", "true"], source)
            patch_file = root / "new.patch"
            patch_file.write_text("diff --git a/icon.svg b/icon.svg\nnew file mode 100644\n"
                                  "--- /dev/null\n+++ b/icon.svg\n@@ -0,0 +1,2 @@\n"
                                  "+<svg>\n+</svg>\n", encoding="utf-8", newline="\n")
            wheel = root / "empty.whl"
            with ZipFile(wheel, "w"):
                pass
            config = {"patches": [{"path": "new.patch"}],
                      "patched_files": {"icon.svg": frontend._sha(b"<svg>\n</svg>\n")}}
            with patch.object(frontend, "SOURCE_CONFIG", root / "config.json"):
                with patch.object(builder, "prepare_additions", side_effect=RuntimeError("hashes verified")):
                    with self.assertRaisesRegex(RuntimeError, "hashes verified"):
                        frontend._apply_ees(source, config, wheel)
            self.assertEqual((source / "icon.svg").read_bytes(), b"<svg>\n</svg>\n")


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
        completion = "const probeCompletion=async response=>{const _chatId=$chatId,responseMessage={},eesHelp=false;" + capture + "\nconst res=await response;" + response + "};"
        reference = _between(source, "user_message: userMessage ? {", "\n\t\t\t\t...(regenerationPrompt")
        reference = "const referenceMessage=(_chatId,responseMessageId,userMessage)=>{const eesHelp=userMessage?.meta?.ees_work_help===1,model={id:'model'};return ({" + reference + "});};"
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
    def test_r11_removed_search_and_reference_have_no_source_entry_points(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
        navigation = (root / "src/lib/components/ees/EesNavigation.svelte").read_text(encoding="utf-8")
        navbar = (root / "src/lib/components/chat/Navbar.svelte").read_text(encoding="utf-8")
        launcher = (Path(__file__).resolve().parents[1] / "branding/ees/ui/ees-work-launcher.js").read_text(encoding="utf-8")
        for name, source, markers in (
            ('navigation', navigation, ('EES.Nav.Find', "['find',")),
            ('toolbar', navbar, ('reference_label', 'EES.GeneralConversation', 'ees-reference-caption', 'class="ew-reference"')),
            ('launcher', launcher, ("action==='find'", "action==='find_workflow'", 'ees-workflow-search', 'ees-workflow-list')),
        ):
            for marker in markers:
                with self.subTest(component=name, marker=marker):
                    self.assertFalse(marker in source, name + ' still exposes ' + marker)

    def test_r11_accessible_panel_control_preserves_native_toolbar_actions(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
        name = "src/lib/components/chat/Navbar.svelte"
        navbar = (root / name).read_text(encoding="utf-8")
        at = navbar.index('data-action="open_panel"')
        control = navbar[navbar.rfind('<button', 0, at):navbar.index('</button>', at)]
        self.assertIn('aria-expanded=', control)
        self.assertIn('aria-controls=', control)
        self.assertIn('EES.OpenPanel', control)
        self.assertIn('data-action="new_chat"', navbar)
        self.assertIn('window.__eesSourceShellV1?.newChat?.()', navbar)
        config = frontend.configuration()
        original = subprocess.check_output(["git", "show", config["commit"] + ":" + name], cwd=root).decode('utf-8')
        # The original authorization guards and click handlers for temporary
        # chat and Native controls are outside the R11 work-panel change.
        for start, end in (
            ("{#if $user?.role === 'user' ? ($user?.permissions?.chat?.temporary", "{#if $mobile && !$temporaryChatEnabled"),
            ("{#if $user?.role === 'admin' || ($user?.permissions.chat?.controls", '</Tooltip>'),
        ):
            with self.subTest(native_control=start):
                self.assertEqual(_between(navbar, start, end), _between(original, start, end))

    def test_layout_hooks_preserve_native_elements_and_reject_source_drift(self):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
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
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
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
        # EesShell is TypeScript. Compile the extracted bridge just as the
        # other source probes do; the pinned Node 22 cannot execute annotations.
        probe = "const ts=require(" + json.dumps(str(root / "node_modules/typescript")) + ");\n" + \
            "eval(ts.transpile(" + json.dumps(probe) + ", {target:ts.ScriptTarget.ES2022}));\n"
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
const userStore={},readyStore={};let ready=true;
const requireStub=name=>name==='svelte/store'?{get:store=>store===readyStore?ready:actor}:name==='$lib/stores'?{user:userStore}:name==='$lib/components/ees/state'?{eesSessionReady:readyStore}:{default:{t:(key,options)=>options.defaultValue}};
new Function('require','module','exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText)(requireStub,moduleValue,moduleValue.exports);
const request=moduleValue.exports.eesRequest;
(async()=>{
 const controller=new AbortController();
 ready=false;await assert.rejects(request('state'),e=>e.status===401);assert.equal(calls.length,0);ready=true;
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


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR") and shutil.which("node"),
                     "Patched source and Node are required for helper send probes.")
class SourceHelperTests(unittest.TestCase):
    run_node = NativeDraftHookTests.run_node

    def source(self, name):
        return (Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve() / name).read_text(encoding="utf-8")

    def transpile_prelude(self, source):
        root = Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve()
        return "const ts=require(" + json.dumps(str(root / "node_modules/typescript")) + ");\n" + \
            "const compiled=ts.transpile(" + json.dumps(source) + ", {target:ts.ScriptTarget.ES2022});\n"

    def test_helper_preflight_keeps_draft_and_freezes_model_reference_with_owner_guards(self):
        source = self.source("src/lib/components/chat/Chat.svelte")
        helper = _between(source, "const eesAskHelp =", "\n\tconst submitPrompt =")
        probe = self.transpile_prelude(helper) + r'''
const assert=require('node:assert/strict');
let eesHelperPending=false,eesHelperNotice='',eesDraftAlive=true,eesDraftOwner='a';
let $user={id:'a'},localStorage={token:'a'},$chatId='chat-a',history={messages:{},currentId:'parent'};
let selectedModels=['first','second'],$models=[{id:'first'},{id:'second'}],chatVariables={},readOnly=false,eesFolderReadOnly=false;
let nativeBusy=false,ready=true,context={system_id:'',context_id:'context-a'},sent=[],persisted=[];
const $i18n={t:(_,o)=>o.defaultValue};const sessionStorage={getItem:()=>null,removeItem(){}};
const draft={prompt:'typed draft',files:[{id:'live-image'}],selectedToolIds:['keep-tool']};
const getChatInputDraft=()=>draft,saveDraft=async(value,id)=>persisted.push({value,id});
const eesNativeBusy=()=>nativeBusy,getChatVariablesForm=()=>({missing:false,conflicts:[]});
const window={__eesNativeDraftV1:{ready:()=>ready},__eesNativeWorkV1:{helpContext:()=>context}};
let status={available:true,protocol:1,model_id:'first'},finish,hold=false;
const eesRequest=async path=>{assert.match(path,/model_id=first/);return hold?await new Promise(r=>finish=r):status;};
const submitPrompt=async(question,files,options)=>{sent.push({question,files,options});history.messages.sent={meta:{ees_work_reference:options.reference}};return 'sent';};
const ask=eval(compiled+';eesAskHelp');
const reference={kind:'help',system_id:'',context_id:'context-a',title:'original'};
(async()=>{
 hold=true;const first=ask({question:'question only',reference});
 assert.equal(eesHelperPending,true);assert.equal((await ask({question:'duplicate',reference})).code,'busy');
 reference.title='changed after click';finish(status);assert.equal((await first).accepted,true);
 assert.equal(sent.length,1);assert.equal(sent[0].question,'question only');assert.deepEqual(sent[0].files,[]);
 assert.equal(sent[0].options.reference.title,'original');assert.equal(sent[0].options.modelId,'first');
 assert.deepEqual(selectedModels,['first','second']);assert.equal(persisted[0].value,draft);
 hold=false;status={available:false,protocol:1,code:'tool_unavailable',message:'Unavailable'};
 assert.equal((await ask({question:'blocked',reference})).accepted,false);assert.equal(sent.length,1);
 status={available:false,protocol:1,code:'tool_unavailable'};
 assert.equal((await ask({question:'missing reason',reference})).accepted,false);assert.equal(sent.length,1);
 assert.match(eesHelperNotice,/administrator/i);assert.match(eesHelperNotice,/tool.*permission.*version/i);
 status={available:true,protocol:1,model_id:'first'};hold=true;
 const moved=ask({question:'moved',reference});context={system_id:'',context_id:'other'};finish(status);
 assert.equal((await moved).code,'context_changed');assert.equal(sent.length,1);
 context={system_id:'',context_id:'context-a'};
 const deniedMove=ask({question:'old unavailable',reference});context={system_id:'',context_id:'new-screen'};eesHelperNotice='current screen notice';
 finish({available:false,protocol:1,code:'tool_unavailable',message:'old unavailable result'});
 assert.equal((await deniedMove).code,'context_changed');assert.equal(eesHelperNotice,'current screen notice');assert.equal(sent.length,1);
 context={system_id:'',context_id:'context-a'};const stale=ask({question:'old user',reference});
 $user={id:'b'};localStorage.token='b';eesHelperNotice='new user notice';finish(status);
 assert.equal((await stale).accepted,false);assert.equal(eesHelperNotice,'new user notice');assert.equal(sent.length,1);
 $user={id:'a'};localStorage.token='a';nativeBusy=true;hold=false;
 assert.equal((await ask({question:'busy',reference})).code,'busy');assert.equal(sent.length,1);
 console.log('source_helper_preflight=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "source_helper_preflight=pass")

    def test_helper_pair_rollback_requires_explicit_unpersisted_server_rejection(self):
        source = self.source("src/lib/components/chat/Chat.svelte")
        submit = _between(source, "const submitPrompt =", "\n\tconst handleManualCompact")
        probe = self.transpile_prelude(submit) + r'''
const assert=require('node:assert/strict');
let history,chatFiles=[{id:'kept-chat-file'}],selectedModels=['first','second'];
let eesDraftAlive=true,$user={id:'actor'},$chatId='chat',id=0;
const uuidv4=()=>`message-${++id}`,equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b),$showCallOverlay=false;
const messageInput={focus(){throw Error('helper must not focus or replace input');}};
const saveSessionSelectedModels=()=>{throw Error('helper must not replace model choice');};
const window={__eesNativeWorkV1:{helpContext:()=>({context_id:'ctx'})}};
let rejection=null;
const sendMessage=async(h,parent,options)=>{
 assert.equal(options.modelId,'first');assert.equal(options.eesHelpGuard(),true);
 h.messages.child={parentId:parent};h.messages[parent].childrenIds.push('child');h.currentId='child';
 if(rejection)throw rejection;
};
const submit=eval(compiled+';submitPrompt');
const reset=()=>{history={messages:{parent:{childrenIds:['older']}},currentId:'parent'};};
const options={modelId:'first',reference:{kind:'help',context_id:'ctx'},actor:'actor',chatId:'chat'};
(async()=>{
 reset();const sent=await submit('question',[],options);
 assert.equal(history.messages[sent].content,'question');assert.deepEqual(history.messages[sent].models,['first']);
 assert.deepEqual(selectedModels,['first','second']);assert.deepEqual(chatFiles,[{id:'kept-chat-file'}]);
 reset();rejection={code:'work_help_unavailable',persisted:false};await assert.rejects(submit('no-save',[],options));
 assert.deepEqual(history,{messages:{parent:{childrenIds:['older']}},currentId:'parent'});
 reset();rejection={code:'work_help_unavailable',persisted:true};await assert.rejects(submit('already saved',[],options));
 assert.equal(Object.keys(history.messages).length,3);assert.equal(history.currentId,'child');
 console.log('source_helper_rollback=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "source_helper_rollback=pass")

    def test_native_completion_api_preserves_structured_errors_only_when_requested(self):
        source = self.source("src/lib/apis/openai/index.ts")
        api = _between(source, "export const generateOpenAIChatCompletion =", "\nexport const synthesizeOpenAISpeech")
        api = api.replace("export const", "const", 1)
        probe = self.transpile_prelude(api) + r'''
const assert=require('node:assert/strict'),WEBUI_BASE_URL='';
const detail={code:'work_help_unavailable',persisted:false,message:'Unavailable'};
const fetch=async()=>({ok:false,json:async()=>({detail})});
const getErrorMessage=error=>error.detail.message;
const generate=eval(compiled+';generateOpenAIChatCompletion');
(async()=>{
 await assert.rejects(generate('token',{}),error=>error==='Unavailable');
 await assert.rejects(generate('token',{},'/api',{preserveError:true}),error=>error.detail===detail);
 console.log('source_helper_api_error=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "source_helper_api_error=pass")

    def test_helper_request_isolation_does_not_change_ordinary_native_send(self):
        source = self.source("src/lib/components/chat/Chat.svelte")
        send = _between(source, "const sendMessageSocket =", "\n\tconst handleOpenAIError")
        probe = self.transpile_prelude(send) + r'''
const assert=require('node:assert/strict');
let chatFiles=[{id:'doc',type:'doc'}],$chatId='chat';
const selectedModels=['first','second'],selectedToolIds=['read-tool','direct_server:0'];
const selectedFilterIds=['personal-filter'],selectedSkillIds=['personal-skill'];
const $settings={params:{temperature:.3},system:'personal system'},params={top_p:.8};
const $user={id:'actor',name:'Actor',email:'actor@example.test'},eesDraftOwner='actor',eesDraftAlive=true;
const localStorage={token:'token'},$temporaryChatEnabled=false,embedded=false;
const $toolServers=[{id:'direct-tool'}],$terminalServers=[{id:'terminal'}, {url:'http://localhost/terminal'}],$selectedTerminalId='terminal';
const $models=[{id:'first',info:{meta:{capabilities:{}}}},{id:'second'}],$socket={id:'socket'},$selectedFolder=null;
const WEBUI_BASE_URL='',chatVariables={},isTemporaryChatId=()=>false,equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const getFeatures=()=>({web_search:true,code_interpreter:true}),getStopTokens=()=>[],getPromptVariables=()=>({});
const scrollToBottom=()=>{},tick=async()=>{},shouldAutoScrollResponse=()=>false;
const CustomEvent=function(type,data){this.type=type;this.detail=data.detail;},eventTarget={dispatchEvent(){}};
const window={__eesNativeWorkV1:{captureReference:()=>({kind:'help',context_id:'live',system_id:'sys',screen:'live-screen'})}};
const requests=[];
const generateOpenAIChatCompletion=async(token,body,url,options)=>{requests.push({body,options});return null;};
const send=eval(compiled+';sendMessageSocket');
const ref={kind:'help',context_id:'frozen',system_id:'sys',screen:'frozen-screen'};
const historyFor=helper=>({messages:{question:{id:'question',parentId:null,role:'user',content:'only question',files:[{id:'doc',type:'doc'}],models:['first'],meta:helper?{ees_work_help:1,ees_work_reference:ref}:{}},answer:{id:'answer',parentId:'question'}}});
(async()=>{
 const draftAssets=JSON.stringify({selectedModels,selectedToolIds,selectedFilterIds,selectedSkillIds,$selectedTerminalId});
 await send($models[0],[{files:[{id:'doc'}]}],historyFor(false),'answer','chat');
 const ordinary=requests[0].body;
 assert.deepEqual(ordinary.files,[{id:'doc',type:'doc'}]);assert.deepEqual(ordinary.filter_ids,['personal-filter']);
 assert.deepEqual(ordinary.tool_ids,['read-tool']);assert.deepEqual(ordinary.skill_ids,['personal-skill']);
 assert.equal(ordinary.terminal_id,'terminal');assert.equal(ordinary.tool_servers.length,2);assert.equal(ordinary.features.web_search,true);
 assert.equal(ordinary.user_message.meta.ees_work_reference.screen,'live-screen');assert.equal(ordinary.user_message.meta.ees_work_help,undefined);
 assert.equal(ordinary.ees_work_composer_models,undefined);
 await send($models[0],[{files:[{id:'doc'}]}],historyFor(true),'answer','chat');
 const helper=requests[1].body;
 assert.equal(helper.files,undefined);assert.equal(helper.filter_ids,undefined);assert.equal(helper.tool_ids,undefined);
 assert.equal(helper.skill_ids,undefined);assert.equal(helper.terminal_id,undefined);assert.deepEqual(helper.tool_servers,[]);
 assert.deepEqual(helper.features,{});assert.deepEqual(helper.background_tasks,{});assert.deepEqual(helper.user_message.files,[]);
 assert.equal(helper.user_message.meta.ees_work_reference.screen,'frozen-screen');assert.equal(helper.user_message.meta.ees_work_help,1);
 assert.deepEqual(helper.ees_work_composer_models,['first','second']);assert.deepEqual(helper.user_message.models,['first']);
 assert.equal(JSON.stringify({selectedModels,selectedToolIds,selectedFilterIds,selectedSkillIds,$selectedTerminalId}),draftAssets);
 assert.deepEqual(chatFiles,[{id:'doc',type:'doc'}]);
 console.log('source_helper_request_isolation=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "source_helper_request_isolation=pass")


@unittest.skipUnless(os.environ.get("EES_TEST_FRONTEND_SOURCE_DIR") and shutil.which("node"),
                     "Patched source and Node are required for Native session lifecycle probes.")
class SourceSessionTests(unittest.TestCase):
    run_node = NativeDraftHookTests.run_node

    def test_cross_tab_session_owner_reload_same_owner_preservation_and_late_guards(self):
        source = (Path(os.environ["EES_TEST_FRONTEND_SOURCE_DIR"]).resolve() /
                  "src/routes/+layout.svelte").read_text(encoding="utf-8")
        handler = _between(source, "const eesRevalidateSession =", "\n\tonDestroy(() => { eesSessionAlive")
        probe = r'''
const assert=require('node:assert/strict');
let eesSessionToken='token-a',eesSessionEpoch=0,eesSessionAlive=true,eesSessionFailed=false,$user={id:'a',token:'token-a'};
let localStorage={token:'token-a'},ready=true,result={id:'a',token:'renewed-a'},held=false,finish,fail=false;
const sessionStorage={'chat-input':'private draft','ees-source-draft-owner':'a',other:'keep',removeItem(key){delete this[key];}};
const eesSessionReady={set(value){ready=value;}},user={set(value){$user=value;}},joined=[],paths=[];
const $socket={emit:(event,value)=>joined.push(value)};
const window={__eesNativeWorkV1:{sync(){}},location:{replace:path=>paths.push(path)}};
const getSessionUser=async token=>{if(fail)throw Error('temporary offline');return held?await new Promise(r=>finish=r):result;};
''' + handler + r'''
(async()=>{
 await eesRevalidateSession({type:'storage',key:'unrelated'});assert.equal(paths.length,0);
 localStorage.token='renewed-a';await eesRevalidateSession({type:'focus'});
 assert.equal(ready,true);assert.equal($user.id,'a');assert.equal(sessionStorage['chat-input'],'private draft');
 assert.equal(paths.length,0);assert.equal(joined.length,1);
 localStorage.token='token-b';result={id:'b',token:'token-b'};fail=true;
 await eesRevalidateSession({type:'storage',key:'token'});assert.equal(ready,false);assert.equal(eesSessionFailed,true);assert.equal($user.id,'a');
 assert.equal(eesSessionToken,'renewed-a');assert.equal(sessionStorage['chat-input'],'private draft');assert.equal(paths.length,0);
 fail=false;held=true;const late=eesRevalidateSession({type:'focus'});
 localStorage.token='token-c';$user={id:'c',token:'token-c'};
 await eesRevalidateSession({type:'focus'});finish({id:'b',token:'token-b'});await late;
 assert.equal($user.id,'c');assert.equal(paths.length,0);assert.equal(ready,true);
 localStorage.token='token-b';const sameTokenCommit=eesRevalidateSession({type:'focus'});
 $user={id:'b',token:'token-b',name:'new Native sign-in'};await eesRevalidateSession({type:'focus'});
 finish({id:'b',token:'token-b',name:'older lookup'});await sameTokenCommit;
 assert.equal($user.name,'new Native sign-in');assert.equal(paths.length,0);
 $user={id:'c',token:'token-c'};eesSessionToken='token-c';
 held=false;localStorage.token='token-b';result={id:'b',token:'token-b'};
 await eesRevalidateSession({type:'focus'});assert.equal($user,null);assert.equal(ready,false);
 assert.deepEqual(paths,['/']);assert.equal(sessionStorage['chat-input'],undefined);assert.equal(sessionStorage.other,'keep');
 $user={id:'b',token:'token-b'};sessionStorage['chat-input']='b draft';localStorage.token='';
 await eesRevalidateSession({type:'storage',key:'token'});assert.deepEqual(paths,['/','/auth']);assert.equal(sessionStorage['chat-input'],undefined);
 eesSessionAlive=false;localStorage.token='token-c';await eesRevalidateSession({type:'focus'});assert.equal(paths.length,2);
 console.log('source_session_owner=pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        self.assertEqual(self.run_node(probe), "source_session_owner=pass")
