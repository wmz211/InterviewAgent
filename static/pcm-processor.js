/**
 * AudioWorklet processor: captures mic audio and resamples to 16kHz PCM Int16.
 * Accumulates samples into ~100ms chunks before posting to avoid tiny packets.
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._targetRate = 16000;
    this._ratio = null;
    // Buffer accumulator — flush when >= 1600 samples (100ms at 16kHz)
    this._buf = new Float32Array(0);
    this._flushAt = 1600; // samples at target rate
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || !input[0].length) return true;

    const samples = input[0]; // Float32Array at native rate

    if (this._ratio === null) {
      this._ratio = sampleRate / this._targetRate;
    }

    // Downsample current frame
    const outLen = Math.floor(samples.length / this._ratio);
    const downsampled = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const src = i * this._ratio;
      const lo = Math.floor(src);
      const hi = Math.min(lo + 1, samples.length - 1);
      downsampled[i] = samples[lo] * (1 - (src - lo)) + samples[hi] * (src - lo);
    }

    // Accumulate
    const merged = new Float32Array(this._buf.length + downsampled.length);
    merged.set(this._buf);
    merged.set(downsampled, this._buf.length);
    this._buf = merged;

    // Flush when accumulated enough
    if (this._buf.length >= this._flushAt) {
      const i16 = new Int16Array(this._buf.length);
      for (let i = 0; i < this._buf.length; i++) {
        i16[i] = Math.max(-32768, Math.min(32767, this._buf[i] * 32768));
      }
      this.port.postMessage(i16.buffer, [i16.buffer]);
      this._buf = new Float32Array(0);
    }

    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
