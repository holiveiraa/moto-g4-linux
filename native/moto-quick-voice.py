# SPDX-License-Identifier: MIT
"""Keyboard dictation: explicit record/stop, async Groq, literal paste, no Enter."""
import threading
import time
from subprocess import TimeoutExpired


class QuickDictation:
    def __init__(self, shell, backend):
        self.s, self.v = shell, backend
        self.state = 'idle'
        self.generation = 0
        self.recorder = None
        self.target = None
        self.context = None
        self.result = ''
        self.last_tick = 0

    @property
    def active(self):
        return self.state in ('recording', 'sending', 'retry', 'canceling')

    def hint(self):
        if self.state == 'recording':
            elapsed = min(60, int(time.monotonic() - self.recorder.started))
            return 'Gravando %02d:%02d · toque no mic para inserir · × cancela' % divmod(elapsed, 60)
        return {'sending': 'Transcrevendo com Groq… · × cancela',
                'retry': 'Falhou · mic tenta novamente · × descarta',
                'result': 'Texto guardado · toque no mic para revisar o destino',
                'canceling': 'Cancelando gravação…'}.get(self.state, '')

    def pane_context(self):
        result = self.s.tmux('display-message', '-p', '-t', 'moto',
                             '#{pane_id}|#{pane_pid}|#{pane_current_command}|#{alternate_on}|#{pane_in_mode}')
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('Terminal indisponível.')
        return result.stdout.strip()

    def refresh(self, message=None):
        self.s.draw()
        if message:
            self.s.message(message)

    def toggle(self):
        if self.state == 'recording':
            self.send()
            return
        if self.state == 'result':
            panel = self.s.panel.voice
            panel.target, panel.transcript = self.target, self.result
            self.state, self.result = 'idle', ''
            panel.review()
            return
        if self.state in ('sending', 'canceling'):
            return
        if self.s.menu:
            self.s.message('Volte ao terminal para usar o microfone do teclado.')
            return
        if self.state == 'retry':
            self.send()
            return
        panel = self.s.panel.voice
        if panel.busy or panel.stopping or panel.recorder.recording:
            self.s.message('Finalize o outro ditado primeiro.')
            return
        recorder = None
        try:
            if not self.v.settings().get('api_key'):
                raise RuntimeError('Configure sua chave em Painel → Voz e áudio → Groq.')
            self.target, self.context = self.v.pane_target(), self.pane_context()
            if self.context.split('|', 1)[0] != self.target[0]:
                raise RuntimeError('A aba mudou. Toque no mic novamente.')
            recorder = self.v.Recorder()
            recorder.start()
        except (OSError, RuntimeError, TimeoutExpired) as error:
            if recorder:
                recorder.discard()
            self.s.message(str(error))
            return
        self.generation += 1
        self.recorder, self.state = recorder, 'recording'
        self.s.mods.clear()
        self.refresh('Gravando · segundo toque transcreve e insere sem Enter · limite 60 s')

    def tick(self):
        if self.state != 'recording':
            return
        if not self.recorder.recording or time.monotonic() - self.recorder.started >= 60:
            self.send()
            return
        now = time.monotonic()
        if now - self.last_tick >= .25:
            self.last_tick = now
            self.s.canvas.itemconfigure(self.s.keyboard_hint, text=self.hint())

    def send(self):
        if self.state not in ('recording', 'retry'):
            return
        recorder, token = self.recorder, self.generation
        self.state = 'sending'
        self.refresh()

        def work():
            text, error, valid_audio = None, None, False
            try:
                path = recorder.stop()
                self.v.inspect_wave(path)
                valid_audio = True
                text = self.v.transcribe(path)
            except (OSError, RuntimeError, TimeoutExpired) as exc:
                error = str(exc)
            if text is not None or not valid_audio:
                recorder.discard()
            self.s.events.put(lambda: self.finish(token, recorder, text, error, valid_audio))
        threading.Thread(target=work, daemon=True).start()

    def finish(self, token, recorder, text, error, valid_audio):
        if token != self.generation:
            recorder.discard()
            return
        if error:
            self.state = 'retry' if valid_audio else 'idle'
            self.recorder = recorder if valid_audio else None
            self.refresh(error)
            return
        self.recorder = None
        self.result = text
        # Check again immediately before paste. An SSH pane cannot expose the
        # remote foreground process reliably, so the text is always sanitized
        # by the backend and no Return/CR/LF/ESC is ever synthesized here.
        try:
            if self.s.menu or self.s.sleeping or self.pane_context() != self.context:
                raise RuntimeError('O destino mudou; toque no mic para revisar o texto.')
            self.v.insert_text(self.target[0], text)
        except (OSError, RuntimeError, ValueError, TimeoutExpired) as exc:
            self.state = 'result'
            self.refresh(str(exc))
            return
        self.state, self.result = 'idle', ''
        self.refresh('Ditado inserido · Enter continua por sua conta')

    def cancel(self):
        if self.state == 'canceling':
            return
        self.generation += 1
        token, recorder = self.generation, self.recorder
        self.recorder, self.result = None, ''
        self.state = 'canceling' if recorder else 'idle'
        self.refresh('Ditado cancelado')
        if not recorder:
            return

        def work():
            recorder.discard()
            def done():
                if token == self.generation:
                    self.state = 'idle'
                    self.refresh()
            self.s.events.put(done)
        threading.Thread(target=work, daemon=True).start()

    def close(self):
        self.generation += 1
        if self.recorder:
            self.recorder.discard()
        self.recorder = None
