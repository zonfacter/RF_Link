import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from rflink_devices import DeviceRegistry, parse_frame, measurement_text, control_target, raw_signal, device_measurement_text

class RegistryTests(unittest.TestCase):
    def test_unknown_followup_keeps_known_command_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            registry=DeviceRegistry(Path(folder)/'devices.json')
            up=parse_frame('20;01;ShutterRemote40;ID=98461A;SWITCH=41;RAW=11;CMD=UP;')
            registry.observe(up,'t1',allow_new=True)
            followup=parse_frame('20;02;ShutterRemote40;ID=98461A;SWITCH=41;RAW=1E;CMD=UNKNOWN;')
            device=registry.observe(followup,'t2')
            self.assertEqual(len(registry.devices),1)
            self.assertEqual(device['fields']['CMD'],'UNKNOWN')
            self.assertEqual(device['fields']['RAW'],'1E')
            self.assertEqual(device['last_known_command'],'UP')
            self.assertEqual(device['last_known_command_at'],'t1')
            self.assertIn('Letzter bekannter Befehl: UP',device_measurement_text(device))
            registry.save()
            restored=DeviceRegistry(registry.filename);restored.load()
            self.assertEqual(restored.devices[up.key]['last_known_command'],'UP')

    def test_signed_temperature_and_sensor_fields(self):
        frame=parse_frame('20;12;Cresta;ID=4D02;TEMP=00c9;HUM=57;BAT=OK;\r')
        self.assertIn('20.1 °C',measurement_text(frame.fields))
        self.assertIn('57 %',measurement_text(frame.fields))
        self.assertIn('-7.5 °C',measurement_text({'TEMP':'804b'}))
        self.assertEqual(measurement_text({'TEMP':'bad-value'}),'TEMP=bad-value')
        self.assertIsNone(control_target(frame))

    def test_protocol_id_channel_identity_and_atomic_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            registry=DeviceRegistry(Path(folder)/'devices.json')
            a=parse_frame('20;01;Cresta;ID=004D02;CHAN=1;TEMP=00C9;')
            equivalent=parse_frame('20;02;cresta;ID=4d02;CHAN=1;TEMP=00CA;')
            b=parse_frame('20;03;Cresta;ID=4D02;CHAN=2;TEMP=00CB;')
            self.assertIsNone(registry.observe(a,'t0',allow_new=False))
            registry.observe(a,'t1',allow_new=True)
            registry.rename(a.key,'Raum','Büro','Notiz')
            registry.observe(equivalent,'t2',allow_new=False)
            registry.observe(b,'t3',allow_new=True)
            registry.save()
            restored=DeviceRegistry(registry.filename);restored.load()
            self.assertEqual(len(restored.devices),2)
            self.assertEqual(restored.devices[a.key]['count'],2)
            self.assertEqual(restored.devices[a.key]['name'],'Raum')
            self.assertEqual(restored.devices[a.key]['last_seen'],'t2')
            self.assertFalse(registry.filename.with_suffix('.tmp').exists())

    def test_status_debug_noise_are_not_devices(self):
        for line in ['20;01;PONG;','20;INFO;RFLink RX/TX ready;','10;HTR008W;000001;00;UP;','noise','20;01;TIMING;Pulses=2;Pulses(uSec)=300,660;']:
            self.assertIsNone(parse_frame(line))
        signal=raw_signal('20;01;TIMING;Pulses=2;Pulses(uSec)=300,660;')
        self.assertEqual(signal['pulses'],2)
        self.assertIsNone(raw_signal('20;01;TIMING;Pulses=3;Pulses(uSec)=300,660;'))

    def test_sensor_cannot_be_used_as_shutter_and_htr_alias_is_bounded(self):
        self.assertEqual(control_target(parse_frame('20;01;ShutterRemote40;ID=ABCDEF;SWITCH=45;CMD=UP;'))['channel'],'5')
        self.assertIsNone(control_target(parse_frame('20;01;HTR008W;ID=000002;SWITCH=00;CMD=UP;')))
        self.assertIsNone(control_target(parse_frame('20;01;HTR008W;ID=000001;SWITCH=01;CMD=UP;')))

    def test_partial_sensor_frames_preserve_values_and_their_age(self):
        with tempfile.TemporaryDirectory() as folder:
            registry=DeviceRegistry(Path(folder)/'devices.json')
            frame=parse_frame('20;01;Cresta;ID=4D02;TEMP=00C9;HUM=57;')
            registry.observe(frame,'t1',allow_new=True)
            registry.observe(parse_frame('20;02;Cresta;ID=4D02;BAT=LOW;'),'t2')
            device=registry.devices[frame.key]
            self.assertEqual(device['fields']['TEMP'],'00C9')
            self.assertEqual(device['field_seen']['TEMP'],'t1')
            self.assertEqual(device['field_seen']['BAT'],'t2')
            self.assertEqual(device['type'],'Klima-Sensor')

    def test_corrupt_registry_is_not_loaded_or_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            filename=Path(folder)/'devices.json';filename.write_text('{broken')
            registry=DeviceRegistry(filename)
            with self.assertRaises(ValueError):registry.load()
            registry.save()
            self.assertEqual(filename.read_text(),'{broken')

if __name__=='__main__':unittest.main()
