# SPDX-License-Identifier: MIT
"""Fullscreen voice pet; Rust owns hearing, protocol and vector poses."""
import importlib.util
from pathlib import Path
import tkinter as tk
import time


def sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


backend = sibling('moto-hermes')
pet = sibling('moto-hermes-pet')


class HermesPanel:
    def __init__(self, panel):
        self.p = panel
        self.worker = self.face_worker = self.listener = None
        self.epoch = self.voice_epoch = self.frame = 0
        self.state = 'disconnected'
        self.last_reply = self.last_user = self.notice = self.login_password = ''
        self.voice_warning = ''
        self.open_activation_pending = False
        self.transcription_mode = None
        self.turn_serial = 0
        self.pending_turn = None
        self.reply_poll_at = 0
        self.delivery_events = []
        self.screen_suspended = False
        self.pending = self.connected = self.transcribing = self.speech_active = False
        self.forgetting = self.switching = self.awake = self.face_pending = False
        self.timer = self.rearm_timer = self.scene = None

    def active(self):
        return self.p.s.menu is not None and self.p.page.startswith('hermes')

    def fullscreen(self):
        return self.active() and self.p.page == 'hermes' and not self.p.s.sleeping

    def home(self, activate_open=True):
        p = self.p
        if p.s.sleeping:
            return
        self.screen_suspended = False
        if self.scene:
            self.scene.dispose()
        p.begin('Hermes', 'hermes', immersive=True)
        self.scene = pet.PetScene(p, self.options, p.s.close_menu)
        self.scene.status(self.notice or 'Diga “Olá Hermes”', 'Converse por voz · segure a tela para opções')
        if self.face_worker is None:
            try:
                self.face_worker = backend.Worker(p.s.events.put, self.face_event, arguments=['--face-stdio'])
                self.face_worker.start()
            except OSError:
                self.face_worker = None
                self.set_status('Instale o componente Rust para animar o Hermes.', 'error')
        if not backend.CONFIG.exists():
            self.set_status('Primeiro, configure seu Hermes em ···', 'disconnected')
        elif self.worker is None and not self.forgetting:
            # Explicit app launch is an optional activation gesture. Old
            # configurations keep local wake; reconnect alone never opts in.
            self.open_activation_pending = activate_open and backend.settings()['start_on_open'] is True
            try:
                self.worker = backend.Worker(p.s.events.put, self.event)
                self.worker.start()
            except OSError:
                self.worker = None
                self.set_status('Componente Rust não instalado. Veja o guia.', 'error')
        elif self.connected:
            self.listen()
        self.schedule()

    def options(self):
        self.stop_local()
        p = self.p
        p.begin('Hermes', 'hermes-options')
        for label, action in [('Voltar ao bichinho', self.home), ('Nova conversa', self.new_session),
                ('Ver conversa / escrever', self.text), ('Conectar', self.connect),
                ('Configurar', self.configure), ('Voltar a dormir', self.sleep)]:
            p.button(label, action)
        if self.last_reply and not self.pending:
            p.button('Ouvir última resposta', self.speak_last)
        if self.pending:
            p.button('Conferir tarefa pendente', self.acknowledge)
            p.button('Cancelar tarefa', self.cancel)
        p.button('Fechar · voltar ao terminal', p.s.close_menu)

    def face_event(self, value):
        self.face_pending = False
        if value.get('event') == 'face' and self.fullscreen():
            self.scene.draw(value['pose'])

    def command(self, value):
        try:
            if self.worker is None:
                raise RuntimeError('Configure e instale o componente Rust primeiro.')
            self.worker.send(value)
            return True
        except RuntimeError as error:
            self.set_status(str(error), 'error')
            return False

    def pause_listening(self):
        self.voice_epoch += 1
        if self.rearm_timer is not None:
            self.p.s.root.after_cancel(self.rearm_timer)
            self.rearm_timer = None
        if self.listener:
            try: self.listener.send({'cmd':'pause', 'voice_epoch':self.voice_epoch})
            except RuntimeError: pass

    def listen(self):
        if not self.fullscreen() or not self.connected or self.pending or self.transcribing or self.speech_active or self.switching:
            return
        if self.listener is None:
            try:
                device = self.p.voice_backend.capture_device()
                if not device:
                    raise RuntimeError('Microfone indisponível: aguarde a inicialização do áudio.')
                self.awake = False
                self.listener = backend.Worker(self.p.s.events.put, self.voice_event, arguments=['--listen', '--device', device])
                self.listener.start()
            except (OSError, RuntimeError) as error:
                self.listener = None
                self.set_status(str(error), 'error')
                return
        self.voice_epoch += 1
        try:
            command = 'activate' if self.open_activation_pending else ('conversation' if self.awake else 'wake')
            self.listener.send({'cmd':command, 'voice_epoch':self.voice_epoch})
            self.open_activation_pending = False
        except RuntimeError:
            self.set_status('A escuta local encerrou. Reabra o app.', 'error')

    def resume_after_voice(self):
        self.pause_listening()
        epoch = self.epoch
        def resume():
            self.rearm_timer = None
            if epoch == self.epoch: self.listen()
        self.rearm_timer = self.p.s.root.after(400, resume)

    def say(self, text):
        if not self.fullscreen():
            return
        self.voice_warning = ''
        self.pause_listening()
        self.set_status(text if len(text) < 70 else 'Estou falando…', 'speaking')
        self.speech_active = self.command({'cmd':'speak', 'text':text})
        if not self.speech_active: self.resume_after_voice()

    def speak_last(self):
        if not self.connected or self.pending or self.speech_active or not self.last_reply:
            return
        text = self.last_reply
        self.speech_active = True  # home must not arm capture before playback
        self.home(activate_open=False)
        self.say(text)

    def voice_event(self, value):
        event = value.get('event')
        if event == 'listener_ready': return
        if event == 'exited':
            if self.listener:
                self.listener.close()
                self.listener = None
            if self.fullscreen(): self.set_status('Escuta local encerrada. Reabra o app.', 'error')
            return
        if not self.fullscreen() or value.get('voice_epoch') != self.voice_epoch: return
        if event == 'wake':
            self.awake = True
            self.say('Olá! Estou ouvindo.')
        elif event == 'utterance' and not (self.pending or self.speech_active or self.transcribing):
            mode = value.get('mode', 'conversation')
            if mode not in ('wake','conversation') or (mode == 'conversation') != self.awake:
                return
            self.voice_warning = ''
            self.pause_listening()
            self.transcribing = True
            self.transcription_mode = mode
            self.set_status('Diga “Olá Hermes”' if mode == 'wake' else 'Estou ouvindo sua mensagem…', 'standby' if mode == 'wake' else 'transcribing')
            if not self.command({'cmd':'transcribe', 'scope':mode, 'epoch':self.epoch, 'path':value['path']}): self.transcribing = False
        elif event == 'voice_listening':
            if self.voice_warning: self.set_status(self.voice_warning, 'error')
            else: self.set_status('Pode falar' if self.awake else 'Diga “Olá Hermes”', 'listening' if self.awake else 'standby')
        elif event == 'capture_health':
            try: backend.save_capture_diagnostic(value.get('metrics') or {})
            except (OSError, ValueError): pass
        elif event == 'speech_checked':
            try: backend.save_speech_decision(value.get('decision') or {})
            except (OSError, ValueError): pass
        elif event == 'voice_error': self.set_status(value.get('text', 'Microfone indisponível.'), 'error')

    def sleep(self):
        self.stop_local()
        self.open_activation_pending = False
        self.awake = False
        self.voice_warning = ''
        if not self.fullscreen(): self.home()
        else: self.listen()

    def new_session(self):
        if not self.connected or self.pending or self.transcribing or self.switching or self.speech_active:
            self.set_status('Aguarde ou confira a tarefa atual antes de trocar a conversa.', 'approval')
            return
        self.pause_listening()
        self.switching = self.command({'cmd':'new_session'})
        if self.switching: self.set_status('Abrindo nova conversa…', 'thinking')

    def set_status(self, text, state='ready'):
        self.notice, self.state = text, state
        if self.fullscreen() and self.scene:
            self.scene.status(text, 'Conversa ativa' if self.awake else 'Seu companheiro · segure a tela para opções')

    def event(self, value):
        if not self.active(): return
        event = value.get('event')
        if event == 'ready': self.connect()
        elif event == 'connected':
            self.login_password = ''
            self.connected, self.pending = True, bool(value.get('pending'))
            self.last_reply = value.get('text', '')
            self.set_status('Confira a tarefa anterior em ···' if self.pending else 'Diga “Olá Hermes”', 'approval' if self.pending else 'standby')
            if self.p.page == 'hermes-login': self.home()
            else: self.listen()
        elif event == 'new_session':
            self.last_user = self.last_reply = ''
            if not self.fullscreen(): self.home()
            self.switching = False
            if self.awake and self.fullscreen(): self.say('Nova conversa. Pode falar.')
            else: self.listen()
        elif event == 'reply':
            if (self.pending_turn is not None and value.get('client_turn') != self.pending_turn) or (self.pending_turn is None and value.get('client_turn') is not None):
                return
            self.delivery('reply_received')
            self.pending = False
            self.pending_turn = None
            self.last_reply = value.get('text', '')
            if self.fullscreen() and self.last_reply and not value.get('cancelled') and backend.settings()['auto_speak']:
                self.say(self.last_reply)
            else:
                self.set_status('Resposta recebida.', 'ready')
                self.resume_after_voice()
            if value.get('client_turn') is not None:
                self.command({'cmd':'ack_reply', 'client_turn':value['client_turn']})
            self.delivery('reply_applied')
        elif event == 'wake_transcript':
            if not (self.transcribing and self.transcription_mode == 'wake' and self.fullscreen() and value.get('epoch') == self.epoch):
                return
            self.transcribing = False
            self.transcription_mode = None
            try: backend.save_voice_diagnostic(value)
            except (OSError, ValueError): pass
            if value.get('accepted') is True:
                try: self.listener.send({'cmd':'accept_wake', 'voice_epoch':self.voice_epoch})
                except (RuntimeError, AttributeError): self.set_status('A escuta encerrou. Reabra o app.', 'error')
            else:
                self.set_status('Diga “Olá Hermes”', 'standby')
                self.listen()
        elif event == 'transcript':
            valid = self.transcribing and self.transcription_mode != 'wake' and self.fullscreen() and value.get('epoch') == self.epoch
            if not valid:
                return
            self.transcribing = False
            self.transcription_mode = None
            if valid:
                action = value.get('action')
                if action == 'new_session': self.new_session()
                elif action == 'close': self.p.s.close_menu()
                elif action == 'sleep': self.sleep()
                elif value.get('text', '').strip(): self.send_text(value['text'])
                else: self.resume_after_voice()
        elif event in ('spoken', 'speech_error'):
            self.speech_active = False
            self.voice_warning = value.get('text', 'Falha na voz. Veja a conversa em ···') if event == 'speech_error' else ''
            self.set_status(value.get('text', 'Pode falar'), 'ready' if event == 'spoken' else 'error')
            self.resume_after_voice()
            self.delivery(event)
        elif event == 'connection_lost':
            self.connected = False
            self.pause_listening()
            self.set_status(value.get('text', 'Conexão encerrada. Reconecte em ···.'), 'error')
            self.delivery('connection_lost')
        elif event == 'status': self.set_status(value.get('text', ''), value.get('state', 'thinking'))
        elif event == 'acknowledged':
            self.pending = False
            self.home()
        elif event == 'error':
            if value.get('operation') == 'transcribe' and value.get('epoch') != self.epoch:
                return
            self.pending = bool(value.get('pending', self.pending))
            if not self.pending: self.pending_turn = None
            self.transcribing = self.switching = False
            text = value.get('text', 'Não foi possível concluir.')
            diagnostic = value.get('rpc') or {}
            if (diagnostic.get('method') in ('session.create', 'session.resume')
                    and type(diagnostic.get('code')) is int):
                text += f" [{diagnostic['method']}, código {diagnostic['code']}]"
            self.set_status(text, 'error')
            if value.get('operation') == 'transcribe': self.voice_warning = text
            if value.get('login') or value.get('totp'):
                self.connected = False
                self.login(two_factor=bool(value.get('totp')))
            elif self.p.page == 'hermes-login':
                self.login_password = ''
                self.p.note.configure(text=self.notice)
            elif not self.pending and not self.speech_active: self.resume_after_voice()
            self.delivery('error')
        elif event == 'exited':
            self.speech_active = False
            if self.worker:
                self.worker.close()
                self.worker = None
            self.connected = False
            self.pause_listening()
            self.set_status('Conexão encerrada. Reabra o app.', 'error')

    def connect(self):
        self.set_status('Conectando ao seu Hermes…', 'connecting')
        self.command({'cmd':'connect'})

    def send_text(self, text):
        if not self.connected or self.pending or self.switching:
            self.set_status('Conecte e confira a tarefa anterior antes de enviar.', 'error')
            return
        self.pause_listening()
        self.last_user = text
        self.turn_serial += 1
        self.pending_turn = f'{self.epoch}:{self.turn_serial}'
        self.reply_poll_at = time.monotonic()+1
        if self.command({'cmd':'send', 'text':text, 'client_turn':self.pending_turn}):
            self.pending = True
            self.set_status('Hermes está pensando…', 'thinking')
            self.delivery('sent')
        else: self.pending_turn = None

    def delivery(self, stage):
        self.delivery_events = (self.delivery_events+[{'stage':stage,
            'milliseconds':round(time.monotonic()*1000), 'pending':self.pending,
            'speaking':self.speech_active, 'connected':self.connected,
            'reply_characters':len(self.last_reply)}])[-16:]
        try: backend.save_delivery_diagnostic(self.delivery_events)
        except (OSError, ValueError): pass

    def stop_local(self):
        self.epoch += 1
        if self.scene:
            self.scene.dispose()
        self.transcribing = False
        self.transcription_mode = None
        self.pause_listening()
        self.stop_speech()

    def leave(self, page):
        if not page.startswith('hermes'): self.close()
        elif page != 'hermes': self.stop_local()

    def suspend_screen(self):
        if not self.active():
            return
        # Blanking is not closing the conversation. Keep network delivery and
        # the paused listener's activation state; no microphone/player remains.
        self.screen_suspended = True
        self.login_password = ''
        self.open_activation_pending = False
        self.stop_local()
        if self.timer is not None:
            self.p.s.root.after_cancel(self.timer)
            self.timer = None
        if self.face_worker:
            self.face_worker.close()
            self.face_worker = None
        self.face_pending = False

    def resume_screen(self):
        if self.screen_suspended and self.active():
            if self.p.page == 'hermes' or (self.p.page == 'hermes-login' and self.connected):
                self.home(activate_open=False)
            else:
                self.screen_suspended = False

    def close(self, after_stop=None):
        self.stop_local()
        self.screen_suspended = False
        self.open_activation_pending = False
        self.login_password = ''
        self.voice_warning = ''
        self.connected = self.speech_active = self.switching = self.awake = False
        if self.timer is not None:
            self.p.s.root.after_cancel(self.timer)
            self.timer = None
        for name in ('face_worker', 'listener'):
            worker = getattr(self, name)
            if worker:
                worker.close()
                setattr(self, name, None)
        if self.worker:
            self.worker.close(after_stop=after_stop)
            self.worker = None
        elif after_stop: after_stop()
        self.face_pending = False
        self.scene = None

    def schedule(self):
        if self.timer is not None: self.p.s.root.after_cancel(self.timer)
        self.timer = self.p.s.root.after(50, self.tick)

    def tick(self):
        self.timer = None
        if not self.active() or self.p.s.sleeping: return
        if self.pending and self.pending_turn is not None and time.monotonic() >= self.reply_poll_at:
            self.reply_poll_at = time.monotonic()+2
            self.command({'cmd':'poll_reply', 'client_turn':self.pending_turn})
        if self.fullscreen() and self.face_worker and not self.face_pending:
            try:
                self.face_worker.send({'cmd':'face', 'state':self.state, 'tick':self.frame})
                self.face_pending = True
                self.frame += 1
            except RuntimeError: self.face_pending = False
        self.timer = self.p.s.root.after(50, self.tick)

    def login(self, two_factor=False):
        p = self.p
        self.stop_local()
        p.begin('Entrar no Umbrel', 'hermes-login', editing=True)
        p.label(backend.settings()['server_url'], p.u(15), p.theme.MUTED)
        p.label('Use a senha da sua conta Umbrel neste aparelho. Ela não será salva.', p.u(16))
        password = p.field('Senha Umbrel', secret=True)
        totp = p.field('Código de autenticação 2FA', secret=True) if two_factor else None
        p.note = p.label(self.notice, p.u(15), p.theme.MUTED)
        def submit():
            value = password.get() or self.login_password
            code = totp.get() if totp is not None else ''
            password.delete(0, 'end')
            if totp is not None:
                totp.delete(0, 'end')
            self.login_password = value
            if self.command({'cmd':'login', 'password':value, 'totp':code}):
                p.note.configure(text='Validando a sessão Umbrel…')
        p.submit = submit
        p.footer_action('Entrar', submit)
        p.entry = totp if two_factor else password

    def configure(self):
        p = self.p
        self.stop_local()
        self.login_password = ''
        value = backend.settings()
        p.begin('Configurar Hermes', 'hermes-config', editing=True)
        p.label('Conecte seu próprio agente. Nenhuma chave ou conta de outra instalação é copiada.', p.u(16), p.theme.MUTED)
        server = p.field('URL do Hermes (HTTPS ou IP Tailscale)', value['server_url'])
        p.label('Via Tailscale: http://IP:porta, sem /chat. A conexão privada é verificada pelo app.', p.u(14), p.theme.MUTED)
        auth_origin = p.field('Origem do login Umbrel (opcional)', value['auth_origin'] or '')
        account = p.field('ID da conta Umbrel (0: proprietário)', value['user_id'])
        profile = p.field('Perfil Hermes (vazio: padrão)', value['profile'])
        ca = p.field('Arquivo CA PEM (opcional)', value['ca_file'] or '')
        speak = tk.BooleanVar(value=value['auto_speak'])
        remember = tk.BooleanVar(value=value['remember_session'])
        start = tk.BooleanVar(value=value['start_on_open'])
        for caption, variable in [('Ler respostas em voz alta', speak), ('Lembrar sessão neste aparelho', remember),
                ('Começar a conversa ao abrir', start)]:
            tk.Checkbutton(p.body, text=caption, variable=variable, bg=p.theme.BG,
                           fg=p.theme.FG, selectcolor=p.theme.KEY, activebackground=p.theme.BG,
                           font=('DejaVu Sans', -p.u(16))).pack(fill='x', pady=p.u(5))
        p.label('A sessão lembrada é privada, mas não criptografada. A chave Groq é configurada em Voz e áudio.', p.u(14), p.theme.MUTED)
        p.label('Com o app aberto, os trechos com fala vão à Groq para reconhecer “Olá Hermes” e os pedidos. O silêncio é filtrado no aparelho.', p.u(14), p.theme.MUTED)
        p.note = p.label('', p.u(15), p.theme.MUTED)
        def save():
            try:
                backend.save_config({'server_url':server.get().strip(), 'user_id':account.get().strip(),
                    'auth_origin':auth_origin.get().strip() or None,
                    'profile':profile.get().strip(), 'ca_file':ca.get().strip() or None,
                    'auto_speak':speak.get(), 'remember_session':remember.get(), 'start_on_open':start.get()})
            except (OSError, ValueError) as error:
                p.note.configure(text=str(error)); return
            self.close()
            self.home()
        p.submit = save
        p.footer_action('Salvar', save)
        p.button('Esquecer sessão salva', self.forget)
        p.entry = server

    def text(self):
        p = self.p
        self.stop_local()
        p.begin('Conversa Hermes', 'hermes-text', editing=True)
        if self.last_user:
            p.label('Você: '+self.last_user[-2000:], p.u(16), p.theme.MUTED)
        p.label(self.last_reply[-5000:] or 'Nenhuma resposta nesta abertura do app.', p.u(16))
        editor = tk.Text(p.body, height=5, bg=p.theme.KEY, fg=p.theme.FG,
                         font=('DejaVu Sans', -p.u(17)), wrap='word', relief='flat')
        editor.pack(fill='x', pady=p.u(8))
        p.register_input(editor)
        p.entry = editor
        p.note = p.label('', p.u(15), p.theme.MUTED)
        def submit():
            value = editor.get('1.0', 'end-1c')
            self.home()
            self.send_text(value)
        p.submit = submit
        p.footer_action('Enviar', submit)

    def stop_speech(self):
        if self.worker:
            self.command({'cmd':'stop_speech'})

    def cancel(self):
        self.stop_local()
        if not self.pending:
            self.set_status('Áudio local interrompido. Nenhuma tarefa ativa neste app.', 'ready')
            return
        if self.command({'cmd':'cancel'}):
            self.set_status('Parada solicitada; os efeitos já executados não são desfeitos.', 'thinking')

    def acknowledge(self):
        p = self.p
        p.begin('Conferir tarefa anterior', 'hermes-acknowledge')
        p.label('Confira o resultado no Hermes. Liberar o app não repete nem desfaz a tarefa anterior.', p.u(19))
        p.button('Já conferi · liberar próximo envio', lambda: self.command({'cmd':'acknowledge_unknown'}))

    def forget(self):
        self.forgetting = True
        self.p.begin('Esquecer sessão', 'hermes-forget')
        self.p.label('Encerrando a sessão antes de apagar o acesso salvo…', self.p.u(17))
        cookie = backend.CONFIG.parent/'hermes-auth.json'
        def after_stop():
            try:
                cookie.unlink(missing_ok=True)
                error = None
            except OSError:
                error = 'Não foi possível remover a sessão salva.'
            def done():
                self.forgetting = False
                if self.active():
                    self.configure()
                    if error:
                        self.p.note.configure(text=error)
            self.p.s.events.put(done)
        self.close(after_stop=after_stop)
