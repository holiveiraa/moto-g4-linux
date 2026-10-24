#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in real-service chain, synthetic microphone/speaker, isolated Tk/tmux.

Requires a private Xvfb DISPLAY and the installed local recognizer/model.
Uses the owner's existing app cookie and Groq key only on this machine; creates
one separate Hermes conversation. Never captures a physical microphone, plays
the loudspeaker or copies credentials into results. See tests/README.md.
"""
import argparse
import array
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave

ROOT = Path(__file__).resolve().parents[1]


def fake_capture(folder):
    """Production listener/VAD still runs; only ALSA input is substituted."""
    with (folder/'capture-count').open('a+') as count:
        fcntl.flock(count, fcntl.LOCK_EX)
        count.seek(0)
        number = int(count.read() or '0') + 1
        count.seek(0); count.truncate(); count.write(str(number)); count.flush()
    def send(pcm):
        for start in range(0, len(pcm), 1920):
            os.write(1, pcm[start:start+1920].ljust(1920, b'\0'))
            time.sleep(.02)
    def silence(seconds): send(bytes(int(seconds*48000)*2))
    def say(name):
        with wave.open(str(folder/name), 'rb') as wav:
            assert wav.getframerate() == 16000 and wav.getnchannels() == 1 and wav.getsampwidth() == 2
            pcm = array.array('h', wav.readframes(wav.getnframes()))
        # Repeat each sample: native 48 kHz input, downsampled by the real listener.
        native = array.array('h', (v for sample in pcm for v in (sample,)*3))
        silence(.6); send(native.tobytes()); silence(4)
    app_open = (folder/'activation').read_text() == 'app-open'
    if app_open and number == 1:
        say('question.wav')
    elif not app_open and number == 1:
        say('negative.wav')
        say('wake.wav')
    elif not app_open and number == 2:
        say('question.wav')
    # Speech-shaped noise below the measured front-end floor must not create
    # another transcription/agent turn after the reply has rearmed capture.
    while True:
        with wave.open(str(folder/'question.wav'), 'rb') as wav:
            low = array.array('h', wav.readframes(wav.getnframes()))
        peak = max((abs(v) for v in low), default=1) or 1
        noise = array.array('h', (int(v*24/peak) for sample in low for v in (sample,)*3))
        send(noise.tobytes()); silence(1)


def fake_playback(folder):
    total = 0
    while block := sys.stdin.buffer.read(8192): total += len(block)
    with (folder/'playback-counts').open('a') as output:
        output.write(str(total)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-config', type=Path, required=True)
    parser.add_argument('--wake-wav', type=Path, required=True)
    parser.add_argument('--negative-wav', type=Path, required=True)
    parser.add_argument('--question-wav', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--expected-transcript', help='Known synthetic question text; compare without logging the returned transcript.')
    parser.add_argument('--activation', choices=('wake-word','app-open'), default='wake-word')
    parser.add_argument('--idle-seconds', type=int, default=5, help='Observe rearmed capture without another request (5-90 seconds).')
    args = parser.parse_args()
    if not 5 <= args.idle_seconds <= 90:
        parser.error('idle-seconds must be between 5 and 90')
    if not os.environ.get('DISPLAY'):
        parser.error('Start a private Xvfb display first; never use the owner display.')
    os.umask(0o077)
    source = args.live_config.resolve(strict=True)
    originals = {p:p.read_bytes() for p in (source, source.with_name('hermes-auth.json'), source.with_name('groq.json'))}
    server = 'moto-hermes-chain-'+str(os.getpid())
    real_run = subprocess.run
    def tmux(*tail):
        return real_run(['tmux','-L',server,*tail],capture_output=True,text=True,timeout=4)
    def remap(argv, *more, **kwargs):
        argv = list(argv)
        if argv[:3] == ['tmux','-L','moto']: argv[2] = server
        return real_run(argv,*more,**kwargs)
    spec = importlib.util.spec_from_file_location('chain_shell', ROOT/'native/moto-shell.py')
    ui = importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)
    backend = ui.panel_module.hermes_module.backend
    shell = terminal = None
    with tempfile.TemporaryDirectory(prefix=server+'-') as directory:
        folder = Path(directory)
        config = folder/'config'; config.mkdir(mode=0o700)
        for original, data in originals.items(): (config/original.name).write_bytes(data)
        settings = json.loads(originals[source]); settings.update(auto_speak=True, remember_session=True, start_on_open=args.activation=='app-open')
        (config/source.name).write_text(json.dumps(settings))
        (folder/'activation').write_text(args.activation)
        # Never copy the production journal/session: this worker creates its own.
        for supplied, name in ((args.negative_wav,'negative.wav'),(args.wake_wav,'wake.wav'),(args.question_wav,'question.wav')):
            shutil.copyfile(supplied, folder/name)
        tools = folder/'bin'; tools.mkdir(mode=0o700)
        for name, flag in (('arecord','--fake-capture'),('aplay','--fake-playback')):
            wrapper = tools/name
            wrapper.write_text('#!'+sys.executable+'\nimport os\nos.execv('+repr(sys.executable)+','+
                repr([sys.executable,str(Path(__file__).resolve()),flag,str(folder)])+')\n')
            wrapper.chmod(0o700)
        os.environ['PATH'] = str(tools)+os.pathsep+os.environ['PATH']
        os.environ['MOTO_UX_CONFIG'] = str(folder/'ux.json')
        backend.CONFIG = config/source.name
        backend.CAPTURE_DIAGNOSTIC = folder/'runtime/capture.json'
        backend.BINARY = str(args.binary.resolve(strict=True))
        commands = []; events = []; failures = []; phases = []; activations = []
        original_worker = backend.Worker
        class ObservedWorker(original_worker):
            # Observe real commands/events, without replacing worker behavior.
            def send(self, value):
                if self.arguments[0] != '--face-stdio': commands.append(value.get('cmd'))
                super().send(value)
            def deliver(self, value, generation=None):
                name = value.get('event')
                if name == 'wake': activations.append(value.get('source'))
                if name == 'transcript' and args.expected_transcript is not None:
                    def normalize(text):
                        decomposed = unicodedata.normalize('NFD', text.lower())
                        words = ''.join(c if c.isalnum() else ' ' for c in decomposed if not unicodedata.combining(c))
                        return ' '.join(words.split())
                    if normalize(value.get('text', '')) != normalize(args.expected_transcript):
                        failures.append(('transcript_mismatch', None, 'Known synthetic question was not recognized.'))
                        return
                if name not in ('face','listener_ready'): events.append(name)
                # These workers return fixed, sanitized client error strings;
                # never retain status/reply/transcript payloads here.
                if name in ('error','speech_error','voice_error'):
                    failures.append((name, value.get('operation'), value.get('text','')[:256]))
                super().deliver(value, generation)
        backend.Worker = ObservedWorker
        ui.SOCKET = str(folder/'control.sock')
        light = folder/'brightness'; light.write_text('100'); ui.LIGHT = light
        ui.Shell.write_geometry = lambda self: None
        ui.Shell.vpn_worker = lambda self: None
        ui.Shell.tmux = lambda self,*tail: tmux(*tail)
        assert tmux('-f','/dev/null','new-session','-d','-s','moto','sleep 600').returncode == 0
        terminal = subprocess.Popen(['xterm','-class','XTerm','-e','tmux','-L',server,'attach','-t','moto'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            subprocess.run = remap
            shell = ui.Shell(); app = shell.panel.hermes
            shell.root.report_callback_exception = lambda kind,error,trace: failures.append(('tk',kind.__name__))
            shell.panel.voice_backend.capture_device = lambda: 'hw:0,0'
            shell.panel.voice_backend.CONFIG = config/'groq.json'
            app.home()
            quiet_until = None
            deadline = time.monotonic()+240
            while time.monotonic() < deadline:
                shell.root.update(); time.sleep(.005)
                if failures: raise RuntimeError('Chain failed at '+repr(failures)+'; events='+repr(events))
                if 'wake_checked' in events and 'wake' not in events and app.notice == 'Diga “Olá Hermes”':
                    if 'rejected_wake_restored' not in phases: phases.append('rejected_wake_restored')
                # Reader events precede Tk delivery. Wait for the UI to apply
                # the second spoken result and the newly rearmed listener.
                required_listens = 2 if args.activation=='app-open' else 4
                if (events.count('spoken') >= 2 and events.count('voice_listening') >= required_listens
                        and app.awake and not (app.pending or app.transcribing or app.speech_active)
                        and app.notice == 'Pode falar'):
                    if quiet_until is None: quiet_until = time.monotonic()+args.idle_seconds
                    if time.monotonic() >= quiet_until: break
                if commands.count('transcribe') > 1 or commands.count('send') > 1:
                    raise RuntimeError('Unsolicited turn during rearmed idle observation')
            else: raise RuntimeError('Chain timed out; event names='+repr(events)+'; commands='+repr(commands))
            if args.activation=='wake-word': assert 'rejected_wake_restored' in phases
            assert activations == ['app_open' if args.activation=='app-open' else 'wake_word']
            for name in ('connected','wake','utterance','transcript','reply'): assert name in events, name
            assert events.index('wake') < events.index('utterance') < events.index('transcript') < events.index('reply')
            assert commands.count('transcribe') == 1 and commands.count('send') == 1
            assert app.awake and not (app.pending or app.transcribing or app.speech_active)
            assert app.notice == 'Pode falar'
            counts = [int(n) for n in (folder/'playback-counts').read_text().splitlines()]
            assert len(counts) == 2 and all(n > 0 for n in counts)
            speech = json.loads((config/'hermes-speech-diagnostic.json').read_text())
            assert speech['outcome'] == 'completed' and speech['bytes'] == counts[-1]
            print(json.dumps({'passed':True,'live_services':['Groq','Hermes','Edge'],
                'transcript_checked':args.expected_transcript is not None,
                'synthetic_microphone':True,'synthetic_speaker':True,'activation':args.activation,
                'negative_wake_restored':'rejected_wake_restored' in phases,
                'postwake_transcriptions':1,'agent_turns':1,'audio_bytes':counts,
                'speech_sample_rate':speech['sample_rate'],'largest_reply_chunk':speech['largest_chunk'],
                'rearmed':True,'idle_without_extra_turn_seconds':args.idle_seconds}),flush=True)
        finally:
            subprocess.run = real_run
            if shell:
                children = [w.process for w in (app.worker,app.face_worker,app.listener) if w and w.process]
                app.close(); shell.quick_voice.close()
                # Keep ephemeral credentials until all their workers stop.
                for child in children: child.wait(timeout=9)
                shell.root.destroy()
            if terminal:
                terminal.terminate()
                try: terminal.wait(timeout=3)
                except subprocess.TimeoutExpired: terminal.kill(); terminal.wait(timeout=3)
            tmux('kill-server')
            for original, data in originals.items(): assert original.read_bytes() == data


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--fake-capture': fake_capture(Path(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == '--fake-playback': fake_playback(Path(sys.argv[2]))
    else: main()
