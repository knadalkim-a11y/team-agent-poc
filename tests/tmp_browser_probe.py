"""TEMPORARY investigation probe; delete before any merge.

Repeats one real browser test and, when it fails, prints what the page did
(focus moves, key presses, menu and dialog state changes, repaints, requests)
so the failing order of events can be read from the job log.
"""
import argparse, json, os, sys, time, unittest, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tests'))
os.chdir(ROOT)
parser = argparse.ArgumentParser()
parser.add_argument('test'); parser.add_argument('--rounds', type=int, default=10)
parser.add_argument('--rate', type=float, default=1); parser.add_argument('--out', required=True)
parser.add_argument('--probe', action='store_true')
parser.add_argument('--raf-delay', type=int, default=0)
parser.add_argument('--fetch-delay', type=int, default=0)
parser.add_argument('--dump-pass', action='store_true')
parser.add_argument('--css', default='')
parser.add_argument('--tail', type=int, default=330)
parser.add_argument('--menu-close-range', default='')
args = parser.parse_args()
module_name, class_name, method = args.test.split('.')
module = __import__(module_name)
case = getattr(module, class_name)
out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
PROBE = r"""(()=>{ if(window.__probe)return; const log=[]; const t=()=>Math.round(performance.now()*10)/10;
 const id=e=>e? (e.tagName+(e.id?'#'+e.id:'')+(e.dataset?.authorAction?'[a='+e.dataset.authorAction+']':'')+(e.dataset?.action?'[act='+e.dataset.action+']':'')+(e.className&&typeof e.className==='string'?'.'+e.className.split(' ').slice(0,2).join('.'):'')):'null';
 window.__probe={log};
 document.addEventListener('focusin',e=>log.push([t(),'focusin',id(e.target)]),true);
 document.addEventListener('focusout',e=>log.push([t(),'focusout',id(e.target),'->',id(e.relatedTarget)]),true);
 document.addEventListener('keydown',e=>log.push([t(),'keydown',e.key,id(e.target),'active='+id(document.activeElement)]),true);
 document.addEventListener('click',e=>{const row=[t(),'click',id(e.target),'trusted='+e.isTrusted];log.push(row);queueMicrotask(()=>row.push('prevented='+e.defaultPrevented,'active='+id(document.activeElement)));},true);
 document.addEventListener('toggle',e=>log.push([t(),'toggle',id(e.target),'open='+e.target.open]),true);
 new MutationObserver(rs=>{for(const r of rs){ if(r.type==='childList'){const where=id(r.target); if(/ees-work|ew-|DETAILS|SECTION|ASIDE/.test(where)||r.target.id==='ees-work-designer'||r.target.querySelector?.('#ees-work-designer')) log.push([t(),'childList',where,'+'+r.addedNodes.length,'-'+r.removedNodes.length,'active='+id(document.activeElement)]);}
   else log.push([t(),'attr',r.attributeName,id(r.target),String(r.target.getAttribute(r.attributeName)),'active='+id(document.activeElement)]);}}).observe(document,{subtree:true,childList:true,attributes:true,attributeFilter:['open','inert','data-ees-motion','data-ees-chat-state','data-author-split']});
 const raf=()=>{requestAnimationFrame(raf);}; })()"""
original_setup = case.setUp
def set_up(self):
    original_setup(self)
    if args.rate != 1:
        self.browser.call('Emulation.setCPUThrottlingRate', {'rate': args.rate})
    if args.raf_delay:
        slow = "(()=>{if(window.__slowRaf)return;window.__slowRaf=true;const raf=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=cb=>raf(()=>setTimeout(()=>cb(performance.now()),%d));})()" % args.raf_delay
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': slow})
        self.browser.evaluate(slow)
    if args.probe:
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': PROBE})
        self.browser.evaluate(PROBE)
    if args.menu_close_range:
        import random
        low, high = [int(x) for x in args.menu_close_range.split(',')]
        self._menu_close = random.randint(low, high)
        case._last_menu_close = self._menu_close
        args.css = '.ew-procedure-menu > div{--ees-motion-close:%dms}' % self._menu_close
        css = "(()=>{const add=()=>{if(!document.head)return setTimeout(add,5);let s=document.getElementById('probe-css');if(!s){s=document.createElement('style');s.id='probe-css';document.head.append(s);}s.textContent=%s;};add();})()" % json.dumps(args.css)
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': css})
        self.browser.evaluate(css)
    elif args.css:
        css = "(()=>{if(window.__probeCss)return;const add=()=>{if(!document.head)return setTimeout(add,5);window.__probeCss=true;const s=document.createElement('style');s.textContent=%s;document.head.append(s);};add();})()" % json.dumps(args.css)
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': css})
        self.browser.evaluate(css)
    if args.fetch_delay:
        slow = "(()=>{if(window.__slowFetch)return;window.__slowFetch=true;const f=window.fetch.bind(window);let n=0;window.fetch=(...a)=>{const id=++n,u=String(a[0]?.url||a[0]).replace(location.origin,'').slice(0,90),t=()=>Math.round(performance.now()*10)/10;window.__probe?.log.push([t(),'fetch-start',id,u]);return new Promise(r=>setTimeout(r,%d)).then(()=>f(...a)).then(x=>{window.__probe?.log.push([t(),'fetch-end',id,u,x.status]);return x;});};})()" % args.fetch_delay
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': slow})
        self.browser.evaluate(slow)
    if args.probe:
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': PROBE})
        self.browser.evaluate(PROBE)
case.setUp = set_up
original_test = getattr(case, method)
def wrapped(self):
    try:
        original_test(self)
        if args.dump_pass:
            data = self.browser.evaluate("window.__probe?.log||null")
            (out / ('pass-%d.json' % wrapped.round)).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except BaseException:
        try:
            data = self.browser.evaluate("(()=>{try{window.__c3?.stop();}catch(e){};return {c3:window.__c3?.evidence?{inputs:window.__c3.evidence.inputs,events:window.__c3.evidence.events.slice(-80),frames:window.__c3.evidence.frames.slice(-200).map(f=>({t:f.t,focus:f.focus,nodes:f.nodes.map(n=>({kind:n.kind,state:n.state,id:n.id,inert:n.inert}))}))}:null,probe:window.__probe?.log||null,active:document.activeElement?.outerHTML?.slice(0,300),menu:document.querySelector('.ew-procedure-menu')?.outerHTML?.slice(0,900),heading:document.querySelector('.ew-author-definition-head')?.innerText?.slice(0,200),designer:document.querySelector('#ees-work-designer')?.innerText?.slice(0,700),list:[...document.querySelectorAll('[data-author-action=open]')].map(e=>(e.dataset.id||'')+':'+e.textContent.trim().slice(0,40)),now:performance.now()};})()")
            (out / ('failure-%d.json' % wrapped.round)).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            rows = (data.get('probe') or [])[-args.tail:]
            print('PROBE_FAILURE round=%d now=%s active=%s' % (wrapped.round, data.get('now'), (data.get('active') or '')[:160].replace('\n', ' ')), flush=True)
            for row in rows:
                print('PROBE_ROW ' + ' '.join(str(item) for item in row)[:230], flush=True)
            print('PROBE_MENU ' + (data.get('menu') or '')[:700].replace('\n', ' '), flush=True)
            print('PROBE_HEADING ' + repr(data.get('heading')), flush=True)
            print('PROBE_DESIGNER ' + repr(data.get('designer')), flush=True)
            print('PROBE_LIST ' + repr(data.get('list')), flush=True)
        except Exception as error:
            (out / ('failure-%d.txt' % wrapped.round)).write_text('evidence unavailable: %r' % (error,), encoding='utf-8')
        raise
wrapped.round = 0
wrapped.__name__ = method
setattr(case, method, wrapped)
failed = 0; rows = []
for index in range(1, args.rounds + 1):
    wrapped.round = index
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(unittest.TestSuite([case(method)]))
    ok = result.wasSuccessful()
    rows.append((index, ok, round(time.monotonic() - started, 1)))
    if not ok:
        failed += 1
        text = stream.getvalue()
        (out / ('run-%d.log' % index)).write_text(text, encoding='utf-8')
        line = next((l for l in text.splitlines() if 'AssertionError' in l or 'Error:' in l), '')
        print('round', index, 'FAIL', 'menu_close=%s' % getattr(case, '_last_menu_close', ''), line[:200], flush=True)
print('DONE', args.test, 'fetch_delay', args.fetch_delay, 'raf_delay', args.raf_delay, 'rate', args.rate, 'rounds', args.rounds, 'failed', failed, 'seconds', [r[2] for r in rows], flush=True)
