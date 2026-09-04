import { activateRoute } from './routes/registry.js';
document.documentElement.dataset.frontendArchitecture = 'typed-route-modules-v1';
document.addEventListener('questflow:route-ready', (event) => {
    const detail = event.detail;
    if (detail?.route)
        void activateRoute(detail.route);
});
const initial = document.querySelector('.page.is-active')?.dataset.page;
if (initial)
    void activateRoute(initial);
