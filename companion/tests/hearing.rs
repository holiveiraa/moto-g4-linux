// SPDX-License-Identifier: MIT
use moto_hermes::{
    face,
    hearing::{self, Segmenter, FRAME_SAMPLES},
};
use serde_json::json;

#[test]
fn wake_diagnostics_exclude_ambient_words_and_bound_metrics() {
    let result = hearing::wake_diagnostic(
        &json!({"text":"private ambient words",
        "probability":0.9,"no_speech":0.01,"milliseconds":1800,"secret":"fixture-secret"}),
        &[1000; 48000],
    );
    assert_eq!(
        result,
        json!({"accepted":false,"phrase_match":false,
        "probability":0.9,"no_speech":0.01,"milliseconds":1800,
        "capture_ms":1000,"peak":1000,"rms":1000,"clipped_samples":0})
    );
    let invalid = hearing::wake_diagnostic(
        &json!({"text":"Olá Hermes",
        "probability":2,"no_speech":-1,"milliseconds":25001}),
        &[],
    );
    assert_eq!(
        invalid,
        json!({"accepted":false,"phrase_match":true,
        "probability":null,"no_speech":null,"milliseconds":null,
        "capture_ms":0,"peak":0,"rms":0,"clipped_samples":0})
    );
}

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

#[test]
fn wake_resampler_preserves_speech_band_and_rejects_folded_ultrasound() {
    fn signal(hz: f64) -> Vec<i16> {
        (0..48000)
            .map(|n| {
                (12000.0 * (std::f64::consts::TAU * hz * n as f64 / 48000.0).sin()).round() as i16
            })
            .collect()
    }
    fn rms(v: &[i16]) -> f64 {
        (v.iter().map(|s| (*s as f64).powi(2)).sum::<f64>() / v.len() as f64).sqrt()
    }
    let speech = hearing::wake_pcm(&signal(1000.0));
    let upper = hearing::wake_pcm(&signal(6000.0));
    let alias = hearing::wake_pcm(&signal(12000.0));
    assert_eq!(speech.len(), 16000);
    let inner = |v: &[i16]| rms(&v[100..v.len() - 100]);
    assert!((inner(&speech) - 8485.3).abs() < 20.0);
    assert!((inner(&upper) - 8485.3).abs() < 100.0);
    assert!(
        inner(&alias) < 8.5,
        "12 kHz must not alias into 4 kHz speech"
    );
    let dc = hearing::wake_pcm(&vec![10000; 48000]);
    assert!(dc[100..15900].iter().all(|s| (*s - 10000).abs() <= 1));
    assert!(hearing::wake_pcm(&[]).is_empty());
    assert_eq!(hearing::wake_pcm(&[0; 8]).len(), 2);
    let full = hearing::wake_pcm(&vec![i16::MAX; 48000]);
    assert!(full.iter().all(|s| *s >= 0));
}
