from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import urllib.request,hashlib,json,zipfile,os
assets=[{'name':'upstream','url':'https://files.pythonhosted.org/packages/4c/e4/28abecd6b75fa6fa40ae181d2fa9f57593e26d13309c90531dee5b4acc28/open_webui-0.11.3-py3-none-any.whl','path':'dist/upstream/open_webui-0.11.3-py3-none-any.whl','sha256':'8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547','bytes':146072797},{'name':'chrome','url':'https://storage.googleapis.com/chrome-for-testing-public/153.0.8010.52/linux64/chrome-headless-shell-linux64.zip','path':'dist/recovery/chrome-headless-shell-linux64.zip','bytes':119702187}]
def download(item):
 p=Path(item['path']);p.parent.mkdir(parents=True,exist_ok=True)
 with urllib.request.urlopen(item['url'],timeout=60) as response,p.open('wb') as out:
  while chunk:=response.read(1024*1024):out.write(chunk)
 b=p.read_bytes();digest=hashlib.sha256(b).hexdigest();assert len(b)==item['bytes']
 if 'sha256'in item:assert digest==item['sha256']
 result={**item,'downloaded_sha256':digest,'downloaded_at':datetime.now(timezone.utc).isoformat(),'tls_verification':'default enabled'}
 if item['name']=='chrome':
  destination=Path('dist/runtime/tools')
  with zipfile.ZipFile(p) as z:
   for info in z.infolist():
    relative=Path(info.filename);assert not relative.is_absolute() and '..' not in relative.parts
    target=destination/relative
    if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
    mode=info.external_attr>>16
    if mode:target.chmod(mode&0o777)
  result['executable']='dist/runtime/tools/chrome-headless-shell-linux64/chrome-headless-shell'
  result['executable_sha256']=hashlib.sha256(Path(result['executable']).read_bytes()).hexdigest()
 return result
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(download,assets))
Path('dist/recovery/downloads.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,indent=2))
