# SPDX-License-Identifier: MIT
"""Wi-Fi screens: saved credentials are reused, never returned to the UI."""
import tkinter as tk


class WifiPanel:
    def __init__(self, panel, services):
        self.p, self.services = panel, services
        self.saved, self.busy, self.selected = [], False, None
        self.status_signature = None

    def home(self):
        p = self.p
        p.begin('Wi-Fi', 'wifi')
        self.status_label = p.label('Lendo a conexão…')
        self.status_signature = None
        self.update_status()
        p.note = p.label('Lendo redes salvas e buscando redes próximas…', color=p.theme.MUTED)
        p.label('REDES SALVAS', color=p.theme.MUTED)
        self.saved_frame = p.row()
        p.label('REDES PRÓXIMAS', color=p.theme.MUTED)
        p.networks = p.row()
        p.button('Outra rede / rede oculta', lambda: self.credentials('', True, hidden=True))
        p.button('Buscar novamente', self.home)
        def read():
            saved = self.services.wifi_saved()
            try:
                return {'saved': saved, 'nearby': self.services.wifi_scan()}
            except (RuntimeError, OSError):
                return {'saved': saved, 'nearby': [], 'error': 'Não foi possível buscar redes. As redes salvas continuam disponíveis.'}
        p.task(read, self.scanned)

    def update_status(self):
        d = self.p.s.device.get('wifi', {})
        signature = (d.get('wpa_state'), d.get('ssid'), d.get('ip_address'))
        if signature != self.status_signature:
            self.status_signature = signature
            text = 'Conectado a '+d.get('ssid', 'rede Wi-Fi') if d.get('wpa_state') == 'COMPLETED' else 'Nenhuma rede conectada'
            self.status_label.configure(text=text)

    def scanned(self, result):
        p = self.p
        if isinstance(result, list):
            result = {'saved': [], 'nearby': result}
        self.saved = result['saved']
        groups = {}
        for profile in self.saved:
            groups.setdefault((profile['ssid_hex'], profile['secure']), []).append(profile)
        for profiles in groups.values():
            profile = profiles[0]
            suffix = 'Conectada' if any(row['current'] for row in profiles) else 'Senha salva' if profile['secure'] else 'Rede salva'
            p.button(profile['ssid']+'\n'+suffix+'  ›', lambda row=profile: self.details(row), parent=self.saved_frame, color=p.theme.PANEL)
        if not groups:
            p.label('Nenhuma rede salva ainda.', parent=self.saved_frame, color=p.theme.MUTED)
        for net in result['nearby']:
            key = (net.get('ssid_hex', net['ssid'].encode().hex()), net['secure'])
            profiles = groups.get(key, [])
            caption = net['ssid']+'\n'+('Salva' if profiles else 'Protegida' if net['secure'] else 'Aberta')+' · '+net['band']
            action = (lambda row=profiles[0]: self.details(row)) if profiles else (lambda row=net: self.credentials(row['ssid'], row['secure']))
            button = p.button(caption, action, parent=p.networks)
            if not net['supported']:
                button.configure(state='disabled')
        p.note.configure(text=result.get('error') or 'Redes salvas conectam sem pedir a senha novamente.')

    def details(self, profile):
        self.selected = profile
        p = self.p
        p.begin('Rede salva', 'wifi-saved')
        p.label(profile['ssid'], size=p.u(22), color=p.theme.ACCENT)
        p.label('Protegida · credencial guardada no aparelho' if profile['secure'] else 'Rede aberta · sem senha', color=p.theme.MUTED)
        button = p.button('Conectar com dados salvos', lambda: self.run(lambda: self.services.wifi_connect_saved(profile)), color=p.theme.ACCENT)
        if not profile['supported']:
            button.configure(state='disabled')
        if profile['secure'] and profile['supported']:
            p.button('Atualizar senha', lambda: self.credentials(profile['ssid'], True, profile['hidden']))
        siblings = [row for row in self.saved if row['ssid_hex'] == profile['ssid_hex'] and row['secure'] == profile['secure']]
        if len(siblings) > 1:
            p.button(f'Perfis desta rede ({len(siblings)})', lambda: self.profiles(siblings))
        p.button('Esquecer este perfil…', lambda: self.forget(profile), color='#593040')
        p.note = p.label('Conectar não cria outro perfil. Falhas não apagam a senha salva.', color=p.theme.MUTED)
        if not profile['supported']:
            p.note.configure(text='Este perfil usa uma autenticação ainda não suportada pela interface.')

    def profiles(self, rows):
        p = self.p
        p.begin('Perfis Wi-Fi', 'wifi-profiles')
        p.label('Há mais de um perfil com este nome. Eles podem ter credenciais diferentes.', color=p.theme.MUTED)
        for profile in rows:
            p.button(profile['ssid']+' · perfil '+profile['id']+(' · conectado' if profile['current'] else ''), lambda row=profile: self.details(row))

    def forget(self, profile):
        self.selected = profile
        p = self.p
        p.begin('Esquecer rede', 'wifi-forget')
        p.label(profile['ssid'], size=p.u(22))
        p.label('Remove apenas este perfil e sua credencial salva. Se estiver conectado por ele, a rede será desconectada.')
        p.button('Esquecer este perfil', lambda: self.run(lambda: self.services.wifi_forget(profile)), color='#593040')
        p.note = p.label('Outros perfis e redes serão preservados.', color=p.theme.MUTED)

    def credentials(self, ssid, secure, hidden=False):
        p = self.p
        p.begin('Conectar Wi-Fi', 'credentials', editing=True)
        name = p.field('Nome da rede', ssid)
        password = p.field('Senha WPA2' if secure else 'Rede aberta — sem senha', secret=True) if secure else None
        p.entry = password or name
        p.note = p.label('A credencial fica somente neste aparelho.', color=p.theme.MUTED)
        p.submit = lambda: self.connect(name.get(), password.get() if password else '', secure, hidden)
        row = p.row()
        p.connect_button = p.button('Conectar e salvar', p.submit, parent=row, side='left', color=p.theme.SELECTED)
        if password:
            p.button('Ver senha', lambda: password.configure(show='' if password.cget('show') else '●'), parent=row, side='right')

    def connect(self, ssid, password, secure=True, hidden=False):
        self.run(lambda: self.services.wifi_join(ssid, password, secure, hidden))

    def run(self, function):
        p = self.p
        if self.busy:
            p.note.configure(text='Uma conexão já está em andamento. Aguarde alguns segundos.')
            return
        self.busy = True
        p.note.configure(text='Aplicando… o terminal continua disponível.', fg=p.theme.MUTED)
        def work():
            try:
                return function(), None
            except (OSError, RuntimeError, ValueError) as exc:
                return None, str(exc)
            finally:
                self.busy = False
        def done(result):
            value, error = result
            if error:
                p.note.configure(text=error, fg=p.theme.ERROR)
            elif isinstance(value, dict) and not value['saved']:
                p.note.configure(text=value['message'], fg=p.theme.ERROR)
                p.button('Salvar novamente', self.save_again)
            else:
                p.s.message(value['message'] if isinstance(value, dict) else value)
                self.home()
        p.task(work, done)

    def save_again(self):
        def save():
            if not self.services.wifi_save():
                raise RuntimeError('Ainda não foi possível salvar. A conexão atual foi mantida.')
            return 'Redes salvas no aparelho.'
        self.run(save)

    def back(self):
        if self.p.page == 'wifi-forget' and self.selected:
            self.details(self.selected)
        else:
            self.home()
