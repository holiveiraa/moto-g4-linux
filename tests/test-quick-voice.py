#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Async dictation contracts: destination changes, cancellation and retries."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace as NS
import unittest

spec = spec_from_file_location('quick', Path(__file__).resolve().parents[1] / 'native/moto-quick-voice.py')
quick = module_from_spec(spec)
spec.loader.exec_module(quick)


class Recorder:
    def start(self):
        self.recording, self.started = True, time.monotonic()
        self.discard_calls = 0

    def stop(self):
        self.recording = False
        return Path('/fixture/audio.wav')

    def discard(self):
        self.recording = False
        self.discard_calls = getattr(self, 'discard_calls', 0) + 1


class QuickTests(unittest.TestCase):
    def setUp(self):
        self.inserted, self.messages = [], []
        self.context = '%1|100|ssh|0|0'
        self.shell = NS(menu=None, sleeping=False, mods=set(), events=queue.Queue(),
                        draw=lambda: None, message=self.messages.append,
                        tmux=lambda *a: NS(returncode=0, stdout=self.context),
                        panel=NS(voice=NS(busy=False, stopping=False, recorder=NS(recording=False))))
        self.backend = NS(Recorder=Recorder, settings=lambda: {'api_key': 'fixture'},
                          pane_target=lambda: ['%1', 'example-server'], inspect_wave=lambda p: {},
                          transcribe=lambda p: 'Olá Codex',
                          insert_text=lambda pane, text: self.inserted.append((pane, text)))
        self.q = quick.QuickDictation(self.shell, self.backend)

    def until(self, condition):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            while not self.shell.events.empty():
                self.shell.events.get_nowait()()
            if condition():
                return
            time.sleep(.005)
        self.fail('Async action did not complete')

    def test_second_tap_pastes_once_to_captured_pane(self):
        self.q.toggle()
        self.assertEqual(self.q.state, 'recording')
        self.q.toggle()
        self.until(lambda: self.q.state == 'idle')
        self.assertEqual(self.inserted, [('%1', 'Olá Codex')])

    def test_changed_tab_keeps_text_without_pasting(self):
        self.q.toggle()
        self.context = '%2|200|bash|0|0'
        self.q.toggle()
        self.until(lambda: self.q.state == 'result')
        self.assertEqual(self.q.result, 'Olá Codex')
        self.assertEqual(self.inserted, [])

    def test_same_pane_changed_program_requires_review(self):
        self.q.toggle()
        self.context = '%1|100|bash|0|0'
        self.q.toggle()
        self.until(lambda: self.q.state == 'result')
        self.assertEqual(self.inserted, [])

    def test_late_canceled_response_does_not_paste_or_change_new_recording(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.backend.transcribe = lambda p: (gate.wait(2), 'Late result')[1]
        self.q.toggle()
        old_recorder = self.q.recorder
        self.q.toggle()
        self.q.cancel()
        self.until(lambda: self.q.state == 'idle')
        self.q.toggle()
        gate.set()
        self.until(lambda: old_recorder.discard_calls >= 3)
        self.assertEqual(self.q.state, 'recording')
        self.assertEqual(self.inserted, [])
        self.q.close()

    def test_network_error_keeps_audio_for_explicit_retry(self):
        calls = []
        def transcribe(path):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError('Offline')
            return 'Retry worked'
        self.backend.transcribe = transcribe
        self.q.toggle()
        self.q.toggle()
        self.until(lambda: self.q.state == 'retry')
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(self.q.recorder)
        self.q.toggle()
        self.until(lambda: self.q.state == 'idle')
        self.assertEqual(self.inserted, [('%1', 'Retry worked')])

    def test_panel_focus_never_receives_automatic_paste(self):
        self.q.toggle()
        self.shell.menu = object()
        self.q.toggle()
        self.until(lambda: self.q.state == 'result')
        self.assertEqual(self.inserted, [])

    def test_missing_key_does_not_start_microphone(self):
        self.backend.settings = lambda: {}
        self.q.toggle()
        self.assertEqual(self.q.state, 'idle')
        self.assertIsNone(self.q.recorder)

    def test_duration_limit_stops_and_transcribes(self):
        self.q.toggle()
        self.q.recorder.started -= 61
        self.q.tick()
        self.until(lambda: self.q.state == 'idle')
        self.assertEqual(len(self.inserted), 1)


if __name__ == '__main__':
    unittest.main()
