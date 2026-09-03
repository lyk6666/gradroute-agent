/**
 * Deliver ResizeObserver callbacks once per animation frame without dropping an
 * observed target. Chromium reports an undelivered-notifications error when a
 * measurement callback causes another layout inside the same delivery cycle.
 *
 * React Flow uses ResizeObserver for its viewport. Deferring that callback
 * breaks the delivery loop; merging entries by target preserves every pending
 * measurement instead of keeping only the final callback payload.
 */

type MarkedResizeObserver = typeof ResizeObserver & {
  __graduationAgentFrameScheduled?: true;
};

export function installResizeObserverFrameScheduler() {
  if (typeof window === 'undefined' || typeof window.ResizeObserver === 'undefined') return;

  const CurrentResizeObserver = window.ResizeObserver as MarkedResizeObserver;
  if (CurrentResizeObserver.__graduationAgentFrameScheduled) return;

  const pendingFrames = new WeakMap<ResizeObserver, number>();
  const pendingEntriesByObserver = new WeakMap<ResizeObserver, Map<Element, ResizeObserverEntry>>();

  class FrameScheduledResizeObserver extends CurrentResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      super((entries, observer) => {
        const pendingEntries = pendingEntriesByObserver.get(observer) ?? new Map<Element, ResizeObserverEntry>();
        entries.forEach((entry) => pendingEntries.set(entry.target, entry));
        pendingEntriesByObserver.set(observer, pendingEntries);
        if (pendingFrames.has(observer)) return;
        const frame = window.requestAnimationFrame(() => {
          pendingFrames.delete(observer);
          const mergedEntries = [...pendingEntries.values()];
          pendingEntries.clear();
          callback(mergedEntries, observer);
        });
        pendingFrames.set(observer, frame);
      });
    }

    override disconnect() {
      const pendingFrame = pendingFrames.get(this);
      if (pendingFrame !== undefined) window.cancelAnimationFrame(pendingFrame);
      pendingFrames.delete(this);
      pendingEntriesByObserver.delete(this);
      super.disconnect();
    }

    override unobserve(target: Element) {
      pendingEntriesByObserver.get(this)?.delete(target);
      super.unobserve(target);
    }
  }

  Object.defineProperty(FrameScheduledResizeObserver, '__graduationAgentFrameScheduled', {
    value: true,
  });
  window.ResizeObserver = FrameScheduledResizeObserver;
}

installResizeObserverFrameScheduler();
