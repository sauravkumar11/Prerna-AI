import { useEffect, useRef } from "react";
import "./SiriOrb.css";

const EMOTION_COLORS = {
  CALM:      { c1: "56,189,248",  c2: "59,130,246",  c3: "139,92,246"  },
  EXCITED:   { c1: "251,191,36",  c2: "245,158,11",  c3: "239,68,68"   },
  PLAYFUL:   { c1: "52,211,153",  c2: "16,185,129",  c3: "59,130,246"  },
  CARING:    { c1: "244,114,182", c2: "236,72,153",  c3: "139,92,246"  },
  SAD:       { c1: "99,102,241",  c2: "79,70,229",   c3: "55,48,163"   },
  ANGRY:     { c1: "239,68,68",   c2: "220,38,38",   c3: "245,158,11"  },
  SHY:       { c1: "251,146,60",  c2: "249,115,22",  c3: "244,114,182" },
  SURPRISED: { c1: "167,243,208", c2: "52,211,153",  c3: "251,191,36"  },
};

export default function SiriOrb({
  state = "idle",
  emotion = "CALM",
  amplitude = 0,
  listening,
  volume,
}) {
  const wrapperRef = useRef(null);
  const canvasRef  = useRef(null);
  const rafRef     = useRef(null);
  const tRef       = useRef(0);

  const resolvedState = listening !== undefined
    ? (listening ? "listening" : "idle")
    : state;
  const resolvedAmp = volume !== undefined ? volume : amplitude;

  const colors = EMOTION_COLORS[emotion] || EMOTION_COLORS.CALM;
  const { c1, c2, c3 } = colors;

  // Push emotion colors to CSS vars
  useEffect(() => {
    const w = wrapperRef.current;
    if (!w) return;
    w.style.setProperty("--c1", c1);
    w.style.setProperty("--c2", c2);
    w.style.setProperty("--c3", c3);
  }, [c1, c2, c3]);

  // Amplitude → scale/brightness
  useEffect(() => {
    const w = wrapperRef.current;
    if (!w) return;
    const amp   = Math.max(0, Math.min(1, resolvedAmp));
    const scale = 1 + amp * 0.45;
    const bri   = 1 + amp * 2.2;
    w.style.transform = `scale(${scale}, ${1 + amp * 0.35})`;
    w.style.filter    = `brightness(${bri})`;
  }, [resolvedAmp]);

  // Canvas overlay: listening bars, thinking dots, speaking waves
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;

    const draw = () => {
      tRef.current += 0.016;
      const t  = tRef.current;
      const W  = cv.width;
      const H  = cv.height;
      const cx = W / 2;
      const cy = H / 2;
      const R  = W / 2;
      const r  = R * 0.53; // matches core size ratio
      const ctx = cv.getContext("2d");
      ctx.clearRect(0, 0, W, H);

      if (resolvedState === "listening") {
        const nBars = 24;
        for (let i = 0; i < nBars; i++) {
          const angle = (i / nBars) * Math.PI * 2;
          const amp2  =
            0.04 +
            0.13 * Math.abs(Math.sin(t * 4.5 + i * 0.45)) +
            0.07 * Math.abs(Math.sin(t * 7.2 + i * 0.82)) +
            0.04 * Math.abs(Math.sin(t * 2.8 + i * 1.1));
          const r1    = r * 1.07;
          const r2    = r * (1.15 + amp2 * 2.0);
          const alpha = 0.22 + 0.65 * amp2;
          ctx.strokeStyle = `rgba(${c1},${alpha})`;
          ctx.lineWidth   = 2.2;
          ctx.lineCap     = "round";
          ctx.beginPath();
          ctx.moveTo(cx + Math.cos(angle) * r1, cy + Math.sin(angle) * r1);
          ctx.lineTo(cx + Math.cos(angle) * r2, cy + Math.sin(angle) * r2);
          ctx.stroke();
        }
      }

      if (resolvedState === "thinking") {
        const orbits = [
          { dist: r * 1.38, speed:  2.2, sz: 4.5, alpha: 0.92, phase: 0   },
          { dist: r * 1.58, speed: -1.4, sz: 3.2, alpha: 0.55, phase: 1.2 },
          { dist: r * 1.76, speed:  1.0, sz: 2.2, alpha: 0.30, phase: 2.5 },
        ];
        orbits.forEach(o => {
          ctx.strokeStyle = "rgba(80,150,255,0.1)";
          ctx.lineWidth   = 0.8;
          ctx.setLineDash([3, 5]);
          ctx.beginPath(); ctx.arc(cx, cy, o.dist, 0, Math.PI * 2); ctx.stroke();
          ctx.setLineDash([]);

          const angle = t * o.speed + o.phase;
          for (let j = 7; j >= 0; j--) {
            const ta = angle - j * 0.2 * Math.sign(o.speed);
            const tx = cx + Math.cos(ta) * o.dist;
            const ty = cy + Math.sin(ta) * o.dist;
            ctx.fillStyle = `rgba(${c1},${o.alpha * (1 - j / 8) * 0.4})`;
            ctx.beginPath(); ctx.arc(tx, ty, o.sz * (1 - j / 10), 0, Math.PI * 2); ctx.fill();
          }
          const mx = cx + Math.cos(angle) * o.dist;
          const my = cy + Math.sin(angle) * o.dist;
          const dg = ctx.createRadialGradient(mx, my, 0, mx, my, o.sz * 1.8);
          dg.addColorStop(0, `rgba(210,240,255,${o.alpha})`);
          dg.addColorStop(0.4, `rgba(${c2},${o.alpha * 0.7})`);
          dg.addColorStop(1, "rgba(60,120,255,0)");
          ctx.fillStyle = dg;
          ctx.beginPath(); ctx.arc(mx, my, o.sz * 1.8, 0, Math.PI * 2); ctx.fill();
        });
      }

      if (resolvedState === "speaking") {
        const spkAmp =
          0.45 +
          0.38 * Math.abs(Math.sin(t * 5.5)) +
          0.12 * Math.abs(Math.sin(t * 11));
        const nLines  = 9;
        const spacing = 7;
        for (let side = -1; side <= 1; side += 2) {
          for (let li = 0; li < nLines; li++) {
            const yOff   = (li - (nLines - 1) / 2) * spacing;
            const falloff = 1 - Math.abs(yOff) / ((nLines / 2) * spacing + 2);
            if (falloff <= 0.05) continue;
            const startX = cx + side * r * 1.06;
            const maxLen = r * (0.55 + 0.45 * spkAmp) * falloff;
            const wAmp   = 7 * spkAmp * falloff;
            const alpha  = (0.28 + 0.6 * spkAmp) * falloff;
            ctx.beginPath();
            const steps = 18;
            for (let s = 0; s <= steps; s++) {
              const px = startX + side * (s / steps) * maxLen;
              const py = cy + yOff + Math.sin(t * 8 + s * 0.6) * wAmp * (s / steps);
              s === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
            }
            const grd = ctx.createLinearGradient(startX, 0, startX + side * maxLen, 0);
            grd.addColorStop(0, `rgba(${c1},${alpha})`);
            grd.addColorStop(1, `rgba(${c2},0)`);
            ctx.strokeStyle = grd;
            ctx.lineWidth   = 1.8;
            ctx.lineCap     = "round";
            ctx.stroke();
          }
        }
      }

      if (resolvedState === "wake") {
        for (let i = 0; i < 3; i++) {
          const phase = ((t * 2.5 + i * 0.5) % 1.5) / 1.5;
          const wr    = r * (1.05 + phase * 2.2);
          const wa    = (1 - phase) * 0.75;
          ctx.strokeStyle = `rgba(${c1},${wa})`;
          ctx.lineWidth   = 2.5 - i * 0.5;
          ctx.beginPath(); ctx.arc(cx, cy, wr, 0, Math.PI * 2); ctx.stroke();
        }
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    cancelAnimationFrame(rafRef.current);
    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [resolvedState, c1, c2]);

  const needsCanvas = ["listening", "thinking", "speaking", "wake"].includes(resolvedState);

  return (
    <div className="siri-container">
      <div
        ref={wrapperRef}
        className="voice-reactive-wrapper"
        style={{ "--c1": c1, "--c2": c2, "--c3": c3 }}
      >
        <div className={`siri-orb orb-${resolvedState}`}>
          <div className="orb-layer layer1" />
          <div className="orb-layer layer2" />
          <div className="orb-layer layer3" />

          {needsCanvas && (
            <canvas
              ref={canvasRef}
              className="orb-canvas-overlay"
              width={360}
              height={360}
            />
          )}

          <div className="orb-core">
            <div className="core-inner" />
            {resolvedState === "thinking" && <div className="thinking-ring" />}
          </div>
        </div>
      </div>
    </div>
  );
}
