# Ingenus POC: steps for Psiog IT

Short checklist. Background and reasons are in `psiog_it_request_v1-4_v1-6.md`.
All data is synthetic. Everything is read-only. Needed for about six weeks.

Users: Sridhar Vetrivel, Aditya Manthena, and up to two testers (names to follow).

## Step 1. Create the server app (Entra admin center > App registrations > New registration)

1. Name: `Ingenus POC MCP Server`. Account type: this directory only. No redirect URI.
2. **Expose an API:** keep the default Application ID URI (`api://<client-id>`).
3. Add a scope: name `access_as_user`, who can consent: **Admins only**, state: Enabled.
4. **Manifest:** set the access token version to 2 (`requestedAccessTokenVersion: 2`; please confirm the field name in the portal).
5. **API permissions > Microsoft Graph > Delegated:** `User.Read`, `Files.Read.All`, `Sites.Read.All`.
   (Stricter option: delegated `Sites.Selected` for the `INGENUS` site only. Tell us which you choose.)
6. Click **Grant admin consent**.
7. **Certificates & secrets > Certificates:** upload the `.cer` we send you. No client secret.

## Step 2. Create the desktop client app

1. Name: `Ingenus POC Desktop Client`. Account type: this directory only.
2. Redirect URI: platform **Public client/native**, `http://localhost`.
3. **Authentication:** Allow public client flows = **Yes**.
4. **API permissions > My APIs:** `Ingenus POC MCP Server` > Delegated > `access_as_user`. **Grant admin consent.**
5. Go back to the server app > Expose an API > **Authorized client applications:** add this app's client ID for `access_as_user`.

## Step 3. Limit who can sign in

1. Create a security group, for example `SG-Ingenus-POC`, with the named users.
2. For **both** apps: Enterprise applications > the app > Properties > **Assignment required = Yes**.
3. Users and groups > assign the group.

## Step 4. SharePoint

1. Add the named users as **members** of `https://psiog0.sharepoint.com/sites/INGENUS` (read access is enough).
2. Confirm it is acceptable that the site name contains the client's name.
3. If you chose `Sites.Selected` in step 1: grant the server app read access to this site only.

## Step 5. VM

| Item            | Request                                                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Size            | 2 vCPU, 4 GB RAM, 40 GB disk                                                                                                                   |
| OS              | Windows Server 2022 (or Ubuntu 24.04)                                                                                                          |
| Inbound         | TCP 443 from the office network and VPN only. Nothing from the internet                                                                        |
| Outbound        | HTTPS 443 to `login.microsoftonline.com`, `graph.microsoft.com`, `pypi.org`, `files.pythonhosted.org` (or give us your package mirror) |
| Software        | Python 3.13                                                                                                                                    |
| Access          | Remote desktop or SSH for Sridhar                                                                                                              |
| DNS             | An internal name, for example `ingenus-poc.psiog.local`                                                                                      |
| Service account | One account the server runs as. No admin rights after setup                                                                                    |

## Step 6. HTTPS certificate for the VM's DNS name

Choose one and tell us which:

1. A certificate from a **publicly trusted CA** for a Psiog-owned name (preferred; nothing changes on laptops).
2. A certificate from the internal CA, **plus** the internal root certificate (`.cer`) sent to us.

Reason: the client runs on Node.js, which does not trust an internal CA by default.

## Step 7. Send back to us (email or Teams)

- [ ] Tenant ID
- [ ] Server app: client ID and Application ID URI
- [ ] Desktop client app: client ID
- [ ] Which Graph permissions were granted (step 1.5 option)
- [ ] Confirmation the `.cer` is uploaded (or the thumbprint of the one you issued)
- [ ] Security group name and members
- [ ] VM hostname, IP, OS and how to connect
- [ ] Certificate option from step 6 (and the root `.cer` if option 2)
- [ ] Any policy step you need us to follow

## Step 8. At the end

Delete both app registrations and the group, delete or wipe the VM, archive or delete the `INGENUS` site.

## Order, if you want to do it in stages

1. Steps 1 to 4 first. They are enough for us to start reading SharePoint.
2. Steps 5 and 6 next. They are needed to host the server and for HTTPS.
