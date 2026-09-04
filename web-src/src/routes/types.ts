export type RouteId =
  | 'dashboard' | 'visualanalytics' | 'examproject' | 'import' | 'curation'
  | 'review' | 'bankfix' | 'tutor' | 'recommend' | 'stage5' | 'corrections'
  | 'coverage' | 'flow' | 'mobile' | 'settings';

export type RouteModule = {
  mount(context: { route: RouteId; page: HTMLElement }): void | Promise<void>;
  unmount?(): void | Promise<void>;
};

