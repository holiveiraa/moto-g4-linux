// SPDX-License-Identifier: MIT
//! Separate local-only process: ALSA -> VAD -> local wake recognition.
//! Only a post-wake utterance produces a private WAV event for the GUI. No
//! Backend, HTTP client, API keys or cloud fallback are constructed here.
use crate::{
    hearing::{self, Segmenter, FRAME_SAMPLES},
    storage, Error, Result,
};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{BufRead, Read, Write},
    os::unix::{
        fs::{MetadataExt, OpenOptionsExt},
        io::AsRawFd,
        process::CommandExt,
    },
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

const MODEL: &str = "/usr/local/share/moto-hermes/ggml-tiny-q5_1.bin";
const MODEL_SHA: &str = "818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7";
const LOCAL: Error = Error("Ativação local indisponível. Confira o modelo e o componente moto-wake; nenhum áudio foi enviado.");
type Emit = Arc<dyn Fn(Value) + Send + Sync>;
#[derive(Clone, Copy, PartialEq, Eq)]
enum Mode {
    Paused,
    Wake,
    Conversation,
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Desired {
    mode: Mode,
    epoch: u64,
}
struct Control {
    desired: Desired,
    awake: bool,
    alive: bool,
}
type Shared = Arc<Mutex<Control>>;
fn current(c: &Shared, d: Desired) -> bool {
    c.lock().is_ok_and(|s| s.alive && s.desired == d)
}
fn nonblocking(fd: i32) -> Result<()> {
    unsafe {
        let flags = libc::fcntl(fd, libc::F_GETFL);
        if flags < 0 || libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) < 0 {
            return Err(LOCAL);
        }
    }
    Ok(())
}
struct Process {
    child: Child,
    input: Option<ChildStdin>,
    output: ChildStdout,
    pending: Vec<u8>,
}
impl Process {
    fn spawn(mut command: Command, lease: Option<i32>) -> Result<Self> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 || libc::getppid() == 1 {
                    return Err(std::io::Error::other("parent exited"));
                }
                if let Some(fd) = lease {
                    if libc::fcntl(fd, libc::F_SETFD, 0) < 0 {
                        return Err(std::io::Error::last_os_error());
                    }
                }
                Ok(())
            });
        }
        let mut child = command.spawn().map_err(|_| LOCAL)?;
        let input = child.stdin.take();
        let output = child.stdout.take().ok_or(LOCAL)?;
        let process = Self {
            child,
            input,
            output,
            pending: Vec::new(),
        };
        nonblocking(process.output.as_raw_fd())?;
        if let Some(input) = &process.input {
            nonblocking(input.as_raw_fd())?;
        }
        Ok(process)
    }
    fn line(&mut self, control: &Shared, desired: Desired, seconds: u64) -> Result<Value> {
        let deadline = Instant::now() + Duration::from_secs(seconds);
        while current(control, desired) && Instant::now() < deadline {
            if let Some(end) = self.pending.iter().position(|b| *b == b'\n') {
                let line: Vec<_> = self.pending.drain(..=end).collect();
                return serde_json::from_slice(&line).map_err(|_| LOCAL);
            }
            let mut buf = [0; 2048];
            match self.output.read(&mut buf) {
                Ok(0) => return Err(LOCAL),
                Ok(n) => {
                    self.pending.extend_from_slice(&buf[..n]);
                    if self.pending.len() > 8192 {
                        return Err(LOCAL);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(10))
                }
                Err(_) => return Err(LOCAL),
            }
        }
        Err(LOCAL)
    }
    fn decode(&mut self, audio: &[i16], control: &Shared, desired: Desired) -> Result<Value> {
        let down = hearing::wake_pcm(audio);
        let mut packet = (down.len() as u32).to_le_bytes().to_vec();
        for s in down {
            packet.extend(s.to_le_bytes());
        }
        let mut rest = packet.as_slice();
        let deadline = Instant::now() + Duration::from_secs(15);
        while !rest.is_empty() && current(control, desired) && Instant::now() < deadline {
            match self.input.as_mut().ok_or(LOCAL)?.write(rest) {
                Ok(0) => return Err(LOCAL),
                Ok(n) => rest = &rest[n..],
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(10))
                }
                Err(_) => return Err(LOCAL),
            }
        }
        if !rest.is_empty() {
            return Err(LOCAL);
        }
        self.line(control, desired, 25)
    }
}
impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
struct Capture {
    process: Process,
    _lease: File,
}
impl Capture {
    fn new(device: &str) -> Result<Self> {
        let lease = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/run/moto-capture.lock")
            .map_err(|_| Error("Microfone em uso ou indisponível."))?;
        let info = lease.metadata().map_err(|_| LOCAL)?;
        if !info.is_file() || info.uid() != unsafe { libc::geteuid() } || info.mode() & 0o077 != 0 {
            return Err(LOCAL);
        }
        if unsafe { libc::flock(lease.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(Error("Microfone em uso; termine o outro ditado."));
        }
        let mut cmd = Command::new("arecord");
        cmd.args([
            "-q", "-D", device, "-t", "raw", "-f", "S16_LE", "-r", "48000", "-c", "1",
        ]);
        let process = Process::spawn(cmd, Some(lease.as_raw_fd()))?;
        Ok(Self {
            process,
            _lease: lease,
        })
    }
}
struct Private(PathBuf);
impl Private {
    fn new() -> Result<Self> {
        // /run is volatile on the supported installation. Never honor TMPDIR.
        let path = PathBuf::from("/run").join(format!(
            "moto-hermes-listen-{}-{}",
            std::process::id(),
            storage::id()?
        ));
        std::os::unix::fs::DirBuilderExt::mode(&mut fs::DirBuilder::new(), 0o700)
            .create(&path)
            .map_err(|_| LOCAL)?;
        Ok(Self(path))
    }
    fn wav(&self, audio: &[i16]) -> Result<PathBuf> {
        let path = self.0.join("utterance.wav");
        let bytes = (audio.len() * 2) as u32;
        let mut f = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .custom_flags(libc::O_NOFOLLOW)
            .mode(0o600)
            .open(&path)
            .map_err(|_| LOCAL)?;
        let mut data = b"RIFF".to_vec();
        data.extend((bytes + 36).to_le_bytes());
        data.extend(b"WAVEfmt ");
        data.extend(16u32.to_le_bytes());
        data.extend(1u16.to_le_bytes());
        data.extend(1u16.to_le_bytes());
        data.extend(48000u32.to_le_bytes());
        data.extend(96000u32.to_le_bytes());
        data.extend(2u16.to_le_bytes());
        data.extend(16u16.to_le_bytes());
        data.extend(b"data");
        data.extend(bytes.to_le_bytes());
        for sample in audio {
            data.extend(sample.to_le_bytes());
        }
        f.write_all(&data).map_err(|_| LOCAL)?;
        Ok(path)
    }
    fn clear(&self) {
        let _ = fs::remove_file(self.0.join("utterance.wav"));
    }
}
impl Drop for Private {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn helper(control: &Shared, desired: Desired) -> Result<Process> {
    let metadata = fs::metadata(MODEL).map_err(|_| LOCAL)?;
    if !metadata.is_file() || metadata.len() > 40 * 1024 * 1024 {
        return Err(LOCAL);
    }
    let check = Command::new("sha256sum")
        .arg(MODEL)
        .stderr(Stdio::null())
        .output()
        .map_err(|_| LOCAL)?;
    if !check.status.success() || !String::from_utf8_lossy(&check.stdout).starts_with(MODEL_SHA) {
        return Err(LOCAL);
    }
    let mut cmd = Command::new("/usr/local/bin/moto-wake");
    cmd.args(["--model", MODEL]);
    let mut process = Process::spawn(cmd, None)?;
    if process.line(control, desired, 25)?["ready"] != true {
        return Err(LOCAL);
    }
    Ok(process)
}
fn segment(
    input: &mut Capture,
    control: &Shared,
    desired: Desired,
    alive: &AtomicBool,
    seconds: usize,
) -> Result<Option<Vec<i16>>> {
    let mut vad = Segmenter::new(seconds);
    let mut buf = [0u8; 8192];
    while alive.load(Ordering::SeqCst) && current(control, desired) {
        if input.process.pending.len() < FRAME_SAMPLES * 2 {
            match input.process.output.read(&mut buf) {
                Ok(0) => return Err(Error("A captura do microfone foi encerrada.")),
                Ok(n) => input.process.pending.extend_from_slice(&buf[..n]),
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(10));
                    continue;
                }
                Err(_) => return Err(LOCAL),
            }
        }
        while input.process.pending.len() >= FRAME_SAMPLES * 2 {
            let bytes: Vec<_> = input.process.pending.drain(..FRAME_SAMPLES * 2).collect();
            let samples: Vec<_> = bytes
                .as_chunks::<2>()
                .0
                .iter()
                .map(|b| i16::from_le_bytes([b[0], b[1]]))
                .collect();
            if let Some(audio) = vad.feed(&samples) {
                return Ok(Some(audio));
            }
        }
    }
    Ok(None)
}
struct WakeCapture {
    alive: Arc<AtomicBool>,
    latest: Arc<Mutex<Option<Vec<i16>>>>,
    error: Arc<Mutex<Option<Error>>>,
    thread: Option<thread::JoinHandle<()>>,
}
impl WakeCapture {
    fn new(device: &str, control: &Shared, desired: Desired) -> Self {
        let alive = Arc::new(AtomicBool::new(true));
        let latest = Arc::new(Mutex::new(None));
        let error = Arc::new(Mutex::new(None));
        let a = alive.clone();
        let l = latest.clone();
        let e = error.clone();
        let c = control.clone();
        let device = device.to_string();
        let worker = thread::spawn(move || {
            let result = (|| {
                let mut input = Capture::new(&device)?;
                while let Some(audio) = segment(&mut input, &c, desired, &a, 5)? {
                    // One latest candidate only; replace old audio while inference runs.
                    *l.lock().map_err(|_| LOCAL)? = Some(audio);
                }
                Ok::<_, Error>(())
            })();
            if let Err(error) = result {
                if let Ok(mut slot) = e.lock() {
                    *slot = Some(error);
                }
            }
        });
        Self {
            alive,
            latest,
            error,
            thread: Some(worker),
        }
    }
}
impl Drop for WakeCapture {
    fn drop(&mut self) {
        self.alive.store(false, Ordering::SeqCst);
        if let Some(worker) = self.thread.take() {
            let _ = worker.join();
        }
    }
}
fn capture_turn(
    device: &str,
    control: &Shared,
    desired: Desired,
    wake: &mut Option<Process>,
    private: &Private,
    emit: &Emit,
) -> Result<()> {
    private.clear();
    if desired.mode == Mode::Wake {
        if wake.is_none() {
            *wake = Some(helper(control, desired)?);
        }
        if !current(control, desired) {
            return Ok(());
        }
        let capture = WakeCapture::new(device, control, desired);
        emit(json!({"event":"voice_listening","voice_epoch":desired.epoch,"mode":"wake"}));
        while current(control, desired) {
            if let Some(error) = capture.error.lock().map_err(|_| LOCAL)?.take() {
                return Err(error);
            }
            let audio = capture.latest.lock().map_err(|_| LOCAL)?.take();
            if let Some(audio) = audio {
                emit(json!({"event":"wake_checking","voice_epoch":desired.epoch}));
                let result = wake
                    .as_mut()
                    .ok_or(LOCAL)?
                    .decode(&audio, control, desired)?;
                if !current(control, desired) {
                    return Ok(());
                }
                emit(json!({"event":"wake_checked","voice_epoch":desired.epoch,
                    "decision":hearing::wake_diagnostic(&result, &audio)}));
                if hearing::valid_wake(&result) {
                    {
                        let mut c = control.lock().map_err(|_| LOCAL)?;
                        if !c.alive || c.desired != desired {
                            return Ok(());
                        }
                        c.awake = true;
                        c.desired.mode = Mode::Paused;
                    }
                    // Stop and join local capture BEFORE acknowledgment/playback.
                    drop(capture);
                    emit(json!({"event":"wake","voice_epoch":desired.epoch}));
                    return Ok(());
                }
                // A rejected candidate ends checking, not the listening turn.
                // Restore standby even if no further speech is detected.
                emit(json!({"event":"voice_listening","voice_epoch":desired.epoch,"mode":"wake"}));
            } else {
                thread::sleep(Duration::from_millis(10));
            }
        }
    } else {
        let mut input = Capture::new(device)?;
        emit(json!({"event":"voice_listening","voice_epoch":desired.epoch,"mode":"conversation"}));
        let audio = segment(&mut input, control, desired, &AtomicBool::new(true), 45)?;
        drop(input);
        if let Some(audio) = audio {
            let mut c = control.lock().map_err(|_| LOCAL)?;
            if c.alive && c.awake && c.desired == desired {
                let path = private.wav(&audio)?;
                c.desired.mode = Mode::Paused;
                emit(json!({"event":"utterance","voice_epoch":desired.epoch,"path":path}));
            }
        }
    }
    Ok(())
}
pub fn run(device: &str, emit: Emit) -> Result<()> {
    let tail = device.strip_prefix("hw:").ok_or(LOCAL)?;
    if tail.len() > 16
        || tail.split(',').count() != 2
        || tail
            .split(',')
            .any(|s| s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()))
    {
        return Err(LOCAL);
    }
    let private = Private::new()?;
    let shared = Arc::new(Mutex::new(Control {
        desired: Desired {
            mode: Mode::Paused,
            epoch: 0,
        },
        awake: false,
        alive: true,
    }));
    let control = shared.clone();
    let output = emit.clone();
    let device = device.to_string();
    let worker = thread::spawn(move || {
        let mut wake = None;
        loop {
            let state = match control.lock() {
                Ok(c) if c.alive => c.desired,
                _ => break,
            };
            if state.mode == Mode::Paused {
                thread::sleep(Duration::from_millis(15));
                continue;
            }
            if let Err(error) = capture_turn(&device, &control, state, &mut wake, &private, &output)
            {
                wake = None;
                if let Ok(mut c) = control.lock() {
                    if c.alive && c.desired == state {
                        c.desired.mode = Mode::Paused;
                        output(
                            json!({"event":"voice_error","voice_epoch":state.epoch,"text":error.0}),
                        );
                    }
                }
            }
        }
    });
    emit(json!({"event":"listener_ready"}));
    let mut stdin = std::io::stdin().lock();
    loop {
        let mut line = Vec::new();
        if stdin
            .by_ref()
            .take(8193)
            .read_until(b'\n', &mut line)
            .unwrap_or(0)
            == 0
            || line.len() > 8192
        {
            break;
        }
        let Ok(value) = serde_json::from_slice::<Value>(&line) else {
            continue;
        };
        let command = value["cmd"].as_str().unwrap_or("");
        if command == "close" {
            break;
        }
        let mut c = shared.lock().map_err(|_| LOCAL)?;
        let epoch = value["voice_epoch"].as_u64().unwrap_or(0);
        c.desired.epoch = epoch;
        match command {
            "wake" => {
                c.awake = false;
                c.desired.mode = Mode::Wake;
            }
            "conversation" if c.awake => c.desired.mode = Mode::Conversation,
            "pause" => c.desired.mode = Mode::Paused,
            _ => {
                c.desired.mode = Mode::Paused;
                emit(
                    json!({"event":"voice_error","voice_epoch":epoch,"text":"Aguardando ativação local por voz."}),
                );
            }
        }
    }
    if let Ok(mut c) = shared.lock() {
        c.alive = false;
    }
    let _ = worker.join();
    Ok(())
}
