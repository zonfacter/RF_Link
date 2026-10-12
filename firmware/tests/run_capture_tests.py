"""Compile the real firmware codec and replay the existing RFDEBUG captures."""
from pathlib import Path
from collections import Counter
import os
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPECTED = {
    '10xdown_ch3_QRFDebug_PluginOff.csv': {'98461A4433': 10, '98461A443C': 10},
    '10xdown_ch4_QRFDebug_PluginOff.csv': {'98461A4455': 10},
    '10xstop_ch3_QRFDebug_PluginOff.csv': {'98461A4333': 10, '98461A433C': 9},
    '10xup_ch3_QRFDebug.csv': {'98461A4311': 10, '98461A431E': 8},
    '10xup_ch3_QRFDebug_PluginOff.csv': {'98461A4355': 10},
    'logs/5xDown_CH4_RFDebug.csv': {'98461A4533': 10, '98461A453C': 15},
    'logs/5xDown_CH5_RFDebug.csv': {'98461A4555': 15},
    'logs/5xStop_CH4_RFDebug.csv': {'98461A4433': 12, '98461A443C': 17},
    'logs/5xStop_CH5_RFDebug.csv': {'98461A4511': 10, '98461A451E': 12},
    'logs/5xUp_CH4_RFDebug.csv': {'98461A4455': 18},
    'logs/5xUp_CH5_RFDebug.csv': {'98461A4455': 9, '98461A4511': 6, '98461A451E': 8, '98461A4555': 9},
    'firmware/hardware-tests/capture_20261012_201504.jsonl': {'98461A4155': 6},
}

def main():
    compiler = os.environ.get('CXX') or shutil.which('g++')
    if not compiler:
        for candidate in ('C:/msys64/ucrt64/bin/g++.exe', 'C:/msys64/mingw64/bin/g++.exe'):
            if Path(candidate).exists():
                compiler = candidate
                break
    if not compiler:
        raise SystemExit('C++ compiler required. Set CXX to g++.')
    build = HERE / 'build'
    build.mkdir(exist_ok=True)
    exe = build / ('capture_harness.exe' if os.name == 'nt' else 'capture_harness')
    command = [compiler, '-std=c++11', '-Wall', '-Wextra', '-I', str(HERE.parent / 'include'),
               '-I', str(HERE / 'stubs'), str(HERE / 'capture_harness.cpp'), '-o', str(exe)]
    if os.name == 'nt':
        command.append('-static')
    compiler_env = os.environ.copy()
    compiler_env['PATH'] = str(Path(compiler).resolve().parent) + os.pathsep + compiler_env.get('PATH', '')
    subprocess.run(command, check=True, env=compiler_env)
    total = 0
    debug_total = 0
    for filename, expected in EXPECTED.items():
        records = []
        for line in (ROOT / filename).read_text(encoding='utf-8').splitlines():
            if filename.endswith('.jsonl'):
                import json
                line = json.loads(line)['raw']
            match = re.search(r'Pulses\(uSec\)=([0-9a-fA-F,]+)', line)
            if not match:
                continue
            text = match[1]
            if ',' in text:
                samples = [int(x) // 30 for x in text.split(',') if x]
            elif len(text) % 2 == 0:
                samples = [int(text[i:i+2], 16) for i in range(0, len(text), 2)]
            else:
                continue
            if any(x > 255 for x in samples):
                raise AssertionError('Pulse does not fit RFLink byte representation')
            records.append(str(len(samples)) + ' ' + ' '.join(map(str, samples)))
        result = subprocess.run([str(exe)], input='\n'.join(records) + '\n',
                                text=True, capture_output=True, check=True)
        decoded = Counter(x for x in result.stdout.splitlines() if x != 'REJECT')
        assert decoded == Counter(expected), (filename, decoded, expected)
        debug_total += len(records)
        total += sum(decoded.values())
        print(f'{filename}: {sum(decoded.values())}/{len(records)} decoded; {dict(decoded)}')
    # Earlier multi-frame signal family must not be misidentified as this protocol.
    legacy_records = []
    for filename in ('Fernbedienung Log RAW.txt', 'Fernbedienung sende Log.txt'):
        for line in (HERE.parent / 'legacy' / filename).read_text(encoding='utf-8').splitlines():
            match = re.search(r'Pulses\(uSec\)=([0-9,]+)', line)
            if match:
                samples = [int(x) // 30 for x in match[1].split(',') if x]
                legacy_records.append(str(len(samples)) + ' ' + ' '.join(map(str, samples)))
    result = subprocess.run([str(exe)], input='\n'.join(legacy_records) + '\n',
                            text=True, capture_output=True, check=True)
    assert all(x == 'REJECT' for x in result.stdout.splitlines()), result.stdout
    print(f'PASS: {total}/{debug_total} captured packets decoded; '
          f'{len(legacy_records)} legacy packets rejected; '
          '65536 channel/command round trips and malformed-frame checks.')

if __name__ == '__main__':
    main()
