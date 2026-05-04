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
  const lenis = new Lenis({
    duration: 1.1,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
    wheelMultiplier: 1,
    touchMultiplier: 2
  });
  function raf(time) {
    lenis.raf(time);
    requestAnimationFrame(raf);
  }
  requestAnimationFrame(raf);

  if (window.gsap && window.ScrollTrigger) {
    gsap.registerPlugin(ScrollTrigger);
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((time) => lenis.raf(time * 1000));
    gsap.ticker.lagSmoothing(0);
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

  // Smooth scroll via Lenis pour les liens internes
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (targetId === '#') return;
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        lenis.scrollTo(target, { offset: -80, duration: 1.4 });
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

    // Stats counter
    gsap.utils.toArray('.stat-num[data-count]').forEach(el => {
      const target = parseInt(el.dataset.count, 10);
      gsap.fromTo(el,
        { innerText: 0 },
        {
          innerText: target,
          duration: 2.2,
          ease: 'power2.out',
          snap: { innerText: 1 },
          scrollTrigger: {
            trigger: el,
            start: 'top 85%',
            toggleActions: 'play none none none'
          }
        }
      );
    });

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

    // Songs list reveal
    gsap.utils.toArray('.songs li').forEach((li, i) => {
      gsap.fromTo(li,
        { opacity: 0, x: -30 },
        {
          opacity: 1, x: 0,
          duration: 0.6,
          ease: 'power2.out',
          delay: i * 0.02,
          scrollTrigger: {
            trigger: li,
            start: 'top 92%',
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

  /* ---------- 7. REPERTOIRE TABS ---------- */
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('tab-active'));
      tab.classList.add('tab-active');
      document.querySelectorAll('[data-tab-content]').forEach(c => c.classList.remove('songs-active'));
      const content = document.querySelector(`[data-tab-content="${target}"]`);
      if (content) {
        content.classList.add('songs-active');
        if (window.gsap) {
          gsap.fromTo(content.querySelectorAll('li'),
            { opacity: 0, y: 20 },
            { opacity: 1, y: 0, duration: 0.5, stagger: 0.03, ease: 'power2.out' }
          );
        }
        if (window.ScrollTrigger) ScrollTrigger.refresh();
      }
    });
  });

  /* ---------- 8. VIDEO LAZY LOAD ---------- */
  document.querySelectorAll('.video-wrap[data-video]').forEach(wrap => {
    wrap.addEventListener('click', () => {
      const id = wrap.dataset.video;
      const iframe = document.createElement('iframe');
      iframe.src = `https://www.youtube.com/embed/${id}?autoplay=1&rel=0`;
      iframe.title = 'YouTube video player';
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
      iframe.allowFullscreen = true;
      wrap.innerHTML = '';
      wrap.appendChild(iframe);
    }, { once: true });
  });

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
