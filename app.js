/* ====================================================================
   THE JAMMERZ — app.js
   GSAP + ScrollTrigger + Lenis smooth scroll + interactions
   ==================================================================== */

// Active la classe gsap-ready UNIQUEMENT si GSAP + ScrollTrigger sont disponibles.
// Si ces libs ne chargent pas, le contenu reste visible (fallback de sécurité).
if (window.gsap && window.ScrollTrigger) {
  document.documentElement.classList.add('gsap-ready');
}

// Filet de sécurité ABSOLU : après 4s, si du contenu est encore caché, on le révèle.
setTimeout(() => {
  document.querySelectorAll('[data-reveal]').forEach(el => {
    const cs = getComputedStyle(el);
    if (parseFloat(cs.opacity) < 0.1) {
      el.style.opacity = '1';
      el.style.transform = 'none';
    }
  });
}, 4000);

document.addEventListener('DOMContentLoaded', () => {

  /* ---------- 1. LOADER ---------- */
  const loader = document.getElementById('loader');
  window.addEventListener('load', () => {
    setTimeout(() => loader.classList.add('hidden'), 600);
  });
  // Filet : cache le loader après 3s même si load ne fire pas
  setTimeout(() => loader && loader.classList.add('hidden'), 3000);

  /* ---------- 2. YEAR ---------- */
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- 3. LENIS SMOOTH SCROLL ---------- */
  // Garde-fou : si le CDN Lenis ne charge pas (unpkg bloque par ORB, coupure
  // reseau, bloqueur de pub...), on degrade proprement au lieu de casser TOUT
  // le JS de la page. Le scroll natif prend alors le relais.
  let lenis = null;
  if (typeof Lenis !== 'undefined') {
    lenis = new Lenis({
      duration: 1.1,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 1,
      touchMultiplier: 2
    });
    const raf = (time) => {
      lenis.raf(time);
      requestAnimationFrame(raf);
    };
    requestAnimationFrame(raf);

    if (window.gsap && window.ScrollTrigger) {
      gsap.registerPlugin(ScrollTrigger);
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add((time) => lenis.raf(time * 1000));
      gsap.ticker.lagSmoothing(0);
    }
  } else if (window.gsap && window.ScrollTrigger) {
    // Lenis absent : on enregistre quand meme ScrollTrigger pour les animations.
    gsap.registerPlugin(ScrollTrigger);
  }

  /* ---------- 4. CUSTOM CURSOR ---------- */
  const cursor = document.getElementById('cursor');
  const cursorFollower = document.getElementById('cursorFollower');
  if (cursor && cursorFollower && window.matchMedia('(pointer: fine)').matches) {
    let mouseX = 0, mouseY = 0;
    let followerX = 0, followerY = 0;
    document.addEventListener('mousemove', (e) => {
      mouseX = e.clientX; mouseY = e.clientY;
      cursor.style.left = mouseX + 'px';
      cursor.style.top = mouseY + 'px';
    });
    function animateFollower() {
      followerX += (mouseX - followerX) * 0.15;
      followerY += (mouseY - followerY) * 0.15;
      cursorFollower.style.left = followerX + 'px';
      cursorFollower.style.top = followerY + 'px';
      requestAnimationFrame(animateFollower);
    }
    animateFollower();

    document.querySelectorAll('a, button, .member-card, .tarif-card, .video-wrap, .songs li, input, select, textarea').forEach(el => {
      el.addEventListener('mouseenter', () => cursorFollower.classList.add('hover'));
      el.addEventListener('mouseleave', () => cursorFollower.classList.remove('hover'));
    });
  }

  /* ---------- 5. NAV SCROLLED + ACTIVE LINK + BURGER ---------- */
  const nav = document.getElementById('nav');
  const navMenu = document.querySelector('.nav-menu');
  const navBurger = document.getElementById('navBurger');

  if (navBurger) {
    navBurger.addEventListener('click', () => {
      navBurger.classList.toggle('active');
      navMenu.classList.toggle('open');
    });
    navMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        navBurger.classList.remove('active');
        navMenu.classList.remove('open');
      });
    });
  }

  // Smooth scroll pour les liens internes (Lenis si dispo, sinon natif)
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (targetId === '#') return;
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        if (lenis) {
          lenis.scrollTo(target, { offset: -80, duration: 1.4 });
        } else {
          const y = target.getBoundingClientRect().top + window.pageYOffset - 80;
          window.scrollTo({ top: y, behavior: 'smooth' });
        }
      }
    });
  });

  /* ---------- 6. GSAP SCROLL ANIMATIONS ---------- */
  if (window.gsap && window.ScrollTrigger) {

    // Nav scrolled state
    ScrollTrigger.create({
      start: 'top -50',
      end: 99999,
      onUpdate: (self) => {
        if (self.scroll() > 50) nav.classList.add('scrolled');
        else nav.classList.remove('scrolled');
      }
    });

    // Reveal generic animation
    gsap.utils.toArray('[data-reveal]').forEach((el, i) => {
      gsap.fromTo(el,
        { opacity: 0, y: 50 },
        {
          opacity: 1, y: 0,
          duration: 1.1,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: el,
            start: 'top bottom-=50',
            toggleActions: 'play none none none'
          }
        }
      );
    });

    // Hero parallax + scale au scroll
    gsap.to('.hero-name', {
      scale: 1.15,
      opacity: 0.4,
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: true
      }
    });
    gsap.to('.hero-tag, .hero-subtitle, .hero-actions', {
      y: -100,
      opacity: 0,
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: true
      }
    });

    // Stats counter — voir bloc plus bas (IntersectionObserver, plus robuste)

    // Background blobs parallax
    gsap.to('.blob-1', { y: -150, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 1 } });
    gsap.to('.blob-2', { y: -300, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 1 } });
    gsap.to('.blob-3', { y: -200, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 1.5 } });

    // Section title split-like reveal
    gsap.utils.toArray('.section-title').forEach(title => {
      gsap.fromTo(title,
        { opacity: 0, y: 80, scale: 0.9 },
        {
          opacity: 1, y: 0, scale: 1,
          duration: 1.4,
          ease: 'expo.out',
          scrollTrigger: {
            trigger: title,
            start: 'top 80%',
            toggleActions: 'play none none none'
          }
        }
      );
    });

    // Members staggered entrance
    gsap.fromTo('.member-card',
      { opacity: 0, y: 60, rotateX: 15 },
      {
        opacity: 1, y: 0, rotateX: 0,
        duration: 1.2,
        ease: 'power3.out',
        stagger: 0.12,
        scrollTrigger: {
          trigger: '.members-grid',
          start: 'top 75%',
          toggleActions: 'play none none none'
        }
      }
    );

    // Tarif cards staggered
    gsap.fromTo('.tarif-card',
      { opacity: 0, y: 50, scale: 0.95 },
      {
        opacity: 1, y: 0, scale: 1,
        duration: 0.9,
        ease: 'power3.out',
        stagger: 0.08,
        scrollTrigger: {
          trigger: '.tarifs-grid',
          start: 'top 80%',
          toggleActions: 'play none none none'
        }
      }
    );

    // Songs list reveal (uniquement le set actif au scroll initial — les autres
    // s'animent via le handler de tab pour eviter qu'ils restent invisibles)
    gsap.utils.toArray('.songs.songs-active li').forEach((li, i) => {
      gsap.fromTo(li,
        { opacity: 0, x: -30 },
        {
          opacity: 1, x: 0,
          duration: 0.6,
          ease: 'power2.out',
          delay: i * 0.02,
          scrollTrigger: {
            trigger: li,
            start: 'top bottom-=20',
            toggleActions: 'play none none none'
          }
        }
      );
    });

    // Section nav active link tracking
    const sections = document.querySelectorAll('section[id]');
    sections.forEach(section => {
      ScrollTrigger.create({
        trigger: section,
        start: 'top 50%',
        end: 'bottom 50%',
        onEnter: () => setActiveLink(section.id),
        onEnterBack: () => setActiveLink(section.id)
      });
    });
    function setActiveLink(id) {
      document.querySelectorAll('.nav-menu a').forEach(a => a.classList.remove('active'));
      const link = document.querySelector(`.nav-menu a[href="#${id}"]`);
      if (link) link.classList.add('active');
    }
  }

  /* ---------- 6.5 STATS COUNTERS (bulletproof) ----------
     STRATEGIE :
     1. Les valeurs finales sont DEJA dans le HTML (6, 35, 100%, 4H).
        Donc meme sans JS, l'utilisateur voit les bonnes donnees.
     2. Le JS optionnellement reset a 0 puis anime jusqu'a target.
        Si quoi que ce soit foire, on ne cache pas la donnee.
     ------------------------------------------------------------- */
  function setupCounters() {
    var els = document.querySelectorAll('.stat-num[data-count]');
    if (!els.length) return;

    function animate(el) {
      if (el.dataset.animated === '1') return;
      el.dataset.animated = '1';
      var target = parseInt(el.dataset.count, 10);
      var suffix = el.dataset.suffix || '';
      // Reset visuel a 0 juste avant l'anim (sinon on voit la valeur fixe sauter)
      el.textContent = '0' + suffix;
      var duration = 1800;
      var start = performance.now();
      function tick(now) {
        var elapsed = now - start;
        var progress = Math.min(elapsed / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (progress < 1) requestAnimationFrame(tick);
        else el.textContent = target + suffix;
      }
      requestAnimationFrame(tick);
    }

    function inViewport(el) {
      var r = el.getBoundingClientRect();
      var vh = window.innerHeight || document.documentElement.clientHeight;
      return r.top < vh * 0.9 && r.bottom > 0;
    }

    // Fire pour les elements deja visibles AU CHARGEMENT
    els.forEach(function(el){ if (inViewport(el)) animate(el); });

    // Sur scroll : check les autres
    var onScroll = function() {
      els.forEach(function(el){
        if (el.dataset.animated !== '1' && inViewport(el)) animate(el);
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });

    // Filet : si scroll ne fire pas, on anime tout apres 5s
    setTimeout(function() {
      els.forEach(function(el){ if (el.dataset.animated !== '1') animate(el); });
    }, 5000);
  }

  // Lance immediatement (DOMContentLoaded est deja fire ici)
  setupCounters();
  // Re-check apres window load (au cas ou)
  window.addEventListener('load', setupCounters);

  /* ---------- 6.6 CARROUSEL AGENDA ----------
     Le controleur du carrousel « Nos prochains lives » est volontairement place
     HORS de ce handler (en bas du fichier, IIFE autonome initGigsCarousel) pour
     qu'il fonctionne meme si une lib externe (GSAP/Lenis) casse ce bloc. */

  /* ---------- 7. REPERTOIRE TABS ---------- */
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('tab-active'));
      tab.classList.add('tab-active');
      document.querySelectorAll('[data-tab-content]').forEach(c => c.classList.remove('songs-active'));
      const content = document.querySelector(`[data-tab-content="${target}"]`);
      if (!content) return;
      content.classList.add('songs-active');
      // Force visibilite immediate des li (en cas ou scrollTrigger les a mis a opacity:0)
      content.querySelectorAll('li').forEach(li => {
        li.style.opacity = '1';
        li.style.transform = 'none';
      });
      if (window.gsap) {
        gsap.fromTo(content.querySelectorAll('li'),
          { opacity: 0, y: 20 },
          { opacity: 1, y: 0, duration: 0.5, stagger: 0.03, ease: 'power2.out',
            clearProps: 'transform' }
        );
      }
      if (window.ScrollTrigger) ScrollTrigger.refresh();
    });
  });

  /* ---------- 8. VIDEOS ----------
     Les iframes YouTube sont desormais embedees directement dans le HTML.
     Le visiteur clique sur Play du player YouTube natif -> ca part.
     Plus de logique custom de lazy-load qui pouvait casser. */

  /* ---------- 9. CONTACT FORM ---------- */
  const form = document.getElementById('contactForm');
  const toast = document.getElementById('toast');

  // Si l'URL contient ?sent=1 (retour Formsubmit), on affiche le toast
  if (window.location.search.includes('sent=1') && toast) {
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 5000);
    // Nettoie l'URL
    window.history.replaceState({}, '', window.location.pathname);
  }

  if (form) {
    form.addEventListener('submit', (e) => {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.querySelector('span:first-child').textContent = 'Envoi en cours...';
        submitBtn.disabled = true;
      }
      // Le formulaire continue de soumettre normalement vers Formsubmit
    });
  }

  /* ---------- 10. PERFORMANCE: refresh ScrollTrigger après load images ---------- */
  if (window.ScrollTrigger) {
    window.addEventListener('load', () => ScrollTrigger.refresh());
  }
});

/* ====================================================================
   CARROUSEL AGENDA / PROCHAINS LIVES  —  IIFE AUTONOME
   Volontairement HORS du handler DOMContentLoaded principal : si une lib
   externe (GSAP/Lenis) casse ce handler, le carrousel continue de marcher.
   Defilement horizontal natif (scroll-snap) + fleches + barre de progression.
   Si tout tient dans la largeur -> mode statique (cartes centrees, controles
   caches). Auto-init que le DOM soit deja pret ou non. Aucune dependance.
   ==================================================================== */
(function initGigsCarousel() {
  function setup() {
    const carousel = document.querySelector('.gigs-carousel');
    if (!carousel || carousel.dataset.gigsReady === '1') return;
    const viewport = carousel.querySelector('.gigs-viewport');
    const track = carousel.querySelector('.gigs-track');
    if (!viewport || !track) return;          // cartes pas encore la : on reessaiera au load
    carousel.dataset.gigsReady = '1';

    const prevBtn = carousel.querySelector('.gigs-prev');
    const nextBtn = carousel.querySelector('.gigs-next');
    const thumb = carousel.querySelector('.gigs-progress-thumb');
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const cards = () => track.querySelectorAll('.gig-card');

    // Pas de defilement = largeur d'une carte + gap (mesure reelle).
    function stepSize() {
      const list = cards();
      if (list.length < 2) return viewport.clientWidth;
      const d = Math.abs(list[1].getBoundingClientRect().left -
                         list[0].getBoundingClientRect().left);
      return d > 0 ? d : list[0].getBoundingClientRect().width + 20;
    }
    function maxScroll() { return Math.max(0, track.scrollWidth - viewport.clientWidth); }
    function currentIndex() { return Math.round(viewport.scrollLeft / stepSize()); }

    function scrollToIndex(i) {
      const max = cards().length - 1;
      const clamped = Math.max(0, Math.min(i, max));
      viewport.scrollTo({ left: Math.round(clamped * stepSize()),
                          behavior: reduce ? 'auto' : 'smooth' });
    }

    function refresh() {
      const max = maxScroll();
      const overflow = max > 4;
      carousel.classList.toggle('is-static', !overflow);
      const x = viewport.scrollLeft;
      if (prevBtn) prevBtn.disabled = !overflow || x <= 2;
      if (nextBtn) nextBtn.disabled = !overflow || x >= max - 2;
      if (thumb) {
        const sw = track.scrollWidth || 1;
        const frac = Math.min(1, viewport.clientWidth / sw);
        const room = 100 - frac * 100;
        thumb.style.width = (frac * 100) + '%';
        thumb.style.left = (max > 0 ? (x / max) * room : 0) + '%';
      }
    }

    if (prevBtn) prevBtn.addEventListener('click', () => scrollToIndex(currentIndex() - 1));
    if (nextBtn) nextBtn.addEventListener('click', () => scrollToIndex(currentIndex() + 1));

    viewport.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); scrollToIndex(currentIndex() + 1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); scrollToIndex(currentIndex() - 1); }
    });

    let ticking = false;
    viewport.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { refresh(); ticking = false; });
    }, { passive: true });

    window.addEventListener('resize', refresh, { passive: true });
    window.addEventListener('load', refresh);
    // Plusieurs passes : polices/images peuvent modifier les largeurs apres coup.
    refresh();
    setTimeout(refresh, 300);
    setTimeout(refresh, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
  // Filet : si les cartes arrivent tard (polices/agenda), on retente au load.
  window.addEventListener('load', setup);
})();
