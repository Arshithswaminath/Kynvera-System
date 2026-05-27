/**
 * Boots the Approval activity live trail on all HR form sidebars.
 * Polls /hr/api/signoff-activity after submit or when ?edit=<id> is present.
 */
(function () {
  function hrApi() {
    return window.HrGenericFormEdit || null;
  }

  function bootLiveActivity() {
    if (!document.getElementById('hrSignoffActivitySec')) return;
    var api = hrApi();
    if (!api || !api.bootSignoffActivitySidebar) return;
    api.bootSignoffActivitySidebar();
  }

  function startLivePoll(submissionId) {
    if (!submissionId) return;
    var api = hrApi();
    if (!api || !api.startSignoffActivityPoll) return;
    api.startSignoffActivityPoll(String(submissionId));
  }

  function installSubmitHook() {
    if (window.__hrSignoffActivitySubmitHooked) return;
    window.__hrSignoffActivitySubmitHooked = true;
    var origFetch = window.fetch;
    window.fetch = function () {
      var args = arguments;
      var resource = args[0];
      var url = typeof resource === 'string'
        ? resource
        : (resource instanceof Request ? resource.url : '');
      return origFetch.apply(this, args).then(function (res) {
        if (url.indexOf('/hr/api/submit') !== -1 && res && res.ok) {
          res.clone().json().catch(function () { return null; }).then(function (body) {
            if (body && body.success && body.submission_id) {
              startLivePoll(body.submission_id);
            }
          });
        }
        return res;
      });
    };
  }

  function init() {
    installSubmitHook();
    bootLiveActivity();
  }

  window.addEventListener('load', init);
  if (document.readyState === 'complete') init();
})();
