import neopixel
from machine import ADC, Pin
from time import ticks_ms, ticks_diff, sleep

x = ADC(Pin(36))
y = ADC(Pin(39))
led = Pin(19, Pin.OUT)


# Full 0–3.3V input range
x.atten(ADC.ATTN_11DB)
y.atten(ADC.ATTN_11DB)

x_min = 900
x_max = 3000
y_min = 900
y_max = 3000

joystick_positions = ["center"]
inputs = []
print(joystick_positions[-1])
konami = ["up", "up", "down", "down", "left", "right",
          "left", "right", "B", "A"]

# Morse code: A (Dash-Dot-Dot)
# Morse code: B

# NeoPixel setup
lights = neopixel.NeoPixel(Pin(15), 2)

# button setup
btn_a = Pin(34, Pin.IN, Pin.PULL_UP)
btn_b = Pin(35, Pin.IN, Pin.PULL_UP)
DEBOUNCE_MS = 200
last_press = 0

state = 1  # 0 = blinking plane lights, 1 = hue cycle

def button_handler(pin):
    global last_press, state
    curr_time = ticks_ms()
    if ticks_diff(curr_time, last_press) > DEBOUNCE_MS:
        if pin.value() == 0:
            last_press = curr_time
            if pin == btn_a:
                inputs.append("A")
                if (len(inputs) > 10): del inputs[0]
            elif pin == btn_b:
                inputs.append("B")
                if (len(inputs) > 10): del inputs[0]
            print(inputs, len(inputs))
            #print(pin)
            #state = 1 - state  # toggle state
            #print("Button pressed, State:", state)

btn_a.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
btn_b.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

# Color wheel helper function was pulled from the
# internet because I didn't know how to do hue shifting
def color_wheel(pos):
    pos = pos % 256
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)

# Main loop
last_update_time = 0
blink_interval = 1000  # ms, for state 0

blink_on = True
hue = 0

# pw = [up, up, down, down, left, right, left, right]
# up is x < 3% (toward grove port)
# down is x > 97% (away from grove port)
# left is y < 3%
# right is y > 97%

while True:
    curr_time = ticks_ms()
    x_voltage = x.read()   # 0–4095
    y_voltage = y.read()
    x_norm = (x_voltage - x_min) / (x_max - x_min)
    y_norm = (y_voltage - y_min) / (y_max - y_min)
    #print (x_norm, y_norm)
    pressed = x_voltage > 4000   # button press drives X to its maximum



    if state == 0:
        if ticks_diff(curr_time, last_update_time) >= blink_interval:
            last_update_time = curr_time
            blink_on = not blink_on
            if blink_on:
                lights[0] = (0, 20, 2)   # green
                lights[1] = (0, 0, 0)    # off
            else:
                lights[0] = (0, 0, 0)    # off
                lights[1] = (20, 0, 0)   # red
            lights.write()

    else:
        #if
        if (x_norm > 0.95 and joystick_positions[-1] != "up"):
            joystick_positions.append("up")
        elif x_norm < 0.05 and joystick_positions[-1] != "down":
            if pressed == 0: joystick_positions.append("down")
            #print(inputs)
        elif y_norm < 0.05 and joystick_positions[-1] != "left":
            joystick_positions.append("left")
            #print(inputs)
        elif y_norm > 0.95 and joystick_positions[-1] != "right":
            joystick_positions.append("right")
            #print(inputs)
        elif abs(x_norm - 0.5) < 0.03 and abs(y_norm - 0.5) < 0.03:
            if joystick_positions[-1] != "center":
                inputs.append(joystick_positions[-1])
                if (len(inputs) > 10): del inputs[0]
                joystick_positions.append("center")
                print(inputs, len(inputs))


        if inputs == konami:
            led.on()
        else:
            led.off()


        #print(f"X: {x_norm:.2f} Y: {y_norm:.2f} Pressed: {pressed}")