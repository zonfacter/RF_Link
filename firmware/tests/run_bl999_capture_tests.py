"""Compile actual BL999 decoder/plugin and replay measured sensor frames."""
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
compiler=os.environ.get('CXX') or shutil.which('g++')
if not compiler and Path('C:/msys64/ucrt64/bin/g++.exe').exists():
    compiler='C:/msys64/ucrt64/bin/g++.exe'
if not compiler:raise SystemExit('g++ required; configure CXX.')
build=HERE/'build';build.mkdir(exist_ok=True)
exe=build/('bl999_harness.exe' if os.name=='nt' else 'bl999_harness')
args=[compiler,'-std=c++11','-Wall','-Wextra','-I',str(HERE.parent/'include'),str(HERE/'bl999_harness.cpp'),'-o',str(exe)]
if os.name=='nt':args.append('-static')
env=os.environ.copy();env['PATH']=str(Path(compiler).resolve().parent)+os.pathsep+env.get('PATH','')
subprocess.run(args,check=True,env=env)
fixture=json.loads((HERE/'bl999_measured_pulses.json').read_text(encoding='utf-8'))
frames=fixture['frames']
data='\n'.join(str(len(frame))+' '+' '.join(map(str,frame)) for frame in frames)+'\n'
result=subprocess.run([str(exe)],input=data,text=True,capture_output=True,check=True)
lines=result.stdout.splitlines()
assert lines==['20;00;BL999;ID=0108;CHAN=1;TEMP=00DD;HUM=31;BAT=OK;'],lines
print('PASS: two measured sensor frames, checksum, negative temperature, truncated/invalid rejection, repeated-frame confirmation and suppression.')
