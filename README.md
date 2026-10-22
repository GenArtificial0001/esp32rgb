# esp32rgb — Selector RGB web con MicroPython

Servidor web que corre **dentro de la ESP32** (MicroPython) y sirve una página
pensada para el celular: la pantalla principal es una **paleta multicolor**
como la de Paint (tono de izquierda a derecha, saturación de arriba a abajo)
por la que se desliza el dedo y el LED cambia en vivo. También hay un
`<input type="color">` ("Más colores")
para usar el selector nativo del
teléfono, sin escribir códigos. Suma un control de brillo, colores rápidos y
botones Apagar/Blanco. La página es responsiva: en vertical apila todo, y con
el celular acostado o en PC muestra el selector y los controles lado a lado.

La página funciona de dos formas:

- **Local**: abierta desde la IP de la placa (`http://192.168.x.x/`), habla con
  la ESP32 por HTTP en la misma red.
- **Desde internet**: publicada en GitHub Pages, habla con la placa a través de
  un broker MQTT público. Así se controla desde cualquier lugar, y también la
  placa **simulada en Wokwi** (que no acepta conexiones entrantes).

El último color se guarda en `color.json` y se restaura al reiniciar.

## Estructura

```
config.py        Wi-Fi, tipo de LED y pines (único archivo a editar)
led.py           Abstracción del LED: neopixel / rgb_pwm / single
main.py          Conexión Wi-Fi (con AP de respaldo) + servidor HTTP + bucle principal
mqtt_bridge.py   Puente MQTT para la página publicada en internet
www/index.html   Interfaz web (sin dependencias externas, cliente MQTT propio)
index.html       Redirección a www/ para GitHub Pages
wokwi/           Circuito y config para el simulador Wokwi
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
   mpremote connect COM3 fs cp config.py led.py mqtt_bridge.py main.py : + fs mkdir :www + fs cp www/index.html :www/index.html
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

## Acceso desde internet (GitHub Pages + MQTT)

```
celular / PC ──wss──▶ broker.hivemq.com ◀──mqtt── ESP32 (real o Wokwi)
 (GitHub Pages)        tópicos esp32rgb/<DEVICE_ID>/…
```

1. En GitHub: **Settings → Pages → Build and deployment → Deploy from a
   branch → `main` / `(root)` → Save** (el repo tiene que ser público en el
   plan gratuito).
2. A los minutos la página queda en
   <https://genartificial0001.github.io/esp32rgb/>.
3. La placa se identifica por `DEVICE_ID` en `config.py`. La página usa por
   defecto `genartificial0001-rgb`; para otra placa: `…/esp32rgb/?id=mi-placa`.

Arriba a la derecha la página muestra **Placa en línea / desconectada**, y en
el panel el color que la placa confirmó haber aplicado.

Tópicos: `color` (página → placa), `state` (placa → página) y `status`
(`online`/`offline`). Los tres son retenidos: la placa recibe el último color
aunque se conecte después.

## Simulación en Wokwi

La carpeta `wokwi/` tiene el circuito listo: ESP32 DevKit C v4 + LED RGB de
cátodo común en GPIO 25/26/27 con resistencias de 220 Ω.

1. Crear un proyecto **MicroPython** (no Arduino, no sirve uno con
   `sketch.ino`): <https://wokwi.com/projects/new/micropython-esp32>
2. En la pestaña `diagram.json`, reemplazar todo por `wokwi/diagram.json`
   (el LED queda conectado solo).
3. Pegar `main.py`. Con el menú ▾ de las pestañas → **New file...** crear
   `led.py`, `mqtt_bridge.py` y `config.py` (este último con el contenido de
   `wokwi/config.py`: red `Wokwi-GUEST`, modo `rgb_pwm`).
4. Play. Cuando el monitor serie muestre `MQTT conectado`, abrir la página de
   GitHub Pages y elegir un color: el LED del simulador cambia en ~1 s.

En la simulación también se puede escribir `#00ff88` + Enter en el monitor
serie.

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
credenciales reales. Nada tiene autenticación: cualquiera en la misma red puede
usar la API local, y el broker MQTT es público, así que cualquiera que conozca
el `DEVICE_ID` puede cambiar el color. Para algo más que una demo, usar un
`DEVICE_ID` difícil de adivinar o un broker propio con usuario y clave.
