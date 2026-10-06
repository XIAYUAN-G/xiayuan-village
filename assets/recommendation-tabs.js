(() => {
  const pageToTab = {
    '保研01-什么是保研.html': 'overview',
    '保研02-校内推免资格.html': 'eligibility',
    '保研03-校外推免资格.html': 'admission',
    '保研04-推免系统确认.html': 'system'
  };
  const params = new URLSearchParams(window.location.search);

  if (params.has('embed')) {
    const panel = params.get('panel') || pageToTab[location.pathname.split('/').pop()];
    const reportHeight = () => {
      const root = document.documentElement;
      const body = document.body;
      const height = Math.ceil(Math.max(root.scrollHeight, root.offsetHeight, body.scrollHeight, body.offsetHeight));
      window.parent.postMessage({ type: 'recommendation-panel-height', panel, height }, '*');
    };
    document.addEventListener('click', event => {
      const link = event.target.closest('a[href]');
      if (!link) return;
      const target = pageToTab[new URL(link.href, location.href).pathname.split('/').pop()];
      if (!target) return;
      event.preventDefault();
      window.parent.postMessage({ type: 'recommendation-select-panel', panel: target }, '*');
    });
    window.addEventListener('load', reportHeight);
    window.addEventListener('resize', reportHeight);
    if ('ResizeObserver' in window && document.body) new ResizeObserver(reportHeight).observe(document.body);
    requestAnimationFrame(reportHeight);
    return;
  }

  const host = document.querySelector('[data-recommendation-host]');
  if (!host) return;
  const tabNav = document.querySelector('.page-nav[role="tablist"]');
  const buttons = tabNav ? [...tabNav.querySelectorAll('[data-tab]')] : [];
  const panels = [...host.querySelectorAll('[data-panel]')];
  const panelByName = name => host.querySelector(`[data-panel="${name}"]`);
  const resizeFrame = frame => {
    try {
      const doc = frame.contentDocument;
      if (!doc) return;
      const root = doc.documentElement;
      const body = doc.body;
      frame.style.height = `${Math.ceil(Math.max(root.scrollHeight, root.offsetHeight, body.scrollHeight, body.offsetHeight))}px`;
    } catch (_) {
      /* The content will report its own height when it is available. */
    }
  };
  const selectPanel = name => {
    const panel = panelByName(name);
    if (!panel) return;
    buttons.forEach(button => {
      const active = button.dataset.tab === name;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
    });
    panels.forEach(item => {
      const active = item === panel;
      item.classList.toggle('is-active', active);
      item.hidden = !active;
    });
    const frame = panel.querySelector('.recommendation-tab-frame');
    if (frame) {
      resizeFrame(frame);
      requestAnimationFrame(() => resizeFrame(frame));
    }
  };

  buttons.forEach(button => button.addEventListener('click', () => selectPanel(button.dataset.tab)));
  host.querySelectorAll('.recommendation-tab-frame').forEach(frame => frame.addEventListener('load', () => resizeFrame(frame)));
  window.addEventListener('message', event => {
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'recommendation-select-panel') selectPanel(data.panel);
    if (data.type === 'recommendation-panel-height') {
      const frame = panelByName(data.panel)?.querySelector('.recommendation-tab-frame');
      if (frame && Number.isFinite(data.height)) frame.style.height = `${Math.max(1, Math.ceil(data.height))}px`;
    }
  });
  selectPanel(params.get('tab') && panelByName(params.get('tab')) ? params.get('tab') : (buttons.find(button => button.classList.contains('is-active'))?.dataset.tab || buttons[0]?.dataset.tab));
})();
