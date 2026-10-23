// SPDX-License-Identifier: MIT
//! HTTP is confined to a known peer through the phone's existing Tailscale TUN.
use crate::{Error, Result};
use reqwest::{blocking::Client, redirect::Policy};
use serde_json::Value;
use socket2::{Domain, Protocol, Socket, Type};
use std::{
    fs,
    io::Read,
    net::{IpAddr, SocketAddr, TcpStream},
    os::{
        fd::AsRawFd,
        unix::fs::{FileTypeExt, MetadataExt},
    },
    path::Path,
    time::Duration,
};
use url::{Host, Url};

pub const INTERFACE: &str = "tailscale0";
const LOCAL_SOCKET: &str = "/run/tailscale/tailscaled.sock";
pub const REQUIRED: Error = Error("HTTP exige o IP de um dispositivo da sua Tailscale, com a VPN conectada neste Moto. Não houve conexão pela rede comum.");

pub fn is_tailnet_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let b = v4.octets();
            b[0] == 100 && (64..128).contains(&b[1])
        }
        IpAddr::V6(v6) => v6.segments()[..3] == [0xfd7a, 0x115c, 0xa1e0],
    }
}

/// None means authenticated HTTPS or a literal loopback test, never HTTP DNS.
pub fn candidate(url: &Url) -> Result<Option<IpAddr>> {
    if url.scheme() == "https" {
        return Ok(None);
    }
    let ip = match url.host() {
        Some(Host::Ipv4(ip)) => IpAddr::V4(ip),
        Some(Host::Ipv6(ip)) => IpAddr::V6(ip),
        _ => return Err(REQUIRED),
    };
    if url.scheme() != "http" {
        return Err(REQUIRED);
    }
    if matches!(ip, IpAddr::V4(ip) if ip.octets() == [127,0,0,1])
        || ip == IpAddr::V6(std::net::Ipv6Addr::LOCALHOST)
    {
        return Ok(None);
    }
    if is_tailnet_ip(ip) {
        Ok(Some(ip))
    } else {
        Err(REQUIRED)
    }
}

pub fn validate_peer(status: &Value, ip: IpAddr) -> Result<()> {
    let contains = |value: &Value| {
        value.as_array().is_some_and(|items| {
            items
                .iter()
                .any(|item| item.as_str().and_then(|s| s.parse::<IpAddr>().ok()) == Some(ip))
        })
    };
    if status["BackendState"] != "Running"
        || status["TUN"] != true
        || !is_tailnet_ip(ip)
        || !status["Peer"].as_object().is_some_and(|peers| {
            peers
                .values()
                .any(|peer| peer["Online"] == true && contains(&peer["TailscaleIPs"]))
        })
    {
        return Err(REQUIRED);
    }
    Ok(())
}

fn local_status(path: &Path, owner: u32) -> Result<Value> {
    let meta = fs::symlink_metadata(path).map_err(|_| REQUIRED)?;
    let parent = fs::symlink_metadata(path.parent().ok_or(REQUIRED)?).map_err(|_| REQUIRED)?;
    if !meta.file_type().is_socket()
        || meta.uid() != owner
        || !parent.is_dir()
        || parent.uid() != owner
        || parent.mode() & 0o022 != 0
    {
        return Err(REQUIRED);
    }
    let socket = Socket::new(Domain::UNIX, Type::STREAM, None).map_err(|_| REQUIRED)?;
    let address = socket2::SockAddr::unix(path).map_err(|_| REQUIRED)?;
    socket
        .connect_timeout(&address, Duration::from_secs(2))
        .map_err(|_| REQUIRED)?;
    let mut credentials = libc::ucred {
        pid: 0,
        uid: u32::MAX,
        gid: u32::MAX,
    };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // LocalAPI identity comes from the kernel, not from an HTTP header or JSON.
    let result = unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut credentials as *mut libc::ucred).cast(),
            &mut length,
        )
    };
    if result != 0
        || length as usize != std::mem::size_of::<libc::ucred>()
        || credentials.uid != owner
    {
        return Err(REQUIRED);
    }
    drop(socket);
    let client = Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .unix_socket(path)
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|_| REQUIRED)?;
    let mut response = client
        .get("http://local-tailscaled.sock/localapi/v0/status")
        .send()
        .map_err(|_| REQUIRED)?;
    if !response.status().is_success() {
        return Err(REQUIRED);
    }
    let mut data = Vec::new();
    response
        .by_ref()
        .take(1024 * 1024 + 1)
        .read_to_end(&mut data)
        .map_err(|_| REQUIRED)?;
    if data.len() > 1024 * 1024 {
        return Err(REQUIRED);
    }
    serde_json::from_slice(&data).map_err(|_| REQUIRED)
}

pub fn verify(url: &Url) -> Result<Option<IpAddr>> {
    let Some(ip) = candidate(url)? else {
        return Ok(None);
    };
    validate_peer(&local_status(Path::new(LOCAL_SOCKET), 0)?, ip)?;
    // Check before every HTTP request, including reuse of a pooled socket.
    // SO_BINDTODEVICE remains the kernel-enforced route boundary at I/O time.
    let flags = fs::read_to_string("/sys/class/net/tailscale0/flags").map_err(|_| REQUIRED)?;
    let flags =
        u32::from_str_radix(flags.trim().trim_start_matches("0x"), 16).map_err(|_| REQUIRED)?;
    if flags & libc::IFF_UP as u32 == 0 {
        return Err(REQUIRED);
    }
    Ok(Some(ip))
}

pub(crate) fn connect_bound(address: SocketAddr) -> Result<TcpStream> {
    let socket = Socket::new(
        Domain::for_address(address),
        Type::STREAM,
        Some(Protocol::TCP),
    )
    .map_err(|_| REQUIRED)?;
    socket
        .bind_device(Some(INTERFACE.as_bytes()))
        .map_err(|_| REQUIRED)?;
    socket
        .connect_timeout(&address.into(), Duration::from_secs(5))
        .map_err(|_| REQUIRED)?;
    Ok(socket.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::{io::Write, os::unix::net::UnixListener, thread};

    #[test]
    fn a_cgnat_address_alone_is_not_a_verified_encrypted_peer() {
        let ip: IpAddr = "100.64.0.10".parse().unwrap();
        let good = json!({"BackendState":"Running","TUN":true,"Peer":{"node":{"Online":true,"TailscaleIPs":["100.64.0.10"]}}});
        assert!(validate_peer(&good, ip).is_ok());
        for bad in [
            json!({}),
            json!({"BackendState":"Running","TUN":true,"Peer":{}}),
            {
                let mut value = good.clone();
                value["BackendState"] = json!("Stopped");
                value
            },
            {
                let mut value = good.clone();
                value["TUN"] = json!(false);
                value
            },
            {
                let mut value = good.clone();
                value["Peer"]["node"]["Online"] = json!(false);
                value
            },
            {
                let mut value = good.clone();
                value["Peer"]["node"]["TailscaleIPs"] = json!(["100.64.0.11"]);
                value["Peer"]["node"]["AllowedIPs"] = json!(["100.64.0.0/10"]);
                value
            },
        ] {
            assert_eq!(validate_peer(&bad, ip), Err(REQUIRED));
        }
    }

    #[test]
    fn http_cannot_use_lan_dns_or_a_fake_tailnet_range() {
        for url in [
            "http://192.168.1.10/",
            "http://server.example/",
            "http://localhost/",
            "http://100.128.0.1/",
            "http://[fd7a:115c:a1e1::10]/",
        ] {
            assert_eq!(candidate(&Url::parse(url).unwrap()), Err(REQUIRED));
        }
        for url in [
            "https://server.example/",
            "http://127.0.0.1/",
            "http://[::1]/",
        ] {
            assert_eq!(candidate(&Url::parse(url).unwrap()), Ok(None));
        }
        assert_eq!(
            candidate(&Url::parse("http://100.64.0.10:18790/").unwrap()),
            Ok(Some("100.64.0.10".parse().unwrap()))
        );
    }

    #[test]
    fn localapi_is_bounded_and_decodes_chunked_http_without_external_network() {
        let root =
            std::env::temp_dir().join(format!("moto-tailnet-{}", crate::storage::id().unwrap()));
        fs::create_dir(&root).unwrap();
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let path = root.join("daemon.sock");
        let listener = UnixListener::bind(&path).unwrap();
        let thread = thread::spawn(move || {
            // First connection proves SO_PEERCRED; second carries LocalAPI HTTP.
            drop(listener.accept().unwrap());
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut request = [0; 4096];
            let n = stream.read(&mut request).unwrap();
            assert!(String::from_utf8_lossy(&request[..n]).starts_with("GET /localapi/v0/status "));
            let body = b"{\"BackendState\":\"Running\",\"TUN\":true}";
            write!(stream,"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n{:x}\r\n",body.len()).unwrap();
            stream.write_all(body).unwrap();
            stream.write_all(b"\r\n0\r\n\r\n").unwrap();
        });
        assert_eq!(
            local_status(&path, unsafe { libc::geteuid() }).unwrap()["TUN"],
            true
        );
        thread.join().unwrap();
        assert_eq!(
            local_status(&path, unsafe { libc::geteuid() }.wrapping_add(1)),
            Err(REQUIRED)
        );
        fs::remove_dir_all(root).unwrap();
    }
}
