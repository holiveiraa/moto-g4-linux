// SPDX-License-Identifier: MIT
use moto_hermes::{
    face,
    hearing::{self, Segmenter, FRAME_SAMPLES},
};
use serde_json::json;

#[test]
fn wake_requires_the_whole_phrase_speech_and_probability() {
    assert!(hearing::valid_wake(
        &json!({"text":" Olá, Hermes!","probability":0.85,"no_speech":0.02})
    ));
    assert!(hearing::valid_wake(
        &json!({"text":"Ula Hermes.","probability":0.49,"no_speech":0.001})
    ));
    assert!(!hearing::valid_wake(
        &json!({"text":"Ula Maria.","probability":0.9,"no_speech":0.001})
    ));
    for value in [
        json!({"text":"Olá Maria","probability":0.9,"no_speech":0.01}),
        json!({"text":"Olá Hermes e o resto da televisão","probability":0.9,"no_speech":0.01}),
        json!({"text":"Olá Hermes","probability":0.2,"no_speech":0.01}),
        json!({"text":"Olá Hermes","probability":0.9,"no_speech":0.8}),
        json!({"text":"Olá Hermes"}),
    ] {
        assert!(!hearing::valid_wake(&value));
    }
}
#[test]
fn commands_are_exact_utterances_not_substrings_in_a_request() {
    assert_eq!(hearing::action("Nova conversa!"), Some("new_session"));
    assert_eq!(
        hearing::action("Hermes, nova conversa"),
        Some("new_session")
    );
    assert_eq!(hearing::action("Fechar aplicativo"), Some("close"));
    assert_eq!(hearing::action("Voltar a dormir"), Some("sleep"));
    assert_eq!(
        hearing::action("Explique o que significa nova conversa"),
        None
    );
}
#[test]
fn constant_background_is_not_accepted_as_an_utterance() {
    for level in [200, 1500] {
        let mut vad = Segmenter::new(1);
        for _ in 0..500 {
            assert!(vad.feed(&[level; FRAME_SAMPLES]).is_none());
        }
    }
}
#[test]
fn fullscreen_vector_pose_animates_idle_and_has_no_large_bitmap() {
    let a = face::pose("standby", 0).unwrap();
    let b = face::pose("standby", 10).unwrap();
    assert_ne!(a, b);
    assert!(a.to_string().len() < 1000);
    assert_ne!(
        face::pose("speaking", 3).unwrap(),
        face::pose("listening", 3).unwrap()
    );
}
