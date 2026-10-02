/* Unit fixtures for the actual browser modules. Not Native product evidence. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const viewSource=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-view.js'),'utf8');
const launcherSource=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8');
function renderer(extra={}){const context={document:{querySelector:()=>null},window:{},location:{origin:'http://native.test'},URL,console,...extra};vm.createContext(context);vm.runInContext(viewSource,context);return context;}
function run(context,source){return vm.runInContext(source,context);}
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function controller(){
 const calls=[],renders=[],timers=new Map();let auth='actor-a-token',counter=0,reply=()=>({ok:true,capabilities:{actor_id:'a'},systems:[],workflows:[],runs:[],my_work:[],ui_state:{revision:0,state:{}},operations:{}});
 const document={body:{dataset:{}},documentElement:{},querySelector:()=>({}),addEventListener(){},querySelectorAll:()=>[]};
 const window={addEventListener(){}};
 const view={render:value=>renders.push(value),sync(){},suspend(){},reset(){},setBusy(){},capture(){},readInputs:()=>({inputs:{}}),authoringHost:()=>null};
 const designer={render(){},reset(){},setBusy(){},handleEvent:()=>({handled:false}),acceptProposal:()=>({ok:true})};
 const context=renderer({document,window,location:{origin:'http://native.test',pathname:'/',search:''},localStorage:{getItem:()=>auth},URLSearchParams,crypto:{randomUUID:()=>`request-${++counter}`},setTimeout:fn=>{const key=++counter;timers.set(key,fn);return key;},clearTimeout:key=>timers.delete(key),requestAnimationFrame(){},MutationObserver:class{observe(){}},fetch:async(url,options)=>{const call={url,options,body:options?.body?JSON.parse(options.body):null};calls.push(call);const value=await reply(call);return {ok:value?.httpError?false:true,status:value?.status || 200,headers:{get:()=> 'application/json'},json:async()=>value};}});
 let dialogReply=()=>Promise.resolve(false);context.testUI={...run(context,'workUI'),dialog:options=>dialogReply(options)};
 context.createWorkView=()=>view;context.createWorkDesigner=()=>designer;
 const instrumented=launcherSource.replace('dialog,closeDialog}=workUI;','dialog,closeDialog}=testUI;').replace('  schedule();\n})();',`  identity=token();restored=true;window.testController={setRestored:value=>{restored=value;},sync,loadOptions,confirmDialog,refresh,command,operationsCommand,select,models,normalized,reference,reset,context,handleClick,handleEvent,requestIntent,previewInputProposal,applyInputProposal,setupWorkTool,beginChatCreation,finishChatCreation,acceptNativeProposal,adminDialog,downloadRun,openLegacy, snapshot:()=>({state,selection,error:error || commandError,receipts:[...receipts],epoch}),setState:value=>{state=value;},setIdentity:()=>{identity=token();},setSelection:value=>{selection={...selection,...value};}};\n})();`);
 vm.runInContext(instrumented,context);
 return {context,api:window.testController,calls,renders,timers,view,designer,setAuth:value=>{auth=value;},setReply:value=>{reply=value;},setDialog:value=>{dialogReply=value;}};
}
module.exports={renderer,run,controller,deferred,viewSource,launcherSource,root};
