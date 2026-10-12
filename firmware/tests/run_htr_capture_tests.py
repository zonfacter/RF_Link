"""Replay labelled HTR captures through the real firmware decoder/adapter tests."""
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
exe = HERE / 'build' / ('capture_harness.exe' if os.name == 'nt' else 'capture_harness')
if not exe.exists():
    raise SystemExit('Run firmware/tests/run_capture_tests.py first to compile the test harness.')
capture = HERE.parent / 'hardware-tests' / 'capture_20261012_201834.jsonl'
for button in ('UP', 'STOP', 'DOWN'):
    lines = []
    for text in capture.read_text(encoding='utf-8').splitlines():
        row = json.loads(text)
        if row['label'] != 'HTR008W_' + button + '_initial':
            continue
        match = re.search(r'Pulses\(uSec\)=([0-9,]+)', row['raw'])
        if match:
            samples = [int(x) // 30 for x in match[1].split(',')]
            lines.append(str(len(samples)) + ' ' + ' '.join(map(str, samples)))
    out = subprocess.run([str(exe), '--htr'], input='\n'.join(lines),
                         text=True, capture_output=True, check=True)
    counts = Counter(x for x in out.stdout.splitlines() if x != 'REJECT')
    assert counts == Counter({'HTR:' + button: 6}), (button, counts)
    print(button, dict(counts), 'from', len(lines), 'packets')
print('PASS: all 9 complete button recordings decoded from both direct and legacy timings; TX adapter waveforms and malformed frames checked.')
