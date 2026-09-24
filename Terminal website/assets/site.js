/* Every page: the header's hairline appears once the page has moved, so at the
   top the header sits on the page instead of drawing a line across it. */
(function () {
  'use strict';
  var top = document.querySelector('.top');
  if (!top) return;
  function edge() { top.classList.toggle('edge', window.scrollY > 4); }
  edge();
  window.addEventListener('scroll', edge, { passive: true });
})();
