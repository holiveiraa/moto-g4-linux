#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated real Tk review: touch navigation, scrolling and form isolation. No API."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def main():
    os.environ['DISPLAY'] = ':9'
    folder = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
    loader = importlib.machinery.SourceFileLoader('panel_review', str(folder/'moto-shell'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    ui = importlib.util.module_from_spec(spec)
    loader.exec_module(ui)
    ui.SOCKET = '/run/moto-panel-v2-review.sock'
    ui.Shell.write_geometry = lambda self: None
    ui.Shell.vpn_worker = lambda self: None
    ui.Shell.refresh_tmux = lambda self: None
    ui.Shell.refresh_tmux_once = lambda self: None
    shell = ui.Shell()
    p = shell.panel
    services = ui.panel_module.services
    services.wifi_saved = lambda: []
    services.wifi_scan = lambda: [{'ssid': 'Rede de teste longa ' + str(i), 'signal': -55,
        'band': '2.4 GHz', 'supported': True, 'secure': True} for i in range(12)]
    shell.device = {'battery': '78', 'charging': 'Discharging',
                    'wifi': {'ssid': 'Rede de casa', 'wpa_state': 'COMPLETED'},
                    'vpn': services.tailscale_view({'BackendState': 'Running', 'TailscaleIPs': ['100.64.0.1'],
                                                  'Self': {'Online': True}}), 'ssh_auth': {}}
    sent = []
    shell.keys.send = lambda *args: sent.append(args)
    def pump():
        shell.root.update()
    def footer_ok():
        pump()
        bottom = shell.h-(shell.kh if shell.visible else 0)
        assert p.footer.winfo_rooty()+p.footer.winfo_height() <= bottom
        assert p.footer.winfo_rooty() >= shell.hh
        assert any(w.cget('text').endswith('Terminal') for w in p.footer.winfo_children())
    def capture(name):
        pump()
        subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-v2-'+name+'.xwd'], check=True)
    def click(button):
        p.scroll.reveal(button)
        pump()
        x, y = button.winfo_width()//2, button.winfo_height()//2
        button.event_generate('<ButtonPress-1>', x=x, y=y)
        button.event_generate('<ButtonRelease-1>', x=x, y=y)
        pump()
    try:
        with tempfile.TemporaryDirectory(prefix='moto-v2-review-', dir='/run') as temp:
            ui.panel_module.voice_module.voice.CONFIG = Path(temp)/'groq.json'
            ui.panel_module.voice_module.voice.capture_device = lambda: ''
            shell.mods.add('Ctrl'); shell.draw()
            before_keys = tuple(shell.canvas.find_all())
            p.home(); pump()
            assert tuple(shell.canvas.find_all()) == before_keys, 'Hidden keyboard was redrawn'
            assert not shell.mods
            shell.close_menu(); pump()
            assert shell.visible and tuple(shell.canvas.find_all()) != before_keys
            assert shell.key_rects['mod:Ctrl'][1] == ui.KEY, 'Cleared Ctrl is still highlighted'
            print('PASS: hidden keyboard is not redrawn; returning rebuilds keys with cleared modifiers')
            times = []
            for _ in range(5):
                start = time.monotonic()
                p.home(); pump()
                times.append(round((time.monotonic()-start)*1000, 1))
            footer_ok(); capture('home')
            original_brightness = shell.brightness
            original_light = shell.light
            brightness_writes = []
            def fake_brightness(value, persist=True):
                shell.light = value
                brightness_writes.append((value, persist))
            shell.brightness = fake_brightness
            p.home(); pump()
            assert not brightness_writes, 'Opening panel changed brightness'
            slider = p.brightness_slider
            width, height = slider.winfo_width(), slider.winfo_height()
            assert height >= p.u(48) and width >= p.u(96)
            slider.event_generate('<ButtonPress-1>', x=width//4, y=height-3)
            slider.event_generate('<B1-Motion>', x=width*3//4, y=height-3)
            pump()
            assert brightness_writes and not any(persist for _, persist in brightness_writes)
            assert 12 <= shell.light <= 255
            slider.event_generate('<ButtonRelease-1>', x=width*3//4, y=height-3)
            pump()
            assert sum(persist for _, persist in brightness_writes) == 1
            previous = slider.value
            square_minus = next(w for w in descendants(slider.master) if isinstance(w, tk.Button) and w.cget('text') == '−')
            assert square_minus.winfo_width() >= p.u(48) and square_minus.winfo_height() >= p.u(48)
            click(square_minus)
            assert slider.value == previous-5
            assert sum(persist for _, persist in brightness_writes) == 2
            slider.set(-999, commit=True); assert slider.value == 5 and shell.light >= 12
            slider.set(999, commit=True); assert slider.value == 100 and shell.light == 255
            shell.brightness, shell.light = original_brightness, original_light
            p.home(); pump(); capture('home')
            print('PASS: brightness full-height touch, immediate preview, one save per release, +/-5%, safe limits; hardware writes stubbed')
            click(next(w for w in descendants(p.body) if isinstance(w, tk.Button) and w.cget('text').startswith('SSH')))
            assert p.page == 'ssh'
            footer_ok(); capture('connections')
            p.wifi(); pump()
            deadline = time.monotonic()+3
            while len(p.networks.winfo_children()) < 7 and time.monotonic() < deadline:
                pump(); time.sleep(.02)
            footer_ok()
            button = p.networks.winfo_children()[0]
            p.scroll.reveal(button); pump()
            button.event_generate('<ButtonPress-1>', x=40, y=50)
            button.event_generate('<B1-Motion>', x=40, y=-200)
            button.event_generate('<ButtonRelease-1>', x=40, y=-200)
            pump()
            assert p.page == 'wifi', 'Scroll gesture activated a network'
            assert p.scroll.canvas.yview()[0] > 0, 'Drag did not scroll'
            p.back(); assert p.page == 'home'
            print('PASS: native press/release navigation, drag cancels activation, visible fixed footer')

            p.credentials('Rede de teste', True); pump()
            for char in 'testSecret123': shell.emit(char)
            assert p.entry.get() == 'testSecret123' and p.entry.cget('show')
            assert not sent
            p.scroll.reveal(p.entry); pump()
            assert p.entry.winfo_rooty() >= p.scroll.canvas.winfo_rooty()
            footer_ok(); capture('wifi-form')
            p.voice.configure(); pump()
            shell.emit('x')
            assert p.entry.get() == 'x' and not sent
            entry = p.entry
            challenge = 'https://login.tailscale.com/a/test-only-pending'
            shell.device['ssh_auth'] = {'url': challenge, 'pane': '%99'}
            p.update(); pump()
            assert p.entry is entry and p.entry.get() == 'x' and p.page == 'voice-key'
            assert p.last_ssh_auth_shown != challenge
            shell.device['ssh_auth'] = {}
            p.update(); pump()
            assert p.entry is entry and p.auth_notice is None
            footer_ok(); capture('voice-key')
            p.back(); assert p.page == 'voice'
            p.system(); p.terminal_tools(); p.back(); assert p.page == 'system'
            p.energy(); p.power('poweroff'); p.back(); assert p.page == 'energy'
            print('PASS: masked forms with keyboard, no terminal leakage, contextual Back, no power action invoked')
            print('PASS: asynchronous SSH challenge preserves the current form and its text')

            p.home(); pump()
            body = p.body
            p.scroll.canvas.yview_moveto(.4)
            before = p.scroll.canvas.yview()
            p.update(); pump()
            assert p.body is body and p.scroll.canvas.yview() == before
            # A stale worker cannot modify a newer page.
            import threading
            gate = threading.Event()
            called = []
            p.task(lambda: gate.wait(1), lambda result: called.append(result))
            p.connections(); gate.set()
            deadline = time.monotonic()+2
            while time.monotonic() < deadline:
                while not shell.events.empty(): shell.events.get_nowait()()
                pump(); time.sleep(.01)
            assert not called
            shell.close_menu(); assert shell.menu is None and shell.visible
            print('PASS: state refresh preserves view; stale worker ignored; terminal keyboard restored')
            print('Panel render ms (5 samples, not touch latency):', times)
    finally:
        shell.close_menu()
        shell.quick_voice.close()
        shell.sock.close()
        shell.root.destroy()
        Path(ui.SOCKET).unlink(missing_ok=True)


if __name__ == '__main__': main()
