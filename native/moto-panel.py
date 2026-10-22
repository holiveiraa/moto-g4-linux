# SPDX-License-Identifier: MIT
"""Touch settings/dashboard built on the phone's existing Tk shell."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import tkinter as tk

loader = importlib.machinery.SourceFileLoader('moto_services', str(Path(__file__).with_name('moto-services.py')))
spec = importlib.util.spec_from_loader(loader.name, loader)
services = importlib.util.module_from_spec(spec)
loader.exec_module(services)
voice_spec = importlib.util.spec_from_file_location('moto_voice_panel', Path(__file__).with_name('moto-voice-panel.py'))
voice_module = importlib.util.module_from_spec(voice_spec)
voice_spec.loader.exec_module(voice_module)
widget_spec = importlib.util.spec_from_file_location('moto_widgets', Path(__file__).with_name('moto-widgets.py'))
widgets = importlib.util.module_from_spec(widget_spec)
widget_spec.loader.exec_module(widgets)
BG, PANEL, KEY, FG, MUTED, ACCENT = widgets.BG, widgets.PANEL, widgets.KEY, widgets.FG, widgets.MUTED, widgets.ACCENT

def sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

hosts = sibling('moto-hosts')
wifi_module = sibling('moto-wifi-panel')
ssh_module = sibling('moto-ssh-panel')
appearance_module = sibling('moto-appearance')


class DevicePanel:
    def __init__(self, shell):
        self.s = shell
        self.page = ''
        self._entry = None
        self.inputs = []
        self.input_focus_job = None
        self.submit = None
        self.generation = 0
        self.restore_keyboard = True
        self.photo = None
        self.vpn_busy = False
        self.vpn_signature = ''
        self.auth_link_visible = False
        self.last_ssh_auth_shown = ''
        self.ssh_auth_url = ''
        self.theme = widgets
        self.host_store = hosts.HostStore()
        self.wifi_ui = wifi_module.WifiPanel(self, services)
        self.ssh = ssh_module.SSHPanel(self)
        self.voice = voice_module.VoicePanel(self)
        self.voice_backend = voice_module.voice
        self.u = lambda value: max(1, round(value * self.s.w / 360))
        self.appearance = appearance_module.AppearancePanel(self)

    @property
    def entry(self):
        return self._entry

    @entry.setter
    def entry(self, widget):
        self.activate_input(widget)

    def activate_input(self, widget, take_focus=True, reveal=True):
        previous = self._entry
        self._entry = widget
        if self.input_focus_job is not None:
            self.s.root.after_cancel(self.input_focus_job)
            self.input_focus_job = None
        if previous is not widget:
            for field, active in ((previous, False), (widget, True)):
                if field is not None and field.winfo_exists():
                    field.configure(highlightbackground=ACCENT if active else KEY)
                    caption = getattr(field, '_moto_caption', None)
                    if caption is not None and caption.winfo_exists():
                        caption.configure(fg=ACCENT if active else MUTED)
        if widget is None or not widget.winfo_exists():
            return
        if reveal and previous is not widget:
            self.scroll.reveal(widget)
        if take_focus:
            generation = self.generation
            def restore():
                self.input_focus_job = None
                if (self.s.menu and self.generation == generation and self._entry is widget
                        and widget.winfo_exists() and widget.cget('state') == 'normal'
                        and not self.s.sleeping):
                    # Overrideredirect keyboard/menu windows do not reliably
                    # receive WM focus. Restore the actual Tk input after a tap.
                    if widget.focus_get() is not widget:
                        widget.focus_force()
            self.input_focus_job = self.s.root.after_idle(restore)

    def register_input(self, widget, caption=None):
        widget._moto_caption = caption
        self.inputs.append(widget)
        widget.configure(insertbackground=ACCENT, insertwidth=self.u(2),
                         insertontime=600, insertofftime=400, highlightthickness=self.u(2),
                         highlightbackground=KEY, highlightcolor=ACCENT,
                         selectbackground=widgets.SELECTED, selectforeground=FG, exportselection=False)
        def touched(event):
            if widget.cget('state') == 'normal':
                self.activate_input(widget)
        widget.bind('<ButtonRelease-1>', touched, add='+')
        widget.bind('<FocusIn>', lambda event: self.activate_input(widget, take_focus=False), add='+')
        widget.bind('<Tab>', lambda event: self.next_input(widget), add='+')
        widget.bind('<Shift-Tab>', lambda event: self.next_input(widget, True), add='+')
        widget.bind('<ISO_Left_Tab>', lambda event: self.next_input(widget, True), add='+')
        return widget

    def next_input(self, current, reverse=False):
        fields = [field for field in self.inputs if field.winfo_exists() and field.cget('state') == 'normal']
        if fields:
            index = fields.index(current) if current in fields else -1
            self.entry = fields[(index+(-1 if reverse else 1)) % len(fields)]
        return 'break'

    def begin(self, title, page, editing=False, keep_voice=False):
        s = self.s
        self.appearance.leave(page)
        if hasattr(s, 'quick_voice') and s.quick_voice.active:
            s.quick_voice.cancel()
        if not keep_voice:
            self.voice.leave()
        if not s.menu:
            self.restore_keyboard = s.visible
        else:
            s.menu.destroy()
        self.generation += 1
        self.page, self.entry, self.submit = page, None, None
        self.inputs = []
        self.last_metrics = None
        s.visible = editing
        s.keyboard.deiconify() if editing else s.keyboard.withdraw()
        height = s.h - (s.kh if editing else 0)
        s.menu = s.window(s.w, height, 0, 0)
        s.header.withdraw()
        bar = tk.Frame(s.menu, bg=BG)
        bar.pack(fill='x', padx=self.u(16), pady=(self.u(12), self.u(8)))
        tk.Label(bar, text=title, bg=BG, fg=FG, anchor='w', wraplength=s.w-self.u(32),
                 font=('DejaVu Sans', -self.u(24), 'bold')).pack(fill='x')
        self.notice_bar = tk.Frame(s.menu, bg=BG)
        self.notice_bar.pack(fill='x', padx=self.u(16))
        self.auth_notice = None
        self.footer = tk.Frame(s.menu, bg=BG)
        self.footer.pack(side='bottom', fill='x', padx=self.u(16), pady=self.u(8))
        self.scroll = widgets.ScrollBody(s.menu, self.u)
        self.scroll.pack(fill='both', expand=True)
        self.body = self.scroll.content
        if page == 'home':
            self.button('← Terminal', s.close_menu, parent=self.footer, side='left', color=ACCENT)
            self.button('Energia', self.energy, parent=self.footer, side='right')
        else:
            self.button('‹ Voltar', self.back, parent=self.footer, side='left')
            self.button('Terminal', s.close_menu, parent=self.footer, side='right', color=ACCENT)
        s.mods.clear()
        s.draw()
        s.resize_terminal()
        s.menu.lift()
        if editing:
            s.keyboard.lift()
        s.write_geometry()

    def label(self, text, size=28, color=None, parent=None, **pack):
        color = FG if color is None else color
        label = tk.Label(parent or self.body, text=text, bg=BG, fg=color,
                         font=('DejaVu Sans', -max(self.u(14), size)), justify='left', anchor='w',
                         wraplength=self.s.w-self.u(46))
        label.pack(fill='x', pady=self.u(4), **pack)
        self.scroll.bind_drag(label)
        return label

    def button(self, text, action, parent=None, side=None, size=30, color=None):
        color = KEY if color is None else color
        color = KEY if color == '#223249' else color
        font_size = max(self.u(14), size)
        footer = parent is getattr(self, 'footer', None)
        b = widgets.TouchButton(parent or self.body, scroll=None if footer else self.scroll,
                      text=text, command=action, bg=color, fg=BG if color == ACCENT else FG,
                      activebackground=color, activeforeground=BG if color == ACCENT else FG, disabledforeground=MUTED,
                      relief='flat', bd=0, highlightthickness=0, takefocus=True,
                      font=('DejaVu Sans', -font_size), padx=self.u(10),
                      anchor='center' if footer or text in ('−', '+') else 'w', justify='left',
                      pady=max(self.u(8), (self.u(48)-int(font_size*1.25))//2),
                      wraplength=(self.s.w-self.u(72))//2 if side else self.s.w-self.u(72))
        b.pack(**({'side': side, 'padx': self.u(2), 'fill': 'x', 'expand': True} if side else {'fill': 'x', 'pady': self.u(4)}))
        return b

    def row(self):
        frame = tk.Frame(self.body, bg=BG)
        frame.pack(fill='x', pady=6)
        self.scroll.bind_drag(frame)
        return frame

    def task(self, function, success):
        generation = self.generation
        def work():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, str(exc)
            def finish():
                if not self.s.menu or self.generation != generation:
                    return
                if error:
                    self.note.configure(text=error, fg=widgets.ERROR)
                else:
                    success(value)
            self.s.events.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def home(self):
        self.begin('Painel', 'home')
        self.metrics = self.label('Lendo o aparelho…', color=MUTED)
        row = self.row()
        self.wifi_tile = self.button('Wi-Fi\nVer redes', self.wifi, parent=row, side='left', color=PANEL)
        self.vpn_tile = self.button('VPN / Tailscale\nVer conexão', self.vpn, parent=row, side='left', color=PANEL)
        percent = max(5, min(100, round(self.s.light/255*100)))
        self.brightness_label = self.label(f'Brilho  {percent}%', color=FG)
        row = self.row()
        self.square_button(row, '−', lambda: self.brightness_slider.step(-5), 'left')
        self.square_button(row, '+', lambda: self.brightness_slider.step(5), 'right')
        self.brightness_slider = widgets.TouchSlider(row, self.u, percent,
                lambda value: self.set_brightness(value, False), lambda value: self.set_brightness(value, True))
        self.brightness_slider.pack(side='left', fill='x', expand=True, padx=self.u(8))
        row = self.row()
        self.volume_label = self.label('Volume', parent=row)
        self.volume_label.pack_forget()
        self.volume_label.pack(side='left', fill='x', expand=True)
        self.next_volume_check, self.current_volume = 0, None
        self.button('−', lambda: self.change_volume(-1), parent=row, side='left')
        self.button('+', lambda: self.change_volume(1), parent=row, side='left')
        self.button('SSH  ›', self.ssh.home, color=PANEL)
        self.button('Voz e áudio  ›', self.voice.home, color=PANEL)
        self.button('Aparência  ›', self.appearance.show, color=PANEL)
        self.button('Sistema  ›', self.system, color=PANEL)
        self.note = self.label('', color=MUTED)
        self.update()

    def square_button(self, parent, text, command, side):
        frame = tk.Frame(parent, bg=BG, width=self.u(48), height=self.u(48))
        frame.pack(side=side)
        frame.pack_propagate(False)
        button = self.button(text, command, parent=frame)
        button.pack_configure(fill='both', expand=True, padx=0, pady=0)
        return button

    def set_brightness(self, percent, persist):
        self.s.brightness(max(12, min(255, round(percent/100*255))), persist=persist)
        self.brightness_label.configure(text=f'Brilho  {percent}%')

    def change_volume(self, direction):
        def done(message):
            self.note.configure(text=message, fg=ACCENT)
            self.refresh_volume(force=True)
        self.task(lambda: services.volume(direction), done)

    def refresh_volume(self, force=False):
        now = time.monotonic()
        if not force and now < self.next_volume_check:
            return
        self.next_volume_check = now+1
        try:
            percent = max(0, min(100, int(json.loads(Path('/var/lib/moto-audio-volume.json').read_text())['percent'])))
            text = f'Volume  {percent}%'
        except (OSError, ValueError, KeyError, TypeError):
            text = 'Volume'
        if text != self.current_volume:
            self.current_volume = text
            self.volume_label.configure(text=text)

    def connections(self):
        # Compatibility entry point; each destination has its own page.
        self.begin('Conexões', 'connections')
        self.button('Wi-Fi', self.wifi)
        self.button('VPN / Tailscale', self.vpn)
        self.button('SSH', self.ssh.home)

    def footer_action(self, text, action):
        existing = self.footer.winfo_children()
        primary = self.button(text, action, parent=self.footer, side='left', color=ACCENT)
        existing[-1].configure(bg=KEY, fg=FG, activeforeground=FG)
        for child in self.footer.winfo_children():
            child.pack_forget()
        for index, child in enumerate([existing[0], primary, existing[-1]]):
            child.grid(row=0, column=index, sticky='nsew', padx=self.u(2))
            self.footer.columnconfigure(index, weight=1, uniform='actions')

    def terminal_tools(self):
        self.begin('Terminal e teclado', 'terminal-tools')
        row = self.row()
        self.button('Texto −', lambda: self.s.action('font-down'), parent=row, side='left')
        self.button('Texto +', lambda: self.s.action('font-up'), parent=row, side='left')
        row = self.row()
        self.button('Copiar seleção', self.s.copy_selection, parent=row, side='left')
        self.button('Colar', self.s.paste_buffer, parent=row, side='right')
        self.label('Ctrl, Alt e Shift: toque e depois a tecla. Segure e arraste no terminal para selecionar texto.', color=MUTED)

    def energy(self):
        self.begin('Energia', 'energy')
        self.label('Apagar a tela mantém o Linux ligado.', color=MUTED)
        self.button('Apagar tela', lambda: (self.s.close_menu(), self.s.action('screen-toggle')))
        self.button('Reiniciar…', lambda: self.power('reboot'))
        self.button('Desligar…', lambda: self.power('poweroff'), color=widgets.DANGER)

    def back(self):
        page = self.page
        if page in ('wifi', 'vpn', 'ssh'):
            self.home()
        elif page.startswith('wifi-'):
            self.wifi_ui.back()
        elif page.startswith('ssh-'):
            self.ssh.back()
        elif page == 'credentials':
            self.wifi()
        elif page == 'vpn-details':
            self.vpn()
        elif page.startswith('voice-'):
            self.voice.home()
        elif page == 'power':
            self.energy()
        elif page in ('terminal-tools', 'system-info'):
            self.system()
        elif page == 'appearance':
            self.home()
        else:
            self.home()

    def update(self):
        request = self.s.device.get('ssh_auth') or {}
        if request.get('url') and request['url'] != self.last_ssh_auth_shown:
            protected = self.s.menu and (self.entry is not None or self.page.startswith('voice-')
                                         or self.page == 'appearance'
                                         or self.voice.busy or self.voice.stopping)
            if protected:
                if self.auth_notice is None:
                    self.auth_notice = tk.Label(self.notice_bar, text='SSH aguarda autorização. Termine esta edição primeiro.',
                            bg=widgets.SELECTED, fg=FG, font=('DejaVu Sans', -self.u(14)),
                            wraplength=self.s.w-self.u(48), padx=self.u(8), pady=self.u(8))
                    self.auth_notice.pack(fill='x', pady=self.u(4))
                return
            self.ssh_authorize()
            return
        if not self.s.menu:
            return
        if not request.get('url') and self.auth_notice is not None:
            self.auth_notice.destroy()
            self.auth_notice = None
        if self.page == 'ssh-auth':
            if not request.get('url'):
                self.s.close_menu()
                self.s.message('Verificação encerrada · voltando ao SSH')
            elif request['url'] != self.ssh_auth_url:
                self.ssh_authorize()
            return
        if self.page == 'vpn':
            state = self.s.device.get('vpn') or {}
            signature = json.dumps([state, request], sort_keys=True)
            if not self.vpn_busy and signature != self.vpn_signature:
                self.vpn()
            return
        if self.page == 'wifi':
            self.wifi_ui.update_status()
            return
        if self.page != 'home':
            return
        d = self.s.device
        self.refresh_volume()
        signature = (d.get('battery'), d.get('charging'), d.get('wifi', {}).get('ssid'),
                     d.get('vpn', {}).get('title'))
        if signature == self.last_metrics:
            return
        self.last_metrics = signature
        if not d:
            self.metrics.configure(text='Lendo o aparelho…')
            return
        wifi = d.get('wifi', {}).get('ssid', 'Sem rede')
        vpn = d.get('vpn', {}).get('title', 'Verificando')
        charging = ' · carregando' if d.get('charging') == 'Charging' else ''
        self.metrics.configure(text=f"{d.get('battery', '?')}% bateria{charging}")
        self.wifi_tile.configure(text='Wi-Fi\n' + wifi)
        self.vpn_tile.configure(text='VPN / Tailscale\n' + vpn)

    def wifi(self):
        self.wifi_ui.home()

    def scanned(self, networks):
        self.wifi_ui.scanned(networks)

    def field(self, caption, value='', secret=False):
        label = self.label(caption, 26, MUTED)
        entry = tk.Entry(self.body, font=('DejaVu Sans', -self.u(17)), bg=KEY, fg=FG, insertbackground=ACCENT,
                         relief='flat', show='●' if secret else '')
        entry.pack(fill='x', ipady=22, pady=6)
        entry.insert(0, value)
        return self.register_input(entry, label)

    def credentials(self, ssid, secure, hidden=False):
        self.wifi_ui.credentials(ssid, secure, hidden)

    def connect_wifi(self, ssid, password, secure, hidden=False):
        self.wifi_ui.connect(ssid, password, secure, hidden)

    def key(self, action, modifiers):
        e = self.entry
        if not e or not e.winfo_exists():
            return
        if e.cget('state') != 'normal':
            return
        self.activate_input(e, reveal=False)
        if action == 'Return':
            if self.submit:
                self.submit()
            return
        if action == 'Tab':
            self.next_input(e, 'Shift' in modifiers)
            return
        if action == 'Escape':
            self.back()
            return
        if isinstance(e, tk.Text):
            if 'Ctrl' in modifiers and action.lower() == 'a':
                e.tag_add('sel', '1.0', 'end-1c')
            elif action in ('Left', 'Right', 'Up', 'Down', 'Home', 'End'):
                movement = {'Left': '-1c', 'Right': '+1c', 'Up': '-1l', 'Down': '+1l'}
                position = 'insert linestart' if action == 'Home' else 'insert lineend' if action == 'End' else 'insert ' + movement[action]
                e.mark_set('insert', position)
                e.tag_remove('sel', '1.0', 'end')
            elif action in ('BackSpace', 'Delete'):
                if e.tag_ranges('sel'):
                    e.delete('sel.first', 'sel.last')
                elif action == 'BackSpace' and e.compare('insert', '>', '1.0'):
                    e.delete('insert-1c', 'insert')
                elif action == 'Delete':
                    e.delete('insert', 'insert+1c')
            elif len(action) == 1 and not ({'Ctrl', 'Alt'} & modifiers):
                if e.tag_ranges('sel'):
                    e.delete('sel.first', 'sel.last')
                e.insert('insert', action.upper() if 'Shift' in modifiers else action)
            e.see('insert')
            return
        if action in ('Left', 'Right', 'Home', 'End'):
            pos = e.index('insert')
            e.icursor(0 if action == 'Home' else 'end' if action == 'End' else max(0, pos + (-1 if action == 'Left' else 1)))
            e.xview('insert')
            return
        if action == 'BackSpace':
            if e.selection_present():
                e.delete('sel.first', 'sel.last')
            elif e.index('insert'):
                e.delete(e.index('insert')-1)
        elif action == 'Delete':
            e.delete('insert')
        elif 'Ctrl' in modifiers and action.lower() == 'a':
            e.selection_range(0, 'end')
        elif len(action) == 1 and not ({'Ctrl', 'Alt'} & modifiers):
            if e.selection_present():
                e.delete('sel.first', 'sel.last')
            e.insert('insert', action.upper() if 'Shift' in modifiers else action)
        e.xview('insert')

    def vpn(self):
        self.begin('VPN / Tailscale', 'vpn')
        state = self.s.device.get('vpn') or services.tailscale_view({})
        self.vpn_signature = json.dumps([state, self.s.device.get('ssh_auth') or {}], sort_keys=True)
        active = state.get('connected', False)
        kind = state.get('kind', 'unavailable')
        self.label(state.get('title', 'Lendo conexão…'), 33, ACCENT if active else MUTED)
        self.note = self.label(state.get('detail', ''), 26, MUTED)
        if state.get('ip'):
            self.label(f"IP: {state['ip']}  ·  {state.get('name', 'moto-g4-linux')}", 25)
        if kind == 'network':
            self.button('Abrir Wi-Fi', self.wifi)
        elif kind not in ('connected', 'warning', 'approval', 'degraded'):
            caption = 'Retomar VPN' if kind == 'paused' else ('Gerar QR de autorização' if kind == 'login' else 'Conectar')
            if kind != 'login' or not state.get('url'):
                b = self.button(caption, self.connect_vpn)
                if self.vpn_busy:
                    b.configure(state='disabled', text='Conectando…')
        if kind == 'login' and state.get('url'):
            self.auth(state['url'])
        if self.s.device.get('ssh_auth', {}).get('url'):
            self.label('Uma sessão SSH aguarda autorização no terminal.', color=MUTED)
        if state.get('can_ssh'):
            self.label('Últimos aparelhos vistos' if kind == 'degraded' else 'Na sua rede agora', 27, MUTED)
            for peer in state['peers'][:4]:
                self.label(f"● {peer['name']}   {peer['ip']}", 26)
            self.button('Pausar VPN neste aparelho', self.pause_vpn, size=26)
        if state.get('health'):
            self.button('Ver diagnóstico da conexão', self.vpn_diagnostics, size=26)
        if kind in ('degraded', 'unavailable'):
            self.button('Reconectar sem recadastrar', self.reconnect_vpn, size=27)
        row = self.row()
        self.button('Verificar agora', self.refresh_vpn, parent=row, side='left')

    def refresh_vpn(self):
        self.note.configure(text='Verificando a conexão…')
        self.task(lambda: services.snapshot()['vpn'], self.vpn_result)

    def vpn_result(self, state):
        self.s.device['vpn'] = state
        self.vpn()

    def vpn_diagnostics(self):
        self.begin('Conexão', 'vpn-details')
        state = self.s.device.get('vpn') or {}
        self.label(state.get('title', 'Sem estado'), 32)
        for warning in state.get('health', [])[:4]:
            self.label(warning, 23, MUTED)
        if state.get('key_expiry'):
            self.label('Validade informada pelo Tailscale:\n' + state['key_expiry'], 23, MUTED)
        self.label('Wi-Fi sem Internet, serviço indisponível e cadastro expirado são problemas diferentes. Verificar a conexão não apaga seu cadastro.', 24, MUTED)

    def connect_vpn(self):
        self.vpn_operation(services.tailscale_connect)

    def reconnect_vpn(self):
        self.vpn_operation(services.tailscale_reconnect)

    def vpn_operation(self, operation):
        if self.vpn_busy:
            return
        self.vpn_busy = True
        self.note.configure(text='Conectando à sua rede…')
        def connect():
            try:
                return operation()
            finally:
                self.vpn_busy = False
        self.task(connect, self.vpn_result)

    def pause_vpn(self):
        self.task(lambda: services.command('tailscale', 'down'), lambda _: self.paused())

    def paused(self):
        self.s.device['vpn'] = services.tailscale_state()
        self.vpn()

    def auth(self, url, ssh=False):
        url = services.tailscale_auth_url(url)
        if not url:
            self.label('Não foi possível obter um link oficial. Verifique a conexão.', 24, MUTED)
            return
        self.label('Leia com a câmera do iPhone ou de outro celular e confirme no navegador.', 28)
        try:
            # Private temporary file is deleted after Tk loads it; no old QR remains.
            with tempfile.NamedTemporaryFile(prefix='moto-vpn-', suffix='.png', dir='/run') as png:
                subprocess.run(['qrencode', '-o', png.name, '-s', '9', '-m', '4', url],
                               check=True, timeout=3, capture_output=True)
                self.photo = tk.PhotoImage(file=png.name)
                maximum = min(self.s.w - 140, 640)
                factor = max(1, (self.photo.width() + maximum - 1) // maximum)
                if factor > 1:
                    self.photo = self.photo.subsample(factor)
            tk.Label(self.body, image=self.photo, bg='white', padx=20, pady=20).pack(pady=12)
        except (OSError, subprocess.SubprocessError, tk.TclError):
            self.auth_link_visible = True
            self.label('QR indisponível. Use o link alternativo abaixo.', 24, MUTED)
        self.label('O terminal volta automaticamente quando a solicitação de verificação encerrar.' if ssh else
                   'Pode deixar esta tela aberta: a conexão será confirmada automaticamente.', 24, ACCENT)
        if self.auth_link_visible:
            self.label(url, 22, ACCENT)
        else:
            self.button('Mostrar link alternativo', self.show_auth_link, size=24)

    def show_auth_link(self):
        self.auth_link_visible = True
        self.ssh_authorize() if self.page == 'ssh-auth' else self.vpn()

    def ssh_authorize(self):
        request = self.s.device.get('ssh_auth') or {}
        url = services.tailscale_auth_url(request.get('url', ''))
        if not url:
            return
        self.begin('Autorizar sessão SSH', 'ssh-auth')
        self.last_ssh_auth_shown = url
        self.ssh_auth_url = url
        self.label('Seu Moto já está na VPN.', 32, ACCENT)
        self.note = self.label('O servidor pediu uma verificação de segurança para esta sessão SSH. Isso não cadastra o Moto novamente.', 27, MUTED)
        self.auth(url, ssh=True)

    def close_terminal(self, ident):
        # Freeze ID and full name at confirmation time, never a shifting index.
        row = self.s.tabs.get(ident)
        if row is None:
            self.s.message('Essa aba já foi fechada')
            self.s.refresh_tmux_once()
            return
        self.begin('Fechar aba', 'close-terminal')
        self.label(row['name'], 40, ACCENT)
        self.label('Fecha esta aba e desconecta sua sessão SSH, se houver. Comandos em execução podem ser interrompidos.', 30)
        if len(self.s.tabs.list()) == 1:
            self.label('Um novo terminal local ficará no lugar, para você continuar usando o Moto.', 27, MUTED)
        self.button('Fechar esta aba', lambda target=row['id']: self.s.close_terminal(target), color=widgets.DANGER)
        self.button('Cancelar · voltar ao terminal', self.s.close_menu)

    def system(self):
        self.begin('Sistema', 'system')
        self.label('Personalize o seu espaço de trabalho.', color=MUTED)
        self.button('Terminal e teclado  ›', self.terminal_tools, color=PANEL)
        self.button('Sobre e diagnóstico  ›', self.system_info, color=PANEL)
        self.button('Energia  ›', self.energy, color=PANEL)
        self.label('Power: um toque apaga/acende a tela. Volume: ajusta o som.', color=MUTED)

    def system_info(self):
        self.begin('Sobre e diagnóstico', 'system-info')
        d = self.s.device
        self.label('Linux nativo · Alpine · aarch64', 32, ACCENT)
        self.label(f"Memória: {d.get('ram_free', '?')} MB livres de {d.get('ram_total', '?')} MB", 29)
        self.label(f"Inicialização: {'armazenamento interno' if d.get('persistent') else 'RAM temporária'}\n"
                   f"Armazenamento livre: {d.get('disk_free', '?')} MB\n"
                   f"Tempo ligado: {d.get('uptime', 0)//3600} h {(d.get('uptime', 0)//60)%60} min\n"
                   f"Alto-falante / microfone: {'placa disponível' if d.get('audio') else 'driver indisponível'}", 29)
        self.label('Para apagar/acender a tela: toque curto em Power.\nPara desligar: painel → Desligar.\nPara ligar após desligar: segure Power por alguns segundos.\nDesligar a tela ainda não suspende o sistema.', 27, MUTED)

    def power(self, operation):
        self.begin('Desligar' if operation == 'poweroff' else 'Reiniciar', 'power')
        installed = Path('/etc/moto-persistent').exists()
        self.label('Os arquivos e redes serão preservados. As sessões abertas serão encerradas.' if installed else
                   'A sessão atual ainda está em RAM. Desligar perde as alterações e volta ao sistema gravado no aparelho.', 32)
        self.label('A tela apagada por Power é diferente de desligar o aparelho.', 26, MUTED)
        self.button('Confirmar desligamento' if operation == 'poweroff' else 'Confirmar reinício',
                    lambda: subprocess.Popen(['/usr/sbin/moto-power', operation]), color=widgets.DANGER)
        self.button('Cancelar', self.home)
