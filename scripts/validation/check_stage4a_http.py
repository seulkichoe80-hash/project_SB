"""Bounded local deny-all HTTP verification; no authentication overrides."""
from pathlib import Path
import os,sys,time,threading,socket,json,urllib.request,urllib.error
root=Path(__file__).resolve().parents[2]
output=Path(sys.argv[1]).resolve()
if output.exists(): raise RuntimeError('Use NEW evidence path')
runtime=root/'work/stage4a/http-verified'
runtime.mkdir(parents=True,exist_ok=True)
os.chdir(runtime);sys.path.insert(0,str(root))
started=time.perf_counter()
import uvicorn
from apps.api.main import create_app
app=create_app(runtime/'isolated-data',parsing_enabled=True)
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
t=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);t.start()
checks=[]
try:
 for _ in range(100):
  if server.started:break
  time.sleep(.02)
 for method,path in [('GET','/documents?active_only=false'),('POST','/documents?filename=synthetic.pdf'),('GET','/documents/d/versions/v'),('GET','/documents/d/versions/v/original'),('GET','/documents/d/versions/v/parsing'),('DELETE','/documents/d')]:
  try:
   urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}'+path,method=method),timeout=2);status=200
  except urllib.error.HTTPError as e:status=e.code
  except urllib.error.URLError:status='BLOCKED'
  checks.append({'method':method,'path':path,'status':status,'result':'PASS' if status==401 else 'BLOCKED' if status=='BLOCKED' else 'FAIL'})
finally:
 server.should_exit=True;t.join(3)
report={'scope':'Actual uvicorn TCP HTTP via urllib; no auth override; NOT authenticated browser integration','checks':checks,'seconds':time.perf_counter()-started}
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
