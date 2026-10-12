"""Read-only RF reception check after BUILD 0B upload; sends no RF commands."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import serial

parser=argparse.ArgumentParser()
parser.add_argument('--port',default='COM3')
parser.add_argument('--seconds',type=int,default=120)
args=parser.parse_args()
records=[]
with serial.Serial(args.port,57600,timeout=0.25,write_timeout=2) as port:
    start=time.monotonic()
    queried=False
    while time.monotonic()-start < args.seconds:
        if not queried and time.monotonic()-start>=3:
            for command in ('10;VERSION;','10;PING;','10;RFUDEBUG=ON;'):
                port.write((command+'\n').encode('ascii'))
            queried=True
        raw=port.readline().decode('ascii',errors='replace').strip()
        if raw:
            records.append({'time':datetime.now().astimezone().isoformat(),'direction':'rx','raw':raw})
            if ';DEBUG;' not in raw:print(raw,flush=True)
            if ';BL999;' in raw:
                break
    port.write(b'10;RFUDEBUG=OFF;\n')
result={'port':args.port,'build0b_confirmed':any('BUILD=0b;' in r['raw'] for r in records),
        'pong_confirmed':any(';PONG;' in r['raw'] for r in records),
        'sensor_received':any(';BL999;' in r['raw'] for r in records),'records':records}
Path(__file__).with_name('COM3_build0B_sensor_check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({key:value for key,value in result.items() if key!='records'}),flush=True)
if not result['build0b_confirmed'] or not result['pong_confirmed']:raise SystemExit('Version/PING check failed')
