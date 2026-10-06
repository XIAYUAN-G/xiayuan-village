(() => {
  const initPaperGuideStyle = () => {
    const main = document.querySelector('main');
    if (!main || document.body.classList.contains('paper-guide-page') || main.dataset.paperGuideUniversal === 'true') return;
    main.dataset.paperGuideUniversal = 'true';
    main.classList.add('paper-universal-main');

    const layoutOnly = node => node.matches('nav, .tabs, .toolbar, .quick, .filter-bar, .filter-controls, .tab-nav, .tab-links, .tabs-wrap, .toolbar-wrap, .recommendation-tab-panel');
    const sectionSelectors = 'section, article, aside, .section-card, .content-section, .guide-card, .paper-block, .panel, .tab-panel, .recommendation-tab-panel';
    const directSections = [...main.children].filter(node => {
      if (layoutOnly(node)) return false;
      return node.matches(sectionSelectors) || !!node.querySelector('h2');
    });
    const directSectionFor = heading => {
      let node = heading;
      while (node && node.parentElement !== main) node = node.parentElement;
      if (node && layoutOnly(node)) {
        const contentSection = heading.closest('section.paper-block, section.section-card, section.content-section, article, aside, .section-card, .content-section, .guide-card, .panel, .card');
        if (contentSection && contentSection !== main && !layoutOnly(contentSection)) return contentSection;
      }
      return node && node !== main ? node : heading.parentElement;
    };

    directSections.forEach(section => section.classList.add('paper-universal-section', 'xmu-paper-section'));

    let number = 0;
    [...main.querySelectorAll('h2')]
      .filter(heading => !heading.closest('header, footer, dialog, .modal, .map-popup'))
      .forEach(heading => {
        const section = directSectionFor(heading);
        if (section && section !== main && !layoutOnly(section)) section.classList.add('paper-universal-section', 'xmu-paper-section');
        heading.classList.add('paper-universal-heading', 'xmu-paper-heading');
        const siblingNumber = heading.parentElement?.querySelector(':scope > .section-no, :scope > .section-number, :scope > .section-index');
        if (siblingNumber) heading.querySelectorAll('.paper-universal-index, .xmu-paper-number').forEach(node => node.remove());
        const existingNumber = heading.querySelector('.paper-universal-index, .xmu-paper-number, .index, .section-no, .section-number, .section-index') || siblingNumber;
        if (!existingNumber) {
          const index = document.createElement('span');
          index.className = 'paper-universal-index xmu-paper-number';
          index.textContent = String(++number).padStart(2, '0');
          heading.prepend(index);
        }
      });

    const boxSelectors = 'article, .card, .panel, .info-card, .guide-card, .notice, .tip, .callout, .alert, .content-card, .entry-card, .facility, .guide-item, .resource-card, .paper-block';
    main.querySelectorAll(boxSelectors).forEach(box => {
      if (box.classList.contains('paper-universal-section') || box.closest('header, footer, dialog, .modal')) return;
      box.classList.add('paper-universal-box');
      if (box.matches('.notice, .tip, .callout, .alert')) box.classList.add('paper-universal-note');
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPaperGuideStyle, { once: true });
  else initPaperGuideStyle();
})();
