#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline companion lifecycle and shared microphone ownership regressions."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'native'/(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class CaptureOwnership(unittest.TestCase):
    def test_capture_is_exclusive_across_processes_and_released(self):
        capture = module('moto-capture')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'capture.lock'
            first = capture.CaptureLease(path)
            first.acquire()
            code = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
            held = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
            self.assertNotEqual(held.returncode, 0)
            first.release()
            released = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
            self.assertEqual(released.returncode, 0)

    def test_symbolic_link_and_nonprivate_lock_are_rejected(self):
        capture = module('moto-capture')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'lock'; target = Path(folder)/'target'
            target.write_text('fixture')
            path.symlink_to(target)
            with self.assertRaises(RuntimeError): capture.CaptureLease(path).acquire()
            self.assertEqual(target.read_text(), 'fixture')

    def test_capture_child_keeps_lease_after_parent_releases_its_copy(self):
        capture = module('moto-capture')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'lock'
            lease = capture.CaptureLease(path); lease.acquire()
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], pass_fds=(lease.fileno(),))
            try:
                lease.release()
                other = capture.CaptureLease(path)
                with self.assertRaises(RuntimeError): other.acquire()
            finally:
                child.terminate(); child.wait(timeout=3)
            other.acquire(); other.release()


class CompanionFiles(unittest.TestCase):
    def test_capture_health_saves_counters_only_and_discards_stale_epochs(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder, patch.object(self.h.backend, 'CAPTURE_DIAGNOSTIC', Path(folder)/'runtime/capture.json'):
            metrics = {'frames':250,'raw_voice_frames':63,'gated_voice_frames':0,
                       'max_rms':24,'min_voice_rms':64,'text':'private noise words','audio':'private audio'}
            app.voice_event({'event':'capture_health','voice_epoch':app.voice_epoch,'metrics':metrics})
            path = Path(folder)/'runtime/capture.json'
            self.assertEqual(json.loads(path.read_text()), {k:v for k,v in metrics.items() if k not in ('text','audio')})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            app.voice_event({'event':'capture_health','voice_epoch':app.voice_epoch+1,'metrics':{'frames':500}})
            self.assertEqual(json.loads(path.read_text())['frames'],250)
            app.worker.send.assert_not_called()
            app.voice_event({'event':'speech_checked','voice_epoch':app.voice_epoch,'decision':{
                'accepted':False,'speech_ms':0,'max_run_ms':0,'milliseconds':8,'text':'private words'}})
            self.assertEqual(json.loads(path.with_name('speech.json').read_text()),
                             {'accepted':False,'speech_ms':0,'max_run_ms':0,'milliseconds':8})
            app.worker.send.assert_not_called()

    def test_replaying_a_known_answer_never_submits_another_agent_turn(self):
        from unittest.mock import Mock
        app = self.app()
        app.home = Mock()
        app.last_reply = 'Known completed answer'
        app.pending = True
        app.speak_last()
        app.worker.send.assert_not_called()
        app.pending = False
        app.speak_last()
        self.assertEqual(app.worker.send.call_args.args[0], {'cmd':'speak','text':'Known completed answer'})
        self.assertFalse(any(call.args[0]['cmd']=='send' for call in app.worker.send.call_args_list))

    def test_screen_off_keeps_task_delivery_but_stops_audio_and_face(self):
        from unittest.mock import Mock
        app = self.app()
        app.pending = app.awake = True
        app.face_worker = Mock()
        network, listener, face = app.worker, app.listener, app.face_worker
        app.suspend_screen()
        network.close.assert_not_called()
        listener.close.assert_not_called()
        self.assertEqual(listener.send.call_args.args[0]['cmd'], 'pause')
        face.close.assert_called_once()
        self.assertIsNone(app.face_worker)
        self.assertTrue(app.pending and app.awake)
        network.send.reset_mock()
        app.p.s.sleeping = True
        app.event({'event':'reply','text':'completed while blank'})
        self.assertFalse(app.pending)
        self.assertEqual(app.last_reply, 'completed while blank')
        network.send.assert_not_called()
        app.home = Mock()
        app.p.s.sleeping = False
        app.resume_screen()
        app.home.assert_called_once_with(activate_open=False)

    def test_open_activation_is_explicit_once_and_never_starts_a_pending_task(self):
        app = self.app()
        app.open_activation_pending = True
        app.pending = True
        app.listen()
        app.listener.send.assert_not_called()
        app.pending = False
        app.listen()
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'], 'activate')
        self.assertFalse(app.open_activation_pending)
        app.voice_event({'event':'wake','voice_epoch':app.voice_epoch,'source':'app_open'})
        self.assertTrue(app.awake)
        self.assertEqual(app.worker.send.call_args.args[0]['cmd'], 'speak')
        app.event({'event':'spoken'})
        self.callbacks.pop()()
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'], 'conversation')
        app.sleep()
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'], 'wake')

    def test_existing_configuration_never_silently_opts_into_open_activation(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'hermes.json'
            path.write_text('{"server_url":"https://server.example:18790/"}')
            self.assertIs(h.settings(path)['start_on_open'], False)
            h.save_config(dict(h.settings(path),start_on_open=True),path)
            self.assertIs(h.settings(path)['start_on_open'], True)
            with self.assertRaises(ValueError): h.save_config(dict(h.settings(path),start_on_open='false'),path)

    def test_http_tailnet_candidate_is_saved_but_lan_and_http_dns_are_rejected(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'hermes.json'
            for url in ('http://100.64.0.10:18790/', 'http://[fd7a:115c:a1e0::10]:18790/'):
                h.save_config(dict(h.DEFAULTS,server_url=url),path)
                self.assertEqual(h.settings(path)['server_url'],url)
            for url in ('http://192.168.1.10:18790/', 'http://server.example/', 'http://localhost:80/', 'http://100.128.0.1/'):
                with self.assertRaises(ValueError): h.save_config(dict(h.DEFAULTS,server_url=url),path)

    def test_settings_are_private_and_invalid_changes_preserve_previous_value(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'private/hermes.json'
            value = {'server_url':'https://server.example:18789/', 'auth_origin':None, 'user_id':'0', 'profile':'', 'ca_file':None, 'auto_speak':True, 'remember_session':False, 'start_on_open':False}
            h.save_config(value, path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            for url in ('http://server.example/', 'https://user:secret@server.example/', 'https://server.example/?token=x'):
                with self.assertRaises(ValueError): h.save_config(dict(value, server_url=url), path)
                self.assertEqual(json.loads(path.read_text()), value)

    def test_worker_private_protocol_does_not_put_login_in_argv(self):
        h = module('moto-hermes')
        with patch.object(h.subprocess, 'Popen') as launch:
            process = launch.return_value
            process.poll.return_value = None
            process.stdin.fileno.return_value = -1
            client = h.Worker(lambda callback: None, lambda event: None, binary='/fixture/moto-hermes', config='/fixture/hermes.json')
            client.start()
            client.send({'cmd':'login', 'password':'fixture-password', 'totp':'123456'})
            self.assertEqual(launch.call_args.args[0], ['/fixture/moto-hermes','--stdio','--config','/fixture/hermes.json'])
            self.assertNotIn('fixture-password', repr(launch.call_args))
            self.assertIn('fixture-password', process.stdin.write.call_args.args[0])
            client.close()

    def test_close_deadline_includes_a_full_pipe_to_an_unresponsive_child(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'stalled-child'
            binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(30)\n')
            binary.chmod(0o700)
            client = h.Worker(lambda callback: None, lambda event: None, binary=binary)
            client.start()
            process = client.process
            fd = process.stdin.fileno()
            os.set_blocking(fd,False)
            try:
                while True: os.write(fd, b'x'*4096)
            except BlockingIOError:
                pass
            done = threading.Event()
            client.close(after_stop=done.set)
            self.assertTrue(done.wait(7))
            self.assertIsNotNone(process.poll())

    def test_closed_worker_discards_queued_callbacks(self):
        h = module('moto-hermes')
        callbacks=[]; events=[]
        client=h.Worker(callbacks.append, events.append)
        client.deliver({'event':'reply','text':'late fixture'})
        client.close()
        for callback in callbacks: callback()
        self.assertEqual(events, [])

    def test_forget_cleanup_runs_after_worker_can_no_longer_save_a_cookie(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder)/'fixture-worker'
            cookie = Path(folder)/'hermes-auth.json'
            binary.write_text('#!'+sys.executable+'\nimport pathlib,sys,time\n'
                'sys.stdin.readline()\ntime.sleep(.1)\n'
                'pathlib.Path(sys.argv[-1]).with_name("hermes-auth.json").write_text("fixture-cookie")\n')
            binary.chmod(0o700)
            done = threading.Event()
            client = h.Worker(lambda callback: None, lambda event: None, binary=binary, config=Path(folder)/'hermes.json')
            client.start()
            def forget():
                self.assertIsNotNone(process.poll())
                cookie.unlink(missing_ok=True)
                done.set()
            process = client.process
            client.close(after_stop=forget)
            self.assertTrue(done.wait(4))
            self.assertFalse(cookie.exists())

    def app(self):
        from unittest.mock import Mock
        with patch.dict(sys.modules, {'tkinter': SimpleNamespace()}):
            h = module('moto-hermes-panel')
        self.h = h
        h.backend.save_delivery_diagnostic = Mock()
        root = Mock()
        root.after.side_effect = lambda delay, callback: self.callbacks.append(callback) or len(self.callbacks)
        self.callbacks = []
        panel = SimpleNamespace(s=SimpleNamespace(menu=object(), sleeping=False, root=root), page='hermes')
        app = h.HermesPanel(panel)
        app.connected = True
        app.scene = Mock()
        app.listener = Mock()
        app.worker = Mock()
        return app

    def test_recovered_reply_is_acknowledged_and_spoken_once_without_resending(self):
        from unittest.mock import Mock
        app = self.app()
        app.say = Mock()
        app.send_text('fixture question')
        tag = app.pending_turn
        reply = {'event':'reply','client_turn':tag,'text':'fixture answer'}
        with patch.object(self.h.backend, 'settings', return_value={'auto_speak':True}):
            app.event(reply)
            app.event(reply)
            app.event(dict(reply,client_turn='older-turn'))
        app.say.assert_called_once_with('fixture answer')
        self.assertFalse(app.pending)
        self.assertIsNone(app.pending_turn)
        calls = [call.args[0] for call in app.worker.send.call_args_list]
        self.assertEqual(sum(v['cmd']=='send' for v in calls),1)
        self.assertIn({'cmd':'ack_reply','client_turn':tag},calls)

    def test_delivery_diagnostics_exclude_text_and_identity(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder, patch.object(h,'CAPTURE_DIAGNOSTIC',Path(folder)/'capture.json'):
            h.save_delivery_diagnostic([{'stage':'reply_received','pending':True,'speaking':False,
                'connected':True,'reply_characters':600,'milliseconds':42,
                'text':'private response','session_id':'private-session','token':'private-token'}]*20)
            data = (Path(folder)/'delivery.json').read_text()
            self.assertEqual(len(json.loads(data)['events']),16)
            self.assertNotIn('private',data)

    def test_groq_checks_wake_before_any_agent_submission_and_replies_rearm(self):
        app = self.app()
        app.voice_event({'event':'utterance','voice_epoch':0,'path':'/fixture/prewake.wav'})
        app.worker.send.assert_not_called()
        app.voice_event({'event':'utterance','mode':'wake','voice_epoch':0,'path':'/fixture/wake.wav'})
        self.assertTrue(app.transcribing)
        self.assertEqual(app.worker.send.call_args.args[0], {'cmd':'transcribe','scope':'wake','epoch':app.epoch,'path':'/fixture/wake.wav'})
        app.event({'event':'wake_transcript','epoch':app.epoch,'accepted':False,'characters':12})
        self.assertFalse(app.awake or app.transcribing)
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'],'wake')
        epoch = app.voice_epoch
        app.voice_event({'event':'utterance','mode':'wake','voice_epoch':epoch,'path':'/fixture/second-wake.wav'})
        app.event({'event':'wake_transcript','epoch':app.epoch,'accepted':True,'characters':10})
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'],'accept_wake')
        self.assertFalse(any(call.args[0]['cmd']=='send' for call in app.worker.send.call_args_list))
        app.voice_event({'event':'wake','voice_epoch':app.voice_epoch,'source':'groq'})
        self.assertTrue(app.awake and app.speech_active)
        self.assertEqual(app.worker.send.call_args.args[0]['cmd'], 'speak')
        app.event({'event':'spoken'})
        self.callbacks.pop()()
        self.assertEqual(app.listener.send.call_args.args[0]['cmd'], 'conversation')
        epoch = app.voice_epoch
        app.voice_event({'event':'utterance','voice_epoch':epoch-1,'path':'/fixture/stale.wav'})
        self.assertFalse(app.transcribing)
        app.voice_event({'event':'utterance','voice_epoch':epoch,'path':'/fixture/current.wav'})
        self.assertTrue(app.transcribing)
        self.assertEqual(app.worker.send.call_args.args[0], {'cmd':'transcribe','scope':'conversation','epoch':app.epoch,'path':'/fixture/current.wav'})

    def test_groq_wake_reply_from_an_abandoned_screen_cannot_activate(self):
        app = self.app()
        app.voice_event({'event':'utterance','mode':'wake','voice_epoch':0,'path':'/fixture/wake.wav'})
        app.epoch += 1
        app.listener.send.reset_mock()
        app.event({'event':'wake_transcript','epoch':app.epoch-1,'accepted':True,'characters':10})
        app.listener.send.assert_not_called()
        self.assertFalse(app.awake)

    def test_conversation_transcript_cannot_be_used_as_a_wake_result(self):
        app = self.app()
        app.transcribing = True
        app.transcription_mode = 'wake'
        app.event({'event':'transcript','epoch':app.epoch,'text':'private prewake words'})
        self.assertTrue(app.transcribing)
        app.worker.send.assert_not_called()

    def test_groq_failure_is_visible_without_an_automatic_upload_retry(self):
        app = self.app()
        app.transcribing = True
        app.transcription_mode = 'wake'
        app.event({'event':'error','operation':'transcribe','epoch':app.epoch,'pending':False,'text':'Groq indisponível'})
        self.callbacks.pop()()
        app.voice_event({'event':'voice_listening','voice_epoch':app.voice_epoch,'mode':'wake'})
        self.assertEqual(app.notice,'Groq indisponível')
        app.worker.send.assert_not_called()
        self.assertFalse(app.awake)

    def test_rejected_wake_restores_standby_and_diagnostic_is_private_without_text(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as folder, patch.object(self.h.backend, 'CONFIG', Path(folder)/'hermes.json'):
            app.transcribing = True
            app.transcription_mode = 'wake'
            app.event({'event':'wake_transcript','epoch':app.epoch,'accepted':False,'characters':12,
                       'text':'private ambient words','audio':'private audio'})
            self.assertEqual(app.notice, 'Diga “Olá Hermes”')
            app.worker.send.assert_not_called()
            path = Path(folder)/'hermes-voice-diagnostic.json'
            self.assertEqual(json.loads(path.read_text()), {'accepted':False,'recognizer':'groq','characters':12})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            app.event({'event':'wake_transcript','epoch':app.epoch-1,'accepted':True,'characters':10})
            self.assertFalse(json.loads(path.read_text())['accepted'])

    def test_transcription_from_an_abandoned_screen_cannot_become_a_new_prompt(self):
        app = self.app()
        app.transcribing = app.awake = True
        app.epoch = 4
        app.event({'event':'transcript','epoch':3,'text':'old private utterance'})
        self.assertTrue(app.transcribing)
        app.worker.send.assert_not_called()
        app.event({'event':'error','operation':'transcribe','epoch':3,'text':'stale'})
        self.assertTrue(app.transcribing)

    def test_speech_failure_remains_visible_while_rearmed_until_the_next_utterance(self):
        app = self.app(); app.awake = app.speech_active = True
        error = 'VOICE_CONNECTION: Falha na conexão de voz com o Hermes.'
        app.event({'event':'speech_error','text':error})
        self.callbacks.pop()()
        app.voice_event({'event':'voice_listening','voice_epoch':app.voice_epoch,'mode':'conversation'})
        self.assertEqual(app.notice, error)
        self.assertEqual(app.state, 'error')
        app.voice_event({'event':'utterance','voice_epoch':app.voice_epoch,'path':'/fixture/next.wav'})
        self.assertEqual(app.voice_warning, '')
        self.assertTrue(app.transcribing)

    def test_new_conversation_waits_for_confirmation_and_voice_command_never_reaches_llm(self):
        app = self.app()
        app.awake = app.transcribing = True
        app.last_reply = 'previous reply'
        app.last_user = 'previous question'
        app.event({'event':'transcript','epoch':app.epoch,'text':'Nova conversa','action':'new_session'})
        self.assertTrue(app.switching)
        self.assertEqual(app.last_reply, 'previous reply')
        self.assertEqual(app.worker.send.call_args.args[0], {'cmd':'new_session'})
        app.event({'event':'new_session'})
        self.assertFalse(app.switching)
        self.assertEqual((app.last_user,app.last_reply), ('',''))
        self.assertEqual(app.worker.send.call_args.args[0]['cmd'], 'speak')

    def test_pending_turn_prevents_context_switch_and_closing_invalidates_rearm(self):
        app = self.app()
        app.pending = True
        app.new_session()
        app.worker.send.assert_not_called()
        app.pending = False
        app.resume_after_voice()
        callback = self.callbacks.pop()
        app.close()
        callback()
        self.assertIsNone(app.listener)
        self.assertIsNone(app.worker)

    def test_rpc_failure_shows_only_method_and_numeric_code(self):
        app = self.app()
        app.event({'event':'error','operation':'connect','text':'Operação recusada.',
                   'rpc':{'method':'session.create','code':4001,'detail':'fixture-private-secret'}})
        self.assertEqual(app.notice, 'Operação recusada. [session.create, código 4001]')
        self.assertNotIn('fixture-private-secret', app.notice)

    def test_killed_listener_cleanup_is_private_and_scoped_to_its_pid(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            own = run/'moto-hermes-listen-123-fixture'
            own.mkdir(mode=0o700)
            (own/'utterance.wav').write_bytes(b'synthetic audio')
            other = run/'moto-hermes-listen-456-fixture'
            other.mkdir(mode=0o700)
            h.cleanup_listener(123,run)
            self.assertFalse(own.exists())
            self.assertTrue(other.exists())

    def test_native_fields_and_no_terminal_paste_contract(self):
        text=(ROOT/'native/moto-hermes-panel.py').read_text()
        self.assertIn('p.field(',text)
        self.assertIn('p.register_input(',text)
        self.assertNotIn('send-keys',text)
        self.assertNotIn('insert_text(',text)


if __name__ == '__main__': unittest.main(verbosity=2)
