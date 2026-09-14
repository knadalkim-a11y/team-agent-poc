/* EES Work entry: keep the native SPA and its unsent chat intact underneath. */
(() => {
  'use strict';
  if (window.__eesWorkLauncher) return;
  window.__eesWorkLauncher = true;
  let dialog = null;
  let opener = null;
  let checking = false;
  const available = () => document.querySelector('#sidebar-new-chat-button') &&
    !location.pathname.startsWith('/auth');

  function close() {
    if (!dialog) return;
    dialog.close();
    dialog.remove();
    dialog = null;
    opener?.focus();
  }

  async function open(event) {
    if (checking || dialog || !available()) return;
    checking = true;
    opener = event.currentTarget;
    opener.disabled = true;
    try {
      // Only retrieve this fixed document using the existing login cookie.
      // No token is copied into the demo and no business API is invoked.
      const response = await fetch('/ees-work-demo/', {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('auth-or-unavailable');
      const html = await response.text();
      if (!html.includes('id="ees-demo-workspace"')) throw new Error('not-installed');
      if (!available()) return;
      dialog = document.createElement('dialog');
      dialog.id = 'ees-work-demo-dialog';
      dialog.setAttribute('aria-label', 'EES Work 시연');
      const header = document.createElement('header');
      const title = document.createElement('strong');
      title.textContent = 'EES Work 시연';
      const back = document.createElement('button');
      back.type = 'button';
      back.textContent = '기존 대화로 돌아가기';
      back.addEventListener('click', close);
      header.append(title, back);
      const frame = document.createElement('iframe');
      frame.title = 'EES Work · 시연용 목업';
      frame.src = '/ees-work-demo/';
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
      dialog.append(header, frame);
      dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
      document.body.append(dialog);
      dialog.showModal();
      back.focus();
    } catch (_) {
      window.alert('시연 화면을 열지 못했습니다. 로그인 상태와 EES Work 배포 여부를 확인해 주세요.');
    } finally {
      checking = false;
      if (opener) opener.disabled = false;
    }
  }

  function attach() {
    if (!available()) {close(); document.querySelector('#ees-work-demo-entry')?.remove(); return;}
    if (document.querySelector('#ees-work-demo-open')) return;
    // Upstream also has an always-hidden shortcut with the new-chat ID.
    // Attach a separate row only beside its native sidebar search row.
    const anchor = document.querySelector('#sidebar-search-button');
    if (!anchor) return;
    const button = document.createElement('button');
    button.id = 'ees-work-demo-open';
    button.type = 'button';
    button.textContent = 'EES Work 시연';
    button.title = '시연용 목업 · 실제 시스템 미연결';
    button.addEventListener('click', open);
    const row = document.createElement('div');
    row.id = 'ees-work-demo-entry';
    row.append(button);
    anchor.parentElement.insertAdjacentElement('afterend', row);
  }

  window.addEventListener('message', event => {
    if (event.origin === location.origin && dialog &&
        event.source === dialog.querySelector('iframe').contentWindow &&
        event.data?.type === 'ees-work-demo-close') close();
  });
  new MutationObserver(attach).observe(document.documentElement, {childList: true, subtree: true});
  attach();
})();
