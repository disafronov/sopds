(function () {
  "use strict";

  const COOKIE_NAME = "timezone";
  // sessionStorage key that records that a cookie + reload attempt was made.
  const COOKIE_ATTEMPT_KEY = "sopds-tz-cookie-attempt";

  let tz;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch (e) {
    return;
  }
  if (!tz) {
    return;
  }

  function getCookie(name) {
    const match = document.cookie.match(
      new RegExp("(?:^|;\\s*)" + name + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : null;
  }

  if (getCookie(COOKIE_NAME) !== tz) {
    // Guard against an infinite reload loop when cookies are blocked: the
    // cookie + reload attempt is allowed at most once per session. If the
    // flag is already present, the cookie was not persisted on the previous
    // attempt, so reloading again would not help.
    if (sessionStorage.getItem(COOKIE_ATTEMPT_KEY)) {
      return;
    }
    sessionStorage.setItem(COOKIE_ATTEMPT_KEY, "1");
    document.cookie =
      COOKIE_NAME + "=" + tz + "; path=/; SameSite=Lax; max-age=31536000";
    location.reload();
  }
})();
