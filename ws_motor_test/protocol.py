"""Pure protocol/input helpers, also used by desktop tests."""
import math

def angle_value(text):
    value = float(str(text).replace(',', '.'))
    if not math.isfinite(value) or not 0 <= value <= 60:
        raise ValueError('Aci 0..60 araliginda olmali.')
    return value

def parse_status(line):
    parts = line.split(',')
    if len(parts) != 13 or parts[0] != 'STATE3':
        return None
    try:
        pos, target, upper, cal, moving, armed, commissioning = map(int, parts[1:8])
        angle, goal = map(float, parts[8:10])
        count, last_angle, speed = int(parts[10]), float(parts[11]), int(parts[12])
        if not 1 <= count <= 16 or speed not in (100,400,800) or not math.isfinite(last_angle):
            return None
        if not 0 <= last_angle <= 60 or (cal and (count < 2 or last_angle != 60)):
            return None
        if any(v not in (0, 1) for v in (cal, moving, armed, commissioning)):
            return None
        if not all(math.isfinite(v) for v in (angle, goal)):
            return None
        if not 0 <= pos <= 1000000 or not 0 <= target <= 1000000:
            return None
        if cal:
            if not 0 < upper <= 1000000 or max(pos, target) > upper or commissioning:
                return None
            if not 0 <= angle <= 60 or not 0 <= goal <= 60:
                return None
        elif upper != 0 or angle != -1 or goal != -1:
            return None
        return dict(pos=pos, target=target, upper=upper, cal=bool(cal),
                    moving=bool(moving), armed=bool(armed), commissioning=bool(commissioning),
                    angle=angle, goal=goal, count=count, last_angle=last_angle, speed=speed)
    except ValueError:
        return None

class Keys:
    def __init__(self):
        self.held = set()
    def press(self, key):
        if key in ('w', 's'):
            self.held.add(key)
    def release(self, key):
        self.held.discard(key)
    def clear(self):
        self.held.clear()
    def command(self):
        return 'W' if self.held == {'w'} else 'S' if self.held == {'s'} else 'X'

ERRORS = {
    'OTHER_PORT_ACTIVE': 'Diger USB portunda kontrol acik. Diger uygulamayi durdur/kapat.',
    'DISARMED': 'Kontrol kapali. Kontrolu ac dugmesine bas.',
    'CAL_REQUIRED': 'Once altta kalibrasyonu baslat, sonra W/S ile ilerle.',
    'CAL_REQUIRES_ZERO_IDLE': 'Once S ile sayaci 0 konumuna getirip dur. Kol da gercekte altta olmali.',
    'STOP_FIRST': 'Once W/S tusunu birak ve durmasini bekle.',
    'BAD_CAL_POINT': 'Kayit olmadi: duruyor olmalisin; aci ve darbe onceki noktadan buyuk olmali (en fazla 16 nokta).',
    'BAD_ANGLE': 'Aci 0 ile 60 arasinda bir sayi olmali.',
    'BAD_SPEED': 'Jog hizi 100, 400 veya 800 olmali.',
    'CAL_SAVE_FAILED': 'Kalibrasyon bellekte saklanamadi. Kontrol kapatildi.',
    'LINE_TOO_LONG': 'Seri komut bozuldu. Kontrolu yeniden ac.',
}
