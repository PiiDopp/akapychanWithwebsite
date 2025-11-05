(function () {
  document.documentElement.classList.add("is-entering");
  requestAnimationFrame(() => {
    document.documentElement.classList.remove("is-entering");
    document.documentElement.classList.add("is-entered");
  });

  document.addEventListener("click", function (e) {
    const a = e.target.closest("a");
    if (!a) return;
    if (a.matches(".runBtn, [data-skip-transition]")) return;

    const sameOrigin = a.origin === location.origin;
    const sameTab = !a.target || a.target === "_self";
    const isHash =
      a.hash &&
      a.pathname === location.pathname &&
      a.search === location.search;

    if (!sameOrigin || !sameTab || isHash) return;

    e.preventDefault();
    const go = () => {
      location.href = a.href;
    };

    const root = document.documentElement;
    root.classList.add("is-leaving");
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      go();
    };
    root.addEventListener("transitionend", finish, { once: true });
    setTimeout(finish, 350);
  });

  window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
      document.documentElement.classList.add("is-entered");
      document.documentElement.classList.remove("is-entering", "is-leaving");
    }
  });
})();
