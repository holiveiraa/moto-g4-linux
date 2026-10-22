// SPDX-License-Identifier: MIT
//! Real HTTP/WebSocket fixture. No owner account, cloud API or device is contacted.
use moto_hermes::{
    config::Config,
    net::{self, Backend},
    storage,
};
use serde_json::{json, Value};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::{TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc, Arc,
    },
    thread,
    time::Duration,
};
use tungstenite::{
    handshake::server::{Request, Response},
    Message,
};

struct Fixture {
    base: String,
    stop: Arc<AtomicBool>,
    submits: Arc<AtomicUsize>,
    edge: Arc<AtomicBool>,
    creates: Arc<AtomicUsize>,
    fail_create: Arc<AtomicBool>,
    root: PathBuf,
    task: Option<thread::JoinHandle<()>>,
}
impl Fixture {
    fn new(drop_turn: bool, wait_cancel: bool) -> Self {
        Self::options(drop_turn, wait_cancel, true)
    }
    fn options(drop_turn: bool, wait_cancel: bool, require_totp: bool) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let base = format!("http://{}/", listener.local_addr().unwrap());
        let stop = Arc::new(AtomicBool::new(false));
        let submits = Arc::new(AtomicUsize::new(0));
        let edge = Arc::new(AtomicBool::new(true));
        let creates = Arc::new(AtomicUsize::new(0));
        let fail_create = Arc::new(AtomicBool::new(false));
        let root =
            std::env::temp_dir().join(format!("moto-hermes-gateway-{}", storage::id().unwrap()));
        fs::create_dir(&root).unwrap();
        let (stopper, count, url) = (stop.clone(), submits.clone(), base.clone());
        let provider = edge.clone();
        let sessions = creates.clone();
        let failing = fail_create.clone();
        let task = thread::spawn(move || {
            let mut children = Vec::new();
            while !stopper.load(Ordering::SeqCst) {
                match listener.accept() {
                    Ok((stream, _)) => {
                        let url = url.clone();
                        let count = count.clone();
                        let provider = provider.clone();
                        let sessions = sessions.clone();
                        let failing = failing.clone();
                        children.push(thread::spawn(move || {
                            serve(
                                stream,
                                &url,
                                count,
                                drop_turn,
                                wait_cancel,
                                require_totp,
                                provider,
                                sessions,
                                failing,
                            )
                        }));
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(5))
                    }
                    Err(_) => break,
                }
            }
            for child in children {
                let _ = child.join();
            }
        });
        Self {
            base,
            stop,
            submits,
            edge,
            creates,
            fail_create,
            root,
            task: Some(task),
        }
    }
    fn config(&self) -> Config {
        let mut config = Config::for_server(&self.base).unwrap();
        config.auth_origin = Some(self.base.clone());
        config
    }
    fn backend(&self) -> Backend {
        Backend::new(self.config(), &self.root).unwrap()
    }
    fn app(&self) -> App {
        storage::save(
            &self.root.join("hermes.json"),
            &serde_json::to_value(self.config()).unwrap(),
        )
        .unwrap();
        let tools = self.root.join("tools");
        fs::create_dir_all(&tools).unwrap();
        let aplay = tools.join("aplay");
        fs::write(&aplay, "#!/bin/sh\ncat > \"$MOTO_FIXTURE_AUDIO\"\n").unwrap();
        fs::set_permissions(aplay, fs::Permissions::from_mode(0o700)).unwrap();
        let binary = std::env::var_os("MOTO_HERMES_BINARY")
            .unwrap_or_else(|| env!("CARGO_BIN_EXE_moto-hermes").into());
        let mut child = Command::new(binary)
            .args([
                "--stdio",
                "--config",
                self.root.join("hermes.json").to_str().unwrap(),
            ])
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    tools.display(),
                    std::env::var("PATH").unwrap_or_default()
                ),
            )
            .env("MOTO_FIXTURE_AUDIO", self.root.join("pcm-received"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let output = child.stdout.take().unwrap();
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                if let Ok(line) = line {
                    if let Ok(value) = serde_json::from_str::<Value>(&line) {
                        if tx.send(value).is_err() {
                            break;
                        }
                    }
                } else {
                    break;
                }
            }
        });
        App { child, rx }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(task) = self.task.take() {
            task.join().unwrap();
        }
        fs::remove_dir_all(&self.root).unwrap();
    }
}
struct App {
    child: Child,
    rx: mpsc::Receiver<Value>,
}
impl App {
    fn send(&mut self, value: Value) {
        writeln!(self.child.stdin.as_mut().unwrap(), "{value}").unwrap();
        self.child.stdin.as_mut().unwrap().flush().unwrap();
    }
    fn event(&self, kind: &str) -> Value {
        for _ in 0..30 {
            let value = self
                .rx
                .recv_timeout(Duration::from_secs(5))
                .expect("fixture event deadline");
            if value["event"] == kind {
                return value;
            }
            assert!(
                value["event"] != "error",
                "unexpected fixture event: {value}"
            );
        }
        panic!("missing expected event {kind}");
    }
    fn login(&mut self) {
        self.event("ready");
        self.send(json!({"cmd":"login","password":"fixture-password","totp":"123456"}));
        assert_eq!(self.event("connected")["pending"], false);
    }
}
impl Drop for App {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn http(stream: &mut TcpStream, status: &str, headers: &str, body: &str) {
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n{headers}\r\n{body}",
        body.len()
    )
    .unwrap();
}
#[allow(clippy::too_many_arguments)] // Explicit independent fixture behaviors.
#[allow(clippy::result_large_err)] // tungstenite's server callback fixes this error type.
fn serve(
    mut stream: TcpStream,
    base: &str,
    count: Arc<AtomicUsize>,
    drop_turn: bool,
    wait_cancel: bool,
    require_totp: bool,
    edge: Arc<AtomicBool>,
    creates: Arc<AtomicUsize>,
    fail_create: Arc<AtomicBool>,
) {
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut peek = [0; 4096];
    let n = stream.peek(&mut peek).unwrap_or(0);
    let preview = String::from_utf8_lossy(&peek[..n]);
    if preview.contains("Upgrade: websocket") || preview.contains("upgrade: websocket") {
        let speech = preview.starts_with("GET /api/audio/speak-stream");
        let mut ws =
            match tungstenite::accept_hdr(stream, |request: &Request, response: Response| {
                assert!(request
                    .uri()
                    .query()
                    .unwrap_or("")
                    .contains("token=fixture-hermes-token"));
                assert!(request.headers()["cookie"]
                    .to_str()
                    .unwrap()
                    .contains("UMBREL_APP_SESSION=fixture-app-cookie"));
                Ok(response)
            }) {
                Ok(ws) => ws,
                Err(_) => return,
            };
        if speech {
            let _ = ws.read();
            let _ = ws.send(Message::Text(
                json!({"type":"start","sample_rate":24000,"channels":1})
                    .to_string()
                    .into(),
            ));
            let _ = ws.send(Message::Binary([1, 2, 3, 4].repeat(1200).into()));
            let _ = ws.send(Message::Text(json!({"type":"end"}).to_string().into()));
            let _ = ws.read();
            return;
        }
        let mut active = String::from("runtime-moto");
        while let Ok(Message::Text(data)) = ws.read() {
            let value: Value = serde_json::from_str(&data).unwrap();
            if value["method"] == "session.create" && fail_create.load(Ordering::SeqCst) {
                let _ = ws.send(Message::Text(json!({"jsonrpc":"2.0","id":value["id"],"error":{"code":-32000,"message":"fixture create rejected"}}).to_string().into()));
                continue;
            }
            let result = match value["method"].as_str().unwrap_or("") {
                "session.create" => {
                    let n = creates.fetch_add(1, Ordering::SeqCst) + 1;
                    let suffix = if n == 1 {
                        String::new()
                    } else {
                        format!("-{n}")
                    };
                    active = format!("runtime-moto{suffix}");
                    json!({"session_id":active,"stored_session_id":format!("stored-moto{suffix}"),"messages":[],"running":false})
                }
                "session.resume" => {
                    let stored = value["params"]["session_id"].as_str().unwrap();
                    assert!(stored.starts_with("stored-moto"));
                    active = stored.replacen("stored-", "runtime-", 1);
                    json!({"session_id":active,"resumed":stored,"messages":[],"running":false})
                }
                "prompt.submit" => {
                    assert_eq!(value["params"]["session_id"], active);
                    count.fetch_add(1, Ordering::SeqCst);
                    json!({"status":"streaming"})
                }
                "session.interrupt" => json!({"status":"interrupted"}),
                other => panic!("unexpected fixture method {other}"),
            };
            if ws
                .send(Message::Text(
                    json!({"jsonrpc":"2.0","id":value["id"],"result":result})
                        .to_string()
                        .into(),
                ))
                .is_err()
            {
                return;
            }
            if value["method"] == "prompt.submit" {
                if drop_turn {
                    let _ = ws.close(None);
                    return;
                }
                if wait_cancel {
                    continue;
                }
                for (session, kind, text) in [
                    ("telegram", "message.complete", "foreign-private"),
                    (active.as_str(), "reasoning.delta", "hidden-reasoning"),
                    (
                        active.as_str(),
                        "message.complete",
                        "Olá, resposta do fixture.",
                    ),
                ] {
                    if ws.send(Message::Text(json!({"jsonrpc":"2.0","method":"event","params":{"session_id":session,"type":kind,"payload":{"text":text}}}).to_string().into())).is_err() { return; }
                }
            } else if value["method"] == "session.interrupt" {
                let _ = ws.send(Message::Text(json!({"method":"event","params":{"session_id":active,"type":"message.complete","payload":{"text":"Interrompido."}}}).to_string().into()));
            }
        }
        return;
    }
    let mut reader = BufReader::new(&mut stream);
    let mut first = String::new();
    if reader.read_line(&mut first).is_err() {
        return;
    }
    let mut headers = String::new();
    let mut length = 0;
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line).unwrap_or(0) == 0 || line == "\r\n" {
            break;
        }
        if line.to_lowercase().starts_with("content-length:") {
            length = line.split(':').nth(1).unwrap().trim().parse().unwrap();
        }
        headers.push_str(&line);
    }
    assert!(length < 8192);
    let mut body = vec![0; length];
    if reader.read_exact(&mut body).is_err() {
        return;
    }
    drop(reader);
    let path = first.split_whitespace().nth(1).unwrap_or("");
    if path == "/" {
        if headers.contains("UMBREL_APP_SESSION=fixture-app-cookie") {
            http(
                &mut stream,
                "200 OK",
                "Content-Type: text/html\r\n",
                "<script>window.__HERMES_SESSION_TOKEN__=\"fixture-hermes-token\";</script>",
            );
        } else {
            http(
                &mut stream,
                "302 Found",
                "Location: /app-auth?app=hermes-agent&origin=host&path=%2F\r\n",
                "",
            );
        }
    } else if path == "/api/audio/voice-config" {
        assert!(headers
            .to_lowercase()
            .contains("authorization: bearer fixture-hermes-token"));
        assert!(headers.contains("UMBREL_APP_SESSION=fixture-app-cookie"));
        let tts = if edge.load(Ordering::SeqCst) {
            json!({"mode":"relay","reason":"provider 'edge' has no client wire"})
        } else {
            json!({"mode":"direct","provider":"openai","api_key":"fixture-provider-secret"})
        };
        http(
            &mut stream,
            "200 OK",
            "Content-Type: application/json\r\n",
            &json!({"ok":true,"tts":tts}).to_string(),
        );
    } else if path.starts_with("/v1/account/login?") {
        let value: Value = serde_json::from_slice(&body).unwrap();
        if value["password"] != "fixture-password" {
            http(
                &mut stream,
                "401 Unauthorized",
                "",
                "{\"error\":{\"message\":\"Incorrect password\"}}",
            );
        } else if require_totp && value["totpToken"] != "123456" {
            http(
                &mut stream,
                "401 Unauthorized",
                "",
                "{\"error\":{\"message\":\"Missing 2FA code\"}}",
            );
        } else {
            assert_eq!(value["password"], "fixture-password");
            let payload = json!({"url":format!("{base}umbrel_/api/v1/auth/handoff"),"params":{"r":"/","handoff":"fixture-one-use"}});
            http(
                &mut stream,
                "200 OK",
                "Content-Type: application/json\r\n",
                &payload.to_string(),
            );
        }
    } else if path == "/umbrel_/api/v1/auth/handoff" {
        assert!(String::from_utf8_lossy(&body).contains("handoff=fixture-one-use"));
        http(&mut stream,"302 Found","Location: /\r\nSet-Cookie: UMBREL_APP_SESSION=fixture-app-cookie; Path=/; HttpOnly; SameSite=Lax\r\n", "");
    } else {
        http(&mut stream, "404 Not Found", "", "");
    }
}

#[test]
fn login_2fa_handoff_cookie_and_authenticated_websocket() {
    let fixture = Fixture::new(false, false);
    let backend = fixture.backend();
    let alive = AtomicBool::new(true);
    assert_eq!(backend.discover().unwrap_err(), net::LOGIN);
    assert_eq!(
        backend.login("fixture-password", "", &alive).unwrap_err(),
        net::TOTP
    );
    let token = backend.login("fixture-password", "123456", &alive).unwrap();
    assert_eq!(token, "fixture-hermes-token");
    let mut ws = backend.socket("/api/ws", &token).unwrap();
    assert_eq!(
        net::call(&mut ws, "session.create", json!({}), &alive).unwrap()["stored_session_id"],
        "stored-moto"
    );
}

#[test]
fn password_only_account_does_not_require_or_enable_two_factor() {
    let fixture = Fixture::options(false, false, false);
    let backend = fixture.backend();
    let alive = AtomicBool::new(true);
    let error = backend
        .login("wrong-fixture-password", "", &alive)
        .unwrap_err();
    assert_ne!(error, net::TOTP);
    assert!(!error.0.contains("wrong-fixture-password"));
    assert_eq!(
        backend.login("fixture-password", "", &alive).unwrap(),
        "fixture-hermes-token"
    );
}

#[test]
fn binary_chat_ignores_foreign_events_and_plays_only_returned_pcm() {
    let fixture = Fixture::new(false, false);
    let mut app = fixture.app();
    app.login();
    app.send(json!({"cmd":"send","text":"Olá Hermes"}));
    let reply = app.event("reply");
    assert_eq!(reply["text"], "Olá, resposta do fixture.");
    app.send(json!({"cmd":"speak","text":reply["text"]}));
    app.event("spoken");
    assert_eq!(
        fs::read(fixture.root.join("pcm-received")).unwrap(),
        [1, 2, 3, 4].repeat(1200)
    );
    assert_eq!(fixture.submits.load(Ordering::SeqCst), 1);
}

#[test]
fn unconfirmed_provider_never_starts_speech_or_exposes_provider_keys() {
    let fixture = Fixture::new(false, false);
    fixture.edge.store(false, Ordering::SeqCst);
    let mut app = fixture.app();
    app.login();
    app.send(json!({"cmd":"speak","text":"read only with Edge"}));
    let error = app.event("speech_error");
    assert!(error["text"].as_str().unwrap().contains("Edge TTS"));
    assert!(!error.to_string().contains("fixture-provider-secret"));
    assert!(!fixture.root.join("pcm-received").exists());
}

#[test]
fn alsa_player_failure_is_reported_instead_of_success() {
    let fixture = Fixture::new(false, false);
    let mut app = fixture.app();
    app.login();
    fs::write(
        fixture.root.join("tools/aplay"),
        "#!/bin/sh\ncat > /dev/null\nexit 1\n",
    )
    .unwrap();
    app.send(json!({"cmd":"speak","text":"fixture speech"}));
    assert!(app.event("speech_error")["text"]
        .as_str()
        .unwrap()
        .contains("áudio"));
}

#[test]
fn lost_reply_survives_restart_and_does_not_repeat_a_prompt() {
    let fixture = Fixture::new(true, false);
    {
        let mut app = fixture.app();
        app.login();
        app.send(json!({"cmd":"send","text":"one operation"}));
        assert_eq!(app.event("error")["pending"], true);
        app.send(json!({"cmd":"send","text":"one operation"}));
        assert_eq!(app.event("error")["pending"], true);
    }
    let mut app = fixture.app();
    app.event("ready");
    app.send(json!({"cmd":"login","password":"fixture-password","totp":"123456"}));
    assert_eq!(app.event("connected")["pending"], true);
    app.send(json!({"cmd":"send","text":"one operation"}));
    assert_eq!(app.event("error")["pending"], true);
    assert_eq!(fixture.submits.load(Ordering::SeqCst), 1);
}

#[test]
fn cancelling_a_turn_sends_scoped_interrupt_and_waits_for_finalization() {
    let fixture = Fixture::new(false, true);
    let mut app = fixture.app();
    app.login();
    app.send(json!({"cmd":"send","text":"wait until cancelled"}));
    for _ in 0..100 {
        if fixture.submits.load(Ordering::SeqCst) > 0 {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    app.send(json!({"cmd":"cancel"}));
    assert_eq!(app.event("reply")["cancelled"], true);
}

#[test]
fn new_conversation_changes_current_session_and_survives_restart() {
    let fixture = Fixture::new(false, false);
    {
        let mut app = fixture.app();
        app.login();
        app.send(json!({"cmd":"send","text":"old topic"}));
        app.event("reply");
        app.send(json!({"cmd":"new_session"}));
        app.event("new_session");
        assert_eq!(
            storage::load(&fixture.root.join("hermes-task.json")).unwrap()["stored_session_id"],
            "stored-moto-2"
        );
        app.send(json!({"cmd":"send","text":"new topic"}));
        app.event("reply");
    }
    let mut app = fixture.app();
    app.login();
    app.send(json!({"cmd":"send","text":"continue new topic"}));
    app.event("reply");
    assert_eq!(fixture.creates.load(Ordering::SeqCst), 2);
    assert_eq!(fixture.submits.load(Ordering::SeqCst), 3);
    assert_eq!(
        storage::load(&fixture.root.join("hermes-task.json")).unwrap()["stored_session_id"],
        "stored-moto-2"
    );
}

#[test]
fn failed_new_conversation_keeps_the_previous_session_usable() {
    let fixture = Fixture::new(false, false);
    let mut app = fixture.app();
    app.login();
    fixture.fail_create.store(true, Ordering::SeqCst);
    app.send(json!({"cmd":"new_session"}));
    app.event("error");
    assert_eq!(
        storage::load(&fixture.root.join("hermes-task.json")).unwrap()["stored_session_id"],
        "stored-moto"
    );
    app.send(json!({"cmd":"send","text":"still the original conversation"}));
    app.event("reply");
    assert_eq!(fixture.creates.load(Ordering::SeqCst), 1);
}

#[test]
fn uncertain_turn_cannot_be_abandoned_by_starting_another_session() {
    let fixture = Fixture::new(true, false);
    let mut app = fixture.app();
    app.login();
    app.send(json!({"cmd":"send","text":"operation with lost receipt"}));
    assert_eq!(app.event("error")["pending"], true);
    app.send(json!({"cmd":"new_session"}));
    assert_eq!(app.event("error")["pending"], true);
    assert_eq!(fixture.creates.load(Ordering::SeqCst), 1);
    assert_eq!(fixture.submits.load(Ordering::SeqCst), 1);
}
