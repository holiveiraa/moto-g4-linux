// SPDX-License-Identifier: MIT
//! Original CPU rasterizer. Tk hosts the returned PPM; no GPU, browser or SDL runtime.
use crate::{Error, Result};
use serde_json::{json, Value};

/// Small vector pose for the fullscreen native canvas. No per-frame bitmap
/// scaling or copied Arduino artwork; animation geometry is original Rust.
pub fn pose(state: &str, tick: u32) -> Result<Value> {
    if ![
        "ready",
        "standby",
        "connecting",
        "listening",
        "transcribing",
        "thinking",
        "speaking",
        "approval",
        "error",
        "disconnected",
    ]
    .contains(&state)
    {
        return Err(Error("Estado da face inválido."));
    }
    let t = tick as f64;
    let blink = match tick % 113 {
        106 => 0.65,
        107 => 0.25,
        108 | 109 => 0.04,
        110 => 0.25,
        111 => 0.65,
        _ => 1.0,
    };
    let gaze_x = (t * 0.037).sin() * 0.022;
    let breath = (t * 0.045).sin() * 0.007;
    let height = match state {
        "standby" => 0.075,
        "listening" => 0.23,
        "thinking" | "transcribing" => 0.14,
        "error" => 0.12,
        _ => 0.19,
    } * blink;
    let color = match state {
        "error" => "#ff9c9c",
        "approval" => "#f7ca78",
        "disconnected" | "connecting" => "#9eb5d2",
        "standby" => "#65d1c9",
        _ => "#7ff5cd",
    };
    let y = 0.40 + breath + if state == "thinking" { -0.025 } else { 0.0 };
    let mouth = if state == "speaking" {
        0.025 + (t * 0.9).sin().abs() * 0.060
    } else {
        0.0
    };
    Ok(
        json!({"eyes":[[0.285+gaze_x,y,0.235,height],[0.715+gaze_x,y,0.235,height]],"mouth":mouth,"smile":state!="error","accent":color,"breath":breath,"state":state}),
    )
}
pub fn render(state: &str, size: usize, tick: u32) -> Result<Vec<u8>> {
    if !(64..=320).contains(&size) {
        return Err(Error("Tamanho da face inválido."));
    }
    if ![
        "ready",
        "connecting",
        "listening",
        "transcribing",
        "thinking",
        "speaking",
        "approval",
        "error",
        "disconnected",
    ]
    .contains(&state)
    {
        return Err(Error("Estado da face inválido."));
    }
    let mut data = format!("P6\n{size} {size}\n255\n").into_bytes();
    let accent = match state {
        "error" => [248, 130, 143],
        "approval" => [244, 195, 106],
        "disconnected" => [148, 168, 191],
        _ => [86, 223, 177],
    };
    let blink = state == "ready" && tick % 47 >= 45;
    for y in 0..size {
        for x in 0..size {
            let px = x as f64 / size as f64;
            let py = y as f64 / size as f64;
            let ellipse = |cx: f64, cy: f64, rx: f64, ry: f64| {
                ((px - cx) / rx).powi(2) + ((py - cy) / ry).powi(2) <= 1.
            };
            let eye_y = if state == "thinking" { 0.37 } else { 0.41 };
            let eye_height = if blink {
                0.012
            } else if state == "listening" {
                0.095
            } else {
                0.065
            };
            let eyes =
                ellipse(0.34, eye_y, 0.05, eye_height) || ellipse(0.66, eye_y, 0.05, eye_height);
            let mouth = if state == "speaking" {
                ellipse(0.5, 0.67, 0.09, 0.025 + 0.012 * (tick % 5) as f64)
            } else if state == "error" {
                (px - 0.5).abs() < 0.09 && (py - 0.68).abs() < 0.012
            } else {
                let d = ((px - 0.5).powi(2) + (py - 0.57).powi(2)).sqrt();
                (0.12..=0.135).contains(&d) && py > 0.64
            };
            let radius = ((px - 0.5).powi(2) + (py - 0.5).powi(2)).sqrt();
            let ring = (0.435..=0.442).contains(&radius);
            let color = if eyes || mouth {
                accent
            } else if ring {
                [34, 57, 64]
            } else {
                [11, 17, 27]
            };
            data.extend_from_slice(&color);
        }
    }
    Ok(data)
}
