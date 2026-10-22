# SPDX-License-Identifier: MIT
"""Built-in theme preview and save on the existing device panel."""
class AppearancePanel:
    def __init__(self, panel):
        self.p = panel
        self.preview_base = None

    def leave(self, next_page):
        if next_page != 'appearance' and self.preview_base is not None:
            self.p.s.apply_theme(self.preview_base)
            self.preview_base = None

    def show(self):
        p, t = self.p, self.p.theme
        if self.preview_base is None:
            self.preview_base = p.s.theme_name
        p.begin('Aparência', 'appearance')
        p.label('Toque para experimentar. Salvar mantém a escolha; Voltar cancela a prévia.', color=t.MUTED)
        for name, theme in t.experience.THEMES.items():
            selected = name == p.s.theme_name
            p.button(('●  ' if selected else '')+theme['name']+'\n'+theme['detail'],
                     lambda key=name: self.preview(key), color=t.SELECTED if selected else t.PANEL)
        p.note = p.label('', color=t.MUTED)
        p.footer_action('Salvar tema', self.commit_theme)

    def preview(self, name):
        self.p.s.apply_theme(name)
        self.show()

    def commit_theme(self):
        p = self.p
        try:
            p.theme.experience.save_preferences({'theme': p.s.theme_name})
        except OSError:
            p.note.configure(text='Não foi possível salvar. A prévia continua disponível.', fg=p.theme.ERROR)
            return
        self.preview_base = None
        p.home()
        p.s.message('Tema salvo')
