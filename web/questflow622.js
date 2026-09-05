(() => {
  'use strict';
  const RELEASE = '6.24.0';
  const MOBILE_RELEASE = '0.16.0';

  function applyRelease() {
    document.body.dataset.questflowRelease = RELEASE;
    document.documentElement.dataset.visualSystem = 'editorial-bento';
    document.querySelectorAll('.brand-copy small').forEach((node) => {
      if (/6\.21\./.test(node.textContent || '')) node.textContent = `Versão ${RELEASE}`;
    });
    document.querySelectorAll('.mobile-studio-kicker').forEach((node) => { node.textContent = `MOBILE ${MOBILE_RELEASE}`; });
    document.querySelectorAll('[data-mobile-source-version]').forEach((node) => { node.textContent = MOBILE_RELEASE; });
    document.querySelectorAll('.page[data-page="mobile"] h2, .page[data-page="mobile"] p').forEach((node) => {
      if (/0\.(?:14|15)\.\d+/.test(node.textContent || '')) node.textContent = node.textContent.replaceAll(/0\.(?:14|15)\.\d+/g, MOBILE_RELEASE);
    });
    document.querySelectorAll('.page[data-page]').forEach((page) => {
      page.dataset.visualSystem = 'qf622';
      const heading = page.querySelector(':scope > .page-header h1, :scope > .dashboard-hero h1');
      if (heading && !heading.dataset.qf622Title) {
        heading.dataset.qf622Title = 'true';
        heading.setAttribute('data-route-label', page.dataset.page || '');
      }
    });
  }

  function onRoute() {
    requestAnimationFrame(applyRelease);
  }

  document.addEventListener('questflow:route-ready', onRoute);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', applyRelease, { once: true });
  else applyRelease();
})();
