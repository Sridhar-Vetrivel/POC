# AWS sandbox VM: step-by-step runbook for testing the hosted server (checklist 2.1)

**Status (11 Nov 2026): written for someone new to AWS; step A has been run, steps B to M have not.** Written for Sridhar (and Aditya) to follow with me. Commands marked **tested** were run on 11 Nov in WSL Ubuntu; everything else is **unverified until we run it**. Where I am unsure of a name, a screen label or a flag it says **verify**. AWS screens change: if a label differs a little, look for the closest one, and tell me what you see. Tags: **SAID** = someone stated it; **ASSUMED** = my reading; **UNKNOWN** = not known yet.

**Who does what.** Each step says who acts:
- **[YOU: Console]**: you click in the AWS web console (https://console.aws.amazon.com).
- **[YOU: VM terminal]**: you paste commands into the browser terminal of the VM (Session Manager, step D). I cannot reach that terminal.
- **[ME: laptop]**: I run it from this session, in your normal terminal. Read-only checks only, until you say go for a change.
- **[YOU: say go]**: I wait for your word before anything that creates, changes or costs.

## 0. Words you will meet (one line each)

| Word | What it is |
|---|---|
| **Account** | The AWS "tenant" your sandbox lives in. Everything is created inside one account |
| **Region** | A city where AWS runs machines, such as `ap-southeast-2` (Sydney). Most things are per region: always check the region name at the top right of the console |
| **EC2 instance** | One virtual machine (the "VM") |
| **Instance type** | The size of the VM, such as `t3.medium` (2 CPUs, 4 GB of memory). Bigger costs more per hour |
| **AMI** | The starting disk image (here: Ubuntu Linux) |
| **EBS volume** | The VM's disk |
| **Security group** | The VM's firewall: a list of who may connect to which port |
| **Elastic IP** | A fixed public address. Without one the public address changes every time the VM is stopped and started |
| **IAM role / instance profile** | A badge the VM wears that lets it use AWS services. Ours lets it be reached by Session Manager (and read one S3 bucket) |
| **SSM Session Manager** | A browser terminal into the VM, with no open port 22 and no SSH keys |
| **S3 bucket** | A cloud folder. We use one briefly to move the code to the VM |
| **Budget** | A spending limit with an email alarm |
| **Stop vs Terminate** | **Stop** switches the VM off (the disk stays and still costs a little). **Terminate** deletes the VM for good |

## 1. Decisions

| # | Decision | Answer so far |
|---|---|---|
| 1 | Account, profile, region | Default profile; its region is `ap-southeast-2` (Sydney). **The CLI session had expired, so the account is not confirmed.** Step B |
| 2 | OS | **Linux, Ubuntu LTS** (Sridhar, 11 Nov) |
| 3 | Size | Start with 4 GB of memory (`t3.medium`, **ASSUMED** enough for the server, Postgres and the embedding model; we measure in step L). **Verify** the type exists in the region |
| 4 | Budget | A small cap, VM stopped when idle (Sridhar, 11 Nov). **The number is still to be set** (ask Aditya). I have not looked up prices |
| 5 | HTTPS name | Ask Aditya for a domain (Sridhar, 11 Nov). Until it exists we test through a private tunnel (step J1) |
| 6 | Who may reach the VM | See section 2, rule 6: **a public certificate needs ports 80 and 443 open to the internet**, so "only my IP" does not work for HTTPS. Sign-in stays on |
| 7 | Data | **Synthetic only.** Check the Psiog AI policy before any file goes on the VM |

## 2. Ground rules

1. **I run no command that creates, changes or deletes anything in AWS without your "go" for that step.**
2. **Tag everything** `project=ingenus-poc`, `owner=sridhar`, `delete-after=<date>`. Teardown finds things by this tag.
3. **Nothing secret in the repo or in chat.** The certificate key is made on the VM and stays there. The Postgres password is made on the VM. No AWS access keys in any file.
4. **No real data.** Rule 9 of CLAUDE.md applies on the VM too.
5. **No AWS-only services in the code** (decision 0009). The VM is plain Linux, Postgres and a proxy.
6. **A correction to my first draft: an "only my IP" rule breaks free HTTPS.** The proxy (Caddy) gets its certificate from Let's Encrypt, whose servers must reach ports 80 and 443 on the VM. So those two ports must be open to the internet (`0.0.0.0/0`). This is acceptable only because the server refuses every call without a valid Entra token (checked in step I: it answers 401), the data is synthetic, and the VM is stopped when idle. If Aditya says no, the alternative is a load balancer with an AWS certificate (more cost, more steps): ask him. Port 22 is never opened.
7. **Stop the VM whenever you are not testing.** A forgotten VM is the main cost risk.

## 3. What we are building

```
second laptop (Claude Desktop + bridge) --HTTPS 443--> Caddy --> MCP server 127.0.0.1:8765 --> Postgres + pgvector (same VM)
                                                                      |--> Microsoft Graph (SharePoint, OneDrive) and Entra sign-in
```

The network-drive source cannot be reached from AWS, so it is not part of this test.

## 4. Steps

### A. Run the server on Linux in WSL first (free) — **DONE 11 Nov 2026**

[ME: laptop]. Result:

| Check | Result |
|---|---|
| Python | WSL Ubuntu 26.04 has Python 3.14, no pip, no `python3-venv`, and no sudo. Worked around with `python3 -m venv --without-pip`, `get-pip.py`, `pip install uv`, `uv python install 3.13`, `uv venv --python 3.13`, `uv pip install -e ".[meaning,dev]"` (**tested**). The same sequence works on the VM, with or without sudo |
| Test suite on Linux | **343 passed, 3 failed, 7 skipped** (6 need Node for the bridge; 1 depended on a Postgres password file that is git-ignored: with a dummy file all Postgres tests ran and passed) |
| The 3 failures | All the same cause: Windows drive paths (`C:/Windows/win.ini`, `C:/x.txt`) are **not refused on Linux**, because there they look like ordinary relative names. Files: `test_v1_graph_source.py`, `test_v1_multi_source.py`, `test_v1_network_source.py`. They end as "no such file", so nothing is read, but the guard that should refuse them before any request does not. **Fixed 11 Nov 2026 (not committed):** `core/scope.py` now refuses drive letters and rooted or network paths on every system; two new tests. **After the fix: 353 passed, 0 failed, 7 skipped on Linux, and the whole suite passes on Windows** |
| Server on Linux | Started, listened on 127.0.0.1, 10 tools listed, `resolve_customer` and `get_rebate_setup` (mock SAP) answered, the call log's hash chain verified (**tested**) |

### B. Sign in and confirm the account (read-only, then a budget)

1. **[YOU]** In your terminal (the PowerShell where `aws` works) run `aws login`. A browser opens. Sign in with the account your boss gave you for the TAC sandbox, and approve.
2. **[ME: laptop]** I run `aws sts get-caller-identity` and `aws configure get region`. **You should see:** an account number and a role name that match the TAC sandbox. **If it is not the sandbox, stop and tell Aditya.** Do not continue on a production account.
3. **[YOU: Console]** Create the budget. Search the console for **Billing and Cost Management** > left menu **Budgets** > **Create budget** > **Use a template (simplified)** > **Monthly cost budget** > enter a name `ingenus-poc-monthly`, the amount (the cap Aditya gives you), your email > **Create budget**. (Labels: **verify**; a sandbox may block budgets: if so, ask Aditya who owns cost limits.) **You should see:** the budget in the list.

### C. Make the VM's badge, firewall and a place for the code

1. **[YOU: Console] The role (badge).** Search **IAM** > **Roles** > **Create role** > Trusted entity type **AWS service** > Use case **EC2** > Next > search and tick **AmazonSSMManagedInstanceCore** > Next > Role name `ingenus-poc-ssm-role` > add tag `project=ingenus-poc` > **Create role**. **You should see:** the role listed. (AWS creates the matching instance profile of the same name when you use the EC2 use case: **verify** in step D that it appears in the list.)
2. **[YOU: Console] The firewall.** Search **EC2** > left menu **Security Groups** > **Create security group**. Name `ingenus-poc-sg`, description `Ingenus POC sandbox`, VPC: the default one. **Inbound rules** > **Add rule** twice: type **HTTP**, source **Anywhere-IPv4 (0.0.0.0/0)**; type **HTTPS**, source **Anywhere-IPv4**. **Do not add SSH.** Leave outbound as it is. Add the tag `project=ingenus-poc` > **Create security group**.
3. **[YOU: Console] The code bucket.** Search **S3** > **Create bucket** > a name that is unique (for example `ingenus-poc-transfer-<your-initials>-<random digits>`), region as in B, leave **Block all public access ON** > tag `project=ingenus-poc` > **Create bucket**. Write the exact name down; I call it `BUCKET` below.
4. **[YOU: Console] Let the VM read that one bucket.** **IAM** > **Roles** > `ingenus-poc-ssm-role` > **Add permissions** > **Create inline policy** > **JSON** tab, paste (replace `BUCKET`):

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::BUCKET/*"}]}
```

Name it `ingenus-poc-read-code` > **Create policy**.

### D. Launch the VM

1. **[YOU: say go]** Tell me you are about to launch, and the budget cap is set.
2. **[YOU: Console]** **EC2** > **Instances** > **Launch instances**. Check the region at the top right is the one from B.
   - **Name:** `ingenus-poc-sandbox`.
   - **Application and OS Images:** choose **Ubuntu**; pick the newest **Ubuntu Server LTS**, **64-bit (x86)**. (**Verify** the version shown; I will not guess an image id.)
   - **Instance type:** `t3.medium`.
   - **Key pair:** choose **Proceed without a key pair** (we use Session Manager, not SSH).
   - **Network settings** > **Edit**: **Auto-assign public IP: Enable**; **Select existing security group** > `ingenus-poc-sg`.
   - **Configure storage:** `30` GiB, type **gp3**; under **Advanced** set **Encrypted: Yes**.
   - **Advanced details** (expand): **IAM instance profile** = `ingenus-poc-ssm-role`; **Metadata version** = **V2 only (token required)**.
   - **Resource tags** > add `project=ingenus-poc`, `owner=sridhar`, `delete-after=<date>` for **Instances** and **Volumes**.
   - **Launch instance.**
3. Wait until **Instance state** is **Running** and **Status check** is **2/2 checks passed** (a few minutes).
4. **Connect.** Select the instance > **Connect** > tab **Session Manager** > **Connect**. If the button is grey, wait 2 to 5 minutes and refresh: the VM needs time to register. **You should see** a black browser terminal. **If it stays grey after 10 minutes:** the badge is missing or wrong (check step C1 and the instance's **Actions > Security > Modify IAM role**); tell me.
5. **[YOU: VM terminal]** Paste, then send me the output:

```bash
sudo -i
lsb_release -a | head -3
free -m | head -2
df -h / | tail -1
curl -s -m 5 -o /dev/null -w "outbound internet: %{http_code}\n" https://pypi.org
```

**You should see:** Ubuntu, about 4 GB of memory, about 29 GB of disk, and `outbound internet: 200`.

### E. Put the code on the VM

1. **[ME: laptop]** I make the archive from the committed code: `git archive --format=zip -o ingenus-poc.zip HEAD` (about 3 MB; it contains no secrets, because `.env` and `secrets/` are not in git).
2. **[ME: laptop]** I upload it with `aws s3 cp ingenus-poc.zip s3://BUCKET/ingenus-poc.zip`, after your go.
3. **[YOU: VM terminal]** (still as root):

```bash
apt-get update -y && apt-get install -y unzip curl git python3 ca-certificates
adduser --disabled-password --gecos "" ingenus
sudo -u ingenus bash -c 'mkdir -p /home/ingenus/app'
# the VM needs the AWS command-line tool to fetch the zip (the apt package may not exist on a new Ubuntu: then the snap is used)
apt-get install -y awscli || snap install aws-cli --classic
aws s3 cp s3://BUCKET/ingenus-poc.zip /tmp/ingenus-poc.zip
sudo -u ingenus unzip -q -o /tmp/ingenus-poc.zip -d /home/ingenus/app
ls /home/ingenus/app | head
```

**You should see:** `CLAUDE.md MCP-PlugIn MCP-Server README.md ... pyproject.toml`. **If `aws s3 cp` fails with access denied:** the policy in C4 has the wrong bucket name (**verify** it, and the instance profile).

4. **[YOU: VM terminal]** Install Python 3.13 and the server as the `ingenus` user (the same sequence that worked in WSL, **tested** there):

```bash
sudo -iu ingenus bash -c '
set -e
cd /home/ingenus/app
python3 -m venv --without-pip .boot
curl -fsSL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
.boot/bin/python /tmp/get-pip.py -q
.boot/bin/python -m pip install -q uv
.boot/bin/uv python install 3.13
.boot/bin/uv venv --python 3.13 .venv
.boot/bin/uv pip install --python .venv/bin/python -e ".[meaning]"
.venv/bin/python -c "import ingenus_mcp; print(\"import ok\", ingenus_mcp.__version__)"
'
```

**You should see:** `import ok 0.2.0`. It takes a few minutes. **If `python3 -m venv` fails** on the image: run `apt-get install -y python3-venv` as root and repeat.

### F. Postgres with pgvector

1. **[YOU: VM terminal]** (as root). Add the official PostgreSQL package source, then install Postgres 18 and pgvector. **Verify these lines against https://www.postgresql.org/download/linux/ubuntu/ first**; the page has the current commands. They look like:

```bash
apt-get install -y postgresql-common
/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
apt-get install -y postgresql-18 postgresql-18-pgvector
systemctl status postgresql --no-pager | head -3
```

**If the package source does not yet support this Ubuntu version** (possible for a brand-new release, **UNKNOWN**), use Ubuntu's own `postgresql` and `postgresql-NN-pgvector` packages instead (`apt-cache search pgvector` shows the names). **Write the outcome down: it is the first real answer to the open on-prem question "can pgvector be installed?" (decision 0009).**

2. **[YOU: VM terminal]** Make the database, a user with a generated password, and the extension:

```bash
sudo -iu ingenus bash -c 'mkdir -p /home/ingenus/app/MCP-Server/secrets && chmod 700 /home/ingenus/app/MCP-Server/secrets'
PW=$(openssl rand -hex 24)
sudo -u postgres psql -c "CREATE ROLE ingenus LOGIN PASSWORD '$PW';"
sudo -u postgres psql -c "CREATE DATABASE ingenus_audit OWNER ingenus;"
sudo -u postgres psql -d ingenus_audit -c "CREATE EXTENSION IF NOT EXISTS vector;"
printf '%s' "$PW" > /home/ingenus/app/MCP-Server/secrets/pg_password.txt
chown ingenus:ingenus /home/ingenus/app/MCP-Server/secrets/pg_password.txt && chmod 600 /home/ingenus/app/MCP-Server/secrets/pg_password.txt
unset PW
sudo -u postgres psql -d ingenus_audit -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
```

**You should see:** a row `vector | 0.x.x`. Do not paste the password anywhere.

### G. Certificate key and Entra

1. **[YOU: VM terminal]** Make a **new** key pair **on the VM** (never copy the laptop's key). This is the same method as [developer_guide.md](../developer_guide.md#L131) (5.1), with a 180-day certificate:

```bash
sudo -iu ingenus bash -c '
cd /home/ingenus/app/MCP-Server/secrets
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 180 -keyout server_key.pem -out server_cert.pem -subj "/CN=ingenus-poc-sandbox"
chmod 600 server_key.pem
openssl x509 -in server_cert.pem -outform DER -out ingenus-poc-sandbox.cer
openssl x509 -in server_cert.pem -noout -fingerprint -sha1
'
```

2. **Send me the fingerprint** (the `SHA1 Fingerprint=...` line; it is not a secret). Remove the colons for the setting.
3. **Get the public `.cer` file to your laptop** without the private key: in the VM terminal run `base64 -w0 /home/ingenus/app/MCP-Server/secrets/ingenus-poc-sandbox.cer` and paste the output to me; I decode it into a `.cer` file on your laptop (it is a public certificate).
4. **[YOU: Console, Entra admin center, the dev tenant]** App registrations > **Ingenus POC MCP Server** > **Certificates & secrets** > **Certificates** > **Upload certificate** > choose the `.cer`. **You should see:** a new row whose thumbprint equals the fingerprint (colons removed). **Undo (teardown):** delete that row.

### H. Settings and the service

1. **Get the values from your laptop file** `MCP-Server\.env` (open it yourself; do not paste secrets): `INGENUS_TENANT_ID`, `INGENUS_SERVER_CLIENT_ID`, `INGENUS_SP_SITE_URL`, `INGENUS_SP_FOLDER`, `INGENUS_OD_FOLDER`. Do **not** copy the certificate lines or the Postgres lines: the VM has its own.
2. **[YOU: VM terminal]** Create the settings file (as root) with your values in place of the `<...>` markers (`<FINGERPRINT>` is from G, without colons). `INGENUS_PUBLIC_URL` stays a placeholder until the domain exists:

```bash
mkdir -p /etc/ingenus
cat > /etc/ingenus/ingenus.env <<'EOF'
INGENUS_NO_ENV_FILE=1
INGENUS_AUTH=entra
INGENUS_TENANT_ID=<tenant id>
INGENUS_SERVER_CLIENT_ID=<server app id>
INGENUS_CERT_KEY_FILE=secrets/server_key.pem
INGENUS_CERT_THUMBPRINT=<FINGERPRINT>
INGENUS_PUBLIC_URL=http://127.0.0.1:8765/mcp
INGENUS_SOURCES=sharepoint,onedrive
INGENUS_SP_SITE_URL=<site url>
INGENUS_SP_FOLDER=<folder>
INGENUS_OD_FOLDER=<folder>
INGENUS_PG_HOST=127.0.0.1
INGENUS_PG_PORT=5432
INGENUS_PG_DB=ingenus_audit
INGENUS_PG_USER=ingenus
INGENUS_PG_PASSWORD_FILE=secrets/pg_password.txt
INGENUS_EMBED_MODEL=nomic
INGENUS_SAP_ADAPTER=mock
EOF
chmod 600 /etc/ingenus/ingenus.env
```

(`INGENUS_NO_ENV_FILE=1` stops the server reading any `.env`. The names are from the developer guide settings table; **verify** the port with `sudo -u postgres psql -c "SHOW port;"`: it is normally 5432.)

3. **Fetch the embedding model once** (the server never downloads while running; it needs outbound internet):

```bash
sudo -iu ingenus bash -c 'cd /home/ingenus/app && set -a && . /etc/ingenus/ingenus.env 2>/dev/null; set +a; .venv/bin/python -m ingenus_mcp.embeddings fetch && .venv/bin/python -m ingenus_mcp.embeddings status'
```

If the `ingenus` user cannot read `/etc/ingenus/ingenus.env` (mode 600, root), run the two `embeddings` commands with `INGENUS_EMBED_MODEL=nomic` typed on the command line instead.

4. **Make it a service** (as root):

```bash
cat > /etc/systemd/system/ingenus-mcp.service <<'EOF'
[Unit]
Description=Ingenus MCP server (POC, sandbox)
After=network-online.target postgresql.service

[Service]
User=ingenus
WorkingDirectory=/home/ingenus/app
EnvironmentFile=/etc/ingenus/ingenus.env
ExecStart=/home/ingenus/app/.venv/bin/python -m ingenus_mcp.server --host 127.0.0.1 --port 8765
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now ingenus-mcp
sleep 5; systemctl status ingenus-mcp --no-pager | head -8
curl -s -o /dev/null -w "local answer: %{http_code}\n" http://127.0.0.1:8765/mcp
```

**You should see:** `active (running)` and `local answer: 401` (sign-in is on, and the call has no token). **If it is `failed`:** run `journalctl -u ingenus-mcp -n 30 --no-pager` and send me the last lines (remove nothing secret: the log has none).

### I. HTTPS in front (needs the domain; skip until Aditya gives one)

1. **[YOU]** Get from Aditya: the domain name (for example `poc.<something>`) and who adds the DNS record.
2. **[YOU: Console]** **EC2** > **Elastic IPs** > **Allocate Elastic IP address** > tag `project=ingenus-poc` > **Allocate** > select it > **Actions > Associate Elastic IP address** > choose the instance > **Associate**. Write the address down.
3. **[YOU or Aditya]** Create an **A record** `<domain> -> <that elastic IP>`. Check later with `nslookup <domain>`.
4. **[YOU: VM terminal]** Install Caddy (**verify** against https://caddyserver.com/docs/install#debian-ubuntu-raspbian; the lines there are the current ones), then:

```bash
cat > /etc/caddy/Caddyfile <<'EOF'
<domain> {
    reverse_proxy 127.0.0.1:8765
}
EOF
systemctl restart caddy; sleep 10; systemctl status caddy --no-pager | head -5
```

5. In `/etc/ingenus/ingenus.env` change `INGENUS_PUBLIC_URL` to `https://<domain>/mcp`, then `systemctl restart ingenus-mcp`.
6. **[ME: laptop]** From your laptop: `curl -s -o /dev/null -w "%{http_code}" https://<domain>/mcp`. **You should see:** `401` (not a certificate error, not 200). **Also verify:** the SDK's host-header protection must accept the VM's name. This is **UNKNOWN and untested**. If you see a 4xx **other than 401** (for example 403 or 421) while step H4's local answer was 401, that is the symptom; send me the response and we look in the SDK for its allowed-hosts setting.

### J. Smoke test

**J1. Without a domain (private tunnel):** **[YOU]** Install the **Session Manager plugin** on your laptop (search "Session Manager plugin install Windows" in the AWS docs; one-time). Then in your terminal: `aws ssm start-session --target <instance id> --document-name AWS-StartPortForwardingSession --parameters "portNumber=8765,localPortNumber=8765"` and leave it open. The VM's server now appears at `http://127.0.0.1:8765/mcp` on your laptop (loopback, so the bridge accepts plain `http`). Close your local server first so the port is free. **This tests everything except HTTPS and the host-header check.**

**J2. With the domain:** **[ME: laptop]** `scripts/signin_check.py` against the VM; then on the **second laptop**, install the bridge as in the README (Server URL = `https://<domain>/mcp`, plus Tenant ID, Desktop client app ID and Server app ID). First chat opens a browser: sign in with a tenant account. Ask Q1: "Check Chain A against SAP as of 31 Aug 2026." **You should see:** 1,800.00 and 12,600.00, and the log on the VM names the signed-in person: `sudo tail -n 5 /home/ingenus/app/MCP-Server/data/runtime/tool_calls.jsonl` (**verify** the log path with `ls` if it differs).

### K. The QA the VM exists for (Systems Designer, 21 Oct: multiple users and the logging)

| # | Do | Done when |
|---|---|---|
| K1 | Two people (or sessions) check different customers at the same time (needs the second laptop and person) | Both get correct figures; each call is logged under the right name |
| K2 | Login events: accepted, and refused (a wrong or expired token) | Both appear in the log and in Postgres |
| K3 | On the VM: `sudo -iu ingenus bash -c 'cd /home/ingenus/app && set -a && . /etc/ingenus/ingenus.env; set +a; .venv/bin/python -m ingenus_mcp.audit verify'` (**verify** the options with `--help`) | The hash chain is intact after concurrent writes |
| K4 | Compare the log's line count with the Postgres `events` table | Same count, no duplicate hashes |
| K5 | `audit ship` and `prune` against the VM's database; check history across two people | The second person sees the first person's check only for files they can open |
| K6 | Run the dashboard on the VM (loopback only) and view it through a tunnel (as J1, port 8766) | Totals match the log. **Never open port 8766 in the security group** |

### L. Measure and write down (we have none of these today)

On the VM: memory and CPU of the server while idle and during a check (`free -m`, `ps -o rss,cmd -C python`, `top -b -n1 | head -15`); disk used (`df -h /`); time to restart (`systemctl restart ingenus-mcp` and time to the first answer). From the laptop: first-call and warm-call times; whether Claude Desktop times out on a slow first call. Write each in section 8. **Do not treat a load run over the internet as a capacity result.**

### M. Stop and teardown (do this every session, and in full when finished)

- **Idle:** **[YOU: Console]** **EC2** > select the instance > **Instance state** > **Stop instance**. (An Elastic IP that is not attached to a running VM costs a little: release it if you will be away for days.)
- **Finished:** **Instance state > Terminate**; then delete: the **EBS volume** (if it remains), the **Elastic IP** (**Release**), the **security group**, the **S3 bucket** (empty it, then delete), the **IAM role** `ingenus-poc-ssm-role`, the **budget** if it is ours, and the **DNS record**. **Delete the test certificate row in Entra.**
- **Check nothing is left [ME: laptop, read-only]:** `aws ec2 describe-instances`, `describe-volumes`, `describe-addresses` and `aws s3 ls`, filtered by or looking for the `project=ingenus-poc` tag. Check **Cost Explorer** the next day.
- **Never leave the VM running overnight** unless the budget alarm exists and you have said so.

## 5. What this proves, and what it does not

**Proves (if it passes):** the server runs on Linux; pgvector installs from packages; HTTPS and the host-header check work with a real name; a second laptop signs in and gets the same figures; concurrent users are logged correctly on a real host; real memory and time numbers.

**Does not prove:** the network drive (not reachable from AWS); the Principal Architect's VM (a different account, OS and network); Ingenus's on-prem server (OS and Postgres UNKNOWN); real SAP, real contracts or any policy question; capacity.

## 6. Risks

| Risk | What we do |
|---|---|
| A forgotten VM or disk costs money | Budget alarm, tags, "stop when idle", step M |
| Wrong account | Step B stops the run if it is not the sandbox |
| Ports 80 and 443 open to the world | Sign-in on (401 without a token), synthetic data only, stop when idle; port 22 and 8766 never open |
| Key or password leaks | Made on the VM, mode 600, never in the repo or chat; delete the Entra certificate at the end |
| Policy: files on AWS | Decision 7 |
| Linux surprises | Step A found one (Windows paths); the rest we meet on the VM |
| My commands are untested on this image | Each step shows what you should see; tell me when it differs and stop |

## 7. Inputs needed

| # | What | From |
|---|---|---|
| D1 | A domain and a DNS record (or permission to use a temporary name); also whether 80 and 443 may be open (rule 6) | Aditya |
| D2 | The monthly budget cap | Aditya |
| D3 | May synthetic contracts sit on this VM under the Psiog AI policy? | Psiog AI policy, Aditya |
| D4 | A second person and laptop with their own Claude account (also unlocks TP-4, TP-5, TP-9 and TP-12) | Sridhar |
| D5 | ~~The small fix in the path guard for Windows-style paths on Linux~~ | Done 11 Nov 2026 (Sridhar said do it); uncommitted |

## 8. Results (fill in as we go)

| Step | Result | Date |
|---|---|---|
| A, server on Linux (WSL) | 343 passed, 3 failed (Windows paths), 7 skipped; after the path-guard fix 353 passed, 0 failed, 7 skipped; server runs, 10 tools, chain intact | 11 Nov 2026 |
| B, account and region | `aws login` done; account **089020215064**, IAM user `sridhar.vetrivel` in groups `Administrators` and `Bedrock-POC`; region `ap-southeast-2`. **Not yet confirmed as the TAC sandbox** (no account alias; no EC2 instances in the region; two existing budgets, `My Monthly Cost Budget` 100 and `da-monthly` 60; the groups date from 2022 and 2024). Waiting for Sridhar to confirm with Aditya | 11 Nov 2026 |
| D, VM running; Session Manager connects | | |
| E, code and Python 3.13 on the VM | | |
| F, pgvector installed from packages | | |
| H, service running; local answer 401 | | |
| I, HTTPS and host-header check with a real name | | |
| J, second laptop signs in | | |
| K1 to K6 | | |
| L, memory and times | | |
| M, teardown confirmed | | |

Related: [v1_open_items_checklist.md](v1_open_items_checklist.md) (2.1), [decision 0009](decisions/0009-v1-poc-vm-on-aws-provisioned-by-principal-architect.md), [developer_guide.md](../developer_guide.md), [release_v1.1.md](release_v1.1.md).
