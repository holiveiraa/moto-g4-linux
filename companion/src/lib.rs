// SPDX-License-Identifier: MIT
pub mod auth;
pub mod config;
pub mod face;
pub mod hearing;
pub mod listener;
pub mod net;
pub mod protocol;
pub mod state;
pub mod storage;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Error(pub &'static str);
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}
impl std::error::Error for Error {}
pub type Result<T> = std::result::Result<T, Error>;
