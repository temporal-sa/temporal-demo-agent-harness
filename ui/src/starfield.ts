// The demo buildkit's starfield (assets/js/starfield.js), as a module: parallax drift,
// twinkle, and an occasional shooting star on a full-page canvas. Kept close to the original
// so the two stay easy to compare.

type Star = { x: number; y: number; z: number; r: number; tw: number; hue: string };

export function startStarfield(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext("2d")!;
  let w = 0;
  let h = 0;
  let field: Star[] = [];
  let shooting: { x: number; y: number; vx: number; vy: number; life: number } | null = null;
  let last = performance.now();
  let paused = false;
  let raf = 0;

  function newStar(anywhere: boolean): Star {
    const depth = Math.random();
    return {
      x: anywhere ? Math.random() * w : w + 2,
      y: Math.random() * h,
      z: depth,
      r: 0.3 + depth * 1.3,
      tw: Math.random() * Math.PI * 2,
      // Mostly white, a few lavender and purple.
      hue: Math.random() < 0.12 ? (Math.random() < 0.5 ? "203,203,249" : "182,100,255") : "248,250,252",
    };
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    field = Array.from({ length: Math.round((w * h) / 2600) }, () => newStar(true));
  }

  function frame(now: number) {
    const dt = Math.min(64, now - last) / 1000;
    last = now;
    ctx.clearRect(0, 0, w, h);
    for (const s of field) {
      if (!paused) {
        s.tw += dt * (1 + s.z * 2);
        s.x -= 4 * (0.15 + s.z) * dt;
      }
      if (s.x < -10) Object.assign(s, newStar(false));
      const a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(s.tw)) * (0.4 + s.z * 0.6);
      ctx.fillStyle = `rgba(${s.hue},${a.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    if (!paused) {
      if (!shooting && Math.random() < dt * 0.08) {
        shooting = { x: Math.random() * w, y: Math.random() * h * 0.4, vx: -600 - Math.random() * 400, vy: 220, life: 1 };
      }
      if (shooting) {
        const s = shooting;
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        s.life -= dt * 1.2;
        const g = ctx.createLinearGradient(s.x, s.y, s.x - s.vx * 0.12, s.y - s.vy * 0.12);
        g.addColorStop(0, `rgba(248,250,252,${Math.max(0, s.life)})`);
        g.addColorStop(1, "rgba(248,250,252,0)");
        ctx.strokeStyle = g;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(s.x - s.vx * 0.12, s.y - s.vy * 0.12);
        ctx.stroke();
        if (s.life <= 0) shooting = null;
      }
    }
    raf = requestAnimationFrame(frame);
  }

  addEventListener("resize", resize);
  resize();
  raf = requestAnimationFrame(frame);

  return {
    setPaused: (value: boolean) => (paused = value),
    stop() {
      cancelAnimationFrame(raf);
      removeEventListener("resize", resize);
    },
  };
}
