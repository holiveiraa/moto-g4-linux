// SPDX-License-Identifier: MIT
use crate::{Error, Result};
use serde_json::{json, Value};
pub const MAX_FRAME: usize = 1024 * 1024;
pub const MAX_TEXT: usize = 20000;
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
pub fn pcm_start(value: &Value) -> Result<u32> {
    let rate = value["sample_rate"].as_u64().unwrap_or(0);
    if value["type"] != "start" || !(8000..=48000).contains(&rate) || value["channels"] != 1 {
        return Err(Error("Formato PCM do servidor incompatível."));
    }
    Ok(rate as u32)
}
pub fn validate_pcm(data: &[u8]) -> Result<()> {
    if data.is_empty() || !data.len().is_multiple_of(2) || data.len() > 262144 {
        return Err(Error("Bloco de áudio inválido."));
    }
    Ok(())
}
pub struct Reply {
    session: String,
    admission: Option<String>,
    pub execution_generation: Option<u64>,
    pub cancelled: bool,
    completed: bool,
}
impl Reply {
    pub fn new(session: &str) -> Self {
        Self {
            session: session.into(),
            admission: None,
            execution_generation: None,
            cancelled: false,
            completed: false,
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
            || self
                .admission
                .as_deref()
                .is_none_or(|id| params["admission_id"] != id)
            || value["method"] != "event"
        {
            return Ok(None);
        }
        let generation = params["execution_generation"].as_u64();
        let queued_cancel = generation.is_none()
            && self.execution_generation.is_none()
            && params["type"] == "message.complete"
            && params["payload"]["outcome"] == "cancelled";
        if (generation.is_none() && !queued_cancel)
            || (self.execution_generation.is_some() && generation != self.execution_generation)
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
