import { useEffect, useRef } from "react";

const EDGE_SIZE = 96;
const MAX_SPEED = 22;

/**
 * Scroll a marked table viewport (or the page) while a drag is held near an
 * edge. Keeping the animation in one RAF loop avoids jumpy dragover scrolling.
 */
export function useDragPageAutoScroll(active: boolean) {
  const speed = useRef({ x: 0, y: 0 });
  const target = useRef<HTMLElement | Window>(window);
  const frame = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!active) return;

    const tick = () => {
      if (speed.current.x !== 0 || speed.current.y !== 0) {
        target.current.scrollBy({
          left: speed.current.x,
          top: speed.current.y,
          behavior: "instant",
        });
      }
      frame.current = window.requestAnimationFrame(tick);
    };
    const onDragOver = (event: DragEvent) => {
      const scrollSurface = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest<HTMLElement>("[data-drag-scroll]");
      const bounds = scrollSurface?.getBoundingClientRect();
      target.current = scrollSurface ?? window;
      const topDistance = bounds ? event.clientY - bounds.top : event.clientY;
      const bottomDistance = bounds
        ? bounds.bottom - event.clientY
        : window.innerHeight - event.clientY;
      const leftDistance = bounds ? event.clientX - bounds.left : event.clientX;
      const rightDistance = bounds
        ? bounds.right - event.clientX
        : window.innerWidth - event.clientX;
      let y = 0;
      let x = 0;
      if (topDistance < EDGE_SIZE) {
        y = -MAX_SPEED * (1 - Math.max(0, topDistance) / EDGE_SIZE);
      } else if (bottomDistance < EDGE_SIZE) {
        y = MAX_SPEED * (1 - Math.max(0, bottomDistance) / EDGE_SIZE);
      }
      if (leftDistance < EDGE_SIZE) {
        x = -MAX_SPEED * (1 - Math.max(0, leftDistance) / EDGE_SIZE);
      } else if (rightDistance < EDGE_SIZE) {
        x = MAX_SPEED * (1 - Math.max(0, rightDistance) / EDGE_SIZE);
      }
      speed.current = { x, y };
    };
    const stop = () => {
      speed.current = { x: 0, y: 0 };
    };

    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", stop);
    window.addEventListener("dragend", stop);
    frame.current = window.requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", stop);
      window.removeEventListener("dragend", stop);
      if (frame.current !== undefined) window.cancelAnimationFrame(frame.current);
      speed.current = { x: 0, y: 0 };
    };
  }, [active]);
}
