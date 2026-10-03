import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Sparkles, X } from "lucide-react";

import {
  clampFloatingPosition,
  defaultFloatingPosition,
  parseFloatingPosition,
  type FloatingPosition,
} from "../services/floatingCopilotPosition";
import "./FloatingCopilotButton.css";

const STORAGE_KEY = "diaglob-copilot-fab-position";
const DRAG_THRESHOLD = 5;

interface FloatingCopilotButtonProps {
  open: boolean;
  onToggle: () => void;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  origin: FloatingPosition;
}

function initialPosition() {
  const saved = parseFloatingPosition(localStorage.getItem(STORAGE_KEY));
  return clampFloatingPosition(
    saved || defaultFloatingPosition(window.innerWidth, window.innerHeight),
    window.innerWidth,
    window.innerHeight,
  );
}

export default function FloatingCopilotButton({
  open,
  onToggle,
}: FloatingCopilotButtonProps) {
  const [position, setPosition] = useState<FloatingPosition>(initialPosition);
  const positionRef = useRef(position);
  const dragRef = useRef<DragState | null>(null);
  const draggedRef = useRef(false);
  const suppressClickRef = useRef(false);

  useEffect(() => {
    const handleResize = () => {
      setPosition((current) => {
        const next = clampFloatingPosition(
          current,
          window.innerWidth,
          window.innerHeight,
        );
        positionRef.current = next;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;

    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origin: position,
    };
    draggedRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const moveDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;

    if (
      !draggedRef.current
      && Math.hypot(deltaX, deltaY) >= DRAG_THRESHOLD
    ) {
      draggedRef.current = true;
    }

    if (!draggedRef.current) return;

    const next = clampFloatingPosition(
      {
        x: drag.origin.x + deltaX,
        y: drag.origin.y + deltaY,
      },
      window.innerWidth,
      window.innerHeight,
    );
    positionRef.current = next;
    setPosition(next);
  };

  const finishDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    dragRef.current = null;
    if (draggedRef.current) {
      suppressClickRef.current = true;
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(positionRef.current),
      );
    }
  };

  const handleClick = () => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    onToggle();
  };

  return (
    <button
      type="button"
      className={`copilot-floating-button ${open ? "is-open" : ""}`}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`,
      }}
      aria-label={open ? "Cerrar Copiloto IA" : "Abrir Copiloto IA"}
      aria-pressed={open}
      title={open ? "Cerrar Copiloto IA" : "Abrir Copiloto IA"}
      onPointerDown={startDrag}
      onPointerMove={moveDrag}
      onPointerUp={finishDrag}
      onPointerCancel={finishDrag}
      onClick={handleClick}
    >
      <span className="copilot-floating-button-glow" aria-hidden="true" />
      <span className="copilot-floating-button-icon">
        {open ? <X size={22} /> : <Sparkles size={22} />}
      </span>
      {!open && (
        <span className="copilot-floating-button-label">Copiloto</span>
      )}
    </button>
  );
}
