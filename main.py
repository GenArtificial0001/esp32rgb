# Punto de entrada: conecta el Wi-Fi y sirve el selector RGB por HTTP.
# MicroPython ejecuta main.py automáticamente al arrancar la placa.
import json
import os
import select
import socket
import sys
import time

import network

import config
from led import Led

STATE_FILE = "color.json"


def find_index():
    # Wokwi web no permite carpetas: ahí index.html queda en la raíz.
    for path in ("www/index.html", "index.html"):
        try:
            os.stat(path)
            return path
        except OSError:
            pass
    return None


INDEX_FILE = find_index()


def load_color():
    # Se persiste el último color para que sobreviva a un reinicio de la placa.
    try:
        with open(STATE_FILE) as f:
            c = json.load(f)
        return c["r"], c["g"], c["b"]
    except (OSError, ValueError, KeyError):
        return 0, 0, 0


def save_color(r, g, b):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"r": r, "g": g, "b": b}, f)
    except OSError:
        pass


def connect_wifi(led):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if config.WIFI_SSID and config.WIFI_SSID != "TU_RED_WIFI":
        print("Conectando a", config.WIFI_SSID, "...")
        sta.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        t0 = time.time()
        blink = False
        while not sta.isconnected() and time.time() - t0 < config.WIFI_TIMEOUT_S:
            # Parpadeo azul mientras conecta: feedback visual sin monitor serie.
            blink = not blink
            led.set(0, 0, 40 if blink else 0)
            time.sleep(0.5)
        if sta.isconnected():
            return sta.ifconfig()[0], "STA"
    sta.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=config.AP_SSID, password=config.AP_PASSWORD,
              authmode=network.AUTH_WPA2_PSK)
    while not ap.active():
        time.sleep(0.1)
    return ap.ifconfig()[0], "AP"


def parse_query(qs):
    params = {}
    for part in qs.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[k] = v
    return params


def color_from_params(p):
    if "hex" in p:
        h = p["hex"].replace("%23", "").lstrip("#")
        if len(h) != 6:
            raise ValueError("hex inválido")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return int(p.get("r", 0)), int(p.get("g", 0)), int(p.get("b", 0))


def send(cl, status, ctype, body):
    if isinstance(body, str):
        body = body.encode()
    cl.send("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
            "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
            % (status, ctype, len(body)))
    cl.send(body)


def send_file(cl, path, ctype):
    # Se envía en bloques para no cargar el HTML completo en la RAM de la placa.
    if path is None:
        send(cl, "404 Not Found", "text/plain", "Falta index.html en la placa")
        return
    size = os.stat(path)[6]
    cl.send("HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
            "Connection: close\r\n\r\n" % (ctype, size))
    buf = bytearray(1024)
    with open(path, "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            cl.send(buf[:n])


def color_json(led):
    r, g, b = led.color
    return json.dumps({"r": r, "g": g, "b": b,
                       "hex": "#%02x%02x%02x" % (r, g, b),
                       "mode": led.mode})


bridge = None  # puente MQTT, se crea en serve() si MQTT_ENABLED


def apply_color(led, rgb):
    # Punto único para cambiar el color, venga de la web local, la consola
    # serie o MQTT: así el estado guardado y el publicado nunca divergen.
    led.set(*rgb)
    save_color(*led.color)
    if bridge:
        bridge.publish_state(led.color)


def handle(cl, led):
    req = cl.recv(1024).decode()
    if not req:
        return
    line = req.split("\r\n", 1)[0]
    try:
        method, target, _ = line.split(" ", 2)
    except ValueError:
        send(cl, "400 Bad Request", "text/plain", "Bad Request")
        return
    path, _, qs = target.partition("?")

    if path in ("/", "/index.html"):
        send_file(cl, INDEX_FILE, "text/html; charset=utf-8")
    elif path == "/api/color" and method == "GET" and not qs:
        send(cl, "200 OK", "application/json", color_json(led))
    elif path == "/api/color":
        # Acepta ?r=&g=&b= o ?hex=RRGGBB, por GET o POST, para poder
        # probarlo también desde el navegador o con curl.
        try:
            r, g, b = color_from_params(parse_query(qs))
        except ValueError:
            send(cl, "400 Bad Request", "application/json",
                 '{"error": "color invalido"}')
            return
        apply_color(led, (r, g, b))
        send(cl, "200 OK", "application/json", color_json(led))
    elif path == "/api/off":
        apply_color(led, (0, 0, 0))
        send(cl, "200 OK", "application/json", color_json(led))
    else:
        send(cl, "404 Not Found", "text/plain", "No encontrado")


def parse_serial(line):
    # Acepta "#ff0080", "ff0080", "255 0 128", "255,0,128" u "off".
    line = line.strip().lower()
    if line in ("off", "apagar"):
        return 0, 0, 0
    parts = line.replace(",", " ").split()
    if len(parts) == 3:
        return tuple(int(p) for p in parts)
    return color_from_params({"hex": line})


def handle_serial(led):
    line = sys.stdin.readline()
    if not line.strip():
        return
    try:
        apply_color(led, parse_serial(line))
    except ValueError:
        print("Formato: #RRGGBB | R G B | off")
        return
    print("Color:", "#%02x%02x%02x" % led.color)


def serve(led):
    global bridge
    addr = socket.getaddrinfo("0.0.0.0", config.HTTP_PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(4)
    # Un solo bucle atiende el servidor HTTP local, la consola serie y MQTT
    # (la vía que usa la página publicada en internet y la que funciona en Wokwi).
    poller = select.poll()
    poller.register(s, select.POLLIN)
    poller.register(sys.stdin, select.POLLIN)
    if config.MQTT_ENABLED:
        from mqtt_bridge import Bridge
        bridge = Bridge(poller, lambda rgb: apply_color(led, rgb))
    print("Consola serie: escribí #RRGGBB, 'R G B' u 'off' y Enter")
    while True:
        if bridge:
            bridge.tick()
        # Timeout de 1 s para que tick() corra aunque no llegue nada.
        for obj, _ in poller.poll(1000):
            if bridge and obj is bridge.sock:
                bridge.readable()
            elif obj is s:
                cl, remote = s.accept()
                cl.settimeout(5)
                try:
                    handle(cl, led)
                except Exception as e:  # un cliente roto no debe tumbar el servidor
                    print("Error atendiendo", remote, e)
                finally:
                    cl.close()
            else:
                handle_serial(led)


def main():
    led = Led()
    ip, mode = connect_wifi(led)
    led.set(*load_color())
    if mode == "AP":
        print("Sin Wi-Fi: punto de acceso '%s' (clave '%s')"
              % (config.AP_SSID, config.AP_PASSWORD))
    print("Selector RGB listo en http://%s/" % ip)
    serve(led)


main()
