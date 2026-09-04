import { activateRoute } from './routes/registry.js';

document.documentElement.dataset.frontendArchitecture = 'typed-route-modules-v1';

document.addEventListener('questflow:route-ready', (event) => {
  const detail = (event as CustomEvent<{ route?: string }>).detail;
  if (detail?.route) void activateRoute(detail.route);
});

const initial = document.querySelector<HTMLElement>('.page.is-active')?.dataset.page;
if (initial) void activateRoute(initial);

