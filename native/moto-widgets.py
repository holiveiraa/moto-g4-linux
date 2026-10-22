# SPDX-License-Identifier: MIT
"""Shared touch components; no network, terminal or audio side effects."""
import math
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from collections import OrderedDict

BG, PANEL, KEY = '#0B1118', '#141E2A', '#1E2C3B'
FG, MUTED, ACCENT = '#F1F5FA', '#A8B8CA', '#68E3BC'
ERROR, SELECTED = '#FFADB6', '#205745'
_backgrounds = OrderedDict()
_background_bytes = 0
_BACKGROUND_LIMIT = 8 * 1024 * 1024


class TouchButton(tk.Button):
    """Native focus/disabled semantics with release-only, scroll-aware activation."""
    def __init__(self, parent, *, scroll=None, **kwargs):
        self.rounded_ready = False
        self.fill_color = kwargs.get('bg', KEY)
        kwargs['bg'] = kwargs['activebackground'] = BG
        super().__init__(parent, **kwargs)
        self.pad_y = int(self.cget('pady'))
        self.minimum_height = self.winfo_reqheight()
        self.background_image = None
        self.background_signature = None
        self.rounded_ready = True
        self.bind('<Configure>', self.paint)
        self.scroll = scroll
        self.down = None
        self.dragged = False
        self.rest_colors = None
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.release)

    def configure(self, cnf=None, **kwargs):
        if 'bg' in kwargs or 'background' in kwargs:
            self.fill_color = kwargs.get('bg', kwargs.get('background'))
            kwargs.pop('background', None)
            kwargs['bg'] = BG
        if 'activebackground' in kwargs:
            kwargs['activebackground'] = BG
        result = super().configure(cnf, **kwargs)
        if self.rounded_ready and any(key in kwargs for key in ('text', 'bg', 'background')):
            if 'text' in kwargs and self.background_image:
                font = tkfont.Font(font=self.cget('font'))
                limit = max(1, int(self.cget('wraplength')))
                lines = sum(max(1, math.ceil(font.measure(line)/limit)) for line in kwargs['text'].split('\n'))
                super().configure(height=max(self.minimum_height, lines*font.metrics('linespace')+2*self.pad_y)-2)
            self.paint()
        return result

    config = configure

    def cget(self, key):
        return self.fill_color if key in ('bg', 'background') else super().cget(key)

    def paint(self, event=None):
        global _background_bytes
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 3 or height <= 3:
            return
        # Tk adds an intrinsic two pixels to image buttons even with bd/padding
        # zero (verified on the installed Tk). Exclude it to avoid a resize loop.
        width, height = width-2, height-2
        fill = self.cget('bg')
        radius = min(24, width//4, height//4)
        key = (str(self.tk), width, height, fill, radius)
        if self.background_signature == key and self.background_image is not None:
            return
        image = _backgrounds.get(key)
        if image is None:
            image = tk.PhotoImage(master=self, width=width, height=height)
            image.put(BG, to=(0, 0, width, height))
            image.put(fill, to=(0, radius, width, height-radius))
            for y in range(radius):
                inset = round(radius-math.sqrt(radius*radius-(radius-y-.5)**2))
                image.put(fill, to=(inset, y, width-inset, y+1))
                image.put(fill, to=(inset, height-y-1, width-inset, height-y))
            _backgrounds[key] = image
            _background_bytes += width*height*4
            while _background_bytes > _BACKGROUND_LIMIT and len(_backgrounds) > 1:
                old_key, _ = _backgrounds.popitem(last=False)
                _background_bytes -= old_key[1]*old_key[2]*4
        else:
            _backgrounds.move_to_end(key)
        if self.background_image is image:
            return
        self.background_image = image
        self.background_signature = key
        # Image-sized buttons use pixel dimensions. Keep native focus, text,
        # disabled state and invoke behavior; only their background is custom.
        super().configure(image=image, compound='center', width=width, height=height, padx=0, pady=0)

    def press(self, event):
        if self.cget('state') == 'disabled':
            return 'break'
        self.down = (event.x_root, event.y_root)
        self.dragged = False
        self.rest_colors = (self.cget('bg'), self.cget('fg'))
        self.configure(state='normal', bg=ACCENT, fg=BG)
        if self.scroll:
            self.scroll.start(event)
        return 'break'

    def motion(self, event):
        if self.down:
            if max(abs(event.x_root-self.down[0]), abs(event.y_root-self.down[1])) > 18:
                self.dragged = True
                self.restore()
            if self.scroll:
                self.scroll.move(event)
        return 'break'

    def release(self, event):
        fire = self.down and not self.dragged and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self.down = None
        self.restore()
        if fire and self.cget('state') != 'disabled':
            self.invoke()
        return 'break'

    def restore(self):
        if self.rest_colors:
            self.configure(bg=self.rest_colors[0], fg=self.rest_colors[1])
            self.rest_colors = None


class ScrollBody(tk.Frame):
    """Body with an explicit touch scrollbar and drag-scrolling non-editable content."""
    def __init__(self, parent, scale):
        super().__init__(parent, bg=BG)
        self.scale = scale
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0, yscrollincrement=1)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.layout('Moto.Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children':
                     [('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure('Moto.Vertical.TScrollbar', background=KEY, troughcolor=BG,
                        bordercolor=BG, lightcolor=KEY, darkcolor=KEY, borderwidth=0,
                        width=scale(8))
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                 style='Moto.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.scrolled)
        self.gutter = tk.Frame(self, bg=BG, width=scale(10))
        self.gutter.pack(side='right', fill='y')
        self.gutter.pack_propagate(False)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = tk.Frame(self.canvas, bg=BG)
        self.item = self.canvas.create_window(scale(16), 0, anchor='nw', window=self.content)
        self.content.bind('<Configure>', self.layout)
        self.canvas.bind('<Configure>', self.resize)
        self.start_y = self.last_y = 0
        self.dragging = False
        self.bind_drag(self.canvas)
        self.bind_drag(self.content)

    def scrolled(self, first, last):
        self.bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.bar.place_forget()
        else:
            self.bar.place(in_=self.gutter, x=0, y=0, relheight=1, relwidth=1)

    def bind_drag(self, widget):
        widget.bind('<ButtonPress-1>', self.start)
        widget.bind('<B1-Motion>', self.move)
        widget.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta/120)*self.scale(32), 'units'))
        widget.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-self.scale(32), 'units'))
        widget.bind('<Button-5>', lambda e: self.canvas.yview_scroll(self.scale(32), 'units'))

    def start(self, event):
        self.start_y = self.last_y = event.y_root
        self.dragging = False

    def move(self, event):
        if abs(event.y_root-self.start_y) > self.scale(6):
            self.dragging = True
        if self.dragging:
            self.canvas.yview_scroll(int(self.last_y-event.y_root), 'units')
        self.last_y = event.y_root

    def resize(self, event):
        self.canvas.itemconfigure(self.item, width=max(1, event.width-self.scale(32)))
        self.layout()

    def layout(self, event=None):
        bbox = self.canvas.bbox('all')
        if bbox:
            self.canvas.configure(scrollregion=(0, 0, bbox[2], max(bbox[3]+self.scale(12), self.canvas.winfo_height())))

    def reveal(self, widget):
        """Keep a focused field visible without rebuilding it or changing its text."""
        self.update_idletasks()
        top = widget.winfo_rooty()-self.canvas.winfo_rooty()
        bottom = top+widget.winfo_height()
        if top < 0:
            self.canvas.yview_scroll(math.floor(top)-self.scale(8), 'units')
        elif bottom > self.canvas.winfo_height():
            self.canvas.yview_scroll(math.ceil(bottom-self.canvas.winfo_height())+self.scale(8), 'units')


class TouchSlider(tk.Canvas):
    """The full 48-unit surface tracks touch; persistence happens once on release."""
    def __init__(self, parent, scale, value, changed, committed, minimum=5, maximum=100):
        super().__init__(parent, height=scale(48), bg=BG, highlightthickness=1,
                         highlightbackground=BG, highlightcolor=ACCENT, takefocus=True)
        self.scale, self.value = scale, value
        self.minimum, self.maximum = minimum, maximum
        self.changed, self.committed = changed, committed
        self.held = False
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<Left>', lambda event: self.step(-5))
        self.bind('<Right>', lambda event: self.step(5))
        self.bind('<Home>', lambda event: self.set(self.minimum, commit=True))
        self.bind('<End>', lambda event: self.set(self.maximum, commit=True))

    def draw(self):
        self.delete('all')
        left, right = self.scale(14), max(self.scale(15), self.winfo_width()-self.scale(14))
        y = self.winfo_height()/2
        position = left+(right-left)*(self.value-self.minimum)/(self.maximum-self.minimum)
        self.create_line(left, y, right, y, fill=KEY, width=self.scale(8), capstyle='round')
        self.create_line(left, y, position, y, fill=ACCENT, width=self.scale(8), capstyle='round')
        radius = self.scale(12)
        self.create_oval(position-radius, y-radius, position+radius, y+radius, fill=ACCENT, outline='')

    def set(self, value, commit=False):
        value = max(self.minimum, min(self.maximum, round(value)))
        if value != self.value:
            self.value = value
            self.changed(value)
            self.draw()
        if commit:
            self.committed(value)
        return 'break'

    def at(self, event):
        left, right = self.scale(14), max(self.scale(15), self.winfo_width()-self.scale(14))
        self.set(self.minimum+(event.x-left)/(right-left)*(self.maximum-self.minimum))

    def press(self, event):
        self.focus_set()
        self.held = True
        self.at(event)
        return 'break'

    def motion(self, event):
        if self.held:
            self.at(event)
        return 'break'

    def release(self, event):
        if self.held:
            self.at(event)
            self.held = False
            self.committed(self.value)
        return 'break'

    def step(self, amount):
        return self.set(self.value+amount, commit=True)
