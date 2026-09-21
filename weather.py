import network
import urequests
import time
from machine import Pin, PWM

WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = "foundedin1883"

servo = PWM(Pin(19))
servo.freq(50)

def set_angle(angle):
    angle = max(0, min(180, angle))
    reversed_angle = 180 - angle   # flips direction to match clockwise rotation
    duty = int(1638 + (8192 - 1638) * (reversed_angle / 180))
    servo.duty_u16(duty)

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print("Connecting to WiFi...")
    while not wlan.isconnected():
        time.sleep(0.5)
    print("Connected to WiFi")

def get_boston_temp():
    url = "https://api.open-meteo.com/v1/forecast?latitude=42.36&longitude=-71.06&current_weather=true&temperature_unit=fahrenheit"
    response = urequests.get(url)
    data = response.json()
    response.close()
    return data["current_weather"]["temperature"]

connect_wifi()

while True:
    try:
        temp_f = get_boston_temp()
        angle = (temp_f - (-10)) / (100 - (-10)) * 180   # map -10..100°F to 0..180°
        angle = max(0, min(180, angle))
        set_angle(angle)
        print("Boston temp: {:.1f}°F -> servo angle: {:.1f}°".format(temp_f, angle))
    except Exception as e:
        print("Error:", e)

    time.sleep(3600)
