from machine import Pin, SoftI2C
import time
import math
import veml6040
 
# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------
DEBOUNCE_MS = 50
SAMPLES_PER_CLASS = 5              # bricks to scan for each class
CLASSES = ["warm", "cool"]         # trained in this order
TOTAL_SAMPLES = SAMPLES_PER_CLASS * len(CLASSES)
K = 3                              # odd number avoids ties with 2 classes
 
# ------------------------------------------------------------
# Buttons (polled, no interrupts)
# ------------------------------------------------------------
class Button:
    """Detects a press as a change away from the pin's resting level.
    The resting level is read at startup, so it works whether the button
    pulls the pin LOW or HIGH when pressed. Don't hold buttons at boot."""
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
            return state != self.idle      # only count the press, not the release
        return False
 
button_Play = Button(34)
button_Train = Button(35)
print("Button idle levels -> play:", button_Play.idle, " train:", button_Train.idle)
 
# ------------------------------------------------------------
# Sensor
# ------------------------------------------------------------
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
print("I2C devices found:", i2c.scan())
 
sensor = veml6040.VEML6040(i2c)
sensor.trigger_measurement()
 
def read_color(samples=3):
    """Average a few readings to reduce noise."""
    r_sum = g_sum = b_sum = 0
    for _ in range(samples):
        red, green, blue, white = sensor.read_rgbw()
        r_sum += red
        g_sum += green
        b_sum += blue
        time.sleep_ms(50)
    return r_sum / samples, g_sum / samples, b_sum / samples
 
def normalize(r, g, b):
    """Color proportions, so brightness/distance matters less."""
    total = r + g + b
    if total == 0:
        return (0.0, 0.0, 0.0)
    return (r / total, g / total, b / total)
 
# ------------------------------------------------------------
# Servos
# ------------------------------------------------------------
from machine import PWM
 
SERVO_MIN_US = 500      # pulse width at 0 degrees
SERVO_MAX_US = 2500     # pulse width at 180 degrees
 
servo_warm = PWM(Pin(19), freq=50)
servo_cool = PWM(Pin(4), freq=50)
 
def servo_angle(servo, angle):
    pulse_us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * angle / 180
    servo.duty_u16(int(pulse_us * 65535 / 20000))   # 20 ms period at 50 Hz
 
def servo_sweep(servo):
    for angle in range(0, 181, 5):      # sweep 0 -> 180
        servo_angle(servo, angle)
        time.sleep_ms(15)
    time.sleep_ms(100)                  # let it physically reach 180
    servo_angle(servo, 0)               # snap straight back to 0
 
servo_angle(servo_warm, 0)
servo_angle(servo_cool, 0)
 
# ------------------------------------------------------------
# KNN
# ------------------------------------------------------------
data = []          # each entry: (r_norm, g_norm, b_norm, label)
 
def k_nearest_neighbor(x, y, z, k=3):
    distances = []
    for d in data:
        dist = math.sqrt((x - d[0]) ** 2 + (y - d[1]) ** 2 + (z - d[2]) ** 2)
        distances.append((dist, d[3]))
 
    distances.sort()
    nearest = distances[:min(k, len(distances))]
    classes = [label for dist, label in nearest]
    print("k nearest:", classes)
 
    return max(set(classes), key=classes.count)
 
# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------
sample_count = 0
 
print("=== TRAINING ===")
print("Place a WARM brick (red/orange/yellow) and press Train.")
 
while True:
    # ---------------- TRAIN SECTION ----------------
    if button_Train.was_pressed():
        if sample_count >= TOTAL_SAMPLES:
            data = []
            sample_count = 0
            print("\nTraining reset.")
            print("Place a WARM brick and press Train.")
        else:
            label = CLASSES[sample_count // SAMPLES_PER_CLASS]
            r, g, b = read_color()
            rn, gn, bn = normalize(r, g, b)
            data.append((rn, gn, bn, label))
            sample_count += 1
 
            print("Sample {}/{} [{}]  raw=({:.0f}, {:.0f}, {:.0f})  norm=({:.3f}, {:.3f}, {:.3f})".format(
                sample_count, TOTAL_SAMPLES, label, r, g, b, rn, gn, bn))
 
            if sample_count == SAMPLES_PER_CLASS:
                print("\nNow place a COOL brick (blue/green/purple) and press Train.")
            elif sample_count == TOTAL_SAMPLES:
                print("\n=== TRAINING COMPLETE ===")
                print("Place any brick and press Play to classify.")
                print("(Press Train again to restart training.)")
 
    # ---------------- RUN / PLAY SECTION ----------------
    if button_Play.was_pressed():
        print("Play pressed")
        if sample_count < TOTAL_SAMPLES:
            print("Finish training first ({}/{} samples).".format(sample_count, TOTAL_SAMPLES))
        else:
            try:
                r, g, b = read_color()
                rn, gn, bn = normalize(r, g, b)
                print("norm=({:.3f}, {:.3f}, {:.3f})".format(rn, gn, bn))
                result = k_nearest_neighbor(rn, gn, bn, K)
                print(">>> This brick is: {} <<<\n".format(result.upper()))
                if result == "warm":
                    servo_sweep(servo_warm)
                elif result == "cool":
                    servo_sweep(servo_cool)
            except Exception as e:
                print("Error during classification:", e)
 
    time.sleep_ms(20)