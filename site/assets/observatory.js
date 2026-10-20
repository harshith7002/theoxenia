/* Show stale processing honestly; offer a refresh when a newer build exists. */
(() => {
  const freshness = document.getElementById('observatory-freshness');
  const refresh = document.getElementById('observatory-refresh');
  if (!freshness || !refresh) return;
  const original = freshness.textContent;
  let initialBuild;
  async function check() {
    const age = Date.now() - Date.parse(freshness.dataset.checked);
    freshness.textContent = original + (age > 8 * 3600000 ? ' No recent processing check; see processing history.' : '');
    if (document.hidden) return;
    try {
      const response = await fetch('build.json', {cache: 'no-store'});
      if (!response.ok) return;
      const build = await response.json();
      const identity = build.git_sha + ':' + build.generated_at;
      if (initialBuild && identity !== initialBuild) refresh.hidden = false;
      initialBuild = initialBuild || identity;
    } catch (_) { /* Keep the last verified evidence visible offline. */ }
  }
  check();
  setInterval(check, 120000);
})();
