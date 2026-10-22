class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.offset = 0;
    this.port.onmessage = (event) => {
      if (event.data === "flush") {
        this.flush();
      }
    };
  }

  flush() {
    if (!this.offset) {
      return;
    }
    const chunk = this.buffer.slice(0, this.offset);
    this.port.postMessage(chunk, [chunk.buffer]);
    this.offset = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) {
      return true;
    }
    for (let index = 0; index < channel.length; index += 1) {
      this.buffer[this.offset] = channel[index];
      this.offset += 1;
      if (this.offset === this.buffer.length) {
        this.flush();
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
