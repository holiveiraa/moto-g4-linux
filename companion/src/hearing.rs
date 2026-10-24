// SPDX-License-Identifier: MIT
//! Local voice boundaries. This module has no HTTP, WebSocket, key or backend.
use serde_json::Value;
use std::collections::VecDeque;

/// Fixed-rate 48 -> 16 kHz decimation, with an antialias low-pass before
/// dropping samples. A three-sample box average folds high-frequency capture
/// noise into the speech band. This 129-tap Blackman-windowed sinc has a 7 kHz
/// cutoff, unity DC gain and preserves sample count/timing. No AGC or model bias.
pub fn wake_pcm(audio: &[i16]) -> Vec<i16> {
    const HALF: isize = 64;
    static COEFFICIENTS: std::sync::OnceLock<[f64; 129]> = std::sync::OnceLock::new();
    let coefficients = COEFFICIENTS.get_or_init(|| {
        let mut values = [0.0; 129];
        for (i, value) in values.iter_mut().enumerate() {
            let j = i as f64 - HALF as f64;
            let x = 2.0 * 7000.0 / 48000.0 * j;
            let sinc = if i == HALF as usize {
                1.0
            } else {
                (std::f64::consts::PI * x).sin() / (std::f64::consts::PI * x)
            };
            let window = 0.42
                + 0.5 * (std::f64::consts::PI * j / HALF as f64).cos()
                + 0.08 * (std::f64::consts::TAU * j / HALF as f64).cos();
            *value = 2.0 * 7000.0 / 48000.0 * sinc * window;
        }
        let sum: f64 = values.iter().sum();
        for value in &mut values {
            *value /= sum;
        }
        values
    });
    (0..audio.len() / 3)
        .map(|n| {
            let center = (n * 3 + 1) as isize;
            let value: f64 = coefficients
                .iter()
                .enumerate()
                .filter_map(|(i, c)| {
                    let position = center + i as isize - HALF;
                    (position >= 0)
                        .then(|| audio.get(position as usize))
                        .flatten()
                        .map(|s| *s as f64 * c)
                })
                .sum();
            value.round().clamp(i16::MIN as f64, i16::MAX as f64) as i16
        })
        .collect()
}

pub const FRAME_SAMPLES: usize = 960; // 20 ms at native capture 48 kHz.

pub fn normalized(text: &str) -> String {
    text.to_lowercase()
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'â' | 'ã' | 'ä' => 'a',
            'é' | 'ê' | 'è' | 'ë' => 'e',
            'í' | 'ì' | 'î' | 'ï' => 'i',
            'ó' | 'ô' | 'õ' | 'ò' | 'ö' => 'o',
            'ú' | 'ü' | 'ù' | 'û' => 'u',
            'ç' => 'c',
            c if c.is_alphanumeric() => c,
            _ => ' ',
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
fn wake_threshold(result: &Value) -> Option<f64> {
    // One measured tiny-model phonetic variant, never broad fuzzy matching.
    let phrase = normalized(result["text"].as_str().unwrap_or(""));
    match phrase.as_str() {
        "ola hermes" | "ola ermes" => Some(0.40),
        "ula hermes" => Some(0.45),
        _ => None,
    }
}
pub fn valid_wake(result: &Value) -> bool {
    let Some(threshold) = wake_threshold(result) else {
        return false;
    };
    result["probability"]
        .as_f64()
        .is_some_and(|p| (threshold..=1.0).contains(&p))
        && result["no_speech"]
            .as_f64()
            .is_some_and(|p| (0.0..=0.45).contains(&p))
}

/// One bounded decision, without ambient text or audio. Never forward the
/// recognizer's object: future helper fields may contain private material.
pub fn wake_diagnostic(result: &Value, audio: &[i16]) -> Value {
    let energy: f64 = audio.iter().map(|s| (*s as f64).powi(2)).sum();
    let probability = |key: &str| result[key].as_f64().filter(|v| (0.0..=1.0).contains(v));
    serde_json::json!({
        "capture_ms": audio.len() as u64 * 1000 / 48000,
        "peak": audio.iter().map(|s| i32::from(*s).unsigned_abs()).max().unwrap_or(0),
        "rms": (energy / audio.len().max(1) as f64).sqrt().round() as u64,
        "clipped_samples": audio.iter().filter(|s| i32::from(**s).unsigned_abs() >= 32760).count(),
        "accepted": valid_wake(result),
        "phrase_match": wake_threshold(result).is_some(),
        "probability": probability("probability"),
        "no_speech": probability("no_speech"),
        "milliseconds": result["milliseconds"].as_u64().filter(|v| *v <= 25000),
    })
}
pub fn action(text: &str) -> Option<&'static str> {
    match normalized(text).as_str() {
        "nova conversa" | "hermes nova conversa" => Some("new_session"),
        "fechar aplicativo" | "encerrar aplicativo" | "fechar hermes" | "voltar ao terminal" => {
            Some("close")
        }
        "voltar a dormir" | "hermes dormir" | "parar de ouvir" => Some("sleep"),
        _ => None,
    }
}

/// Bounded automatic endpointing. Noise/silence never invokes recognition.
pub struct Segmenter {
    vad: webrtc_vad::Vad,
    lead: VecDeque<i16>,
    audio: Vec<i16>,
    onset: usize,
    voiced: usize,
    quiet: usize,
    max_samples: usize,
}
impl Segmenter {
    pub fn new(seconds: usize) -> Self {
        Self {
            vad: webrtc_vad::Vad::new_with_rate_and_mode(
                webrtc_vad::SampleRate::Rate48kHz,
                webrtc_vad::VadMode::Aggressive,
            ),
            lead: VecDeque::new(),
            audio: Vec::new(),
            onset: 0,
            voiced: 0,
            quiet: 0,
            max_samples: seconds.clamp(1, 45) * 48000,
        }
    }
    pub fn feed(&mut self, frame: &[i16]) -> Option<Vec<i16>> {
        if frame.len() != FRAME_SAMPLES {
            return None;
        }
        let speech = self.vad.is_voice_segment(frame).unwrap_or(false);
        self.feed_decision(frame, speech)
    }
    fn feed_decision(&mut self, frame: &[i16], speech: bool) -> Option<Vec<i16>> {
        if self.audio.is_empty() {
            self.lead.extend(frame);
            while self.lead.len() > FRAME_SAMPLES * 15 {
                self.lead.pop_front();
            }
            if !speech {
                self.onset = 0;
                return None;
            }
            self.onset += 1;
            if self.onset < 3 {
                return None;
            }
            self.audio.extend(self.lead.drain(..));
            self.voiced = 3;
            self.quiet = 0;
            return None;
        }
        self.audio.extend_from_slice(frame);
        if speech {
            self.voiced += 1;
            self.quiet = 0;
        } else {
            self.quiet += 1;
        }
        if self.quiet >= 35 || self.audio.len() >= self.max_samples {
            let audio = std::mem::take(&mut self.audio);
            let valid = self.voiced >= 12;
            self.onset = 0;
            self.voiced = 0;
            self.quiet = 0;
            self.lead.clear();
            return valid.then_some(audio);
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn endpointing_needs_speech_then_silence_and_never_runs_on_silence() {
        let mut vad = Segmenter::new(45);
        for _ in 0..500 {
            assert!(vad.feed_decision(&[0; FRAME_SAMPLES], false).is_none());
        }
        for _ in 0..25 {
            assert!(vad.feed_decision(&[1500; FRAME_SAMPLES], true).is_none());
        }
        let mut result = None;
        for _ in 0..36 {
            result = vad.feed_decision(&[0; FRAME_SAMPLES], false).or(result);
        }
        assert!(result.unwrap().len() > FRAME_SAMPLES * 25);
        for _ in 0..100 {
            assert!(vad.feed_decision(&[0; FRAME_SAMPLES], false).is_none());
        }
    }
    #[test]
    fn brief_clicks_are_discarded_and_long_audio_is_bounded() {
        let mut vad = Segmenter::new(1);
        for _ in 0..4 {
            assert!(vad.feed_decision(&[2000; FRAME_SAMPLES], true).is_none());
        }
        for _ in 0..40 {
            assert!(vad.feed_decision(&[0; FRAME_SAMPLES], false).is_none());
        }
        let mut found = None;
        for _ in 0..60 {
            if let Some(a) = vad.feed_decision(&[2000; FRAME_SAMPLES], true) {
                found = Some(a);
                break;
            }
        }
        assert!(found.unwrap().len() <= 48000 + FRAME_SAMPLES);
    }
}
