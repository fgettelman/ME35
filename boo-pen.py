from machine import Pin, SoftI2C, PWM
import time
import struct
import math
 
# ---------- Settings to tune ----------
TAP_THRESHOLD = 0.5   # in g's (resting total is about 1.0)
HOLD_TIME = 5         # seconds to hold the pen out
SAMPLES_PER_COLOR = 5 # training samples for red and for blue
K = 3                 # how many nearest samples vote
MAX_DISTANCE = 0.08   # how close a reading must be to a sample to count
DEBOUNCE_MS = 50
 
CENTER = 90
RED_SIDE = 0
BLUE_SIDE = 180
 
# ---------- Setup ----------
i2c_color = SoftI2C(scl=Pin(22), sda=Pin(21))
i2c_accel = SoftI2C(scl=Pin(33), sda=Pin(25))
print("Accelerometer bus:", [hex(a) for a in i2c_accel.scan()])  # expect 0x19
print("Color sensor bus:", [hex(a) for a in i2c_color.scan()])   # expect 0x10
 
left_eye = Pin(27, Pin.OUT)
right_eye = Pin(26, Pin.OUT)
led_3 = Pin(19, Pin.OUT, value=1)  # extra LED, always on
led_4 = Pin(14, Pin.OUT, value=1)  # extra LED, always on
servo = PWM(Pin(18), freq=50)
 
ACCEL = 0x19
COLOR = 0x10  # VEML6040 address
 
# Accelerometer: 100 Hz, all axes on (CTRL_REG1), +/-2g range (CTRL_REG4)
i2c_accel.writeto_mem(ACCEL, 0x20, bytes([0x57]))
i2c_accel.writeto_mem(ACCEL, 0x23, bytes([0x08]))
 
# Color sensor (VEML6040): config register 0x00
# 0x20 = 160 ms reading time, auto mode, sensor on
i2c_color.writeto_mem(COLOR, 0x00, bytes([0x20, 0x00]))
time.sleep_ms(200)
 
 
# ---------- Buttons (same method as the color sorter) ----------
class Button:
    """Counts a press as a change away from the pin's resting level.
    Don't hold the buttons while the board starts."""
    def __init__(self, pin_num):
        self.pin = Pin(pin_num, Pin.IN)
        self.idle = self.pin.value()
        self.last_state = self.idle
        self.last_time = time.ticks_ms()
 
    def was_pressed(self):
        state = self.pin.value()
        now = time.ticks_ms()
        if state != self.last_state and time.ticks_diff(now, self.last_time) > DEBOUNCE_MS:
            self.last_state = state
            self.last_time = now
            return state != self.idle   # count the press, not the release
        return False
 
 
train_button = Button(34)
start_button = Button(35)
 
 
# ---------- Helper functions ----------
def set_servo(angle):
    # 0 degrees = 0.5 ms pulse, 180 degrees = 2.4 ms pulse, out of a 20 ms period
    pulse_us = 500 + (angle / 180) * 1900
    servo.duty_u16(int(pulse_us / 20000 * 65535))
 
 
def eyes(on):
    left_eye.value(on)
    right_eye.value(on)
    led_3.value(on)
    led_4.value(on)
 
 
def startled_blink():
    for _ in range(4):
        eyes(0)
        time.sleep(0.15)
        eyes(1)
        time.sleep(0.15)
 
 
def read_accel():
    # Read X, Y, Z (6 bytes). 0x80 tells the chip to step through the registers.
    data = i2c_accel.readfrom_mem(ACCEL, 0x28 | 0x80, 6)
    x, y, z = struct.unpack("<hhh", data)
    return x / 16384, y / 16384, z / 16384  # convert to g's
 
 
def read_reg16(reg):
    # Each VEML6040 color value is 2 bytes, low byte first
    data = i2c_color.readfrom_mem(COLOR, reg, 2)
    return struct.unpack("<H", data)[0]
 
 
def read_color():
    # Red = 0x08, Green = 0x09, Blue = 0x0A, White = 0x0B
    r = read_reg16(0x08)
    g = read_reg16(0x09)
    b = read_reg16(0x0A)
    w = read_reg16(0x0B)
    return w, r, g, b
 
 
def deliver_pen(angle, name):
    print(name, "! Here's your", name, "pen.")
    set_servo(angle)
    time.sleep(HOLD_TIME)
    set_servo(CENTER)
    time.sleep(1)  # give the user time to move the card away
 
 
# ---------- KNN (same method as the color sorter) ----------
data = []  # each entry: (r_norm, g_norm, b_norm, label)
 
 
def normalize(r, g, b):
    # Color proportions, so brightness/distance matters less
    total = r + g + b
    if total == 0:
        return (0.0, 0.0, 0.0)
    return (r / total, g / total, b / total)
 
 
def k_nearest_neighbor(x, y, z, k):
    distances = []
    for d in data:
        dist = math.sqrt((x - d[0]) ** 2 + (y - d[1]) ** 2 + (z - d[2]) ** 2)
        distances.append((dist, d[3]))
    distances.sort()
    nearest = distances[:k]
    labels = [label for dist, label in nearest]
    # returns the winning label and how close the nearest sample was
    return max(set(labels), key=labels.count), nearest[0][0]
 
 
# ---------- Training ----------
set_servo(CENTER)
eyes(1)
 
print("=== TRAINING ===")
print("Hold a RED card at the sensor and press Train.")
while True:
    if train_button.was_pressed() and len(data) < SAMPLES_PER_COLOR * 2:
        label = "Red" if len(data) < SAMPLES_PER_COLOR else "Blue"
        c, r, g, b = read_color()
        data.append(normalize(r, g, b) + (label,))
        print(label, "sample", (len(data) - 1) % SAMPLES_PER_COLOR + 1)
        if len(data) == SAMPLES_PER_COLOR:
            print("Now hold a BLUE card and press Train.")
        elif len(data) == SAMPLES_PER_COLOR * 2:
            print("Training done! Press Start.")
 
    if start_button.was_pressed():
        if len(data) == SAMPLES_PER_COLOR * 2:
            break
        print("Finish training first -", len(data), "of 10 samples saved.")
 
    time.sleep_ms(20)
 
# ---------- Start ----------
print("Boo-Pen is awake! Hold a card at the sensor and press Start.")
 
while True:
    # 1. Was the ghost tapped?
    x, y, z = read_accel()
    total = math.sqrt(x * x + y * y + z * z)
    # print(total)  # uncomment to tune TAP_THRESHOLD
    if abs(total - 1.0) > TAP_THRESHOLD:
        print("Eek! Tapped!")
        startled_blink()
        time.sleep(0.3)
 
    # 2. Start button pressed? Read the card in front of the color sensor.
    if start_button.was_pressed():
        c, r, g, b = read_color()
        rn, gn, bn = normalize(r, g, b)
        color, closest = k_nearest_neighbor(rn, gn, bn, K)
        # print(rn, gn, bn, color, closest)  # uncomment to tune MAX_DISTANCE
        if closest < MAX_DISTANCE:
            if color == "Red":
                deliver_pen(RED_SIDE, "Red")
            elif color == "Blue":
                deliver_pen(BLUE_SIDE, "Blue")
        else:
            print("That doesn't look like red or blue - try again.")
 
    time.sleep(0.05)