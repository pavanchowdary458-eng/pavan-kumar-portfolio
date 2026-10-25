const menu = document.querySelector(".menu-btn");
const nav = document.querySelector("nav");
menu.addEventListener("click", () => nav.classList.toggle("open"));
document.querySelectorAll("nav a").forEach(a => a.addEventListener("click", () => nav.classList.remove("open")));

// Contact form: send via the JSON API without a page reload (falls back to normal POST if JS is off)
const form = document.getElementById("contact-form");
if (form) {
  const status = document.getElementById("form-status");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    const data = Object.fromEntries(new FormData(form));
    status.className = "form-status";
    status.textContent = "Sending…";
    btn.disabled = true;
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const out = await res.json();
      const details = out.errors ? " " + Object.values(out.errors).join(" ") : "";
      status.textContent = out.message + details;
      status.className = "form-status " + (out.ok ? "ok" : "error");
      if (out.ok) form.reset();
    } catch (err) {
      status.textContent = "Network error. Please try again.";
      status.className = "form-status error";
    } finally {
      btn.disabled = false;
    }
  });
}
