(function () {
  "use strict";

  var tz;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch (e) {
    return;
  }
  if (!tz) {
    return;
  }

  function getCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|;\\s*)" + name + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : null;
  }

  if (getCookie("timezone") !== tz) {
    document.cookie =
      "timezone=" + tz + "; path=/; SameSite=Lax; max-age=31536000";
    location.reload();
  }
})();
