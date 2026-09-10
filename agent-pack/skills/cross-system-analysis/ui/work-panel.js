/* Fixed bootstrap shared by the existing analysis and WO Tools. It coordinates
 * one launcher and registered screens; business state remains in each Tool. */
(function () {
  if (window.__eesWorkPanelV1) return;
  const chats = new Map(), legacyLaunchers = new Map(), route = id => '/c/' + encodeURIComponent(id);
  let active = null, disposed = false, restoring = false;
  const layout = () => {
    const anchor = document.querySelector('#chat-container #chat-pane'), column = anchor?.parentElement, row = column?.parentElement;
    const controls = column?.querySelector('nav button[aria-label="Controls"]'), wrapper = controls?.parentElement;
    const toolbar = wrapper?.parentElement || column?.querySelector('nav .flex-none.items-center.gap-2.self-center');
    return row?.isConnected && toolbar?.isConnected && getComputedStyle(row).display === 'flex' ? {column, toolbar, wrapper} : null;
  };
  const create = chatId => {
    const slot = document.createElement('div'); slot.className = 'flex';
    const launcher = document.createElement('button'); launcher.id = 'ees-work-panel-toggle'; launcher.type = 'button';
    launcher.className = 'flex size-6 cursor-pointer items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-50/40 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800/40 dark:hover:text-gray-200';
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    Object.entries({viewBox: '0 0 24 24', width: '20', height: '20', fill: 'none', stroke: 'currentColor', 'stroke-width': '1', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'}).forEach(([key, value]) => icon.setAttribute(key, value));
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', 'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm10 0v18'); icon.append(path); launcher.append(icon); slot.append(launcher);
    const chat = {chatId, screens: new Map(), selected: null, opened: false, launcher, slot};
    launcher.addEventListener('click', () => chat.opened ? close(chatId) : select(chatId, chat.selected, {open: true}));
    return chat;
  };
  const notify = chat => {
    const info = {selected: chat.selected, open: chat.opened, available: Array.from(chat.screens.keys())};
    chat.screens.forEach(screen => screen.onChange?.(info));
    const title = chat.opened ? '업무 패널 닫기' : '업무 패널 열기';
    chat.launcher.title = title; chat.launcher.setAttribute('aria-label', title); chat.launcher.setAttribute('aria-expanded', String(chat.opened));
    chat.launcher.setAttribute('aria-controls', chat.screens.get(chat.selected)?.hostId || ''); chat.launcher.style.backgroundColor = chat.opened ? '#8882' : '';
  };
  const restore = chatId => {
    const chat = chats.get(chatId);
    if (!chat || restoring || disposed || location.pathname !== route(chatId)) return false;
    restoring = true;
    try {
      // WO and equipment share one host. Close nonselected screens BEFORE the
      // selected screen is opened, so closing a sibling cannot hide it again.
      chat.screens.forEach((screen, key) => { if ((!chat.opened || key !== chat.selected) && screen.isOpen()) screen.close(); });
      const screen = chat.screens.get(chat.selected);
      if (chat.opened && screen && !screen.isOpen()) screen.open();
      if (!chat.opened && chat.column) chat.column.style.minWidth = chat.originalMinWidth;
      notify(chat); return true;
    } finally { restoring = false; }
  };
  const select = (chatId, key, options = {}) => {
    const chat = chats.get(chatId);
    if (!chat || !chat.screens.has(key) || location.pathname !== route(chatId)) return false;
    chat.selected = key; chat.opened = options.open !== false; restore(chatId); sync();
    if (chat.opened && options.focus !== false) chat.screens.get(key).focus?.();
    return true;
  };
  const close = chatId => {
    const chat = chats.get(chatId); if (!chat || location.pathname !== route(chatId)) return false;
    chat.opened = false; restore(chatId); return true;
  };
  const sync = () => {
    if (disposed) return;
    if (/^\/(auth|logout)(\/|$)/.test(location.pathname)) { destroy(); return; }
    const next = Array.from(chats.values()).find(chat => location.pathname === route(chat.chatId)) || null;
    if (active && active !== next) { active.slot.remove(); if (active.column) active.column.style.minWidth = active.originalMinWidth; }
    active = next; const nextLayout = next ? layout() : null;
    if (!nextLayout) { next?.slot.remove(); return; }
    if (next.column !== nextLayout.column) { next.column = nextLayout.column; next.originalMinWidth = next.column.style.minWidth; }
    // Existing tabs may still contain a cached older Tool until a full refresh.
    // Hide its duplicate launcher without detaching its draft controller.
    ['ees-work-panel-toggle', 'ees-cooperation-toggle'].forEach(id => {
      const button = document.getElementById(id);
      if (button && !Array.from(chats.values()).some(chat => chat.launcher === button)) {
        if (!legacyLaunchers.has(button)) legacyLaunchers.set(button, {id: button.id, display: button.style.display});
        button.id = id + '-legacy'; button.style.display = 'none';
      }
    });
    if (next.slot.parentElement !== nextLayout.toolbar) nextLayout.toolbar.insertBefore(next.slot, nextLayout.wrapper || null);
    restore(next.chatId);
  };
  const register = (chatId, screen) => {
    if (disposed || typeof chatId !== 'string' || !['analysis', 'equipment', 'wo'].includes(screen?.key)
        || !['open', 'close', 'isOpen'].every(key => typeof screen[key] === 'function')) return false;
    let chat = chats.get(chatId); if (!chat) { chat = create(chatId); chats.set(chatId, chat); }
    chat.screens.set(screen.key, screen); if (!chat.selected) chat.selected = screen.key;
    // Registration never opens a screen. The first real Tool request selects
    // its screen; later restore calls keep the user's closed preference.
    notify(chat); return true;
  };
  const unregister = (chatId, key) => {
    const chat = chats.get(chatId); if (!chat) return;
    chat.screens.delete(key);
    if (chat.selected === key) { chat.selected = chat.screens.keys().next().value || null; chat.opened = false; }
    if (!chat.screens.size) { chat.slot.remove(); chats.delete(chatId); }
    else notify(chat);
    sync();
  };
  const observer = new MutationObserver(sync), navigation = window.navigation;
  const destroy = () => {
    if (disposed) return; disposed = true; observer.disconnect();
    window.removeEventListener('popstate', sync); window.removeEventListener('pagehide', destroy); navigation?.removeEventListener('navigatesuccess', sync);
    chats.forEach(chat => { chat.slot.remove(); if (chat.column) chat.column.style.minWidth = chat.originalMinWidth; }); chats.clear();
    legacyLaunchers.forEach((previous, button) => { button.id = previous.id; button.style.display = previous.display; }); legacyLaunchers.clear();
    active = null; delete window.__eesWorkPanelV1;
  };
  window.__eesWorkPanelV1 = {register, select, close, restore, sync, unregister, destroy,
    available: (chatId, key) => Boolean(chats.get(chatId)?.screens.has(key)), selected: chatId => chats.get(chatId)?.selected || null,
    isOpen: chatId => Boolean(chats.get(chatId)?.opened), focus: chatId => chats.get(chatId)?.launcher.focus({preventScroll: true})};
  observer.observe(document.body, {childList: true, subtree: true}); window.addEventListener('popstate', sync); window.addEventListener('pagehide', destroy); navigation?.addEventListener('navigatesuccess', sync);
})();
