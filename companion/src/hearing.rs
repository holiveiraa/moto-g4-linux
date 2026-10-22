// SPDX-License-Identifier: MIT
//! Local voice boundaries. This module has no HTTP, WebSocket, key or backend.
use serde_json::Value;
use std::collections::VecDeque;

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
pub fn valid_wake(result: &Value) -> bool {
    // One measured tiny-model phonetic variant, never broad fuzzy matching.
    let phrase = normalized(result["text"].as_str().unwrap_or(""));
    let threshold = match phrase.as_str() {
        "ola hermes" | "ola ermes" => 0.40,
        "ula hermes" => 0.45,
        _ => return false,
    };
    result["probability"]
        .as_f64()
        .is_some_and(|p| (threshold..=1.0).contains(&p))
        && result["no_speech"]
            .as_f64()
            .is_some_and(|p| (0.0..=0.45).contains(&p))
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
