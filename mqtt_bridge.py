# Puente MQTT: recibe colores publicados por la página web desde internet y
# publica el estado real del LED para que la página lo muestre.
#
# Tópicos (prefijo esp32rgb/<DEVICE_ID>/):
#   color   <- "#rrggbb" que publica la página (retenido: al reconectar, la
#              placa recibe el último color elegido aunque no estuviera en línea)
#   state   -> "#rrggbb" que la placa aplicó de verdad (retenido)
#   status  -> "online" / "offline" (este último lo publica el broker solo,
#              como "última voluntad", si la placa se cae sin avisar)
import time

import config

KEEPALIVE_S = 60
RETRY_S = 10


def parse_hex(msg):
    h = msg.decode().strip().lstrip("#")
    if len(h) != 6:
        raise ValueError("hex inválido")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class Bridge:
    def __init__(self, poller, on_color):
        self.poller = poller
        self.on_color = on_color
        base = "esp32rgb/%s/" % config.DEVICE_ID
        self.t_color = (base + "color").encode()
        self.t_state = (base + "state").encode()
        self.t_status = (base + "status").encode()
        self.client = None
        self.sock = None
        self.next_try = 0
        self.last_ping = 0

    def _on_msg(self, topic, msg):
        try:
            self.on_color(parse_hex(msg))
        except ValueError:
            print("MQTT: color inválido", msg)

    def connect(self):
        from umqtt.simple import MQTTClient
        import machine
        import ubinascii
        cid = b"esp32rgb-" + ubinascii.hexlify(machine.unique_id())
        c = MQTTClient(cid, config.MQTT_BROKER, port=config.MQTT_PORT,
                       keepalive=KEEPALIVE_S)
        c.set_callback(self._on_msg)
        c.set_last_will(self.t_status, b"offline", retain=True)
        c.connect()
        c.publish(self.t_status, b"online", retain=True)
        c.subscribe(self.t_color)
        self.client, self.sock = c, c.sock
        self.poller.register(self.sock, 1)  # select.POLLIN
        self.last_ping = time.time()
        print("MQTT conectado a %s, tópico %s"
              % (config.MQTT_BROKER, self.t_color.decode()))

    def _drop(self, err):
        print("MQTT desconectado:", err)
        if self.sock:
            try:
                self.poller.unregister(self.sock)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
        self.client = self.sock = None
        self.next_try = time.time() + RETRY_S

    def tick(self):
        # Llamado en cada vuelta del bucle principal: reconecta y mantiene viva
        # la sesión (sin pings el broker corta a los KEEPALIVE_S segundos).
        now = time.time()
        if self.client is None:
            if now >= self.next_try:
                try:
                    self.connect()
                except Exception as e:
                    self._drop(e)
            return
        if now - self.last_ping >= KEEPALIVE_S // 2:
            try:
                self.client.ping()
                self.last_ping = now
            except Exception as e:
                self._drop(e)

    def readable(self):
        try:
            self.client.check_msg()
        except Exception as e:
            self._drop(e)

    def publish_state(self, rgb):
        if self.client is None:
            return
        try:
            self.client.publish(self.t_state, b"#%02x%02x%02x" % rgb, retain=True)
        except Exception as e:
            self._drop(e)
