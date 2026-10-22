#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline tests: credential handling, HTTP failures, audio bounds and paste data."""
import array
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import wave

spec = spec_from_file_location('voice', Path(__file__).resolve().parents[1]/'native/moto-voice.py')
v = module_from_spec(spec)
spec.loader.exec_module(v)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old = v.CONFIG
        self.old_lock = v.capture.LOCK
        v.capture.LOCK = Path(self.folder.name)/'capture.lock'
        v.CONFIG = Path(self.folder.name)/'private/groq.json'

    def tearDown(self):
        v.CONFIG = self.old
        v.capture.LOCK = self.old_lock
        self.folder.cleanup()

    def wav(self, amplitude=2000, seconds=1):
        path = Path(self.folder.name)/'test.wav'
        samples = array.array('h', (int(amplitude*math.sin(i*.2)) for i in range(int(16000*seconds))))
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            stream.writeframes(samples.tobytes())
        return path

    def test_private_key_roundtrip(self):
        v.save_key('gsk_'+'testOnly'*8)
        self.assertTrue(v.settings()['api_key'].startswith('gsk_'))
        if os.name != 'nt':
            self.assertEqual(v.CONFIG.stat().st_mode & 0o777, 0o600)
            self.assertEqual(v.CONFIG.parent.stat().st_mode & 0o777, 0o700)
        v.remove_key()
        self.assertFalse(v.settings())

    def test_bad_key_does_not_replace_good(self):
        key = 'gsk_'+'testOnly'*8
        v.save_key(key)
        for bad in ('', 'Bearer '+key, key+'\nInjected: header', 'é'*30):
            with self.assertRaises(ValueError):
                v.save_key(bad)
        self.assertEqual(v.settings()['api_key'], key)

    def test_no_request_without_key(self):
        with patch.object(v, 'build_opener') as opener:
            with self.assertRaises(RuntimeError):
                v.test_key()
            opener.assert_not_called()

    def test_http_error_redacts_upstream(self):
        key = 'gsk_'+'testOnly'*8
        v.save_key(key)
        for code in (401, 403, 429, 500, 302):
            err = HTTPError(v.API, code, key, {}, io.BytesIO(key.encode()))
            with patch.object(v, 'build_opener') as opener:
                opener.return_value.open.side_effect = err
                with self.assertRaises(RuntimeError) as caught:
                    v.test_key()
                self.assertNotIn(key, str(caught.exception))

    def test_redirect_is_refused(self):
        self.assertIsNone(v.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://elsewhere/'))

    def test_capture_limits_and_silence(self):
        self.assertAlmostEqual(v.inspect_wave(self.wav())['seconds'], 1)
        for amplitude, seconds in ((0, 1), (2000, .1), (2000, 62)):
            with self.assertRaises(RuntimeError):
                v.inspect_wave(self.wav(amplitude, seconds))

    def test_transcription_multipart(self):
        with patch.object(v, 'request', return_value={'text': 'Olá, ação no Example server.'}) as request:
            self.assertEqual(v.transcribe(self.wav()), 'Olá, ação no Example server.')
            args = request.call_args.args
            self.assertEqual(args[0], 'audio/transcriptions')
            self.assertIn(b'name="language"\r\n\r\npt', args[1])
            self.assertIn(b'RIFF', args[1])
            self.assertIn(b'whisper-large-v3-turbo', args[1])
        with patch.object(v, 'request', return_value={'text': ''}):
            with self.assertRaises(RuntimeError):
                v.transcribe(self.wav())

    def test_paste_removes_execution_controls(self):
        value = v.safe_text('Olá\r\nrm exemplo\tç\x1b[31m\x00\u202e')
        self.assertEqual(value, 'Olá rm exemplo ç[31m')
        self.assertNotIn('\n', value)
        self.assertNotIn('\x1b', value)
        self.assertEqual(len(v.safe_text('x'*25000)), 20000)

    def test_closed_target_does_not_load_buffer(self):
        import subprocess
        with patch.object(v.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '%8\n', '')) as command:
            with self.assertRaises(RuntimeError):
                v.insert_text('%3', 'olá')
            self.assertEqual(command.call_count, 1)

    def test_capture_does_not_choose_multimedia10(self):
        with patch.object(Path, 'read_text', return_value='00-09: MultiMedia10 : capture 1\n00-00: MultiMedia1 : capture 1\n'):
            self.assertEqual(v.capture_device(), 'hw:0,0')

    @unittest.skipIf(os.name == 'nt', 'Linux recording process signals')
    def test_stop_and_discard_leave_no_recording_child(self):
        import subprocess
        import sys
        real_popen = subprocess.Popen
        real_directory = tempfile.TemporaryDirectory
        original = self.wav()
        processes = []
        def launch(args, **kwargs):
            self.assertIn('60', args)
            code = 'import shutil,sys,time; shutil.copyfile(sys.argv[1],sys.argv[2]); time.sleep(60)'
            child = real_popen([sys.executable, '-c', code, str(original), args[-1]], **kwargs)
            processes.append(child)
            return child
        recorder = v.Recorder()
        with patch.object(v, 'capture_device', return_value='hw:0,0'), patch.object(v.subprocess, 'Popen', side_effect=launch), patch.object(v.tempfile, 'TemporaryDirectory', side_effect=lambda **kw: real_directory(prefix=kw.get('prefix'), dir=self.folder.name)):
            try:
                recorder.start()
                deadline = time.monotonic() + 2
                while (not recorder.path.exists() or recorder.path.stat().st_size < 44) and time.monotonic() < deadline:
                    time.sleep(.02)
                folder = recorder.path.parent
                self.assertTrue(recorder.recording)
                path = recorder.stop()
                self.assertAlmostEqual(v.inspect_wave(path)['seconds'], 1)
                recorder.discard()
                self.assertIsNotNone(processes[0].poll())
                self.assertFalse(folder.exists())
                # Navigation can discard while the stop/transcription worker is
                # finishing. Both must reap the owned child and release capture.
                recorder.start()
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(recorder.stop), pool.submit(recorder.discard)]
                    for future in futures:
                        try:
                            future.result(timeout=5)
                        except RuntimeError:
                            pass  # Discard won: no recording remains to transcribe.
                self.assertIsNotNone(processes[-1].poll())
                lease = v.capture.CaptureLease()
                lease.acquire(); lease.release()
            finally:
                recorder.discard()


if __name__ == '__main__':
    unittest.main(verbosity=2)
