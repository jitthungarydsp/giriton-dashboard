const form = document.querySelector("#login-form");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const togglePassword = document.querySelector("#toggle-password");
const message = document.querySelector("#message");

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

  message.classList.add("ok");
  message.textContent = "Belépés sablon kész. A következő körben ide kötjük be a valódi azonosítást.";
});
