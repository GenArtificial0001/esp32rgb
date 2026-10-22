# Documentación técnica — esp32rgb paso a paso

Explicación de todo el código del proyecto: qué hace cada archivo, en qué
orden se ejecuta y por qué está hecho así. Los enlaces del tipo
[main.py:50](main.py#L50) abren el archivo en la línea exacta dentro de GitHub.

**Índice**

1. [Visión general](#1-visión-general)
2. [Recorrido de un color, de punta a punta](#2-recorrido-de-un-color-de-punta-a-punta)
3. [Firmware de la ESP32 (MicroPython)](#3-firmware-de-la-esp32-micropython)
   - [config.py](#31-configpy--configuración)
   - [led.py](#32-ledpy--control-del-led)
   - [main.py](#33-mainpy--programa-principal)
   - [mqtt_bridge.py](#34-mqtt_bridgepy--puente-con-internet)
4. [Página web (www/index.html)](#4-página-web-wwwindexhtml)
5. [Publicación en GitHub Pages (index.html)](#5-publicación-en-github-pages-indexhtml)
6. [Simulación en Wokwi](#6-simulación-en-wokwi)
7. [Problemas frecuentes](#7-problemas-frecuentes)

---

## 1. Visión general

El sistema tiene dos partes que se comunican:

| Parte | Dónde corre | Qué hace |
|---|---|---|
| **Firmware** (`main.py`, `led.py`, `mqtt_bridge.py`, `config.py`) | En la ESP32, real o simulada en Wokwi | Se conecta al Wi-Fi, recibe colores y los aplica al LED |
| **Página web** (`www/index.html`) | En el navegador del celular o la PC | Muestra la paleta y manda el color elegido |

La página puede llegar a la placa por **dos caminos**:

```
Camino LOCAL (misma red Wi-Fi)
  celular ──HTTP──▶ ESP32 (http://192.168.x.x/api/color?hex=ff0080)

Camino INTERNET (GitHub Pages, sirve también para Wokwi)
  celular ──WebSocket──▶ broker.hivemq.com ◀──MQTT── ESP32
             publica "color"                 se suscribe a "color"
             lee "state" y "status"          publica "state" y "status"
```

¿Por qué hace falta el camino por internet? Desde internet no se puede llegar
directo a una placa que está detrás del router de tu casa, y en el plan gratuito
de Wokwi la placa simulada no acepta conexiones entrantes. En los dos casos la
placa **sí puede salir** a internet. Por eso las dos partes se encuentran en un
punto intermedio: un *broker* MQTT público.

---

## 2. Recorrido de un color, de punta a punta

Qué pasa cuando deslizás el dedo por la paleta abierta desde GitHub Pages:

1. El navegador dispara `pointermove` sobre la paleta → `pickAt()` calcula el
   color según la posición del dedo ([www/index.html:340](www/index.html#L340)).
2. `choose()` guarda ese color como `base` y redibuja la pantalla
   ([www/index.html:332](www/index.html#L332)).
3. `push()` limita los envíos a uno cada 120 ms
   ([www/index.html:310](www/index.html#L310)) y `sendNow()` publica, por
   ejemplo, `#ff0080` en el tópico `esp32rgb/genartificial0001-rgb/color`
   ([www/index.html:317](www/index.html#L317)).
4. El broker reenvía el mensaje a todos los suscriptos a ese tópico, entre ellos
   la ESP32.
5. En la placa, el bucle principal ve que llegaron datos al socket MQTT y llama
   a `bridge.readable()` ([main.py:217](main.py#L217)) → `_on_msg()` convierte
   el texto en `(255, 0, 128)` ([mqtt_bridge.py:38](mqtt_bridge.py#L38)).
6. `apply_color()` enciende el LED, guarda el color en `color.json` y publica el
   estado en `.../state` ([main.py:129](main.py#L129)).
7. La página recibe `.../state` y muestra "Color en la placa: #FF0080"
   ([www/index.html:281](www/index.html#L281)).

---

## 3. Firmware de la ESP32 (MicroPython)

Al arrancar, MicroPython ejecuta solo el archivo `main.py`. Los demás son
módulos que `main.py` importa.

### 3.1 `config.py` — configuración

Es el único archivo que hay que tocar para adaptar el proyecto a otra red u
otra placa. Lo leen `main.py`, `led.py` y `mqtt_bridge.py`.

| Líneas | Qué define |
|---|---|
| [7–9](config.py#L7) | `WIFI_SSID`, `WIFI_PASSWORD` y cuántos segundos esperar la conexión |
| [11–12](config.py#L11) | Nombre y clave de la red propia que crea la placa si no hay Wi-Fi |
| [19](config.py#L19) | `LED_MODE`: tipo de LED (`neopixel`, `rgb_pwm` o `single`) |
| [25](config.py#L25) | Pin del LED WS2812 incorporado (48 en ESP32-S3, 8 en C3/C6) |
| [28–31](config.py#L28) | Pines R, G y B para un LED RGB de 3 patas, y si es de ánodo común |
| [34](config.py#L34) | Pin del LED monocolor (2 en la ESP32 DevKit clásica) |
| [37](config.py#L37) | Puerto del servidor web (80) |
| [44–47](config.py#L44) | MQTT: si se usa, a qué broker se conecta y el `DEVICE_ID` de la placa |

> `DEVICE_ID` es el "nombre" de la placa en el broker. La página tiene que usar
> el mismo, por defecto `genartificial0001-rgb` o el que le pases con `?id=`.

### 3.2 `led.py` — control del LED

Esconde las diferencias entre los tipos de LED. El resto del programa siempre
llama `led.set(r, g, b)` con valores de 0 a 255, sin importar qué LED haya.

- **[led.py:9](led.py#L9) `__init__`** — según `config.LED_MODE` prepara:
  - `neopixel`: un objeto `NeoPixel` de 1 LED en el pin configurado.
  - `rgb_pwm`: tres salidas **PWM** (una por color) a 1000 Hz. PWM prende y
    apaga el pin muy rápido; cuanto más tiempo está prendido, más brilla.
  - `single`: una sola salida PWM.
  - Al final apaga el LED con `set(0, 0, 0)`.
- **[led.py:26](led.py#L26) `set(r, g, b)`**
  1. Limita cada valor entre 0 y 255 por si llega algo fuera de rango.
  2. Guarda el color en `self.color` para poder consultarlo después.
  3. Lo aplica según el tipo de LED:
     - `neopixel`: escribe el color y llama `write()`.
     - `rgb_pwm`: convierte 0–255 a 0–65535 (`v * 257`), que es lo que espera
       `duty_u16`. Si el LED es de ánodo común, invierte el valor.
     - `single`: un LED de un solo color no puede mostrar tonos, así que calcula
       cuánta luz tiene el color (*luminancia*: el verde pesa más porque el ojo
       es más sensible a él) y la usa como brillo.
- **[led.py:42](led.py#L42) `off()`** — atajo para `set(0, 0, 0)`.

### 3.3 `main.py` — programa principal

Orden de ejecución: la última línea llama `main()` ([main.py:242](main.py#L242)),
y `main()` ([main.py:231](main.py#L231)) hace esto:

```
Led()  →  connect_wifi()  →  restaurar el último color  →  serve()  (bucle infinito)
```

#### Arranque y persistencia

- **[main.py:18](main.py#L18) `find_index()`** — busca la página en
  `www/index.html` y, si no existe, en `index.html`. Solo se usa en el camino
  local.
- **[main.py:32](main.py#L32) `load_color()`** y
  **[main.py:42](main.py#L42) `save_color()`** — leen y escriben `color.json`
  en la memoria de la placa, para que al reiniciarla vuelva el último color.
  Si el archivo no existe o está dañado, arranca en negro sin fallar.

#### Conexión Wi-Fi — [main.py:50](main.py#L50) `connect_wifi(led)`

1. Activa el modo estación (cliente de una red existente).
2. Si se configuró una red, intenta conectar durante `WIFI_TIMEOUT_S` segundos.
   Mientras tanto el LED **parpadea en azul**, así se sabe qué está haciendo sin
   monitor serie.
3. Si conecta, devuelve la IP.
4. Si no, crea su propia red (`ESP32-RGB`, modo punto de acceso) y devuelve
   `192.168.4.1`. Así la página local sigue siendo usable sin router.

#### Servidor web local

- **[main.py:75](main.py#L75) `parse_query()`** — convierte `r=1&g=2&b=3` en un
  diccionario.
- **[main.py:84](main.py#L84) `color_from_params()`** — acepta `?hex=ff0080` o
  `?r=255&g=0&b=128`. Si el hex no tiene 6 caracteres, lanza `ValueError`.
- **[main.py:93](main.py#L93) `send()`** — arma una respuesta HTTP mínima
  (estado, tipo, largo y cuerpo).
- **[main.py:102](main.py#L102) `send_file()`** — manda `index.html` en bloques
  de 1 KB para no cargar todo el archivo en la poca RAM de la placa.
- **[main.py:119](main.py#L119) `color_json()`** — el color actual en JSON:
  `{"r":255,"g":0,"b":128,"hex":"#ff0080","mode":"neopixel"}`.
- **[main.py:138](main.py#L138) `handle()`** — lee la primera línea del pedido
  (`POST /api/color?hex=ff0080 HTTP/1.1`) y decide qué hacer:

  | Ruta | Respuesta |
  |---|---|
  | `/` | La página web |
  | `GET /api/color` sin parámetros | El color actual |
  | `/api/color?…` | Cambia el color |
  | `/api/off` | Apaga el LED |
  | Cualquier otra | 404 |

#### Punto único de cambio — [main.py:129](main.py#L129) `apply_color()`

Todo cambio de color pasa por acá, venga de la web local, de la consola serie o
de MQTT. Hace tres cosas siempre juntas: prende el LED, guarda en
`color.json` y publica el estado por MQTT. Como es un solo lugar, lo guardado y
lo publicado nunca quedan distintos.

#### Consola serie

- **[main.py:172](main.py#L172) `parse_serial()`** — entiende `#ff0080`,
  `ff0080`, `255 0 128`, `255,0,128` u `off`.
- **[main.py:183](main.py#L183) `handle_serial()`** — lee la línea que
  escribiste en el monitor serie (USB o el de Wokwi) y la aplica.

#### Bucle principal — [main.py:195](main.py#L195) `serve(led)`

La placa tiene que atender **tres cosas a la vez**: el servidor web, la consola
serie y MQTT. En lugar de usar hilos, usa `select.poll()`, que espera hasta que
alguna de ellas tenga datos.

1. Abre el servidor web en el puerto 80.
2. Registra en el *poller* el servidor y la entrada serie (`sys.stdin`).
3. Si `MQTT_ENABLED`, crea el `Bridge`, que registra su propio socket cuando se
   conecta.
4. Repite para siempre:
   - `bridge.tick()`: reconecta si se cortó y manda un *ping* para que el broker
     no corte la sesión.
   - `poller.poll(1000)`: espera hasta 1 segundo. El límite existe para que
     `tick()` se ejecute aunque no llegue nada.
   - Según quién tenga datos: MQTT → `bridge.readable()`; servidor → acepta el
     pedido y llama `handle()`; consola → `handle_serial()`.
   - Un pedido web con errores no tumba el servidor: el `try/except` lo registra
     y sigue.

### 3.4 `mqtt_bridge.py` — puente con internet

**MQTT** es un protocolo de mensajes muy liviano, ideal para microcontroladores.
Los clientes no hablan entre sí: **publican** mensajes en *tópicos* (como
carpetas) y se **suscriben** a los tópicos que les interesan. El *broker*
reenvía cada mensaje a los suscriptos.

Tópicos usados (prefijo `esp32rgb/<DEVICE_ID>/`):

| Tópico | Quién publica | Contenido | Para qué |
|---|---|---|---|
| `color` | Página | `#rrggbb` | Color pedido |
| `state` | Placa | `#rrggbb` | Color que la placa aplicó de verdad |
| `status` | Placa / broker | `online` / `offline` | Saber si la placa está conectada |

Los tres son **retenidos**: el broker guarda el último mensaje y se lo da a
quien se suscriba después. Por eso, si encendés la placa más tarde, recibe
igual el último color elegido.

- **[mqtt_bridge.py:18](mqtt_bridge.py#L18) `parse_hex()`** — convierte
  `b"#ff0080"` en `(255, 0, 128)`.
- **[mqtt_bridge.py:26](mqtt_bridge.py#L26) `__init__`** — arma los nombres de
  los tres tópicos y deja la conexión "pendiente".
- **[mqtt_bridge.py:44](mqtt_bridge.py#L44) `connect()`**
  1. Crea el cliente `umqtt.simple`, que viene incluido en MicroPython, con un
     identificador único sacado del chip (`machine.unique_id()`).
  2. Configura la **última voluntad**: si la placa se desconecta sin avisar, el
     propio broker publica `offline` en `status`.
  3. Se conecta, publica `online`, se suscribe a `color` y registra el socket en
     el *poller* del bucle principal.
- **[mqtt_bridge.py:62](mqtt_bridge.py#L62) `_drop()`** — ante cualquier error
  cierra todo y programa un reintento en `RETRY_S` (10 s).
- **[mqtt_bridge.py:76](mqtt_bridge.py#L76) `tick()`** — si no hay conexión y ya
  pasó el tiempo de espera, reconecta. Si hay conexión, manda un ping cada 30 s
  (la mitad del *keepalive* de 60 s).
- **[mqtt_bridge.py:94](mqtt_bridge.py#L94) `readable()`** — procesa el mensaje
  que llegó (`check_msg`), que termina en `_on_msg` → `apply_color`.
- **[mqtt_bridge.py:100](mqtt_bridge.py#L100) `publish_state()`** — publica el
  color aplicado en `state`.

---

## 4. Página web (`www/index.html`)

Un solo archivo con HTML, CSS y JavaScript, sin librerías ni CDN, para que la
placa pueda servirlo sola y funcione sin depender de servicios externos.

### 4.1 Estructura (HTML) — [www/index.html:122](www/index.html#L122)

```
header   → título + indicador de estado (punto de color)
palette  → paleta multicolor con el marcador (círculo)
panel    → color actual + "Más colores", brillo, colores rápidos,
           color confirmado por la placa, botones Apagar / Blanco
```

### 4.2 Estilos (CSS) — [www/index.html:8](www/index.html#L8)

- **Variables** en `:root` (colores, espacios, bordes), para cambiar el aspecto
  desde un solo lugar.
- **La paleta** ([www/index.html:44](www/index.html#L44)) son dos degradados
  superpuestos, sin imágenes:
  - abajo, el arco iris horizontal: rojo → amarillo → verde → celeste → azul →
    violeta → rojo (el **tono**);
  - encima, un degradado vertical de transparente a blanco (la
    **saturación**: arriba color puro, abajo blanco).
- `touch-action: none` en la paleta: el dedo arrastra el color sin que la página
  se desplace.
- **El marcador** ([www/index.html:54](www/index.html#L54)) es un círculo blanco
  que se agranda mientras arrastrás.
- **Responsiva**: tamaños con `clamp()` y `dvh` para cualquier pantalla, botones
  de al menos 44–54 px para tocar con el dedo, márgenes `safe-area` para
  celulares con muesca. El `@media`
  ([www/index.html:113](www/index.html#L113)) pasa a dos columnas con el celular
  acostado o en PC.

### 4.3 Lógica (JavaScript) — [www/index.html:157](www/index.html#L157)

#### Modo de conexión — [www/index.html:167](www/index.html#L167)

```js
const MODE = (location.protocol === "http:" && !params.has("mqtt")) ? "local" : "mqtt";
```

- Abierta desde la placa (`http://192.168.x.x`) → modo `local` (HTTP).
- Abierta desde GitHub Pages (`https://…`) → modo `mqtt`.
- `?id=nombre` elige la placa; `?mqtt=1` fuerza MQTT (útil para pruebas).

#### Estado — [www/index.html:174](www/index.html#L174)

- `base`: el color elegido, a pleno.
- `bright`: el brillo, de 0 a 100.
- `output()`: lo que realmente se manda = `base × brillo`.
- `touched`: cuando el usuario ya eligió algo, el estado que llega de la placa
  no le pisa la selección.

#### Paleta: de posición a color

- **[www/index.html:340](www/index.html#L340) `pickAt(e)`** — toma la posición
  del dedo dentro de la paleta:
  - **x** → tono de 0° a 360° (`x / ancho × 360`)
  - **y** → saturación de 1 a 0 (`1 − y / alto`)
  - mueve el marcador y llama `choose()`.
- **[www/index.html:184](www/index.html#L184) `hsvToHex(h, s)`** — fórmula
  estándar de HSV a RGB (con brillo 1, porque el brillo va en el slider).
- **[www/index.html:188](www/index.html#L188) `hexToHs(hex)`** — la inversa. Se
  usa para ubicar el marcador cuando el color viene de un color rápido o de la
  placa.
- **Eventos** ([www/index.html:348](www/index.html#L348)): se usan *Pointer
  Events*, que funcionan igual con dedo, mouse o lápiz.
  - `pointerdown`: empieza el arrastre. `setPointerCapture` sigue al dedo aunque
    salga del borde de la paleta.
  - `pointermove`: actualiza el color mientras dura el arrastre.
  - `pointerup` / `pointercancel`: termina el arrastre.

#### Elegir y mandar

- **[www/index.html:332](www/index.html#L332) `choose(hex)`** — fija el color.
  Si la luz estaba apagada (brillo 0), la vuelve a encender al 100%.
- **[www/index.html:196](www/index.html#L196) `render()`** — redibuja todo:
  código del color, muestra, degradado del brillo, brillo alrededor de la
  paleta, posición del marcador y qué color rápido está marcado.
- **[www/index.html:310](www/index.html#L310) `push()`** — al arrastrar se
  generan decenas de eventos por segundo. `push()` manda como máximo uno cada
  120 ms y **siempre el último**, para no saturar a la placa ni al broker.
- **[www/index.html:317](www/index.html#L317) `sendNow()`** — en modo `mqtt`
  publica en `…/color`; en modo `local` hace `POST /api/color?hex=…` y muestra
  el color que devuelve la placa.

#### Cliente MQTT propio — [www/index.html:238](www/index.html#L238)

Los navegadores no hablan MQTT directo, pero sí **WebSocket**, y el broker
acepta MQTT dentro de WebSocket (`wss://broker.hivemq.com:8884/mqtt`). En lugar
de agregar una librería de cientos de KB, la página trae un cliente mínimo que
arma los paquetes a mano:

| Función | Qué hace |
|---|---|
| `str(s)` | Codifica un texto como MQTT: 2 bytes de largo + texto en UTF-8 |
| `packet(type, body)` | Arma un paquete: tipo + largo variable + contenido |
| `connect()` [L248](www/index.html#L248) | Abre el WebSocket y manda `CONNECT` (MQTT 3.1.1, sesión limpia, *keepalive* 60 s) |
| `feed()` [L264](www/index.html#L264) | Junta los bytes recibidos y los corta en paquetes (pueden llegar varios juntos o uno partido) |
| `handle()` [L281](www/index.html#L281) | `CONNACK` → se suscribe a `state` y `status` y arranca el ping cada 30 s · `PUBLISH` → actualiza estado o color confirmado |
| `publish()` [L300](www/index.html#L300) | Manda el color con la marca de retenido (`0x31`) |

Si se corta la conexión, reconecta sola a los 3 segundos.

#### Arranque — [www/index.html:373](www/index.html#L373)

Dibuja la pantalla y, según el modo, se conecta al broker o le pide el color
actual a la placa (`GET /api/color`).

---

## 5. Publicación en GitHub Pages (`index.html`)

GitHub Pages publica la raíz del repositorio, pero la app está en `www/`. El
`index.html` de la raíz solo redirige a `www/` y conserva los parámetros
(`?id=…`).

Para activarlo: **Settings → Pages → Deploy from a branch → `main` / `(root)`**.
Queda en <https://genartificial0001.github.io/esp32rgb/>.

---

## 6. Simulación en Wokwi

[Wokwi](https://wokwi.com) simula la ESP32 en el navegador. Corre **el mismo
firmware** que la placa real; solo cambian la configuración y el circuito.

### 6.1 Archivos del proyecto en Wokwi

| Archivo en Wokwi | De dónde sale | Cambios respecto de la placa real |
|---|---|---|
| `main.py` | [main.py](main.py) | Ninguno |
| `led.py` | [led.py](led.py) | Ninguno |
| `mqtt_bridge.py` | [mqtt_bridge.py](mqtt_bridge.py) | Ninguno |
| `config.py` | [wokwi/config.py](wokwi/config.py) | Red `Wokwi-GUEST` sin clave y modo `rgb_pwm` |
| `diagram.json` | [wokwi/diagram.json](wokwi/diagram.json) | Circuito con el LED RGB |

El proyecto de Wokwi tiene que ser de **MicroPython**, no de Arduino:
<https://wokwi.com/projects/new/micropython-esp32>.

### 6.2 `wokwi/config.py`

Misma estructura que `config.py`, con dos diferencias:

- `WIFI_SSID = "Wokwi-GUEST"` y clave vacía: es la red Wi-Fi simulada de Wokwi,
  que da salida real a internet.
- `LED_MODE = "rgb_pwm"`: usa el LED RGB externo del diagrama en los pines
  25/26/27, en lugar de un LED incorporado.

### 6.3 `wokwi/diagram.json` — el circuito

Describe las piezas y los cables:

**Piezas (`parts`)**

| id | Tipo | Detalle |
|---|---|---|
| `esp` | `board-esp32-devkit-c-v4` | La ESP32; `env` elige la versión de MicroPython |
| `rgb1` | `wokwi-rgb-led` | LED RGB de **cátodo común** (la pata común va a GND) |
| `rR`, `rG`, `rB` | `wokwi-resistor` | Resistencias de 220 Ω, una por color |

**Conexiones (`connections`)**

```
GPIO 25 ──[220 Ω]── R   (rojo)
GPIO 26 ──[220 Ω]── G   (verde)   LED RGB
GPIO 27 ──[220 Ω]── B   (azul)
GND ─────────────── COM (cátodo común)
TX / RX ─────────── monitor serie
```

Cada conexión es `["pieza:pin", "pieza:pin", "color del cable", []]`. Las
resistencias limitan la corriente; en un circuito real protegen el LED y el
pin de la ESP32.

### 6.4 Qué pasa al darle Play

1. Wokwi arranca MicroPython y ejecuta `main.py`.
2. El LED parpadea en azul mientras conecta a `Wokwi-GUEST`.
3. El monitor serie muestra `Selector RGB listo en http://…` y luego
   `MQTT conectado a broker.hivemq.com`.
4. La placa recibe el último color retenido y lo aplica.
5. Desde ese momento, cada color que elegís en
   <https://genartificial0001.github.io/esp32rgb/> llega a la placa simulada en
   alrededor de un segundo, y la página pasa a "Placa en línea".

> En Wokwi gratis la dirección `http://…` que imprime la placa **no se puede
> abrir** (no hay conexiones entrantes). Por eso en Wokwi se usa siempre la
> página de GitHub Pages, que llega por MQTT.

---

## 7. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| La página queda en "Esperando placa…" | La placa no está corriendo o no conectó a MQTT | Ver el monitor serie: tiene que decir `MQTT conectado` |
| "Placa en línea" pero el LED no cambia | `DEVICE_ID` distinto entre `config.py` y la página | Usar el mismo nombre, o abrir la página con `?id=<DEVICE_ID>` |
| `ImportError: no module named 'led'` | Falta `led.py` en la placa o en Wokwi, o tiene otro nombre | Crear el archivo con el nombre exacto y pegar su contenido |
| Archivos vacíos en Wokwi | "New file..." crea el archivo vacío | Pegar el contenido desde los links *raw* del README |
| El LED no enciende en Wokwi | Proyecto de Arduino, o `diagram.json` sin cablear | Crear proyecto MicroPython y pegar `wokwi/diagram.json` |
| "Sin conexión al broker" | La red bloquea WebSocket hacia `broker.hivemq.com:8884` | Probar desde otra red (por ejemplo, datos móviles) |
| Los colores se ven raros en un LED de 3 patas | El LED es de ánodo común | Poner `COMMON_ANODE = True` en `config.py` |

**Seguridad:** el broker es público y no tiene usuario ni clave. Cualquiera que
conozca el `DEVICE_ID` puede cambiar el color. Para una demo alcanza; para algo
más serio, usar un `DEVICE_ID` difícil de adivinar o un broker propio con
autenticación.
