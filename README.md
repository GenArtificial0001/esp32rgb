# esp32rgb — Selector RGB web con MicroPython

Servidor web que corre **dentro de la ESP32** (MicroPython) y sirve una página con
un selector de color (sliders R/G/B, selector nativo, hex y colores rápidos). Cada
cambio se envía a la placa y se aplica al LED incorporado al instante. El último
color se guarda en `color.json` y se restaura al reiniciar.

## Estructura

```
config.py        Wi-Fi, tipo de LED y pines (único archivo a editar)
led.py           Abstracción del LED: neopixel / rgb_pwm / single
main.py          Conexión Wi-Fi (con AP de respaldo) + servidor HTTP
www/index.html   Interfaz web (sin dependencias externas)
```

## ¿Qué LED tiene mi placa?

| Placa | LED incorporado | `LED_MODE` | Pin |
|---|---|---|---|
| ESP32-S3-DevKitC-1 | WS2812 RGB | `neopixel` | 48 (algunas v1.1: 38) |
| ESP32-C3-DevKitM-1 | WS2812 RGB | `neopixel` | 8 |
| ESP32-C6-DevKitC-1 | WS2812 RGB | `neopixel` | 8 |
| ESP32 DevKit V1 (clásica) | LED azul monocolor | `single` | 2 |
| Cualquier ESP32 + LED RGB externo | 3 patas | `rgb_pwm` | 25/26/27 |

Con `single` el LED no puede mostrar tonos: el color elegido se convierte a brillo.

## Instalación

1. Flashear MicroPython en la placa (firmware desde <https://micropython.org/download/>):

   ```bash
   pip install esptool mpremote
   ```

   ```bash
   esptool.py --chip esp32 --port COM3 erase_flash
   ```

   ```bash
   esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 ESP32_GENERIC-xxxx.bin
   ```

   (Para S3/C3 usar `--chip esp32s3` / `esp32c3` y dirección `0x0`.)

2. Editar `config.py`: `WIFI_SSID`, `WIFI_PASSWORD`, `LED_MODE` y el pin.

3. Copiar los archivos a la placa:

   ```bash
   mpremote connect COM3 fs cp config.py led.py main.py : + fs mkdir :www + fs cp www/index.html :www/index.html
   ```

4. Reiniciar y ver la IP en el monitor serie:

   ```bash
   mpremote connect COM3 reset repl
   ```

   Se imprime `Selector RGB listo en http://192.168.x.x/`. Abrir esa URL desde
   un celular o PC en la misma red.

Mientras conecta al Wi-Fi el LED parpadea en azul. Si no logra conectar en
15 s, la placa crea la red **`ESP32-RGB`** (clave `esp32rgb123`) y el selector
queda en <http://192.168.4.1/>.

## Consola serie

Además de la web, el color se puede cambiar desde el monitor serie (USB, o el
de Wokwi) escribiendo una línea y Enter: `#ff0080`, `255 0 128` u `off`.

## Simulación en Wokwi

La carpeta `wokwi/` tiene el circuito listo: ESP32 DevKit C v4 + LED RGB de
cátodo común en GPIO 25/26/27 con resistencias de 220 Ω.

1. Crear un proyecto **MicroPython** (no Arduino):
   <https://wokwi.com/projects/new/micropython-esp32>
2. Reemplazar `diagram.json` por `wokwi/diagram.json`.
3. Pegar `main.py` y `led.py`, y como `config.py` usar `wokwi/config.py`
   (red `Wokwi-GUEST`, modo `rgb_pwm`). Agregar también `index.html` en la
   raíz: Wokwi no admite carpetas y `main.py` lo busca ahí si no existe `www/`.
4. Play y, en el monitor serie, escribir `#00ff88` + Enter.

En el plan gratuito de Wokwi **no se puede abrir la página web** del ESP32
simulado: las conexiones entrantes necesitan el Private IoT Gateway (solo para
cuentas pagas, en <http://localhost:9080/>). Por eso en la simulación el color
se controla por la consola serie; la página web se prueba con la placa real.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Interfaz web |
| GET | `/api/color` | Color actual `{"r","g","b","hex","mode"}` |
| GET/POST | `/api/color?r=255&g=0&b=128` | Cambia el color |
| GET/POST | `/api/color?hex=ff0080` | Cambia el color (hex) |
| GET/POST | `/api/off` | Apaga el LED |

Ejemplo:

```bash
curl -X POST "http://192.168.4.1/api/color?hex=00ff88"
```

## Nota de seguridad

`config.py` contiene la clave del Wi-Fi: no subir al repositorio la versión con
credenciales reales. El servidor no tiene autenticación; cualquiera en la misma
red puede cambiar el color.
