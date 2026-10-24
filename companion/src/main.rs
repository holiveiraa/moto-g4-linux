// SPDX-License-Identifier: MIT
use base64::{engine::general_purpose::STANDARD, Engine};
use moto_hermes::{
    config::Config,
    face,
    net::{self, Backend},
    protocol,
    state::Turn,
    storage, Error, Result,
};
use serde_json::{json, Value};
use std::{
    io::{self, BufRead, Read, Write},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU8, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tungstenite::Message;

#[derive(Clone)]
struct Output(Arc<Mutex<io::Stdout>>);
impl Output {
    fn event(&self, value: Value) {
        if let Ok(mut output) = self.0.lock() {
            let _ = serde_json::to_writer(&mut *output, &value);
            let _ = output.write_all(b"\n");
            let _ = output.flush();
        }
    }
}
struct Model {
    token: Option<String>,
    stored: String,
    create_key: String,
    turn: Turn,
}
impl Model {
    fn load(backend: &Backend) -> Result<Self> {
        let saved =
            storage::load(&backend.directory.join("hermes-task.json")).unwrap_or(Value::Null);
        let (stored, key, mut turn) = if saved["binding"] == backend.config.binding() {
            (
                saved["stored_session_id"]
                    .as_str()
                    .unwrap_or("")
                    .to_string(),
                saved["create_key"].as_str().unwrap_or("").to_string(),
                serde_json::from_value(saved["turn"].clone()).unwrap_or_default(),
            )
        } else {
            (String::new(), String::new(), Turn::default())
        };
        turn.disconnected();
        if std::env::var_os("MOTO_HERMES_REQUIRE_EXISTING_SESSION").is_some() && stored.is_empty() {
            return Err(Error("A revisão exige uma conversa existente com a mesma conta e perfil. Nenhuma conversa foi criada."));
        }
        Ok(Self {
            token: None,
            stored,
            create_key: if key.is_empty() { storage::id()? } else { key },
            turn,
        })
    }
    fn save(&self, backend: &Backend) -> Result<()> {
        storage::save(
            &backend.directory.join("hermes-task.json"),
            &json!({"binding":backend.config.binding(),"stored_session_id":self.stored,"create_key":self.create_key,"turn":self.turn}),
        )
    }
}
struct Chat {
    ws: net::Socket,
    gateway: protocol::Gateway,
    heartbeat: Instant,
}
#[derive(Clone)]
struct Runtime {
    backend: Backend,
    model: Arc<Mutex<Model>>,
    chat: Arc<Mutex<Option<Chat>>>,
    completed_reply: Arc<Mutex<Option<Value>>>,
    output: Output,
    alive: Arc<AtomicBool>,
    busy: Arc<AtomicBool>,
    speech_busy: Arc<AtomicBool>,
    turn_signal: Arc<AtomicU8>,
    speech_signal: Arc<AtomicU8>,
}
impl Runtime {
    fn snapshot(&self, ws: &mut net::Socket, gateway: protocol::Gateway) -> Result<Value> {
        let model = self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?;
        let mut params = if model.stored.is_empty() {
            gateway.create(&model.create_key)
        } else {
            gateway.resume(&model.stored)
        };
        let method = if model.stored.is_empty() {
            "session.create"
        } else {
            "session.resume"
        };
        if !self.backend.config.profile.is_empty() {
            params["profile"] = json!(self.backend.config.profile);
        }
        drop(model);
        let result = net::call_diagnosed(
            ws,
            method,
            params,
            &self.alive,
            &self.backend.directory,
            gateway,
        )?;
        let id = result["session_id"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() < 256)
            .ok_or(Error(
                "A versão do Hermes não retornou uma sessão compatível.",
            ))?;
        let stored = result["stored_session_id"]
            .as_str()
            .or_else(|| result["resumed"].as_str())
            .unwrap_or("");
        let mut model = self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?;
        if !stored.is_empty() {
            model.stored = stored.into();
        }
        if model.stored.is_empty() {
            return Err(Error(
                "O Hermes não retornou a identidade persistente da conversa.",
            ));
        }
        if result["running"] == true && !model.turn.busy() {
            model.turn.begin("observed-running")?;
            model.turn.disconnected();
        }
        model.save(&self.backend)?;
        let _ = id;
        Ok(result)
    }
    fn connect(&self, credentials: Option<(&str, &str)>) -> Result<Value> {
        storage::save(
            &self.backend.directory.join("hermes-diagnostic.json"),
            &Value::Null,
        )?;
        let token = match credentials {
            Some((password, totp)) => self.backend.login(password, totp, &self.alive)?,
            None => self.backend.discover()?,
        };
        if !self.alive.load(Ordering::SeqCst) {
            return Err(Error("Operação cancelada."));
        }
        let mut connection = self.chat.lock().map_err(|_| net::NETWORK)?;
        if connection.is_none() {
            let mut ws = self.backend.socket("/api/ws", &token)?;
            let gateway = net::gateway(&mut ws, &self.alive)?;
            *connection = Some(Chat {
                ws,
                gateway,
                heartbeat: Instant::now(),
            });
        }
        let chat = connection.as_mut().ok_or(net::NETWORK)?;
        let result = self.snapshot(&mut chat.ws, chat.gateway)?;
        if !self.alive.load(Ordering::SeqCst) {
            return Err(Error("Operação cancelada."));
        }
        let mut model = self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?;
        model.token = Some(token);
        self.backend.remember()?;
        // History is shown, never spoken automatically after reconnect.
        let last = protocol::history_reply(&result);
        Ok(json!({"event":"connected","pending":model.turn.busy(),"text":last}))
    }
    fn token(&self) -> Result<String> {
        self.model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?
            .token
            .clone()
            .ok_or(net::LOGIN)
    }
    fn new_session(&self) -> Result<Value> {
        if self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?
            .turn
            .busy()
        {
            return Err(net::UNKNOWN);
        }
        if self.speech_busy.load(Ordering::SeqCst) {
            return Err(Error("Aguarde a voz parar antes de abrir outra conversa."));
        }
        storage::save(
            &self.backend.directory.join("hermes-diagnostic.json"),
            &Value::Null,
        )?;
        self.token()?;
        let mut connection = self.chat.lock().map_err(|_| net::NETWORK)?;
        let chat = connection.as_mut().ok_or(net::LOGIN)?;
        let gateway = chat.gateway;
        let ws = &mut chat.ws;
        let previous = self.snapshot(ws, gateway)?;
        if previous["running"] == true {
            return Err(net::UNKNOWN);
        }
        let key = storage::id()?;
        let mut params = gateway.create(&key);
        if !self.backend.config.profile.is_empty() {
            params["profile"] = json!(self.backend.config.profile);
        }
        let result = net::call_diagnosed(
            ws,
            "session.create",
            params,
            &self.alive,
            &self.backend.directory,
            gateway,
        )?;
        let stored = result["stored_session_id"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() < 256)
            .ok_or(Error(
                "O Hermes não confirmou uma nova conversa. A anterior foi mantida.",
            ))?;
        if result["session_id"]
            .as_str()
            .is_none_or(|s| s.is_empty() || s.len() >= 256)
            || result["running"] == true
            || !self.alive.load(Ordering::SeqCst)
        {
            return Err(Error(
                "Não foi possível confirmar a nova conversa. A anterior foi mantida.",
            ));
        }
        let mut model = self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?;
        if stored == model.stored {
            return Err(Error("O Hermes retornou a conversa anterior."));
        }
        let next = Model {
            token: model.token.clone(),
            stored: stored.into(),
            create_key: key,
            turn: Turn::default(),
        };
        // Switch only after the server returned a new owned session and the
        // journal was safely saved. Creation errors retain the old conversation.
        next.save(&self.backend)?;
        *model = next;
        Ok(json!({"event":"new_session"}))
    }
    fn turn(&self, text: &str) -> Result<Value> {
        if text.trim().is_empty() || text.chars().count() > protocol::MAX_TEXT {
            return Err(Error("Digite uma mensagem de até 20 mil caracteres."));
        }
        self.token()?;
        if self
            .model
            .lock()
            .map_err(|_| Error("Estado indisponível."))?
            .turn
            .busy()
        {
            return Err(net::UNKNOWN);
        }
        let mut connection = self.chat.lock().map_err(|_| net::NETWORK)?;
        let chat = connection.as_mut().ok_or(net::LOGIN)?;
        let gateway = chat.gateway;
        let ws = &mut chat.ws;
        let snapshot = self.snapshot(ws, gateway)?;
        let sid = snapshot["session_id"]
            .as_str()
            .ok_or(Error("Sessão inválida."))?;
        if snapshot["running"] == true {
            return Err(net::UNKNOWN);
        }
        // Baseline before admission: replay must never consume an earlier turn.
        let mut replay_sequence = 0;
        let mut replay_epoch = String::new();
        if !gateway.canonical() {
            let mut params = json!({"session_id":sid,"last_seen":u64::MAX});
            if !self.backend.config.profile.is_empty() {
                params["profile"] = json!(self.backend.config.profile);
            }
            let baseline = net::call(ws, "session.events.since", params, &self.alive)?;
            replay_sequence = baseline["latest_seq"].as_u64().ok_or(net::UNKNOWN)?;
            replay_epoch = baseline["epoch"].as_str().ok_or(net::UNKNOWN)?.into();
        }
        let mut replay_due = Instant::now();
        let mut replay_waiting = false;
        let request = storage::id()?;
        {
            let mut model = self
                .model
                .lock()
                .map_err(|_| Error("Estado indisponível."))?;
            model.turn.begin(&request)?;
            // Persist BEFORE dispatch. A crash may leave unknown, but can never trigger automatic replay.
            model.save(&self.backend)?;
        }
        if !self.alive.load(Ordering::SeqCst) {
            return Err(net::UNKNOWN);
        }
        let mut submission = gateway.submit(sid, text, &request);
        if !gateway.canonical() && !self.backend.config.profile.is_empty() {
            submission["profile"] = json!(self.backend.config.profile);
        }
        net::send(ws, protocol::rpc(&request, "prompt.submit", submission))?;
        let mut reply = if gateway.canonical() {
            protocol::Reply::new(sid)
        } else {
            protocol::Reply::legacy(sid)
        };
        let deadline = Instant::now() + Duration::from_secs(600);
        let mut stop_sent = false;
        let mut cancel_sent = false;
        let mut interrupt_sent = false;
        let mut execution_generation = None;
        let mut admission_id = None;
        let mut accepted = false;
        let mut early_events = Vec::new();
        let mut early_bytes = 0;
        while self.alive.load(Ordering::SeqCst) && Instant::now() < deadline {
            if chat.heartbeat.elapsed() >= Duration::from_secs(15) {
                net::send(
                    ws,
                    protocol::rpc("moto-heartbeat", "gateway.ping", json!({})),
                )?;
                chat.heartbeat = Instant::now();
            }
            if !gateway.canonical()
                && accepted
                && !replay_waiting
                && replay_due.elapsed() >= Duration::from_secs(2)
            {
                let mut params = json!({"session_id":sid,"last_seen":replay_sequence});
                if !self.backend.config.profile.is_empty() {
                    params["profile"] = json!(self.backend.config.profile);
                }
                net::send(
                    ws,
                    protocol::rpc("moto-replay", "session.events.since", params),
                )?;
                replay_waiting = true;
                replay_due = Instant::now();
            }
            if self.turn_signal.load(Ordering::SeqCst) == 1
                && ((!gateway.canonical() && accepted && !interrupt_sent)
                    || (execution_generation.is_some() && !interrupt_sent)
                    || (execution_generation.is_none() && admission_id.is_some() && !cancel_sent))
            {
                let (method, params) = if !gateway.canonical() {
                    interrupt_sent = true;
                    let mut params = json!({"session_id":sid});
                    if !self.backend.config.profile.is_empty() {
                        params["profile"] = json!(self.backend.config.profile);
                    }
                    ("session.interrupt", params)
                } else if let Some(generation) = execution_generation {
                    interrupt_sent = true;
                    (
                        "session.interrupt",
                        json!({"session_id":sid,"execution_generation":generation}),
                    )
                } else {
                    cancel_sent = true;
                    (
                        "prompt.cancel",
                        json!({"session_id":sid,"admission_id":admission_id}),
                    )
                };
                let stop_id = if interrupt_sent {
                    "moto-interrupt"
                } else {
                    "moto-cancel"
                };
                net::send(ws, protocol::rpc(stop_id, method, params))?;
                stop_sent = true;
                let mut model = self
                    .model
                    .lock()
                    .map_err(|_| Error("Estado indisponível."))?;
                model.turn.request_stop();
                model.save(&self.backend)?;
                self.output.event(json!({"event":"status","state":"thinking","text":"Parada solicitada; aguardando o Hermes."}));
            }
            if let Some(Message::Text(data)) = net::receive(ws)? {
                let mut frames: std::collections::VecDeque<_> = protocol::frames(&data)?.into();
                while let Some(value) = frames.pop_front() {
                    if value["id"] == "moto-replay" && replay_waiting {
                        replay_waiting = false;
                        let result = &value["result"];
                        if value.get("error").is_some()
                            || result["truncated"] != false
                            || result["epoch"] != replay_epoch
                        {
                            return Err(net::UNKNOWN);
                        }
                        let events = result["events"].as_array().ok_or(net::UNKNOWN)?;
                        let latest = result["latest_seq"].as_u64().ok_or(net::UNKNOWN)?;
                        if latest < replay_sequence {
                            return Err(net::UNKNOWN);
                        }
                        for params in events.iter().rev() {
                            // Replayed params pass through the same scoped completion parser.
                            let seq = params["seq"].as_u64().ok_or(net::UNKNOWN)?;
                            if seq > replay_sequence && seq <= latest && params["session_id"] == sid
                            {
                                frames.push_front(json!({"method":"event","params":params}));
                            }
                        }
                        replay_sequence = latest;
                        continue;
                    }
                    if value["id"] == request {
                        let mut model = self
                            .model
                            .lock()
                            .map_err(|_| Error("Estado indisponível."))?;
                        if value.get("error").is_some() {
                            model.turn.complete();
                            model.save(&self.backend)?;
                            return Err(Error("O Hermes recusou a mensagem; nada foi reenviado."));
                        }
                        if value["result"]["voice_stopped"] == true {
                            model.turn.complete();
                            model.save(&self.backend)?;
                            return Ok(json!({"event":"reply","text":"","cancelled":true}));
                        }
                        execution_generation = value["result"]["execution_generation"].as_u64();
                        admission_id = value["result"]["admission_id"]
                            .as_str()
                            .filter(|s| !s.is_empty() && s.len() <= 256)
                            .map(str::to_owned);
                        if gateway.canonical() {
                            let admission = admission_id.as_deref().ok_or(net::UNKNOWN)?;
                            reply.bind(admission, execution_generation);
                        } else if value["result"]["status"] != "streaming" {
                            // Legacy queued/steered replies do not identify a
                            // unique execution. Never speak a preceding result.
                            return Err(net::UNKNOWN);
                        }
                        accepted = true;
                        for event in early_events.drain(..).rev() {
                            frames.push_front(event);
                        }
                        model.turn.accept();
                        model.save(&self.backend)?;
                    }
                    if value["method"] == "event"
                        && value["params"]["session_id"] == sid
                        && !accepted
                        && matches!(
                            value["params"]["type"].as_str(),
                            Some("message.start" | "message.complete")
                        )
                    {
                        early_bytes += value.to_string().len();
                        if early_events.len() >= 32 || early_bytes > protocol::MAX_FRAME {
                            return Err(net::UNKNOWN);
                        }
                        early_events.push(value);
                        continue;
                    }
                    if (value["id"] == "moto-cancel" && cancel_sent)
                        || (value["id"] == "moto-interrupt" && interrupt_sent)
                    {
                        if value.get("error").is_some() {
                            return Err(Error("O Hermes não confirmou a parada. Confira a tarefa antes de continuar."));
                        }
                        // A terminal queued-admission receipt is authoritative even
                        // when no assistant message was ever started.
                        if value["id"] == "moto-cancel" && value["result"]["status"] == "started" {
                            // The queued admission may have started before cancel
                            // arrived. Interrupt only its acknowledged generation.
                            execution_generation = value["result"]["execution_generation"].as_u64();
                        }
                        if value["id"] == "moto-cancel" && value["result"]["status"] == "terminal" {
                            let mut model = self
                                .model
                                .lock()
                                .map_err(|_| Error("Estado indisponível."))?;
                            model.turn.complete();
                            model.save(&self.backend)?;
                            return Ok(
                                json!({"event":"reply","text":"Solicitação encerrada no Hermes.","cancelled":value["result"]["outcome"] == "cancelled"}),
                            );
                        }
                    }
                    if value["params"]["session_id"] == sid
                        && (matches!(
                            value["method"].as_str(),
                            Some("approval.request" | "clarify.request")
                        ) || (value["method"] == "event"
                            && matches!(
                                value["params"]["type"].as_str(),
                                Some("approval.request" | "clarify.request")
                            )))
                    {
                        self.output.event(json!({"event":"status","state":"approval","text":"O Hermes aguarda uma confirmação. Abra a sessão no Hermes; o app não aprova por voz."}));
                    }
                    let completed = reply.feed(&value)?;
                    execution_generation = reply.execution_generation.or(execution_generation);
                    if let Some(text) = completed {
                        let mut model = self
                            .model
                            .lock()
                            .map_err(|_| Error("Estado indisponível."))?;
                        model.turn.complete();
                        model.save(&self.backend)?;
                        return Ok(
                            json!({"event":"reply","text":text,"cancelled":stop_sent || reply.cancelled}),
                        );
                    }
                }
            }
        }
        Err(net::UNKNOWN)
    }
    fn task(&self, command: Value) -> thread::JoinHandle<()> {
        let runtime = self.clone();
        thread::spawn(move || {
            let kind = command["cmd"].as_str().unwrap_or("");
            let result = match kind {
                "connect" => runtime.connect(None),
                "login" => runtime.connect(Some((
                    command["password"].as_str().unwrap_or(""),
                    command["totp"].as_str().unwrap_or(""),
                ))),
                "send" => runtime.turn(command["text"].as_str().unwrap_or("")),
                "new_session" => runtime.new_session(),
                "transcribe" => {
                    let path = PathBuf::from(command["path"].as_str().unwrap_or(""));
                    runtime
                        .backend
                        .transcribe(&path, &runtime.backend.directory.join("groq.json"))
                        .map(|text| if command["scope"] == "wake" {
                            json!({"event":"wake_transcript","epoch":command["epoch"],"accepted":moto_hermes::hearing::matches_wake(&text),"characters":text.chars().count(),"recognizer":"groq"})
                        } else {
                            json!({"event":"transcript","epoch":command["epoch"],"action":moto_hermes::hearing::action(&text),"text":text})
                        })
                }
                _ => Err(Error("Operação desconhecida.")),
            };
            if kind == "send" && result.is_err() {
                if let Ok(mut model) = runtime.model.lock() {
                    model.turn.disconnected();
                    let _ = model.save(&runtime.backend);
                }
            }
            let result = result.map(|mut value| {
                if kind == "send" {
                    value["client_turn"] = command["client_turn"].clone();
                    if let Ok(mut cached) = runtime.completed_reply.lock() {
                        *cached = Some(value.clone());
                    }
                }
                value
            });
            if result.as_ref().is_err_and(|error| *error == net::NETWORK) {
                if let Ok(mut chat) = runtime.chat.lock() {
                    *chat = None;
                }
            }
            runtime.busy.store(false, Ordering::SeqCst);
            if runtime.alive.load(Ordering::SeqCst) {
                match result {
                    Ok(value) => runtime.output.event(value),
                    Err(error) => runtime.output.event(json!({"event":"error","operation":kind,"epoch":command["epoch"],"text":error.0,"login":error==net::LOGIN,"totp":error==net::TOTP,"pending":runtime.model.lock().is_ok_and(|m|m.turn.busy()),"rpc":if matches!(kind,"connect"|"login"|"new_session") { storage::load(&runtime.backend.directory.join("hermes-diagnostic.json")).unwrap_or(Value::Null) } else { Value::Null }})),
                }
            }
        })
    }
}
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args == ["--smoke"] {
        smoke();
        return;
    }
    if args == ["--face-stdio"] {
        let output = Output(Arc::new(Mutex::new(io::stdout())));
        let mut input = io::stdin().lock();
        loop {
            let mut line = Vec::new();
            if input
                .by_ref()
                .take(8193)
                .read_until(b'\n', &mut line)
                .unwrap_or(0)
                == 0
                || line.len() > 8192
            {
                break;
            }
            let Ok(v) = serde_json::from_slice::<Value>(&line) else {
                continue;
            };
            if v["cmd"] == "close" {
                break;
            }
            if let Ok(pose) = face::pose(
                v["state"].as_str().unwrap_or("standby"),
                v["tick"].as_u64().unwrap_or(0) as u32,
            ) {
                output.event(json!({"event":"face","pose":pose}));
            }
        }
        return;
    }
    if args.len() == 3 && args[0] == "--listen" && args[1] == "--device" {
        let output = Output(Arc::new(Mutex::new(io::stdout())));
        let failure = output.clone();
        if let Err(e) = moto_hermes::listener::run(&args[2], Arc::new(move |v| output.event(v))) {
            failure.event(json!({"event":"voice_error","text":e.0}));
        }
        return;
    }
    if args.len() != 3 || args[0] != "--stdio" || args[1] != "--config" {
        eprintln!("Usage: moto-hermes --stdio --config <private-config.json> | --smoke\nCommands use private JSON lines on stdin; never pass credentials as arguments.");
        std::process::exit(2);
    }
    let output = Output(Arc::new(Mutex::new(io::stdout())));
    let path = PathBuf::from(&args[2]);
    let initialized = (|| {
        let config = Config::load(&path)?;
        let directory = path.parent().ok_or(Error("Pasta privada inválida."))?;
        let backend = Backend::new(config, directory)?;
        let model = Model::load(&backend)?;
        Ok::<_, Error>(Runtime {
            backend,
            model: Arc::new(Mutex::new(model)),
            chat: Arc::new(Mutex::new(None)),
            completed_reply: Arc::new(Mutex::new(None)),
            output: output.clone(),
            alive: Arc::new(AtomicBool::new(true)),
            busy: Arc::new(AtomicBool::new(false)),
            speech_busy: Arc::new(AtomicBool::new(false)),
            turn_signal: Arc::new(AtomicU8::new(0)),
            speech_signal: Arc::new(AtomicU8::new(0)),
        })
    })();
    let runtime = match initialized {
        Ok(r) => r,
        Err(e) => {
            output.event(json!({"event":"error","text":e.0}));
            return;
        }
    };
    output.event(json!({"event":"ready","version":env!("CARGO_PKG_VERSION")}));
    let pulse = runtime.clone();
    let mut jobs = vec![thread::spawn(move || {
        while pulse.alive.load(Ordering::SeqCst) {
            if let Ok(mut connection) = pulse.chat.try_lock() {
                if let Some(chat) = connection.as_mut() {
                    let result = (|| {
                        if chat.heartbeat.elapsed() >= Duration::from_secs(15) {
                            net::send(
                                &mut chat.ws,
                                protocol::rpc("moto-heartbeat", "gateway.ping", json!({})),
                            )?;
                            chat.heartbeat = Instant::now();
                        }
                        net::receive(&mut chat.ws)?;
                        Ok::<_, Error>(())
                    })();
                    if result.is_err() {
                        *connection = None;
                        pulse.output.event(json!({"event":"connection_lost","text":"Conexão com o Hermes encerrada. Reconecte à conversa existente."}));
                    }
                }
            }
            thread::sleep(Duration::from_millis(100));
        }
    })];
    let mut input = io::stdin().lock();
    loop {
        let mut line = Vec::new();
        match input.by_ref().take(131073).read_until(b'\n', &mut line) {
            Ok(0) | Err(_) => break,
            Ok(n) if n > 131072 || !line.ends_with(b"\n") => {
                output.event(json!({"event":"error","text":"Comando local grande demais."}));
                break;
            }
            _ => (),
        }
        let value: Value = match serde_json::from_slice(&line) {
            Ok(value) => value,
            Err(_) => {
                output.event(json!({"event":"error","text":"Comando local inválido."}));
                continue;
            }
        };
        match value["cmd"].as_str().unwrap_or("") {
            "close" => break,
            "poll_reply" => {
                if let Ok(cached) = runtime.completed_reply.lock() {
                    if let Some(reply) = cached
                        .as_ref()
                        .filter(|reply| reply["client_turn"] == value["client_turn"])
                    {
                        output.event(reply.clone());
                    } else {
                        output.event(json!({"event":"turn_state","client_turn":value["client_turn"],"reply_available":false,"busy":runtime.busy.load(Ordering::SeqCst)}));
                    }
                }
            }
            "ack_reply" => {
                if let Ok(mut cached) = runtime.completed_reply.lock() {
                    if cached
                        .as_ref()
                        .is_some_and(|reply| reply["client_turn"] == value["client_turn"])
                    {
                        *cached = None;
                    }
                }
            }
            "stop_speech" => {
                runtime.speech_signal.store(1, Ordering::SeqCst);
            }
            "cancel" => {
                runtime.turn_signal.store(1, Ordering::SeqCst);
                runtime.speech_signal.store(1, Ordering::SeqCst);
            }
            "acknowledge_unknown" => {
                if !runtime.busy.load(Ordering::SeqCst) {
                    if let Ok(mut model) = runtime.model.lock() {
                        model.turn.complete();
                        if model.save(&runtime.backend).is_ok() {
                            output.event(json!({"event":"acknowledged"}));
                        }
                    }
                }
            }
            "face" => {
                if value["format"] == "pose" {
                    if let Ok(pose) = face::pose(
                        value["state"].as_str().unwrap_or("standby"),
                        value["tick"].as_u64().unwrap_or(0) as u32,
                    ) {
                        output.event(json!({"event":"face","pose":pose}));
                    }
                    continue;
                }
                if let Ok(data) = face::render(
                    value["state"].as_str().unwrap_or("ready"),
                    216,
                    value["tick"].as_u64().unwrap_or(0) as u32,
                ) {
                    output.event(json!({"event":"face","ppm":STANDARD.encode(data)}));
                }
            }
            "speak" => {
                if runtime.busy.load(Ordering::SeqCst) {
                    output.event(json!({"event":"speech_error","text":"Aguarde a operação atual antes de falar."}));
                    continue;
                }
                if runtime
                    .speech_busy
                    .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                    .is_err()
                {
                    continue;
                }
                runtime.speech_signal.store(0, Ordering::SeqCst);
                let r = runtime.clone();
                jobs.push(thread::spawn(move || {
                    let text = value["text"].as_str().unwrap_or("");
                    let result = if text.is_empty() || text.chars().count() > protocol::MAX_TEXT {
                        Err(Error("Texto de voz inválido."))
                    } else {
                        r.token().and_then(|token| {
                            net::speech(&r.backend, &token, text, &r.speech_signal, &r.alive)
                        })
                    };
                    r.speech_busy.store(false, Ordering::SeqCst);
                    if r.alive.load(Ordering::SeqCst) {
                        match result {
                            Ok(()) => r.output.event(json!({"event":"spoken"})),
                            Err(e) => r.output.event(json!({"event":"speech_error","text":e.0})),
                        }
                    }
                }));
            }
            "connect" | "login" | "send" | "transcribe" | "new_session" => {
                if runtime
                    .busy
                    .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                    .is_ok()
                {
                    runtime.turn_signal.store(0, Ordering::SeqCst);
                    jobs.push(runtime.task(value));
                } else {
                    output
                        .event(json!({"event":"error","operation":value["cmd"],"epoch":value["epoch"],"text":"Aguarde a operação em andamento."}));
                }
            }
            _ => output.event(json!({"event":"error","text":"Comando local desconhecido."})),
        }
        jobs.retain_mut(|job| !job.is_finished());
    }
    runtime.alive.store(false, Ordering::SeqCst);
    runtime.speech_signal.store(1, Ordering::SeqCst);
    let deadline = Instant::now() + Duration::from_secs(2);
    while jobs.iter().any(|job| !job.is_finished()) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(20));
    }
}
fn smoke() {
    // No account, microphone, server request or configuration change.
    let result = thread::spawn(|| {
        let now = Instant::now();
        let id = storage::id()?;
        let shared = Mutex::new(std::collections::HashMap::new());
        shared
            .lock()
            .map_err(|_| Error("Mutex indisponível."))?
            .insert(id, now);
        thread::sleep(Duration::from_millis(1));
        if now.elapsed().is_zero() {
            return Err(Error("Relógio monotônico indisponível."));
        }
        Ok::<_, Error>(())
    })
    .join()
    .ok()
    .and_then(|r| r.ok());
    if result.is_none() {
        eprintln!("Runtime/RNG smoke failed");
        std::process::exit(1);
    }
    println!("PASS: native threads, OS RNG, clock and Rust runtime. TLS/audio/UI need separate acceptance.");
}
