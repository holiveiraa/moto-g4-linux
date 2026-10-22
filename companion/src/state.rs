// SPDX-License-Identifier: MIT
use crate::{Error, Result};
use serde::{Deserialize, Serialize};

#[derive(Default, Clone, Serialize, Deserialize)]
pub struct Turn {
    pub request_id: Option<String>,
    pub phase: Phase,
}
#[derive(Default, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    #[default]
    Idle,
    Submitting,
    Running,
    Stopping,
    Unknown,
}
impl Turn {
    pub fn begin(&mut self, request: &str) -> Result<()> {
        if self.busy() {
            return Err(Error("Reconcilie a tarefa anterior antes de enviar outra."));
        }
        self.request_id = Some(request.into());
        self.phase = Phase::Submitting;
        Ok(())
    }
    pub fn accept(&mut self) {
        self.phase = Phase::Running;
    }
    pub fn disconnected(&mut self) {
        if self.busy() {
            self.phase = Phase::Unknown;
        }
    }
    pub fn request_stop(&mut self) {
        if self.busy() {
            self.phase = Phase::Stopping;
        }
    }
    pub fn complete(&mut self) {
        self.phase = Phase::Idle;
        self.request_id = None;
    }
    pub fn uncertain(&self) -> bool {
        self.phase == Phase::Unknown
    }
    pub fn busy(&self) -> bool {
        self.phase != Phase::Idle
    }
}
