# Configuración para el simulador Wokwi: misma estructura que ../config.py,
# con la red simulada Wokwi-GUEST y el LED RGB cableado en diagram.json.
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASSWORD = ""
WIFI_TIMEOUT_S = 15

AP_SSID = "ESP32-RGB"
AP_PASSWORD = "esp32rgb123"

LED_MODE = "rgb_pwm"
NEOPIXEL_PIN = 48
PIN_R = 25
PIN_G = 26
PIN_B = 27
COMMON_ANODE = False
SINGLE_PIN = 2

HTTP_PORT = 80
