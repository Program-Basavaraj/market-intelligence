try { const t = localStorage.getItem("mi-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage unavailable */ }
