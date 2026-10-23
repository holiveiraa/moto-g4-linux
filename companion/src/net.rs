// SPDX-License-Identifier: MIT
use crate::{auth, config::Config, protocol, storage, tailnet, Error, Result};
use reqwest::{
    blocking::{Client, Response},
    cookie::{CookieStore, Jar},
    redirect::Policy,
};
use serde_json::{json, Value};
use std::{
    io::{Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU8, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};
use tungstenite::{
    client::IntoClientRequest, stream::MaybeTlsStream, Connector, Message, WebSocket,
};
pub type Socket = WebSocket<MaybeTlsStream<TcpStream>>;
const NETWORK: Error =
    Error("Sem conexão autenticada com o Hermes. Confira a URL, o certificado e a sessão.");
pub const LOGIN: Error = Error("Entre com sua conta Umbrel neste aparelho.");
pub const TOTP: Error = Error("Digite o código de 2FA da sua conta Umbrel.");
pub const UNKNOWN: Error =
    Error("Resultado da tarefa incerto. Confira no Hermes antes de continuar; nada foi reenviado.");

#[derive(Clone)]
pub struct Backend {
    pub config: Config,
    client: Client,
    tailnet_client: Client,
    pub jar: Arc<Jar>,
    tls: Arc<rustls::ClientConfig>,
    pub directory: PathBuf,
}
impl Backend {
    pub fn new(config: Config, directory: &Path) -> Result<Self> {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let jar = Arc::new(Jar::default());
        let mut builder = Client::builder()
            .redirect(Policy::none())
            .cookie_provider(jar.clone())
            .no_proxy()
            .timeout(Duration::from_secs(20))
            .connect_timeout(Duration::from_secs(8))
            .user_agent("MotoHermes/0.1");
        let mut tailnet_builder = Client::builder()
            .redirect(Policy::none())
            .cookie_provider(jar.clone())
            .no_proxy()
            .timeout(Duration::from_secs(20))
            .connect_timeout(Duration::from_secs(8))
            .user_agent("MotoHermes/0.1")
            .interface(tailnet::INTERFACE);
        let mut roots = rustls::RootCertStore::empty();
        for cert in rustls_native_certs::load_native_certs().certs {
            let _ = roots.add(cert);
        }
        if let Some(path) = &config.ca_file {
            let data =
                std::fs::read(path).map_err(|_| Error("Não foi possível ler o certificado CA."))?;
            if data.len() > 1024 * 1024 {
                return Err(Error("Arquivo CA grande demais."));
            }
            let mut count = 0;
            for cert in rustls_pemfile::certs(&mut data.as_slice()) {
                let cert = cert.map_err(|_| Error("Certificado CA inválido."))?;
                let extra = reqwest::Certificate::from_der(cert.as_ref())
                    .map_err(|_| Error("Certificado CA inválido."))?;
                builder = builder.add_root_certificate(extra.clone());
                tailnet_builder = tailnet_builder.add_root_certificate(extra);
                roots
                    .add(cert)
                    .map_err(|_| Error("Certificado CA inválido."))?;
                count += 1;
            }
            if count == 0 {
                return Err(Error("O arquivo CA não contém certificados PEM."));
            }
        }
        if config.remember_session {
            if let Ok(saved) = storage::load(&directory.join("hermes-auth.json")) {
                if saved["binding"] == config.binding() {
                    if let Some(cookie) = saved["cookie"]
                        .as_str()
                        .filter(|s| s.len() < 8192 && !s.chars().any(char::is_control))
                    {
                        // The saved value is exactly one named app-gateway cookie, not a Set-Cookie header.
                        if cookie.starts_with("__Host-UMBREL_APP_SESSION_HTTPS=")
                            || cookie.starts_with("UMBREL_APP_SESSION=")
                        {
                            let secure = if config.url().scheme() == "https" {
                                "; Secure"
                            } else {
                                ""
                            };
                            jar.add_cookie_str(
                                &format!("{cookie}; Path=/; HttpOnly{secure}"),
                                &config.url(),
                            );
                        }
                    }
                }
            }
        }
        let tls = rustls::ClientConfig::builder()
            .with_root_certificates(roots)
            .with_no_client_auth();
        Ok(Self {
            config,
            client: builder.build().map_err(|_| NETWORK)?,
            tailnet_client: tailnet_builder.build().map_err(|_| NETWORK)?,
            jar,
            tls: Arc::new(tls),
            directory: directory.into(),
        })
    }
    fn client_for(&self, url: &url::Url) -> Result<&Client> {
        if tailnet::verify(url)?.is_some() {
            Ok(&self.tailnet_client)
        } else {
            Ok(&self.client)
        }
    }
    pub fn discover(&self) -> Result<String> {
        let response = self
            .client_for(&self.config.url())?
            .get(self.config.url())
            .send()
            .map_err(|_| NETWORK)?;
        if response.status().is_redirection() {
            return Err(LOGIN);
        }
        auth::dashboard_token(&body(response, protocol::MAX_FRAME)?)
    }
    pub fn login(&self, password: &str, totp: &str, alive: &AtomicBool) -> Result<String> {
        if password.is_empty() || password.len() > 4096 || totp.len() > 16 {
            return Err(Error("Confira a senha e o código de 2FA."));
        }
        let response = self
            .client_for(&self.config.url())?
            .get(self.config.url())
            .send()
            .map_err(|_| NETWORK)?;
        if !response.status().is_redirection() {
            return self.discover();
        }
        let redirect = response
            .headers()
            .get(reqwest::header::LOCATION)
            .and_then(|h| h.to_str().ok())
            .ok_or(NETWORK)?;
        let target = auth::login_target(&self.config, redirect)?;
        if !alive.load(Ordering::SeqCst) {
            return Err(Error("Operação cancelada."));
        }
        let response = self
            .client_for(&target)?
            .post(target)
            .json(&json!({"userId":self.config.user_id,"password":password,"totpToken":totp}))
            .send()
            .map_err(|_| NETWORK)?;
        if response.status() == 401 {
            let data: Value =
                serde_json::from_str(&body_unchecked(response, 8192)?).unwrap_or(Value::Null);
            return Err(
                if matches!(
                    data["error"]["message"].as_str(),
                    Some("Missing 2FA code" | "Incorrect 2FA code")
                ) {
                    TOTP
                } else {
                    Error("Senha Umbrel recusada. Confira e tente novamente.")
                },
            );
        }
        let value: Value = serde_json::from_str(&body(response, 16384)?).map_err(|_| NETWORK)?;
        let (url, r, handoff) = auth::validate_handoff(&self.config, &value)?;
        if !alive.load(Ordering::SeqCst) {
            return Err(Error("Operação cancelada."));
        }
        let response = self
            .client_for(&url)?
            .post(url)
            .form(&[("r", r), ("handoff", handoff)])
            .send()
            .map_err(|_| NETWORK)?;
        if !response.status().is_redirection() {
            return Err(NETWORK);
        }
        let location = response
            .headers()
            .get(reqwest::header::LOCATION)
            .and_then(|h| h.to_str().ok())
            .ok_or(NETWORK)?;
        let returned = self.config.url().join(location).map_err(|_| NETWORK)?;
        if returned.origin() != self.config.url().origin() || !returned.username().is_empty() {
            return Err(NETWORK);
        }
        self.discover()
    }
    pub fn remember(&self) -> Result<()> {
        if !self.config.remember_session {
            return Ok(());
        }
        if let Some(header) = self.jar.cookies(&self.config.url()) {
            let raw = header.to_str().map_err(|_| NETWORK)?;
            let name = if self.config.url().scheme() == "https" {
                "__Host-UMBREL_APP_SESSION_HTTPS="
            } else {
                "UMBREL_APP_SESSION="
            };
            if let Some(cookie) = raw.split(';').map(str::trim).find(|s| s.starts_with(name)) {
                storage::save(
                    &self.directory.join("hermes-auth.json"),
                    &json!({"binding":self.config.binding(),"cookie":cookie}),
                )?;
            }
        }
        Ok(())
    }
    pub fn socket(&self, route: &str, token: &str) -> Result<Socket> {
        let origin = self.config.url();
        let private_ip = tailnet::verify(&origin)?;
        let mut url = self.config.route(route);
        url.query_pairs_mut().append_pair("token", token);
        let scheme = if origin.scheme() == "https" {
            "wss"
        } else {
            "ws"
        };
        url.set_scheme(scheme).map_err(|_| NETWORK)?;
        let mut request = url.as_str().into_client_request().map_err(|_| NETWORK)?;
        if let Some(cookie) = self.jar.cookies(&origin) {
            request.headers_mut().insert("Cookie", cookie);
        }
        request.headers_mut().insert(
            "Origin",
            origin
                .origin()
                .ascii_serialization()
                .parse()
                .map_err(|_| NETWORK)?,
        );
        let mut connected = None;
        for address in origin
            .socket_addrs(|| None)
            .map_err(|_| NETWORK)?
            .into_iter()
            .take(8)
        {
            let attempt = if let Some(ip) = private_ip {
                if address.ip() != ip {
                    return Err(tailnet::REQUIRED);
                }
                tailnet::connect_bound(address)
            } else {
                TcpStream::connect_timeout(&address, Duration::from_secs(5)).map_err(|_| NETWORK)
            };
            if let Ok(stream) = attempt {
                connected = Some(stream);
                break;
            }
        }
        let stream = connected.ok_or(NETWORK)?;
        stream
            .set_read_timeout(Some(Duration::from_secs(8)))
            .map_err(|_| NETWORK)?;
        stream
            .set_write_timeout(Some(Duration::from_secs(5)))
            .map_err(|_| NETWORK)?;
        let cfg = tungstenite::protocol::WebSocketConfig::default()
            .max_message_size(Some(protocol::MAX_FRAME))
            .max_frame_size(Some(protocol::MAX_FRAME));
        let (mut ws, _) = tungstenite::client_tls_with_config(
            request,
            stream,
            Some(cfg),
            Some(Connector::Rustls(self.tls.clone())),
        )
        .map_err(|_| NETWORK)?;
        set_timeout(&mut ws, Duration::from_millis(250))?;
        Ok(ws)
    }
    pub fn transcribe(&self, path: &Path, groq: &Path) -> Result<String> {
        let data = recording(path)?;
        let secret = storage::load(groq)?;
        let key = secret["api_key"]
            .as_str()
            .filter(|k| {
                k.len() >= 20
                    && k.len() <= 256
                    && k.bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
            })
            .ok_or(Error("Configure sua chave Groq em Voz e áudio."))?;
        let form = reqwest::blocking::multipart::Form::new()
            .text("model", "whisper-large-v3-turbo")
            .text("language", "pt")
            .text("response_format", "json")
            .part(
                "file",
                reqwest::blocking::multipart::Part::bytes(data)
                    .file_name("voice.wav")
                    .mime_str("audio/wav")
                    .map_err(|_| NETWORK)?,
            );
        // A separate client has no Umbrel cookies, custom CA, proxy or redirected credentials.
        let client = Client::builder()
            .redirect(Policy::none())
            .no_proxy()
            .timeout(Duration::from_secs(60))
            .build()
            .map_err(|_| NETWORK)?;
        let response = client
            .post("https://api.groq.com/openai/v1/audio/transcriptions")
            .bearer_auth(key)
            .multipart(form)
            .send()
            .map_err(|_| Error("Groq indisponível; grave novamente quando conectar."))?;
        if !response.status().is_success() {
            return Err(Error(
                "A Groq recusou a transcrição; confira sua chave e limites.",
            ));
        }
        let value: Value = serde_json::from_str(&body(response, 131072)?)
            .map_err(|_| Error("Resposta da Groq inválida."))?;
        let text = value["text"].as_str().unwrap_or("").trim();
        if text.is_empty() || text.chars().count() > protocol::MAX_TEXT {
            return Err(Error("Nenhuma fala reconhecida. Grave novamente."));
        }
        Ok(text.into())
    }
    pub fn require_edge(&self, token: &str) -> Result<()> {
        // This response can contain keys for OTHER providers: never log, persist
        // or forward it. The inspected v0.22.4 relay verdict identifies Edge.
        let response = self
            .client_for(&self.config.route("/api/audio/voice-config"))?
            .get(self.config.route("/api/audio/voice-config"))
            .bearer_auth(token)
            .send()
            .map_err(|_| NETWORK)?;
        let value: Value = serde_json::from_str(&body(response, 65536)?).map_err(|_| NETWORK)?;
        if value["ok"] == true
            && value["tts"]["mode"] == "relay"
            && value["tts"]["reason"] == "provider 'edge' has no client wire"
        {
            Ok(())
        } else {
            Err(Error("Não foi possível confirmar Edge TTS neste perfil. Confira o provedor e voice.client_direct no Hermes; a resposta continua em texto."))
        }
    }
}
fn body_unchecked(mut response: Response, max: usize) -> Result<String> {
    let mut data = Vec::new();
    response
        .by_ref()
        .take(max as u64 + 1)
        .read_to_end(&mut data)
        .map_err(|_| NETWORK)?;
    if data.len() > max {
        return Err(Error("Resposta do servidor grande demais."));
    }
    String::from_utf8(data).map_err(|_| NETWORK)
}
fn body(response: Response, max: usize) -> Result<String> {
    if !response.status().is_success() {
        return Err(if matches!(response.status().as_u16(), 401 | 403) {
            LOGIN
        } else {
            NETWORK
        });
    }
    body_unchecked(response, max)
}
pub fn set_timeout(ws: &mut Socket, timeout: Duration) -> Result<()> {
    let stream = match ws.get_mut() {
        MaybeTlsStream::Plain(s) => s,
        MaybeTlsStream::Rustls(s) => &mut s.sock,
        _ => return Err(NETWORK),
    };
    stream.set_read_timeout(Some(timeout)).map_err(|_| NETWORK)
}
pub fn send(ws: &mut Socket, value: Value) -> Result<()> {
    ws.send(Message::Text(value.to_string().into()))
        .map_err(|_| NETWORK)
}
pub fn receive(ws: &mut Socket) -> Result<Option<Message>> {
    match ws.read() {
        Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => Ok(None),
        Ok(Message::Close(_)) => Err(NETWORK),
        Ok(frame) => Ok(Some(frame)),
        Err(tungstenite::Error::Io(e))
            if matches!(
                e.kind(),
                std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
            ) =>
        {
            Ok(None)
        }
        Err(_) => Err(NETWORK),
    }
}
pub fn call(ws: &mut Socket, method: &str, params: Value, alive: &AtomicBool) -> Result<Value> {
    let id = storage::id()?;
    send(ws, protocol::rpc(&id, method, params))?;
    let deadline = Instant::now() + Duration::from_secs(40);
    while Instant::now() < deadline && alive.load(Ordering::SeqCst) {
        if let Some(Message::Text(data)) = receive(ws)? {
            for value in protocol::frames(&data)? {
                if value["id"] == id {
                    if value.get("error").is_some() {
                        return Err(Error(
                            "O Hermes recusou esta operação. Confira a versão e o perfil.",
                        ));
                    }
                    return Ok(value["result"].clone());
                }
            }
        }
    }
    Err(Error("Tempo de resposta do Hermes esgotado."))
}
pub fn recording(path: &Path) -> Result<Vec<u8>> {
    use std::{fs::OpenOptions, os::unix::fs::OpenOptionsExt};
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|_| Error("Gravação indisponível."))?;
    let mut data = Vec::new();
    Read::by_ref(&mut file)
        .take(7 * 1024 * 1024 + 1)
        .read_to_end(&mut data)
        .map_err(|_| Error("Gravação inválida."))?;
    if data.len() > 7 * 1024 * 1024
        || data.len() < 44
        || &data[..4] != b"RIFF"
        || &data[8..12] != b"WAVE"
    {
        return Err(Error("Gravação WAV inválida ou grande demais."));
    }
    let mut pos = 12;
    let mut format = None;
    let mut samples = 0;
    while pos + 8 <= data.len() {
        let len = u32::from_le_bytes(data[pos + 4..pos + 8].try_into().unwrap()) as usize;
        let start = pos + 8;
        let end = start
            .checked_add(len)
            .filter(|n| *n <= data.len())
            .ok_or(Error("Gravação WAV truncada."))?;
        if &data[pos..pos + 4] == b"fmt " && len >= 16 {
            let encoding = u16::from_le_bytes(data[start..start + 2].try_into().unwrap());
            let channels = u16::from_le_bytes(data[start + 2..start + 4].try_into().unwrap());
            let rate = u32::from_le_bytes(data[start + 4..start + 8].try_into().unwrap());
            let bits = u16::from_le_bytes(data[start + 14..start + 16].try_into().unwrap());
            if encoding != 1
                || !(1..=2).contains(&channels)
                || bits != 16
                || !(8000..=48000).contains(&rate)
            {
                return Err(Error("Formato da gravação incompatível."));
            }
            format = Some((rate, channels));
        }
        if &data[pos..pos + 4] == b"data" {
            samples = len;
        }
        pos = end + len % 2;
    }
    let (rate, channels) = format.ok_or(Error("Gravação sem formato PCM."))?;
    let duration = samples as f64 / (rate as f64 * channels as f64 * 2.);
    if !(0.25..=61.).contains(&duration) {
        return Err(Error("Gravação muito curta ou longa."));
    }
    Ok(data)
}

pub fn speech(
    backend: &Backend,
    token: &str,
    text: &str,
    stop: &AtomicU8,
    alive: &AtomicBool,
) -> Result<()> {
    use std::{
        os::unix::{io::AsRawFd, process::CommandExt},
        process::{Command, Stdio},
    };
    backend.require_edge(token)?;
    if !alive.load(Ordering::SeqCst) || stop.load(Ordering::SeqCst) != 0 {
        return Ok(());
    }
    let mut ws = backend.socket("/api/audio/speak-stream", token)?;
    send(&mut ws, json!({"text":text,"done":true}))?;
    let mut player: Option<std::process::Child> = None;
    let mut received = 0usize;
    let deadline = Instant::now() + Duration::from_secs(180);
    let mut result = (|| {
        while Instant::now() < deadline
            && alive.load(Ordering::SeqCst)
            && stop.load(Ordering::SeqCst) == 0
        {
            match receive(&mut ws)? {
                Some(Message::Text(data)) => {
                    let value: Value = serde_json::from_str(&data)
                        .map_err(|_| Error("Metadados de voz inválidos."))?;
                    match value["type"].as_str() {
                        Some("start") if player.is_none() => {
                            let rate = protocol::pcm_start(&value)?;
                            let mut cmd = Command::new("aplay");
                            cmd.args(["-q", "-D", "default", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", &rate.to_string()]).stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null());
                            // No orphan speaker if the application process is killed.
                            unsafe {
                                cmd.pre_exec(|| {
                                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                                        return Err(std::io::Error::last_os_error());
                                    }
                                    if libc::getppid() == 1 {
                                        return Err(std::io::Error::other("parent exited"));
                                    }
                                    Ok(())
                                });
                            }
                            player = Some(cmd.spawn().map_err(|_| Error("Reprodução indisponível: instale alsa-utils."))?);
                            let fd = player.as_ref().and_then(|child| child.stdin.as_ref()).ok_or(Error("Saída de áudio indisponível."))?.as_raw_fd();
                            unsafe { let flags = libc::fcntl(fd, libc::F_GETFL); if flags < 0 || libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) < 0 { return Err(Error("Não foi possível limitar a reprodução.")); } }
                        }
                        Some("end") => return if received > 0 { Ok(()) } else { Err(Error("O provedor não produziu áudio.")) },
                        _ => return Err(Error("Voz indisponível; a resposta continua em texto. Confira o provedor Edge no Hermes.")),
                    }
                }
                Some(Message::Binary(data)) => {
                    protocol::validate_pcm(&data)?;
                    received += data.len();
                    if received > 24 * 1024 * 1024 {
                        return Err(Error("Resposta de áudio longa demais."));
                    }
                    let output = player
                        .as_mut()
                        .and_then(|p| p.stdin.as_mut())
                        .ok_or(Error("Áudio chegou sem formato."))?;
                    let mut left = data.as_ref();
                    while !left.is_empty() {
                        if !alive.load(Ordering::SeqCst) || stop.load(Ordering::SeqCst) != 0 {
                            return Ok(());
                        }
                        if Instant::now() >= deadline {
                            return Err(Error("Tempo de voz esgotado."));
                        }
                        match output.write(left) {
                            Ok(0) => return Err(Error("Reprodução encerrada.")),
                            Ok(n) => left = &left[n..],
                            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                                std::thread::sleep(Duration::from_millis(10))
                            }
                            Err(_) => return Err(Error("Não foi possível tocar o áudio.")),
                        }
                    }
                }
                _ => (),
            }
        }
        if stop.load(Ordering::SeqCst) == 0 && alive.load(Ordering::SeqCst) {
            Err(Error("Tempo de voz esgotado."))
        } else {
            Ok(())
        }
    })();
    let _ = send(&mut ws, json!({"stop":true}));
    if let Some(mut child) = player {
        drop(child.stdin.take());
        let drain = Instant::now() + Duration::from_secs(3);
        let mut exited = false;
        while result.is_ok()
            && stop.load(Ordering::SeqCst) == 0
            && alive.load(Ordering::SeqCst)
            && Instant::now() < drain
        {
            match child.try_wait() {
                Ok(Some(status)) => {
                    exited = true;
                    if !status.success() {
                        result = Err(Error("O reprodutor de áudio falhou. Confira a saída ALSA."));
                    }
                    break;
                }
                Ok(None) => (),
                Err(_) => {
                    result = Err(Error("Não foi possível confirmar a reprodução."));
                    break;
                }
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        if result.is_ok()
            && !exited
            && alive.load(Ordering::SeqCst)
            && stop.load(Ordering::SeqCst) == 0
        {
            result = Err(Error("A saída de áudio não concluiu a reprodução."));
        }
        let _ = child.kill();
        let _ = child.wait();
    }
    result
}
