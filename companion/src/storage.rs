// SPDX-License-Identifier: MIT
use crate::{Error, Result};
use serde_json::Value;
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::Path,
};

pub fn id() -> Result<String> {
    let mut bytes = [0u8; 16];
    getrandom::getrandom(&mut bytes)
        .map_err(|_| Error("Aleatoriedade do sistema indisponível."))?;
    Ok(bytes.iter().map(|n| format!("{n:02x}")).collect())
}
fn no_symlinks(path: &Path) -> Result<()> {
    for p in path.ancestors() {
        if fs::symlink_metadata(p).is_ok_and(|m| m.file_type().is_symlink()) {
            return Err(Error("A configuração privada não aceita links simbólicos."));
        }
    }
    Ok(())
}
pub fn load(path: &Path) -> Result<Value> {
    no_symlinks(path)?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|_| Error("Configuração não encontrada; configure o Hermes no painel."))?;
    let metadata = file
        .metadata()
        .map_err(|_| Error("Configuração inválida."))?;
    if !metadata.is_file() || metadata.len() > 65536 || metadata.permissions().mode() & 0o077 != 0 {
        return Err(Error(
            "A configuração deve ser um arquivo privado (0600), de até 64 KiB.",
        ));
    }
    let mut data = Vec::new();
    file.read_to_end(&mut data)
        .map_err(|_| Error("Não foi possível ler a configuração."))?;
    serde_json::from_slice(&data).map_err(|_| Error("Configuração JSON inválida."))
}
pub fn save(path: &Path, value: &Value) -> Result<()> {
    no_symlinks(path)?;
    let parent = path.parent().ok_or(Error("Destino privado inválido."))?;
    fs::create_dir_all(parent).map_err(|_| Error("Não foi possível criar a pasta privada."))?;
    no_symlinks(path)?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
        .map_err(|_| Error("Não foi possível proteger a pasta."))?;
    let temporary = parent.join(format!(".hermes-{}", id()?));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)
            .map_err(|_| Error("Não foi possível salvar a sessão."))?;
        serde_json::to_writer(&mut file, value)
            .map_err(|_| Error("Não foi possível salvar a sessão."))?;
        file.write_all(b"\n")
            .and_then(|_| file.sync_all())
            .map_err(|_| Error("Não foi possível sincronizar a sessão."))?;
        fs::rename(&temporary, path).map_err(|_| Error("Não foi possível substituir a sessão."))?;
        fs::File::open(parent)
            .and_then(|f| f.sync_all())
            .map_err(|_| Error("Não foi possível sincronizar a pasta."))
    })();
    let _ = fs::remove_file(temporary);
    result
}
