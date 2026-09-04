/* Development-only UX guard.
 *
 * QuestFlow users should not see React Native/Expo development chrome while studying.
 * Production/Preview builds do not render these overlays. In a Dev Client this guard
 * keeps Fast Refresh active but suppresses its visible "Refreshing..." banner and
 * closes the development menu if it was left open.
 */
declare const require: (id: string) => any;

type DevLoadingViewLike = {
  hide?: () => void;
  showMessage?: (...args: unknown[]) => void;
};

let patched = false;

export function suppressDevelopmentChrome(): void {
  if (!__DEV__ || patched) return;
  patched = true;

  try {
    const module = require('react-native/Libraries/Utilities/DevLoadingView');
    const devLoadingView: DevLoadingViewLike | undefined = module?.default || module;
    devLoadingView?.hide?.();
    if (devLoadingView) devLoadingView.showMessage = () => undefined;
  } catch {
    // Internal RN API is development-only; Preview/Production builds do not need it.
  }

  try {
    const devMenu = require('expo-dev-menu');
    devMenu?.hideMenu?.();
    devMenu?.closeMenu?.();
  } catch {
    // expo-dev-menu is absent from production bundles by design.
  }
}
