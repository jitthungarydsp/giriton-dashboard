(() => {
  let mounted = false;
  let busy = false;
  let configured = false;
  let availableAt = 0;
  let root, api, button, message, dialog;

  function updateButton() {
    const remaining = Math.max(0, Math.ceil((availableAt - Date.now()) / 1000));
    button.disabled = busy || !configured || remaining > 0;
    button.textContent = busy ? "Hívás indítása…" : remaining ? `Új kapunyitás ${remaining} mp múlva` : "Kapunyitás indítása";
  }

  function showResult(text, success) {
    dialog.querySelector("[data-gate-spinner]").hidden = true;
    dialog.querySelector("h3").textContent = success ? "Híváskérés elküldve" : "A hívás nem igazolható vissza";
    dialog.querySelector("p").textContent = text;
    dialog.querySelector("button").hidden = false;
    dialog.setAttribute("aria-busy", "false");
  }

  async function submit() {
    if (button.disabled || busy) return;
    busy = true;
    updateButton();
    dialog.querySelector("h3").textContent = "Kapunyitó hívás indítása…";
    dialog.querySelector("p").textContent = "Kérjük, várj a visszaigazolásra.";
    dialog.querySelector("[data-gate-spinner]").hidden = false;
    dialog.querySelector("button").hidden = true;
    dialog.setAttribute("aria-busy", "true");
    dialog.showModal();
    // No automatic retry: the server may have accepted a call even if the connection drops.
    const requestId = crypto.randomUUID();
    availableAt = Date.now() + 60000;
    try {
      const result = await api("/api/admin/gate/open", {
        method: "POST", body: JSON.stringify({ request_id: requestId }), silentLoading: true,
      });
      if (!result.ok || !result.callSid) throw new Error("Hiányos szerverválasz. Ellenőrizd a Twilio hívásnaplót.");
      availableAt = Date.now() + (result.cooldownSeconds || 60) * 1000;
      const text = "A Twilio fogadta a kapunyitó híváskérést. A kapu tényleges kinyílását kérjük, ellenőrizd a helyszínen.";
      message.textContent = text;
      message.className = "gate-feedback success";
      showResult(text, true);
    } catch (error) {
      const text = `${error.message || "A hívás indítását nem sikerült visszaigazolni."} Új hívás előtt ellenőrizd a Twilio hívásnaplót.`;
      message.textContent = text;
      message.className = "gate-feedback error";
      showResult(text, false);
    } finally {
      busy = false;
      updateButton();
    }
  }

  async function mount(container, dependencies) {
    root = container;
    api = dependencies.api;
    if (!mounted) {
      mounted = true;
      root.innerHTML = `<section class="gate-panel">
        <small class="eyebrow">ADMIN</small><h2>Kapunyitás</h2>
        <p class="muted">A gomb megnyomásával telefonhívást indítasz a kapunyitóhoz.</p>
        <button type="button" class="primary" data-gate-open disabled>Beállítások ellenőrzése…</button>
        <p class="gate-feedback" data-gate-message role="status" aria-live="polite"></p>
        <button type="button" class="secondary" data-gate-refresh>Beállítások ellenőrzése</button>
      </section>`;
      button = root.querySelector("[data-gate-open]");
      message = root.querySelector("[data-gate-message]");
      dialog = document.createElement("dialog");
      dialog.className = "gate-dialog";
      dialog.setAttribute("aria-labelledby", "gate-dialog-title");
      dialog.innerHTML = `<div class="global-loading-card"><span data-gate-spinner class="global-loading-spinner" aria-hidden="true"></span><h3 id="gate-dialog-title"></h3><p></p><button class="primary" type="button">Rendben</button></div>`;
      document.body.append(dialog);
      dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
      dialog.querySelector("button").addEventListener("click", () => { if (!busy) dialog.close(); });
      button.addEventListener("click", submit);
      root.querySelector("[data-gate-refresh]").addEventListener("click", refresh);
      setInterval(() => { if (!root.classList.contains("hidden")) updateButton(); }, 1000);
    }
    if (!busy) await refresh();
  }

  async function refresh() {
    if (busy) return;
    configured = false;
    updateButton();
    try {
      const config = await api("/api/admin/gate", { silentLoading: true });
      configured = Boolean(config.configured);
      availableAt = Math.max(availableAt, Date.now() + (config.cooldownSeconds || 0) * 1000);
      message.textContent = configured ? "A kapunyitás használatra kész." : "A Twilio még nincs megfelelően beállítva a szerveren.";
      message.className = "gate-feedback";
    } catch (error) {
      message.textContent = error.message || "A beállítások ellenőrzése nem sikerült.";
      message.className = "gate-feedback error";
    }
    updateButton();
  }

  window.JittGate = { mount };
})();
