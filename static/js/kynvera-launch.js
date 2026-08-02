/**
 * Portal launch page — send user to product app via SSO after login.
 * Expects window.__LAUNCH_APP__, __LAUNCH_PATH__, __ACCESS_FLAG__, __KYNVERA_HUB__.
 */
(function () {
  "use strict";

  var hub = window.__KYNVERA_HUB__ || {};
  var appKey = window.__LAUNCH_APP__ || "";
  var launchPath = window.__LAUNCH_PATH__ || "/";
  var accessFlag = window.__ACCESS_FLAG__ || "";
  var box = document.getElementById("launchBox");

  function showError(msg, linkHref, linkText) {
    if (!box) return;
    box.innerHTML =
      "<h1>Could not open this app</h1>" +
      '<p class="err"></p>' +
      (linkHref
        ? '<p style="margin-top:1rem"><a href="' +
          linkHref +
          '">' +
          (linkText || "Go back") +
          "</a></p>"
        : "");
    var err = box.querySelector(".err");
    if (err) err.textContent = msg;
  }

  function appUrl() {
    if (appKey === "fire") return (hub.fire_app_url || "").trim();
    if (appKey === "municipality") return (hub.municipality_app_url || "").trim();
    return "";
  }

  function getToken() {
    try {
      return localStorage.getItem("access_token") || "";
    } catch (e) {
      return "";
    }
  }

  function goLogin() {
    window.location.replace("/login?next=" + encodeURIComponent(launchPath));
  }

  function entitlementOk(user) {
    if (!user) return false;
    if (user.role === "admin") return true;
    if (!accessFlag) return true;
    return user[accessFlag] === true;
  }

  function launch() {
    var base = appUrl();
    if (!base) {
      showError(
        "This application URL is not configured. Set KYNVERA_FIRE_APP_URL or KYNVERA_MUNICIPALITY_APP_URL on the portal.",
        "/",
        "Back to Kynvera Home"
      );
      return;
    }
    if (window.KynveraHub && typeof window.KynveraHub.launchApp === "function") {
      window.KynveraHub.launchApp(base, "/dashboard");
      return;
    }
    var token = getToken();
    if (!token) {
      goLogin();
      return;
    }
    window.location.href =
      base.replace(/\/$/, "") +
      "/sso/consume?token=" +
      encodeURIComponent(token) +
      "&next=" +
      encodeURIComponent("/dashboard");
  }

  var token = getToken();
  if (!token) {
    goLogin();
    return;
  }

  fetch("/api/auth/me", {
    headers: { Authorization: "Bearer " + token, Accept: "application/json" },
  })
    .then(function (r) {
      if (r.status === 401 || r.status === 422) {
        goLogin();
        return null;
      }
      return r.ok ? r.json() : null;
    })
    .then(function (data) {
      if (data === null) return;
      var user = data && data.user ? data.user : null;
      try {
        if (user) localStorage.setItem("user", JSON.stringify(user));
      } catch (e) {}
      if (!entitlementOk(user)) {
        showError(
          "Your account does not have access to this application. Ask an administrator to grant it.",
          "/",
          "Back to Kynvera Home"
        );
        return;
      }
      launch();
    })
    .catch(function () {
      // Token present but me failed — still attempt SSO if URL configured
      launch();
    });
})();
