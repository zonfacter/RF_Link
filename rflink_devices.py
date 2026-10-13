"""RFLink serial parsing and external device registry; no hardware writes."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


@dataclass
class Frame:
    protocol: str
    device_id: str
    channel: str
    fields: dict
    raw: str

    @property
    def key(self):
        identifier = self.device_id.upper()
        if re.fullmatch(r'[0-9A-F]+', identifier):
            identifier = format(int(identifier, 16), 'X')
        return json.dumps([self.protocol.casefold(), identifier, self.channel.upper()], separators=(',', ':'))


def parse_frame(raw):
    parts = raw.strip().split(';')
    if len(parts) < 4 or parts[0] != '20' or not re.fullmatch(r'[0-9A-Fa-f]{1,2}', parts[1]):
        return None
    protocol = parts[2].strip()
    if protocol.upper() in ('DEBUG', 'TIMING', 'INFO') or '=' in protocol:
        return None
    fields = {}
    for part in parts[3:]:
        if '=' in part:
            name, value = part.split('=', 1)
            fields[name.upper()] = value.strip()
    identifier = fields.get('ID', '')
    if not protocol or not identifier or len(identifier) > 64:
        return None
    channel = fields.get('SWITCH', fields.get('CHANNEL', fields.get('CHAN', '')))
    return Frame(protocol, identifier.upper(), channel.upper(), fields, raw.strip())


def control_target(frame):
    try:
        if frame.protocol.casefold() == 'shutterremote40':
            channel = int(frame.channel, 16)
            identifier = int(frame.device_id, 16)
            if 0x40 <= channel <= 0x45 and 0 <= identifier <= 0xFFFFFF:
                return {'protocol':'Nobily', 'device_id':f'{identifier:06X}', 'channel':str(channel - 0x40)}
        if frame.protocol.casefold() == 'htr008w' and int(frame.device_id,16) == 1 and int(frame.channel,16) == 0:
            return {'protocol':'HTR008W', 'device_id':'000001', 'channel':'0'}
    except ValueError:
        pass
    return None


def measurement_text(fields):
    result = []
    for name, value in fields.items():
        if name in ('ID', 'SWITCH', 'CHANNEL', 'CHAN', 'CHANNELBYTE'):
            continue
        try:
            if name == 'TEMP':
                if not re.fullmatch(r'[0-9A-Fa-f]{1,4}', value):
                    raise ValueError()
                number = int(value,16)
                temperature = -(number & 0x7FFF) if number & 0x8000 else number
                result.append(f'{temperature / 10:g} °C')
            elif name == 'HUM':
                humidity = int(value,10)
                if not 0 <= humidity <= 100:
                    raise ValueError()
                result.append(f'{humidity} % rF')
            elif name == 'BARO':
                result.append(f'{int(value,16)} hPa')
            elif name == 'BAT':
                result.append('Batterie OK' if value == 'OK' else 'Batterie schwach' if value == 'LOW' else f'BAT={value}')
            else:
                result.append(f'{name}={value}')
        except ValueError:
            result.append(f'{name}={value}')
    return ' · '.join(result)


def device_type(frame):
    if control_target(frame):
        return 'Rollladen'
    if 'TEMP' in frame.fields or 'HUM' in frame.fields:
        return 'Klima-Sensor'
    if 'CMD' in frame.fields:
        return 'Schalter / Funk'
    return 'Sensor / Funk'


def device_measurement_text(device):
    fields = dict(device['fields'])
    if fields.get('CMD') == 'UNKNOWN' and device.get('last_known_command'):
        fields.pop('CMD')
        return measurement_text(fields) + ' | Letzter bekannter Befehl: ' + device['last_known_command'] + ' (unbekanntes Folgetelegramm)'
    return measurement_text(fields)


class DeviceRegistry:
    def __init__(self, filename):
        self.filename = Path(filename)
        self.devices = {}
        self.dirty = False

    def load(self):
        if not self.filename.exists():
            return
        data = json.loads(self.filename.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('version') != 1 or not isinstance(data.get('devices'), dict):
            raise ValueError('Unbekanntes Format der lokalen Gerätedatei')
        for key, device in data['devices'].items():
            if not isinstance(device,dict) or not all(name in device for name in ('protocol','device_id','channel','fields','count')):
                raise ValueError('Ungültiger Eintrag in der lokalen Gerätedatei')
            if not all(isinstance(device[name],str) for name in ('protocol','device_id','channel')) or not isinstance(device['fields'],dict) or not isinstance(device['count'],int) or device['count'] < 0:
                raise ValueError('Ungültige Datentypen in der lokalen Gerätedatei')
            if not all(isinstance(name,str) and isinstance(value,str) for name,value in device['fields'].items()):
                raise ValueError('Ungültige Messwerte in der lokalen Gerätedatei')
            if any(name in device and not isinstance(device[name],str) for name in ('name','room','notes','last_seen','first_seen','raw','type')):
                raise ValueError('Ungültige Gerätebeschreibung in der lokalen Gerätedatei')
            if 'field_seen' in device and (not isinstance(device['field_seen'],dict) or not all(isinstance(value,str) for value in device['field_seen'].values())):
                raise ValueError('Ungültige Messwert-Zeitstempel')
            if Frame(device['protocol'],device['device_id'],device['channel'],device['fields'],'').key != key:
                raise ValueError('Gerätekennung stimmt nicht mit dem Eintrag überein')
        self.devices = data['devices']

    def register(self, frame):
        device = self.devices.get(frame.key)
        if device is None:
            device = {'protocol':frame.protocol, 'device_id':frame.device_id, 'channel':frame.channel,
                      'name':'', 'room':'', 'notes':'', 'first_seen':'', 'last_seen':'', 'count':0, 'fields':{}, 'type':device_type(frame)}
            self.devices[frame.key] = device
            self.dirty = True
        return device

    def observe(self, frame, timestamp, allow_new=False):
        key = frame.key
        device = self.devices.get(key)
        if device is None:
            if not allow_new:
                return None
            device = self.register(frame)
        if not device.get('first_seen'):
            device['first_seen'] = timestamp
        device['count'] += 1
        device['last_seen'] = timestamp
        command = frame.fields.get('CMD')
        if command and command != 'UNKNOWN':
            device['last_known_command'] = command
            device['last_known_command_at'] = timestamp
        device['fields'].update(frame.fields)
        device.setdefault('field_seen',{}).update({name:timestamp for name in frame.fields})
        device['raw'] = frame.raw
        device['type'] = device_type(Frame(frame.protocol,frame.device_id,frame.channel,device['fields'],frame.raw))
        self.dirty = True
        return device

    def rename(self, key, name, room, notes):
        self.devices[key].update(name=name.strip(),room=room.strip(),notes=notes.strip())
        self.dirty = True

    def save(self):
        if not self.dirty:
            return
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.filename.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version':1,'devices':self.devices},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(self.filename)
        self.dirty = False


def raw_signal(raw):
    match = re.fullmatch(r'20;[0-9A-Fa-f]{1,2};(DEBUG|TIMING);Pulses=(\d+);Pulses\(uSec\)=([0-9,]+);?', raw.strip())
    if not match:
        return None
    values = [int(value) for value in match[3].split(',') if value]
    if not values or len(values) != int(match[2]):
        return None
    # This signature groups identical recordings only; it is not an RF device ID.
    signature = hashlib.sha256((match[1] + ':' + ','.join(map(str,values))).encode()).hexdigest()[:16]
    return {'signature':signature,'source':match[1],'pulses':len(values),'values':values,'raw':raw.strip()}
