/**
 * Kynvera Hub — portal launcher for separate product apps.
 * Expects window.__KYNVERA_HUB__ = { hub_mode, fire_app_url, municipality_app_url, home_url }
 */
(function (global) {
  "use strict";

  function hubConfig() {
    return global.__KYNVERA_HUB__ || {};
  }

  function isHubMode() {
    if (document.body && document.body.classList.contains("page-dashboard-hub")) {
      return true;
    }
    return !!hubConfig().hub_mode;
  }

  function getAccessToken() {
    try {
      return localStorage.getItem("access_token") || "";
    } catch (e) {
      return "";
    }
  }

  function buildSsoUrl(appBase, nextPath) {
    var base = (appBase || "").replace(/\/$/, "");
    if (!base) return "";
    var token = getAccessToken();
    if (!token) return base + "/login";
    var next = nextPath || "/dashboard";
    return (
      base +
      "/sso/consume?token=" +
      encodeURIComponent(token) +
      "&next=" +
      encodeURIComponent(next)
    );
  }

  function launchApp(appBase, nextPath) {
    var url = buildSsoUrl(appBase, nextPath);
    if (!url) {
      alert("This application URL is not configured. Set KYNVERA_FIRE_APP_URL / KYNVERA_MUNICIPALITY_APP_URL.");
      return;
    }
    window.location.href = url;
  }

  function updateHubModuleVisibility(user) {
    if (!isHubMode()) return false;
    var isAdmin = user && user.role === "admin";
    var cfg = hubConfig();

    function show(el, on) {
      if (!el) return;
      el.style.display = on ? "block" : "none";
      el.style.visibility = on ? "visible" : "hidden";
    }

    var fireCard = document.getElementById("module-fire-app");
    var muniCard = document.getElementById("module-municipality-app");
    var adminCard = document.getElementById("module-admin");

    var canFire =
      isAdmin || (user && user.access_fire_app === true);
    var canMuni =
      isAdmin || (user && user.access_municipality_app === true);

    show(fireCard, canFire && !!(cfg.fire_app_url || "").trim());
    show(muniCard, canMuni && !!(cfg.municipality_app_url || "").trim());
    // If URLs missing but user has access, still show card (click warns)
    if (canFire && fireCard && !(cfg.fire_app_url || "").trim()) show(fireCard, true);
    if (canMuni && muniCard && !(cfg.municipality_app_url || "").trim()) show(muniCard, true);
    show(adminCard, isAdmin);

    // Hide legacy in-app module cards on the portal homepage
    [
      "module-hr",
      "module-inspection",
      "module-store",
      "module-ticketing",
      "module-operations",
      "module-finance",
      "module-dochub",
      "module-submitted-forms",
      "module-pending-review",
      "module-device-management",
      "module-bd",
      "module-cd-notifications",
      "module-report-generation",
      "module-review-history",
    ].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.style.display = "none";
        el.style.visibility = "hidden";
      }
    });

    return true;
  }

  function bindLaunchers() {
    if (!isHubMode()) return;
    var cfg = hubConfig();
    var fire = document.getElementById("module-fire-app");
    var muni = document.getElementById("module-municipality-app");
    if (fire) {
      fire.addEventListener("click", function (e) {
        e.preventDefault();
        launchApp(cfg.fire_app_url, "/dashboard");
      });
    }
    if (muni) {
      muni.addEventListener("click", function (e) {
        e.preventDefault();
        launchApp(cfg.municipality_app_url, "/dashboard");
      });
    }
  }

  global.KynveraHub = {
    isHubMode: isHubMode,
    updateHubModuleVisibility: updateHubModuleVisibility,
    launchApp: launchApp,
    bindLaunchers: bindLaunchers,
    hubConfig: hubConfig,
  };

  document.addEventListener("DOMContentLoaded", bindLaunchers);
})(window);
