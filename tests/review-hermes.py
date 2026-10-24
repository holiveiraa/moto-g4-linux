#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated Tk/XTest/tmux review with the real Rust face and synthetic account/events.

Run in an isolated Linux display/container only. No actual server or Groq call.
MOTO_HERMES_BINARY points to the locally built host binary.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not os.environ.get('DISPLAY') or not os.environ.get('MOTO_HERMES_BINARY'):
        raise SystemExit('Use a private Xvfb display and set MOTO_HERMES_BINARY.')
    spec = importlib.util.spec_from_file_location('hermes_ui_review', ROOT/'native/moto-shell.py')
    ui = importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)
    backend = ui.panel_module.hermes_module.backend
    real_run = subprocess.run
    shell = terminal = None
    server = 'moto-hermes-review-'+str(os.getpid())
    def tmux(*args):
        return real_run(['tmux','-L',server,*args],capture_output=True,text=True,timeout=3)
    def remap(args, *more, **kwargs):
        args = list(args)
        if args[:3] == ['tmux','-L','moto']: args[2] = server
        return real_run(args,*more,**kwargs)
    with tempfile.TemporaryDirectory(prefix=server) as directory:
        private=Path(directory)
        os.environ['MOTO_UX_CONFIG']=str(private/'ux.json')
        sink=private/'received'
        receiver=private/'receiver.sh'
        receiver.write_text('#!/bin/sh\nstty -echo -icanon\ncat > '+str(sink)+'\n'); receiver.chmod(0o700)
        assert tmux('-f','/dev/null','new-session','-d','-s','moto',str(receiver)).returncode == 0
        backend.CONFIG=private/'config/hermes.json'
        backend.CAPTURE_DIAGNOSTIC=private/'runtime/capture.json'
        backend.BINARY=os.environ['MOTO_HERMES_BINARY']
        backend.save_config(dict(backend.DEFAULTS,server_url='http://127.0.0.1:9/',auto_speak=False))
        original_worker=backend.Worker
        class FixtureWorker(original_worker):
            def send(self, value):
                command=value['cmd']
                if self.arguments[0] == '--listen':
                    if command == 'accept_wake': self.deliver({'event':'wake','voice_epoch':value['voice_epoch'],'source':'groq'})
                    return
                if command in ('connect','login'):
                    self.deliver({'event':'connected','text':'Olá! Como posso ajudar?','pending':False})
                elif command == 'send':
                    self.deliver({'event':'reply','client_turn':value.get('client_turn'),'text':'Resposta simulada: '+value['text']})
                elif command == 'speak':
                    self.deliver({'event':'spoken'})
                elif command == 'transcribe':
                    if value.get('scope') == 'wake': self.deliver({'event':'wake_transcript','epoch':value['epoch'],'accepted':True,'recognizer':'groq','characters':10})
                    else: self.deliver({'event':'transcript','epoch':value['epoch'],'text':'Pergunta por voz'})
                elif command == 'new_session':
                    self.deliver({'event':'new_session'})
                elif command in ('stop_speech','cancel','ack_reply','poll_reply'):
                    return
                else: super().send(value)
        backend.Worker=FixtureWorker
        ui.SOCKET=str(private/'control.sock')
        light=private/'brightness'; light.write_text('100'); ui.LIGHT=light
        ui.Shell.write_geometry=lambda self: None
        ui.Shell.vpn_worker=lambda self: None
        ui.Shell.tmux=lambda self,*args: tmux(*args)
        terminal=subprocess.Popen(['xterm','-class','XTerm','-e','tmux','-L',server,'attach','-t','moto'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            time.sleep(.3)
            subprocess.run=remap
            shell=ui.Shell(); p=shell.panel; app=p.hermes
            errors=[]
            shell.root.report_callback_exception=lambda kind,error,trace: errors.append(error)
            p.host_store=ui.panel_module.hosts.HostStore(private/'hosts.json')
            p.voice_backend.capture_device=lambda: 'hw:0,0'
            p.voice_backend.CONFIG=private/'config/groq.json'
            p.voice_backend.capture.LOCK=private/'capture.lock'
            shell.device={'battery':'78','charging':'Discharging','wifi':{'ssid':'Rede de teste'},'vpn':{'title':'Conectada'},'ssh_auth':{}}
            def pump(seconds=.3):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    shell.root.update()
                    if errors: raise errors.pop(0)
                    time.sleep(.005)
            def capture(name):
                pump()
                output=Path(os.environ.get('MOTO_HERMES_REVIEW_OUTPUT', str(private)))
                output.mkdir(parents=True,exist_ok=True)
                real_run(['xwd','-root','-silent','-out',str(output/(name+'.xwd'))],check=True)
            before=tmux('list-windows','-F','#{window_id}').stdout
            app.home(); pump(1)
            assert app.connected and app.scene and app.frame > 1
            assert not shell.keyboard.winfo_ismapped() and not shell.header.winfo_ismapped()
            assert shell.menu.winfo_width()==shell.w and shell.menu.winfo_height()==shell.h
            assert app.scene.canvas.winfo_height()==shell.h
            before_pose=app.scene.canvas.coords(app.scene.eyes[0])
            pump(.5)
            assert app.scene.canvas.coords(app.scene.eyes[0]) != before_pose
            capture('hermes-ready')
            app.voice_event({'event':'utterance','mode':'wake','voice_epoch':app.voice_epoch,'path':'/fixture/wake.wav'}); pump(.6)
            assert app.awake and not app.speech_active
            app.voice_event({'event':'utterance','voice_epoch':app.voice_epoch,'path':'/fixture/postwake.wav'}); pump(.6)
            assert app.last_reply=='Resposta simulada: Pergunta por voz' and not app.pending
            app.transcribing=True
            app.event({'event':'transcript','epoch':app.epoch,'action':'new_session','text':'Nova conversa'}); pump(.6)
            assert app.last_reply==app.last_user=='' and not app.switching and app.awake
            app.set_status('Pode falar', 'listening'); capture('hermes-listening')
            assert not (sink.read_bytes() if sink.exists() else b'')
            app.text(); pump()
            editor=p.entry
            assert isinstance(editor,tk.Text) and editor.focus_get() is editor
            shell.emit('ã'); shell.emit('ç'); pump()
            assert editor.get('1.0','end-1c')=='ãç'
            assert not (sink.read_bytes() if sink.exists() else b'')
            p.submit(); pump()
            assert app.last_reply=='Resposta simulada: ãç'
            capture('hermes-reply')
            app.login(); pump()
            assert len(p.inputs)==1 and p.inputs[0].cget('show')
            capture('hermes-password')
            app.login_password='fixture-password'; app.login(two_factor=True); pump()
            assert len(p.inputs)==2 and p.entry is p.inputs[1]
            assert p.entry.focus_get() is p.entry and all(field.cget('show') for field in p.inputs)
            capture('hermes-two-factor')
            cookie=backend.CONFIG.parent/'hermes-auth.json'
            cookie.write_text('fixture-cookie')
            app.forget(); pump(.6)
            assert not cookie.exists() and not app.forgetting and p.page=='hermes-config'
            app.home(); pump(.5)
            network, listener = app.worker, app.listener
            app.pending = True
            shell.action('screen-toggle'); pump()
            assert shell.sleeping and app.worker is network and app.listener is listener and app.face_worker is None
            app.event({'event':'reply','text':'Completed while the display was blank.'}); pump()
            assert not app.pending and app.last_reply=='Completed while the display was blank.' and not app.speech_active
            shell.wake(); pump()
            assert app.worker is network and app.face_worker is not None and not app.screen_suspended
            assert app.notice != 'Hermes está pensando…'
            app.pending = app.awake = True
            app.set_status('Hermes está pensando…', 'thinking')
            shell.action('screen-toggle'); pump()
            shell.wake(); pump()
            assert app.pending and app.worker is network
            completed = 'A long synthetic answer after a tool completed. '*120
            started = time.monotonic()
            app.event({'event':'reply','text':completed}); pump(.6)
            assert not app.pending and app.last_reply==completed and time.monotonic()-started<2
            shell.close_menu(); pump()
            assert tmux('list-windows','-F','#{window_id}').stdout==before
            assert not (sink.read_bytes() if sink.exists() else b'')
            print('PASS: fullscreen animated Rust vector face, hidden keyboard, native Text/caret, password-only + optional 2FA forms, blank/close worker cleanup, preserved tmux and no PTY input leak')
        finally:
            subprocess.run=real_run
            if shell:
                shell.panel.hermes.close(); shell.quick_voice.close()
                shell.root.destroy()
            if terminal:
                terminal.terminate()
                try: terminal.wait(timeout=3)
                except subprocess.TimeoutExpired: terminal.kill(); terminal.wait(timeout=3)
            tmux('kill-server')


if __name__=='__main__': main()
