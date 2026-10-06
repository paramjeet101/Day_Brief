// ============================================================================
// DayBrief AI — frontend behaviour (lightweight, no framework)
// ============================================================================
(function () {
    "use strict";

    function getCookie(name) {
        var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
        return m ? decodeURIComponent(m.pop()) : null;
    }

    // ---- "Refresh brief" → regenerate via the API, then reload ------------
    var form = document.getElementById("generate-form");
    var btn = document.getElementById("generate-btn");
    if (form && btn) {
        form.addEventListener("submit", async function (evt) {
            evt.preventDefault();
            var label = btn.textContent;
            btn.disabled = true;
            btn.textContent = "⏳ Refreshing…";
            try {
                var res = await fetch(btn.getAttribute("data-api"), {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "X-CSRFToken": getCookie("csrftoken") || "", "Content-Type": "application/json" },
                    body: "{}",
                });
                if (!res.ok) throw new Error("HTTP " + res.status);
                window.location.reload();
            } catch (e) {
                btn.disabled = false;
                btn.textContent = label;
                form.submit(); // graceful fallback to a normal POST
            }
        });
    }

    // ---- Flash auto-dismiss -----------------------------------------------
    document.querySelectorAll(".flash").forEach(function (el) {
        setTimeout(function () {
            el.style.transition = "opacity .4s ease, transform .4s ease";
            el.style.opacity = "0";
            el.style.transform = "translateY(-8px)";
            setTimeout(function () { el.remove(); }, 400);
        }, 5000);
    });

    // ---- Timezone hint for the preferences form ---------------------------
    var tzInput = document.querySelector('input[name="timezone"]');
    if (tzInput && (!tzInput.value || tzInput.value === "UTC")) {
        try {
            var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            if (tz) tzInput.placeholder = tz + " (detected)";
        } catch (e) { /* ignore */ }
    }

    // ---- Theme (persisted) + toggle ---------------------------------------
    var root = document.documentElement;
    try {
        var saved = localStorage.getItem("daybrief-theme");
        if (saved) root.setAttribute("data-theme", saved);
    } catch (e) { /* private mode */ }

    var toggle = document.getElementById("theme-toggle");
    if (toggle) {
        toggle.addEventListener("click", function () {
            var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
            root.setAttribute("data-theme", next);
            try { localStorage.setItem("daybrief-theme", next); } catch (e) { /* ignore */ }
        });
    }
})();
