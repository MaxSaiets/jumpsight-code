/* Job opening, answer-video sync controller, follow zoom and theme engine. */
(function () {
  'use strict';
  const NS = window.JS.app;
  async function openJob(jobId, stem) {
    const epoch = ++NS.resultRequestEpoch;
    NS.pendingOpenEpoch = epoch;
    try {
      const r = await NS.fetchJobResults(jobId, { requestEpoch: epoch, fromHistory: true });
      if (epoch !== NS.resultRequestEpoch) return false;
      if (r !== true) return r;
      NS.go('answer');
      /* A log row is a specific ATTEMPT in the video; we open exactly it,
         not the first (a tap on 'fall' must not open a clean attempt next to it). */
      if (stem) {
        const i = NS.activeAttempts.findIndex(a => a && a.stem === stem);
        if (i > 0) NS.renderAttempt(i);
      }
      return r;
    } finally {
      if (NS.pendingOpenEpoch === epoch) NS.pendingOpenEpoch = null;
    }
  }

  /* HONEST ESTIMATE OF ANALYSIS TIME.
     MEASURED on seven evaluation clips with a warm server, in TWO
     independent runs (runs/evidence/rerun_baseline.json and rerun_batch.json
     of a separate research project, 14 measurements together): analysis time was
     0.68–2.16 of the video's own duration, median 0.88 and 1.01 respectively,
     in seconds 6.7–30.9 for clips of 8.0–40.2 s. The coefficients below are
     the measured edges of both runs, not round numbers 'with a margin'.
     One run is too few: on one clip the ratio was 0.77 in
     the first run and 0.68 in the second, so a lower edge taken from one
     run would prove overestimated next time and the forecast would miss
     the real 27.2 s from below.
     Also: until the models are warm, any forecast is misleading (the first
     analysis right after server start cost 30.4 s versus 7.1 s on a
     warm one), so we first ask /warm_state. */
  /* Constants are used only for the first answer, before /status arrives;
     afterwards the range comes from the server's eta_lo/eta_hi (the same law, measured
     in production on a CPU worker: 12 s clip → 11–19 s, 87 s → 40–90 s). */
  function setWaitEta(durationS) {
    const el = document.getElementById('wait-eta');
    if (!el) return;
    delete el.dataset.srv;
    el.dataset.live = '1';
    el.textContent = 'Usually about a minute. You can go to Training — we will tell you when it is ready.';
  }

  /* ZOOM. On a wide frame (the whole rink, broadcast) the skater is a tenth of the frame, and on a phone the jump
     is not visible. The frame is scaled and shifted so the skater stands in the
     center, following the MEASURED track (pose joint box at the same time as
     take-off and landing; jumpsight_bridge.skater_track). Nothing
     is drawn on top (PRODUCT.md §1). Without a track
     there is no button. */
  const FOLLOW = { track: null, on: false };
  function trackAt(track, t) {
    const p = track && track.pts;
    if (!p || !p.length) return null;
    if (t <= p[0][0]) return p[0];
    if (t >= p[p.length - 1][0]) return p[p.length - 1];
    let lo = 0, hi = p.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (p[mid][0] <= t) lo = mid; else hi = mid; }
    const a = p[lo], b = p[hi], u = (t - a[0]) / Math.max(1e-6, b[0] - a[0]);
    return [t, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }
  /* The skater fills about 60% of the frame height; no more than 3× zoom, beyond that pixels show */
  function followZoomOf(track) {
    return track && Number.isFinite(track.person_h) ? Math.min(3, Math.max(1, 0.6 / Math.max(0.05, track.person_h))) : 1;
  }
  function followTransform(vid, track, z) {
    if (!vid || !track || z <= 1.01) return '';
    const W = vid.clientWidth, H = vid.clientHeight, vw = vid.videoWidth, vh = vid.videoHeight;
    if (!W || !H || !vw || !vh || getComputedStyle(vid).objectFit !== 'contain') return '';
    const s0 = Math.min(W / vw, H / vh), cw = vw * s0, ch = vh * s0, ox = (W - cw) / 2, oy = (H - ch) / 2;
    const p = trackAt(track, vid.currentTime);
    if (!p) return '';
    const px = ox + p[1] * cw, py = oy + p[2] * ch;
    let tx = W / 2 - px * z, ty = H / 2 - py * z;
    /* no empty margin past the frame edge where the scale allows it */
    const minX = W - (ox + cw) * z, maxX = -ox * z, minY = H - (oy + ch) * z, maxY = -oy * z;
    tx = minX <= maxX ? Math.min(maxX, Math.max(minX, tx)) : (minX + maxX) / 2;
    ty = minY <= maxY ? Math.min(maxY, Math.max(minY, ty)) : (minY + maxY) / 2;
    return `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(${z.toFixed(3)})`;
  }
  function setFollow(vid, track, on) {
    if (!vid) return;
    const tr = on ? followTransform(vid, track, followZoomOf(track)) : '';
    if (tr) { vid.style.transformOrigin = '0 0'; vid.style.transition = 'none'; vid.style.transform = tr; }
    else if (vid.dataset.follow === '1') { vid.style.transform = ''; vid.style.transformOrigin = ''; vid.style.transition = ''; }
    vid.dataset.follow = tr ? '1' : '0';
  }
  function applyFollow() {
    const st = document.getElementById('ans-vid-stage');
    setFollow(document.getElementById('ans-video'), FOLLOW.track,
      FOLLOW.on && !(st && st.classList.contains('is-cropped')));
  }
  /* on by default when the skater is small (≤ 37% of frame height);
     an explicit choice by the person is remembered */
  function syncFollowFor(a) {
    FOLLOW.track = a && a.track && Array.isArray(a.track.pts) && a.track.pts.length >= 5 ? a.track : null;
    const z = followZoomOf(FOLLOW.track);
    let pref = null;
    try { pref = localStorage.getItem('js.follow'); } catch (_) { }
    /* On a 576×1024 video at
       410 kbit/s, the zoom stretched several hundred pixels across the whole screen.
       By default, close-up is used only when the source pixel stretch is ≤ 1.2× (CSS px). */
    const vidEl = document.getElementById('ans-video');
    let lowRes = false;
    if (vidEl && vidEl.videoHeight > 0) {
      const shownH = vidEl.getBoundingClientRect().height || vidEl.clientHeight || 0;
      lowRes = shownH > 0 && (shownH * z) / vidEl.videoHeight > 1.2;
    } else if (vidEl && !vidEl.dataset.followWait) {
      vidEl.dataset.followWait = '1';
      vidEl.addEventListener('loadedmetadata', () => { delete vidEl.dataset.followWait; syncFollowFor(a); applyFollow(); }, { once: true });
    }
    FOLLOW.on = !!FOLLOW.track && z >= 1.25 && (pref === '1' || (pref === null && z >= 1.6 && !lowRes));
    const btn = document.getElementById('btn-follow');
    if (btn) {
      btn.hidden = !FOLLOW.track || z < 1.25;
      btn.textContent = FOLLOW.on ? 'full frame' : 'close-up';
      btn.setAttribute('aria-pressed', String(FOLLOW.on));
    }
    applyFollow();
  }

  function initVideoSync() {
    const vid = document.getElementById('ans-video');
    if (!vid) return;

    const timeDisp = document.getElementById('vid-time-display');
    const speedBtn = document.getElementById('btn-speed-toggle');

    vid.ontimeupdate = () => {
      if (timeDisp && vid.duration) {
        const cur = vid.currentTime.toFixed(1);
        const dur = vid.duration.toFixed(1);
        timeDisp.textContent = `${cur}s / ${dur}s`;
      }
      /* ATTEMPT WINDOW: in a 35-second training recording the player
         played the whole clip, and the jump had to be hunted for. While playing, the loop is
         within [take-off − 1 s, landing + 1 s]; manual seeking
         and frame-by-frame mode are not touched (only when not paused). */
      if (NS.ANS_WIN && !NS.scrubAll && !vid.paused && vid.currentTime > NS.ANS_WIN.t1 + 0.05) vid.currentTime = NS.ANS_WIN.t0;
      syncScrub();
    };

    /* ── SCRUB BAR ──────────────────────────────────────────────────
       Without it the jump could only be caught with buttons. The range is the attempt window
       or the whole recording; the flight is highlighted from the MEASURED take-off and
       landing; under the bar, the time and phase (approach / flight +0.12 s / exit). */
    const scrub = document.getElementById('ans-scrub');
    const range = document.getElementById('ans-scrub-range');
    const flight = document.getElementById('ans-scrub-flight');
    const nowEl = document.getElementById('ans-scrub-now');
    const phaseEl = document.getElementById('ans-scrub-phase');
    const allBtn = document.getElementById('btn-scrub-all');
    const span = () => {
      const dur = vid.duration && isFinite(vid.duration) ? vid.duration : null;
      if (!dur) return null;
      if (NS.ANS_WIN && !NS.scrubAll) return [NS.ANS_WIN.t0, Math.min(NS.ANS_WIN.t1, dur)];
      return [0, dur];
    };
    let dragging = false;
    function syncScrub() {
      if (!scrub || !range) return;
      const sp = span();
      scrub.hidden = !sp;
      if (!sp) return;
      const [r0, r1] = sp, w = Math.max(1e-6, r1 - r0);
      if (!dragging) range.value = String(Math.round(Math.min(1, Math.max(0, (vid.currentTime - r0) / w)) * 1000));
      if (flight) {
        if (NS.ANS_PH) {
          const a = Math.max(0, (NS.ANS_PH.t - r0) / w), b = Math.min(1, (NS.ANS_PH.l - r0) / w);
          flight.hidden = !(b > a);
          flight.style.left = `${(a * 100).toFixed(2)}%`;
          flight.style.width = `${((b - a) * 100).toFixed(2)}%`;
        } else flight.hidden = true;
      }
      const t = vid.currentTime;
      if (nowEl) nowEl.textContent = `${t.toFixed(2)} s`;
      if (phaseEl) {
        phaseEl.textContent = !NS.ANS_PH ? ''
          : t < NS.ANS_PH.t ? `${(NS.ANS_PH.t - t).toFixed(2)} s to take-off`
          : t <= NS.ANS_PH.l ? `in the air +${(t - NS.ANS_PH.t).toFixed(2)} s`
          : `after landing +${(t - NS.ANS_PH.l).toFixed(2)} s`;
        phaseEl.classList.toggle('is-air', !!NS.ANS_PH && t >= NS.ANS_PH.t && t <= NS.ANS_PH.l);
      }
      if (allBtn) {
        allBtn.hidden = !NS.ANS_WIN;
        allBtn.textContent = NS.scrubAll ? 'jump only' : 'whole video';
      }
    }
    window.__jsScrubSync = syncScrub;
    if (range) {
      const seekTo = () => {
        const sp = span(); if (!sp) return;
        const v = Number(range.value) / 1000;
        try { vid.currentTime = sp[0] + v * (sp[1] - sp[0]); } catch (_) { }
        syncScrub();
      };
      range.addEventListener('pointerdown', () => { dragging = true; vid.pause(); });
      range.addEventListener('input', () => { vid.pause(); seekTo(); });
      const end = () => { dragging = false; seekTo(); };
      range.addEventListener('pointerup', end);
      range.addEventListener('change', end);
    }
    if (allBtn) allBtn.onclick = () => { NS.scrubAll = !NS.scrubAll; syncScrub(); };
    vid.addEventListener('loadedmetadata', syncScrub);
    vid.addEventListener('seeked', syncScrub);
    /* 'close-up' follows the frame during scrubbing too, and when paused */
    ['loadedmetadata', 'seeked', 'timeupdate'].forEach(ev => vid.addEventListener(ev, applyFollow));
    window.addEventListener('resize', applyFollow);
    document.addEventListener('fullscreenchange', () => setTimeout(applyFollow, 50));
    const followBtn = document.getElementById('btn-follow');
    if (followBtn) followBtn.onclick = () => {
      FOLLOW.on = !FOLLOW.on;
      try { localStorage.setItem('js.follow', FOLLOW.on ? '1' : '0'); } catch (_) { }
      followBtn.textContent = FOLLOW.on ? 'full frame' : 'close-up';
      followBtn.setAttribute('aria-pressed', String(FOLLOW.on));
      applyFollow();
    };
    /* during playback timeupdate fires about 4 times per second, so the bar jerked */
    (function tick() {
      if (!vid.paused && !dragging && document.getElementById('scr-answer') && !document.getElementById('scr-answer').hidden) { syncScrub(); applyFollow(); }
      requestAnimationFrame(tick);
    })();
    /* a tap on the video itself: pause / play, as in any player */
    vid.addEventListener('click', () => {
      if (vid.paused) vid.play().catch(() => {}); else vid.pause();
    });

    if (speedBtn) {
      speedBtn.onclick = () => {
        if (NS.videoSpeed === 1.0) NS.videoSpeed = 0.5;
        else if (NS.videoSpeed === 0.5) NS.videoSpeed = 0.25;
        else NS.videoSpeed = 1.0;
        vid.playbackRate = NS.videoSpeed;
        /* the word stays next to the number. A bare '1.0x' stood above
           the ROTATIONS caption and read as '1.0 rotation', the only visible number
           on a screen where numbers are hidden on purpose. */
        speedBtn.innerHTML = `${NS.videoSpeed}x <span class="speed-pill__w" data-t="speedWord">`
          + 'speed' + '</span>';
        NS.playClickSound(700, 0.04);
      };
    }

    // Frame-by-frame Stepper Controls
    const btnPrevFrame = document.getElementById('btn-frame-prev');
    if (btnPrevFrame) {
      btnPrevFrame.onclick = () => {
        vid.pause();
        vid.currentTime = Math.max(0, vid.currentTime - 1 / NS.videoFps);
        NS.playClickSound(500, 0.02);
      };
    }

    const btnNextFrame = document.getElementById('btn-frame-next');
    if (btnNextFrame) {
      btnNextFrame.onclick = () => {
        vid.pause();
        vid.currentTime = Math.min(vid.duration || 10, vid.currentTime + 1 / NS.videoFps);
        NS.playClickSound(500, 0.02);
      };
    }

    const btnFramePlay = document.getElementById('btn-frame-play');
    if (btnFramePlay) {
      btnFramePlay.onclick = () => {
        if (vid.paused) {
          vid.play().catch(() => {});
        } else {
          vid.pause();
        }
        NS.playClickSound(600, 0.03);
      };
    }

    // Skeleton Canvas HUD (Disabled by default - clean video only)
    const skelCanvas = document.getElementById('ans-skeleton-canvas');
    const btnSkel = document.getElementById('btn-toggle-skeleton');
    if (btnSkel) btnSkel.style.color = 'var(--dim2)';

    /* This video's pose is not in the browser (jumpsight does not serve it to the front end),
       so the overlay is impossible. A button that 'does nothing' is worse than a missing one:
       on a phone a title tooltip does not exist, and the control looked
       broken. We hide it; the canvas stays for the future. */
    if (btnSkel) btnSkel.style.display = 'none';

    // 3D Avatar Toggle (Switch between video+skeleton and interactive 3D character)
    const btnAvatar3D = document.getElementById('btn-toggle-avatar3d');
    const avatarFrame = document.getElementById('ans-avatar-frame');
    const ansVideo = document.getElementById('ans-video');

    if (btnAvatar3D && avatarFrame && ansVideo) {
      const avatarOff = () => {
        btnAvatar3D.style.color = '';
        avatarFrame.src = 'about:blank';
        avatarFrame.style.display = 'none';
        ansVideo.style.display = 'block';
        if (skelCanvas) skelCanvas.style.display = 'block';
      };
      btnAvatar3D.onclick = async () => {
        NS.playClickSound(680, 0.03);
        /* State is read from the DOM, not from a closure: the iframe is put out from outside too
           (navigation to another screen), and the local variable would then lie. */
        if (avatarFrame.style.display === 'block') { avatarOff(); return; }
        const a = NS.activeAttempts[NS.currentAttemptIdx] || NS.activeAttempts[0];
        const stem = a && a.stem;
        if (!stem) return;
        /* Check BEFORE display, otherwise the user gets an empty viewer without explanation. The avatar is built for almost every attempt
           (coverage 97%, tools/avatar_coverage.py), so refusal is RARE, and that is
           exactly why it must name the reason rather than say 'unavailable'.
           The reason is the point. */
        let ok = false;
        let why = '';
        try { ok = (await fetch(`/coach/avatar3d/${stem}`, { method: 'HEAD' })).ok; } catch (e) { }
        if (!ok) {
          const old = btnAvatar3D.textContent;
          btnAvatar3D.disabled = true;
          btnAvatar3D.textContent = 'Building 3D…';
          try {
            const started = await fetch(`/coach/avatar3d/${stem}/generate`, { method: 'POST' });
            if (started.ok) {
              for (let i = 0; i < 90; i++) {
                await new Promise(resolve => setTimeout(resolve, 1000));
                const status = await fetch(`/coach/avatar3d/${stem}/status`);
                const js = status.ok ? await status.json() : { state: 'failed' };
                if (js.state === 'ready') { ok = true; break; }
                if (js.state === 'failed' || js.state === 'unavailable') {
                  why = String(js.detail || '');
                  break;
                }
              }
            }
          } catch (e) { }
          btnAvatar3D.disabled = false;
          btnAvatar3D.textContent = old;
          if (!ok) {
            /* The reason comes from the server, not a shared 'unavailable': three different
               cases (video already removed by TTL, pose not readable,
               phases not measured) require different actions from the person. */
            const short = /video unavailable|video already/i.test(why)
              ? 'the video is no longer on the server'
              : /pose not found|unusable/i.test(why)
              ? 'the pose is unreadable in this footage'
              : /no phases/i.test(why)
              ? 'the jump phases were not measured'
              : '3D unavailable now';
            btnAvatar3D.textContent = short;
            btnAvatar3D.title = why || '';
            btnAvatar3D.style.color = 'var(--dim2)';
            setTimeout(() => { btnAvatar3D.textContent = old; btnAvatar3D.style.color = ''; }, 4000);
            return;
          }
        }
        btnAvatar3D.style.color = 'var(--action)';
        avatarFrame.src = `/coach/avatar/${stem}`;
        avatarFrame.style.display = 'block';
        ansVideo.style.display = 'none';
        if (skelCanvas) skelCanvas.style.display = 'none';
      };
    }

    // Fullscreen (phone: the video is deliberately small, full screen on tap)
    const btnFs = document.getElementById('btn-fullscreen');
    if (btnFs) btnFs.onclick = () => {
      try {
        if (vid.webkitEnterFullscreen && !vid.requestFullscreen) { vid.webkitEnterFullscreen(); return; }   // iOS Safari
        const st = document.getElementById('ans-vid-stage') || vid;
        if (document.fullscreenElement) document.exitFullscreen();
        else (st.requestFullscreen ? st.requestFullscreen() : vid.requestFullscreen()).catch(() => {});
      } catch (e) { }
    };

    // Zoom Lens Toggle (1.0x -> 1.5x -> 2.0x)
    let zoomIdx = 0;
    const zoomLevels = ['1.0x', '1.5x', '2.0x'];
    const vidStage = document.getElementById('ans-vid-stage');
    const btnZoom = document.getElementById('btn-zoom-toggle');
    if (btnZoom && vidStage) {
      btnZoom.onclick = () => {
        zoomIdx = (zoomIdx + 1) % zoomLevels.length;
        btnZoom.textContent = `🔍 ${zoomLevels[zoomIdx]}`;
        vidStage.className = 'vid-stage' + (zoomIdx === 1 ? ' is-zoom-15' : zoomIdx === 2 ? ' is-zoom-20' : '');
        NS.playClickSound(720, 0.04);
      };
    }

    // Voice Coaching Announcement (Web Speech API)
    const btnVoice = document.getElementById('btn-voice-verdict');
    if (btnVoice) {
      btnVoice.onclick = () => {
        if ('speechSynthesis' in window) {
          window.speechSynthesis.cancel();
          /* Demo data is shown ONLY while there is no real analysis yet.
       A real analysis with zero jumps is an honest empty state, not a demo. */
    const list = NS.activeAttempts.length ? NS.activeAttempts
      : [NS.realResults ? { num: '—',
          name: 'No jumps found', verdictClass: 'none',
          verdictTitle: 'No jump found in this video',
          verdictSub: 'Most common causes: the skater is far away or partly out of frame; filmed from above or behind; under 30 fps.',
          airTime: '—', height: '—', errors: null, hasDisambig: false } : NS.emptyAttempt()];
          const a = list[NS.currentAttemptIdx] || list[0];
          const text = `${a.name || 'Jump'}, ${a.num || ''} rotations. ${a.verdictTitle || 'Analysis complete'}.`;
          const utt = new SpeechSynthesisUtterance(text);
          utt.lang = 'en-US';
          utt.rate = 1.0;
          btnVoice.style.color = 'var(--action)';
          utt.onend = () => { btnVoice.style.color = ''; };
          window.speechSynthesis.speak(utt);
          NS.playClickSound(800, 0.05);
        }
      };
    }

    /* KEYBOARD ON DESKTOP: a coach on a laptop steps through frames with the arrows, space pauses,
       [ ] go to the previous/next attempt.
       Only on the answer screen and not from input fields. */
    document.addEventListener('keydown', e => {
      if (NS.currentScreen !== 'answer') return;
      const tag = (e.target && e.target.tagName) || '';
      if (/INPUT|TEXTAREA|SELECT/.test(tag) || (e.target && e.target.isContentEditable)) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        vid.pause();
        const step = (e.shiftKey ? 10 : 1) / NS.videoFps;
        vid.currentTime = e.key === 'ArrowLeft'
          ? Math.max(0, vid.currentTime - step)
          : Math.min(vid.duration || 10, vid.currentTime + step);
      } else if (e.key === ' ' && tag !== 'BUTTON') {
        e.preventDefault();
        if (vid.paused) vid.play().catch(() => {}); else vid.pause();
      } else if (e.key === '[' || e.key === ']') {
        const total = NS.activeAttempts.length;
        if (total > 1) NS.renderAttempt((NS.currentAttemptIdx + (e.key === ']' ? 1 : total - 1)) % total);
      }
    });

    // Interactive Jump Pins on Timeline
    document.querySelectorAll('.jump-pin').forEach(pin => {
      pin.onclick = () => {
        const att = parseInt(pin.getAttribute('data-att') || 0);
        document.querySelectorAll('.jump-pin').forEach(p => p.classList.remove('is-active'));
        pin.classList.add('is-active');
        NS.renderAttempt(att);
      };
    });
  }

  /* ── Theme Engine ── */
  function setTheme(mode) {


    const root = document.documentElement;
    const themeBtn = document.getElementById('btn-theme');

    if (mode === 'dark') {
      root.setAttribute('data-theme', 'dark');
      root.classList.add('dark');
      if (themeBtn) themeBtn.textContent = '☀️';
    } else if (mode === 'light') {
      root.setAttribute('data-theme', 'light');
      root.classList.remove('dark');
      if (themeBtn) themeBtn.textContent = '🌙';
    } else {
      root.removeAttribute('data-theme');
      root.classList.remove('dark');
      const isDarkOS = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      if (themeBtn) themeBtn.textContent = isDarkOS ? '☀️' : '🌙';
    }

    localStorage.setItem('js.theme', mode);

    document.querySelectorAll('.theme-b').forEach(b => {
      if (b.getAttribute('data-theme') === mode) {
        b.classList.add('is-on');
      } else {
        b.classList.remove('is-on');
      }
    });
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const next = current === 'dark' ? 'light' : 'dark';
    setTheme(next);
  }

  function initTheme() {
    const saved = localStorage.getItem('js.theme') || 'auto';
    setTheme(saved);
  }

  Object.assign(NS, {
     openJob, setWaitEta, FOLLOW, setFollow, syncFollowFor, initVideoSync, setTheme, toggleTheme, initTheme,
  });
})();
