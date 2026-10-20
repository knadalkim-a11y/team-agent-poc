/* Lifecycle checks use the actual browser helper; computed styles are supplied by
 * the DOM fixture. Native tests separately measure CSS and real input/focus. */
const test=require('node:test'),assert=require('node:assert/strict');
const {renderer}=require('./ees_workspace_ui_fixture.cjs');
function harness(){
 let now=0,next=0,reduced=false;const timers=new Map(),mediaListeners=new Set();
 const media={get matches(){return reduced;},addEventListener(type,fn){mediaListeners.add(fn);},removeEventListener(type,fn){mediaListeners.delete(fn);}};
 const values={'--ees-motion-fast':'120ms','--ees-motion-open':'200ms','--ees-motion-close':'150ms','--ees-motion-open-easing':'cubic-bezier(0.2, 0.8, 0.2, 1)','--ees-motion-close-easing':'cubic-bezier(0.4, 0, 1, 1)'};
 function element(){const attrs=new Map(),listeners=new Map(),style=new Map();return {inert:false,isConnected:true,focusCount:0,style:{setProperty:(k,v)=>style.set(k,v),removeProperty:k=>style.delete(k)},styles:style,
  setAttribute:(k,v)=>attrs.set(k,String(v)),getAttribute:k=>attrs.get(k)??null,removeAttribute:k=>attrs.delete(k),
  addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);},removeEventListener(type,fn){listeners.get(type)?.delete(fn);},
  emit(type,patch={}){for(const fn of [...(listeners.get(type)||[])])fn({type,target:this,...patch});},focus(){this.focusCount++;},computed:{opacity:'.42',transform:'matrix(1, 0, 0, 1, 0, -2)'}};}
 const root=element(),document={documentElement:root,body:element(),activeElement:null},context=renderer({document,window:{matchMedia:()=>media},getComputedStyle:el=>({...el.computed,getPropertyValue:name=>values[name]??''}),setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id)});
 function advance(ms){const end=now+ms;while(true){const scheduled=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!scheduled)break;now=scheduled[1].at;timers.delete(scheduled[0]);scheduled[1].fn();}now=end;}
 return {motion:context.window.__eesMotionV1,document,element,advance,timers,values,setReduced(value){reduced=value;for(const fn of [...mediaListeners])fn({matches:value});}};
}
test('C3 close releases interaction immediately then cleans and restores focus once on its own end signal',async()=>{
 const h=harness(),surface=h.element(),focus=h.element(),order=[];
 const done=h.motion.close(surface,{release:()=>order.push(['release',surface.getAttribute('data-ees-motion'),surface.inert]),cleanup:()=>order.push(['cleanup']),restoreFocus:focus});
 assert.deepEqual(order,[['release','closing',true]]);assert.equal(surface.getAttribute('aria-hidden'),'true');assert.equal(focus.focusCount,0);
 surface.emit('animationend',{target:h.element(),animationName:'ees-motion-close'});surface.emit('animationend',{animationName:'ees-motion-open'});assert.equal(order.length,1);
 surface.emit('animationend',{animationName:'ees-motion-close'});assert.equal(await done,true);h.advance(300);assert.equal(order.length,2);assert.equal(focus.focusCount,1);assert.equal(h.timers.size,0);
});
test('C3 missing end signal closes at CSS close duration plus 50ms',async()=>{
 const h=harness(),surface=h.element();let cleaned=0;const done=h.motion.close(surface,{cleanup:()=>cleaned++});
 h.advance(199);assert.equal(cleaned,0);h.advance(1);assert.equal(await done,true);assert.equal(cleaned,1);
});
test('C3 reopening cancels pending cleanup and focus while reversing from the current frame',async()=>{
 const h=harness(),surface=h.element(),focus=h.element();let cleaned=0;
 const closing=h.motion.close(surface,{cleanup:()=>cleaned++,restoreFocus:focus});h.advance(30);h.motion.open(surface);
 assert.equal(await closing,false);assert.equal(surface.inert,false);assert.equal(surface.getAttribute('aria-hidden'),null);assert.equal(surface.getAttribute('data-ees-motion'),'opening');assert.equal(surface.styles.get('--ees-motion-from-opacity'),'.42');
 h.advance(220);assert.equal(cleaned,0);assert.equal(focus.focusCount,0);assert.equal(surface.getAttribute('data-ees-motion'),'opening');h.advance(30);assert.equal(surface.getAttribute('data-ees-motion'),null);
});
test('C3 rapid repeated close shares one completion and later cycles are independent',async()=>{
 const h=harness(),surface=h.element();let cleaned=0;h.motion.open(surface);h.advance(1);
 const first=h.motion.close(surface,{cleanup:()=>cleaned++});const duplicate=h.motion.close(surface,{cleanup:()=>cleaned+=100});assert.equal(first,duplicate);
 surface.emit('animationend',{animationName:'ees-motion-close'});assert.equal(await first,true);h.motion.open(surface);const second=h.motion.close(surface,{cleanup:()=>cleaned++});h.advance(200);assert.equal(await second,true);assert.equal(cleaned,2);assert.equal(h.timers.size,0);
});
test('C3 reduced motion has zero CSS-derived timings and synchronous cleanup/focus without a timer',async()=>{
 const h=harness();h.setReduced(true);const surface=h.element(),focus=h.element();let cleaned=0;
 h.motion.open(surface);assert.equal(surface.getAttribute('data-ees-motion'),null);const done=h.motion.close(surface,{cleanup:()=>cleaned++,restoreFocus:focus});
 assert.equal(cleaned,1);assert.equal(focus.focusCount,1);assert.equal(h.timers.size,0);assert.equal(await done,true);assert.equal(h.motion.settings(surface).open,0);assert.equal(h.motion.settings(surface).close,0);
});
test('C3 enabling reduced motion during an exit immediately completes and clears fallback',async()=>{
 const h=harness(),surface=h.element();let cleaned=0;const done=h.motion.close(surface,{cleanup:()=>cleaned++});h.advance(20);h.setReduced(true);
 assert.equal(cleaned,1);assert.equal(await done,true);assert.equal(h.timers.size,0);
});
test('C3 replacing a closing window finishes its cleanup without stale focus return',async()=>{
 const h=harness(),old=h.element(),focus=h.element();let cleaned=0;const done=h.motion.close(old,{cleanup:()=>cleaned++,restoreFocus:focus});
 h.motion.finish(old,{restoreFocus:false});assert.equal(await done,true);assert.equal(cleaned,1);assert.equal(focus.focusCount,0);h.advance(1000);assert.equal(cleaned,1);
});
test('C3 opening end cleanup cannot clear a subsequent closing state',async()=>{
 const h=harness(),surface=h.element();h.motion.open(surface);const done=h.motion.close(surface);surface.emit('animationend',{animationName:'ees-motion-open'});assert.equal(surface.getAttribute('data-ees-motion'),'closing');h.advance(200);assert.equal(await done,true);
});
test('C3 timing reader uses current computed CSS tokens, including seconds, without another timing source',()=>{
 const h=harness(),surface=h.element();h.values['--ees-motion-close']='.31s';h.values['--ees-motion-fast']='40ms';const settings=h.motion.settings(surface);assert.equal(settings.close,310);assert.equal(settings.fast,40);assert.equal(settings.openEasing,h.values['--ees-motion-open-easing']);
});

test('C3 released background interaction wins over a stale close focus return',async()=>{
 const h=harness(),surface=h.element(),focus=h.element(),input=h.element();h.document.activeElement=surface;
 const done=h.motion.close(surface,{restoreFocus:focus});h.document.activeElement=input;h.advance(200);assert.equal(await done,true);assert.equal(focus.focusCount,0);assert.equal(h.document.activeElement,input);
});
