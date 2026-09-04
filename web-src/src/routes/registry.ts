import type { RouteId, RouteModule } from './types.js';

const legacy = () => import('./legacy.js');
const loaders: Record<RouteId, () => Promise<{ default: RouteModule }>> = {
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

let active: { id: RouteId; module: RouteModule } | null = null;

export async function activateRoute(route: string): Promise<void> {
  if (!(route in loaders)) return;
  const id = route as RouteId;
  const page = document.querySelector<HTMLElement>(`[data-page="${CSS.escape(id)}"]`);
  if (!page) return;
  if (active?.id !== id) await active?.module.unmount?.();
  const loaded = await loaders[id]();
  active = { id, module: loaded.default };
  await loaded.default.mount({ route: id, page });
}

