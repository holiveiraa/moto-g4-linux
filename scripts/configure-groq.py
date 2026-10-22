#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Temporary loopback-only browser form; send key to Moto over pinned SSH stdin.

No account credentials in URLs, argv, logs or browser storage. The URL contains
only a random local form nonce. Run on the USB maintenance PC, not the phone.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
from pathlib import Path
import secrets
import re
import subprocess
import time
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
NONCE = secrets.token_urlsafe(32)
PAGE = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moto Linux · configurar Groq</title>
<style>body{background:#0b111b;color:#eef4ff;font:18px system-ui;margin:8vh auto;padding:24px;max-width:620px}
h1{color:#56dfb1}input,button{font:inherit;box-sizing:border-box;padding:16px;width:100%;margin:12px 0;border-radius:10px;border:1px solid #415469}
input{background:#121d2b;color:#fff}button{background:#56dfb1;color:#0b111b;cursor:pointer}small{color:#a9bbd0}a{color:#56dfb1}</style>
<h1>Ditado no Moto Linux</h1><p>Cole sua chave API da Groq. Ela será salva no Moto pelo USB, usando SSH.</p>
<form method="post" autocomplete="off"><input type="hidden" name="nonce" value="__NONCE__">
<label for="key">Chave API Groq</label><input id="key" name="api_key" type="password" autocomplete="off" required minlength="20" maxlength="256" autofocus>
<button>Salvar chave no Moto</button></form><small>Este formulário é temporário e funciona só neste PC.
A chave não é enviada a este chat. Para validar com a Groq, use “Testar conexão” no painel do Moto.</small></html>'''


class Form(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body):
        raw = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def valid(self):
        return self.path == '/' + NONCE and self.headers.get('Host') == self.server.host_header

    def do_GET(self):
        self.respond(200, PAGE.replace('__NONCE__', NONCE)) if self.valid() else self.respond(404, 'Página indisponível.')

    def do_POST(self):
        # Embedded webviews can submit an opaque Origin. The unguessable route
        # and body nonce remain mandatory, and the server is loopback-only.
        if not self.valid() or self.headers.get('Origin') not in (None, 'null', 'http://' + self.server.host_header):
            return self.respond(403, 'Origem inválida.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError()
            data = parse_qs(self.rfile.read(length).decode(), strict_parsing=True)
            if not secrets.compare_digest(data.get('nonce', [''])[0], NONCE):
                raise ValueError()
            key = data['api_key'][0].strip()
            if not 20 <= len(key) <= 256 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in key):
                raise ValueError()
            private = ROOT / '.private'
            args = ['ssh', '-i', str(private/'device-debug-ed25519'), '-o', 'IdentitiesOnly=yes',
                    '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(private/'device-known-hosts'),
                    '-o', 'ConnectTimeout=8', 'root@172.16.42.1', 'python3 /usr/sbin/moto-voice.py save-key-stdin']
            result = subprocess.run(args, input=json.dumps({'api_key': key}).encode(), capture_output=True, timeout=15)
            if result.returncode:
                return self.respond(503, '<h1>Moto não respondeu</h1><p>Confira o USB e tente novamente. A chave não foi registrada neste PC.</p>')
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
            return self.respond(400, '<h1>Não foi possível salvar</h1><p>Confira a chave e a conexão USB. Volte para tentar novamente.</p>')
        self.server.saved = True
        self.respond(200, '<meta charset="utf-8"><title>Chave salva</title><h1>Chave salva no Moto.</h1><p>No aparelho: Painel → Voz, ditado e áudio → Configurar Groq → Testar conexão.</p><p>Você pode fechar esta página.</p>')
        print('Chave salva no Moto; formulário encerrado.', flush=True)


def main():
    global NONCE
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--nonce', default=NONCE)
    options = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,80}', options.nonce):
        raise SystemExit('Invalid form nonce')
    NONCE = options.nonce
    server = HTTPServer(('127.0.0.1', options.port), Form)
    server.host_header = '127.0.0.1:%d' % server.server_port
    server.timeout, server.saved = 1, False
    print('http://' + server.host_header + '/' + NONCE, flush=True)
    deadline = time.monotonic() + 900
    try:
        while time.monotonic() < deadline and not server.saved:
            server.handle_request()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
