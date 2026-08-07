'use client'

// Real barge-in detection: while Billion is speaking, the normal STT
// pipeline (use-voice.ts) is deliberately silent for echo-avoidance --
// confirmed live as the actual reason the user couldn't interrupt her at
// all before this existed. This runs a separate, lightweight voice-activity
// detector (Silero VAD via @ricky0123/vad-web, WASM/ONNX, real speech
// detection -- not just an amplitude gate, which would false-trigger on
// Billion's own voice bleeding through speakers) on its own short-lived mic
// stream, ONLY while she's talking. The moment it confirms real speech
// (onSpeechRealStart -- fires only once a segment clears minSpeechMs, not
// on every noise blip), the caller is expected to stop her and resume
// normal listening; this module has no opinion on what happens next.
//
// echoCancellation/noiseSuppression/autoGainControl are requested explicitly
// on the VAD's own stream (browsers' real AEC operates on system audio
// output, not just what this page happens to be playing, but it needs to be
// asked for -- it is not on by default on a bare getUserMedia call).

import { MicVAD } from '@ricky0123/vad-web'

// CDN-hosted, not bundled: @ricky0123/vad-web's own real, documented
// quick-start (github.com/ricky0123/vad) points at these same jsdelivr
// paths for both the WASM runtime and the Silero model, specifically to
// avoid a bundler needing to know how to copy .onnx/.wasm binaries into a
// public asset directory. Version-pinned so a future upstream release can't
// silently change shape underneath this.
const ONNX_WASM_BASE_PATH = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/'
const VAD_ASSET_BASE_PATH = 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.30/dist/'

let activeVad: MicVAD | null = null
let starting: Promise<void> | null = null

/**
 * Starts watching the mic for real speech and calls `onInterrupt` the
 * instant it's confirmed (not on every noise blip -- see onSpeechRealStart
 * above). Safe to call while a previous watch is still starting/running;
 * only one real VAD instance is ever live at a time. Returns a stop
 * function that tears down the mic stream and the VAD instance -- always
 * call it the moment playback ends or an interrupt already fired, so the
 * mic isn't held open by two things at once.
 */
export function startInterruptWatch(onInterrupt: () => void): () => void {
  let stopped = false

  starting = (async () => {
    try {
      const vad = await MicVAD.new({
        onnxWASMBasePath: ONNX_WASM_BASE_PATH,
        baseAssetPath: VAD_ASSET_BASE_PATH,
        getStream: () =>
          navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          }),
        onSpeechRealStart: () => {
          if (!stopped) onInterrupt()
        },
        // Real speech-start, not just a raised eyebrow -- 200ms (a touch
        // above the library's own default) so a single cough or chair
        // creak during playback doesn't cut Billion off; still well under
        // the ~300-500ms a human perceives as "instant" for a genuine
        // interruption.
        minSpeechMs: 200,
      })
      if (stopped) {
        await vad.destroy()
        return
      }
      activeVad = vad
      await vad.start()
    } catch (err) {
      // Mic denied, no real audio device, or the CDN assets didn't load --
      // fail silently into "no barge-in this session" rather than breaking
      // the rest of voice mode, which works fine without this.
      console.warn('[interrupt-vad] could not start:', err)
    }
  })()

  return () => {
    stopped = true
    const vad = activeVad
    activeVad = null
    if (vad) void vad.destroy()
  }
}
