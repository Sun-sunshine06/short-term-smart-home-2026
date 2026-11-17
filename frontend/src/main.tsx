// Keep old bookmarks working while exposing one canonical workbench URL.
const currentUrl = new URL(window.location.href);
if (currentUrl.searchParams.has('design')) {
  currentUrl.searchParams.delete('design');
  window.history.replaceState(null, '', currentUrl.pathname + currentUrl.search + currentUrl.hash);
}
void import('./astryx-entry');
