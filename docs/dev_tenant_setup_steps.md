# Setting up the v1 server's identity and SharePoint: the steps we did, in detail

What the repo owner did on 20 Oct 2026 in a Microsoft 365 developer tenant, with the screens as they looked then
(menu names may differ slightly in other portal versions). The same steps are what **Psiog IT** (or any admin) would do in
another tenant: [`psiog_it_steps_v1-4_v1-6.md`](psiog_it_steps_v1-4_v1-6.md) is the short checklist for them, this is the
long version. Why each thing exists is in decision [0004](decisions/0004-v1-per-user-sign-in-and-sharepoint-reading.md).

Real IDs are **not** written here. Fill in the table below as you go; the values go into `MCP-Server/.env`
(git-ignored), never into code or tests.

| Value | Where you get it | Yours |
|---|---|---|
| Tenant ID | Server app > Overview > **Directory (tenant) ID** | |
| Server app ID | Server app > Overview > **Application (client) ID** | |
| Application ID URI | Server app > Expose an API (it is `api://<server app ID>`) | |
| Desktop client app ID | Desktop client app > Overview > **Application (client) ID** | |
| SharePoint site URL | The site's address, `https://<tenant>.sharepoint.com/sites/<site>` | |
| Folder in the library | The path of the contracts folder, for example `General/synthetic/contracts` | |
| Certificate SHA-1 thumbprint | Printed when you make the certificate (step 5) | |

## 0. Before you start

- You need an account that can register apps and grant admin consent (here a Global Administrator). Check under
  **Entra admin center > Roles & administrators**: your account should be listed under *Global Administrator*, or try
  step 1; if **+ New registration** is greyed out or the consent button is inactive, you lack the role.
- Use `https://entra.microsoft.com` (or `portal.azure.com` > **Microsoft Entra ID**).
- The people who will use the server must be accounts **in this tenant**. The Claude account (`@psiog.com` here) is a
  different login and is not used for this.

## 1. The server app ("Ingenus POC MCP Server")

**1.1 Register it.** Entra ID > **App registrations** > **+ New registration**.
- Name: `Ingenus POC MCP Server`
- Supported account types: **Single tenant only** (the dropdown shows your tenant's short name after it)
- Redirect URI: **leave empty**
- **Register.** On the Overview page copy the tenant ID and the application (client) ID into the table.

**1.2 Give it an Application ID URI.** Left menu > **Expose an API**.
- Next to *Application ID URI* click **Add**. The side panel suggests `api://<server app ID>`; if it is empty, type that.
  **Save.** (Nothing is pre-filled in this portal version.)

**1.3 Add the scope.** Same page > **+ Add a scope**.

| Field | Value |
|---|---|
| Scope name | `access_as_user` |
| Who can consent | **Admins only** |
| Admin consent display name | `Use the Ingenus POC server` |
| Admin consent description | `Lets the Ingenus POC desktop client call the Ingenus POC server as the signed-in user.` |
| State | Enabled |

**Add scope.** It appears as `api://<server app ID>/access_as_user`. Leave *Authorized client applications* empty for now
(step 2.5).

**1.4 Set the token version to 2.** Left menu > **Manifest**. Use the **Microsoft Graph App Manifest (New)** tab (the
other one is being retired; edit only one, the portal updates the other).
- Find, inside the `"api"` block: `"requestedAccessTokenVersion": null,`
- Change `null` to `2` so it reads `"requestedAccessTokenVersion": 2,` and click **Save**.
- Why: the server checks the token's issuer and audience in their version 2.0 form; pinning the version means the
  format is ours, not Entra's default. Reopen the manifest afterwards and confirm it shows `2`.

**1.5 Add the Graph permissions (delegated, read-only).** Left menu > **API permissions** > **+ Add a permission** >
**Microsoft Graph** > **Delegated permissions**. Tick `Files.Read.All` and `Sites.Read.All` (`User.Read` is already
there) > **Add permissions**. Choose *Delegated*, never *Application*: delegated means "as the signed-in user".

**1.6 Grant admin consent.** Same page > **Grant admin consent for <your tenant>** > confirm. All three rows must show a
green tick and "Granted for <tenant>". (The "Admin consent required" column is only a default; ignore it.)

**1.7 The certificate.** Done later, in step 5, once the key pair exists. No client secret is used.

## 2. The desktop client app ("Ingenus POC Desktop Client")

This is what the bridge signs the user in with. It is a *public client*: it has no secret.

**2.1 Register it.** **App registrations** > **+ New registration**.
- Name: `Ingenus POC Desktop Client`; account types: **Single tenant only**
- Redirect URI: platform **Public client/native (mobile & desktop)**, value `http://localhost`
- **Register**; copy its application (client) ID into the table.

**2.2 Allow public client flows.** Left menu > **Authentication** (it may be called *Authentication (Preview)* with a
*Settings* tab) > **Allow public client flows = Yes** > **Save**.

**2.3 Let it call the server app.** Left menu > **API permissions** > **+ Add a permission**.
- Open **APIs my organization uses** and search for the server app by name or by its client ID. (The **My APIs** tab showed
  *No results* here: it only lists apps your account **owns**. If you prefer it, add yourself under the server app's
  **Owners**.)
- Select it > **Delegated permissions** > tick `access_as_user` > **Add permissions**.

**2.4 Grant admin consent.** **Grant admin consent for <your tenant>** > confirm. The list must show two green rows:
`Ingenus POC MCP Server > access_as_user` and `Microsoft Graph > User.Read`.

**2.5 Authorise it on the server app.** Open the **server** app > **Expose an API** > *Authorized client applications* >
**+ Add a client application**. Paste the desktop client's ID, tick `access_as_user`, **Add application**. A notice
"Successfully added Authorized client applications" appears, and the list shows the client ID. Compare that ID with the
desktop client's Overview page: they must be identical.

## 3. Who may sign in

**3.1 Make a group.** Entra ID > **Groups** > **New group**: type **Security**, name `SG-Ingenus-POC`. Add the people who
may use the server (here `develop.admin`) as members > **Create**. **Add yourself before the next step**, or you lock
yourself out of your own tests.

**3.2 Require assignment, on both apps.** Entra ID > **Enterprise applications**; for `Ingenus POC MCP Server`, then
again for `Ingenus POC Desktop Client`:
1. **Properties** > **Assignment required? = Yes** > **Save**.
2. **Users and groups** > **Add user/group** > pick `SG-Ingenus-POC` > **Assign**.

Anyone outside the group is now refused by Entra. (If an app is missing from the list, search by name or clear the
"Application type" filter.)

## 4. SharePoint

**4.1 The site.** Create (or use) a team site, here `mcp-sharepoint-test`, a private Microsoft 365 group. Add the group's
people as **Members** (read access is enough): site gear > **Site permissions**. The server reads **as each user**, so a
person who is not a member sees nothing.

**4.2 The folder layout.** In the site's **Documents** library create `General` > `synthetic` > `contracts`, and upload the
30 synthetic contract PDFs from `MCP-PlugIn/data/synthetic/contracts` keeping the sub-folders: `Chain_X` (4 files),
`Chain_Y` (1), `Wholesaler_Z` (1) and `bulk/Customer_01` to `Customer_08` (3 each). Wait until every spinner has gone, then
check you can open one PDF in the browser.

**4.3 Find the exact folder path.** Open the `contracts` folder and copy the address bar. The `id=` part is the encoded
path; decoded it reads `/sites/<site>/Shared Documents/General/synthetic/contracts`. "Shared Documents" is the library's
real name (the menu calls it *Documents*). The settings take the **site URL** and the path **after** the library name.

**4.4 Other folders in the site are not ours.** The library may hold other people's folders (here `AI_Absorption`). The
server reads only the configured folder and refuses any path outside it (a test covers this).

## 5. The certificate (the server's proof of identity)

The server needs one credential to swap a user's token for a Graph token. A certificate is used, not a secret: only the
public half is uploaded.

**5.1 Make the key pair** (OpenSSL; Git Bash has it). Full commands and the rules are in
[`developer_guide.md`](../developer_guide.md) section 5.1. In short:

```bash
mkdir -p MCP-Server/secrets && cd MCP-Server/secrets
export MSYS_NO_PATHCONV=1
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 180 -keyout server_key.pem -out server_cert.pem -subj "/CN=ingenus-poc-mcp-server"
openssl x509 -in server_cert.pem -outform DER -out ingenus-poc-mcp-server.cer
openssl x509 -in server_cert.pem -noout -fingerprint -sha1
```

The last line prints the thumbprint (remove the colons) for the table. Keep only `server_key.pem` in the git-ignored
`MCP-Server/secrets/`; keep the public `.pem` and `.cer` outside the repo.

**5.2 Upload the `.cer`** (never the key): server app > **Certificates & secrets** > **Certificates** tab > **Upload
certificate**. Check that the thumbprint shown starts the same as yours. The certificate is valid for 180 days; note the
expiry date and rotate before it.

**5.3 Say where the key and IDs are.** Copy `MCP-Server/.env.example` to `MCP-Server/.env` and fill in the table values.
`INGENUS_CERT_KEY_FILE=secrets/server_key.pem` (relative paths are read from `MCP-Server/`).

## 6. Check it works

**6.1 Without Claude** (two terminals, repo root):
1. `python -m ingenus_mcp.server`
2. `python MCP-Server\scripts\signin_check.py`: a browser opens; sign in with an account **of this tenant** (use a private
   window if the browser offers another account). Expected: step 1 prints HTTP 401, step 2 names who signed in, step 3 lists
   3 Chain X files with the draft left out, step 4 gives monthly gap 8,500.00 and exposure 17,000.00, and the last line
   says PASS.

**6.2 In Claude Desktop.** Build the bridge (`python MCP-Server/bridge/build_bridge.py`), then *Settings > Extensions >
Advanced settings > Extension Developer > Install unpacked extension* and choose `MCP-Server\build\bridge`. Fill in the Server
URL (`http://127.0.0.1:8765/mcp`), Tenant ID, Desktop client app ID and Server app ID. In a new chat ask: *Check Chain X's
contract against SAP as of 31 Aug 2026.* The first time a browser opens for the sign-in. Then confirm in
`MCP-Server\data\runtime\tool_calls.jsonl` that every call names the signed-in person.

## 7. What went differently from the plan

- The Application ID URI was not pre-filled: add it by hand (1.2).
- The token version field is `requestedAccessTokenVersion` inside the `"api"` block of the Microsoft Graph manifest (1.4).
- **My APIs** listed nothing for the server app; **APIs my organization uses** found it (2.3).
- The Claude login and the Microsoft sign-in are two different accounts; the log shows the Microsoft one.
- Nothing here needed Psiog IT, because the owner had admin rights in their own tenant. Psiog's tenant, and later
  Ingenus's, repeat the same steps with their admins; only the IDs and the site URL change.

## 8. Clean-up (end of a trial)

Delete both app registrations and the group (this revokes tokens and consent), delete the certificate files and
`MCP-Server/.env`, delete `%LOCALAPPDATA%\Ingenus\bridge\msal-cache.json`, and archive or delete the SharePoint site.
