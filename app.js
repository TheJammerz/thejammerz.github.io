/* ====================================================================
   THE JAMMERZ — app.js
   GSAP + ScrollTrigger + interactions (defilement 100% natif)
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
    setTimeout(() => loader.classList.add('hidden'), 200);
  });
  // Filet : cache le loader même si load ne fire pas (iframes, CDN lent...).
  // C'est ce délai qui commandait le LCP mesuré par Google : l'image du hero
  // reste cachée derrière le voile du loader tant qu'il est affiché.
  setTimeout(() => loader && loader.classList.add('hidden'), 700);

  /* ---------- 2. YEAR ---------- */
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- 3. DEFILEMENT : 100% NATIF ---------- */
  // Lenis (defilement "smooth" en JS) a ete RETIRE le 01/09/2026.
  // Pourquoi : Lenis intercepte la molette et deplace la page lui-meme, image
  // par image, sur le THREAD PRINCIPAL. Des que ce thread est occupe (GSAP,
  // repeinture d'un flou, iframes YouTube/Instagram), la page ne bouge PLUS
  // DU TOUT tant qu'il n'est pas libre -> c'est exactement la "latence a la
  // molette" signalee. Le defilement natif, lui, est gere par le compositeur
  // (un autre thread) : il repond toujours, meme si le JS rame.
  // ScrollTrigger fonctionne nativement avec le scroll du navigateur.
  if (window.gsap && window.ScrollTrigger) {
    gsap.registerPlugin(ScrollTrigger);
    gsap.ticker.lagSmoothing(0);
  }

  /* ---------- 4. CUSTOM CURSOR ---------- */
  const cursor = document.getElementById('cursor');
  const cursorFollower = document.getElementById('cursorFollower');
  if (cursor && cursorFollower && window.matchMedia('(pointer: fine)').matches) {
    // On ecrit UNIQUEMENT des transform, et UNIQUEMENT dans la boucle rAF.
    // Avant : chaque mousemove ecrivait left/top -> recalcul de mise en page a
    // chaque micro-mouvement de souris, y compris pendant le defilement.
    let mouseX = -100, mouseY = -100;
    let followerX = -100, followerY = -100;
    document.addEventListener('mousemove', (e) => {
      mouseX = e.clientX; mouseY = e.clientY;
    }, { passive: true });
    function animateFollower() {
      cursor.style.transform = 'translate3d(' + mouseX + 'px,' + mouseY + 'px,0) translate(-50%,-50%)';
      followerX += (mouseX - followerX) * 0.15;
      followerY += (mouseY - followerY) * 0.15;
      cursorFollower.style.transform = 'translate3d(' + followerX.toFixed(1) + 'px,' + followerY.toFixed(1) + 'px,0) translate(-50%,-50%)';
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

  // Liens internes : plus AUCUN javascript (01/09/2026).
  // Le navigateur fait le travail tout seul, grace a deux lignes de CSS :
  //   html { scroll-behavior: smooth }   -> le defilement est doux
  //   html { scroll-padding-top: 90px }  -> la cible ne passe pas sous le menu
  // Avantages : ca marche meme si le JS plante ou n'est pas encore charge, et
  // c'est le compositeur du navigateur qui anime (pas le thread principal).

  /* ---------- 6. GSAP SCROLL ANIMATIONS ---------- */
  if (window.gsap && window.ScrollTrigger) {

    // Nav scrolled state
    // onUpdate part a CHAQUE frame de scroll : avant, on ecrivait dans le DOM
    // 60 fois par seconde pour rien. On ne touche a la classe que si l'etat
    // change reellement (01/09/2026).
    let navScrolled = null;
    ScrollTrigger.create({
      start: 'top -50',
      end: 99999,
      onUpdate: (self) => {
        const actif = self.scroll() > 50;
        if (actif !== navScrolled) {
          navScrolled = actif;
          nav.classList.toggle('scrolled', actif);
        }
      }
    });

    // Reveal generic animation
    // (les .section-title sont exclus : ils ont leur propre entrée 3D plus bas,
    //  et un double tween laisserait un transform inline qui bloque le survol)
    gsap.utils.toArray('[data-reveal]').filter(el => !el.classList.contains('section-title')).forEach((el, i) => {
      gsap.fromTo(el,
        { opacity: 0, y: 50 },
        {
          opacity: 1, y: 0,
          duration: 1.1,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: el,
            start: 'top bottom-=50',
            toggleActions: 'play none none none',
            once: true
          }
        }
      );
    });

    // Parallaxe du hero : RETIREE le 01/09/2026. Elle visait '.hero-name', une
    // classe qui n'existe dans AUCUNE page (GSAP le signalait dans la console).
    // Elle creait pour rien un ScrollTrigger en "scrub", donc un calcul a chaque
    // image de defilement.
    // (fix 22/07/2026 : l'ancien fondu parallaxe de .hero-tag/.hero-subtitle/
    //  .hero-actions au scroll est retiré — demande Quentin, la zone sous le
    //  logo doit rester visible et défiler naturellement.)

    // Stats counter — voir bloc plus bas (IntersectionObserver, plus robuste)

    // Parallaxe des blobs de fond : RETIREE le 01/09/2026.
    // Ces 3 tweens n'avaient AUCUN effet visible. .blob-1/2/3 portent deja une
    // animation CSS (@keyframes blobFloat1/2/3) qui anime transform, et une
    // animation CSS l'emporte sur un style inline dans la cascade. Verifie en
    // direct sur thejammerz.com : poser transform:translateY(-9999px) en inline
    // sur .blob-1 laisse le transform calcule a matrix(1,0,0,1,0,0).
    // C'etaient donc 3 ScrollTrigger en "scrub" recalcules a chaque frame de
    // scroll pour zero pixel de difference a l'ecran.

    // Section title : entrée 3D « claquée » depuis la profondeur.
    // SANS translation verticale (fix 22/07 : avec y:80 le titre traversait le
    // sous-titre pendant l'anim → superposition). Pivot en bas du titre pour
    // que rien ne déborde vers le bas. clearProps retire le transform inline
    // en fin d'anim pour laisser la bascule CSS :hover prendre le relais.
    gsap.utils.toArray('.section-title').forEach(title => {
      gsap.fromTo(title,
        { opacity: 0, scale: 0.92, rotateX: 60, transformPerspective: 900, transformOrigin: '50% 100%' },
        {
          opacity: 1, scale: 1, rotateX: 0,
          duration: 1.2,
          ease: 'expo.out',
          clearProps: 'transform',
          scrollTrigger: {
            trigger: title,
            start: 'top 80%',
            toggleActions: 'play none none none',
            once: true
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
          toggleActions: 'play none none none',
          once: true
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
          toggleActions: 'play none none none',
          once: true
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
            toggleActions: 'play none none none',
            once: true
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
     qu'il fonctionne meme si une lib externe (GSAP) casse ce bloc. */

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
   externe (GSAP) casse ce handler, le carrousel continue de marcher.
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

/* ====================================================================
   FX 3D — pack validé 2026-07-22 — IIFE AUTONOME
   Tilt 3D des cartes membres (+ reflet qui suit la souris) et pause
   hors écran du vinyle / de l'équalizer. Aucune dépendance (ni GSAP,
   ) : si une lib externe casse, ces effets tiennent seuls.
   Réversible : supprimer ce bloc + le bloc « 24. FX 3D » de styles.css
   + les 2 inserts HTML (vinyle répertoire, équalizer footer).
   ==================================================================== */
(function initFx3D() {
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function setup() {
    if (document.body.dataset.fx3dReady === '1') return;
    document.body.dataset.fx3dReady = '1';

    /* Vinyle + équalizer : n'animent que quand ils sont visibles */
    var runners = document.querySelectorAll('.vinyl-fx, .eq-footer');
    if ('IntersectionObserver' in window && runners.length) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          en.target.classList.toggle('fx-run', en.isIntersecting && !reduced);
        });
      });
      runners.forEach(function (el) { io.observe(el); });
    } else {
      runners.forEach(function (el) { if (!reduced) el.classList.add('fx-run'); });
    }

    /* Tilt 3D cartes membres — souris uniquement */
    if (reduced || !window.matchMedia('(pointer: fine)').matches) return;
    document.querySelectorAll('.member-card').forEach(function (card) {
      var glare = document.createElement('div');
      glare.className = 'card-glare';
      card.appendChild(glare);

      card.addEventListener('pointermove', function (e) {
        var r = card.getBoundingClientRect();
        var nx = (e.clientX - r.left) / r.width - 0.5;
        var ny = (e.clientY - r.top) / r.height - 0.5;
        card.classList.add('tilting');
        card.style.transform = 'translateY(-8px) rotateX(' + (ny * -9).toFixed(2) + 'deg) rotateY(' + (nx * 9).toFixed(2) + 'deg)';
        card.style.setProperty('--gx', ((nx + 0.5) * 100).toFixed(1) + '%');
        card.style.setProperty('--gy', ((ny + 0.5) * 100).toFixed(1) + '%');
      });
      card.addEventListener('pointerleave', function () {
        card.classList.remove('tilting');
        card.style.transform = '';
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();

/* ====================================================================
   AVIS GOOGLE EN ORBITE — autour de « Nos prochains lives »
   --------------------------------------------------------------------
   Les cartes tournent autour de la rubrique. Devant, elles passent en
   grand et bien lisibles ; derriere, elles s'effacent presque, comme si
   elles etaient plus loin.

   Trois promesses tenues ici :
   1. On peut TOUJOURS cliquer sur une date : la couche entiere est en
      pointer-events: none (voir styles.css).
   2. On finit par voir TOUS les avis : quand une carte disparait
      derriere, on lui donne l'avis suivant de la liste avant qu'elle ne
      revienne. La liste vient du bloc AVIS:AUTO, rempli chaque nuit
      depuis Google par scripts/update_avis.py.
   3. Ca ne coute rien a la molette : seuls transform et opacity bougent,
      et l'animation s'arrete des que la rubrique n'est plus a l'ecran.
   ==================================================================== */
(function () {
  'use strict';

  var VITESSE = 0.55;        // la vitesse « lente » validee sur la maquette 01
  var MAX_ORBITE = 6;        // cartes en vol en meme temps
  var SEUIL_ECHANGE = 0.08;  // en dessous, la carte est invisible : on l'echange
  var DUREE_MOBILE = 7000;   // ms entre deux avis sur telephone

  var ETOILE = '<svg viewBox="0 0 24 24" fill="#fbbc04" aria-hidden="true">' +
    '<path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8z"/></svg>';
  var LOGO_G = '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path fill="#4285f4" d="M23 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.2a5.3 5.3 0 01-2.3 3.5v2.9h3.7c2.2-2 3.4-5 3.4-8.6z"/>' +
    '<path fill="#34a853" d="M12 23.5c3.1 0 5.7-1 7.6-2.8l-3.7-2.9c-1 .7-2.3 1.1-3.9 1.1-3 0-5.5-2-6.4-4.7H1.8v3A11.5 11.5 0 0012 23.5z"/>' +
    '<path fill="#fbbc04" d="M5.6 14.2a6.9 6.9 0 010-4.4v-3H1.8a11.5 11.5 0 000 10.4z"/>' +
    '<path fill="#ea4335" d="M12 5.1c1.7 0 3.2.6 4.4 1.7l3.3-3.3A11.5 11.5 0 001.8 6.8l3.8 3a6.9 6.9 0 016.4-4.7z"/></svg>';

  function neuf(balise, classe) {
    var e = document.createElement(balise);
    if (classe) e.className = classe;
    return e;
  }

  /* Le squelette d'une carte. On le construit UNE fois puis on ne fait que
     changer les textes : rien n'est recree a chaque tour. Les textes viennent
     de clients Google, donc ils passent par textContent et jamais par
     innerHTML — un avis contenant un chevron ne peut rien casser. */
  function squelette() {
    var el = neuf('div', 'avis');
    var tete = neuf('div', 'avis-tete');
    var pastille = neuf('span', 'avis-pastille');
    var qui = neuf('span', 'avis-qui');
    var nom = neuf('span', 'avis-nom');
    var etoiles = neuf('span', 'avis-etoiles');
    etoiles.innerHTML = ETOILE + ETOILE + ETOILE + ETOILE + ETOILE;
    qui.appendChild(nom);
    qui.appendChild(etoiles);
    tete.appendChild(pastille);
    tete.appendChild(qui);

    var texte = neuf('p', 'avis-texte');

    var pied = neuf('p', 'avis-pied');
    var logo = neuf('span', 'avis-logo');
    logo.innerHTML = LOGO_G;
    var quoi = neuf('span');
    quoi.textContent = 'Avis Google';
    var quand = neuf('span', 'avis-quand');
    pied.appendChild(logo);
    pied.appendChild(quoi);
    pied.appendChild(quand);

    el.appendChild(tete);
    el.appendChild(texte);
    el.appendChild(pied);
    el._nom = nom;
    el._texte = texte;
    el._quand = quand;
    el._pastille = pastille;
    return el;
  }

  /* « il y a 3 mois ». Le fichier depose par le robot ne contient que la date
     brute (2026-05-14) : une phrase toute faite vieillirait dans la page et
     obligerait le robot a la reecrire chaque nuit pour rien. On la calcule
     donc ici, au moment d'afficher. Rien n'est invente : c'est la vraie date
     de l'avis, juste dite en francais. */
  function quandLisible(a) {
    if (a.quand) return a.quand;              /* ancien format, on respecte */
    if (!a.date) return '';
    var t = Date.parse(a.date);
    if (isNaN(t)) return '';
    var jours = Math.floor((Date.now() - t) / 86400000);
    if (jours < 0) return '';
    if (jours < 7) return "cette semaine";
    if (jours < 14) return "il y a une semaine";
    if (jours < 31) return "il y a " + Math.floor(jours / 7) + " semaines";
    var mois = Math.floor(jours / 30.4);
    if (mois < 2) return "il y a un mois";
    if (mois < 12) return "il y a " + mois + " mois";
    var ans = Math.floor(jours / 365.25);
    return ans < 2 ? "il y a un an" : "il y a " + ans + " ans";
  }

  function remplir(el, a) {
    el._nom.textContent = a.nom || '';
    el._texte.textContent = a.texte || '';
    el._quand.textContent = quandLisible(a);
    var p = el._pastille;
    p.textContent = '';
    p.style.background = 'hsl(' + (a.teinte || 0) + ' 52% 42%)';
    if (a.photo) {
      var img = new Image();
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      // Google renvoie parfois une photo qui refuse de s'afficher ailleurs que
      // chez lui : si elle tombe, on retombe sur l'initiale, jamais sur un trou.
      img.referrerPolicy = 'no-referrer';
      img.onerror = function () {
        // Une photo lente peut echouer APRES que la carte a change d'avis :
        // sans ce garde, on collait l'initiale de l'ancien a cote du nom du
        // nouveau — un vrai avis signe par la mauvaise personne.
        if (img.parentNode !== p) return;
        p.removeChild(img);
        p.textContent = a.ini || '?';
      };
      img.src = a.photo;
      p.appendChild(img);
    } else {
      p.textContent = a.ini || '?';
    }
  }

  /* La meme liste, immobile et complete, pour les lecteurs d'ecran : la couche
     animee, elle, leur est masquee. */
  function listeLecture(avis) {
    var ul = neuf('ul', 'avis-lecture');
    for (var i = 0; i < avis.length; i++) {
      var li = neuf('li');
      li.textContent = (avis[i].nom || 'Client') + ' — 5 sur 5 — ' +
                       (avis[i].texte || '') + ' — Avis Google';
      ul.appendChild(li);
    }
    return ul;
  }

  function setup() {
    var source = document.getElementById('avis-google');
    var couche = document.getElementById('avisOrbite');
    var defile = document.getElementById('avisDefile');
    var section = document.getElementById('agenda');
    if (!source || !couche || !defile || !section) return;

    var AVIS = [];
    try { AVIS = JSON.parse(source.textContent || '[]'); } catch (e) { AVIS = []; }
    if (!Array.isArray(AVIS)) AVIS = [];
    // Ceinture et bretelles : on ne montre que des avis qui ont vraiment un
    // texte. Sans avis, la rubrique reste exactement comme avant.
    AVIS = AVIS.filter(function (a) { return a && a.texte; });
    if (!AVIS.length) return;

    section.appendChild(listeLecture(AVIS));
    couche.setAttribute('aria-hidden', 'true');
    defile.setAttribute('aria-hidden', 'true');

    var doux = window.matchMedia &&
               window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var grand = window.matchMedia ? window.matchMedia('(min-width: 900px)') : null;

    // ---------------------------------------------------- version telephone
    var minuterie = null;
    var carteMobile = null;
    var iMobile = 0;

    function demarrerMobile() {
      if (carteMobile) return;
      carteMobile = squelette();
      remplir(carteMobile, AVIS[0]);
      carteMobile.style.opacity = '1';
      defile.appendChild(carteMobile);
      defile.classList.add('est-actif');
      if (doux || AVIS.length < 2) return;   // mouvement reduit : on en laisse un
      minuterie = window.setInterval(function () {
        carteMobile.style.opacity = '0';
        window.setTimeout(function () {
          if (!carteMobile) return;
          iMobile = (iMobile + 1) % AVIS.length;
          remplir(carteMobile, AVIS[iMobile]);
          carteMobile.style.opacity = '1';
        }, 450);
      }, DUREE_MOBILE);
    }

    function arreterMobile() {
      if (minuterie) { window.clearInterval(minuterie); minuterie = null; }
      if (carteMobile) { defile.removeChild(carteMobile); carteMobile = null; }
      defile.classList.remove('est-actif');
    }

    // ------------------------------------------------------ version orbite
    var cartes = [];
    var curseur = 0;
    var t = 0;
    var dernier = 0;
    var image = null;
    var visible = false;
    var L = 0, H = 0, cw = 246, ch = 180, oy = 0, ryMax = 210;

    /* Hauteur d'un bloc DANS la rubrique, en ignorant les animations.
       On additionne les offsetTop plutot que de lire un rectangle a l'ecran :
       a l'arrivee, les blocs montent en glissant (data-reveal). Un rectangle
       lu pendant ce glissement donne une place FAUSSE de quelques dizaines de
       pixels, et le cercle se posait donc un peu au hasard selon le moment de
       la mesure. offsetTop, lui, donne la place au repos. */
    function hautDansSection(el) {
      var y = 0;
      while (el && el !== section) {
        y += el.offsetTop;
        el = el.offsetParent;
      }
      return el === section ? y : -1;
    }

    /* Ou passe le cercle ?
       PAS au milieu de la rubrique. Ce milieu-la tombe sur le titre, et les
       cartes tournaient donc autour de « NOS PROCHAINS LIVES ». Quentin a
       demande le 03/09/2026 de DESCENDRE le cercle pour qu'il tourne autour
       des dates et de ce qu'il y a en dessous.
       On vise donc une bande qui commence en HAUT du bloc des dates et finit
       en BAS de la rubrique, puis on centre l'orbite dessus. La bande est
       MESUREE, jamais ecrite en dur : elle suit le nombre de dates affichees
       et la largeur de l'ecran. */
    function bande() {
      var haut = H * 0.45;
      var bloc = section.querySelector('.gigs-carousel');
      if (bloc) {
        var h = hautDansSection(bloc);
        if (h > 0 && h < H) haut = h;
      }
      return { haut: haut, bas: Math.max(haut + 1, H - 6) };
    }

    function mesurer() {
      var r = couche.getBoundingClientRect();
      L = r.width;
      H = r.height;
      if (cartes.length) {
        cw = cartes[0].offsetWidth || 246;
        /* 180 est le plancher : une carte peut grandir jusqu'a 4 lignes de
           texte APRES la mesure (elle change d'avis en tournant). On reserve
           la place du pire cas, sinon la carte la plus haute serait rognee. */
        ch = 180;
        for (var i = 0; i < cartes.length; i++) {
          if (cartes[i].offsetHeight > ch) ch = cartes[i].offsetHeight;
        }
      }
      /* Devant, une carte est a l'echelle 1 ; derriere, a 0.52 (voir « ech »
         dans dessiner). La place a reserver n'est donc pas la meme en haut
         qu'en bas : c'est ce qui fait descendre le centre encore un peu. */
      var b = bande();
      var hautChemin = b.haut + ch * 0.26;
      var basChemin = b.bas - ch * 0.5;
      if (basChemin < hautChemin) hautChemin = basChemin = (b.haut + b.bas) / 2;
      oy = (hautChemin + basChemin) / 2 - H / 2;
      ryMax = Math.max(60, (basChemin - hautChemin) / 2);
    }

    function construire() {
      if (cartes.length) return;
      var n = Math.min(MAX_ORBITE, AVIS.length);
      for (var i = 0; i < n; i++) {
        var el = squelette();
        remplir(el, AVIS[i]);
        el._p = 1;
        couche.appendChild(el);
        cartes.push(el);
      }
      curseur = n % AVIS.length;
      mesurer();
      dessiner();   // une premiere image tout de suite, sans attendre la boucle
    }

    function detruire() {
      if (image) { window.cancelAnimationFrame(image); image = null; }
      while (cartes.length) couche.removeChild(cartes.pop());
    }

    /* L'ellipse large et horizontale de la maquette 01. p = la profondeur :
       1 = tout devant, 0 = tout derriere. */
    function dessiner() {
      var n = cartes.length;
      if (!n || !L) return;
      /* 0.52 = la demi-largeur d'une carte (0.5) plus un cheveu de marge : le
         cercle est assez etroit pour qu'aucune carte ne sorte du cadre. Avant
         c'etait 0.38, et sur un ecran de 1024 la carte de gauche etait coupee
         net par le bord. */
      var rx = Math.min(L * 0.42, 620, Math.max(70, L / 2 - cw * 0.52));
      /* ryMax et oy viennent de mesurer() : ils garantissent qu'aucune carte
         ne depasse de la rubrique, en haut comme en bas. Le 300 n'est la que
         pour eviter un cercle demesure sur un tres grand ecran. */
      var ry = Math.min(ryMax, 300);
      for (var i = 0; i < n; i++) {
        var el = cartes[i];
        var a = t * 0.34 + i * (Math.PI * 2 / n);
        var p = (Math.cos(a) + 1) / 2;
        var x = Math.sin(a) * rx;
        var y = Math.cos(a) * ry + oy;

        // C'est ici qu'on tient la promesse « on voit TOUS les avis » : la
        // carte vient de passer sous le seuil d'invisibilite, donc personne ne
        // la regarde -> on lui glisse l'avis suivant avant qu'elle ne revienne.
        if (AVIS.length > n && el._p >= SEUIL_ECHANGE && p < SEUIL_ECHANGE) {
          remplir(el, AVIS[curseur]);
          curseur = (curseur + 1) % AVIS.length;
        }
        el._p = p;

        var ech = 0.52 + 0.48 * p;
        var op = 0.06 + 0.94 * Math.pow(p, 1.7);
        // Filet de securite : ce qui depasse du cadre s'efface au lieu d'etre
        // coupe net par le bord de la rubrique. A gauche/droite d'abord...
        var dehors = Math.abs(x) + (cw * ech) / 2 - L / 2;
        if (dehors > 0) op *= Math.max(0, 1 - dehors / (cw * 0.45));
        // ...et en haut/bas ensuite, depuis que le cercle est descendu : le
        // bord bas de la rubrique est maintenant tout pres du bas du cercle.
        var demiH = (ch * ech) / 2;
        var sortie = Math.max(0, (H / 2 + y) + demiH - H, demiH - (H / 2 + y));
        if (sortie > 0) op *= Math.max(0, 1 - sortie / (ch * 0.45));

        el.style.transform = 'translate(-50%,-50%) translate3d(' + x.toFixed(1) +
                             'px,' + y.toFixed(1) + 'px,0) scale(' + ech.toFixed(3) + ')';
        el.style.opacity = op.toFixed(3);
        // 3 = devant le contenu, 1 = derriere. Jamais au-dessus du menu (100).
        el.style.zIndex = p > 0.5 ? 3 : 1;
      }
    }

    function boucle(ms) {
      if (!visible) { image = null; return; }   // hors ecran : on ne calcule rien
      if (!dernier) dernier = ms;
      var dt = Math.min((ms - dernier) / 1000, 0.05);
      dernier = ms;
      t += dt * VITESSE;
      dessiner();
      image = window.requestAnimationFrame(boucle);
    }

    function relancer() {
      if (doux || image || !cartes.length) return;
      dernier = 0;
      image = window.requestAnimationFrame(boucle);
    }

    function demarrerOrbite() {
      construire();
      if (doux) { t = 1.2; dessiner(); return; }   // mouvement reduit : fige
      if (visible) relancer();
    }

    // ------------------------------------------------------- aiguillage
    function estGrand() { return grand ? grand.matches : window.innerWidth >= 900; }

    function appliquer() {
      if (estGrand()) {
        arreterMobile();
        demarrerOrbite();
      } else {
        detruire();
        demarrerMobile();
      }
    }

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entrees) {
        for (var i = 0; i < entrees.length; i++) visible = entrees[i].isIntersecting;
        if (visible) relancer();
      }, { rootMargin: '150px' }).observe(section);
    } else {
      visible = true;
    }

    var attente = null;
    function reagir() {
      if (attente) window.clearTimeout(attente);
      attente = window.setTimeout(function () { appliquer(); mesurer(); dessiner(); }, 200);
    }
    window.addEventListener('resize', reagir, { passive: true });
    // Un onglet ouvert en arriere-plan n'a aucune largeur au depart, et il ne
    // recoit PAS d'evenement resize le jour ou on l'affiche enfin : sans ce
    // guetteur la rubrique resterait bloquee sur la version telephone.
    if ('ResizeObserver' in window) new ResizeObserver(reagir).observe(section);

    // Un onglet qui revient de loin ne doit pas faire un bond de plusieurs tours.
    document.addEventListener('visibilitychange', function () { dernier = 0; });

    appliquer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();
