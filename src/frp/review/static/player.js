// Frame-navigation state for the review viewer. No DOM access, so it is unit-tested under Node.
(function (root) {
  'use strict';

  function clampFrame(index, count) {
    if (!(count >= 1)) return 0;
    const whole = Number.isFinite(index) ? Math.trunc(index) : 0;
    return Math.max(0, Math.min(count - 1, whole));
  }

  function frameLabel(frame, count) {
    return 'Frame ' + frame + ' / ' + Math.max(0, count - 1) +
      (frame === 0 ? ' — conditioned first frame (later frames are primary)' : '');
  }

  // Play advances one frame per tick and stops on the last frame; any manual move pauses.
  function createFrameState(count, initial) {
    let frame = clampFrame(initial, count);
    let playing = false;
    return {
      frame: () => frame,
      playing: () => playing,
      select: (index) => { playing = false; frame = clampFrame(index, count); return frame; },
      step: (delta) => { playing = false; frame = clampFrame(frame + delta, count); return frame; },
      play: () => {
        if (count < 2) return false;
        if (frame >= count - 1) frame = 0;
        playing = true;
        return true;
      },
      pause: () => { playing = false; },
      tick: () => {
        if (!playing) return frame;
        frame = clampFrame(frame + 1, count);
        if (frame >= count - 1) playing = false;
        return frame;
      },
    };
  }

  const api = { clampFrame: clampFrame, createFrameState: createFrameState, frameLabel: frameLabel };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FRPPlayer = Object.freeze(api);
}(this));
