window.EmberSound = (function () {
  let ctx = null;
  let enabled = localStorage.getItem("emberplay_sound") !== "off";

  function getCtx() {
    if (!ctx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      ctx = new AudioContextClass();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function tone(freq, startTime, duration, type, gainPeak) {
    const audioCtx = getCtx();
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type || "sine";
    osc.frequency.setValueAtTime(freq, startTime);
    gain.gain.setValueAtTime(0, startTime);
    gain.gain.linearRampToValueAtTime(gainPeak || 0.15, startTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration);
  }

  function playWin() {
    if (!enabled) return;
    const audioCtx = getCtx();
    if (!audioCtx) return;
    const now = audioCtx.currentTime;
    tone(523.25, now, 0.12, "triangle", 0.12);
    tone(659.25, now + 0.1, 0.12, "triangle", 0.12);
    tone(783.99, now + 0.2, 0.22, "triangle", 0.14);
  }

  function playBigWin() {
    if (!enabled) return;
    const audioCtx = getCtx();
    if (!audioCtx) return;
    const now = audioCtx.currentTime;
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => {
      tone(freq, now + i * 0.09, 0.25, "triangle", 0.14);
    });
  }

  function playLose() {
    if (!enabled) return;
    const audioCtx = getCtx();
    if (!audioCtx) return;
    const now = audioCtx.currentTime;
    tone(220, now, 0.18, "sawtooth", 0.08);
    tone(164.81, now + 0.12, 0.22, "sawtooth", 0.08);
  }

  function playClick() {
    if (!enabled) return;
    const audioCtx = getCtx();
    if (!audioCtx) return;
    tone(880, audioCtx.currentTime, 0.05, "square", 0.05);
  }

  function isEnabled() {
    return enabled;
  }

  function setEnabled(value) {
    enabled = value;
    localStorage.setItem("emberplay_sound", value ? "on" : "off");
  }

  function toggle() {
    setEnabled(!enabled);
    if (enabled) playClick();
    return enabled;
  }

  return { playWin, playBigWin, playLose, playClick, isEnabled, setEnabled, toggle };
})();

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("sound-toggle");
  if (!btn) return;

  function render() {
    btn.textContent = window.EmberSound.isEnabled() ? "🔊" : "🔇";
    btn.style.opacity = window.EmberSound.isEnabled() ? "1" : "0.5";
  }
  render();

  btn.addEventListener("click", () => {
    window.EmberSound.toggle();
    render();
  });
});
