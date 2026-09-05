(function () {
  "use strict";

  var form = document.getElementById("newsletter-form");
  var toast = document.getElementById("toast");
  var toastTimer = null;

  function showToast(text) {
    if (!toast) return;
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.classList.remove("show");
    }, 4000);
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = document.getElementById("email").value.trim();
      var button = form.querySelector("button");
      var originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "Sending…";

      fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { status: res.status, data: data };
          });
        })
        .then(function (result) {
          if (result.data.ok) {
            showToast(result.data.message || "Subscribed.");
            form.reset();
          } else {
            showToast(result.data.error || "Something went wrong.");
          }
        })
        .catch(function () {
          showToast("Network error — please try again.");
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = originalLabel;
        });
    });
  }

  // Contact form
  var contactForm = document.getElementById("contact-form");
  var contactNote = document.getElementById("contact-note");

  if (contactForm) {
    contactForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var button = contactForm.querySelector("button[type='submit']");
      var originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "Sending…";

      var payload = {
        name: document.getElementById("name").value.trim(),
        email: document.getElementById("c-email").value.trim(),
        phone: document.getElementById("phone").value.trim(),
        message: document.getElementById("message").value.trim(),
      };

      fetch("/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { status: res.status, data: data };
          });
        })
        .then(function (result) {
          var text = result.data.ok
            ? result.data.message || "Message sent."
            : result.data.error || "Something went wrong.";
          if (contactNote) {
            contactNote.textContent = text;
            contactNote.hidden = false;
          }
          showToast(text);
          if (result.data.ok) contactForm.reset();
        })
        .catch(function () {
          showToast("Network error — please try again.");
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = originalLabel;
        });
    });
  }

  // Mobile nav toggle: reveal the nav links list in place of the icon row.
  var navToggle = document.querySelector(".nav-toggle");
  var navLinks = document.querySelector(".nav-links");
  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      var isOpen = navLinks.style.display === "flex";
      navLinks.style.display = isOpen ? "none" : "flex";
      navLinks.style.flexDirection = "column";
      navLinks.style.position = "absolute";
      navLinks.style.top = "64px";
      navLinks.style.right = "32px";
      navLinks.style.background = "#12172a";
      navLinks.style.border = "1px solid rgba(255,255,255,0.09)";
      navLinks.style.borderRadius = "14px";
      navLinks.style.padding = "16px 22px";
      navLinks.style.gap = "14px";
      navToggle.setAttribute("aria-expanded", String(!isOpen));
    });
  }
})();
