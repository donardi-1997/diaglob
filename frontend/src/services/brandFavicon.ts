/**
 * Keep the favicon in sync with the app's manual light/dark switch.
 * Observing the root theme also covers public pages that toggle it directly.
 */
export function initializeBrandFavicon(): () => void {
  const icon = document.querySelector<HTMLLinkElement>('link[data-diaglob-favicon]');
  if (!icon) return () => undefined;

  const sync = () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    icon.href = isDark
      ? "/brand/diaglob-mark-dark.svg?v=coral-20261118"
      : "/brand/diaglob-mark.svg?v=coral-20261118";
  };

  sync();
  const observer = new MutationObserver(sync);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}
