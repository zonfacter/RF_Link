"""Replay complete data frames with missing sync using the actual RX plugin."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime

HERE = Path(__file__).resolve().parent
compiler = shutil.which('g++') or 'C:/msys64/ucrt64/bin/g++.exe'
exe = HERE / 'build' / 'clipped_nobily_harness.exe'
env = os.environ.copy()
env['PATH'] = str(Path(compiler).resolve().parent) + os.pathsep + env.get('PATH','')
subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-static', '-I',
                str(HERE.parent / 'include'), str(HERE / 'clipped_nobily_harness.cpp'),
                '-o', str(exe)], check=True, env=env)
records = [json.loads(line) for line in (HERE / 'nobily_missing_sync.jsonl').read_text().splitlines()]
start = datetime.fromisoformat(records[0]['time'])
inputs = []
for record in records:
    samples = [int(value)//30 for value in re.search(r'Pulses\(uSec\)=([0-9,]+)', record['raw'])[1].split(',')]
    timestamp = 10000 + round((datetime.fromisoformat(record['time']) - start).total_seconds()*1000)
    inputs.append(f'{timestamp} {len(samples)} ' + ' '.join(map(str, samples)))
result = subprocess.run([str(exe)], input='\n'.join(inputs)+'\n', text=True, capture_output=True, check=True)
lines = result.stdout.splitlines()
assert lines and all('ID=98461A;SWITCH=42;' in line for line in lines), lines
assert {re.search(r'RAW=([0-9A-F]+)',line)[1] for line in lines} == {'11','33','55','3C'}, lines
assert len(lines) < len(records), 'First unconfirmed frames must not be published'
print(f'PASS: {len(records)} measured clipped frames, {len(lines)} repeat-confirmed outputs; UP/DOWN/STOP and unknown raw commands preserved.')
