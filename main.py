# Robot (listener / central): drives 2 motors from the joystick controller

from BLE_CEEO import Listen
from machine import Pin, PWM
import time
import json
import color_knn
import neopixel                                    # NEW

sensor = color_knn.make_sensor()
classifier = color_knn.ColorClassifier()

NAME = "Tommy"         # must match the controller's NAME
buffer = b""

DEADZONE = 0.1         # ignore small wobble around the stick's center
TIMEOUT_MS = 500       # stop the motors if no joystick data arrives for this long
PWM_FREQ = 1000


# ---------- Motors ----------
def set_duty(pwm, frac):
    # frac is 0 to 1; works on both old and new ESP32 MicroPython
    if hasattr(pwm, "duty_u16"):
        pwm.duty_u16(int(frac * 65535))
    else:
        pwm.duty(int(frac * 1023))


def make_pwm(pin_num):
    pwm = PWM(Pin(pin_num))
    pwm.freq(PWM_FREQ)
    set_duty(pwm, 0)
    return pwm


# Left motor: driver inputs IN1/IN2
left_a = make_pwm(12)
left_b = make_pwm(13)

# Right motor: driver inputs IN3/IN4
right_a = make_pwm(14)
right_b = make_pwm(27)

NUM_PIXELS = 8                                     # NEW: number of LEDs on your strip
np = neopixel.NeoPixel(Pin(15), NUM_PIXELS)        # NEW

latest = None          # newest (x, y) from the controller, or None if nothing new
last_data = 0          # time of the last joystick message


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def to_axis(n):
    # Convert 0–1 into -1 to 1, with 0 at the center of the stick
    v = (n - 0.5) * 2
    if abs(v) < DEADZONE:
        return 0.0
    return v


def set_motor(pin_a, pin_b, speed):
    # speed is -1 (full reverse) to 1 (full forward)
    if speed > 0:
        set_duty(pin_a, speed)
        set_duty(pin_b, 0)
    elif speed < 0:
        set_duty(pin_a, 0)
        set_duty(pin_b, -speed)
    else:
        set_duty(pin_a, 0)
        set_duty(pin_b, 0)


def drive(x_norm, y_norm):
    # Arcade mixing: y = forward/back, x = turn
    forward = to_axis(y_norm)
    turn = to_axis(x_norm)
    left = clamp(forward + turn, -1.0, 1.0)
    right = clamp(forward - turn, -1.0, 1.0)
    set_motor(left_a, left_b, left)
    set_motor(right_a, right_b, right)


def stop_motors():
    set_motor(left_a, left_b, 0)
    set_motor(right_a, right_b, 0)


def callback(data):
    # Pieces arrive in up to 20-byte chunks; a newline ends each message
    global buffer, latest, last_data
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        try:
            msg = json.loads(line.decode())
        except ValueError:
            continue           # skip a garbled message instead of crashing
        if "x" in msg and "y" in msg:
            latest = (msg["x"], msg["y"])
            last_data = time.ticks_ms()
            #print("Joystick:", latest)   # remove once everything works


p = None
try:
    stop_motors()
    p = Listen(NAME, verbose=False)
    p.callback = callback

    print("Looking for", NAME, "...")
    if p.connect_up():
        print("Connected")
        b = PWM(Pin(4)); [(b.freq(f), time.sleep_ms(150)) for f in (1047, 1319, 1568, 2093)]; b.deinit()
        last_data = time.ticks_ms()
        on_red = False                             # NEW: True while over the red tape

        while p.is_connected:
            color = classifier.classify(sensor.rgbc())
            if color == "red":
    
                if not on_red:                     # NEW: send once per crossing
                    on_red = True                  # NEW
                    payload = json.dumps("finish") + "\n"
                    # NEW
                    print(color)
                    b = PWM(Pin(4)); [(b.freq(f), time.sleep_ms(150)) for f in (2093, 1568, 1319, 1047)]; b.deinit()
                    for start in range(0, len(payload), 20):         # NEW
                        p.send(payload[start:start + 20])            # NEW
                        time.sleep_ms(20)                            # NEW
                # NEW: blink red, switching on/off every 250 ms
                if (time.ticks_ms() // 250) % 2 == 0:                # NEW
                    np.fill((255, 0, 0))                             # NEW
                else:                                                # NEW
                    np.fill((0, 0, 0))                               # NEW
                np.write()                                           # NEW
            elif on_red:                           # NEW: left the tape
                on_red = False                     # NEW
                np.fill((0, 0, 0))                 # NEW: lights off
                np.write()                         # NEW
            # Drive the motors with the newest joystick reading
            if latest is not None:
                x_norm, y_norm = latest
                latest = None
                drive(x_norm, y_norm)

            # Safety stop if the joystick data stops arriving
            if time.ticks_diff(time.ticks_ms(), last_data) > TIMEOUT_MS:
                stop_motors()

            time.sleep_ms(10)
    print("Lost connection")
finally:
    stop_motors()
    if p:
        p.disconnect()