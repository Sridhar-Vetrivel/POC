# Request to Psiog IT: Entra app registrations, SharePoint access and a VM for the Ingenus POC

**From:** Sridhar Vetrivel (Psiog pre-sales) · **Date:** 19 Oct 2026 · **For:** Psiog IT (Entra ID and infrastructure admins)
**Purpose:** set up what a proof of concept needs to (1) read a Psiog SharePoint folder through Microsoft Graph,
read-only, and (2) run one small internal server that only signed-in, named people can use.

---

## 1. Summary

We are building a pre-sales proof of concept for a client (Ingenus): a small read-only server that Claude Desktop
connects to, which reads contract files and compares them with mock SAP data. **All data is synthetic**: invented
contracts and numbers, no client data and no personal data. Nothing is written anywhere except the server's own log.

We need from you:

| # | Item | Section |
|---|---|---|
| 1 | An app registration for the **server** (exposes an API; reads SharePoint on behalf of the signed-in user) | 3 |
| 2 | An app registration for the **desktop client** (signs the user in; public client, no secret) | 4 |
| 3 | Delegated, **read-only** Microsoft Graph permissions, with admin consent | 3.3 |
| 4 | "Assignment required" on both, limited to a small group of named users | 5 |
| 5 | Members added to the existing SharePoint site `INGENUS` | 6 |
| 6 | A small internal VM, an internal DNS name and an HTTPS certificate | 7 |
| 7 | The values listed in section 9, sent back to us | 9 |

Users: Sridhar Vetrivel, Aditya Manthena, and up to two testers (names to follow). Duration: about six weeks.
Everything is removed or handed back at the end (section 10).

## 2. How it fits together

```
Claude Desktop on a Psiog laptop
   └─ bridge (a small extension; signs the user in to Entra as a public client, no secret)
        │  HTTPS, Bearer token for the server's API, over the office network or VPN
        ▼
Ingenus POC server on the internal VM                     (validates the token; logs the user per call)
        │  on-behalf-of the signed-in user, delegated, read-only
        ▼
Microsoft Graph → SharePoint site INGENUS, folder Documents/General/synthetic/contracts
```

- The **server** never holds a user's password and never writes to SharePoint: its Graph permissions are read-only,
  and they are **delegated**, so the server can never see more than the signed-in user can.
- The VM is **not** reachable from the internet; there is no inbound rule from outside.

## 3. App registration 1: the server ("Ingenus POC MCP Server")

Entra admin center > Identity > Applications > **App registrations** > **New registration**:

| Setting | Value |
|---|---|
| Name | `Ingenus POC MCP Server` |
| Supported account types | **Accounts in this organizational directory only** (single tenant) |
| Redirect URI | None |

### 3.1 Expose an API

App registration > **Expose an API**:

1. **Application ID URI:** accept the default `api://<server-client-id>`.
2. **Add a scope:**

| Field | Value |
|---|---|
| Scope name | `access_as_user` |
| Who can consent | Admins only |
| Admin consent display name | `Use the Ingenus POC server` |
| Admin consent description | `Lets the Ingenus POC desktop client call the Ingenus POC server as the signed-in user.` |
| State | Enabled |

3. **Authorized client applications:** after app registration 2 exists, add its client ID here for the
   `access_as_user` scope (so users are not asked to consent).

### 3.2 Token version

App registration > **Manifest**: set the access token version to **2** (`"requestedAccessTokenVersion": 2`, or
`api.requestedAccessTokenVersion` in the newer manifest format). Please confirm the field name in the current portal.

### 3.3 API permissions (delegated, read-only)

App registration > **API permissions** > Add a permission > Microsoft Graph > **Delegated permissions**:

| Permission | Why |
|---|---|
| `User.Read` | Sign-in and the user's name for the log |
| `Files.Read.All` | Read the contract files the signed-in user can read |
| `Sites.Read.All` | Find the SharePoint site and library |

Then **Grant admin consent for Psiog**. No application permissions and no write permissions are requested.

**Least-privilege alternative (your choice):** delegated `Sites.Selected` limited to the `INGENUS` site, instead of
`Files.Read.All` and `Sites.Read.All`. It needs a per-site grant by a SharePoint admin. Please tell us which you
prefer; our code works with either. (We have not verified that delegated `Sites.Selected` covers our calls; we
will test it if you choose it.)

### 3.4 Credential: a certificate, not a secret

The server exchanges the user's token for a Graph token (the on-behalf-of flow), so it needs **one** credential.

- Please use a **certificate**, not a client secret.
- Preferred: we create the key pair on the VM (the private key never leaves it) and send you the public
  certificate (`.cer`) to upload under **Certificates & secrets > Certificates**. Validity: 6 months is enough.
- If your policy is to issue the certificate yourselves, install it on the VM in the machine's certificate store
  and tell us the thumbprint.

## 4. App registration 2: the desktop client ("Ingenus POC Desktop Client")

**New registration**:

| Setting | Value |
|---|---|
| Name | `Ingenus POC Desktop Client` |
| Supported account types | **Accounts in this organizational directory only** |
| Redirect URI | Platform **Public client/native (mobile & desktop)**: `http://localhost` |

Then:

1. **Authentication** > Advanced settings > **Allow public client flows: Yes** (lets the user sign in with a
   device code if a browser redirect is not possible).
2. **API permissions** > Add a permission > **My APIs** > `Ingenus POC MCP Server` > Delegated >
   `access_as_user`. **Grant admin consent for Psiog.**
3. No certificates or secrets: a desktop app cannot keep one secret.

## 5. Who may sign in

For **both** apps, in **Enterprise applications** > the app > Properties:

- **Assignment required: Yes.**
- **Users and groups:** assign a security group, for example `SG-Ingenus-POC`, with the named users from section 1.

Only those users can get a token for the server; everyone else is refused by Entra. Conditional Access policies
that already apply to Psiog users (MFA, compliant device) are fine.

## 6. SharePoint

The site already exists: `https://psiog0.sharepoint.com/sites/INGENUS` (a private Microsoft 365 group, currently one
member). The contracts are under **Documents > General > synthetic > contracts**: 30 synthetic PDFs, each marked
"SYNTHETIC: invented for the Ingenus POC. Not a real contract."

- Please add the users from section 1 as **members** (read access is enough). Because the server reads on behalf of
  each user, a user who is not a member will see nothing.
- Please confirm it is acceptable that **file and folder names include the client's name** ("Ingenus" in the site
  name; customer names in the files are invented).

## 7. The VM

| Item | Request |
|---|---|
| Size | 2 vCPU, 4 GB RAM, 40 GB disk |
| OS | Windows Server 2022 (preferred; a later step may read a Windows file share as a service account) or Ubuntu 24.04 |
| Network | Internal only. **Inbound:** TCP 443 from the office network and the VPN address range. **No inbound from the internet** |
| Outbound | HTTPS 443 to `login.microsoftonline.com` and `graph.microsoft.com` (sign-in and SharePoint), and to `pypi.org` / `files.pythonhosted.org` for installing Python packages (or tell us your package mirror) |
| Software | Python 3.13; we install the rest |
| Access | Remote desktop (or SSH) for Sridhar |
| DNS | An internal name, for example `ingenus-poc.psiog.local` (any name is fine) |
| Service account | A local or domain account the server runs as; no admin rights needed after setup |

### 7.1 HTTPS certificate for the server (please read)

The desktop client refuses plain `http://` to another machine, so the server needs a TLS certificate for its DNS
name. **The client runs on Node.js inside Claude Desktop, and Node does not automatically trust certificates from
an internal (enterprise) certificate authority** the way Windows does. Two ways to handle it:

1. **Preferred:** a certificate from a **publicly trusted CA** for a Psiog-owned name (the name can still resolve
   only inside the network). Nothing needs to change on laptops.
2. A certificate from Psiog's internal CA, **plus** the internal CA's root certificate (`.cer`, public) sent to us, so
   we can configure the client to trust it.

Please tell us which one you can do.

## 8. What we will not do

- No write permissions anywhere: Graph permissions are read-only, and the server has no write code for SharePoint.
- No client secrets in code or in the repository; the certificate's private key stays on the VM.
- No client (Ingenus) data and no personal data: synthetic files only, until Ingenus's data policy is signed off.
- No inbound access from the internet, and no public endpoint.
- Tokens are not passed through: the server gets its own Graph token for each user and never forwards the user's
  token.

## 9. What we need back

| Value | Example |
|---|---|
| Directory (tenant) ID | `xxxxxxxx-xxxx-…` |
| Server app: Application (client) ID and Application ID URI | `api://xxxxxxxx-…` |
| Desktop client app: Application (client) ID | |
| Which Graph permissions were granted (3.3 or the `Sites.Selected` alternative) | |
| Certificate: confirmation that our `.cer` is uploaded, or the thumbprint of yours | |
| Security group name and members | |
| VM: hostname, IP, OS, how to connect | |
| Server TLS certificate: option 1 or 2 from 7.1 (and the root `.cer` if option 2) | |
| Anything your policy requires us to do or document | |

Client IDs and the tenant ID are not secrets, but please send them by email or Teams, not in a public place.

## 10. Duration and clean-up

About six weeks from setup. At the end we will tell you, and you can:

- delete both app registrations and the security group (this revokes all tokens and consents);
- delete the VM, or wipe and hand it back;
- archive or delete the `INGENUS` SharePoint site.

## 11. Not in this request

A Windows file share with a read-only service account (to test reading a network drive) will come as a separate,
small request once this part works.

Thank you. Happy to walk through the design on a call.
Sridhar Vetrivel
