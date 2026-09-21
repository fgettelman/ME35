import network
import urequests
import time
from machine import Pin, PWM

# --- WiFi credentials ---
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = "foundedin1883"

# --- Servo setup ---
servo = PWM(Pin(15))
servo.freq(50)

MIN_DUTY = 1638   # 0 degrees
MAX_DUTY = 8192   # 180 degrees

def set_angle(angle):
    angle = max(0, min(180, angle))
    reversed_angle = 180 - angle   # flips direction so increasing angle = clockwise
    duty = int(MIN_DUTY + (MAX_DUTY - MIN_DUTY) * (reversed_angle / 180))
    servo.duty_u16(duty)

def rewind():
    print("Rewinding servo back to 0 (1 o'clock position)...")
    for angle in range(180, -1, -10):
        set_angle(angle)
        time.sleep(0.02)
    set_angle(0)

# --- WiFi connect ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print("Connecting to WiFi...")
    while not wlan.isconnected():
        time.sleep(0.5)
    print("Connected:", wlan.ifconfig())

# --- Get Boston (Eastern Time) time from Time.now API ---
def get_boston_time():
    url = "https://time.now/developer/api/timezone/America/New_York"

    for attempt in range(3):
        try:
            response = urequests.get(url)
            data = response.json()
            response.close()

            dt_string = data["datetime"]
            date_part, time_part = dt_string.split("T")
            hour = int(time_part[0:2])
            minute = int(time_part[3:5])
            second = int(time_part[6:8])
            return hour, minute, second

        except Exception as e:
            print("API error (attempt {}): {}".format(attempt + 1, e))
            time.sleep(1)

    return None, None, None

# --- Setup ---
connect_wifi()

set_angle(0)
last_total_minutes = -1
last_servo_angle = 0

# --- Main loop: 0.25°/minute (15°/hour), only move servo every 1° change ---
while True:
    hour, minute, second = get_boston_time()

    if hour is not None:
        print("Boston time: {:02d}:{:02d}:{:02d}".format(hour, minute, second))

        # Display-friendly 12-hour value: 0 -> 12, 13 -> 1, etc.
        hour_display = hour % 12
        if hour_display == 0:
            hour_display = 12

        # --- Shift the reference point to 1 o'clock instead of 12 o'clock ---
        # (hour - 1) % 12 makes 1:00 -> 0, 2:00 -> 1, ... 12:00 -> 11
        adjusted_hour = (hour - 1) % 12
        total_minutes = adjusted_hour * 60 + minute   # minutes since 1:00

        if total_minutes != last_total_minutes:
            # Detect wraparound: cycle just rolled from ~719 back to 0 (i.e. hit 1:00 again)
            if total_minutes < last_total_minutes:
                time.sleep(0.5)
                rewind()
                last_servo_angle = 0
            else:
                target_angle = total_minutes * 0.25   # 0.25° per minute = 15° per hour

                if abs(target_angle - last_servo_angle) >= 1:
                    set_angle(target_angle)
                    print("Servo moved to {:.2f} degrees (hour {}, minute {})".format(
                        target_angle, hour_display, minute))
                    last_servo_angle = target_angle
                else:
                    print("Angle change too small ({:.2f}° -> {:.2f}°), skipping servo move".format(
                        last_servo_angle, target_angle))

            last_total_minutes = total_minutes

    time.sleep(15)