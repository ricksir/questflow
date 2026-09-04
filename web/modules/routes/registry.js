const legacy = () => import('./legacy.js');
const loaders = {
    dashboard: legacy,
    visualanalytics: legacy,
    examproject: legacy,
    import: legacy,
    curation: legacy,
    review: legacy,
    bankfix: legacy,
    tutor: legacy,
    recommend: legacy,
    stage5: legacy,
    corrections: legacy,
    coverage: legacy,
    flow: legacy,
    mobile: legacy,
    settings: () => import('./settings.js'),
};
let active = null;
export async function activateRoute(route) {
    if (!(route in loaders))
        return;
    const id = route;
    const page = document.querySelector(`[data-page="${CSS.escape(id)}"]`);
    if (!page)
        return;
    if (active?.id !== id)
        await active?.module.unmount?.();
    const loaded = await loaders[id]();
    active = { id, module: loaded.default };
    await loaded.default.mount({ route: id, page });
}
