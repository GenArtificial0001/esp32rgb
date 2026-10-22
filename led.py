# Abstracción del LED: el servidor siempre llama set(r, g, b) con valores 0-255
# sin importar el tipo de LED físico configurado en config.py.
from machine import Pin, PWM

import config


class Led:
    def __init__(self):
        self.mode = config.LED_MODE
        self.color = (0, 0, 0)
        if self.mode == "neopixel":
            import neopixel
            self._np = neopixel.NeoPixel(Pin(config.NEOPIXEL_PIN, Pin.OUT), 1)
        elif self.mode == "rgb_pwm":
            self._pwm = [
                PWM(Pin(p), freq=1000, duty_u16=0)
                for p in (config.PIN_R, config.PIN_G, config.PIN_B)
            ]
        elif self.mode == "single":
            self._pwm = [PWM(Pin(config.SINGLE_PIN), freq=1000, duty_u16=0)]
        else:
            raise ValueError("LED_MODE desconocido: %s" % self.mode)
        self.set(0, 0, 0)

    def set(self, r, g, b):
        r, g, b = (max(0, min(255, int(v))) for v in (r, g, b))
        self.color = (r, g, b)
        if self.mode == "neopixel":
            self._np[0] = (r, g, b)
            self._np.write()
        elif self.mode == "rgb_pwm":
            for pwm, v in zip(self._pwm, (r, g, b)):
                duty = v * 257  # 0-255 -> 0-65535
                pwm.duty_u16(65535 - duty if config.COMMON_ANODE else duty)
        else:
            # Luminancia percibida (Rec. 601): el LED monocolor solo puede
            # representar "cuánta luz" tiene el color elegido.
            lum = (299 * r + 587 * g + 114 * b) // 1000
            self._pwm[0].duty_u16(lum * 257)

    def off(self):
        self.set(0, 0, 0)
