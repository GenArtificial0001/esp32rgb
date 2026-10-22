# Configuración del selector RGB. Es el único archivo que hace falta editar
# para adaptar el sistema a otra red Wi-Fi u otra placa.

# --- Wi-Fi (modo estación) ---------------------------------------------------
# Si no conecta en WIFI_TIMEOUT_S segundos, la placa levanta su propio punto
# de acceso (AP_SSID) para que el selector siga siendo usable sin router.
WIFI_SSID = "TU_RED_WIFI"
WIFI_PASSWORD = "TU_CLAVE_WIFI"
WIFI_TIMEOUT_S = 15

AP_SSID = "ESP32-RGB"
AP_PASSWORD = "esp32rgb123"  # mínimo 8 caracteres (WPA2)

# --- LED incorporado -----------------------------------------------------------
# "neopixel": LED direccionable WS2812 incorporado (ESP32-S3 / C3 / C6 DevKit).
# "rgb_pwm":  LED RGB de 3 patas, un pin PWM por canal.
# "single":   LED monocolor (GPIO2 de la ESP32 DevKit V1 clásica); el color se
#             traduce a brillo, porque ese LED no puede mostrar tonos.
LED_MODE = "neopixel"

# Pin del WS2812 incorporado. Valores típicos:
#   ESP32-S3-DevKitC-1 -> 48 (algunas revisiones v1.1 usan 38)
#   ESP32-C3-DevKitM-1 -> 8
#   ESP32-C6-DevKitC-1 -> 8
NEOPIXEL_PIN = 48

# Pines para LED_MODE = "rgb_pwm".
PIN_R = 25
PIN_G = 26
PIN_B = 27
COMMON_ANODE = False  # True si el LED RGB es de ánodo común (lógica invertida)

# Pin para LED_MODE = "single".
SINGLE_PIN = 2

# Puerto del servidor web.
HTTP_PORT = 80
