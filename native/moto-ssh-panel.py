# SPDX-License-Identifier: MIT
"""Saved SSH destinations, independent of the Wi-Fi and VPN settings pages."""
import tkinter as tk


class SSHPanel:
    def __init__(self, panel):
        self.p, self.ident = panel, None

    def home(self):
        p = self.p
        p.begin('SSH', 'ssh')
        p.label('Seus servidores, prontos para abrir em uma aba.', color=p.theme.MUTED)
        p.note = p.label('', color=p.theme.MUTED)
        try:
            rows = p.host_store.list()
        except RuntimeError as exc:
            p.note.configure(text=str(exc), fg=p.theme.ERROR)
            return
        p.button('+ Nova conexão', self.form, color=p.theme.ACCENT)
        if not rows:
            p.label('Adicione um destino com endereço e usuário. Não é necessário preencher tudo novamente a cada acesso.')
        for profile in rows:
            mode = 'Tailscale SSH' if profile['mode'] == 'tailscale' else 'SSH'
            p.button(profile['name']+'\n'+profile['user']+'@'+profile['host']+' · '+mode+'  ›',
                     lambda ident=profile['id']: self.details(ident), color=p.theme.PANEL)

    def details(self, ident):
        p = self.p
        try:
            profile = p.host_store.find(ident)
        except RuntimeError as exc:
            self.home(); p.note.configure(text=str(exc), fg=p.theme.ERROR)
            return
        self.ident = ident
        p.begin(profile['name'], 'ssh-details')
        p.label(profile['user']+'@'+profile['host'], size=p.u(20), color=p.theme.ACCENT)
        p.label('Porta '+str(profile['port'])+' · '+('Tailscale SSH' if profile['mode'] == 'tailscale' else 'SSH'), color=p.theme.MUTED)
        p.button('Abrir em nova aba', lambda: p.s.new_terminal(ssh=True, profile=ident), color=p.theme.ACCENT)
        if profile['mode'] == 'ssh':
            p.button('Abrir com entrada manual', lambda: p.s.new_terminal(ssh=True, profile=ident, manual=True))
        p.button('Editar conexão', lambda: self.form(ident))
        if p.host_store.secret_path(ident).exists():
            p.label('Senha salva neste aparelho.', color=p.theme.MUTED)
            p.button('Remover senha salva…', lambda: self.confirm_password_remove(ident))
        p.button('Remover favorito…', lambda: self.confirm_remove(ident))
        p.note = p.label('Senha é opcional. Sem senha salva, o cliente usa sua autenticação habitual e pode pedir a senha no terminal.', color=p.theme.MUTED)

    def form(self, ident=None):
        p = self.p
        self.ident = ident
        try:
            profile = p.host_store.find(ident) if ident else {'name': '', 'host': '', 'user': '', 'port': 22, 'mode': 'ssh'}
        except RuntimeError as exc:
            self.home(); p.note.configure(text=str(exc), fg=p.theme.ERROR)
            return
        p.begin('Editar conexão' if ident else 'Nova conexão SSH', 'ssh-edit', editing=True)
        entries = {key: p.field(label, str(profile[key])) for key, label in
                   [('name', 'Nome'), ('host', 'Endereço / host'), ('user', 'Usuário'), ('port', 'Porta')]}
        password = p.field('Senha SSH (opcional)', secret=True)
        has_password = bool(ident and p.host_store.secret_path(ident).exists())
        p.label('Senha salva: em branco mantém. Preencher substitui. Alterar endereço, usuário, porta ou modo exige informar novamente.' if has_password else
                'Pode deixar vazio. Se preencher, a senha será salva somente neste aparelho.', color=p.theme.MUTED)
        mode = {'value': profile['mode'], 'port': str(profile['port'])}
        row = p.row()
        buttons = {}
        def choose(value):
            if value == 'tailscale' and mode['value'] != 'tailscale':
                mode['port'] = entries['port'].get()
            entries['port'].configure(state='normal')
            if value != mode['value']:
                entries['port'].delete(0, 'end')
                entries['port'].insert(0, '22' if value == 'tailscale' else mode['port'])
            mode['value'] = value
            entries['port'].configure(state='disabled' if value == 'tailscale' else 'normal', disabledbackground=p.theme.KEY, disabledforeground=p.theme.MUTED)
            password.configure(state='disabled' if value == 'tailscale' else 'normal', disabledbackground=p.theme.KEY, disabledforeground=p.theme.MUTED)
            for key, button in buttons.items():
                button.configure(bg=p.theme.ACCENT if key == value else p.theme.KEY,
                                 fg=p.theme.BG if key == value else p.theme.FG,
                                 activeforeground=p.theme.BG if key == value else p.theme.FG)
            if p.entry is entries['port'] and value == 'tailscale':
                p.entry = entries['host']
            if p.entry is password and value == 'tailscale':
                p.entry = entries['host']
        buttons['ssh'] = p.button('SSH', lambda: choose('ssh'), parent=row, side='left')
        buttons['tailscale'] = p.button('Tailscale SSH', lambda: choose('tailscale'), parent=row, side='left')
        choose(mode['value'])
        p.entry = entries['name']
        p.note = p.label('SSH também pode passar pela VPN e pedir senha. Tailscale SSH usa a autorização da sua rede, sem senha salva.', color=p.theme.MUTED)
        def save():
            try:
                saved = p.host_store.save(dict({key: entry.get() for key, entry in entries.items()}, mode=mode['value']), ident,
                                          password=(password.get() or None) if mode['value'] == 'ssh' else '')
            except (ValueError, RuntimeError, OSError) as exc:
                p.note.configure(text=str(exc), fg=p.theme.ERROR)
                return
            self.details(saved['id'])
        p.submit = save
        p.footer_action('Salvar', save)

    def confirm_password_remove(self, ident):
        p = self.p
        self.ident = ident
        p.begin('Remover senha salva', 'ssh-password-remove')
        p.label('O favorito e as abas continuam disponíveis. No próximo acesso, você poderá digitar a senha no terminal.')
        def remove():
            try:
                p.host_store.remove_password(ident)
            except (RuntimeError, OSError) as exc:
                p.note.configure(text=str(exc), fg=p.theme.ERROR)
                return
            self.details(ident)
        p.button('Remover somente a senha', remove, color='#593040')
        p.note = p.label('', color=p.theme.MUTED)

    def confirm_remove(self, ident):
        p = self.p
        try:
            profile = p.host_store.find(ident)
        except RuntimeError:
            self.home(); return
        self.ident = ident
        p.begin('Remover favorito', 'ssh-remove')
        p.label(profile['name'], size=p.u(22))
        p.label('Remove o destino desta lista. As abas abertas continuam funcionando e nenhum servidor será alterado.')
        def remove():
            try:
                p.host_store.remove(ident)
            except (RuntimeError, OSError) as exc:
                p.note.configure(text=str(exc), fg=p.theme.ERROR)
                return
            self.home()
        p.button('Remover favorito', remove, color='#593040')
        p.note = p.label('Você pode adicionar o destino novamente depois.', color=p.theme.MUTED)

    def back(self):
        if self.p.page in ('ssh-edit', 'ssh-remove', 'ssh-password-remove') and self.ident:
            self.details(self.ident)
        else:
            self.home()
