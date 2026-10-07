import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Drag-to-scroll (grab and move) for wide overflow-x containers.
 * - Starts drag on primary mouse button only.
 * - Ignores drags that start on interactive elements so inputs/selects/buttons/links keep working.
 * - Suppresses the click that follows a real drag so row links don't fire accidentally.
 * - Uses a callback ref so listeners attach even when the table mounts late
 *   (after loading / after an employee is selected).
 */
export function useDragScroll<T extends HTMLElement = HTMLDivElement>() {
  const [dragging, setDragging] = useState(false);
  const dragState = useRef({ active: false, startX: 0, startScroll: 0, moved: false, suppressClick: false });
  const cleanupRef = useRef<(() => void) | null>(null);

  const detach = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
  }, []);

  // Detach on unmount.
  useEffect(() => detach, [detach]);

  const ref = useCallback(
    (el: T | null) => {
      detach();
      if (!el) {
        dragState.current.active = false;
        setDragging(false);
        return;
      }

      const isInteractive = (target: EventTarget | null) =>
        (target as HTMLElement)?.closest?.(
          'input, textarea, select, button, a, [contenteditable], [data-no-drag]'
        );

      const onMouseDown = (e: MouseEvent) => {
        if (e.button !== 0) return;
        if (isInteractive(e.target)) return;
        // Only grab when there is actually overflow to scroll.
        if (el.scrollWidth <= el.clientWidth + 1) return;
        dragState.current = {
          active: true,
          startX: e.clientX,
          startScroll: el.scrollLeft,
          moved: false,
          suppressClick: false,
        };
        setDragging(true);
      };

      const onMouseMove = (e: MouseEvent) => {
        const s = dragState.current;
        if (!s.active) return;
        const dx = e.clientX - s.startX;
        if (!s.moved && Math.abs(dx) > 6) s.moved = true;
        if (s.moved) {
          e.preventDefault();
          el.scrollLeft = s.startScroll - dx;
        }
      };

      const endDrag = () => {
        const s = dragState.current;
        if (!s.active) return;
        s.active = false;
        // If we actually dragged, swallow the next click (capture phase).
        s.suppressClick = s.moved;
        s.moved = false;
        setDragging(false);
      };

      const onClickCapture = (e: MouseEvent) => {
        if (dragState.current.suppressClick) {
          dragState.current.suppressClick = false;
          e.preventDefault();
          e.stopPropagation();
        }
      };

      el.addEventListener('mousedown', onMouseDown);
      window.addEventListener('mousemove', onMouseMove, { passive: false });
      window.addEventListener('mouseup', endDrag);
      el.addEventListener('click', onClickCapture, true);
      cleanupRef.current = () => {
        el.removeEventListener('mousedown', onMouseDown);
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', endDrag);
        el.removeEventListener('click', onClickCapture, true);
      };
    },
    [detach]
  );

  return { ref, dragging };
}
