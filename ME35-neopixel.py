import neopixel #importing the library
import time
from machine import Pin # another way of importing a library
lights = neopixel.NeoPixel(Pin(15),2) # 0 is the Pin for neopixel and 4 is the number of lights
lights[0] = (20,0,20) # set the color of 0th light to purple
for i in range(0,10):
    lights[0] = (20,0,20)
    time.sleep(1)
    lights.write()
    lights[0] = (0,0,0)
    time.sleep(1)
    lights.write()
lights.write()