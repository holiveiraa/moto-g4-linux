// SPDX-License-Identifier: MIT
use crate::{Error, Result};
use serde_json::{json, Value};
pub const MAX_FRAME: usize = 1024 * 1024;
pub const MAX_TEXT: usize = 20000;

/// History is display-only on reconnect. Legacy rows use `text`; canonical
/// rows can use `content`. Never select tool/reasoning rows or auto-speak it.
pub fn history_reply(snapshot: &Value) -> String {
    snapshot["messages"]
        .as_array()
        .into_iter()
        .flatten()
        .rev()
        .filter(|row| row["role"] == "assistant")
        .find_map(|row| {
            row["content"]
                .as_str()
                .or_else(|| row["text"].as_str())
                .filter(|text| !text.trim().is_empty())
        })
        .unwrap_or("")
        .chars()
        .filter(|c| !c.is_control() || matches!(c, '\n' | '\t'))
        .take(MAX_TEXT)
        .collect()
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Gateway {
    Canonical,
    Legacy,
}
impl Gateway {
    pub fn canonical(self) -> bool {
        self == Self::Canonical
    }
    pub fn create(self, key: &str) -> Value {
        match self {
            Self::Canonical => json!({"source":"gui","request_id":key}),
            Self::Legacy => {
                json!({"source":"desktop","idempotency_key":key,"close_on_disconnect":false})
            }
        }
    }
    pub fn resume(self, session: &str) -> Value {
        match self {
            Self::Canonical => json!({"session_id":session}),
            Self::Legacy => {
                json!({"session_id":session,"inline_images":false,"close_on_disconnect":false})
            }
        }
    }
    pub fn submit(self, session: &str, text: &str, request: &str) -> Value {
        match self {
            Self::Canonical => {
                json!({"session_id":session,"text":text,"voice_turn":true,"submission_id":request})
            }
            Self::Legacy => {
                json!({"session_id":session,"text":text,"voice_turn":true,"queued":true})
            }
        }
    }
}
pub fn frames(data: &str) -> Result<Vec<Value>> {
    if data.len() > MAX_FRAME {
        return Err(Error("Mensagem do servidor excedeu o limite."));
    }
    serde_json::Deserializer::from_str(data)
        .into_iter::<Value>()
        .map(|v| v.map_err(|_| Error("Protocolo do Hermes inválido.")))
        .collect()
}
pub fn rpc(id: &str, method: &str, params: Value) -> Value {
    json!({"jsonrpc":"2.0","id":id,"method":method,"params":params})
}
/// Only fixed protocol identifiers are eligible for a private diagnostic.
/// Never retain the server's message, detail, params or result.
pub fn rpc_diagnostic(method: &str, canonical: Option<bool>, error: &Value) -> Value {
    let method = match method {
        "session.create" | "session.resume" => Some(method),
        _ => None,
    };
    let reason = error["data"]["reason"].as_str().filter(|s| {
        matches!(
            *s,
            "invalid_params"
                | "not_found"
                | "permission_denied"
                | "profile_mismatch"
                | "admission_conflict"
                | "storage_unavailable"
        )
    });
    let field = error["data"]["field"].as_str().filter(|s| {
        matches!(
            *s,
            "source" | "request_id" | "profile" | "session_id" | "title"
        )
    });
    json!({"method":method,"session_authority":canonical,"code":error["code"].as_i64(),"reason":reason,"field":field})
}
pub fn pcm_start(value: &Value) -> Result<u32> {
    let rate = value["sample_rate"].as_u64().unwrap_or(0);
    if value["type"] != "start" || !(8000..=48000).contains(&rate) || value["channels"] != 1 {
        return Err(Error("VOICE_FORMAT: Formato PCM do servidor incompatível."));
    }
    Ok(rate as u32)
}
// Memory guard per assembled message and short synthesis segment, NOT a turn
// duration limit. Reception and playback are concurrent; a segment's bounded
// queue plus parser payload can temporarily hold roughly two copies. Successive
// text segments reuse that budget rather than accumulating a whole answer.
pub const SPEECH_MESSAGE_MEMORY_BYTES: usize = 32 * 1024 * 1024;
pub const SPEECH_CONTROL_BYTES: usize = 16384;
pub const SPEECH_PROGRESS_SECONDS: u64 = 60;
pub fn validate_pcm(data: &[u8]) -> Result<()> {
    if data.is_empty() || !data.len().is_multiple_of(2) {
        return Err(Error(
            "VOICE_PCM_ALIGNMENT: Bloco PCM vazio ou amostra incompleta.",
        ));
    }
    if data.len() > SPEECH_MESSAGE_MEMORY_BYTES {
        return Err(Error("VOICE_MESSAGE_MEMORY: Uma mensagem de voz excedeu o orçamento de memória de 32 MiB; a resposta continua em texto."));
    }
    Ok(())
}

#[derive(Default)]
pub struct SpeechMetrics {
    pub rate: Option<u32>,
    pub bytes: u64,
    pub chunks: u64,
    pub largest_chunk: usize,
}
impl SpeechMetrics {
    pub fn start(&mut self, value: &Value) -> Result<u32> {
        if self.rate.is_some() {
            return Err(Error(
                "VOICE_PROTOCOL: O servidor repetiu o início do áudio.",
            ));
        }
        let rate = pcm_start(value)?;
        self.rate = Some(rate);
        Ok(rate)
    }
    pub fn accept(&mut self, data: &[u8]) -> Result<()> {
        self.rate
            .ok_or(Error("VOICE_PROTOCOL: Áudio chegou sem formato."))?;
        self.largest_chunk = self.largest_chunk.max(data.len());
        validate_pcm(data)?;
        self.bytes = self.bytes.saturating_add(data.len() as u64);
        self.chunks = self.chunks.saturating_add(1);
        Ok(())
    }
    pub fn finish(&self) -> Result<()> {
        if self.bytes == 0 {
            return Err(Error("VOICE_EMPTY: O provedor não produziu áudio."));
        }
        Ok(())
    }
}
pub struct Reply {
    session: String,
    admission: Option<String>,
    pub execution_generation: Option<u64>,
    pub cancelled: bool,
    completed: bool,
    gateway: Gateway,
}
impl Reply {
    pub fn new(session: &str) -> Self {
        Self {
            session: session.into(),
            admission: None,
            execution_generation: None,
            cancelled: false,
            completed: false,
            gateway: Gateway::Canonical,
        }
    }
    pub fn legacy(session: &str) -> Self {
        Self {
            gateway: Gateway::Legacy,
            ..Self::new(session)
        }
    }
    pub fn bind(&mut self, admission: &str, generation: Option<u64>) {
        self.admission = Some(admission.into());
        self.execution_generation = generation;
    }
    pub fn feed(&mut self, value: &Value) -> Result<Option<String>> {
        let params = &value["params"];
        if params["session_id"] != self.session
            || self.completed
            || (self.gateway.canonical()
                && self
                    .admission
                    .as_deref()
                    .is_none_or(|id| params["admission_id"] != id))
            || value["method"] != "event"
        {
            return Ok(None);
        }
        let generation = params["execution_generation"].as_u64();
        let queued_cancel = generation.is_none()
            && self.execution_generation.is_none()
            && params["type"] == "message.complete"
            && params["payload"]["outcome"] == "cancelled";
        if self.gateway.canonical()
            && ((generation.is_none() && !queued_cancel)
                || (self.execution_generation.is_some() && generation != self.execution_generation))
        {
            return Ok(None);
        }
        if params["type"] == "message.start" || params["type"] == "message.complete" {
            self.execution_generation = generation;
        }
        if params["type"] != "message.complete" {
            return Ok(None);
        }
        let text = params["payload"]["text"].as_str().unwrap_or("");
        if text.len() > MAX_TEXT * 4 {
            return Err(Error("Resposta longa demais para o app."));
        }
        self.completed = true;
        self.cancelled = params["payload"]["outcome"] == "cancelled";
        Ok(Some(
            text.chars()
                .filter(|c| !c.is_control() || matches!(c, '\n' | '\t'))
                .take(MAX_TEXT)
                .collect(),
        ))
    }
}
