from machine import Pin, PWM
import time

# --- Servo setup ---
servo = PWM(Pin(19))
servo.freq(50)  # Standard servo frequency: 50 Hz

# --- Calibration values ---
MIN_DUTY = 1638   # ~0.5ms pulse (0 degrees) — adjust for your servo
MAX_DUTY = 8192   # ~2.5ms pulse (180 degrees) — adjust for your servo

def angle_to_duty(angle):
    """Convert an angle (0-180) to a duty_u16 value, reversed for clockwise motion."""
    reversed_angle = 180 - angle   # flips rotation direction
    return int(MIN_DUTY + (MAX_DUTY - MIN_DUTY) * reversed_angle / 180)

def set_angle(angle):
    duty = angle_to_duty(angle)
    servo.duty_u16(duty)

def move_slowly(start_angle, end_angle, step_delay=0.03):
    """Move the servo one degree at a time so the motion is visible."""
    step = 1 if end_angle > start_angle else -1
    for angle in range(start_angle, end_angle + step, step):
        set_angle(angle)
        time.sleep(step_delay)

# --- Main test sequence ---
print("Starting at 0 degrees")
set_angle(0)
time.sleep(1)

print("Moving slowly to 90 degrees...")
move_slowly(0, 90)
time.sleep(1)

print("Moving slowly to 180 degrees...")
move_slowly(90, 180)
time.sleep(1)

print("Done. Detaching PWM.")
servo.deinit()