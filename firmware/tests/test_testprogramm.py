import sys
from pathlib import Path
import unittest
import tkinter as tk
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
            app=App(root);root.update_idletasks()
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
            app=App(root)
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

if __name__=='__main__':unittest.main()
