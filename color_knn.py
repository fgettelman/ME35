# color_knn.py
# Color sensor + KNN classifier for the line follower (Cytron Robo ESP32, MicroPython).
# Tells apart three colors: red, white, and black.
#
# Run this file directly to calibrate. It collects samples of white paper,
# black tape, and red tape, saves them to color_samples.py on the ESP32,
# then runs a live test that prints the detected color.
#
# Other files can use it like this:
#     from color_knn import make_sensor, ColorClassifier
#     sensor = make_sensor()
#     classifier = ColorClassifier()
#     color = classifier.classify(sensor.rgbc())

from machine import Pin, I2C
import time

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
SENSOR_PINS = (16, 17)         # Grove 1 (use (32, 33) if plugged into Grove 5)

K = 5                          # number of neighbors that vote
SAMPLES_PER_COLOR = 20         # readings per color during calibration
SAMPLE_GAP_MS = 100            # 20 x 100 ms = 2 seconds per color

# (label, instruction)
STEPS = (
    ("white", "over WHITE paper"),
    ("black", "over the middle of the BLACK tape"),
    ("red",   "over the RED tape"),
)

# ----------------------------------------------------------------------
# Color sensor - detects either chip automatically:
#   VEML6040 at 0x10 (red, green, blue, white, 40 ms per reading)
#   TCS34725 at 0x29 (red, green, blue, clear, 7.2 ms per reading)
# ----------------------------------------------------------------------
VEML6040_ADDR = 0x10
TCS34725_ADDR = 0x29
SUPPORTED = (VEML6040_ADDR, TCS34725_ADDR)


class ColorSensor:
    def __init__(self, bus_id, pins):
        self.i2c = None
        a, b = pins
        # Try both pin orders so you don't have to know which is SDA/SCL
        seen = []
        for scl, sda in ((a, b), (b, a)):
            i2c = I2C(bus_id, scl=Pin(scl), sda=Pin(sda), freq=400000)
            found = i2c.scan()
            seen += [hex(x) for x in found if hex(x) not in seen]
            for addr in SUPPORTED:
                if addr in found:
                    self.i2c = i2c
                    self.addr = addr
                    break
            if self.i2c:
                break
        if self.i2c is None:
            raise OSError("No supported color sensor on pins %d and %d. "
                          "Devices found: %s."
                          % (a, b, seen if seen else "none"))

        if self.addr == VEML6040_ADDR:
            # Config: 40 ms integration, auto mode, sensor enabled
            self.i2c.writeto_mem(self.addr, 0x00, bytes([0x00, 0x00]))
            self.interval_ms = 41
        else:
            w = lambda reg, v: self.i2c.writeto_mem(self.addr, 0x80 | reg, bytes([v]))
            w(0x00, 0x01)        # power on
            time.sleep_ms(3)
            w(0x01, 0xFD)        # integration time: 3 cycles = 7.2 ms
            w(0x0F, 0x01)        # gain: 4x
            w(0x00, 0x03)        # power on + measure continuously
            self.interval_ms = 8
        self._last = time.ticks_add(time.ticks_ms(), -self.interval_ms)
        time.sleep_ms(self.interval_ms + 5)   # let the first reading finish

    def _wait_for_new_reading(self):
        # Reading faster than the sensor measures just returns the same
        # value again, so wait until a fresh one is ready.
        wait = self.interval_ms - time.ticks_diff(time.ticks_ms(), self._last)
        if wait > 0:
            time.sleep_ms(wait)
        self._last = time.ticks_ms()

    def _word(self, reg):
        d = self.i2c.readfrom_mem(self.addr, reg, 2)
        return d[0] | (d[1] << 8)

    def rgbc(self):
        """Returns (red, green, blue, clear/white) raw readings."""
        self._wait_for_new_reading()
        if self.addr == VEML6040_ADDR:
            return (self._word(0x08), self._word(0x09),
                    self._word(0x0A), self._word(0x0B))
        d = self.i2c.readfrom_mem(self.addr, 0xA0 | 0x14, 8)
        c = d[0] | (d[1] << 8)
        r = d[2] | (d[3] << 8)
        g = d[4] | (d[5] << 8)
        b = d[6] | (d[7] << 8)
        return r, g, b, c

    def brightness(self):
        return self.rgbc()[3]


def make_sensor():
    """Returns the color sensor."""
    return ColorSensor(0, SENSOR_PINS)


# ----------------------------------------------------------------------
# KNN classifier
# ----------------------------------------------------------------------
def features(r, g, b, c, white_c):
    """Turns a raw reading into 4 numbers that compare well between colors.

    The first three are the color's proportions of red, green and blue
    (so a dim red and a bright red look alike). The fourth is brightness
    relative to white paper, which separates black from white.
    """
    if c == 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (r / c, g / c, b / c, c / white_c)


def knn(f, samples, k=K):
    """Returns the most common label among the k closest samples."""
    nearest = []
    for s in samples:
        d = ((f[0] - s[0]) ** 2 + (f[1] - s[1]) ** 2 +
             (f[2] - s[2]) ** 2 + (f[3] - s[3]) ** 2)
        nearest.append((d, s[4]))
    nearest.sort()

    votes = {}
    for _, label in nearest[:k]:
        votes[label] = votes.get(label, 0) + 1
    return max(votes, key=votes.get)


class ColorClassifier:
    """Loads the saved samples. Use .classify(reading), where reading is
    the (r, g, b, c) tuple from sensor.rgbc(). Returns "red", "white" or "black"."""

    def __init__(self):
        try:
            import color_samples as cs
        except ImportError:
            raise SystemExit("No color samples - run color_knn.py first to calibrate.")
        self.samples = cs.SAMPLES
        self.white_c = cs.WHITE_C

    def classify(self, reading):
        return knn(features(*reading, self.white_c), self.samples)


# ----------------------------------------------------------------------
# Calibration (runs only when this file is run directly)
# ----------------------------------------------------------------------
def collect(sensor):
    readings = []
    for _ in range(SAMPLES_PER_COLOR):
        readings.append(sensor.rgbc())
        time.sleep_ms(SAMPLE_GAP_MS)
    return readings


def average_clear(readings):
    return sum(r[3] for r in readings) // len(readings)


def calibrate():
    sensor = make_sensor()
    print("Sensor found.")
    print("While each set of readings is taken (2 seconds), slowly slide the")
    print("sensor around inside the area, staying away from edges.\n")

    raw = {}
    for label, where in STEPS:
        input("Place the sensor %s, then press Enter..." % where)
        raw[label] = collect(sensor)
        print("   done\n")

    white_c = average_clear(raw["white"])
    black_c = average_clear(raw["black"])
    if white_c - black_c < 100:
        print("WARNING: sensor barely tells black from white.")
        print("         Check its height above the floor and its LED.\n")

    samples = []
    for label, readings in raw.items():
        for r, g, b, c in readings:
            f4 = features(r, g, b, c, white_c)
            samples.append((round(f4[0], 3), round(f4[1], 3),
                            round(f4[2], 3), round(f4[3], 3), label))

    with open("color_samples.py", "w") as f:
        f.write("# Written by color_knn.py\n")
        f.write("WHITE_C = %d\n" % white_c)
        f.write("SAMPLES = [\n")
        for s in samples:
            f.write("    %r,\n" % (s,))
        f.write("]\n")

    print("Saved color_samples.py on the ESP32.\n")

    input("Press Enter for a live test (press Stop in Thonny to end)...")
    while True:
        print("sees:", knn(features(*sensor.rgbc(), white_c), samples))
        time.sleep_ms(200)


if __name__ == "__main__":
    calibrate()