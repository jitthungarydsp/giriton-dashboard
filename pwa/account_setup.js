/* The reset secret is a URL fragment: it is never sent in a GET URL or referrer. */
(() => {
  const match = /^#set-password=([A-Za-z0-9_-]{43})$/.exec(location.hash);
  if (!match) return;
  window.PWA_ACCOUNT_SETUP = true;
  let token = match[1];
  history.replaceState(null, '', location.pathname + location.search);
  const view = document.querySelector('#login-view');
  view.classList.remove('hidden');
  view.querySelectorAll('form, .auth-links').forEach(el => el.classList.add('hidden'));
  const heading = view.querySelector('h1');
  heading.textContent = 'Jelszó beállítása';
  view.querySelector('.muted').textContent = 'Adj meg legalább 12 karakteres új jelszót. A link egyszer használható, és 30 percig érvényes.';
  const form = document.createElement('form');
  form.innerHTML = `<label>Új jelszó<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
    <label>Új jelszó még egyszer<input type="password" name="repeat" autocomplete="new-password" minlength="12" maxlength="128" required></label>
    <p role="status" aria-live="polite"></p><button class="primary" type="submit">Jelszó mentése</button>
    <a class="secondary" href="/">Vissza a belépéshez</a>`;
  view.querySelector('.login-card').append(form);
  let submitting = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    const message = form.querySelector('[role=status]');
    const button = form.querySelector('button');
    const password = form.elements.password.value;
    if (password !== form.elements.repeat.value) { message.textContent = 'A két jelszó nem egyezik.'; return; }
    submitting = true; button.disabled = true; message.textContent = 'Mentés…';
    try {
      const response = await fetch('/api/password-reset/complete', {method: 'POST', cache: 'no-store',
        credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token, password})});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'A jelszó mentése nem sikerült.');
      token = ''; form.reset(); message.textContent = result.message;
      form.querySelectorAll('input').forEach(input => input.disabled = true);
      button.hidden = true;
    } catch (error) {
      message.textContent = error.message + ' Ha a mentés eredménye bizonytalan, próbálj belépni az új jelszóval.';
      button.disabled = false;
    } finally { submitting = false; }
  });
})();
