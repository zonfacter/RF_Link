"""Labelled RFLink recordings. Control with label/command/quit on stdin."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from queue import Queue, Empty
import sys
import threading
import time

import serial

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='COM3')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    output = Path(__file__).resolve().parent / ('capture_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.jsonl')
    queue = Queue()
    def controls():
        for line in sys.stdin:
            queue.put(line.strip())
    threading.Thread(target=controls, daemon=True).start()
    label = 'connection_check'
    with output.open('a', encoding='utf-8', buffering=1) as log, serial.Serial(args.port, 57600, timeout=0.1) as port:
        def record(direction, raw):
            log.write(json.dumps({'time': datetime.now().astimezone().isoformat(),
                                  'label': label, 'direction': direction, 'raw': raw}, ensure_ascii=False) + '\n')
        def send(raw):
            port.write((raw + '\n').encode('ascii'))
            record('tx', raw)
            print('COMMAND ' + raw, flush=True)
        print('RECORDING ' + str(output), flush=True)
        time.sleep(2)
        send('10;RFDEBUG=ON;')
        try:
            running = True
            while running:
                while True:
                    try:
                        control = queue.get_nowait()
                    except Empty:
                        break
                    if control == 'quit':
                        running = False
                        break
                    if control.startswith('label '):
                        label = control[6:]
                        record('label', label)
                        print('LABEL ' + label, flush=True)
                    elif control.startswith('command '):
                        send(control[8:])
                line = port.readline()
                if line:
                    raw = line.decode('utf-8', errors='replace').strip()
                    record('rx', raw)
                    print(raw[:160], flush=True)
        finally:
            send('10;RFDEBUG=OFF;')
    print('CLOSED ' + str(output), flush=True)

if __name__ == '__main__':
    main()
