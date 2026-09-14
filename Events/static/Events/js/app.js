(function () {
  'use strict';

  /* Live check-in count refreshing */
  function bindLiveCounts() {
    document.querySelectorAll('[data-event-slug]').forEach(function (el) {
      var slug = el.dataset.eventSlug;
      var target = el.querySelector('[data-live-count]');
      var refresh = function () {
        fetch('/events/' + encodeURIComponent(slug) + '/count.json')
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (target) target.textContent = data.checked_in;
          })
          .catch(function () {});
      };
      refresh();
      setInterval(refresh, 15000);
    });
  }

  /* Copy share links */
  function bindCopyButtons() {
    document.querySelectorAll('[data-copy-source]').forEach(function (group) {
      var valueEl = group.querySelector('[data-copy-value]');
      var button = group.querySelector('[data-copy-button]');
      if (!valueEl || !button) return;
      button.addEventListener('click', function () {
        valueEl.select();
        navigator.clipboard
          .writeText(valueEl.value)
          .then(function () {
            button.innerHTML = '<svg class="icon"><use href="#i-check"/></svg> Copied';
            setTimeout(function () {
              button.innerHTML =
                '<svg class="icon"><use href="#i-copy"/></svg> Copy';
            }, 1500);
          })
          .catch(function () {});
      });
    });
  }

  /* Live branding preview for the event editor */
  function bindColorPreview() {
    var swatch = document.querySelector('[data-gradient-swatch]');
    if (!swatch) return;
    var initial = getComputedStyle(swatch).backgroundImage;
    var inputs = document.querySelectorAll(
      '[data-color-preview] input[type="text"]'
    );
    inputs.forEach(function (input) {
      input.addEventListener('input', function () {
        var gradiendFrom =
          document.querySelector('[name="gradient_from"]').value || '#6366f1';
        var gradientTo =
          document.querySelector('[name="gradient_to"]').value || '#0f172a';
        swatch.style.background =
          'linear-gradient(135deg, ' + gradiendFrom + ', ' + gradientTo + ')';
      });
    });
  }

  /* Reveal the free-text institution field when "Other" is picked */
  function bindInstitutionOther() {
    var select = document.querySelector('[data-institution-select]');
    var otherInput = document.querySelector('[data-institution-other]');
    if (!select || !otherInput) return;
    var wrap = otherInput.closest('.field');
    var sync = function () {
      var show = select.value === '__other__';
      if (wrap) wrap.style.display = show ? '' : 'none';
      if (otherInput.required) otherInput.required = show;
    };
    select.addEventListener('change', sync);
    sync();
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindLiveCounts();
    bindCopyButtons();
    bindColorPreview();
    bindInstitutionOther();
  });
})();