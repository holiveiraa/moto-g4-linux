#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare local Tk image creation, isolated from the phone's visible display."""
import os
import time
import tkinter as tk
import math
import statistics

os.environ['DISPLAY'] = ':9'
root = tk.Tk(); root.withdraw()
width, height, radius = 976, 150, 24
bg, fill = '#0B1118', '#141E2A'


def puts():
    image = tk.PhotoImage(master=root, width=width, height=height)
    image.put(bg, to=(0, 0, width, height))
    image.put(fill, to=(0, radius, width, height-radius))
    for y in range(radius):
        inset = round(radius-math.sqrt(radius*radius-(radius-y-.5)**2))
        image.put(fill, to=(inset, y, width-inset, y+1))
        image.put(fill, to=(inset, height-y-1, width-inset, height-y))
    return image


def ppm():
    back, front = bytes.fromhex(bg[1:]), bytes.fromhex(fill[1:])
    top = []
    for y in range(radius):
        inset = round(radius-math.sqrt(radius*radius-(radius-y-.5)**2))
        top.append(back*inset+front*(width-2*inset)+back*inset)
    pixels = b''.join(top)+(front*width)*(height-2*radius)+b''.join(reversed(top))
    return tk.PhotoImage(master=root, data=f'P6\n{width} {height}\n255\n'.encode()+pixels, format='PPM')


try:
    a, b = puts(), ppm()
    for x, y in [(0,0),(width//2,0),(0,height//2),(width//2,height//2),(width-1,height-1)]:
        assert a.get(x,y) == b.get(x,y)
    for name, factory in [('put', puts), ('ppm', ppm)]:
        times = []
        for _ in range(30):
            start = time.monotonic()
            image = factory()
            root.update_idletasks()
            times.append((time.monotonic()-start)*1000)
        print(name, 'median_ms=', round(statistics.median(times),2))
finally:
    root.destroy()
