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
    def test_settings_are_private_and_invalid_changes_preserve_previous_value(self):
        h = module('moto-hermes')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'private/hermes.json'
            value = {'server_url':'https://server.example:18789/', 'auth_origin':None, 'user_id':'0', 'profile':'', 'ca_file':None, 'auto_speak':True, 'remember_session':False}
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

    def test_wake_audio_is_never_uploaded_and_replies_rearm_without_touch(self):
        app = self.app()
        app.voice_event({'event':'utterance','voice_epoch':0,'path':'/fixture/prewake.wav'})
        app.worker.send.assert_not_called()
        app.voice_event({'event':'wake','voice_epoch':0})
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
        self.assertEqual(app.worker.send.call_args.args[0], {'cmd':'transcribe','epoch':app.epoch,'path':'/fixture/current.wav'})

    def test_transcription_from_an_abandoned_screen_cannot_become_a_new_prompt(self):
        app = self.app()
        app.transcribing = app.awake = True
        app.epoch = 4
        app.event({'event':'transcript','epoch':3,'text':'old private utterance'})
        self.assertTrue(app.transcribing)
        app.worker.send.assert_not_called()
        app.event({'event':'error','operation':'transcribe','epoch':3,'text':'stale'})
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
