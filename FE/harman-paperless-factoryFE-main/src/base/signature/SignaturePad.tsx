import { useEffect, useRef, useState } from "react";
import { Box, Button, TextField, ToggleButton, ToggleButtonGroup } from "@mui/material";

export interface SignatureValue {
  dataUrl: string;
  method: "draw" | "type";
}

interface Props {
  onChange: (value: SignatureValue | null) => void;
  /** Pre-fills "type your name". */
  defaultName?: string;
  height?: number;
}

const INK = "#0f172a";

/**
 * A signature for a signed approval step: drawn with a finger, pen or mouse,
 * or typed. Either way it leaves as a PNG data URL, which the backend stamps
 * onto the record's PDF.
 */
const SignaturePad = ({ onChange, defaultName = "", height = 150 }: Props) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const inked = useRef(false); // read by pointer handlers, which may run before a re-render
  const [mode, setMode] = useState<"draw" | "type">("draw");
  const [hasInk, setHasInk] = useState(false);
  const [typed, setTyped] = useState(defaultName);

  // size the bitmap to the element (and the screen's pixel ratio) so lines stay crisp
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    const { width } = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx?.scale(ratio, ratio);
  }, [height, mode]);

  const ctx = () => canvasRef.current?.getContext("2d") ?? null;

  const clear = () => {
    const canvas = canvasRef.current;
    const c = ctx();
    if (canvas && c) c.clearRect(0, 0, canvas.width, canvas.height);
    inked.current = false;
    setHasInk(false);
    onChange(null);
  };

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const start = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    last.current = point(e);
  };

  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const c = ctx();
    const p = point(e);
    if (!c || !last.current) return;
    c.strokeStyle = INK;
    c.lineWidth = 2.2;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.beginPath();
    c.moveTo(last.current.x, last.current.y);
    c.lineTo(p.x, p.y);
    c.stroke();
    last.current = p;
    if (!inked.current) {
      inked.current = true;
      setHasInk(true);
    }
  };

  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    last.current = null;
    if (inked.current && canvasRef.current) onChange({ dataUrl: canvasRef.current.toDataURL("image/png"), method: "draw" });
  };

  /** A typed name rendered in a handwriting face. */
  const renderTyped = (name: string) => {
    setTyped(name);
    if (!name.trim()) {
      onChange(null);
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = 600;
    canvas.height = 150;
    const c = canvas.getContext("2d");
    if (!c) return;
    c.fillStyle = INK;
    c.font = 'italic 48px "Segoe Script", "Brush Script MT", "Snell Roundhand", cursive';
    c.textBaseline = "middle";
    c.fillText(name.trim(), 20, 78, 560);
    onChange({ dataUrl: canvas.toDataURL("image/png"), method: "type" });
  };

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={mode}
          onChange={(_, next: "draw" | "type" | null) => {
            if (!next) return;
            setMode(next);
            inked.current = false;
            setHasInk(false);
            if (next === "type") renderTyped(typed);
            else onChange(null);
          }}
        >
          <ToggleButton value="draw" sx={{ textTransform: "none" }}>
            Draw
          </ToggleButton>
          <ToggleButton value="type" sx={{ textTransform: "none" }}>
            Type
          </ToggleButton>
        </ToggleButtonGroup>
        {mode === "draw" && (
          <Button size="small" onClick={clear} disabled={!hasInk} sx={{ textTransform: "none" }}>
            Clear
          </Button>
        )}
      </Box>
      {mode === "draw" ? (
        <canvas
          ref={canvasRef}
          aria-label="Signature area: draw your signature"
          role="img"
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerLeave={end}
          style={{
            width: "100%",
            height,
            border: "1px dashed #94a3b8",
            borderRadius: 8,
            background: "#fff",
            touchAction: "none",
            cursor: "crosshair",
            display: "block",
          }}
        />
      ) : (
        <TextField
          fullWidth
          size="small"
          label="Your name as signature"
          value={typed}
          onChange={(e) => renderTyped(e.target.value)}
          slotProps={{ htmlInput: { style: { fontFamily: '"Segoe Script", "Brush Script MT", cursive', fontSize: 22 } } }}
        />
      )}
      <Box sx={{ fontSize: 11, color: "#6b7280", mt: 0.75 }}>
        Your signature is stamped onto the record's PDF with your name, designation and the time.
      </Box>
    </Box>
  );
};

export default SignaturePad;
