#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in local neural VAD review with supplied synthetic 16 kHz speech.

No microphone, speaker, network, account or device writes. Run with a matching
native moto-vad build and its hash-verified model, on Linux or the target CPU.
"""
import argparse
import array
import hashlib
import json
from pathlib import Path
import select
import struct
import subprocess
import sys
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--speech-wav', type=Path, required=True)
    args = parser.parse_args()
    assert hashlib.sha256(args.model.read_bytes()).hexdigest() == '2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987'
    with wave.open(str(args.speech_wav), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1,2,16000)
        speech = wav.readframes(wav.getnframes())
    assert sys.byteorder == 'little'
    process = subprocess.Popen([str(args.binary.resolve()),'--model',str(args.model.resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def receive():
        assert select.select([process.stdout],[],[],15)[0], 'Neural VAD did not reply'
        return json.loads(process.stdout.readline(8193))
    try:
        assert receive() == {'ready':True}
        noise = array.array('h', (24 if i % 2 else -24 for i in range(32000))).tobytes()
        for pcm, expected in ((bytes(64000),False),(noise,False),(speech,True),(bytes(64000),False)):
            process.stdin.write(struct.pack('<I',len(pcm)//2)+pcm);process.stdin.flush()
            decision = receive()
            assert set(decision) == {'accepted','speech_ms','max_run_ms','milliseconds'}
            assert decision['accepted'] is expected, decision
            assert 0 <= decision['max_run_ms'] <= decision['speech_ms'] <= 51000
        process.stdin.close(); assert process.wait(timeout=5) == 0
        print('PASS: neural VAD rejects silence/noise, accepts known speech and resets between packets; no audio or transcript output.')
    finally:
        if process.poll() is None: process.kill();process.wait(timeout=5)


if __name__ == '__main__': main()
