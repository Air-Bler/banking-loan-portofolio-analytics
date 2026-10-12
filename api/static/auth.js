// "Sign in with Microsoft" for prod: MSAL.js (vendor/msal-browser-3.30.0.min.js) against the Team 2
// Entra app. The API checks the token's signature, issuer, audience and expiry (api/security.py).
// Nothing here is secret: a single-page app has a client ID, never a client secret.
"use strict";

const auth = (() => {
  const CLIENT_ID = "ea9e7159-2ca6-44b0-bc6c-fa2637d51347";
  const AUTHORITY = "https://login.microsoftonline.com/b1732512-60e5-48fb-92e8-8d6902ac1349";
  const SCOPES = [`api://${CLIENT_ID}/access_as_user`];
  // Registered on the Entra app (infra/auth_setup.sh): the site root of prod, dev and localhost:8000.
  const REDIRECT_URI = `${window.location.origin}/`;

  // MSAL opens sign-in in a popup that returns to REDIRECT_URI ("/" redirects to /app/, keeping the
  // #code=... fragment). The opener reads that fragment itself, so the app must stay idle in the popup.
  const inPopup = Boolean(window.opener && window.opener !== window && window.name.startsWith("msal."));

  let client = null;
  let ready = null;
  let interactive = null; // one shared popup when many calls need a new token at once

  function start() {
    if (!ready) {
      client = new msal.PublicClientApplication({
        auth: { clientId: CLIENT_ID, authority: AUTHORITY, redirectUri: REDIRECT_URI, postLogoutRedirectUri: REDIRECT_URI },
        cache: { cacheLocation: "sessionStorage" }, // forgotten when the tab closes
      });
      ready = client.initialize()
        .then(() => client.handleRedirectPromise())
        .then((result) => {
          const account = result?.account || client.getActiveAccount() || client.getAllAccounts()[0] || null;
          if (account) client.setActiveAccount(account);
          return account;
        });
    }
    return ready;
  }

  function account() {
    return client?.getActiveAccount() || null;
  }

  async function signIn() {
    await start();
    const result = await client.loginPopup({ scopes: SCOPES, prompt: "select_account" });
    client.setActiveAccount(result.account);
    return result.account;
  }

  async function signOut() {
    await start();
    const current = account();
    if (!current) return;
    await client.logoutPopup({ account: current, postLogoutRedirectUri: REDIRECT_URI });
  }

  // A valid access token for the API, or null when nobody is signed in. MSAL renews it silently
  // with its refresh token, so the session outlives the one-hour token lifetime.
  async function getAccessToken() {
    await start();
    const current = account();
    if (!current) return null;
    try {
      return (await client.acquireTokenSilent({ scopes: SCOPES, account: current })).accessToken;
    } catch (err) {
      if (!(err instanceof msal.InteractionRequiredAuthError)) throw err;
      interactive ??= client.acquireTokenPopup({ scopes: SCOPES, account: current }).finally(() => { interactive = null; });
      return (await interactive).accessToken;
    }
  }

  // AADSTS50105: the user is in the tenant but not assigned to the app (not a Team 2 member).
  function describeError(err) {
    const text = `${err?.errorCode || ""} ${err?.errorMessage || ""} ${err?.message || ""}`;
    if (text.includes("AADSTS50105")) return "Only Team 2 members can sign in.";
    if (err?.errorCode === "user_cancelled") return "Sign-in was cancelled.";
    if (err?.errorCode === "popup_window_error") return "The sign-in window was blocked. Allow pop-ups for this site and try again.";
    return "Sign-in failed. Try again.";
  }

  return { inPopup, start, account, signIn, signOut, getAccessToken, describeError };
})();
