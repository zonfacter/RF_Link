"""Laptop control, labelled capture and external device assignment for the custom RFLink firmware."""
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent
BUTTONS = {'HOCH': 'UP', 'STOP': 'STOP', 'RUNTER': 'DOWN'}

def control_command(protocol, device_id, channel, button):
    command = BUTTONS.get(button, button)
    if command not in ('UP', 'DOWN', 'STOP'):
        raise ValueError('Unbekannter Befehl')
    value = int(device_id, 16)
    if protocol == 'Nobily':
        ch = int(channel)
        if not 0 <= value <= 0xFFFFFF or not 0 <= ch <= 5:
            raise ValueError('Nobily: ID mit maximal 6 Hexstellen, Kanal 0–5')
        return f'10;ShutterRemote40;{value:06X};{0x40 + ch:02X};{command};'
    if protocol == 'HTR008W':
        if value != 1:
            raise ValueError('HTR008W verwendet die lokale ID 000001')
        return f'10;HTR008W;000001;00;{command};'
    raise ValueError('Unbekanntes Protokoll')

class App:
    def __init__(self, root):
        self.root = root
        root.title('RFLink – Testen und Zuordnen')
        root.geometry('1000x760')
        root.minsize(850, 650)
        self.events = queue.Queue()
        self.port = None
        self.ready = False
        self.closing = False
        self.write_lock = threading.Lock()
        self.stop_job = None
        self.stop_command = None
        self.records = []
        self.port_var = tk.StringVar(value='COM3')
        self.status = tk.StringVar(value='Nicht verbunden · 57600 Baud')
        self.protocol = tk.StringVar(value='Nobily')
        self.device_id = tk.StringVar(value='98461A')
        self.channel = tk.StringVar(value='1')
        self.auto_stop = tk.BooleanVar(value=True)
        self.seconds = tk.StringVar(value='2')
        self.label = tk.StringVar(value='Freier Test')
        self.profile_name = tk.StringVar(value='Rollladen')
        self.profile_status = tk.StringVar(value='Zuordnung wird nur auf diesem Laptop gespeichert.')
        self.profiles = {}
        self.last_received = None
        self.raw = tk.StringVar(value='10;PING;')
        self.build_ui()
        self.refresh_ports()
        self.restore_settings()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
        style.configure('Drive.TButton', font=('Segoe UI', 12, 'bold'), padding=12)
        body = ttk.Frame(self.root, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='RFLink · Testen und Zuordnen', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, textvariable=self.status).pack(anchor='w', pady=(3, 12))
        connection = ttk.Frame(body)
        connection.pack(fill='x', pady=(0, 12))
        self.ports_box = ttk.Combobox(connection, textvariable=self.port_var, width=16, state='readonly')
        self.ports_box.pack(side='left')
        ttk.Button(connection, text='Ports suchen', command=self.refresh_ports).pack(side='left', padx=6)
        self.connect_btn = ttk.Button(connection, text='Verbinden', command=self.toggle_connection)
        self.connect_btn.pack(side='left')
        ttk.Button(connection, text='PING', command=lambda: self.send('10;PING;')).pack(side='left', padx=6)
        controls = ttk.LabelFrame(body, text='Rollladen steuern', padding=12)
        controls.pack(fill='x')
        row = ttk.Frame(controls)
        row.pack(fill='x')
        ttk.Label(row, text='Protokoll').pack(side='left')
        box = ttk.Combobox(row, textvariable=self.protocol, values=['Nobily', 'HTR008W'], state='readonly', width=12)
        box.pack(side='left', padx=(6, 16))
        box.bind('<<ComboboxSelected>>', self.protocol_changed)
        ttk.Label(row, text='ID (Hex)').pack(side='left')
        ttk.Entry(row, textvariable=self.device_id, width=10).pack(side='left', padx=(6, 16))
        ttk.Label(row, text='Kanal').pack(side='left')
        ttk.Combobox(row, textvariable=self.channel, values=['0', '1', '2', '3', '4', '5'], width=4, state='readonly').pack(side='left', padx=6)
        ttk.Label(row, text='0 = alle Nobily-Kanäle').pack(side='left', padx=8)
        row = ttk.Frame(controls)
        row.pack(fill='x', pady=12)
        self.drive_buttons = []
        for caption in ('HOCH', 'STOP', 'RUNTER'):
            button = ttk.Button(row, text=caption, style='Drive.TButton', command=lambda c=caption: self.drive(c), state='disabled')
            button.pack(side='left', expand=True, fill='x', padx=4)
            self.drive_buttons.append(button)
        row = ttk.Frame(controls)
        row.pack(fill='x')
        ttk.Checkbutton(row, text='Automatisch STOP nach', variable=self.auto_stop).pack(side='left')
        ttk.Spinbox(row, from_=1, to=30, textvariable=self.seconds, width=5).pack(side='left', padx=6)
        ttk.Label(row, text='Sekunden · OK bestätigt den Mega, nicht die Motorreaktion.').pack(side='left')
        profiles = ttk.LabelFrame(body, text='Geraete auf dem Laptop zuordnen', padding=12)
        profiles.pack(fill='x', pady=12)
        row = ttk.Frame(profiles)
        row.pack(fill='x')
        self.profile_box = ttk.Combobox(row, textvariable=self.profile_name, width=24)
        self.profile_box.pack(side='left')
        self.profile_box.bind('<<ComboboxSelected>>', self.select_profile)
        ttk.Button(row, text='Letzten Empfang uebernehmen', command=self.use_received).pack(side='left', padx=6)
        ttk.Button(row, text='Zuordnung lokal speichern', command=self.save_profile).pack(side='left')
        ttk.Label(profiles, textvariable=self.profile_status, wraplength=890).pack(anchor='w', pady=6)
        ttk.Label(profiles, text='Nobily: Geraete-ID aus dem Funktelegramm. HTR008W: 000001 ist ein lokaler Alias fuer die getestete Fernbedienung.', wraplength=890).pack(anchor='w')
        logging = ttk.Frame(body)
        logging.pack(fill='x')
        ttk.Label(logging, text='Aufnahme-Label').pack(side='left')
        ttk.Entry(logging, textvariable=self.label, width=26).pack(side='left', padx=6)
        ttk.Button(logging, text='RFDEBUG an', command=lambda: self.send('10;RFDEBUG=ON;')).pack(side='left', padx=3)
        ttk.Button(logging, text='RFDEBUG aus', command=lambda: self.send('10;RFDEBUG=OFF;')).pack(side='left', padx=3)
        ttk.Button(logging, text='Export JSONL', command=self.export).pack(side='right')
        frame = ttk.Frame(body)
        frame.pack(fill='both', expand=True, pady=8)
        self.log = tk.Text(frame, font=('Consolas', 10), background='#172233', foreground='#e3edf8', wrap='none', height=9, state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, command=self.log.yview)
        scroll.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scroll.set)
        rawrow = ttk.Frame(body)
        rawrow.pack(fill='x')
        ttk.Entry(rawrow, textvariable=self.raw).pack(side='left', fill='x', expand=True)
        ttk.Button(rawrow, text='Seriellen Befehl senden', command=lambda: self.send(self.raw.get())).pack(side='left', padx=6)

    def restore_settings(self):
        try:
            values = json.loads((ROOT / 'rflink_test_settings.json').read_text(encoding='utf-8'))
            for name in ('port_var', 'protocol', 'device_id', 'channel'):
                if name in values:
                    getattr(self, name).set(values[name])
            self.profiles = values.get('profiles', {})
            self.profile_box['values'] = list(self.profiles)
            if self.protocol.get() not in ('Nobily', 'HTR008W'):
                self.protocol.set('Nobily')
                self.protocol_changed()
        except (OSError, ValueError):
            pass

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.ports_box['values'] = ports
        if self.port_var.get() not in ports and ports:
            self.port_var.set(ports[0])

    def protocol_changed(self, _=None):
        self.device_id.set('98461A' if self.protocol.get() == 'Nobily' else '000001')
        self.channel.set('1' if self.protocol.get() == 'Nobily' else '0')

    def toggle_connection(self):
        if self.port is not None:
            self.disconnect()
            return
        port_name = self.port_var.get()
        self.connect_btn.configure(state='disabled')
        self.status.set('Verbinde ' + port_name + ' …')
        def connect():
            try:
                port = serial.Serial(port_name, 57600, timeout=0.2, write_timeout=2)
                if self.closing:
                    port.close()
                    return
                self.port = port
                threading.Thread(target=self.reader, args=(port,), daemon=True).start()
                time.sleep(2)
                if self.port is port:
                    self.events.put(('connected', port_name))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=connect, daemon=True).start()

    def reader(self, port):
        buffer = b''
        try:
            while self.port is port:
                data = port.read(port.in_waiting or 1)
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    self.events.put(('rx', line.decode('utf-8', errors='replace').strip()))
                if len(buffer) > 8192:
                    self.events.put(('rx', buffer.decode('utf-8', errors='replace')))
                    buffer = b''
        except Exception as exc:
            if self.port is port:
                self.events.put(('error', str(exc)))

    def send(self, text):
        if not self.ready or self.port is None:
            self.append('info', 'Bitte zuerst verbinden.')
            return False
        text = text.strip()
        if not text.startswith('10;') or len(text) > 59 or '\n' in text or '\r' in text:
            messagebox.showerror('Befehl', 'Ein RFLink-Befehl beginnt mit 10; und hat maximal 59 Zeichen.')
            return False
        try:
            with self.write_lock:
                self.port.write((text + '\n').encode('ascii'))
            self.append('tx', text)
            return True
        except Exception as exc:
            self.events.put(('error', str(exc)))
            return False

    def drive(self, button):
        try:
            cmd = control_command(self.protocol.get(), self.device_id.get(), self.channel.get(), button)
            stop = control_command(self.protocol.get(), self.device_id.get(), self.channel.get(), 'STOP')
            seconds = float(self.seconds.get())
            if not 1 <= seconds <= 30:
                raise ValueError('Automatischer STOP: 1–30 Sekunden')
        except ValueError as exc:
            messagebox.showerror('Eingabe', str(exc))
            return
        previous_stop = self.stop_command
        self.cancel_stop()
        if previous_stop and previous_stop != cmd:
            self.send(previous_stop)
        self.stop_command = None
        if self.send(cmd) and button != 'STOP':
            self.stop_command = stop
            if self.auto_stop.get():
                self.stop_job = self.root.after(int(seconds * 1000), self.timed_stop)

    def timed_stop(self):
        self.stop_job = None
        if self.stop_command:
            self.send(self.stop_command)
        self.stop_command = None

    def cancel_stop(self):
        if self.stop_job:
            self.root.after_cancel(self.stop_job)
        self.stop_job = None

    def use_received(self):
        if self.last_received:
            for key, value in self.last_received.items():
                getattr(self, key).set(value)
            self.profile_status.set('Empfangenes Geraet uebernommen; einen Namen vergeben und lokal speichern.')
        else:
            self.profile_status.set('Zuerst eine Taste einer unterstuetzten Fernbedienung druecken.')

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            return
        try:
            control_command(self.protocol.get(), self.device_id.get(), self.channel.get(), 'STOP')
        except ValueError as exc:
            self.profile_status.set(str(exc))
            return
        self.profiles[name] = {key: getattr(self, key).get() for key in ('protocol', 'device_id', 'channel')}
        self.profile_box['values'] = list(self.profiles)
        self.write_settings()
        self.profile_status.set('Zuordnung auf dem Laptop gespeichert: ' + name)

    def select_profile(self, _=None):
        for key, value in self.profiles.get(self.profile_name.get(), {}).items():
            getattr(self, key).set(value)

    def write_settings(self):
        values = {name: getattr(self, name).get() for name in ('port_var', 'protocol', 'device_id', 'channel')}
        values['profiles'] = self.profiles
        (ROOT / 'rflink_test_settings.json').write_text(json.dumps(values, indent=2), encoding='utf-8')

    def append(self, direction, raw):
        record = {'time': datetime.now().astimezone().isoformat(), 'label': self.label.get(), 'direction': direction, 'raw': raw}
        self.records.append(record)
        self.log.configure(state='normal')
        self.log.insert('end', f'{record["time"][11:19]} {direction.upper():4} {raw}\n')
        self.log.see('end')
        self.log.configure(state='disabled')
        if direction == 'rx':
            parts = raw.split(';')
            fields = dict(part.split('=', 1) for part in parts if '=' in part)
            try:
                brand = parts[2]
                channel = int(fields['SWITCH'], 16)
                if brand == 'ShutterRemote40' and 0x40 <= channel <= 0x45:
                    self.last_received = {'protocol':'Nobily', 'device_id':fields['ID'], 'channel':str(channel - 0x40)}
                elif brand == 'HTR008W' and fields['ID'] == '000001' and channel == 0:
                    self.last_received = {'protocol':'HTR008W', 'device_id':'000001', 'channel':'0'}
                else:
                    return
                self.profile_status.set('Geraet empfangen: ' + str(self.last_received))
            except (IndexError, KeyError, ValueError):
                pass

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'connected':
                    self.ready = True
                    self.status.set('Verbunden mit ' + value + ' · 57600 Baud')
                    self.connect_btn.configure(text='Trennen', state='normal')
                    for button in self.drive_buttons:
                        button.configure(state='normal')
                    self.send('10;PING;')
                    self.send('10;VERSION;')
                elif kind == 'error':
                    self.append('error', value)
                    self.disconnect()
                else:
                    self.append(kind, value)
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self.poll)

    def disconnect(self):
        self.cancel_stop()
        if self.stop_command:
            self.send(self.stop_command)
        self.stop_command = None
        if self.ready:
            self.send('10;RFDEBUG=OFF;')
        port, self.port = self.port, None
        self.ready = False
        if port:
            port.close()
        self.status.set('Nicht verbunden · 57600 Baud')
        self.connect_btn.configure(text='Verbinden', state='normal')
        for button in self.drive_buttons:
            button.configure(state='disabled')

    def export(self):
        destination = filedialog.asksaveasfilename(defaultextension='.jsonl', initialfile='rflink_test.jsonl', filetypes=[('JSONL', '*.jsonl')])
        if destination:
            Path(destination).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in self.records), encoding='utf-8')

    def close(self):
        self.closing = True
        self.disconnect()
        self.write_settings()
        if self.records:
            folder = ROOT / 'testprogramm_logs'
            folder.mkdir(exist_ok=True)
            (folder / ('session_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in self.records), encoding='utf-8')
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
