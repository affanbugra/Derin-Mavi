"""ESP32-S3 / HSD57 pulse-position controller. Encoder stays at HSD57."""
import argparse
import time
import tkinter as tk
from tkinter import messagebox
import serial
from serial.tools import list_ports
from protocol import Keys, angle_value, parse_status, ERRORS

class Controller:
    def __init__(self, root, ser):
        self.root, self.ser = root, ser
        self.rx = b''
        self.keys = Keys()
        self.state = None
        self.last_state = 0
        self.enabled = False
        self.failed = False
        self.last_jog = 'X'
        self.enable_pending = False
        self.after_enable = None
        self.pending_since = 0.0
        self.info = tk.StringVar(value='ESP32 durumu bekleniyor...')
        self.detail = tk.StringVar(value='')
        self.error = tk.StringVar(value='')
        root.title(f'Kamera kolu v3 | 0-60 derece | {ser.port}')
        root.geometry('720x700')
        tk.Label(root, textvariable=self.info, font=('Arial', 15, 'bold')).pack(pady=12)
        tk.Label(root, textvariable=self.detail).pack()
        tk.Label(root, text='Gosterilen aci encoder olcumu degil, kalibrasyondan hesaplanan konumdur.',
                 wraplength=620, fg='#555').pack(pady=8)
        connection_row = tk.Frame(root); connection_row.pack()
        tk.Button(connection_row, text='Kontrolu ac', command=self.arm).pack(side='left',padx=6)
        tk.Button(connection_row, text='Yeniden baglan', command=self.reconnect).pack(side='left',padx=6)
        row = tk.Frame(root); row.pack(pady=12)
        for name, key in [('Asagi (S)', 's'), ('Yukari (W)', 'w')]:
            button = tk.Button(row, text=name, width=22)
            button.pack(side='left', padx=6)
            button.bind('<ButtonPress-1>', lambda e, k=key: self.press(k))
            button.bind('<ButtonRelease-1>', lambda e, k=key: self.release(k))
        tk.Label(root, text='W/S: basili tut. Ikisi birlikte: dur. Space / Esc: kontrolu kapat.').pack()
        speed_row = tk.Frame(root); speed_row.pack(pady=6)
        tk.Label(speed_row, text='Jog hizi:').pack(side='left')
        self.speed = tk.IntVar(value=400)
        for label, value in [('Ince (100)',100), ('Normal (400)',400), ('Hizli (800)',800)]:
            tk.Radiobutton(speed_row, text=label, variable=self.speed, value=value,
                           command=self.set_speed).pack(side='left')
        cal = tk.LabelFrame(root, text='Ilk kurulum: kol fiziksel olarak en asagida baslamali')
        cal.pack(fill='x', padx=15, pady=10)
        tk.Button(cal, text='0 konumunda kalibrasyona basla', command=self.calibrate).pack(pady=5)
        tk.Label(cal, text='W/S basili tutuldukca ilerler; birakinca durur.\n'
                 'Kalibrasyonda ust aci siniri henuz bilinmez: kolu gozleyerek ve olcerek ilerle.').pack()
        cr = tk.Frame(cal); cr.pack(pady=6)
        self.cal_angle = tk.Entry(cr, width=8); self.cal_angle.insert(0, '10'); self.cal_angle.pack(side='left')
        tk.Button(cr, text='Olctugum aciyi kaydet (derece)', command=self.record).pack(side='left', padx=8)
        tk.Label(cal, text='Olculen ara noktalar istege bagli; 60 kaydi bitirir ve kalici bellekte saklanir.').pack()
        self.cal_status = tk.StringVar(value='')
        tk.Label(cal, textvariable=self.cal_status, fg='#006a45').pack(pady=5)
        go = tk.Frame(root); go.pack(pady=10)
        self.entry = tk.Entry(go, width=8, font=('Arial', 14)); self.entry.insert(0, '10'); self.entry.pack(side='left')
        tk.Button(go, text='Dereceye git', command=self.go_entry).pack(side='left', padx=8)
        self.entry.bind('<Return>', lambda e: self.go_entry())
        for a in (0, 10, 30, 60):
            tk.Button(go, text=f'{a} derece', command=lambda a=a: self.go(a)).pack(side='left', padx=3)
        tk.Label(root, text='Hareket sirasindaki yeni hedef, mevcut hedefte durulduktan sonra uygulanir.').pack()
        tk.Button(root, text='DUR / kontrolu kapat', bg='#b32121', fg='white',
                  command=self.disarm).pack(pady=8)
        tk.Label(root, textvariable=self.error, fg='#b32121', wraplength=620).pack()
        root.bind('<KeyPress>', self.key_press)
        root.bind('<KeyRelease>', lambda e: self.release(e.keysym.lower()))
        root.bind('<FocusOut>', lambda e: root.after_idle(self.check_focus))
        root.bind_all('<ButtonRelease-1>', lambda e: self.release_mouse())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.tick()

    def reconnect(self):
        self.disarm()
        self.ser.close()
        ports = list(list_ports.comports())
        if len(ports) != 1:
            self.failed = True
            self.error.set('Tek ESP32 USB baglantisi birak. Bulunan: '+', '.join(p.device for p in ports))
            return
        try:
            connection = open_port(ports[0].device)
        except (OSError, serial.SerialException) as exc:
            self.failed = True; self.error.set(str(exc)); return
        self.ser = connection; self.failed = False; self.state = None
        self.rx = b''; self.last_state = 0
        self.root.title(f'Kamera kolu v3 | 0-60 derece | {connection.port}')
        self.error.set('Yeniden baglandi. Durum bekleniyor; hareket otomatik acilmaz.')

    def send(self, line):
        if self.failed:
            return False
        try:
            data = (line + '\n').encode('ascii')
            if self.ser.write(data) != len(data):
                raise OSError('Eksik seri yazma')
            return True
        except (OSError, serial.SerialException) as exc:
            self.failed = True
            self.enabled = False
            self.keys.clear()
            self.error.set(f'Baglanti kesildi: {exc}. Firmware zaman asimiyla durur.')
            return False

    def arm(self, after=None):
        if self.failed or time.monotonic() - self.last_state > 0.6:
            self.error.set('Guncel ESP32 durumu yok. Baglantiyi kontrol et.'); return
        self.keys.clear(); self.last_jog = 'X'
        self.enabled = False
        self.enable_pending = True
        self.after_enable = after
        self.pending_since = time.monotonic()
        if not self.send('E'):
            self.enable_pending = False
        self.error.set('Kontrol onayi bekleniyor...')

    def disarm(self):
        self.enabled = False; self.enable_pending = False; self.after_enable = None
        self.keys.clear(); self.last_jog = 'X'
        self.send('D')

    def set_speed(self):
        if not self.state or self.state['moving'] or self.keys.held:
            if self.state: self.speed.set(self.state['speed'])
            self.error.set('Hizi degistirmeden once dur.'); return
        self.send(f'V{self.speed.get()}')

    def check_focus(self):
        if self.root.focus_displayof() is None:
            self.disarm()

    def press(self, key):
        if self.enabled:
            self.keys.press(key); self.jog_update()

    def release(self, key):
        if key in self.keys.held:
            self.keys.release(key); self.jog_update()

    def release_mouse(self):
        self.keys.clear(); self.jog_update()

    def key_press(self, event):
        k = event.keysym.lower()
        if k in ('space', 'escape'):
            self.disarm()
        elif not isinstance(event.widget, tk.Entry):
            self.press(k)

    def jog_update(self):
        command = self.keys.command()
        if command != self.last_jog:
            if self.last_jog != 'X': self.send('X')
            if command != 'X': self.send(command)
            self.last_jog = command

    def calibrate(self):
        if not self.enabled: self.error.set('Once kontrolu ac.'); return
        if not self.state or self.state['pos'] or self.state['moving']:
            self.error.set('Kalibrasyon yalnizca 0 darbe konumunda ve dururken baslar.'); return
        self.disarm()
        if messagebox.askyesno('Kalibrasyon', 'Kol gercekte alt 0 konumunda mi?\n'
             'Onceki kalibrasyon silinecek. Kalibrasyon sirasinda fiziksel 60 derece sinirini sen izleyeceksin.'):
            self.root.after_idle(lambda: self.arm(after='K'))

    def record(self):
        if not self.enabled: self.error.set('Once kontrolu ac.'); return
        try: a = angle_value(self.cal_angle.get())
        except ValueError as e: self.error.set(str(e)); return
        if not self.state or not self.state['commissioning']:
            self.error.set('Once kalibrasyonu baslat.'); return
        if self.keys.held or self.state['moving']:
            self.error.set('Kaydetmeden once W/S tusunu birak ve dur.'); return
        self.error.set('Nokta kaydi onayi bekleniyor...')
        self.send(f'C{a:.4f}')

    def go_entry(self):
        try: self.go(angle_value(self.entry.get()))
        except ValueError as e: self.error.set(str(e))

    def go(self, angle):
        if not self.enabled or not self.state or not self.state['cal']:
            self.error.set('Kontrol acik ve kalibrasyon tamamlanmis olmali.'); return
        if self.keys.held: self.error.set('Once jog tusunu birak.'); return
        self.send(f'G{angle_value(angle):.4f}')

    def handle_line(self, line):
        state = parse_status(line)
        if state:
            self.state = state; self.last_state = time.monotonic()
            if not state['armed'] and self.enabled:
                self.enabled = False; self.keys.clear(); self.last_jog = 'X'
                self.error.set('Kontrol kapandi (zaman asimi veya reset). Yeniden kontrolu ac.')
            return
        if line.startswith('STATE,'):
            self.disarm()
            self.error.set('Kartta eski firmware var. v3 firmware yuklenmeli.'); return
        if line == 'OK,E' and self.enable_pending:
            self.enable_pending = False; self.enabled = True
            self.error.set('Kontrol acildi.')
            after, self.after_enable = self.after_enable, None
            if after: self.send(after)
        elif line == 'OK,K':
            self.error.set('Kalibrasyon AKTIF. W/S ile kolu olctugun aciya getir.')
        elif line.startswith('OK,C'):
            a = float(line[4:])
            self.error.set('Kalibrasyon tamamlandi ve kaydedildi.' if a == 60
                           else f'{a:g} derece noktasi kaydedildi.')
            if a < 60:
                self.cal_angle.delete(0,'end'); self.cal_angle.insert(0,f'{min(a+10,60):g}')
        elif line.startswith('ERR,'):
            reason = line.split(',')[-1]
            self.error.set(ERRORS.get(reason, reason))
            if reason == 'CAL_SAVE_FAILED':
                self.disarm()

    def tick(self):
        if not self.failed:
            try: self.rx += self.ser.read(4096)
            except (OSError, serial.SerialException) as e:
                self.disarm(); self.failed = True; self.error.set(str(e))
            for _ in range(100):
                if b'\n' not in self.rx: break
                line, self.rx = self.rx.split(b'\n', 1)
                self.handle_line(line.decode('ascii', 'replace').strip())
            if len(self.rx) > 8192:
                self.rx = b''; self.disarm(); self.error.set('Gecersiz seri veri.')
            if self.enable_pending and time.monotonic()-self.pending_since > 0.6:
                self.disarm(); self.error.set('Kontrol acma onayi gelmedi.')
            if self.enabled and time.monotonic() - self.last_state > 0.6:
                self.disarm(); self.error.set('Telemetri zaman asimi. Kontrol kapatildi.')
            if self.enabled:
                self.send('H')
                if self.keys.command() != 'X':
                    self.send(self.keys.command())
            if self.state:
                s = self.state
                self.info.set(f"Hesaplanan konum: {s['angle']:.2f} derece" if s['cal'] else
                              'Kalibrasyon AKTIF - W/S ile ilerle' if s['commissioning'] else
                              'Once alt konumda kalibrasyon baslat')
                self.detail.set(f"Darbe: {s['pos']} | " + ('HAREKET' if s['moving'] else 'Duruyor')
                    + (' | Kontrol acik' if self.enabled else ' | Kontrol kapali'))
                self.cal_status.set(f"Kayitli nokta: {s['count']} | Son nokta: {s['last_angle']:g} derece"
                                    + (' | TAMAMLANDI' if s['cal'] else ''))
                self.speed.set(s['speed'])
            if time.monotonic()-self.last_state > 0.6:
                self.info.set('Baglanti yok / guncel durum bekleniyor')
        self.root.after(50, self.tick)

    def close(self):
        self.disarm(); self.ser.close(); self.root.destroy()

def open_port(port):
    connection = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=0.05)
    connection.dtr = False
    connection.rts = False
    connection.port = port
    connection.open()
    return connection

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', help='Ornek COM5. Birden cok port varsa belirt.')
    args = ap.parse_args()
    ports = list(list_ports.comports())
    port = args.port or (ports[0].device if len(ports) == 1 else None)
    if not port:
        raise SystemExit('Port belirt: --port COM5. Bulunan: ' + ', '.join(p.device for p in ports))
    try:
        connection = open_port(port)
    except serial.SerialException as exc:
        raise SystemExit(f'{port} acilamadi: {exc}. USB portunu ve Seri Monitoru kontrol et.')
    root = tk.Tk(); Controller(root, connection); root.mainloop()

if __name__ == '__main__':
    main()
