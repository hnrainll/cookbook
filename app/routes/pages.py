"""
Static page routes.
静态页面路由。
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import settings

router = APIRouter(tags=["pages"])

CONTACT_EMAIL_PLACEHOLDER = "__CONTACT_EMAIL__"


PAGE_STYLE = """
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --text: #1f1a17;
      --muted: #5f544d;
      --line: #ded3c4;
      --accent: #8b5e3c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top, rgba(139, 94, 60, 0.12), transparent 32%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      color: var(--text);
    }
    main {
      max-width: 820px;
      margin: 48px auto;
      padding: 0 20px;
    }
    article {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 32px 28px;
      box-shadow: 0 18px 40px rgba(53, 38, 28, 0.08);
    }
    h1, h2 { line-height: 1.2; }
    h1 {
      margin: 0 0 10px;
      font-size: 2.2rem;
      color: var(--accent);
    }
    h2 {
      margin-top: 28px;
      font-size: 1.1rem;
    }
    p, li {
      line-height: 1.7;
      color: var(--text);
    }
    .muted {
      color: var(--muted);
      margin-bottom: 24px;
    }
    ul, ol {
      padding-left: 20px;
    }
    a {
      color: var(--accent);
    }
    code {
      background: rgba(139, 94, 60, 0.08);
      padding: 2px 6px;
      border-radius: 6px;
    }
  </style>
"""


PRIVACY_POLICY_TEMPLATE = (
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy</title>
"""
    + PAGE_STYLE
    + """
</head>
<body>
  <main>
    <article>
      <h1>Privacy Policy</h1>
      <p class="muted">Last updated: April 3, 2026</p>

      <p>
        This Privacy Policy describes how this application and its operator handle information when
        the service is used to connect and synchronize messages across supported third-party
        platforms, including Feishu, Telegram, Threads, Bluesky, Mastodon, and Fanfou.
      </p>

      <h2>Operator</h2>
      <p>
        This service is operated by the deployer or maintainer of this application instance. If you
        publish this service publicly, replace this statement with your organization or operator
        name.
      </p>

      <h2>Information We Collect and Process</h2>
      <p>Depending on the connected platform and features in use, the service may process:</p>
      <ul>
        <li>
          basic account identifiers such as user IDs, sender IDs, platform handles, or chat IDs;
        </li>
        <li>message content that is submitted to the service for synchronization or forwarding;</li>
        <li>
          media metadata and uploaded image files required to process or deliver supported media;
        </li>
        <li>OAuth tokens, access tokens, refresh tokens, and related authorization metadata;</li>
        <li>technical and operational logs used for reliability, security, and debugging.</li>
      </ul>

      <h2>How Information Is Used</h2>
      <p>Information is used only to operate the service, including:</p>
      <ul>
        <li>receiving, transforming, and forwarding messages between connected platforms;</li>
        <li>storing message history and delivery results when persistence is enabled;</li>
        <li>maintaining authorized connections to third-party platforms;</li>
        <li>monitoring service health, troubleshooting, and preventing abuse.</li>
      </ul>

      <h2>Legal Basis and Purpose</h2>
      <p>
        Information is processed solely for the purpose of providing the requested integration and
        synchronization functionality, maintaining service security, and operating the application.
      </p>

      <h2>Data Sharing</h2>
      <p>
        Data is not sold. Information may be shared only with the third-party platforms that you
        explicitly authorize or use through the service, and only as needed to deliver requested
        functionality.
      </p>

      <h2>Data Retention</h2>
      <p>
        Data may be retained for as long as reasonably necessary to operate the service, maintain
        linked platform sessions, provide message delivery records, support troubleshooting, and
        meet legal, compliance, or security obligations. Operators may delete stored data earlier at
        their discretion.
      </p>

      <h2>Data Deletion and Revocation</h2>
      <p>
        You may stop using the service at any time. If platform authorization is revoked or removed,
        associated tokens may no longer be used for synchronization. If you would like data or
        authorizations associated with your use of the service to be deleted, contact the operator
        using the contact information provided below.
      </p>

      <h2>Third-Party Services</h2>
      <p>
        This service depends on third-party platform APIs and infrastructure providers. Your use of
        those platforms remains subject to their own privacy policies and terms.
      </p>

      <h2>Security</h2>
      <p>
        Reasonable technical measures may be used to protect stored credentials, message data, and
        operational records. However, no method of transmission or storage can be guaranteed to be
        completely secure.
      </p>

      <h2>Children</h2>
      <p>
        This service is not intended for children under the age required by applicable law to use
        the connected third-party platforms.
      </p>

      <h2>Changes to This Policy</h2>
      <p>
        This Privacy Policy may be updated from time to time. Continued use of the service after an
        update means the revised version applies from its posted effective date.
      </p>

      <h2>Contact Information</h2>
      <p>
        If you have questions, requests, or concerns about this Privacy Policy or your data, contact
        the service operator at <strong>__CONTACT_EMAIL__</strong>.
      </p>
    </article>
  </main>
</body>
</html>
"""
)


DATA_DELETION_TEMPLATE = (
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Data Deletion Instructions</title>
"""
    + PAGE_STYLE
    + """
</head>
<body>
  <main>
    <article>
      <h1>Data Deletion Instructions</h1>
      <p class="muted">Last updated: April 3, 2026</p>

      <p>
        If you would like your data or platform authorization associated with this service to be
        deleted, follow the instructions below.
      </p>

      <h2>What You Can Request</h2>
      <ul>
        <li>removal of connected platform authorization tokens;</li>
        <li>deletion of stored message records or related delivery metadata, where applicable;</li>
        <li>deletion of other account-linked data retained by this application instance.</li>
      </ul>

      <h2>How to Request Deletion</h2>
      <ol>
        <li>Send a deletion request to <strong>__CONTACT_EMAIL__</strong>.</li>
        <li>
          Include the platform you used, your relevant account identifier, and a brief description
          of your request.
        </li>
        <li>
          If needed, the operator may ask for reasonable information to verify account ownership.
        </li>
      </ol>

      <h2>Authorization Revocation</h2>
      <p>
        You may also revoke this application's access from the relevant third-party platform
        settings where supported. Revoking access may stop future synchronization immediately, but
        it may not automatically remove data already stored by this service.
      </p>

      <h2>Processing Time</h2>
      <p>
        Deletion requests will be processed within a reasonable period, subject to technical,
        security, and legal requirements. Some records may be retained where necessary for security,
        fraud prevention, or legal compliance.
      </p>

      <h2>Contact</h2>
      <p>
        Contact: <strong>__CONTACT_EMAIL__</strong>
      </p>
    </article>
  </main>
</body>
</html>
"""
)


@router.get("/meta/privacy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    return HTMLResponse(
        content=PRIVACY_POLICY_TEMPLATE.replace(
            CONTACT_EMAIL_PLACEHOLDER,
            settings.public_contact_email,
        )
    )


@router.get("/meta/data-deletion", response_class=HTMLResponse)
async def data_deletion_instructions() -> HTMLResponse:
    return HTMLResponse(
        content=DATA_DELETION_TEMPLATE.replace(
            CONTACT_EMAIL_PLACEHOLDER,
            settings.public_contact_email,
        )
    )
