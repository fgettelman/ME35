# ROBOT - save on the robot ESP32 as main.py  (simple PD version)
import time, json, gc, network, espnow
from machine import Pin, I2C, PWM
from neopixel import NeoPixel
 
# ---------------- settings ----------------
SPEED = 0.14      # forward power 0..1 (raise a little if the wheels stop)
KP = 0.09          # P: how hard to steer toward the line
KD = 0.18          # D: stops wobbling
LEFT_DIR = 1       # 1 or -1: flip if the LEFT wheel turns backwards
RIGHT_DIR = -1     # 1 or -1: flip if the RIGHT wheel turns backwards
CORNER_SPEED = 0.25  # wheel power when pivoting in a sharp corner
 
# ---------------- hardware ----------------
center_bus = I2C(0, sda=Pin(21), scl=Pin(22))   # center colour sensor
right_bus = I2C(1, sda=Pin(25), scl=Pin(33))    # right colour sensor
np = NeoPixel(Pin(15), 2)
button = Pin(0, Pin.IN, Pin.PULL_UP)            # BOOT button
left_a, left_b = PWM(Pin(13), freq=1000, duty_u16=0), PWM(Pin(12), freq=1000, duty_u16=0)    # motor 1
right_a, right_b = PWM(Pin(27), freq=1000, duty_u16=0), PWM(Pin(14), freq=1000, duty_u16=0)  # motor 2
 
def motor(a, b, speed):
    duty = int(min(abs(speed), 1) * 65535)
    a.duty_u16(duty if speed > 0 else 0)
    b.duty_u16(duty if speed < 0 else 0)
 
def drive(left, right):
    motor(left_a, left_b, LEFT_DIR * left)
    motor(right_a, right_b, RIGHT_DIR * right)
 
def light(rgb):
    np.fill(tuple(v // 4 for v in rgb)); np.write()
 
def wait_button():
    while button.value(): time.sleep_ms(10)
    while not button.value(): time.sleep_ms(10)
 
# ---------------- colour sensors (VEML6040) ----------------
SENSORS = {"CENTER": center_bus, "RIGHT": right_bus}
for bus in SENSORS.values():
    bus.writeto_mem(0x10, 0x00, b"\x00\x00")    # 40 ms, auto mode, on
time.sleep_ms(50)
 
def read(bus):                                  # [white, red, green, blue]
    return [int.from_bytes(bus.readfrom_mem(0x10, r, 2), "little") for r in (0x0B, 0x08, 0x09, 0x0A)]
 
# ---------------- KNN colour training (saved in colors.json) ----------------
FILE = "colors.json"
COLORS = {"RED": (255, 0, 0), "GREEN": (0, 255, 0), "BLUE": (0, 0, 255)}
 
def train():
    data = []
    for label in ("WHITE", "BLACK", "RED", "GREEN", "BLUE"):
        for s in SENSORS:
            print("Put the", s, "sensor on", label, "and press BOOT")
            wait_button()
            for _ in range(40):
                data.append([label, s] + read(SENSORS[s]))
                time.sleep_ms(50)
    with open(FILE, "w") as f:
        json.dump(data, f)
    return data
 
print("Press BOOT in the next 3 s to retrain")
time.sleep(3)
try:
    if button.value() == 0: raise OSError
    data = json.load(open(FILE))
except OSError:
    data = train()
 
def avg(label, s):
    v = [d[2] for d in data if d[0] == label and d[1] == s]
    return sum(v) / len(v)
 
white = {s: avg("WHITE", s) for s in SENSORS}
black = {s: avg("BLACK", s) for s in SENSORS}
 
def features(reading, s):
    w, r, g, b = reading
    t = (r + g + b) or 1
    return (3 * r / t, 3 * g / t, 3 * b / t, w / white[s])
 
model = {s: [(d[0], features(d[2:], s)) for d in data if d[1] == s] for s in SENSORS}
data = None
gc.collect()
 
def classify(reading, s):                       # 5 nearest neighbours, 4 must agree
    f = features(reading, s)
    near = []
    for lab, ft in model[s]:
        d = sum((x - y) ** 2 for x, y in zip(f, ft))
        if len(near) < 5:
            near.append((d, lab))
        elif d < max(near)[0]:
            near.remove(max(near)); near.append((d, lab))
    votes = [lab for _, lab in near]
    best = max(set(votes), key=votes.count)
    return best if votes.count(best) >= 4 else None
 
def brightness(reading, s):                     # 0 = black, 1 = white
    return max(0, min(1, (reading[0] - black[s]) / (white[s] - black[s])))
 
# ---------------- station (ESP-NOW) ----------------
network.WLAN(network.STA_IF).active(True)
esp = espnow.ESPNow(); esp.active(True)
STATION = b"\xff" * 6
esp.add_peer(STATION)
 
def tell_station(color):                    # quick: never stops the robot for long
    light(COLORS[color])                        # both LEDs show the colour
    esp.send(STATION, color)
    host, msg = esp.recv(50)                    # wait max 50 ms for the ACK
    if msg == b"ACK " + color.encode():
        print("Station ACK:", color)
        np[1] = (60, 60, 60); np.write()        # LED 1 white = station acknowledged
    else:
        print("No ACK from station")
 
# ---------------- main loop ----------------
print("Put the robot on the line and press BOOT")
wait_button()
last_error = 0
seen, streak, last_stop = None, 0, 0
 
while True:
    c = read(center_bus)
    r = read(right_bus)
 
    # colour: same colour 3 readings in a row, at most once every 2 s
    color = None
    for s, reading in (("CENTER", c), ("RIGHT", r)):
        lab = classify(reading, s)
        if lab in COLORS:
            color = lab
    streak = streak + 1 if (color and color == seen) else (1 if color else 0)
    seen = color
    if streak >= 3 and time.ticks_diff(time.ticks_ms(), last_stop) > 2000:
        print("Detected", color)
        tell_station(color)                     # lights + station, robot keeps driving
        last_stop = time.ticks_ms()
 
    # PD line following: tape runs between the sensors
    bc = brightness(c, "CENTER")
    br = brightness(r, "RIGHT")
    if bc > 0.9 and br > 0.9:
        # corner / line lost: pivot on the spot toward where the line was last seen
        if last_error >= 0:
            drive(CORNER_SPEED, -CORNER_SPEED)  # turn right
        else:
            drive(-CORNER_SPEED, CORNER_SPEED)  # turn left
    else:
        error = bc - br                         # + = line to the right, - = line to the left
        turn = KP * error + KD * (error - last_error)
        last_error = error
        base = SPEED * (1 - 0.5 * abs(error))   # slow down while turning
        drive(base + turn, base - turn)
    gc.collect()
    time.sleep_ms(20)