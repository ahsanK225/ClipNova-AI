/* ClipNova Hero Animation Engine — loaded cleanly via /assets/clipnova_hero.js */
function initClipNovaHeroAnimation(container) {
  if (!container) return () => {};
  const canvas = container.querySelector("#clipHeroCanvas");
  if (!canvas) return () => {};
  const ctx = canvas.getContext("2d");
  if (!ctx) return () => {};

  let animId = null;
  let running = true;
  let width = 0, height = 0;
  const mouse = { x: -1000, y: -1000, tx: -1000, ty: -1000, active: false };
  const heroSection = container.closest(".hero") || container;

  const onMouseMove = (e) => {
    const rect = heroSection.getBoundingClientRect();
    mouse.tx = e.clientX - rect.left;
    mouse.ty = e.clientY - rect.top;
    mouse.active = true;
  };
  const onMouseLeave = () => {
    mouse.tx = -1000;
    mouse.ty = -1000;
    mouse.active = false;
  };
  heroSection.addEventListener("mousemove", onMouseMove, { passive: true });
  heroSection.addEventListener("mouseleave", onMouseLeave, { passive: true });

  let cardFade = 1.0;

  const resize = () => {
    const rect = container.getBoundingClientRect();
    width = rect.width || window.innerWidth;
    height = rect.height || (container.parentElement ? container.parentElement.clientHeight : 280);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  window.addEventListener("resize", resize, { passive: true });
  let ro = null;
  if (typeof ResizeObserver !== "undefined") {
    ro = new ResizeObserver(() => resize());
    ro.observe(heroSection);
  }
  resize();

  const cards = [
    { rx: 0.08, ry: 0.46, w: 110, h: 182, rot: -0.06, badge: "⚡ 98 SCORE", title: "GTA 6 Drift", dur: "0:42", c1: "#6366F1", c2: "#00F0FF", speed: 1.1, phase: 0.2, amp: 8, bars: [0.6, 0.9, 0.4, 0.8, 0.5, 0.7] },
    { rx: 0.21, ry: 0.65, w: 94, h: 154, rot: 0.04, badge: "✂️ AUTO SPLIT", title: "Taco Run!", dur: "0:56", c1: "#EC4899", c2: "#8B5CF6", speed: 1.3, phase: 1.9, amp: 10, bars: [0.4, 0.7, 1.0, 0.6, 0.3] },
    { rx: 0.79, ry: 0.38, w: 96, h: 158, rot: -0.04, badge: "🔥 VIRAL 96%", title: "Speed Stream", dur: "0:35", c1: "#3B82F6", c2: "#10B981", speed: 1.0, phase: 3.1, amp: 8, bars: [0.7, 0.3, 0.9, 0.6, 0.8] },
    { rx: 0.92, ry: 0.58, w: 112, h: 186, rot: 0.05, badge: "🎬 SMART CROP", title: "Insane Clutch", dur: "0:28", c1: "#8B5CF6", c2: "#EC4899", speed: 1.25, phase: 4.6, amp: 9, bars: [0.5, 0.8, 0.6, 1.0, 0.7, 0.4] }
  ];

  const glyphs = ["✂️", "🎬", "⚡", "✨", "▶️", "💎"];
  const particles = Array.from({ length: 32 }, (_, i) => ({
    x: Math.random() * 1200,
    y: Math.random() * 600,
    vx: (Math.random() - 0.5) * 0.4,
    vy: -0.3 - Math.random() * 0.5,
    size: 2 + Math.random() * 3,
    alpha: 0.25 + Math.random() * 0.5,
    color: i % 3 === 0 ? "#00F0FF" : i % 3 === 1 ? "#A855F7" : "#FBBF24",
    glyph: i % 5 === 0 ? glyphs[i % glyphs.length] : null
  }));

  const sparks = [];
  const shockwaves = [];
  const cutRatios = [0.22, 0.48, 0.76];
  let lastCutTrigger = -1;
  const startTime = performance.now();

  const drawRoundedRect = (cx, cy, w, h, r) => {
    ctx.beginPath();
    ctx.moveTo(cx + r, cy);
    ctx.lineTo(cx + w - r, cy);
    ctx.quadraticCurveTo(cx + w, cy, cx + w, cy + r);
    ctx.lineTo(cx + w, cy + h - r);
    ctx.quadraticCurveTo(cx + w, cy + h, cx + w - r, cy + h);
    ctx.lineTo(cx + r, cy + h);
    ctx.quadraticCurveTo(cx, cy + h, cx, cy + h - r);
    ctx.lineTo(cx, cy + r);
    ctx.quadraticCurveTo(cx, cy, cx + r, cy);
    ctx.closePath();
  };

  const renderFrame = (now) => {
    if (!running) return;
    const time = (now - startTime) * 0.001;
    if (mouse.active) {
      mouse.x += (mouse.tx - mouse.x) * 0.12;
      mouse.y += (mouse.ty - mouse.y) * 0.12;
    } else {
      mouse.x += (-1000 - mouse.x) * 0.12;
      mouse.y += (-1000 - mouse.y) * 0.12;
    }
    ctx.clearRect(0, 0, width, height);

    if (mouse.x > -500 && mouse.y > -500) {
      const spotGrad = ctx.createRadialGradient(mouse.x, mouse.y, 10, mouse.x, mouse.y, 220);
      spotGrad.addColorStop(0, "rgba(0, 240, 255, 0.09)");
      spotGrad.addColorStop(0.5, "rgba(99, 102, 241, 0.04)");
      spotGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = spotGrad;
      ctx.fillRect(0, 0, width, height);
    }

    const isOptsOpen = !!heroSection.querySelector(".composer-opts.open");
    cardFade = isOptsOpen ? Math.max(0, cardFade - 0.1) : Math.min(1, cardFade + 0.05);

    const trackY1 = isOptsOpen ? Math.min(height * 0.16, 50) : height * 0.28;
    const trackY2 = isOptsOpen ? Math.max(height * 0.90, height - 50) : height * 0.72;
    const tracks = [
      { y: trackY1, h: 26, label: "TRACK 01 • GAMING REACTION" },
      { y: trackY2, h: 26, label: "TRACK 02 • AUDIO & HOOKS" }
    ];

    tracks.forEach((track, tIdx) => {
      ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, track.y - 12);
      ctx.lineTo(width, track.y - 12);
      ctx.moveTo(0, track.y + 12);
      ctx.lineTo(width, track.y + 12);
      ctx.stroke();

      ctx.fillStyle = "rgba(255, 255, 255, 0.04)";
      for (let x = 8; x < width; x += 28) {
        drawRoundedRect(x, track.y - 10, 6, 4, 1);
        ctx.fill();
        drawRoundedRect(x, track.y + 6, 6, 4, 1);
        ctx.fill();
      }

      ctx.fillStyle = "rgba(148, 163, 184, 0.25)";
      ctx.font = "9px 'Geist', monospace";
      ctx.textAlign = "left";
      for (let x = 40; x < width; x += 120) {
        const sec = Math.floor(x / 8);
        const mins = String(Math.floor(sec / 60)).padStart(2, "0");
        const secs = String(sec % 60).padStart(2, "0");
        ctx.fillText(`${mins}:${secs}`, x, track.y - 16);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.beginPath();
        ctx.moveTo(x, track.y - 14);
        ctx.lineTo(x, track.y - 8);
        ctx.stroke();
      }

      const waveGrad = ctx.createLinearGradient(0, track.y - 10, width, track.y + 10);
      if (tIdx === 0) {
        waveGrad.addColorStop(0, "rgba(0, 240, 255, 0.35)");
        waveGrad.addColorStop(0.5, "rgba(99, 102, 241, 0.35)");
        waveGrad.addColorStop(1, "rgba(236, 72, 153, 0.35)");
      } else {
        waveGrad.addColorStop(0, "rgba(168, 85, 247, 0.35)");
        waveGrad.addColorStop(0.5, "rgba(0, 240, 255, 0.35)");
        waveGrad.addColorStop(1, "rgba(16, 185, 129, 0.35)");
      }
      ctx.fillStyle = waveGrad;
      for (let x = 20; x < width - 20; x += 8) {
        const noise = Math.sin(x * 0.04 + time * 2.2 + tIdx) * 0.5 + Math.sin(x * 0.09 - time * 1.5) * 0.3 + Math.cos(x * 0.02 + time * 3.1) * 0.2;
        const barH = Math.max(3, Math.abs(noise) * 16);
        ctx.fillRect(x, track.y - barH / 2, 3, barH);
      }

      for (let c = 0; c < cutRatios.length - 1; c++) {
        const startX = width * cutRatios[c];
        const endX = width * cutRatios[c + 1];
        ctx.fillStyle = "rgba(0, 240, 255, 0.04)";
        ctx.strokeStyle = "rgba(0, 240, 255, 0.18)";
        ctx.lineWidth = 1;
        drawRoundedRect(startX, track.y - 11, endX - startX, 22, 3);
        ctx.fill();
        ctx.stroke();
        if (tIdx === 0 && endX - startX > 80) {
          ctx.fillStyle = "rgba(0, 240, 255, 0.6)";
          ctx.font = "8px 'Geist', sans-serif";
          ctx.fillText("✓ AI CLIP 98%", startX + 8, track.y + 3);
        }
      }
    });

    const scrubberCycle = width + 280;
    const scrubberX = ((time * 70) % scrubberCycle) - 140;
    cutRatios.forEach((ratio, cIdx) => {
      const cutX = width * ratio;
      if (Math.abs(scrubberX - cutX) < 3 && lastCutTrigger !== cIdx) {
        lastCutTrigger = cIdx;
        tracks.forEach(tr => {
          for (let p = 0; p < 12; p++) {
            const angle = Math.random() * Math.PI * 2;
            const spd = 1.2 + Math.random() * 3.5;
            sparks.push({ x: cutX, y: tr.y, vx: Math.cos(angle) * spd, vy: Math.sin(angle) * spd, alpha: 1.0, size: 2 + Math.random() * 2.5, color: p % 2 === 0 ? "#00F0FF" : "#EC4899" });
          }
          shockwaves.push({ x: cutX, y: tr.y, r: 4, alpha: 0.9, maxR: 38 });
        });
      }
    });
    if (Math.abs(scrubberX - width * cutRatios[0]) > 20 && (scrubberX < width * cutRatios[0] || scrubberX > width * cutRatios[cutRatios.length - 1] + 20)) {
      lastCutTrigger = -1;
    }

    if (scrubberX >= -20 && scrubberX <= width + 20) {
      const beamGrad = ctx.createLinearGradient(0, 0, 0, height);
      beamGrad.addColorStop(0, "rgba(0, 240, 255, 0)");
      beamGrad.addColorStop(0.2, "rgba(0, 240, 255, 0.85)");
      beamGrad.addColorStop(0.5, "rgba(236, 72, 153, 0.95)");
      beamGrad.addColorStop(0.8, "rgba(99, 102, 241, 0.85)");
      beamGrad.addColorStop(1, "rgba(99, 102, 241, 0)");
      ctx.strokeStyle = beamGrad;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(scrubberX, 0);
      ctx.lineTo(scrubberX, height);
      ctx.stroke();

      ctx.strokeStyle = "rgba(0, 240, 255, 0.15)";
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(scrubberX, 0);
      ctx.lineTo(scrubberX, height);
      ctx.stroke();

      tracks.forEach(tr => {
        ctx.save();
        ctx.translate(scrubberX, tr.y);
        ctx.fillStyle = "#EC4899";
        ctx.shadowColor = "#EC4899";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.arc(0, 0, 9, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("✂", 0, 0);
        ctx.restore();
      });
    }

    for (let i = shockwaves.length - 1; i >= 0; i--) {
      const sw = shockwaves[i];
      sw.r += 1.8;
      sw.alpha -= 0.04;
      if (sw.alpha <= 0) { shockwaves.splice(i, 1); continue; }
      ctx.save();
      ctx.strokeStyle = `rgba(0, 240, 255, ${sw.alpha})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(sw.x, sw.y, sw.r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    for (let i = sparks.length - 1; i >= 0; i--) {
      const sp = sparks[i];
      sp.x += sp.vx;
      sp.y += sp.vy;
      sp.vy += 0.08;
      sp.alpha -= 0.025;
      if (sp.alpha <= 0) { sparks.splice(i, 1); continue; }
      ctx.save();
      ctx.fillStyle = sp.color;
      ctx.globalAlpha = sp.alpha;
      ctx.shadowColor = sp.color;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, sp.size, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    if (cardFade > 0.01) {
      const px = (mouse.x > -500 ? (mouse.x - width / 2) * 0.015 : 0);
      const py = (mouse.y > -500 ? (mouse.y - height / 2) * 0.015 : 0);
      const cardScale = width < 960 ? 0.82 : 1.0;
      const centerX = width / 2;
      const compHalf = Math.min(Math.max(width * 0.44, 220), 390);

      cards.forEach((card, idx) => {
        if (width < 740 && (idx === 1 || idx === 2)) return;
        const cw = card.w * cardScale, ch = card.h * cardScale;
        let baseX;
        if (idx === 0) baseX = Math.max(cw / 2 + 16, centerX - compHalf - cw - 32);
        else if (idx === 1) baseX = Math.max(cw / 2 + 8, centerX - compHalf - cw / 2 - 14);
        else if (idx === 2) baseX = Math.min(width - cw / 2 - 8, centerX + compHalf + cw / 2 + 14);
        else baseX = Math.min(width - cw / 2 - 16, centerX + compHalf + cw + 32);

        const floatY = Math.sin(time * card.speed + card.phase) * card.amp;
        const cx = baseX + px * (idx % 2 === 0 ? 1 : -1);
        const cy = card.ry * height + floatY + py;

        ctx.save();
        ctx.globalAlpha = cardFade;
        ctx.translate(cx, cy);
        ctx.rotate(card.rot + (mouse.x > -500 ? (mouse.x - width / 2) * 0.00005 : 0));
        ctx.shadowColor = card.c1;
        ctx.shadowBlur = 18;
        drawRoundedRect(-cw / 2, -ch / 2, cw, ch, 12);
        ctx.fillStyle = "rgba(18, 24, 38, 0.82)";
        ctx.fill();

        const borderGrad = ctx.createLinearGradient(-cw / 2, -ch / 2, cw / 2, ch / 2);
        borderGrad.addColorStop(0, card.c1);
        borderGrad.addColorStop(1, card.c2);
        ctx.strokeStyle = borderGrad;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.shadowBlur = 0;

        const pad = 6, thumbW = cw - pad * 2, thumbH = ch * 0.62, thumbX = -cw / 2 + pad, thumbY = -ch / 2 + pad + 18;
        drawRoundedRect(thumbX, thumbY, thumbW, thumbH, 8);
        const thumbGrad = ctx.createLinearGradient(thumbX, thumbY, thumbX + thumbW, thumbY + thumbH);
        thumbGrad.addColorStop(0, "rgba(25, 33, 54, 0.95)");
        thumbGrad.addColorStop(0.5, "rgba(40, 30, 60, 0.85)");
        thumbGrad.addColorStop(1, "rgba(20, 25, 40, 0.95)");
        ctx.fillStyle = thumbGrad;
        ctx.fill();

        ctx.fillStyle = "rgba(0, 240, 255, 0.25)";
        ctx.strokeStyle = "rgba(0, 240, 255, 0.7)";
        ctx.lineWidth = 1;
        drawRoundedRect(thumbX + 5, thumbY + 5, 24, 20, 4);
        ctx.fill();
        ctx.stroke();

        ctx.save();
        ctx.translate(thumbX + thumbW / 2, thumbY + thumbH / 2);
        ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
        ctx.beginPath();
        ctx.arc(0, 0, 11, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath();
        ctx.moveTo(-3, -5);
        ctx.lineTo(5, 0);
        ctx.lineTo(-3, 5);
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
        drawRoundedRect(-cw / 2 + pad, -ch / 2 + pad, cw - pad * 2, 14, 4);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.font = "bold 8px 'Geist', sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(card.badge, -cw / 2 + pad + 4, -ch / 2 + pad + 7);

        const botY = -ch / 2 + pad + 18 + thumbH + 4;
        ctx.fillStyle = "#F1F5F9";
        ctx.font = "bold 9px 'Geist', sans-serif";
        ctx.fillText(card.title, -cw / 2 + pad, botY + 8);

        for (let b = 0; b < card.bars.length; b++) {
          const bNoise = Math.sin(time * 6 + b * 1.2 + idx) * 0.4 + 0.6;
          const bH = Math.max(3, bNoise * 10 * card.bars[b]);
          ctx.fillStyle = b % 2 === 0 ? "#00F0FF" : "#EC4899";
          drawRoundedRect(-cw / 2 + pad + b * 5, ch / 2 - pad - bH, 3, bH, 1);
          ctx.fill();
        }

        ctx.fillStyle = "#94A3B8";
        ctx.font = "8px monospace";
        ctx.textAlign = "right";
        ctx.fillText(card.dur, cw / 2 - pad, ch / 2 - pad - 2);
        ctx.restore();
      });
    }

    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.y < -20) { p.y = height + 20; p.x = Math.random() * width; }
      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      ctx.save();
      if (p.glyph) {
        ctx.globalAlpha = p.alpha * 0.65;
        ctx.font = "12px sans-serif";
        ctx.fillText(p.glyph, p.x, p.y);
      } else {
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    });

    animId = requestAnimationFrame(renderFrame);
  };

  animId = requestAnimationFrame(renderFrame);

  return () => {
    running = false;
    if (animId) cancelAnimationFrame(animId);
    if (ro) ro.disconnect();
    window.removeEventListener("resize", resize);
    heroSection.removeEventListener("mousemove", onMouseMove);
    heroSection.removeEventListener("mouseleave", onMouseLeave);
  };
}
