import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import Keys, angle_value, parse_status
from keyboard_control import Controller

class Label:
    def __init__(self): self.value = ''
    def set(self, value): self.value = value
class Entry:
    def delete(self,*args): pass
    def insert(self,_,value): self.value = value

def controller():
    c = Controller.__new__(Controller)
    c.enabled = c.enable_pending = c.failed = False
    c.after_enable = None; c.keys = Keys(); c.last_jog = 'X'
    c.error = Label(); c.cal_angle = Entry(); c.sent=[]
    c.send = lambda s: c.sent.append(s)
    c.last_state = 0; c.state = None
    return c

class Tests(unittest.TestCase):
    def test_angles(self):
        self.assertEqual(angle_value('10,5'),10.5)
        for v in ('nan','inf','-1','61','','10garbage'):
            with self.assertRaises(ValueError): angle_value(v)
    def test_status(self):
        s=parse_status('STATE3,100,500,1600,1,1,1,0,10,30,4,60,400')
        self.assertEqual(s['count'],4);self.assertEqual(s['speed'],400)
        self.assertIsNotNone(parse_status('STATE3,100,1000000,0,0,1,1,1,-1,-1,1,0,800'))
    def test_invalid_status(self):
        for s in ('STATE,0,0,0,0,0,0,0,-1,-1','STATE3,0,0,0,1,0,0,0,0,0,1,0,400',
            'STATE3,101,0,100,1,0,1,0,60,0,2,60,400','STATE3,0,0,100,1,0,1,0,nan,0,2,60,400',
            'STATE3,0,0,100,1,0,1,0,0,0,2,60,900'):
            self.assertIsNone(parse_status(s))
    def test_keys(self):
        k=Keys();k.press('w');k.press('w');self.assertEqual(k.command(),'W')
        k.press('s');self.assertEqual(k.command(),'X');k.clear();self.assertEqual(k.command(),'X')
    def test_both_keys_stop(self):
        c=controller();c.keys.press('w');c.jog_update();c.keys.press('s');c.jog_update()
        self.assertEqual(c.sent,['W','X'])
    def test_ack_before_calibration(self):
        c=controller();c.enable_pending=True;c.after_enable='K'
        c.handle_line('STATE3,0,0,0,0,0,0,0,-1,-1,1,0,400')
        self.assertTrue(c.enable_pending);self.assertFalse(c.enabled);self.assertEqual(c.sent,[])
        c.handle_line('OK,E');self.assertTrue(c.enabled);self.assertEqual(c.sent,['K'])
    def test_disarm_cancels_pending_enable(self):
        c=controller();c.enable_pending=True;c.after_enable='K';c.disarm();c.handle_line('OK,E')
        self.assertFalse(c.enabled);self.assertEqual(c.sent,['D'])
    def test_calibration_ack(self):
        c=controller();c.handle_line('OK,C10.0000');self.assertEqual(c.cal_angle.value,'20')
        self.assertIn('kaydedildi',c.error.value);c.handle_line('OK,C60.0000');self.assertIn('tamamlandi',c.error.value)
    def test_calibration_error(self):
        c=controller();c.handle_line('ERR,C10,BAD_CAL_POINT');self.assertIn('Kayit olmadi',c.error.value)
    def test_write_failure(self):
        class Broken:
            def write(self,data): raise OSError('unplugged')
        c=controller();c.ser=Broken();c.enabled=True;c.keys.press('w')
        self.assertFalse(Controller.send(c,'H'));self.assertFalse(c.enabled);self.assertTrue(c.failed)
        self.assertEqual(c.keys.command(),'X')
    def test_reset_disarms(self):
        c=controller();c.enabled=True;c.handle_line('STATE3,0,0,0,0,0,0,0,-1,-1,1,0,400')
        self.assertFalse(c.enabled)
    def test_old_firmware_rejected(self):
        c=controller();c.handle_line('STATE,0,0,0,0,0,0,0,-1,-1')
        self.assertEqual(c.sent,['D']);self.assertIn('eski firmware',c.error.value)
    def test_tick_renews_held_jog(self):
        import time
        class Port:
            def read(self,n): return b''
        class Root:
            def after(self,*args): pass
        c=controller();c.ser=Port();c.root=Root();c.rx=b''
        c.enabled=True;c.last_state=time.monotonic();c.keys.press('w')
        c.tick();c.tick();self.assertEqual(c.sent,['H','W','H','W'])
    def test_tick_no_jog_after_release(self):
        import time
        class Port:
            def read(self,n): return b''
        class Root:
            def after(self,*args): pass
        c=controller();c.ser=Port();c.root=Root();c.rx=b''
        c.enabled=True;c.last_state=time.monotonic();c.last_jog='W';c.keys.press('w')
        c.release('w');c.tick();self.assertEqual(c.sent,['X','H'])
if __name__=='__main__':unittest.main()
