(function () {
    const storageKey = `scroll-position:${window.location.href}`;

    if ("scrollRestoration" in window.history) {
        window.history.scrollRestoration = "manual";
    }

    window.addEventListener("pagehide", function () {
        window.sessionStorage.setItem(
            storageKey,
            JSON.stringify({
                x: window.scrollX,
                y: window.scrollY
            })
        );
    });

    window.addEventListener("pageshow", function () {
        const savedPosition = window.sessionStorage.getItem(storageKey);

        if (!savedPosition) {
            return;
        }

        const position = JSON.parse(savedPosition);
        window.requestAnimationFrame(function () {
            window.scrollTo(position.x, position.y);
        });
    });
})();
