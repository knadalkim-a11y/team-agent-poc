"""Shared offline HTML/DOM checks; no browser layout or WebUI claims."""

import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


def load_tool(relative_path):
    path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location("ui_test_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_html(html):
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, dict(attrs)))

    parser = Parser()
    parser.feed(html)
    return parser.tags


def embedded_json(html, id="result-data"):
    match = re.search(r'<script\b[^>]*\bid="' + re.escape(id) + r'"[^>]*>(.*?)</script>', html, re.S)
    if match is None:
        raise AssertionError("Embedded result data is missing")
    return json.loads(match.group(1))


_NODE_HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.value='';this.style={};this.attrs={};this.events={};this._text='';this.disabled=false;this.hidden=false;this.className='';this.classList={add:()=>{}};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.children.push(node);return node;}
  replaceChildren(...nodes){this.children=nodes;this._text='';}
  setAttribute(key,value){this.attrs[key]=String(value);}
  getAttribute(key){return this.attrs[key]??null;}
  addEventListener(name,handler){this.events[name]=handler;}
  focus(){document.activeElement=this;}
  getBoundingClientRect(){return {height:900};}
  fire(name){if(name==='click'&&this.disabled)return;this.events[name]({target:this,currentTarget:this});}
}
const elements={};
const get=id=>{
  if(elements[id])return elements[id];
  const initial=input.elements[id]||{tag:'div',attrs:{}};
  const element=new Element(initial.tag);
  element.attrs=initial.attrs;
  for(const key of ['disabled','hidden','readonly'])if(key in initial.attrs)element[key==='readonly'?'readOnly':key]=true;
  elements[id]=element;
  return element;
};
const descendants=(element,tag)=>element.children.flatMap(child=>typeof child==='string'?[]:[...(child.tagName===tag?[child]:[]),...descendants(child,tag)]);
get(input.data_id).textContent=JSON.stringify(input.data);
const messages=[];
const window={addEventListener:()=>{},postMessage:message=>messages.push(message)};
window.parent=input.bridge==='standalone'?window:{postMessage:message=>{
  if(input.bridge==='throw'&&message.type==='input:prompt')throw new Error('Synthetic bridge failure');
  messages.push(message);
}};
const document={getElementById:get,createElement:tag=>new Element(tag),querySelector:()=>get('main'),addEventListener:()=>{},activeElement:null};
const context=vm.createContext({URL,Date,console,document,window,requestAnimationFrame:handler=>handler(),get,messages,descendants});
vm.runInContext(input.script,context);
const result=vm.runInContext(input.action,context);
process.stdout.write(JSON.stringify(result));
"""


def evaluate_html(html, action, bridge="embed", data_id="result-data"):
    if shutil.which("node") is None:
        raise unittest.SkipTest("Node.js is required for offline DOM checks")
    script = re.search(r"<script>(.*?)</script>", html, re.S)
    if script is None:
        raise AssertionError("Inline renderer script is missing")
    result = subprocess.run(
        ["node", "-e", _NODE_HARNESS],
        input=json.dumps({"data": embedded_json(html, data_id), "data_id": data_id,
                          "elements": {attrs["id"]: {"tag": tag, "attrs": attrs}
                                       for tag, attrs in parse_html(html) if "id" in attrs},
                          "script": script.group(1), "action": action, "bridge": bridge}),
        text=True, capture_output=True, timeout=10, check=True,
    )
    return json.loads(result.stdout)
