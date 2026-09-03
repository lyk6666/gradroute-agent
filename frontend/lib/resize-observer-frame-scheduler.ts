/**
 * Deliver ResizeObserver callbacks on the next animation frame.
 *
 * React Flow measures its viewport and nodes with ResizeObserver. Chromium can
 * report an "undelivered notifications" error when a measurement synchronously
 * schedules another layout during the same delivery cycle. Deferring and
 * coalescing callbacks preserves measurement while breaking that feedback cycle.
 */

type MarkedResizeObserver = typeof ResizeObserver & {
  __graduationAgentFrameScheduled?: true;
};

export function installResizeObserverFrameScheduler() {
  if (typeof window === 'undefined' || typeof window.ResizeObserver === 'undefined') return;

  const CurrentResizeObserver = window.ResizeObserver as MarkedResizeObserver;
  if (CurrentResizeObserver.__graduationAgentFrameScheduled) return;

  const pendingFrames = new WeakMap<ResizeObserver, number>();
  class FrameScheduledResizeObserver extends CurrentResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      super((entries, observer) => {
        const pending = pendingFrames.get(observer);
        if (pending !== undefined) window.cancelAnimationFrame(pending);
        const frame = window.requestAnimationFrame(() => {
          pendingFrames.delete(observer);
          callback(entries, observer);
        });
        pendingFrames.set(observer, frame);
      });
    }

    override disconnect() {
      const pending = pendingFrames.get(this);
      if (pending !== undefined) window.cancelAnimationFrame(pending);
      pendingFrames.delete(this);
      super.disconnect();
    }
  }

  Object.defineProperty(FrameScheduledResizeObserver, '__graduationAgentFrameScheduled', {
    value: true,
  });
  window.ResizeObserver = FrameScheduledResizeObserver;
}

installResizeObserverFrameScheduler();
