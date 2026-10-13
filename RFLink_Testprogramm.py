"""Laptop control, labelled capture and external device assignment for the custom RFLink firmware."""
from datetime import datetime
from collections import deque
import json
from pathlib import Path
import queue
import threading
import time
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
from serial.tools import list_ports
from rflink_devices import DeviceRegistry, Frame, parse_frame, control_target, measurement_text, raw_signal, device_measurement_text

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
    def __init__(self, root, storage_dir=None):
        self.root = root
        self.storage_dir = Path(storage_dir) if storage_dir is not None else ROOT
        root.title('RFLink – Testen und Zuordnen')
        root.geometry('1120x740')
        root.minsize(950, 650)
        self.events = queue.Queue()
        self.port = None
        self.ready = False
        self.closing = False
        self.write_lock = threading.Lock()
        self.stop_job = None
        self.stop_command = None
        self.records = deque(maxlen=5000)
        self.session_path = None
        self.registry = DeviceRegistry(self.storage_dir / 'rflink_devices.json')
        self.registry_error = ''
        try:
            self.registry.load()
        except (OSError, ValueError) as exc:
            self.registry_error = str(exc)
        self.scanning = False
        self.scan_deadline = None
        self.raw_signals = {}
        self.scan_raw_count = 0
        self.scan_decoded_count = 0
        self.latest_frame = None
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
        self.scan_duration = tk.StringVar(value='5 Minuten')
        self.capture_raw = tk.BooleanVar(value=False)
        self.device_filter = tk.StringVar()
        self.device_status = tk.StringVar(value='Aufnahme starten, um neue Geräte lokal zu erfassen. Bekannte Geräte aktualisieren sich bei Empfang.')
        self.activity_status = tk.StringVar(value='Noch keine Aufnahme: Geräte benötigen decodierte Meldungen mit ID.')
        self.edit_name = tk.StringVar()
        self.edit_room = tk.StringVar()
        self.edit_notes = tk.StringVar()
        self.build_ui()
        self.refresh_ports()
        self.restore_settings()
        self.refresh_ports()
        self.refresh_device_table()
        if self.registry_error:
            self.device_status.set('Gerätedatei konnte nicht geladen werden: ' + self.registry_error)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        root.after(1000, self.housekeeping)

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
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill='both', expand=True)
        device_tab = ttk.Frame(self.tabs, padding=10)
        self.control_tab = ttk.Frame(self.tabs, padding=10)
        log_tab = ttk.Frame(self.tabs, padding=10)
        raw_tab = ttk.Frame(self.tabs, padding=10)
        self.raw_tab = raw_tab
        for frame, title in ((device_tab,'Geräte / Aufnahme'),(self.control_tab,'Steuern'),(log_tab,'Serielles Protokoll'),(raw_tab,'Rohsignale')):
            self.tabs.add(frame,text=title)
        self.build_devices_ui(device_tab)
        self.build_raw_ui(raw_tab)
        controls = ttk.LabelFrame(self.control_tab, text='Rollladen steuern', padding=12)
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
        profiles = ttk.LabelFrame(self.control_tab, text='Steuerziele auf dem Laptop speichern', padding=12)
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
        logging = ttk.Frame(log_tab)
        logging.pack(fill='x')
        ttk.Label(logging, text='Aufnahme-Label').pack(side='left')
        ttk.Entry(logging, textvariable=self.label, width=26).pack(side='left', padx=6)
        ttk.Button(logging, text='RFDEBUG an', command=lambda: self.send('10;RFDEBUG=ON;')).pack(side='left', padx=3)
        ttk.Button(logging, text='RFDEBUG aus', command=lambda: self.send('10;RFDEBUG=OFF;')).pack(side='left', padx=3)
        ttk.Button(logging, text='Export JSONL', command=self.export).pack(side='right')
        frame = ttk.Frame(log_tab)
        frame.pack(fill='both', expand=True, pady=8)
        self.log = tk.Text(frame, font=('Consolas', 10), background='#172233', foreground='#e3edf8', wrap='none', height=9, state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, command=self.log.yview)
        scroll.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scroll.set)
        rawrow = ttk.Frame(log_tab)
        rawrow.pack(fill='x')
        ttk.Entry(rawrow, textvariable=self.raw).pack(side='left', fill='x', expand=True)
        ttk.Button(rawrow, text='Seriellen Befehl senden', command=lambda: self.send(self.raw.get())).pack(side='left', padx=6)

    def build_devices_ui(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x')
        self.scan_btn = ttk.Button(row,text='Aufnahme / Anlernen starten',command=self.toggle_scan)
        self.scan_btn.pack(side='left')
        ttk.Combobox(row,textvariable=self.scan_duration,values=['1 Minute','5 Minuten','15 Minuten','Bis zum Stoppen'],state='readonly',width=17).pack(side='left',padx=6)
        ttk.Checkbutton(row,text='Rohsignale mit aufnehmen',variable=self.capture_raw,command=self.scan_options_changed).pack(side='left')
        ttk.Button(row,text='Geräteliste exportieren',command=self.export_devices).pack(side='right')
        ttk.Label(parent,textvariable=self.device_status,wraplength=1010).pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=(0,6))
        ttk.Label(row,textvariable=self.activity_status,wraplength=800).pack(side='left')
        ttk.Button(row,text='Rohsignale ansehen',command=lambda:self.tabs.select(self.raw_tab)).pack(side='right')
        row = ttk.Frame(parent)
        row.pack(fill='x',pady=(0,6))
        ttk.Label(row,text='Suchen').pack(side='left')
        ttk.Entry(row,textvariable=self.device_filter,width=32).pack(side='left',padx=6)
        self.device_filter.trace_add('write',lambda *_:self.refresh_device_table())
        ttk.Label(row,text='Lokale Zuordnung · keine Speicherung im Mega').pack(side='left',padx=12)
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True)
        columns=('name','type','protocol','id','channel','values','seen','count')
        self.device_tree = ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse',height=10)
        for column,title,width in zip(columns,['Name / Raum','Typ','Protokoll','ID','Kanal','Messwerte / Befehl','Letzter Empfang','Anzahl'],[170,110,140,95,65,230,165,65]):
            self.device_tree.heading(column,text=title)
            self.device_tree.column(column,width=width,minwidth=55,stretch=column in ('name','values'))
        self.device_tree.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(frame,orient='vertical',command=self.device_tree.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=self.device_tree.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        self.device_tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        self.device_tree.bind('<<TreeviewSelect>>',self.select_device)
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        for caption,variable,width in [('Name',self.edit_name,22),('Raum',self.edit_room,18),('Notiz',self.edit_notes,28)]:
            ttk.Label(row,text=caption).pack(side='left')
            ttk.Entry(row,textvariable=variable,width=width).pack(side='left',padx=(4,10))
        ttk.Button(row,text='Speichern',command=self.save_device).pack(side='left')
        row=ttk.Frame(parent);row.pack(fill='x')
        self.target_btn=ttk.Button(row,text='Als Steuerziel übernehmen',command=self.use_selected_device,state='disabled')
        self.target_btn.pack(side='left')
        ttk.Button(row,text='Lokal entfernen',command=self.delete_device).pack(side='left',padx=6)
        self.device_detail=tk.Text(parent,height=4,wrap='word',font=('Consolas',9),state='disabled')
        self.device_detail.pack(fill='x',pady=(8,0))

    def build_raw_ui(self,parent):
        ttk.Label(parent,text='Pulsfolgen werden separat gesammelt. Ihre Signatur ist keine Geräte-ID; TIMING kann auch von bekannten Geräten stammen.',wraplength=1000).pack(anchor='w',pady=6)
        self.raw_tree=ttk.Treeview(parent,columns=('source','pulses','count','seen'),show='headings',height=8)
        for column,title in [('source','Quelle'),('pulses','Pegeldauern'),('count','Identische Aufnahmen'),('seen','Letzter Empfang')]:
            self.raw_tree.heading(column,text=title)
        self.raw_tree.pack(fill='both',expand=True)
        self.raw_tree.bind('<<TreeviewSelect>>',self.select_raw_signal)
        self.raw_detail=tk.Text(parent,height=9,wrap='word',font=('Consolas',9),state='disabled')
        self.raw_detail.pack(fill='x',pady=8)
        ttk.Button(parent,text='Gesamte Sitzung als JSONL exportieren',command=self.export).pack(anchor='w')

    def toggle_scan(self):
        if self.scanning:
            self.stop_scan()
            return
        if not self.ready:
            self.device_status.set('Bitte zuerst mit dem Mega verbinden.')
            return
        if self.registry_error:
            self.device_status.set('Die bestehende Gerätedatei konnte nicht gelesen werden; sie wird nicht überschrieben. ' + self.registry_error)
            return
        seconds={'1 Minute':60,'5 Minuten':300,'15 Minuten':900,'Bis zum Stoppen':None}[self.scan_duration.get()]
        self.scanning=True
        self.scan_raw_count=0
        self.scan_decoded_count=0
        self.scan_deadline=time.monotonic()+seconds if seconds else None
        self.scan_btn.configure(text='Aufnahme beenden')
        self.scan_options_changed()
        self.device_status.set('Aufnahme aktiv: Neue decodierte Geräte werden lokal registriert. Sensoren senden oft nur in Intervallen.')
        self.update_activity_status()

    def update_activity_status(self):
        text=f'{self.scan_decoded_count} decodierte Meldungen · {self.scan_raw_count} Rohaufnahmen · {len(self.registry.devices)} gespeicherte Geräte'
        if self.scan_raw_count and not self.scan_decoded_count:
            text+=' — Funk wird empfangen, aber noch kein Gerät decodiert. Siehe Rohsignale.'
        self.activity_status.set(text)

    def scan_options_changed(self):
        if self.scanning and self.ready:
            self.send('10;RFDEBUG=OFF;')
            self.send('10;QRFDEBUG=OFF;')
            self.send('10;RFUDEBUG=' + ('ON;' if self.capture_raw.get() else 'OFF;'))
            self.send('10;RFTIMING=' + ('ON;' if self.capture_raw.get() else 'OFF;'))

    def stop_scan(self):
        was_scanning=self.scanning
        self.scanning=False
        self.scan_deadline=None
        self.scan_btn.configure(text='Aufnahme / Anlernen starten')
        if was_scanning and self.ready:
            self.send('10;RFUDEBUG=OFF;')
            self.send('10;RFTIMING=OFF;')
        self.flush_devices()
        if was_scanning:
            self.device_status.set('Aufnahme beendet. Bekannte Geräte werden bei Empfang weiter aktualisiert.')

    def flush_devices(self):
        if self.registry_error:
            return False
        try:
            self.registry.save()
            return True
        except OSError as exc:
            self.device_status.set('Lokales Speichern fehlgeschlagen: ' + str(exc))
            return False

    def housekeeping(self):
        if self.closing:
            return
        if self.scanning and self.scan_deadline is not None:
            remaining=max(0,int(self.scan_deadline-time.monotonic()))
            if not remaining:
                self.stop_scan()
            else:
                self.scan_btn.configure(text=f'Aufnahme beenden ({remaining} s)')
        self.flush_devices()
        self.root.after(1000,self.housekeeping)

    def refresh_device_table(self):
        search=self.device_filter.get().casefold()
        visible=set()
        for key,device in self.registry.devices.items():
            values=device_measurement_text(device)
            name=device.get('name') or device['protocol']
            if device.get('room'):
                name += ' / ' + device['room']
            row=(name,device.get('type','Funk'),device['protocol'],device['device_id'],device['channel'] or '—',values,(device.get('last_seen') or '')[:19].replace('T',' '),device['count'])
            if search and search not in ' '.join(map(str,row)).casefold():
                continue
            visible.add(key)
            if self.device_tree.exists(key):
                self.device_tree.item(key,values=row)
            else:
                self.device_tree.insert('', 'end',iid=key,values=row)
        for key in self.device_tree.get_children():
            if key not in visible:
                self.device_tree.delete(key)
        if not self.device_tree.selection():
            self.target_btn.configure(state='disabled')

    def selected_device(self):
        selection=self.device_tree.selection()
        if selection:
            return selection[0],self.registry.devices.get(selection[0])
        return None,None

    @staticmethod
    def set_text(widget,text):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',text);widget.configure(state='disabled')

    def select_device(self,_=None):
        key,device=self.selected_device()
        if not device:
            return
        self.edit_name.set(device.get('name',''))
        self.edit_room.set(device.get('room',''))
        self.edit_notes.set(device.get('notes',''))
        frame=Frame(device['protocol'],device['device_id'],device['channel'],device['fields'],device.get('raw',''))
        self.target_btn.configure(state='normal' if control_target(frame) else 'disabled')
        text='Felder: '+json.dumps(device['fields'],ensure_ascii=False)+'\n'+device.get('raw','')
        text+='\nMesswert-Zeitstempel: '+json.dumps(device.get('field_seen',{}),ensure_ascii=False)
        if device['protocol'].casefold()=='htr008w':
            text='HTR: 000001 ist ein lokaler Profilalias, keine entschlüsselte Geräte-ID.\n'+text
        self.set_text(self.device_detail,text)

    def save_device(self):
        key,device=self.selected_device()
        if not device:
            self.device_status.set('Zuerst ein Gerät in der Liste auswählen.')
            return
        self.registry.rename(key,self.edit_name.get(),self.edit_room.get(),self.edit_notes.get())
        saved=self.flush_devices();self.refresh_device_table()
        if saved:self.device_status.set('Name, Raum und Notiz lokal gespeichert.')

    def delete_device(self):
        key,device=self.selected_device()
        if device and messagebox.askyesno('Lokal entfernen','Dieses Gerät aus der lokalen Liste entfernen? Bei laufender Aufnahme kann es erneut erscheinen.'):
            del self.registry.devices[key];self.registry.dirty=True
            self.flush_devices();self.refresh_device_table()
            self.set_text(self.device_detail,'')

    def use_selected_device(self):
        key,device=self.selected_device()
        if not device:
            return
        target=control_target(Frame(device['protocol'],device['device_id'],device['channel'],device['fields'],''))
        if not target:
            self.device_status.set('Für diesen Sensor oder dieses Protokoll sind keine Rollladen-Sendetasten vorgesehen.')
            return
        for name,value in target.items():
            getattr(self,name).set(value)
        self.profile_name.set(device.get('name') or device['protocol'])
        self.tabs.select(self.control_tab)

    def select_raw_signal(self,_=None):
        selection=self.raw_tree.selection()
        if selection:
            self.set_text(self.raw_detail,self.raw_signals[selection[0]]['raw'])

    def export_devices(self):
        destination=filedialog.asksaveasfilename(defaultextension='.json',initialfile='rflink_devices_export.json',filetypes=[('JSON','*.json')])
        if destination:
            try:
                Path(destination).write_text(json.dumps({'version':1,'devices':self.registry.devices},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Export',str(exc))

    def receive_device(self,raw,timestamp):
        frame=parse_frame(raw)
        if frame:
            if self.scanning:
                self.scan_decoded_count+=1
                self.update_activity_status()
            self.latest_frame=frame
            target=control_target(frame)
            if target:
                self.last_received=target
                self.profile_status.set('Gerät empfangen: '+str(target))
            is_new=frame.key not in self.registry.devices
            device=self.registry.observe(frame,timestamp,allow_new=self.scanning)
            if device:
                self.refresh_device_table()
                if is_new:
                    self.flush_devices()
                    self.update_activity_status()
            return
        if self.scanning and self.capture_raw.get():
            signal=raw_signal(raw)
            if signal:
                self.scan_raw_count+=1
                self.update_activity_status()
                key=signal['signature']
                if key not in self.raw_signals and len(self.raw_signals)>=200:
                    oldest=next(iter(self.raw_signals));del self.raw_signals[oldest];self.raw_tree.delete(oldest)
                signal['count']=self.raw_signals.get(key,{}).get('count',0)+1
                self.raw_signals[key]=signal
                values=(signal['source'],signal['pulses'],signal['count'],timestamp[11:19])
                if self.raw_tree.exists(key):self.raw_tree.item(key,values=values)
                else:self.raw_tree.insert('', 'end',iid=key,values=values)

    def restore_settings(self):
        try:
            values = json.loads((self.storage_dir / 'rflink_test_settings.json').read_text(encoding='utf-8'))
            for name in ('port_var', 'protocol', 'device_id', 'channel'):
                if name in values:
                    getattr(self, name).set(values[name])
            self.profiles = values.get('profiles', {})
            if not isinstance(self.profiles,dict):self.profiles={}
            self.profile_box['values'] = list(self.profiles)
            if not self.registry_error:
                for name,target in self.profiles.items():
                    try:
                        control_command(target['protocol'],target['device_id'],target['channel'],'STOP')
                        protocol='ShutterRemote40' if target['protocol']=='Nobily' else 'HTR008W'
                        channel=f"{0x40+int(target['channel']):02X}" if protocol=='ShutterRemote40' else '00'
                        frame=Frame(protocol,target['device_id'],channel,{},'')
                        device=self.registry.register(frame)
                        if not device.get('name'):device['name']=name
                    except (KeyError,TypeError,ValueError):
                        continue
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
        target=control_target(self.latest_frame) if self.latest_frame else None
        if target:
            for key, value in target.items():
                getattr(self, key).set(value)
            self.profile_status.set('Empfangenes Geraet uebernommen; einen Namen vergeben und lokal speichern.')
        else:
            self.profile_status.set('Der letzte Empfang ist kein unterstütztes Steuerziel. Sensoren im Reiter Geräte zuordnen.')

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
        if not self.registry_error:
            protocol='ShutterRemote40' if self.protocol.get()=='Nobily' else 'HTR008W'
            channel=f'{0x40+int(self.channel.get()):02X}' if protocol=='ShutterRemote40' else '00'
            device=self.registry.register(Frame(protocol,self.device_id.get(),channel,{},''))
            device['name']=name;self.registry.dirty=True
            self.flush_devices();self.refresh_device_table()
        self.profile_box['values'] = list(self.profiles)
        self.write_settings()
        self.profile_status.set('Zuordnung auf dem Laptop gespeichert: ' + name)

    def select_profile(self, _=None):
        for key, value in self.profiles.get(self.profile_name.get(), {}).items():
            getattr(self, key).set(value)

    def write_settings(self):
        values = {name: getattr(self, name).get() for name in ('port_var', 'protocol', 'device_id', 'channel')}
        values['profiles'] = self.profiles
        self.storage_dir.mkdir(parents=True,exist_ok=True)
        (self.storage_dir / 'rflink_test_settings.json').write_text(json.dumps(values, indent=2), encoding='utf-8')

    def append(self, direction, raw):
        record = {'time': datetime.now().astimezone().isoformat(), 'label': self.label.get(), 'direction': direction, 'raw': raw}
        self.records.append(record)
        try:
            if self.session_path is None:
                folder=self.storage_dir / 'testprogramm_logs';folder.mkdir(parents=True,exist_ok=True)
                self.session_path=folder / ('session_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.jsonl')
            with self.session_path.open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(record,ensure_ascii=False)+'\n')
        except OSError as exc:
            self.device_status.set('Sitzungsmitschnitt konnte nicht gespeichert werden: '+str(exc))
        self.log.configure(state='normal')
        self.log.insert('end', f'{record["time"][11:19]} {direction.upper():4} {raw}\n')
        if int(self.log.index('end-1c').split('.')[0])>1500:
            self.log.delete('1.0','101.0')
        self.log.see('end')
        self.log.configure(state='disabled')
        if direction == 'rx':
            self.receive_device(raw,record['time'])

    def poll(self):
        try:
            for _ in range(200):
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
        self.stop_scan()
        self.cancel_stop()
        if self.stop_command:
            self.send(self.stop_command)
        self.stop_command = None
        if self.ready:
            self.send('10;RFDEBUG=OFF;')
            self.send('10;RFUDEBUG=OFF;')
            self.send('10;RFTIMING=OFF;')
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
            try:
                if self.session_path and self.session_path.exists():
                    if Path(destination).resolve()!=self.session_path.resolve():shutil.copy2(self.session_path,destination)
                else:
                    Path(destination).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in self.records),encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Export',str(exc))

    def close(self):
        self.closing = True
        self.disconnect()
        self.write_settings()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
