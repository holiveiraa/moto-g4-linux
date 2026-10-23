// SPDX-License-Identifier: MIT
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use url::Url;

#[derive(Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub server_url: String,
    pub auth_origin: Option<String>,
    pub user_id: String,
    pub profile: String,
    pub ca_file: Option<PathBuf>,
    pub auto_speak: bool,
    pub remember_session: bool,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            server_url: "https://server.example:18790/".into(),
            auth_origin: None,
            user_id: "0".into(),
            profile: String::new(),
            ca_file: None,
            auto_speak: true,
            remember_session: false,
        }
    }
}
impl Config {
    pub fn for_server(value: &str) -> Result<Self> {
        let url = endpoint(value)?;
        Ok(Self {
            server_url: url.to_string(),
            ..Self::default()
        })
    }
    pub fn load(path: &Path) -> Result<Self> {
        let value = crate::storage::load(path)?;
        let mut config: Self =
            serde_json::from_value(value).map_err(|_| Error("Configuração do Hermes inválida."))?;
        config.server_url = endpoint(&config.server_url)?.to_string();
        if let Some(value) = &config.auth_origin {
            endpoint(value)?;
        }
        if config.user_id.is_empty()
            || config.user_id.len() > 128
            || config.user_id.chars().any(char::is_control)
            || config.profile.len() > 128
            || config.profile.chars().any(char::is_control)
        {
            return Err(Error("Conta ou perfil inválido."));
        }
        Ok(config)
    }
    pub fn url(&self) -> Url {
        Url::parse(&self.server_url).expect("validated configuration")
    }
    pub fn auth_url(&self) -> Url {
        if let Some(value) = &self.auth_origin {
            return Url::parse(value).expect("validated auth origin");
        }
        let mut url = self.url();
        url.set_port(Some(2000)).expect("validated app origin");
        url
    }
    pub fn route(&self, path: &str) -> Url {
        let mut url = self.url().join(path).expect("fixed route");
        if !self.profile.is_empty() {
            url.query_pairs_mut().append_pair("profile", &self.profile);
        }
        url
    }
    pub fn binding(&self) -> String {
        format!(
            "{}|{}|{}|{}",
            self.server_url,
            self.auth_url(),
            self.user_id,
            self.profile
        )
    }
}
pub fn endpoint(value: &str) -> Result<Url> {
    let url = Url::parse(value).map_err(|_| Error("Informe o endereço do Hermes."))?;
    crate::tailnet::candidate(&url)?;
    if url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err(Error(
            "Use HTTPS ou HTTP pelo IP Tailscale, sem senha, caminho ou parâmetros na URL.",
        ));
    }
    Ok(url)
}
