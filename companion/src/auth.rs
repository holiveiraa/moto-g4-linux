// SPDX-License-Identifier: MIT
use crate::{config::Config, Error, Result};
use serde_json::Value;
use url::Url;
pub fn login_target(config: &Config, redirect: &str) -> Result<Url> {
    let base = config.url();
    let mut url = base
        .join(redirect)
        .map_err(|_| Error("Redirecionamento de login inválido."))?;
    if url.origin() != config.auth_url().origin()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.path() != "/app-auth"
        || url.fragment().is_some()
    {
        return Err(Error("O login apontou para um destino inesperado."));
    }
    let pairs: Vec<_> = url.query_pairs().collect();
    for (key, expected) in [("app", "hermes-agent"), ("origin", "host")] {
        let values: Vec<_> = pairs.iter().filter(|p| p.0 == key).collect();
        if values.len() != 1 || values[0].1 != expected {
            return Err(Error("Login do app incompatível com Umbrel 2.0."));
        }
    }
    let paths: Vec<_> = pairs.iter().filter(|p| p.0 == "path").collect();
    if paths.len() != 1 || !safe_path(&paths[0].1) {
        return Err(Error("Retorno do login inválido."));
    }
    url.set_path("/v1/account/login");
    Ok(url)
}
fn safe_path(value: &str) -> bool {
    value.starts_with('/')
        && !value.starts_with("//")
        && !value.contains('\\')
        && !value.chars().any(char::is_control)
}
pub fn validate_handoff(config: &Config, value: &Value) -> Result<(Url, String, String)> {
    let url = Url::parse(value["url"].as_str().unwrap_or(""))
        .map_err(|_| Error("Handoff de login inválido."))?;
    let base = config.url();
    let target = value["params"]["r"].as_str().unwrap_or("");
    let handoff = value["params"]["handoff"].as_str().unwrap_or("");
    if url.origin() != base.origin()
        || url.path() != "/umbrel_/api/v1/auth/handoff"
        || url.query().is_some()
        || url.fragment().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
        || !safe_path(target)
        || handoff.is_empty()
        || handoff.len() > 8192
        || handoff.chars().any(char::is_control)
    {
        return Err(Error("Handoff apontou para um destino inesperado."));
    }
    Ok((url, target.into(), handoff.into()))
}
pub fn dashboard_token(html: &str) -> Result<String> {
    let part = html
        .split_once("window.__HERMES_SESSION_TOKEN__")
        .ok_or(Error("Esta versão exige outra autenticação do Hermes."))?
        .1;
    let literal = part
        .trim_start()
        .strip_prefix('=')
        .ok_or(Error("Token do Hermes inválido."))?
        .trim_start();
    let mut stream = serde_json::Deserializer::from_str(literal).into_iter::<Value>();
    let value = stream
        .next()
        .ok_or(Error("Token do Hermes ausente."))?
        .map_err(|_| Error("Token do Hermes inválido."))?;
    let token = value.as_str().ok_or(Error("Token do Hermes inválido."))?;
    if token.is_empty()
        || token.len() > 4096
        || token.chars().any(|c| c.is_control() || c.is_whitespace())
    {
        return Err(Error("Token do Hermes inválido."));
    }
    Ok(token.into())
}
