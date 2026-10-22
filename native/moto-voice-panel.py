# SPDX-License-Identifier: MIT
"""Touch dictation UI, layered on DevicePanel's existing keyboard and tasks."""
import importlib.util
from pathlib import Path
import threading
import time
import tkinter as tk

spec = importlib.util.spec_from_file_location('moto_voice', Path(__file__).with_name('moto-voice.py'))
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)
theme_spec = importlib.util.spec_from_file_location('moto_voice_theme', Path(__file__).with_name('moto-widgets.py'))
theme = importlib.util.module_from_spec(theme_spec)
theme_spec.loader.exec_module(theme)
BG, KEY, FG, MUTED, ACCENT = theme.BG, theme.KEY, theme.FG, theme.MUTED, theme.ACCENT


class VoicePanel:
    def __init__(self, panel):
        self.p = panel
        self.recorder = voice.Recorder()
        self.target = None
        self.transcript = ''
        self.busy = False
        self.stopping = False

    def leave(self):
        if self.p.page == 'voice-review' and isinstance(self.p.entry, tk.Text) and self.p.entry.winfo_exists():
            self.transcript = self.p.entry.get('1.0', 'end-1c')
        self.recorder.discard()

    def home(self):
        p = self.p
        p.begin('Voz e áudio', 'voice')
        available = bool(voice.capture_device())
        p.label('Ditado para seus terminais', 38, ACCENT)
        p.label('Fale no Moto, revise o texto e insira na aba do Codex ou em outro terminal.', 28, MUTED)
        if not available:
            p.label('Áudio interno ainda indisponível', 31, theme.ERROR)
            p.label('O driver não disponibilizou o microfone. Você já pode configurar e testar sua chave Groq.', 27, MUTED)
        configured = bool(voice.settings().get('api_key'))
        p.label('Groq: chave cadastrada' if configured else 'Groq: configure sua chave', 29)
        button = p.button('Gravar ditado · até 60 s', self.start, color=theme.SELECTED)
        if not available or not configured or self.busy:
            button.configure(state='disabled')
        if self.transcript:
            p.button('Último texto → aba atual', self.retarget)
        p.button('Configurar Groq / chave API', self.configure)
        p.button('Testar alto-falante', self.speaker)
        p.note = p.label('Os trechos de voz serão enviados à Groq somente quando você tocar em Transcrever. A API pode cobrar pelo uso.', 24, MUTED)

    def configure(self):
        p = self.p
        p.begin('Configurar ditado', 'voice-key', editing=True)
        configured = bool(voice.settings().get('api_key'))
        p.label('Chave já cadastrada. Preencha para substituir.' if configured else 'Use uma chave da sua conta Groq.', 26, MUTED)
        entry = p.field('Chave API Groq', secret=True)
        p.entry = entry
        p.note = p.label('A chave fica somente neste Moto, em arquivo privado. Não aparece no terminal.', 23, MUTED)
        row = p.row()
        save = p.button('Salvar chave', lambda: self.save(entry, save), parent=row, side='left', color=theme.SELECTED, size=27)
        p.button('Mostrar', lambda: entry.configure(show='' if entry.cget('show') else '●'), parent=row, side='right', size=26)
        p.submit = lambda: self.save(entry, save)
        row = p.row()
        test = p.button('Testar conexão', lambda: self.test(test), parent=row, side='left', size=26)
        if not configured:
            test.configure(state='disabled')
        if configured:
            p.button('Remover chave…', self.remove, size=25, color=theme.DANGER)

    def save(self, entry, button):
        try:
            voice.save_key(entry.get())
            entry.delete(0, 'end')
            self.configure()
            self.p.note.configure(text='Chave salva. Toque em Testar conexão para validar com a Groq.', fg=ACCENT)
        except (OSError, ValueError):
            self.p.note.configure(text='Não foi possível salvar. Confira a chave e o armazenamento.', fg=theme.ERROR)

    def test(self, button):
        if button.cget('state') == 'disabled':
            return
        button.configure(state='disabled')
        self.p.note.configure(text='Validando chave e modelo… nenhum áudio será enviado.', fg=MUTED)
        generation = self.p.generation
        def work():
            try:
                text, good = voice.test_key(), True
            except RuntimeError as exc:
                text, good = str(exc), False
            except OSError:
                text, good = 'Falha na validação. Confira a chave, conexão e permissão do modelo.', False
            def done():
                if generation == self.p.generation and self.p.s.menu:
                    button.configure(state='normal')
                    self.p.note.configure(text=text, fg=ACCENT if good else theme.ERROR)
            self.p.s.events.put(done)
        threading.Thread(target=work, daemon=True).start()

    def remove(self):
        p = self.p
        p.begin('Remover chave', 'voice-remove')
        p.label('Remove a chave deste aparelho. Não revoga a chave na sua conta Groq.', 30)
        p.button('Remover do Moto', lambda: (voice.remove_key(), self.home()), color=theme.DANGER)
        p.button('Cancelar', self.configure)

    def start(self):
        if self.busy or self.stopping:
            return
        p = self.p
        if hasattr(p.s, 'quick_voice') and p.s.quick_voice.active:
            p.s.message('Aguarde o microfone do teclado terminar de cancelar.')
            return
        try:
            target = voice.pane_target()
            p.begin('Gravar ditado', 'voice-record')
            self.target = target
            self.recorder.start()
        except (OSError, RuntimeError):
            self.home()
            p.note.configure(text='Não foi possível iniciar o microfone. Verifique o áudio do aparelho.', fg=theme.ERROR)
            return
        p.label('Destino: ' + target[1], 28, MUTED)
        self.timer = p.label('Gravando · 00:00 / 01:00', 40, ACCENT)
        self.meter = tk.Canvas(p.body, height=55, bg=KEY, highlightthickness=0)
        self.meter.pack(fill='x', pady=20)
        self.bar = self.meter.create_rectangle(0, 0, 0, 55, fill=ACCENT, outline='')
        p.label('Fale perto do microfone. Nada foi enviado ainda.', 28, MUTED)
        self.stop_button = p.button('Parar gravação', self.stop, color=theme.DANGER)
        p.button('Cancelar e apagar', self.home)
        p.note = p.label('Limite de 60 segundos. O microfone é desligado ao sair desta tela.', 24, MUTED)
        generation = p.generation
        def tick():
            if p.generation != generation or not p.s.menu:
                return
            elapsed = min(60, int(time.monotonic() - self.recorder.started))
            self.timer.configure(text='Gravando · %02d:%02d / 01:00' % divmod(elapsed, 60))
            self.meter.coords(self.bar, 0, 0, self.meter.winfo_width() * self.recorder.meter, 55)
            if not self.recorder.recording:
                self.stop()
                return
            p.s.root.after(150, tick)
        tick()

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        p = self.p
        self.stop_button.configure(state='disabled')
        p.note.configure(text='Finalizando e conferindo a gravação…', fg=MUTED)
        generation = p.generation
        def work():
            try:
                info, error = voice.inspect_wave(self.recorder.stop()), None
            except (RuntimeError, OSError) as exc:
                info, error = None, str(exc)
            def done():
                self.stopping = False
                if generation != p.generation or not p.s.menu:
                    return
                if error:
                    self.home()
                    p.note.configure(text=error, fg=theme.ERROR)
                else:
                    self.ready(info)
            p.s.events.put(done)
        threading.Thread(target=work, daemon=True).start()

    def ready(self, info):
        p = self.p
        # Keep the stopped recording while moving to the review/upload screen.
        p.begin('Gravação pronta', 'voice-ready', keep_voice=True)
        p.label('%.1f segundos de voz' % info['seconds'], 40, ACCENT)
        p.label('Destino: ' + self.target[1], 28, MUTED)
        p.label('Ao transcrever, este trecho será enviado à Groq usando sua chave API.', 30)
        send = p.button('Transcrever com Groq', lambda: self.send(send), color=theme.SELECTED)
        p.button('Gravar novamente', self.start)
        p.button('Descartar gravação', self.home)
        p.note = p.label('Você revisará o texto antes de inseri-lo. Nenhum Enter é enviado automaticamente.', 25, MUTED)

    def send(self, button):
        if self.busy or button.cget('state') == 'disabled':
            return
        self.busy = True
        button.configure(state='disabled')
        self.p.note.configure(text='Transcrevendo… aguarde. Sair descarta o resultado; o envio já iniciado pode concluir.', fg=MUTED)
        generation, path = self.p.generation, self.recorder.path
        def work():
            try:
                result, error = voice.transcribe(path), None
            except (OSError, RuntimeError) as exc:
                result, error = None, str(exc)
            def done():
                self.busy = False
                if self.p.generation != generation or not self.p.s.menu:
                    return
                if error:
                    button.configure(state='normal', text='Tentar transcrição novamente')
                    self.p.note.configure(text=error, fg=theme.ERROR)
                else:
                    self.transcript = result
                    self.review()
            self.p.s.events.put(done)
        threading.Thread(target=work, daemon=True).start()

    def review(self):
        p = self.p
        p.begin('Revisar ditado', 'voice-review', editing=True)
        p.label('Inserir em: ' + (self.target[1] if self.target else 'nenhuma aba'), 27, MUTED)
        text = tk.Text(p.body, font=('DejaVu Sans', -30), bg=KEY, fg=FG,
                       insertbackground=ACCENT, wrap='word', height=4, relief='flat', padx=14, pady=12)
        text.pack(fill='both', expand=True, pady=10)
        text.insert('1.0', self.transcript)
        p.register_input(text)
        p.entry = text
        p.submit = None
        p.note = p.label('Revise nomes e comandos. Enter só será enviado por você no terminal.', 23, MUTED)
        row = p.row()
        p.button('Inserir no terminal', lambda: self.insert(text.get('1.0', 'end-1c')),
                 parent=row, side='left', size=27, color=theme.SELECTED)
        p.button('Descartar', self.discard_text, parent=row, side='right', size=26)

    def retarget(self):
        try:
            self.target = voice.pane_target()
        except (OSError, RuntimeError):
            self.p.note.configure(text='Abra um terminal antes de inserir o texto.', fg=theme.ERROR)
            return
        self.review()

    def insert(self, text):
        self.transcript = text
        try:
            voice.insert_text(self.target[0] if self.target else '', text)
        except (ValueError, RuntimeError, OSError) as exc:
            self.p.note.configure(text=str(exc), fg=theme.ERROR)
            return
        self.p.s.close_menu()
        self.transcript = ''
        self.p.s.message('Ditado inserido · revise no terminal e pressione Enter quando quiser')

    def discard_text(self):
        self.home()
        self.transcript = ''

    def speaker(self):
        p = self.p
        p.begin('Testar alto-falante', 'voice-speaker')
        p.label('Um tom curto será reproduzido em volume baixo. Use os botões físicos para ajustar depois.', 30)
        p.note = p.label('A saída precisa estar inicializada pelo driver.', 26, MUTED)
        def play():
            spec = importlib.util.spec_from_file_location('moto_audio', Path(__file__).with_name('moto-audio.py'))
            audio = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(audio)
            return audio.test_speaker()
        p.button('Tocar som de teste', lambda: p.task(play, lambda msg: p.note.configure(text=msg)), color=theme.SELECTED)
