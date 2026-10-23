// SPDX-License-Identifier: MIT
use moto_hermes::{auth, config::Config, face, protocol, state::Turn, storage};
use serde_json::json;

#[test]
fn production_endpoint_refuses_plaintext_credentials_and_ambiguous_urls() {
    for url in [
        "http://server.example:18789",
        "https://user:pass@server.example",
        "https://server.example/#x",
        "https://server.example/?token=secret",
        "file:///etc/passwd",
    ] {
        assert!(Config::for_server(url).is_err(), "{url}");
    }
    assert!(Config::for_server("https://server.example:18789/").is_ok());
    assert!(Config::for_server("http://127.0.0.1:8000/").is_ok());
    assert!(Config::for_server("http://100.64.0.10:18790/").is_ok());
    assert!(Config::for_server("http://[fd7a:115c:a1e0::10]:18790/").is_ok());
    assert!(Config::for_server("http://192.168.1.10:18790/").is_err());
    assert!(Config::for_server("http://localhost:18790/").is_err());
}

#[test]
fn login_discovery_requires_expected_app_same_server_and_https() {
    let base = Config::for_server("https://server.example:18789/").unwrap();
    let good = "https://server.example:2000/app-auth?app=hermes-agent&origin=host&path=%2F";
    let login = auth::login_target(&base, good).unwrap();
    assert_eq!(login.path(), "/v1/account/login");
    for bad in [
        good.replace("server.example:2000", "evil.example"),
        good.replace(":2000", ":3000"),
        good.replace("https:", "http:"),
        good.replace("hermes-agent", "other-app"),
        good.replace("origin=host", "origin=tor"),
        format!("{good}&app=other"),
    ] {
        assert!(auth::login_target(&base, &bad).is_err());
    }
}

#[test]
fn handoff_cannot_forward_private_data_to_another_origin() {
    let config = Config::for_server("https://server.example:18789/").unwrap();
    let good = json!({"url":"https://server.example:18789/umbrel_/api/v1/auth/handoff","params":{"r":"/","handoff":"fixture-one-use"}});
    assert!(auth::validate_handoff(&config, &good).is_ok());
    for url in [
        "https://evil.example/umbrel_/api/v1/auth/handoff",
        "http://server.example:18789/umbrel_/api/v1/auth/handoff",
        "https://server.example:18789/other",
    ] {
        let mut value = good.clone();
        value["url"] = json!(url);
        assert!(auth::validate_handoff(&config, &value).is_err());
    }
    let mut value = good;
    value["params"]["r"] = json!("//evil.example");
    assert!(auth::validate_handoff(&config, &value).is_err());
}

#[test]
fn dashboard_token_parser_reads_json_without_executing_javascript() {
    assert_eq!(
        auth::dashboard_token(
            "<script>window.__HERMES_SESSION_TOKEN__=\"fixture-token\";</script>"
        )
        .unwrap(),
        "fixture-token"
    );
    assert!(auth::dashboard_token("window.__HERMES_SESSION_TOKEN__=stealCookies()").is_err());
    assert!(auth::dashboard_token("window.__HERMES_SESSION_TOKEN__=\"x\\nInjected\"").is_err());
}

#[test]
fn an_uncertain_turn_is_not_automatically_resubmitted() {
    let mut turn = Turn::default();
    turn.begin("request-1").unwrap();
    assert!(turn.begin("request-2").is_err());
    turn.accept();
    turn.disconnected();
    assert!(turn.begin("request-1").is_err());
    assert!(turn.begin("request-2").is_err());
    assert!(turn.uncertain());
}

#[test]
fn only_an_observed_final_event_settles_work() {
    let mut turn = Turn::default();
    turn.begin("one").unwrap();
    turn.accept();
    turn.request_stop();
    assert!(turn.busy());
    turn.complete();
    assert!(!turn.busy());
    assert!(!turn.uncertain());
    assert!(turn.begin("two").is_ok());
}

#[test]
fn gateway_events_are_scoped_and_never_expose_reasoning_or_tool_payloads() {
    let mut stream = protocol::Reply::new("moto-runtime");
    stream.bind("owned-admission", Some(1));
    for event in [
        json!({"method":"event","params":{"type":"message.complete","session_id":"telegram","payload":{"text":"private-other-chat"}}}),
        json!({"method":"event","params":{"type":"message.complete","session_id":"moto-runtime","admission_id":"previous-admission","execution_generation":1,"payload":{"text":"previous turn"}}}),
        json!({"method":"event","params":{"type":"message.complete","session_id":"moto-runtime","admission_id":"owned-admission","execution_generation":2,"payload":{"text":"wrong generation"}}}),
        json!({"method":"event","params":{"type":"reasoning.delta","session_id":"moto-runtime","payload":{"text":"private-reasoning"}}}),
        json!({"method":"event","params":{"type":"tool.end","session_id":"moto-runtime","payload":{"text":"tool-secret"}}}),
        json!({"method":"message.delta","params":{"session_id":"telegram","text":"private-other-chat"}}),
        json!({"method":"reasoning.delta","params":{"session_id":"moto-runtime","text":"private-reasoning"}}),
        json!({"method":"tool.end","params":{"session_id":"moto-runtime","output":"tool-secret"}}),
    ] {
        assert!(stream.feed(&event).unwrap().is_none());
    }
    let event = json!({"method":"event","params":{"type":"message.complete","session_id":"moto-runtime","admission_id":"owned-admission","execution_generation":1,"payload":{"text":"Olá, ação concluída."}}});
    assert_eq!(
        stream.feed(&event).unwrap().unwrap(),
        "Olá, ação concluída."
    );
    assert!(stream.feed(&event).unwrap().is_none());
}

#[test]
fn externally_cancelled_owned_queue_can_complete_without_an_execution_generation() {
    let mut reply = protocol::Reply::new("moto-runtime");
    reply.bind("owned", None);
    assert!(reply.feed(&json!({"method":"event","params":{"session_id":"moto-runtime","admission_id":"owned","type":"message.complete","payload":{"text":"unverified success"}}})).unwrap().is_none());
    assert_eq!(reply.feed(&json!({"method":"event","params":{"session_id":"moto-runtime","admission_id":"owned","type":"message.complete","payload":{"outcome":"cancelled","text":""}}})).unwrap(), Some(String::new()));
    assert!(reply.cancelled);
}

#[test]
fn concatenated_rpc_frames_and_oversized_input_are_handled_deliberately() {
    assert_eq!(protocol::frames("{\"id\":1}\n{\"id\":2}").unwrap().len(), 2);
    assert!(protocol::frames("{broken").is_err());
    assert!(protocol::frames(&"x".repeat(protocol::MAX_FRAME + 1)).is_err());
}

#[test]
fn pcm_metadata_and_chunks_are_bounded_before_playback() {
    assert_eq!(
        protocol::pcm_start(&json!({"type":"start","sample_rate":24000,"channels":1})).unwrap(),
        24000
    );
    for value in [
        json!({"type":"start","sample_rate":0,"channels":1}),
        json!({"type":"start","sample_rate":48000,"channels":2}),
        json!({"type":"start","sample_rate":192000,"channels":1}),
    ] {
        assert!(protocol::pcm_start(&value).is_err());
    }
    assert!(protocol::validate_pcm(&[0, 1, 2]).is_err());
    assert!(protocol::validate_pcm(&vec![0; 262146]).is_err());
}

#[test]
fn face_is_a_bounded_software_image_and_states_are_distinct() {
    let idle = face::render("ready", 160, 0).unwrap();
    assert!(idle.starts_with(b"P6\n160 160\n255\n"));
    assert_ne!(idle, face::render("speaking", 160, 2).unwrap());
    assert!(face::render("ready", 4096, 0).is_err());
    assert!(face::render("untrusted-state", 160, 0).is_err());
}

#[test]
fn private_json_is_atomic_owner_only_and_symlinks_are_refused() {
    let root = std::env::temp_dir().join(format!("moto-hermes-test-{}", storage::id().unwrap()));
    std::fs::create_dir(&root).unwrap();
    let path = root.join("session.json");
    storage::save(&path, &json!({"fixture":true})).unwrap();
    use std::os::unix::fs::{symlink, PermissionsExt};
    assert_eq!(
        std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    let link = root.join("symlink.json");
    symlink(&path, &link).unwrap();
    assert!(storage::save(&link, &json!({"fixture":false})).is_err());
    assert_eq!(storage::load(&path).unwrap()["fixture"], true);
    std::fs::remove_dir_all(root).unwrap();
}
