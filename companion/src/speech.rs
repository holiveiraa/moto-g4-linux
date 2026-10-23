// SPDX-License-Identifier: MIT
//! Bounded speech pipeline. Reception/control stays live during paced playback.
use crate::{
    net::{self, Backend, Socket},
    protocol, storage, Error, Result,
};
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    io::Write,
    net::{Shutdown, TcpStream},
    os::unix::{io::AsRawFd, process::CommandExt},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU8, Ordering},
        Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tungstenite::{stream::MaybeTlsStream, Message};

const INPUT_CHARS: usize = 400;
const WRITE_CHUNK: usize = 65536;
const CANCELLED: Error = Error("VOICE_CANCELLED: Voz interrompida.");
const IDLE: Error = Error("VOICE_IDLE_TIMEOUT: A voz ficou 60 segundos sem um novo bloco ou escrita ALSA; a resposta continua em texto.");
const MEMORY: Error = Error("VOICE_SEGMENT_MEMORY: Um trecho de voz excedeu o orçamento de memória de 32 MiB; a resposta continua em texto.");

/// Split at Unicode boundaries, preferring whitespace. Concatenating the pieces
/// restores the exact input; there is no response truncation/duration ceiling.
pub fn pieces(text: &str) -> Vec<&str> {
    let mut result = Vec::new();
    let mut rest = text;
    while !rest.is_empty() {
        let Some((end, _)) = rest.char_indices().nth(INPUT_CHARS) else {
            result.push(rest);
            break;
        };
        let boundary = rest[..end]
            .char_indices()
            .rev()
            .find(|(at, c)| *at > 0 && c.is_whitespace())
            .map(|(at, c)| at + c.len_utf8())
            // Keep an unusually long unbroken token intact. The target size
            // must not change its pronunciation by splitting the word.
            .unwrap_or_else(|| {
                rest[end..]
                    .char_indices()
                    .find(|(_, c)| c.is_whitespace())
                    .map(|(at, c)| end + at + c.len_utf8())
                    .unwrap_or(rest.len())
            });
        result.push(&rest[..boundary]);
        rest = &rest[boundary..];
    }
    result
}

struct Buffer {
    pcm: VecDeque<u8>,
    rate: Option<u32>,
    done: bool,
    error: Option<Error>,
    progress: Instant,
    stats: protocol::SpeechMetrics,
}
impl Buffer {
    fn new() -> Self {
        Self {
            pcm: VecDeque::new(),
            rate: None,
            done: false,
            error: None,
            progress: Instant::now(),
            stats: protocol::SpeechMetrics::default(),
        }
    }
}

fn raw_socket(ws: &Socket) -> Result<TcpStream> {
    let stream = match ws.get_ref() {
        MaybeTlsStream::Plain(s) => s,
        MaybeTlsStream::Rustls(s) => &s.sock,
        _ => return Err(Error("VOICE_CONNECTION: Transporte de voz incompatível.")),
    };
    stream.try_clone().map_err(|_| {
        Error("VOICE_CONNECTION: Não foi possível preparar a interrupção da conexão de voz.")
    })
}

fn receive(mut ws: Socket, shared: &Mutex<Buffer>) -> Result<()> {
    loop {
        match ws.read() {
            Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => {
                // Tungstenite queues the matching Pong. Never wait for ALSA.
                ws.flush().map_err(|_| Error("VOICE_CONNECTION: Falha ao responder ao controle de voz."))?;
            }
            Ok(Message::Text(data)) => {
                if data.len() > protocol::SPEECH_CONTROL_BYTES {
                    return Err(Error("VOICE_CONTROL_LIMIT: Metadados de voz grandes demais."));
                }
                let value: Value = serde_json::from_str(&data)
                    .map_err(|_| Error("VOICE_METADATA: Metadados de voz inválidos."))?;
                let mut state = shared.lock().map_err(|_| Error("VOICE_STATE: Estado de voz indisponível."))?;
                match value["type"].as_str() {
                    Some("start") if state.rate.is_none() => {
                        let rate = state.stats.start(&value)?;
                        state.rate = Some(rate); state.progress = Instant::now();
                    }
                    Some("end") => {state.stats.finish()?; return Ok(());}
                    _ => return Err(Error("VOICE_PROTOCOL: O Hermes não confirmou uma sequência PCM compatível; a resposta continua em texto.")),
                }
            }
            Ok(Message::Binary(data)) => {
                let mut state = shared.lock().map_err(|_| Error("VOICE_STATE: Estado de voz indisponível."))?;
                state.stats.accept(&data)?;
                // Each request contains at most INPUT_CHARS. This is a RAM
                // guard for that request, never a limit on the complete reply.
                if state.stats.bytes > protocol::SPEECH_MESSAGE_MEMORY_BYTES as u64 {return Err(MEMORY);}
                state.pcm.extend(data.iter().copied());
                state.progress = Instant::now();
            }
            Ok(Message::Close(_)) => return Err(Error("VOICE_CONNECTION_CLOSED: A conexão de voz encerrou antes do fim.")),
            Ok(_) => (),
            Err(tungstenite::Error::Io(e)) if matches!(e.kind(),std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => (),
            Err(tungstenite::Error::Capacity(_)) => return Err(Error("VOICE_MESSAGE_MEMORY: Uma mensagem de voz excedeu o orçamento de memória de 32 MiB; a resposta continua em texto.")),
            Err(_) => return Err(Error("VOICE_CONNECTION: Falha na conexão de voz com o Hermes.")),
        }
    }
}

struct Player {
    child: Child,
    rate: u32,
    capacity: usize,
}
impl Player {
    fn new(rate: u32) -> Result<Self> {
        let mut cmd = Command::new("aplay");
        cmd.args([
            "-q",
            "-D",
            "default",
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            &rate.to_string(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
        unsafe {
            cmd.pre_exec(|| {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 || libc::getppid() == 1 {
                    return Err(std::io::Error::other("parent exited"));
                }
                Ok(())
            });
        }
        let child = cmd
            .spawn()
            .map_err(|_| Error("VOICE_PLAYER: Reprodução indisponível; confira alsa-utils."))?;
        let mut player = Self {
            child,
            rate,
            capacity: 65536,
        };
        let fd = player
            .child
            .stdin
            .as_ref()
            .ok_or(Error("VOICE_PLAYER: Saída ALSA indisponível."))?
            .as_raw_fd();
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
            return Err(Error(
                "VOICE_PLAYER: Não foi possível limitar a escrita ALSA.",
            ));
        }
        let capacity = unsafe { libc::fcntl(fd, libc::F_GETPIPE_SZ) };
        if capacity > 0 {
            player.capacity = capacity as usize;
        }
        Ok(player)
    }
    fn drain(&mut self, stop: &AtomicU8, alive: &AtomicBool) -> Result<()> {
        drop(self.child.stdin.take());
        let seconds = self.capacity.div_ceil(self.rate as usize * 2) as u64 + 2;
        let deadline = Instant::now() + Duration::from_secs(seconds);
        while Instant::now() < deadline {
            if stopped(stop, alive) {
                return Err(CANCELLED);
            }
            match self.child.try_wait() {
                Ok(Some(status)) if status.success() => return Ok(()),
                Ok(Some(_)) => {
                    return Err(Error(
                        "VOICE_PLAYER: O reprodutor de áudio falhou. Confira a saída ALSA.",
                    ))
                }
                Ok(None) => thread::sleep(Duration::from_millis(10)),
                Err(_) => {
                    return Err(Error(
                        "VOICE_PLAYER: Não foi possível confirmar a reprodução.",
                    ))
                }
            }
        }
        Err(Error(
            "VOICE_DRAIN_TIMEOUT: A saída ALSA não concluiu a reprodução no prazo do buffer.",
        ))
    }
}
impl Drop for Player {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn stopped(stop: &AtomicU8, alive: &AtomicBool) -> bool {
    stop.load(Ordering::SeqCst) != 0 || !alive.load(Ordering::SeqCst)
}

fn play(
    shared: &Mutex<Buffer>,
    player: &mut Option<Player>,
    stop: &AtomicU8,
    alive: &AtomicBool,
    phase: &mut &'static str,
) -> Result<()> {
    loop {
        if stopped(stop, alive) {
            return Err(CANCELLED);
        }
        let (rate, data, done) = {
            let mut state = shared
                .lock()
                .map_err(|_| Error("VOICE_STATE: Estado de voz indisponível."))?;
            if let Some(error) = state.error {
                *phase = "receiving";
                return Err(error);
            }
            if state.progress.elapsed() >= Duration::from_secs(protocol::SPEECH_PROGRESS_SECONDS) {
                return Err(IDLE);
            }
            let count = WRITE_CHUNK.min(state.pcm.len());
            (
                state.rate,
                state.pcm.drain(..count).collect::<Vec<_>>(),
                state.done,
            )
        };
        if let Some(rate) = rate {
            if player.is_none() {
                *player = Some(Player::new(rate)?);
            }
            if player.as_ref().is_some_and(|p| p.rate != rate) {
                return Err(Error("VOICE_FORMAT: A taxa PCM mudou entre trechos."));
            }
        }
        let mut left = data.as_slice();
        while !left.is_empty() {
            *phase = "playback";
            if stopped(stop, alive) {
                return Err(CANCELLED);
            }
            {
                let state = shared
                    .lock()
                    .map_err(|_| Error("VOICE_STATE: Estado de voz indisponível."))?;
                if let Some(error) = state.error {
                    *phase = "receiving";
                    return Err(error);
                }
                if state.progress.elapsed()
                    >= Duration::from_secs(protocol::SPEECH_PROGRESS_SECONDS)
                {
                    return Err(IDLE);
                }
            }
            let output = player
                .as_mut()
                .and_then(|p| p.child.stdin.as_mut())
                .ok_or(Error("VOICE_PROTOCOL: Áudio chegou sem formato."))?;
            match output.write(left) {
                Ok(0) => return Err(Error("VOICE_PLAYER: Reprodução encerrada.")),
                Ok(n) => {
                    left = &left[n..];
                    shared
                        .lock()
                        .map_err(|_| Error("VOICE_STATE: Estado de voz indisponível."))?
                        .progress = Instant::now();
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(10))
                }
                Err(_) => return Err(Error("VOICE_PLAYER: Não foi possível tocar o áudio.")),
            }
        }
        *phase = "receiving";
        if done && data.is_empty() {
            return Ok(());
        }
        if data.is_empty() {
            thread::sleep(Duration::from_millis(10));
        }
    }
}

fn segment(
    backend: &Backend,
    token: &str,
    text: &str,
    player: &mut Option<Player>,
    control: (&AtomicU8, &AtomicBool),
    stats: &mut protocol::SpeechMetrics,
    phase: &mut &'static str,
) -> Result<()> {
    let (stop, alive) = control;
    *phase = "opening";
    let mut ws = backend.speech_socket(token)?;
    let cancel = raw_socket(&ws)?;
    net::send(&mut ws, json!({"text":text,"done":true}))?;
    let shared = Mutex::new(Buffer::new());
    *phase = "receiving";
    let result = thread::scope(|scope| {
        let reader = scope.spawn(|| {
            let result = receive(ws, &shared);
            if let Ok(mut state) = shared.lock() {
                state.error = result.err();
                state.done = true;
            }
        });
        let result = play(&shared, player, stop, alive, phase);
        if result.is_err() {
            drop(player.take());
        }
        // This clone is independent of the parser lock. shutdown interrupts a
        // blocked TLS/TCP read, including an unfinished fragmented message.
        let _ = cancel.shutdown(Shutdown::Both);
        reader
            .join()
            .map_err(|_| Error("VOICE_STATE: A recepção de voz encerrou inesperadamente."))?;
        result
    });
    if let Ok(state) = shared.lock() {
        stats.rate = state.stats.rate.or(stats.rate);
        stats.bytes = stats.bytes.saturating_add(state.stats.bytes);
        stats.chunks = stats.chunks.saturating_add(state.stats.chunks);
        stats.largest_chunk = stats.largest_chunk.max(state.stats.largest_chunk);
    }
    result
}

pub fn run(
    backend: &Backend,
    token: &str,
    text: &str,
    stop: &AtomicU8,
    alive: &AtomicBool,
) -> Result<()> {
    let mut stats = protocol::SpeechMetrics::default();
    let mut phase = "provider";
    let mut player = None;
    let parts = pieces(text);
    let result = (|| {
        backend.require_edge(token)?;
        for piece in &parts {
            if stopped(stop, alive) {
                return Err(CANCELLED);
            }
            if piece.trim().is_empty() {
                continue;
            }
            segment(
                backend,
                token,
                piece,
                &mut player,
                (stop, alive),
                &mut stats,
                &mut phase,
            )?;
        }
        phase = "draining";
        player
            .as_mut()
            .ok_or(Error("VOICE_EMPTY: O provedor não produziu áudio."))?
            .drain(stop, alive)
    })();
    drop(player);
    let outcome = match result {
        Ok(()) => "completed",
        Err(CANCELLED) => "cancelled",
        Err(error) => error
            .0
            .split(':')
            .next()
            .filter(|s| s.starts_with("VOICE_"))
            .unwrap_or("client_error"),
    };
    let _ = storage::save(
        &backend.directory.join("hermes-speech-diagnostic.json"),
        &json!({
            "outcome":outcome,"phase":phase,"sample_rate":stats.rate,"bytes":stats.bytes,
            "chunks":stats.chunks,"largest_chunk":stats.largest_chunk,
            "segment_memory_bytes":protocol::SPEECH_MESSAGE_MEMORY_BYTES,"input_piece_chars":INPUT_CHARS,"pieces":parts.len(),
            "progress_timeout_seconds":protocol::SPEECH_PROGRESS_SECONDS,
        }),
    );
    if result == Err(CANCELLED) {
        Ok(())
    } else {
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn splitting_preserves_every_character_and_never_splits_utf8() {
        for text in [
            "á ç ô 🦀 ".repeat(500),
            "語🦀".repeat(900),
            "word ".repeat(500),
        ] {
            let parts = pieces(&text);
            assert_eq!(parts.concat(), text);
            assert!(parts.iter().all(|p| !p.is_empty()));
            assert!(parts
                .iter()
                .all(|p| p.chars().count() <= INPUT_CHARS
                    || !p.trim().chars().any(char::is_whitespace)));
        }
    }
}
