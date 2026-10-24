#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in real-service chain and isolated Tk/tmux, synthetic audio by default.

Requires a private Xvfb DISPLAY and the installed Silero detector/model.
Uses the owner's existing app cookie and Groq key only on this machine. Reuse
an explicitly supplied idle test conversation; creating one requires a flag.
--physical-audio explicitly uses the real
microphone/speaker with supplied synthetic stimuli. Never copies credentials
or recordings into results. See tests/README.md.
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
    physical = folder/'physical-tools.json'
    if physical.exists():
        tools = json.loads(physical.read_text())
        os.execv(tools['arecord'], [tools['arecord'], *sys.argv[3:]])
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
    turns = int((folder/'turns').read_text())
    if app_open and 1 <= number <= turns:
        say('question.wav')
    elif not app_open and number == 1:
        say('negative.wav')
    elif not app_open and number == 2:
        say('wake.wav')
    elif not app_open and 3 <= number <= 2+turns:
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
    sessions = parser.add_mutually_exclusive_group(required=True)
    sessions.add_argument('--session-journal', type=Path, help='Reuse this existing idle conversation; source journal is copied and remains unchanged.')
    sessions.add_argument('--create-test-conversation', action='store_true', help='Explicitly authorize one new real Hermes test conversation.')
    parser.add_argument('--drop-first-reply', action='store_true', help='Drop the first local reply delivery and require recovery from the client cache without another agent submission.')
    expected = parser.add_mutually_exclusive_group()
    expected.add_argument('--expected-transcript', help='Known synthetic question text; compare without logging the returned transcript.')
    expected.add_argument('--expected-word', action='append', default=[], help='Require each known stimulus keyword as a complete word; does not establish a verbatim match.')
    parser.add_argument('--turns', type=int, choices=(1,2), default=1)
    parser.add_argument('--activation', choices=('wake-word','app-open'), default='wake-word')
    parser.add_argument('--idle-seconds', type=int, default=5, help='Observe rearmed capture without another request (5-90 seconds).')
    parser.add_argument('--physical-audio', action='store_true', help='Use the real microphone/speaker and play the supplied synthetic stimuli. Close the production voice app first.')
    parser.add_argument('--physical-negative-first', action='store_true', help='Include a negative acoustic stimulus before the wake phrase; default physical review starts with the wake phrase.')
    args = parser.parse_args()
    if not 5 <= args.idle_seconds <= 90:
        parser.error('idle-seconds must be between 5 and 90')
    if not os.environ.get('DISPLAY'):
        parser.error('Start a private Xvfb display first; never use the owner display.')
    os.umask(0o077)
    source = args.live_config.resolve(strict=True)
    originals = {p:p.read_bytes() for p in (source, source.with_name('hermes-auth.json'), source.with_name('groq.json'))}
    journal = None
    if args.session_journal:
        journal = args.session_journal.resolve(strict=True)
        originals[journal] = journal.read_bytes()
        saved = json.loads(originals[journal])
        if not saved.get('stored_session_id') or saved.get('turn',{}).get('phase') != 'idle':
            parser.error('Supply an existing idle test conversation; no new conversation was authorized.')
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
        physical_tools = {name:shutil.which(name) for name in ('arecord','aplay')}
        if args.physical_audio:
            if not all(physical_tools.values()): parser.error('Physical review needs arecord and aplay')
            (folder/'physical-tools.json').write_text(json.dumps(physical_tools))
        config = folder/'config'; config.mkdir(mode=0o700)
        for original, data in originals.items(): (config/original.name).write_bytes(data)
        if journal and journal.name != 'hermes-task.json':
            shutil.copyfile(journal, config/'hermes-task.json')
        settings = json.loads(originals[source]); settings.update(auto_speak=True, remember_session=True, start_on_open=args.activation=='app-open')
        (config/source.name).write_text(json.dumps(settings))
        (folder/'activation').write_text(args.activation)
        (folder/'turns').write_text(str(args.turns))
        # Never copy the production journal/session: this worker creates its own.
        for supplied, name in ((args.negative_wav,'negative.wav'),(args.wake_wav,'wake.wav'),(args.question_wav,'question.wav')):
            shutil.copyfile(supplied, folder/name)
        tools = folder/'bin'; tools.mkdir(mode=0o700)
        for name, flag in (('arecord','--fake-capture'),('aplay','--fake-playback')):
            if args.physical_audio and name == 'aplay': continue
            wrapper = tools/name
            wrapper.write_text('#!'+sys.executable+'\nimport os,sys\nos.execv('+repr(sys.executable)+','+
                repr([sys.executable,str(Path(__file__).resolve()),flag,str(folder)])+'+sys.argv[1:])\n')
            wrapper.chmod(0o700)
        os.environ['PATH'] = str(tools)+os.pathsep+os.environ['PATH']
        os.environ['MOTO_UX_CONFIG'] = str(folder/'ux.json')
        backend.CONFIG = config/source.name
        backend.CAPTURE_DIAGNOSTIC = folder/'runtime/capture.json'
        backend.BINARY = str(args.binary.resolve(strict=True))
        if journal: os.environ['MOTO_HERMES_REQUIRE_EXISTING_SESSION'] = '1'
        commands = []; events = []; failures = []; phases = []; activations = []; played_counts = []; listening_modes = []; speech_decisions = []; transcription_scopes = []; wake_verdicts = []
        reply_available = []; synthesis_delay = []; reply_tags = set()
        negative_used = args.activation=='wake-word' and (not args.physical_audio or args.physical_negative_first)
        expected_wake = 0 if args.activation=='app-open' else (2 if negative_used else 1)
        original_worker = backend.Worker
        class ObservedWorker(original_worker):
            dropped_reply = False
            # Observe real commands/events, without replacing worker behavior.
            def send(self, value):
                if value.get('cmd') == 'speak' and len(reply_available) > len(synthesis_delay):
                    synthesis_delay.append(round((time.monotonic()-reply_available[-1])*1000))
                if self.arguments[0] != '--face-stdio': commands.append(value.get('cmd'))
                if value.get('cmd') == 'transcribe': transcription_scopes.append(value.get('scope','conversation'))
                super().send(value)
            def deliver(self, value, generation=None):
                name = value.get('event')
                if name == 'reply' and value.get('client_turn') not in reply_tags:
                    reply_tags.add(value.get('client_turn'));reply_available.append(time.monotonic())
                if name == 'reply' and args.drop_first_reply and not self.dropped_reply:
                    self.dropped_reply = True
                    return
                if name == 'speech_checked': speech_decisions.append(value.get('decision'))
                if name == 'wake_transcript': wake_verdicts.append(value.get('accepted') is True)
                if name == 'voice_listening': listening_modes.append(value.get('mode'))
                if name == 'spoken': played_counts.append(json.loads((config/'hermes-speech-diagnostic.json').read_text())['bytes'])
                if name == 'wake': activations.append(value.get('source'))
                if name == 'transcript' and (args.expected_transcript is not None or args.expected_word):
                    def normalize(text):
                        decomposed = unicodedata.normalize('NFD', text.lower())
                        words = ''.join(c if c.isalnum() else ' ' for c in decomposed if not unicodedata.combining(c))
                        return ' '.join(words.split())
                    recognized = normalize(value.get('text', ''))
                    matched = (all(normalize(word) in recognized.split() for word in args.expected_word)
                               if args.expected_word else recognized == normalize(args.expected_transcript))
                    if not matched:
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
        stimulus = None
        try:
            subprocess.run = remap
            shell = ui.Shell(); app = shell.panel.hermes
            shell.root.report_callback_exception = lambda kind,error,trace: failures.append(('tk',kind.__name__))
            shell.panel.voice_backend.capture_device = lambda: 'hw:0,0'
            shell.panel.voice_backend.CONFIG = config/'groq.json'
            app.home()
            quiet_until = None
            acoustic_phase = 'initial'
            physical_questions = 0
            acoustic_due = 0
            acoustic_started = time.monotonic()
            deadline = time.monotonic()+240
            while time.monotonic() < deadline:
                shell.root.update(); time.sleep(.005)
                if failures: raise RuntimeError('Chain failed at '+repr(failures)+'; events='+repr(events))
                if False in wake_verdicts and 'wake' not in events and not app.transcribing and app.notice == 'Diga “Olá Hermes”':
                    if 'rejected_wake_restored' not in phases: phases.append('rejected_wake_restored')
                if args.physical_audio:
                    now = time.monotonic()
                    if stimulus and stimulus.poll() is not None and stimulus.returncode:
                        raise RuntimeError('Acoustic stimulus playback failed')
                    if acoustic_phase in ('wait_negative','wait_wake') and now-acoustic_started > 30:
                        metrics = {}
                        for p in (folder/'runtime/speech.json', config/'hermes-voice-diagnostic.json'):
                            if p.exists(): metrics[p.name] = json.loads(p.read_text())
                        raise RuntimeError('Acoustic stimulus was not handled: '+acoustic_phase+'; safe metrics='+repr(metrics)+'; speech decisions='+repr(speech_decisions[-4:]))
                    if acoustic_phase == 'initial' and args.activation == 'wake-word' and 'wake' in listening_modes:
                        acoustic_phase, acoustic_due = ('play_negative' if args.physical_negative_first else 'play_wake'), now+.8
                    elif acoustic_phase == 'wait_negative':
                        if activations: raise RuntimeError('Negative acoustic stimulus activated the assistant')
                        if 'rejected_wake_restored' in phases and stimulus.poll() is not None:
                            acoustic_phase, acoustic_due = 'play_wake', now+.8
                    if (acoustic_phase in ('initial','wait_wake') and app.awake and app.notice == 'Pode falar'
                            and not (app.pending or app.transcribing or app.speech_active)):
                        acoustic_phase, acoustic_due = 'play_question', now+.8
                    if (acoustic_phase == 'wait_question' and physical_questions < args.turns
                            and len(played_counts) >= physical_questions+1 and app.notice == 'Pode falar'
                            and not (app.pending or app.transcribing or app.speech_active)):
                        acoustic_phase, acoustic_due = 'play_question', now+.8
                    if acoustic_phase.startswith('play_') and now >= acoustic_due:
                        name = acoustic_phase.removeprefix('play_')
                        if name == 'question': physical_questions += 1
                        stimulus = subprocess.Popen([physical_tools['aplay'],'-q','-D','default',str(folder/(name+'.wav'))],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        acoustic_phase = 'wait_'+name
                        acoustic_started = now
                # Reader events precede Tk delivery. Wait for the UI to apply
                # the second spoken result and the newly rearmed listener.
                required_listens = (2 if args.activation=='app-open' else (3 if args.physical_audio and not args.physical_negative_first else 4))+args.turns-1
                if (events.count('spoken') >= 1+args.turns and events.count('voice_listening') >= required_listens
                        and app.awake and not (app.pending or app.transcribing or app.speech_active)
                        and app.notice == 'Pode falar'):
                    if quiet_until is None: quiet_until = time.monotonic()+args.idle_seconds
                    if time.monotonic() >= quiet_until: break
                if (transcription_scopes.count('conversation') > args.turns or commands.count('send') > args.turns
                        or transcription_scopes.count('wake') > expected_wake):
                    raise RuntimeError('Unsolicited turn during rearmed idle observation')
            else: raise RuntimeError('Chain timed out; event names='+repr(events)+'; commands='+repr(commands))
            if args.activation=='wake-word' and (not args.physical_audio or args.physical_negative_first): assert 'rejected_wake_restored' in phases
            assert activations == ['app_open' if args.activation=='app-open' else 'groq']
            for name in ('connected','wake','utterance','transcript','reply'): assert name in events, name
            assert events.index('wake') < events.index('transcript') < events.index('reply')
            if args.activation=='wake-word':
                assert events.index('utterance') < events.index('wake_transcript') < events.index('wake')
            assert transcription_scopes.count('wake') == expected_wake
            assert transcription_scopes.count('conversation') == args.turns and commands.count('send') == args.turns
            assert app.awake and not (app.pending or app.transcribing or app.speech_active)
            assert app.notice == 'Pode falar'
            if journal:
                assert json.loads((config/'hermes-task.json').read_text())['stored_session_id'] == saved['stored_session_id']
            if args.drop_first_reply: assert app.worker.dropped_reply and 'poll_reply' in commands
            assert len(synthesis_delay) == args.turns and max(synthesis_delay) < (3000 if args.drop_first_reply else 500)
            counts = played_counts if args.physical_audio else [int(n) for n in (folder/'playback-counts').read_text().splitlines()]
            assert len(counts) == 1+args.turns and all(n > 0 for n in counts)
            speech = json.loads((config/'hermes-speech-diagnostic.json').read_text())
            assert speech['outcome'] == 'completed' and speech['bytes'] == counts[-1]
            print(json.dumps({'passed':True,'live_services':['Groq','Hermes','Edge'],
                'transcript_checked':args.expected_transcript is not None or bool(args.expected_word),
                'transcript_check':'required_words' if args.expected_word else ('exact' if args.expected_transcript is not None else 'none'),
                'synthetic_microphone':not args.physical_audio,'synthetic_speaker':not args.physical_audio,
                'physical_audio':args.physical_audio,'activation':args.activation,
                'reused_conversation':journal is not None,'dropped_reply_recovered':args.drop_first_reply,
                'reply_to_synthesis_request_ms':synthesis_delay,
                'negative_stimulus_used':negative_used,
                'negative_wake_restored':negative_used and 'rejected_wake_restored' in phases,
                'wake_transcriptions':expected_wake,'postwake_transcriptions':args.turns,'agent_turns':args.turns,'audio_bytes':counts,
                'speech_sample_rate':speech['sample_rate'],'largest_reply_chunk':speech['largest_chunk'],
                'rearmed':True,'idle_without_extra_turn_seconds':args.idle_seconds}),flush=True)
        finally:
            subprocess.run = real_run
            if stimulus and stimulus.poll() is None:
                stimulus.terminate();stimulus.wait(timeout=5)
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
    if len(sys.argv) >= 3 and sys.argv[1] == '--fake-capture': fake_capture(Path(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == '--fake-playback': fake_playback(Path(sys.argv[2]))
    else: main()
