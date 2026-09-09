const form = document.querySelector("#login-form");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const togglePassword = document.querySelector("#toggle-password");
const message = document.querySelector("#message");
const loginShell = document.querySelector("#login-shell");
const hubShell = document.querySelector("#hub-shell");
const logoutButton = document.querySelector("#logout-button");

togglePassword?.addEventListener("click", () => {
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  togglePassword.textContent = visible ? "Mutat" : "Elrejt";
});

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  message.classList.remove("ok");

  if (!email.value.trim() || !password.value.trim()) {
    message.textContent = "Add meg az e-mail címet és a jelszót.";
    return;
  }

  loginShell.hidden = true;
  hubShell.hidden = false;
});

logoutButton?.addEventListener("click", () => {
  hubShell.hidden = true;
  loginShell.hidden = false;
  password.value = "";
  message.classList.remove("ok");
  message.textContent = "";
});
