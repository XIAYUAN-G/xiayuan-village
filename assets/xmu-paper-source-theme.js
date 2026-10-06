(() => {
  const main = document.querySelector('main');
  if (!main) return;

  /* 直接打开源页面时也补上表格滚动容器；主导航页已有同名逻辑，这里会自动跳过已有容器。 */
  main.querySelectorAll('table').forEach(table => {
    if (table.closest('.table-wrap, .table-container, .info-table-wrap, .policy-table-wrap, .transport-table-wrap, .quota-table-wrap, .xmu-mobile-scroll-wrap')) return;
    const parent = table.parentElement;
    if (!parent) return;
    const wrap = document.createElement('div');
    wrap.className = 'xmu-mobile-scroll-wrap';
    parent.insertBefore(wrap, table);
    wrap.appendChild(table);
  });

  main.querySelectorAll('h2').forEach((heading, index) => {
    if (heading.closest('header, footer, dialog, .modal, .map-popup')) return;
    if (heading.querySelector('.xmu-paper-number, .paper-universal-index, .index, .section-no, .section-number, .section-index')) return;
    const number = document.createElement('span');
    number.className = 'xmu-paper-number';
    number.textContent = String(index + 1).padStart(2, '0');
    heading.prepend(number);
  });
})();
