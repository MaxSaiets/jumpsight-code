/* Drill card screen: opening a drill, its blocks and attempt pills. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* ── 3.4 Drill Card Viewer ── */
  function openDrill(drill) {
    if (!drill) return;
    NS.activeDrill = drill;

    const catEl = document.getElementById('drill-category-eyebrow');
    if (catEl) catEl.textContent = drill.category || 'DRILL · LEVEL 2 · OFF-ICE';

    const titleEl = document.getElementById('drill-title');
    if (titleEl) titleEl.textContent = drill.title || 'Drill';

    const vidPlayer = document.getElementById('drill-video-player');
    if (vidPlayer) {
      /* /api/drill_media decides the source;
         'no video' is an honest state, not a substitute (an unknown drill must not show someone else's video). */
      vidPlayer.removeAttribute('src'); vidPlayer.load();
      /* Drill demo: ONLY the 3D character (/api/drill_media returns
         kind=mascot or none). The coach's original videos are shown
         nowhere; when there is no demo yet, the card says so honestly, without a foreign video. */
      const box = vidPlayer.closest('.rz-video');
      let note = box && box.querySelector('.rz-drill__nodemo');
      if (!note && box) { note = document.createElement('p'); note.className = 'rz-note rz-drill__nodemo'; box.append(note); }
      if (note) note.hidden = true;
      const stage = vidPlayer.parentElement;
      if (stage) stage.hidden = false;
      /* Demo voice-over lines are shown as subtitles under the player: a phone on ice is often
         muted, and the coach's words must stay visible. */
      let cap = box && box.querySelector('.rz-drill__caption');
      if (!cap && box) { cap = document.createElement('p'); cap.className = 'rz-drill__caption'; cap.setAttribute('aria-live', 'polite'); box.append(cap); }
      if (cap) { cap.hidden = true; cap.textContent = ''; }
      vidPlayer.ontimeupdate = null;
      const bindCaptions = cues => {
        if (!cap || !Array.isArray(cues) || !cues.length) return;
        cap.hidden = false;
        const show = () => {
          const t = vidPlayer.currentTime;
          let cur = null;
          for (const c of cues) { if (c.t <= t + 0.05) cur = c; else break; }
          const txt = cur ? cur.text : cues[0].text;
          if (cap.textContent !== txt) cap.textContent = txt;
        };
        vidPlayer.ontimeupdate = show; show();
      };
      const noDemo = () => {
        if (stage) stage.hidden = true;          /* empty black player carries no information */
        if (cap) cap.hidden = true;
        if (note) { note.hidden = false;
          note.textContent = '3D demo for this drill is still being prepared — follow the steps below.'; }
      };
      if (drill.videoUrl) vidPlayer.src = drill.videoUrl;
      else if (!drill.id) noDemo();               /* block without id (warm-up): nowhere to send the request */
      else {
        fetch(`/api/drill_media/${encodeURIComponent(drill.id)}?lang=en`)
          .then(r => r.ok ? r.json() : null)
          .then(m => { if (m && m.url) { vidPlayer.src = m.url; bindCaptions(m.cues);
            /* The demo voice is synthesized; the TTS terms require saying so */
            const parts = [m.kind === 'related' && m.note ? m.note : '',
                           m.voice_note ? 'AI-generated voice' : ''].filter(Boolean);
            if (note && parts.length) { note.hidden = false; note.textContent = parts.join(' · '); }
          } else noDemo(); })
          .catch(noDemo);
      }
    }

    /* Dosage: only measured or prescribed values. The default '3 × 6 · 90 s' is
       an invention the user reads as the coach's prescription. When the drill
       has no structural sets/reps (livePlan from the backend is only text
       dosageDesc), parse that same text with the same parser as
       the set tracker (window.COACH.parseDosage), otherwise the drill card
       honestly shows '—' although the text below already says '5 per leg'
       (found in a live browser check). */
    const parsed = (window.COACH && window.COACH.parseDosage)
      ? window.COACH.parseDosage(drill.dosageDesc) : { sets: null, reps: null };
    const dSets = drill.sets ?? parsed.sets;
    const dReps = drill.reps ?? (parsed.repsLabel ?? parsed.reps);
    /* The SETS/REPS/REST boxes make sense only when the numbers
       are really there. Otherwise hide the grid and show the dosage itself:
       it is always meaningful ('5 per leg'). */
    const grid = document.getElementById('drill-dosage-grid');
    const hasNumbers = (dSets != null) || (dReps != null) || (drill.rest != null);
    if (grid) grid.hidden = !hasNumbers;
    const setsEl = document.getElementById('drill-sets-val');
    if (setsEl) setsEl.textContent = dSets ?? '—';

    const repsEl = document.getElementById('drill-reps-val');
    if (repsEl) repsEl.textContent = dReps ?? '—';

    const restEl = document.getElementById('drill-rest-val');
    if (restEl) restEl.innerHTML = drill.rest
      ? `${drill.rest}<span class="rz-metric__u"> s</span>` : '—';

    const descEl = document.getElementById('drill-dosage-desc');
    if (descEl) {
      descEl.textContent = drill.dosageDesc
        || 'Quality matters more than speed.';
      /* without numeric boxes the dosage is the main instruction, so it is larger */
      descEl.classList.toggle('rz-drill__dose--primary', !hasNumbers);
    }

    const cueEl = document.getElementById('drill-cue-val');
    if (cueEl) cueEl.textContent = drill.cue ? `“${drill.cue}”` : '';
    /* a 'one focus thought' card with no thought is an empty frame */
    const cueCard = document.getElementById('drill-one-cue');
    if (cueCard) cueCard.hidden = !drill.cue;

    const stepsList = document.getElementById('drill-steps-list');
    if (stepsList && drill.steps) {
      stepsList.innerHTML = drill.steps.map((st, i) => `
        <div class="rz-log-row session-block-row is-static">
          <span class="rz-log-row__ic session-block-idx is-active">${i + 1}</span>
          <span class="rz-log-row__main rz-drill__step">${st}</span>
        </div>
      `).join('');
    }

    const mistakesCard = document.getElementById('card-drill-mistakes');
    const mistakesList = document.getElementById('drill-mistakes-list');
    const hasMistakes = drill.mistakes && drill.mistakes.length;
    if (mistakesCard) mistakesCard.hidden = !hasMistakes;
    if (mistakesList && hasMistakes) {
      mistakesList.innerHTML = drill.mistakes.map((m, i) => `
        <div class="rz-log-row is-static">
          <span class="rz-log-row__ic rz-drill__mistake-ic">!</span>
          <span class="rz-log-row__main rz-drill__mistake">${m}</span>
        </div>
      `).join('');
    }

    const gateEl = document.getElementById('drill-gate-val');
    /* Without drill.gate no pass criterion is shown: a concrete number would be invented for
       a drill that has none. */
    if (gateEl) gateEl.textContent = drill.gate || 'no progression criterion recorded';

    const srcEl = document.getElementById('drill-source-val');
    if (srcEl) srcEl.textContent = drill.source
      ? `Source: ${drill.source}`
      : 'Source: JumpSight knowledge base';

    const startBtn = document.getElementById('btn-drill-start-set');
    if (startBtn) {
      startBtn.innerHTML = (dSets && dReps)
        ? `<span>Start set · ${dSets} × ${dReps}</span>`
        : `<span>Start set</span>`;
      startBtn.onclick = () => {
        if (window.COACH && window.COACH.startSession) {
          window.COACH.startSession(drill);
        }
      };
    }

    NS.go('drill');
  }

  function openDrillBlock(idx) {
    /* A block of the REAL plan opens its own drill. */
    const C = window.COACH || {};
    const list = (C.livePlan && C.livePlan.length) ? C.livePlan : (C.DRILLS_DB || []);
    const item = list[idx % list.length];
    if (item) openDrill(item);
  }

  /* ── 3.1 Answer Screen Renderer & Video Sync ── */
  function rebuildPills() {
    /* '1 / 3' and two arrows: exactly two numbers for any number of attempts
       (a chip per attempt would put as many numbers on screen as jumps in the video).
       The switcher makes sense only when there are several attempts, so the whole block is shown then. */
    const nav = document.getElementById('ans-attempt-nav');
    const pos = document.getElementById('ans-att-pos');
    const total = Math.max(1, NS.activeAttempts.length);
    if (nav) nav.hidden = NS.activeAttempts.length < 2;
    if (pos) pos.textContent = `${(NS.currentAttemptIdx || 0) + 1} / ${total}`;
    const step = d => () => NS.renderAttempt((NS.currentAttemptIdx + d + total) % total);
    const prev = document.getElementById('btn-att-prev');
    const next = document.getElementById('btn-att-next');
    if (prev) prev.onclick = step(-1);
    if (next) next.onclick = step(1);
    if (pos) pos.onclick = () => {
      try { if (window.__jsRevealDetail) window.__jsRevealDetail(true); } catch (e) { }
      const card = document.getElementById('card-attempts');
      if (card && !card.hidden) card.scrollIntoView({ block: 'start', behavior: 'smooth' });
    };
  }

  Object.assign(NS, {
     openDrill, openDrillBlock, rebuildPills,
  });
})();
