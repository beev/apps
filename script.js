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
