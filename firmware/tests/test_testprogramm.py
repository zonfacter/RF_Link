import sys
from pathlib import Path
import unittest
import tkinter as tk
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from RFLink_Testprogramm import App, control_command

class TestProgram(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(control_command('Nobily','98461A','0','STOP'),'10;ShutterRemote40;98461A;40;STOP;')
        self.assertEqual(control_command('Nobily','98461A','5','HOCH'),'10;ShutterRemote40;98461A;45;UP;')
        self.assertEqual(control_command('HTR008W','000001','0','RUNTER'),'10;HTR008W;000001;00;DOWN;')
        with self.assertRaises(ValueError):control_command('Nobily','98461A','6','UP')

    def test_auto_stop_retains_target(self):
        root=tk.Tk();root.withdraw()
        try:
            folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
            app=App(root,folder.name);root.update_idletasks()
            sent=[];app.send=lambda command: sent.append(command) or True
            app.protocol.set('Nobily');app.device_id.set('98461A');app.channel.set('2')
            app.drive('HOCH')
            app.channel.set('3')
            app.timed_stop()
            self.assertEqual(sent[-1],'10;ShutterRemote40;98461A;42;STOP;')
            app.cancel_stop()
        finally:root.destroy()

    def test_received_device_assignment_is_local(self):
        root=tk.Tk();root.withdraw()
        try:
            folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
            app=App(root,folder.name)
            sent=[];app.send=lambda command: sent.append(command) or True
            app.append('rx','20;01;ShutterRemote40;ID=ABCDEF;SWITCH=44;CMD=UP;')
            app.use_received()
            self.assertEqual(app.device_id.get(),'ABCDEF')
            self.assertEqual(app.channel.get(),'4')
            app.write_settings=lambda: None
            app.profile_name.set('Wohnzimmer')
            app.save_profile()
            self.assertEqual(app.profiles['Wohnzimmer']['device_id'],'ABCDEF')
            self.assertEqual(sent,[])
        finally:root.destroy()

    def test_local_sensor_discovery_persistence_and_known_updates(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        root=tk.Tk();root.withdraw()
        try:
            app=App(root,folder.name);app.ready=True
            sent=[];app.send=lambda command: sent.append(command) or True
            app.toggle_scan()
            app.append('rx','20;01;Cresta;ID=4D02;TEMP=00c9;HUM=57;BAT=OK;')
            self.assertEqual(len(app.registry.devices),1)
            key=next(iter(app.registry.devices))
            app.device_tree.selection_set(key);app.select_device()
            self.assertEqual(str(app.target_btn['state']),'disabled')
            app.edit_name.set('Terrasse');app.edit_room.set('Außen');app.save_device()
            app.stop_scan()
            app.append('rx','20;02;Cresta;ID=4D02;TEMP=804b;HUM=61;BAT=LOW;')
            app.append('rx','20;03;Cresta;ID=4D03;TEMP=00c0;')
            self.assertEqual(len(app.registry.devices),1)
            self.assertEqual(app.registry.devices[key]['count'],2)
            self.assertIn('-7.5',app.device_tree.item(key,'values')[5])
            app.flush_devices()
            self.assertFalse(any('RFLEARN' in command or 'LearnedRF' in command for command in sent))
            self.assertFalse(any(command.endswith(';UP;') or command.endswith(';DOWN;') for command in sent))
        finally:root.destroy()
        root=tk.Tk();root.withdraw()
        try:
            restored=App(root,folder.name)
            self.assertEqual(restored.registry.devices[key]['name'],'Terrasse')
            self.assertEqual(restored.registry.devices[key]['room'],'Außen')
            self.assertFalse(restored.scanning)
        finally:root.destroy()

    def test_scan_timeout_and_raw_capture(self):
        import time
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        root=tk.Tk();root.withdraw()
        try:
            app=App(root,folder.name);app.ready=True;app.capture_raw.set(True)
            sent=[];app.send=lambda command: sent.append(command) or True
            app.toggle_scan()
            raw='20;02;DEBUG;Pulses=4;Pulses(uSec)=300,660,660,300;'
            app.append('rx',raw);app.append('rx',raw)
            self.assertEqual(len(app.raw_signals),1)
            self.assertEqual(next(iter(app.raw_signals.values()))['count'],2)
            self.assertEqual(len(app.registry.devices),0)
            self.assertIn('10;RFUDEBUG=ON;',sent)
            self.assertIn('10;RFTIMING=ON;',sent)
            app.scan_deadline=time.monotonic()-1
            app.housekeeping()
            self.assertFalse(app.scanning)
            self.assertIn('10;RFTIMING=OFF;',sent)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
