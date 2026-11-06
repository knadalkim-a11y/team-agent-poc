/* Execute the production prompt controller against delayed Native API responses. */
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs');
const patch = fs.readFileSync(require('node:path').join(__dirname, '../frontend/patches/0001-ees-native-hooks.patch'), 'utf8');
function source(file) { return patch.split(`diff --git a/${file} b/${file}`)[1].split('\ndiff --git ')[0].split('\n').filter(x => x.startsWith('+') && !x.startsWith('+++')).map(x => x.slice(1)).join('\n'); }
const code = source('src/lib/components/ees/EesSavedPrompts.svelte');
function block(start, end) { const a = code.indexOf(start), b = code.indexOf(end, a); assert.ok(a >= 0 && b > a); return code.slice(a, b); }
const functions = block('function session()', '\n\tonDestroy') + block('async function load()', '\n\tfunction listKeys').replace('open: boolean', 'open');
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => {resolve=yes; reject=no;}); return {promise,resolve,reject}; }
function harness() {
 const reads=[], writes=[], chosen=[], notices=[];
 const env={ boundary:'chat-1', $user:{id:'one'}, $eesSessionReady:true, localStorage:{token:'session-one'}, alive:true, sequence:0, show:true, showCreate:false, loading:false, error:false, query:'', items:[], listSession:null, createSession:null, draft:null, prompt:'보존할 현재 입력', canManage:true, search:{focus(){}}, trigger:{focus(){env.focused++;}}, focused:0,
  tick:async()=>{}, t:(_key,fallback)=>fallback, $i18n:{t:key=>key}, toast:{success:value=>notices.push(value)}, onChoose:async text=>chosen.push(text),
  getPrompts:token=>{const d=deferred(); reads.push({token,...d}); return d.promise;}, createNewPrompt:(token,value)=>{const d=deferred();writes.push({token,value,...d});return d.promise;}};
 const api=Function('env',`with(env){${functions};return {session,current,reset,load,opened,choose,saveInput,save};}`)(env);
 return {env,api,reads,writes,chosen,notices};
}
test('saved prompts refresh accessible Native records and distinguish failure from empty results', async()=>{
 const h=harness(), pending=h.api.load();assert.equal(h.env.loading,true);
 h.reads[0].resolve([{id:'own',name:'Private',content:'safe'}, {id:'shared',content:'shared'}, {id:'disabled',content:'off',is_active:false}, null, {id:'bad',content:7}]);await pending;
 assert.deepEqual(h.env.items.map(x=>x.id),['own','shared']);assert.equal(h.env.loading,false);
 await h.api.choose(h.env.items[1]);assert.deepEqual(h.chosen,['shared']);assert.equal(h.writes.length,0);
 const failed=h.api.load();h.reads[1].reject(new Error('offline'));await failed;assert.equal(h.env.error,true);assert.deepEqual(h.env.items,[]);
 const retry=h.api.load();h.reads[2].resolve([]);await retry;assert.equal(h.env.error,false);assert.deepEqual(h.env.items,[]);
});
test('older prompt requests and closed popovers cannot repopulate a newer list',async()=>{
 const h=harness(), first=h.api.load(), second=h.api.load();
 h.reads[1].resolve([{id:'new',content:'new'}]);await second;h.reads[0].resolve([{id:'old',content:'old'}]);await first;assert.equal(h.env.items[0].id,'new');
 const third=h.api.load();await h.api.opened(false);h.reads[2].resolve([{id:'late',content:'late'}]);await third;assert.deepEqual(h.env.items,[]);assert.equal(h.env.loading,false);
});
test('prompt responses and selections never cross account, session, conversation or destruction boundaries',async()=>{
 for(const change of [h=>h.env.$user={id:'two'},h=>h.env.localStorage.token='session-two',h=>h.env.boundary='chat-2',h=>h.env.alive=false,h=>h.env.$eesSessionReady=false]){
  const h=harness(), item={id:'private',content:'private'}, pending=h.api.load();change(h);h.reads[0].resolve([item]);await pending;assert.deepEqual(h.env.items,[]);await h.api.choose(item);assert.deepEqual(h.chosen,[]);
  const k=harness(), loaded=k.api.load();k.reads[0].resolve([item]);await loaded;change(k);await k.api.choose(item);assert.deepEqual(k.chosen,[]);
 }
});
test('save current input prepares a private Native draft and writes only after explicit save',async()=>{
 const h=harness();await h.api.saveInput();assert.equal(h.writes.length,0);assert.equal(h.env.showCreate,true);assert.deepEqual(h.env.draft,{name:'',command:'',content:'보존할 현재 입력',tags:[],access_grants:[]});
 const value={...h.env.draft,name:'내 요청',command:'my-request'};const pending=h.api.save(value);assert.deepEqual(h.writes[0].value,value);assert.equal(h.writes[0].token,'session-one');h.writes[0].resolve({id:'created'});await pending;
 assert.equal(h.env.prompt,'보존할 현재 입력');assert.equal(h.env.showCreate,false);assert.equal(h.env.draft,null);assert.equal(h.notices.length,1);assert.equal(h.env.focused,1);
});
test('failed prompt creation retains the edited content and permits retry without overwriting existing prompts',async()=>{
 const h=harness();await h.api.saveInput();const value={...h.env.draft,name:'duplicate',command:'duplicate'};const pending=h.api.save(value);h.writes[0].reject(new Error('duplicate command'));await assert.rejects(pending,/duplicate/);assert.equal(h.env.showCreate,true);assert.equal(h.env.draft.content,h.env.prompt);
 const retry=h.api.save({...value,command:'new-command'});h.writes[1].resolve({id:'new'});await retry;assert.equal(h.writes.length,2);assert.ok(h.writes.every(w=>w.value.id===undefined));
});
test('save dialog and pending save cannot open or announce success after the session changes',async()=>{
 const h=harness(), tick=deferred();h.env.tick=()=>tick.promise;const opening=h.api.saveInput();h.env.boundary='chat-2';h.api.reset();tick.resolve();await opening;assert.equal(h.env.showCreate,false);
 const k=harness();await k.api.saveInput();k.env.canManage=false;await k.api.save({});assert.equal(k.writes.length,0);
 const j=harness();await j.api.saveInput();const saving=j.api.save({...j.env.draft,name:'save',command:'save'});j.env.$user={id:'two'};j.api.reset();j.writes[0].resolve({id:'accepted-for-original-owner'});await saving;assert.deepEqual(j.notices,[]);assert.equal(j.env.focused,0);
});
test('saved prompt insertion appends to the existing draft and refuses a changed editor context',async()=>{
 const src=source('src/lib/components/chat/MessageInput.svelte');const start=src.indexOf('const insertSavedPrompt ='),end=src.indexOf('const replaceSlashRangeWithPrompt =',start);assert.ok(start>=0&&end>start);
 const inserted=[],doc={content:{size:17}},editor={state:{doc},isDestroyed:false};const env={chatInputEditor:editor,$_user:{id:'one'},localStorage:{token:'one'},chatId:'chat-one',prompt:'Keep my text',replaceSlashRangeWithPrompt:async(...args)=>inserted.push(args)};
 const insert=Function('env',`with(env){${src.slice(start,end).replace('text: string','text')}return insertSavedPrompt;}`)(env);await insert('Saved text');assert.equal(inserted.length,1);assert.deepEqual(inserted[0][1],{from:16,to:16});assert.equal(inserted[0][2],'\n\nSaved text');const current=inserted[0][3];assert.equal(current(),true);editor.state.doc={};assert.equal(current(),false);editor.state.doc=doc;env.chatId='chat-two';assert.equal(current(),false);assert.equal(env.prompt,'Keep my text');
});

// Exercise the changed newline branch with the native schema's empty-text invariant.
test('appending multiline prompts never creates an empty text node',()=>{
 const src=patch.split('diff --git a/src/lib/components/chat/MessageInput.svelte b/src/lib/components/chat/MessageInput.svelte')[1].split('\ndiff --git ')[0].split('\n').filter(line=>(line.startsWith('+')&&!line.startsWith('+++'))||line.startsWith(' ')).map(line=>line.slice(1)).join('\n');
 const expression=src.match(/\.flatMap\(\(line, index\) =>[\s\S]*?\n\s*\);/)[0];
 const state={schema:{text(value){assert.equal(typeof value,'string');assert.ok(value.length);return {text:value};},nodes:{paragraph:{create:(_,content)=>({paragraph:content??null})}}}};
 const convert=Function('state','text',`return text.split('\\n')${expression}`);
 assert.deepEqual(convert(state,'\n\nSaved text'),[{paragraph:null},{paragraph:{text:'Saved text'}}]);
 assert.deepEqual(convert(state,'First\nSecond'),[{text:'First'},{paragraph:{text:'Second'}}]);
});

test('Escape closes the saved-prompt popup and restores its trigger before global shortcuts',()=>{
 const h=harness();
 const handler=block('function listKeys(', '\n</script>')
  .replace('event: KeyboardEvent','event').replaceAll(' as HTMLElement','')
  .replaceAll(' as HTMLButtonElement','').replaceAll('querySelectorAll<HTMLButtonElement>','querySelectorAll');
 h.env.opened=h.api.opened;h.env.loading=true;
 const key=Function('env',`with(env){${handler};return listKeys;}`)(h.env);
 let prevented=false,stopped=false;
 key({key:'Escape',preventDefault(){prevented=true},stopPropagation(){stopped=true}});
 assert.equal(prevented,true);assert.equal(stopped,true);
 assert.equal(h.env.show,false);assert.equal(h.env.loading,false);assert.equal(h.env.sequence,1);
 assert.equal(h.env.focused,1);assert.deepEqual(h.writes,[]);assert.deepEqual(h.chosen,[]);
});
