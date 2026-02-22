/**
 * AudioWorklet processor for real-time microphone capture.
 * Buffers incoming audio samples and posts Float32Array chunks
 * to the main thread for encoding and WebSocket transmission.
 */
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._samples = [];
    this._bufferSize = 4096;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0];
    for (let i = 0; i < channelData.length; i++) {
      this._samples.push(channelData[i]);
    }

    if (this._samples.length >= this._bufferSize) {
      const chunk = new Float32Array(this._samples);
      this._samples = [];
      this.port.postMessage(chunk, [chunk.buffer]);
    }

    return true;
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor);
