// Email links: decode ROT13 addresses stored in data attributes
(function () {
  function rot13(s) {
    return s.replace(/[a-z]/gi, function (c) {
      var base = c <= 'Z' ? 65 : 97;
      return String.fromCharCode(((c.charCodeAt(0) - base + 13) % 26) + base);
    });
  }
  document.querySelectorAll('.js-email').forEach(function (el) {
    el.href = 'mailto:' + rot13(el.dataset.u) + '@' + rot13(el.dataset.d);
  });
}());

// Sticky header: add border/shadow once user scrolls past the top
const header = document.getElementById('site-header');
if (header) {
  window.addEventListener('scroll', () => {
    header.classList.toggle('header--scrolled', window.scrollY > 10);
  }, { passive: true });
}

// Device switcher: segmented control above each mockup
document.querySelectorAll('.device-switcher').forEach(switcher => {
  switcher.querySelectorAll('.device-switcher__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const display = switcher.closest('.device-display');
      const device = btn.dataset.device;

      switcher.querySelectorAll('.device-switcher__btn').forEach(b => {
        b.classList.remove('is-active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('is-active');
      btn.setAttribute('aria-pressed', 'true');

      display.querySelectorAll('.device-view').forEach(view => {
        view.hidden = !view.classList.contains(`device-view--${device}`);
      });
    });
  });
});

// Guide sidebar: permanent from the tablet width up, collapsible below it.
// The markup ships open so that with JavaScript off the nav is always
// visible — a closed <details> would hide it with no way to reopen.
const guideNav = document.querySelector('.guide-nav');
if (guideNav) {
  const narrow = window.matchMedia('(max-width: 899px)');
  const sync = () => { guideNav.open = !narrow.matches; };
  sync();
  narrow.addEventListener('change', sync);
}

// Guide maps: click to load. The Google embed sets a cookie, so nothing is
// requested from Google until the reader presses the button — which is why
// the site needs no consent banner. Pressing the button is the consent.
document.querySelectorAll('.guide-map__consent').forEach(box => {
  const btn = box.querySelector('.guide-map__load');
  if (!btn) return;
  btn.addEventListener('click', () => {
    // Maps JavaScript API form: its `satellite` map type is imagery with no
    // road-name labels, which the iframe embed cannot produce.
    if (box.dataset.mapLat) {
      loadMapsApi(box.dataset.mapKey).then(() => {
        const el = document.createElement('div');
        el.className = 'guide-map__canvas';
        el.setAttribute('role', 'img');
        el.setAttribute('aria-label', box.dataset.mapTitle || 'Map');
        box.replaceWith(el);
        new google.maps.Map(el, {
          center: { lat: +box.dataset.mapLat, lng: +box.dataset.mapLng },
          zoom: +box.dataset.mapZoom,
          mapTypeId: 'satellite',
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true
        });
      }).catch(() => {
        btn.textContent = 'Map could not be loaded';
        btn.disabled = true;
      });
      return;
    }

    const frame = document.createElement('iframe');
    frame.src = box.dataset.mapSrc;
    frame.title = box.dataset.mapTitle || 'Map';
    frame.loading = 'lazy';
    frame.referrerPolicy = 'no-referrer-when-downgrade';
    frame.allowFullscreen = true;
    box.replaceWith(frame);
    frame.focus({ preventScroll: true });
  });
});

// Loads the Maps JavaScript API once, however many maps are on the page.
function loadMapsApi(key) {
  if (window.__mapsApiPromise) return window.__mapsApiPromise;
  window.__mapsApiPromise = new Promise((resolve, reject) => {
    window.__mapsApiReady = resolve;
    const s = document.createElement('script');
    s.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(key) +
            '&v=weekly&loading=async&callback=__mapsApiReady';
    s.async = true;
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return window.__mapsApiPromise;
}
