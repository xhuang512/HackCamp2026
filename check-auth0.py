#!/usr/bin/env python3
"""Check the Auth0 setup from docs/SIGNUP.md without opening a browser.

    python3 check-auth0.py

Read only. It sends no email, creates no account and signs nobody in. It asks
Auth0 the questions whose answers are otherwise one silent 401 on a phone:
is the client id real, is the callback URL registered, is the audience a
registered API, and does the app's own sign-in button reach a code screen.

What it cannot check is whether the email arrives and whether the UBC-only
action runs. Both need a real inbox, so both are in "Done when".
"""

import http.client
import http.cookiejar
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parent
FRONTEND_ENV = ROOT / "frontend" / ".env.local"
BACKEND_ENV = ROOT / "backend" / ".env"
# Must be one of the SPA's Allowed Callback URLs, or Auth0 refuses the probe
# for the right reason and the check reads as a failure.
REDIRECT_URI = "http://localhost:5173"

problems: list[str] = []


def ok(label: str) -> None:
    print(f"  ok    {label}")


def bad(label: str, fix: str) -> None:
    print(f"  FAIL  {label}")
    problems.append(fix)


def read_env(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in path.read_text().splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        )
    }


def main() -> int:
    print("\nenv files")
    front = read_env(FRONTEND_ENV)
    back = read_env(BACKEND_ENV)

    domain = front.get("VITE_AUTH0_DOMAIN", "")
    client_id = front.get("VITE_AUTH0_CLIENT_ID", "")
    audience = front.get("VITE_AUTH0_AUDIENCE", "")

    if domain and client_id:
        ok(f"frontend/.env.local, domain {domain}")
    else:
        bad(
            "frontend/.env.local is missing VITE_AUTH0_DOMAIN or VITE_AUTH0_CLIENT_ID",
            "Step 9. Copy frontend/.env.example to .env.local and fill it in.",
        )
        return report()

    if back.get("AUTH0_DOMAIN") == domain and back.get("AUTH0_AUDIENCE") == audience:
        ok("backend/.env agrees with the frontend")
    else:
        bad(
            "backend/.env does not match the frontend's domain and audience",
            "Step 9. AUTH0_DOMAIN and AUTH0_AUDIENCE must be character for "
            "character what the frontend sends, or every token is rejected.",
        )

    print("\nthe tenant")
    try:
        conn = http.client.HTTPSConnection(domain, timeout=15)
        conn.request("GET", "/.well-known/jwks.json")
        res = conn.getresponse()
        res.read()
        if res.status == 200:
            ok("signing keys are readable, so the backend can verify tokens")
        else:
            bad(f"jwks.json returned {res.status}", "Check VITE_AUTH0_DOMAIN for a typo.")
    except Exception as cause:  # noqa: BLE001
        bad(f"cannot reach {domain} ({cause})", "Check VITE_AUTH0_DOMAIN for a typo.")
        return report()

    print("\nthe application")
    page = authorize(domain, client_id, audience, connection=None)
    if page is None:
        return report()
    body, _url = page

    if "Service not found" in body:
        bad(
            f"the audience {audience} is not a registered API",
            "Step 3. The API's Identifier has to equal VITE_AUTH0_AUDIENCE exactly.",
        )
    else:
        ok(f"the audience {audience} is registered")

    if "Callback URL mismatch" in body or "callback_url_mismatch" in body.lower():
        bad(
            f"{REDIRECT_URI} is not an allowed callback URL",
            "Step 6. Add it to Allowed Callback URLs, Logout URLs and Web Origins.",
        )
    else:
        ok(f"{REDIRECT_URI} is an allowed callback URL")

    if "unauthorized_client" in body.lower():
        bad("the client id is not accepted", "Step 2. Recopy the SPA's Client ID.")
    else:
        ok("the client id is accepted")

    extra = []
    if "Continue with Google" in body:
        extra.append("Google")
    if 'name="password"' in body:
        extra.append("username and password")
    if extra:
        print(f"  note  other ways in are still enabled, {' and '.join(extra)}")
        print("        The UBC-only action still blocks them, but turn them off")
        print("        so the email code is the only door.")

    print("\nthe sign-in button")
    # connection=email is exactly what src/lib/auth.jsx sends.
    page = authorize(domain, client_id, audience, connection="email")
    if page is None:
        return report()
    body, _url = page

    if 'name="password"' in body:
        bad(
            "asking for connection=email still lands on a password form",
            "Step 4. Authentication, Passwordless, Email, choose Code, then open"
            " its Applications tab and enable it for this SPA. Auth0 ignores an"
            " unknown connection and falls back, which is why it looks like"
            " nothing happened.",
        )
    else:
        ok("the email code screen is what the app's button reaches")

    return report()


def authorize(domain: str, client_id: str, audience: str, connection: str | None):
    """Follow /authorize as a browser would, without signing anything in."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email offline_access",
        "audience": audience,
        # A throwaway PKCE challenge. /authorize rejects the request without
        # one, and nothing is ever exchanged for it.
        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        "code_challenge_method": "S256",
        "state": "setup-check",
        "nonce": "setup-check",
    }
    if connection is not None:
        params["connection"] = connection

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    url = f"https://{domain}/authorize?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 hangout-setup-check"})
    try:
        with opener.open(request, timeout=20) as res:
            return " ".join(res.read().decode("utf-8", "replace").split()), res.geturl()
    except urllib.error.HTTPError as cause:
        return " ".join(cause.read().decode("utf-8", "replace").split()), cause.url
    except Exception as cause:  # noqa: BLE001
        bad(f"/authorize did not answer ({cause})", "Check the tenant is awake.")
        return None


def report() -> int:
    if not problems:
        print("\nEverything this can check from here is set up.")
        print("The rest needs a real inbox. See 'Done when' in docs/SIGNUP.md.\n")
        return 0
    print(f"\n{len(problems)} to fix:\n")
    for i, fix in enumerate(problems, 1):
        print(f"  {i}. {re.sub(r"\s+", " ", fix)}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
