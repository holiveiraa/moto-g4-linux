# SPDX-License-Identifier: MIT
"""Fullscreen original robot character. Rust supplies animated vector poses."""
import tkinter as tk

BACKGROUND = '#05090e'


class PetScene:
    def __init__(self, panel, options, close):
        self.p = panel
        self.w, self.h = panel.s.w, panel.s.h
        self.canvas = tk.Canvas(panel.body, bg=BACKGROUND, highlightthickness=0,
                                width=self.w, height=self.h, takefocus=True)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.focus_set()
        self.canvas.bind('<Escape>', lambda _: close())
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.options, self.close = options, close
        self.hold = None
        self.held = False
        self.eyes = [self.canvas.create_polygon(0, 0, 0, 0, fill='#7ff5cd', smooth=True, splinesteps=16) for _ in range(2)]
        self.shine = [self.canvas.create_oval(0, 0, 0, 0, fill='#dffff0', outline='') for _ in range(2)]
        self.cheeks = [self.canvas.create_oval(0, 0, 0, 0, fill='#15372e', outline='') for _ in range(2)]
        self.mouth = self.canvas.create_line(0, 0, 0, 0, fill='#7ff5cd', width=max(3, self.w//100), smooth=True, capstyle='round')
        self.open_mouth = self.canvas.create_oval(0, 0, 0, 0, fill='#7ff5cd', outline='')
        self.title = self.canvas.create_text(self.w/2, self.h*.13, text='H E R M E S',
                   fill='#4b6a73', font=('DejaVu Sans', -panel.u(13), 'bold'))
        self.caption = self.canvas.create_text(self.w/2, self.h*.78, text='Diga “Olá Hermes”',
                   fill='#d9eee8', width=self.w*.84, justify='center', font=('DejaVu Sans', -panel.u(23)))
        self.detail = self.canvas.create_text(self.w/2, self.h*.86, text='Seu companheiro por voz',
                   fill='#708b91', width=self.w*.83, justify='center', font=('DejaVu Sans', -panel.u(13)))
        self.canvas.create_text(self.w*.08, self.h*.045, text='×', fill='#647f88', font=('DejaVu Sans', -panel.u(30)))
        self.canvas.create_text(self.w*.92, self.h*.045, text='···', fill='#647f88', font=('DejaVu Sans', -panel.u(27), 'bold'))
        self.draw({'eyes':[[.285,.4,.235,.075],[.715,.4,.235,.075]],'accent':'#65d1c9','mouth':0,'smile':True,'breath':0})

    def press(self, event):
        self.held = False
        self.hold = self.canvas.after(650, self.show_options)

    def show_options(self):
        self.hold = None
        self.held = True
        self.options()

    def release(self, event):
        if self.hold is not None:
            self.canvas.after_cancel(self.hold)
            self.hold = None
        if self.held:
            return
        if event.y < self.h*.10:
            if event.x < self.w*.2:
                self.close()
            elif event.x > self.w*.8:
                self.options()

    def status(self, caption, detail=''):
        self.canvas.itemconfigure(self.caption, text=caption[:160])
        self.canvas.itemconfigure(self.detail, text=detail)

    def dispose(self):
        if self.hold is not None:
            self.canvas.after_cancel(self.hold)
            self.hold = None

    def draw(self, pose):
        size = min(self.w*.97, self.h*.67)
        ox, oy = (self.w-size)/2, self.h*.44-size*.43
        color = pose['accent']
        for i, (cx, cy, width, height) in enumerate(pose['eyes']):
            x, y = ox+(cx-width/2)*size, oy+(cy-height/2)*size
            w, h = width*size, max(4, height*size)
            r = min(w*.32, h*.45)
            points = [x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y]
            self.canvas.coords(self.eyes[i], *points)
            self.canvas.itemconfigure(self.eyes[i], fill=color)
            glint = min(size*.019, h*.12)
            self.canvas.coords(self.shine[i], x+w*.23-glint,y+h*.22-glint,x+w*.23+glint,y+h*.22+glint)
            cheek_x = ox+(.16 if i == 0 else .84)*size
            self.canvas.coords(self.cheeks[i],cheek_x-size*.034,oy+size*.57,cheek_x+size*.034,oy+size*.591)
        cx, my = ox+size*.5, oy+size*(.65+pose.get('breath',0))
        opening = pose.get('mouth',0)*size
        self.canvas.coords(self.open_mouth,cx-size*.05,my-opening,cx+size*.05,my+opening)
        self.canvas.itemconfigure(self.open_mouth,fill=color,state='normal' if opening > 1 else 'hidden')
        self.canvas.itemconfigure(self.mouth,fill=color,state='hidden' if opening > 1 else 'normal')
        curve = .035 if pose.get('smile',True) else -.015
        self.canvas.coords(self.mouth,cx-size*.08,my,cx,my+size*curve,cx+size*.08,my)
