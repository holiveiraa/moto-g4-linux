# SPDX-License-Identifier: MIT
"""Checks the user contract: controls are reachable and the exit stays visible."""
import tkinter as tk


def reachable(panel):
    shell = panel.s
    shell.root.update()
    viewport = panel.scroll.canvas
    assert viewport.winfo_height() > 100
    bottom = shell.h-(shell.kh if shell.visible else 0)
    assert panel.footer.winfo_rooty()+panel.footer.winfo_height() <= bottom
    old = viewport.yview()[0]
    def walk(parent):
        for widget in parent.winfo_children():
            yield widget
            yield from walk(widget)
    for widget in walk(panel.body):
        if isinstance(widget, (tk.Button, tk.Entry, tk.Text)) and widget.winfo_ismapped():
            assert widget.winfo_height() <= viewport.winfo_height(), ('control taller than viewport', str(widget))
            panel.scroll.reveal(widget)
            shell.root.update_idletasks()
            assert widget.winfo_rooty() >= viewport.winfo_rooty()-2, ('unreachable top', str(widget))
            assert widget.winfo_rooty()+widget.winfo_height() <= viewport.winfo_rooty()+viewport.winfo_height()+2, ('unreachable bottom', str(widget))
            assert 0 <= widget.winfo_rootx() and widget.winfo_rootx()+widget.winfo_width() <= shell.w, ('horizontal clipping', str(widget))
    viewport.yview_moveto(old)
    shell.root.update_idletasks()
