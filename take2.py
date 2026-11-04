# VERSION 3 (low-memory KNN)
# ROBOT - save on the robot ESP32 as main.py
# Two VEML6040 colour sensors: CENTER and RIGHT (right of center).
# Both sensors have the same fixed I2C address (0x10), so each gets its own I2C bus.
# The black tape should run BETWEEN the two sensors.
import time, json, network, espnow, gc
from machine import Pin, I2C, PWM
from neopixel import NeoPixel
 
# ---------- pins (change to match your wiring) ----------
center_bus = I2C(0, sda=Pin(21), scl=Pin(22))   # center colour sensor: D21 / D22
right_bus = I2C(1, sda=Pin(25), scl=Pin(33))    # right colour sensor:  D25 / D33
np = NeoPixel(Pin(15), 2)                       # 2 NeoPixels (LED 0 and LED 1) on D15
button = Pin(0, Pin.IN, Pin.PULL_UP)            # BOOT button
# Motor 1 = LEFT (D13, D12), Motor 2 = RIGHT (D27, D14). Two PWM pins per motor:
# PWM on the first pin = forward, PWM on the second pin = backward.
m1a = PWM(Pin(13), freq=1000, duty_u16=0)       # motor 1 (left)
m1b = PWM(Pin(12), freq=1000, duty_u16=0)
m2a = PWM(Pin(27), freq=1000, duty_u16=0)       # motor 2 (right)
m2b = PWM(Pin(14), freq=1000, duty_u16=0)
 
SPEED = 0.0625     # base speed 0..1 (1/4 of 0.25)
CONFIRM = 3        # colour must be seen this many readings in a row
MIN_VOTES = 4      # at least 4 of the 5 nearest neighbours must agree
KP = 0.04          # P: steer in proportion to the error
KI = 0.0           # I: fixes slow drift to one side (try 0.002 later)
KD = 0.03          # D: damps wobbling
MIN_POWER = 0.25   # lowest power that actually turns your wheels
STEER = 1          # change to -1 only if the wheel test shows it steers the wrong way
FILE = "colors.json"
COLORS = {"RED": (255, 0, 0), "GREEN": (0, 255, 0), "BLUE": (0, 0, 255)}
SENSORS = {"CENTER": center_bus, "RIGHT": right_bus}
 
# ---------- colour sensors (VEML6040) ----------
for bus in SENSORS.values():
    bus.writeto_mem(0x10, 0x00, b"\x00\x00")   # 40 ms integration, auto mode, on
time.sleep_ms(50)
 
def read_sensor(bus):
    def reg(r):
        d = bus.readfrom_mem(0x10, r, 2)
        return d[0] | d[1] << 8
    # white channel is used as "clear" (overall brightness)
    return [reg(0x0B), reg(0x08), reg(0x09), reg(0x0A)]   # white, red, green, blue
 
# ---------- helpers ----------
def light(rgb):
    np.fill(tuple(v // 4 for v in rgb)); np.write()
 
def motor(a, b, speed):                          # speed -1..1
    if abs(speed) < 0.01:
        a.duty_u16(0); b.duty_u16(0); return
    power = MIN_POWER + (1 - MIN_POWER) * min(1, abs(speed))   # skip the dead zone
    duty = int(power * 65535)
    a.duty_u16(duty if speed > 0 else 0)
    b.duty_u16(duty if speed < 0 else 0)
 
def drive(left, right):
    motor(m1a, m1b, -left)                       # minus = reversed direction
    motor(m2a, m2b, -right)
 
def wait_button():
    while button.value(): time.sleep_ms(10)
    while not button.value(): time.sleep_ms(10)
 
# ---------- KNN ----------
def features(reading, sensor):
    c, r, g, b = reading
    s = (r + g + b) or 1
    return (3 * r / s, 3 * g / s, 3 * b / s, c / white[sensor])   # colour + brightness
 
def train():
    data = []
    for label in ("WHITE", "BLACK", "RED", "GREEN", "BLUE"):
        for sensor in SENSORS:
            print("Put the", sensor, "sensor on", label, "and press BOOT")
            wait_button()
            for _ in range(40):
                data.append([label, sensor] + read_sensor(SENSORS[sensor]))
                time.sleep_ms(50)
            print("  got 40 samples")
    with open(FILE, "w") as f:
        json.dump(data, f)
    return data
 
def average_clear(label, sensor):
    vals = [s[2] for s in data if s[0] == label and s[1] == sensor]
    return sum(vals) / len(vals)
 
def classify(reading, sensor, k=5):
    f0, f1, f2, f3 = features(reading, sensor)
    nearest = []                                 # keep only the k closest
    for lab, ft in model[sensor]:                # compare with this sensor's samples only
        d = (ft[0] - f0) ** 2 + (ft[1] - f1) ** 2 + (ft[2] - f2) ** 2 + (ft[3] - f3) ** 2
        if len(nearest) < k:
            nearest.append((d, lab))
        elif d < max(nearest)[0]:
            nearest.remove(max(nearest))
            nearest.append((d, lab))
    votes = [lab for _, lab in nearest]
    best = max(set(votes), key=votes.count)
    return best if votes.count(best) >= MIN_VOTES else None   # None = not sure
 
def brightness(reading, sensor):                 # 0 = black, 1 = white
    x = (reading[0] - black[sensor]) / (white[sensor] - black[sensor])
    return max(0, min(1, x))
 
# ---------- station link (ESP-NOW) ----------
wlan = network.WLAN(network.STA_IF); wlan.active(True)
esp = espnow.ESPNow(); esp.active(True)
STATION = b"\xff" * 6                            # broadcast
esp.add_peer(STATION)
 
def tell_station(color):
    for _ in range(3):                           # up to 3 tries
        esp.send(STATION, color)
        host, msg = esp.recv(300)
        if msg == b"ACK " + color.encode():
            print("Station ACK:", color)
            for _ in range(2):                   # flash white = ACK received
                light((255, 255, 255)); time.sleep_ms(100)
                light(COLORS[color]); time.sleep_ms(100)
            return
    print("No ACK from station")
 
# ---------- start up ----------
print("Press BOOT in the next 3 s to retrain")
time.sleep(3)
try:
    if button.value() == 0: raise OSError
    data = json.load(open(FILE))
    print("Loaded saved colours")
except OSError:
    data = train()
 
white = {s: average_clear("WHITE", s) for s in SENSORS}
black = {s: average_clear("BLACK", s) for s in SENSORS}
model = {sensor: [(s[0], features(s[2:], s[1])) for s in data if s[1] == sensor] for sensor in SENSORS}
data = None                                      # free memory
gc.collect()
 
print("Put the tape between the two sensors and press BOOT to go")
wait_button()
last_color_time = 0
integral = 0
last_error = 0
last_seen = None
streak = 0
loops = 0
 
# ---------- main loop ----------
while True:
    center = read_sensor(center_bus)
    right = read_sensor(right_bus)
 
    # colour check on both sensors
    color = None
    for sensor, reading in (("CENTER", center), ("RIGHT", right)):
        label = classify(reading, sensor)
        if label in COLORS:
            color = label
 
    # only trust a colour after CONFIRM readings in a row
    if color and color == last_seen:
        streak += 1
    else:
        streak = 1 if color else 0
    last_seen = color
 
    if color and streak >= CONFIRM and time.ticks_diff(time.ticks_ms(), last_color_time) > 2000:
        drive(0, 0)
        light(COLORS[color])
        print("Detected", color)
        tell_station(color)                      # signal BEFORE the maneuver
        time.sleep(2)                            # maneuver: stop 2 s (change if needed)
        drive(SPEED, SPEED); time.sleep_ms(300)  # roll off the patch
        last_color_time = time.ticks_ms()
        integral = last_error = 0                # reset PID after stopping
        continue
 
    b_center = brightness(center, "CENTER")
    b_right = brightness(right, "RIGHT")
 
    if b_center > 0.9 and b_right > 0.9:
        # both on white: line lost -> keep turning the way we last turned
        turn = 0.5 * SPEED if last_error > 0 else -0.5 * SPEED   # gentle arc, not a spin
        integral = 0
    else:
        # PID: positive error = line is to the right, negative = to the left
        error = b_center - b_right
        integral = max(-20, min(20, integral + error))   # limit so it can't wind up
        derivative = error - last_error
        last_error = error
        turn = KP * error + KI * integral + KD * derivative
 
    turn = STEER * max(-SPEED, min(SPEED, turn))  # never spin a wheel backwards
    loops += 1
    if loops % 10 == 0:                          # debug: about twice a second
        print("center %.2f  right %.2f  turn %+.3f" % (b_center, b_right, turn))
    drive(SPEED + turn, SPEED - turn)
    if loops % 20 == 0:
        gc.collect()                             # keep memory tidy
    time.sleep_ms(40)                            # one new reading every 40 ms