/* Next-step card, share card and share sheet, and the attempt compare sheet. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* NEXT STEP. The focus and the first drill come from the live day plan
     (/coach/today), the same one as on the 'Training' tab. No plan means no card:
     advice is not invented out of thin air. */
  let nextStepCache = { at: 0, data: null };
  async function loadNextStep(a) {
    const card = document.getElementById('card-next-step');
    if (!card) return;
    const dup = document.getElementById('btn-ans-open-today');
    if (dup) dup.hidden = false;
    if (!a || a.noJump || NS.demoShown || !NS.realResults) { card.hidden = true; return; }
    let d = null;
    const fresh = nextStepCache.data && Date.now() - nextStepCache.at < 30000;
    if (fresh) d = nextStepCache.data;
    else {
      try {
        const r = await fetch('/coach/today?lang=en');
        d = r.ok ? await r.json() : null;
      } catch (_) { d = null; }
      nextStepCache = { at: Date.now(), data: d };
    }
    if (NS.activeAttempts[NS.currentAttemptIdx] !== a) return;
    if (!d || d.empty || !d.focus_text) { card.hidden = true; return; }
    const esc = v => String(v ?? '').replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
    const focus = document.getElementById('next-step-focus');
    /* The focus name and WHERE it comes from: without a 'typical cause from the database',
       which is identical under every jump and read as a diagnosis of this jump */
    const kind = d.focus_source && d.focus_source.kind;
    const why = kind === 'coach' ? 'set by your coach'
      : kind === 'persistent' ? 'recurs in your analyses'
      : kind === 'latest_analysis' ? 'from your latest analysis'
      : kind === 'chosen_goal' ? 'the goal you picked'      : 'base work';
    if (focus) focus.textContent = d.focus === 'rest' || !d.focus_label ? d.focus_text
      : `Focus: ${d.focus_label} · ${why}`;
    const drill = (d.blocks || []).find(b => b && b.drill_id && b.block !== 'warmup');
    const box = document.getElementById('next-step-drill');
    if (box) box.hidden = !drill;
    if (drill) {
      const nm = document.getElementById('next-step-name');
      const meta = document.getElementById('next-step-meta');
      const cue = document.getElementById('next-step-cue');
      if (nm) nm.textContent = (drill.where === 'off_ice' ? 'Off-ice · ' : '') + (drill.name || '');
      if (meta) meta.textContent = [drill.dosage, d.duration_min ? `session ${d.duration_min} min` : '']
        .filter(Boolean).join(' · ');
      const c = (drill.cues || [])[0];
      if (cue) { cue.innerHTML = c ? `“${esc(c)}”` : ''; cue.hidden = !c; }
    }
    card.hidden = false;
    /* 'What to train' at the bottom duplicates this card */
    if (dup) dup.hidden = true;
  }

  /* ── SHARE ─────────────────────────────────────────────────────────
     Stories are not shared as a line of text, so the card is
     1080×1920: a frame in the air from the OWN video, the name, the count, measurements with
     bands and confidence in words, exactly what is on the answer screen, nothing
     extra on top. At the bottom, a call to check your own jump (engagement loop). */
  function shareText(a) {
    const parts = [
      (document.getElementById('ans-verdict-t')?.textContent || '').trim(),
      a.airTime && a.airTime !== '—' ? `air time ${a.airTime} s` : '',
      a.height && a.height !== '—' ? `height ${a.height} cm` : '',
    ].filter(Boolean);
    return (NS.demoShown ? 'JumpSight sample analysis: '
                      : 'My jump on JumpSight: ') + parts.join(' · ');
  }
  async function shareLink() {
    if (NS.demoShown && NS.activeJobIdShown) return `${location.origin}/?job=${encodeURIComponent(NS.activeJobIdShown)}`;
    try {
      if (NS.activeJobIdShown) {
        const r = await fetch('/coach/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job: NS.activeJobIdShown }) });
        if (r.ok) { const j = await r.json(); if (j.token) { const revoke = document.getElementById('btn-ans-revoke-share'); if (revoke) revoke.hidden = false; return `${location.origin}/coach/s/${j.token}`; } }
      }
    } catch (_) { }
    return '';
  }
  async function grabFlightFrame() {
    const v = document.getElementById('ans-video');
    if (!v || !v.videoWidth || !NS.ANS_PH) return null;
    const keep = v.currentTime, wasPaused = v.paused;
    try {
      v.pause();
      await new Promise(res => {
        const done = () => { v.removeEventListener('seeked', done); res(); };
        v.addEventListener('seeked', done);
        v.currentTime = (NS.ANS_PH.t + NS.ANS_PH.l) / 2;
        setTimeout(done, 1500);
      });
      const c = document.createElement('canvas');
      c.width = v.videoWidth; c.height = v.videoHeight;
      c.getContext('2d').drawImage(v, 0, 0);
      c.toDataURL();   // throws if the frame is tainted by a foreign origin
      return c;
    } catch (_) { return null; }
    finally { try { v.currentTime = keep; if (!wasPaused) v.play().catch(() => {}); } catch (_) { } }
  }
  function loadImg(src) {
    return new Promise(res => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(null); im.src = src; });
  }
  async function buildShareCard(a) {
    const W = 1080, H = 1920;
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const g = c.getContext('2d');
    const BG = '#0B1620', INK = '#F4F8FB', DIM = '#9FB6C8', ACC = '#FF8A6B';
    const SANS = '"Archivo", system-ui, -apple-system, "Segoe UI", sans-serif';
    const MONO = '"IBM Plex Mono", ui-monospace, monospace';
    try { await document.fonts.ready; } catch (_) { }
    g.fillStyle = BG; g.fillRect(0, 0, W, H);
    const frame = await grabFlightFrame();
    /* Layout from the bottom up with fixed rows: text never
       overlaps, whatever the frame. */
    const FH = 1060;
    if (frame) {
      const k = Math.max(W / frame.width, FH / frame.height);
      const dw = frame.width * k, dh = frame.height * k;
      g.save(); g.beginPath(); g.rect(0, 0, W, FH); g.clip();
      g.drawImage(frame, (W - dw) / 2, Math.min(0, (FH - dh) / 2), dw, dh);
      g.restore();
    } else {
      g.strokeStyle = ACC; g.lineWidth = 18; g.lineCap = 'round';
      g.beginPath(); g.arc(W / 2, 520, 300, -Math.PI * 0.5, Math.PI * 1.15); g.stroke();
    }
    const grad = g.createLinearGradient(0, FH - 420, 0, FH);
    grad.addColorStop(0, 'rgba(11,22,32,0)'); grad.addColorStop(1, BG);
    g.fillStyle = grad; g.fillRect(0, FH - 420, W, 420);
    const top = g.createLinearGradient(0, 0, 0, 300);
    top.addColorStop(0, 'rgba(11,22,32,.85)'); top.addColorStop(1, 'rgba(11,22,32,0)');
    g.fillStyle = top; g.fillRect(0, 0, W, 300);
    const icon = await loadImg('/static/icon.svg');
    if (icon) g.drawImage(icon, 72, 72, 72, 72);
    g.fillStyle = INK; g.font = `700 44px ${SANS}`; g.textBaseline = 'middle';
    g.fillText('JumpSight', 164, 110);
    if (NS.demoShown) { g.fillStyle = DIM; g.font = `500 30px ${SANS}`; g.textAlign = 'right'; g.fillText('sample analysis', W - 72, 110); g.textAlign = 'left'; }
    const pill = (text, x, yy, bg, fg, size = 30) => {
      g.font = `600 ${size}px ${SANS}`; g.textBaseline = 'middle';
      const w = g.measureText(text).width + size * 1.2, h = size * 1.8;
      g.fillStyle = bg; g.beginPath(); g.roundRect(x, yy - h / 2, w, h, h / 2); g.fill();
      g.fillStyle = fg; g.fillText(text, x + size * 0.6, yy + 1);
      return w;
    };
    g.textBaseline = 'alphabetic';
    /* bottom: call to action */
    g.fillStyle = ACC; g.font = `600 36px ${SANS}`;
    g.fillText('Check your own jump →' + ' ' + location.host, 72, H - 90);
    /* measurements */
    const cells = [];
    if (a.airTime && a.airTime !== '—') cells.push(['air time', a.airTime, 's', typeof a.airHalf === 'number' ? `±${a.airHalf.toFixed(2)}` : '']);
    if (a.height && a.height !== '—') cells.push(['height', a.height, 'cm', typeof a.heightHalfCm === 'number' ? `±${Math.max(1, Math.round(a.heightHalfCm))}` : '']);
    if (typeof a.revFlight === 'number') cells.push(['in flight', a.revFlight.toFixed(2), 'rev', typeof a.revHalf === 'number' ? `±${a.revHalf.toFixed(2)}` : '']);
    if (cells.length) {
      const cw = (W - 144) / cells.length, yl = H - 300, yv = H - 210;
      g.strokeStyle = 'rgba(255,255,255,.14)'; g.lineWidth = 2;
      g.beginPath(); g.moveTo(72, yl - 60); g.lineTo(W - 72, yl - 60); g.stroke();
      cells.forEach(([lbl, v, u, band], i) => {
        const x = 72 + i * cw;
        g.fillStyle = DIM; g.font = `600 28px ${SANS}`; g.fillText(lbl.toUpperCase(), x, yl);
        g.fillStyle = INK; g.font = `700 72px ${MONO}`; g.fillText(v, x, yv);
        g.fillStyle = DIM; g.font = `500 28px ${SANS}`; g.fillText(`${u} ${band}`.trim(), x, yv + 46);
      });
    }
    /* confidence in words */
    const confs = [document.getElementById('ans-name-conf'), document.getElementById('ans-hero-why')]
      .map(e => e && !e.hidden ? e.textContent.trim() : '').filter(Boolean);
    if (confs.length) { let x = 72; confs.forEach(t => { x += pill(t, x, H - 450, 'rgba(255,255,255,.10)', DIM, 30) + 14; }); g.textBaseline = 'alphabetic'; }
    /* count */
    const num = (document.getElementById('ans-hero-num')?.textContent || '').trim();
    const unit = (document.querySelector('#scr-answer .rz-revs__lbl')?.textContent || '').trim();
    const revsShown = !document.querySelector('#scr-answer .rz-revs')?.hidden;
    let yTop = H - 520;
    if (num && num !== '—' && revsShown) {
      g.font = `700 230px ${MONO}`; g.fillStyle = INK; g.fillText(num, 64, H - 520);
      const nw = g.measureText(num).width;
      g.font = `500 44px ${SANS}`; g.fillStyle = DIM; g.fillText(unit, 64 + nw + 28, H - 540);
      yTop = H - 750;
    }
    /* name (up to two lines) and the record above it */
    const title = (document.getElementById('ans-verdict-t')?.textContent || '').trim();
    g.fillStyle = INK; g.font = `700 88px ${SANS}`;
    const words = title.split(' '); let line = ''; const lines = [];
    words.forEach(w0 => { const t = line ? line + ' ' + w0 : w0; if (g.measureText(t).width > W - 144 && line) { lines.push(line); line = w0; } else line = t; });
    if (line) lines.push(line);
    const shown = lines.slice(0, 2);
    shown.forEach((l0, k) => g.fillText(l0, 72, yTop - (shown.length - 1 - k) * 96));
    if (a.record) pill(a.record.label, 72, yTop - shown.length * 96 - 30, ACC, '#2A1410', 32);
    return await new Promise(res => c.toBlob(b => res(b), 'image/png'));
  }
  let shareBlob = null;
  async function openShareSheet() {
    const a = NS.activeAttempts[NS.currentAttemptIdx] || {};
    const sheet = document.getElementById('sheet-share');
    const img = document.getElementById('share-card-img');
    const wait = document.getElementById('share-card-wait');
    if (!sheet) return;
    const opener = document.activeElement;
    sheet.hidden = false; sheet.style.display = 'flex';
    const close = () => { sheet.hidden = true; sheet.style.display = 'none'; opener?.focus?.({ preventScroll: true }); };
    document.getElementById('btn-close-share').onclick = close;
    sheet.onclick = e => { if (e.target === sheet) close(); };
    sheet.onkeydown = e => { if (e.key === 'Escape') close(); };
    document.getElementById('btn-close-share').focus();
    if (img) { img.hidden = true; if (img.src) URL.revokeObjectURL(img.src); img.removeAttribute('src'); }
    if (wait) { wait.hidden = false; wait.textContent = 'Making the card…'; }
    /* 'Send link' works at once: the handler is attached BEFORE the card is built
       (up to 1.5 s of frame search), so a tap in that time still acts. */
    const bLink = document.getElementById('btn-share-link');
    if (bLink) bLink.onclick = async () => {
      const url = await shareLink();
      const text = shareText(a) + (url ? '\n' + url : '');
      try {
        if (navigator.share) { await navigator.share(url ? { text, url } : { text }); return; }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          NS.notice('Link copied — paste it into a message.');
          return;
        }
      } catch (e) { if (e && e.name === 'AbortError') return; }
      NS.notice('Sharing is unavailable here — save the image.');
    };
    shareBlob = null;
    { const b0 = document.getElementById('btn-share-image'); if (b0) b0.disabled = true; }   /* until the card is ready */
    try { shareBlob = await buildShareCard(a); } catch (_) { shareBlob = null; }
    if (shareBlob && img) { img.src = URL.createObjectURL(shareBlob); img.hidden = false; if (wait) wait.hidden = true; }
    else if (wait) wait.textContent = 'Could not make the card — send the link instead.';
    const bImg = document.getElementById('btn-share-image');
    if (bImg) {
      bImg.disabled = !shareBlob;
      bImg.onclick = async () => {
        if (!shareBlob) return;
        const file = new File([shareBlob], 'jumpsight.png', { type: 'image/png' });
        const text = shareText(a);
        try {
          if (navigator.canShare && navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], text }); return; }
        } catch (e) { if (e && e.name === 'AbortError') return; }
        const link = document.createElement('a');
        link.href = URL.createObjectURL(shareBlob); link.download = 'jumpsight.png';
        document.body.appendChild(link); link.click(); link.remove();
        NS.notice('Image saved — add it to a story or a message.');
      };
    }
  }

  /* ATTEMPT COMPARISON.
     Two attempts side by side, synchronized from the MEASURED take-off: shared time t is
     seconds relative to take-off, and each video sits at 'its own take-off + t'.
     A leads (plays natively), B follows as soon as it drifts by more than 0.08 s.
     Candidates: other attempts of this video and, only when the analysis is mine, my
     analyses from the log (a coach viewing a student's analysis does not compare the student with themselves).
     Without a measured take-off and landing there is no attempt here: nothing to align by,
     and an invented alignment is an invented number. */
  const CMP = { a: null, b: null, speed: 1, raf: 0, cands: [], token: 0 };

  function cmpPhase(a) {
    const t = a && a.takeoff != null ? parseFloat(a.takeoff) : NaN;
    const l = a && a.landing != null ? parseFloat(a.landing) : NaN;
    return Number.isFinite(t) && Number.isFinite(l) && l > t ? { t, l } : null;
  }

  function cmpFacts(el, a) {
    const conf = (v, kind) => ({
      name: { high: 'confident', medium: 'likely', low: 'possible' },
      count: { high: 'confident', medium: 'likely', low: 'possible' }
    })[kind][v] || '';
    const rows = [
      ['Name', a.name, conf(a.nameConf, 'name')],
      [a.heroUnit || 'Count', a.num, (a.heroWhy || '').replace(/^.*—\s*/, '')],
      ['Air time', a.airTime !== '—' ? `${a.airTime} s` : '—',
        a.airHalf != null ? `±${a.airHalf.toFixed(2)}` : ''],
      ['Height', a.height !== '—' ? `${a.height} cm` : '—',
        a.heightHalfCm != null ? `±${Math.round(a.heightHalfCm)}` : ''],
    ];
    if (typeof a.revFlight === 'number')
      rows.push(['Rotations in the air', a.revFlight.toFixed(2), a.revHalf != null ? `±${a.revHalf.toFixed(2)}` : '']);
    if (typeof a.rateDeg === 'number')
      rows.push(['Rotation speed', `${(a.rateDeg / 360).toFixed(1)} rotations/s`, typeof a.rateBandRps === 'number' ? `±${a.rateBandRps.toFixed(1)}` : '']);
    el.replaceChildren(...rows.flatMap(([k, v, n]) => {
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd');
      const vEl = document.createElement('span'); vEl.className = 'mono'; vEl.textContent = v || '—';
      dd.append(vEl);
      if (n) { const s = document.createElement('small'); s.textContent = ' ' + n; dd.append(s); }
      return [dt, dd];
    }));
  }

  /* The difference appears only where the ± bands do not overlap, the same rule as
     'What changed' on 'Progress'. Without a known error there is no row. */
  function cmpDiff(a, b) {
    const out = [];
    const num = (x) => (x == null || x === '—' ? null : parseFloat(x));
    const pairs = [
      ['Air time', num(a.airTime), a.airHalf, num(b.airTime), b.airHalf, 2, 's'],
      ['Height', num(a.height), a.heightHalfCm, num(b.height), b.heightHalfCm, 0, 'cm'],
    ];
    if (typeof a.revFlight === 'number' && typeof b.revFlight === 'number')
      pairs.push(['Rotations in the air', a.revFlight, a.revHalf, b.revFlight, b.revHalf, 2, '']);
    for (const [label, va, ha, vb, hb, dp, unit] of pairs) {
      if (![va, ha, vb, hb].every(Number.isFinite)) continue;
      const d = vb - va;
      const text = Math.abs(d) > ha + hb
        ? (`B is ${Math.abs(d).toFixed(dp)} ${unit} ${d > 0 ? 'more' : 'less'}`.replace(/\s+/g, ' '))
        : 'within the measurement error';
      out.push(`${label}: ${text}`);
    }
    return out;
  }

  async function cmpCandidates(current) {
    const list = [];
    NS.activeAttempts.forEach((a, i) => {
      if (a !== current && !a.noJump && cmpPhase(a))
        list.push({ key: `att:${i}`, label: `Attempt ${i + 1} of this video · ${a.name}`,
                    job: NS.lastJobId, attempt: a });
    });
    let rows = [];
    try { const h = await window.__jsHistory(); rows = h.ok && Array.isArray(h.data) ? h.data : []; } catch (_) { }
    if (!rows.some(r => r && r.job === NS.lastJobId)) return list;
    const seen = new Set();
    for (const r of rows) {
      if (!r || !r.job || r.job === 'None' || r.job === NS.lastJobId || !r.stem || seen.has(r.stem)) continue;
      if (r.state && r.state !== 'done') continue;
      /* an unmeasured attempt has neither a name nor phases, so there is nothing to compare;
         in the list it read as 'Oct 7 · null' */
      if (r.outcome === 'not_measured' || !r.jump || r.jump === 'None') continue;
      seen.add(r.stem);
      const when = Number.isFinite(r.ts) ? new Date(r.ts * 1000).toLocaleDateString(NS.LOC(), { day: 'numeric', month: 'short' }) : '';
      const count = r.count_named && r.count_named !== 'None' ? ' · ' + r.count_named : '';
      list.push({ key: `hist:${r.stem}`, label: `${when} · ${NS.historyJumpName(r)}${count}`, job: String(r.job), stem: r.stem });
      if (list.length >= 30) break;
    }
    return list;
  }

  async function cmpResolve(c) {
    if (c.attempt) return c.attempt;
    const res = await fetch(`/summary/${encodeURIComponent(c.job)}`);
    if (!res.ok) return null;
    const data = await res.json();
    const row = (data.jumps || []).find(j => j && j.stem === c.stem);
    return row ? NS.summaryToAttempt(row, c.job) : null;
  }

  function cmpStop() {
    cancelAnimationFrame(CMP.raf); CMP.raf = 0;
    for (const id of ['cmp-video-a', 'cmp-video-b']) document.getElementById(id)?.pause();
  }

  /* The range covers only the stretch that exists in BOTH recordings: if the take-off in B is 0.3 s from the start,
     the strip does not go to −1 s (B would have a zero frame under the caption
     'before take-off 1.00 s'). */
  function cmpRange() {
    const sides = [CMP.a, CMP.b].filter(Boolean);
    const vids = [document.getElementById('cmp-video-a'), document.getElementById('cmp-video-b')];
    const flight = Math.max(...sides.map(s => s.ph.l - s.ph.t));
    let r0 = -Math.min(1.0, ...sides.map(s => s.ph.t));
    let r1 = flight + 1.0;
    sides.forEach((s, i) => {
      const d = vids[i] && vids[i].duration;
      if (Number.isFinite(d) && d > 0) r1 = Math.min(r1, d - s.ph.t);
    });
    return [r0, Math.max(r1, flight)];
  }

  /* t is seconds relative to take-off; each video sits at its own take-off + t */
  function cmpSeek(t) {
    const va = document.getElementById('cmp-video-a'), vb = document.getElementById('cmp-video-b');
    const [r0, r1] = cmpRange();
    t = Math.min(r1, Math.max(r0, t));
    try { va.currentTime = Math.max(0, CMP.a.ph.t + t); } catch (_) { }
    if (CMP.b) try { vb.currentTime = Math.max(0, CMP.b.ph.t + t); } catch (_) { }
    cmpSyncUi(t);
  }

  function cmpNow() {
    const va = document.getElementById('cmp-video-a');
    return va.currentTime - CMP.a.ph.t;
  }

  function cmpSyncUi(t = cmpNow()) {
    const [r0, r1] = cmpRange();
    const range = document.getElementById('cmp-scrub-range');
    if (range && !CMP.dragging) range.value = String(Math.round((t - r0) / (r1 - r0) * 1000));
    const fl = document.getElementById('cmp-scrub-flight');
    if (fl) {
      const fa = CMP.a.ph.l - CMP.a.ph.t;
      fl.style.left = `${((0 - r0) / (r1 - r0) * 100).toFixed(2)}%`;
      fl.style.width = `${(Math.min(fa, r1) / (r1 - r0) * 100).toFixed(2)}%`;
    }
    const phase = (ph, label) => {
      const fl2 = ph.l - ph.t;
      return t < 0 ? `${label}: ${(-t).toFixed(2)} s to take-off`
        : t <= fl2 ? `${label}: in the air +${t.toFixed(2)} s`
        : `${label}: after landing +${(t - fl2).toFixed(2)} s`;
    };
    const pe = document.getElementById('cmp-scrub-phase');
    if (pe) pe.textContent = phase(CMP.a.ph, 'A') + (CMP.b ? ' · ' + phase(CMP.b.ph, 'B') : '');
    /* 'close-up' here too: each video follows its own skater track */
    NS.setFollow(document.getElementById('cmp-video-a'), CMP.a.att.track, NS.FOLLOW.on);
    NS.setFollow(document.getElementById('cmp-video-b'), CMP.b ? CMP.b.att.track : null, NS.FOLLOW.on && !!CMP.b);
  }

  function cmpTick() {
    const va = document.getElementById('cmp-video-a'), vb = document.getElementById('cmp-video-b');
    if (!CMP.a) return;
    const [r0, r1] = cmpRange();
    let t = cmpNow();
    if (t > r1) { cmpSeek(r0); t = r0; }
    if (CMP.b && !va.paused) {
      const want = CMP.b.ph.t + t;
      if (want < 0 || (vb.duration && want > vb.duration)) vb.pause();
      else {
        if (vb.paused) vb.play().catch(() => {});
        if (Math.abs(vb.currentTime - want) > 0.08) vb.currentTime = want;
      }
    }
    cmpSyncUi(t);
    if (!va.paused) CMP.raf = requestAnimationFrame(cmpTick);
  }

  async function cmpSetB(c) {
    const token = ++CMP.token;
    const vb = document.getElementById('cmp-video-b');
    const factsB = document.getElementById('cmp-facts-b');
    const diff = document.getElementById('cmp-diff');
    cmpStop();
    CMP.b = null;
    factsB.replaceChildren();
    diff.replaceChildren();
    let a = null;
    try { a = await cmpResolve(c); } catch (_) { a = null; }
    if (token !== CMP.token) return;
    const ph = cmpPhase(a);
    if (!a || !ph) {
      const p = document.createElement('p'); p.className = 'rz-note';
      p.textContent = 'Take-off and landing were not measured for this attempt — there is nothing to align it by.';
      factsB.replaceChildren(p);
      vb.removeAttribute('src'); vb.load();
      return;
    }
    CMP.b = { att: a, ph };
    const src = `/media/${encodeURIComponent(c.job)}/full/original`;
    if (vb.getAttribute('src') !== src) vb.src = src;
    cmpFacts(factsB, a);
    for (const line of cmpDiff(CMP.a.att, a)) {
      const p = document.createElement('p'); p.textContent = line; diff.append(p);
    }
    const ready = () => cmpSeek(-0.3);
    if (vb.readyState >= 1) ready(); else vb.addEventListener('loadedmetadata', ready, { once: true });
  }

  async function openCompareSheet() {
    const a = NS.activeAttempts[NS.currentAttemptIdx];
    const ph = cmpPhase(a);
    const sheet = document.getElementById('sheet-compare');
    if (!sheet || !a || !ph) return;
    const opener = document.activeElement;
    document.getElementById('ans-video')?.pause();
    CMP.a = { att: a, ph };
    CMP.b = null;
    const va = document.getElementById('cmp-video-a');
    const mainVid = document.getElementById('ans-video');
    const srcA = mainVid && mainVid.currentSrc ? mainVid.currentSrc : `/media/${encodeURIComponent(NS.lastJobId)}/full/original`;
    if (va.src !== srcA) va.src = srcA;
    va.playbackRate = CMP.speed;
    cmpFacts(document.getElementById('cmp-facts-a'), a);
    sheet.hidden = false; sheet.style.display = 'flex';
    const close = () => { cmpStop(); sheet.hidden = true; sheet.style.display = 'none'; opener?.focus?.({ preventScroll: true }); };
    document.getElementById('btn-close-compare').onclick = close;
    sheet.onclick = e => { if (e.target === sheet) close(); };
    sheet.onkeydown = e => { if (e.key === 'Escape') close(); };
    document.getElementById('btn-close-compare').focus();
    const readyA = () => cmpSeek(-0.3);
    if (va.readyState >= 1) readyA(); else va.addEventListener('loadedmetadata', readyA, { once: true });

    const pick = document.getElementById('cmp-pick');
    const empty = document.getElementById('cmp-empty');
    const grid = document.getElementById('cmp-grid');
    pick.replaceChildren(); pick.disabled = true;
    const loading = document.createElement('option'); loading.textContent = 'Finding attempts…';
    pick.append(loading);
    const cands = await cmpCandidates(a);
    if (sheet.hidden || CMP.a.att !== a) return;
    CMP.cands = cands;
    pick.replaceChildren(...cands.map(c => { const o = document.createElement('option'); o.value = c.key; o.textContent = c.label; return o; }));
    pick.disabled = !cands.length;
    empty.hidden = !!cands.length;
    grid.classList.toggle('is-single', !cands.length);
    document.getElementById('cmp-facts-grid')?.classList.toggle('is-single', !cands.length);
    if (!cands.length) {
      empty.textContent = 'There is no other attempt with a measured take-off. Analyse another video to compare them.';
      return;
    }
    pick.onchange = () => { const c = CMP.cands.find(x => x.key === pick.value); if (c) cmpSetB(c); };
    cmpSetB(cands[0]);
  }

  function initCompare() {
    const va = document.getElementById('cmp-video-a'), vb = document.getElementById('cmp-video-b');
    if (!va || !vb) return;
    const both = fn => [va, vb].forEach(fn);
    document.getElementById('cmp-play').onclick = () => {
      if (!CMP.a) return;
      if (va.paused) {
        const [r0, r1] = cmpRange();
        if (cmpNow() >= r1 - 0.02) cmpSeek(r0);
        both(v => { v.playbackRate = CMP.speed; });
        va.play().then(() => { cancelAnimationFrame(CMP.raf); CMP.raf = requestAnimationFrame(cmpTick); }).catch(() => {});
      } else { cmpStop(); cmpSeek(cmpNow()); }
    };
    const step = dir => { if (!CMP.a) return; cmpStop(); cmpSeek(cmpNow() + dir / (NS.videoFps || 30)); };
    document.getElementById('cmp-frame-prev').onclick = () => step(-1);
    document.getElementById('cmp-frame-next').onclick = () => step(1);
    const speed = document.getElementById('cmp-speed');
    speed.onclick = () => {
      CMP.speed = CMP.speed === 1 ? 0.5 : CMP.speed === 0.5 ? 0.25 : 1;
      speed.textContent = CMP.speed === 1 ? '1×' : CMP.speed === 0.5 ? '½×' : '¼×';
      both(v => { v.playbackRate = CMP.speed; });
    };
    const range = document.getElementById('cmp-scrub-range');
    const seekRange = () => { if (!CMP.a) return; const [r0, r1] = cmpRange(); cmpSeek(r0 + Number(range.value) / 1000 * (r1 - r0)); };
    range.addEventListener('pointerdown', () => { CMP.dragging = true; cmpStop(); });
    range.addEventListener('input', () => { cmpStop(); seekRange(); });
    const end = () => { CMP.dragging = false; seekRange(); };
    range.addEventListener('pointerup', end);
    range.addEventListener('change', end);
    both(v => v.addEventListener('click', () => document.getElementById('cmp-play').click()));
    va.addEventListener('pause', () => { if (!vb.paused) vb.pause(); });
  }

  Object.assign(NS, {
     loadNextStep, openShareSheet, openCompareSheet, initCompare,
  });
})();
