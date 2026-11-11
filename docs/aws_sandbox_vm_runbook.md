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
| 1 | Account, profile, region | **Confirmed 11 Nov 2026:** the console header shows `TACSandbox (089020215064)`, the same number the CLI reports; region Asia Pacific (Sydney), `ap-southeast-2` |
| 2 | OS | **Linux, Ubuntu LTS** (Sridhar, 11 Nov) |
| 3 | Size | Start with 4 GB of memory (`t3.medium`, **ASSUMED** enough for the server, Postgres and the embedding model; we measure in step L). **Verify** the type exists in the region |
| 4 | Budget | **No AWS Budget (Sridhar, 11 Nov 2026).** A budget made from the template counted the whole shared account (15.81 spent of 15 on the day it was made), so `ingenus-poc-monthly` was deleted. Cost control is: the VM is on only for second-person testing (a few days), every session starts with `sudo shutdown -h +120`, the VM is stopped when idle, and our cost is read on demand with the commands in section 2d (filtered by Sydney usage types, because cost allocation tags cannot be activated in this account). Prices were read from AWS on 11 Nov (section 2a) |
| 5 | HTTPS name | **A temporary name is enough (Sridhar, 11 Nov).** The AWS-provided `ec2-...amazonaws.com` name will not get a free certificate (section 2c). Plan: steps A to H and J1 (tunnel, no name needed) first; register a cheap domain (about 3 USD a year) only when the second-person test needs HTTPS |
| 6 | Who may reach the VM | See section 2, rule 6: **a public certificate needs ports 80 and 443 open to the internet**, so "only my IP" does not work for HTTPS. Sign-in stays on |
| 7 | Data | **Synthetic only.** Sridhar confirmed on 11 Nov that synthetic contracts may sit on this VM under the Psiog AI policy |

## 2. Ground rules

1. **I run no command that creates, changes or deletes anything in AWS without your "go" for that step.**
2. **Tag everything** `project=ingenus-poc`, `owner=sridhar`, `delete-after=<date>`. Teardown finds things by this tag.
3. **Nothing secret in the repo or in chat.** The certificate key is made on the VM and stays there. The Postgres password is made on the VM. No AWS access keys in any file.
4. **No real data.** Rule 9 of CLAUDE.md applies on the VM too.
5. **No AWS-only services in the code** (decision 0009). The VM is plain Linux, Postgres and a proxy.
6. **A correction to my first draft: an "only my IP" rule breaks free HTTPS.** The proxy (Caddy) gets its certificate from Let's Encrypt, whose servers must reach ports 80 and 443 on the VM. So those two ports must be open to the internet (`0.0.0.0/0`). This is acceptable only because the server refuses every call without a valid Entra token (checked in step I: it answers 401), the data is synthetic, and the VM is stopped when idle. Section 2b explains this with an example. If it is not acceptable, the alternative is a load balancer with an AWS certificate (more cost, more steps). Port 22 is never opened.
7. **Stop the VM whenever you are not testing.** A forgotten VM is the main cost risk.

## 2a. What it will cost (prices read from AWS for Sydney, on demand, USD, on 11 Nov 2026)

| Item | Price | Notes |
|---|---|---|
| VM `t3.medium` (Linux), while running | **0.0528 per hour** | `t3.small` is 0.0264, `t3.large` 0.1056 |
| Public IPv4 address, while in use | 0.005 per hour | Charged for the VM's ordinary public address too |
| Disk, gp3, 30 GB | **0.096 per GB-month = 2.88 a month** (about 0.10 a day) | Charged **even while the VM is stopped**, until the disk is deleted |
| Elastic IP, if we use one | 0.005 per hour, **always** (in use or idle) = 0.12 a day | Release it when finished; stopping the VM does not stop this charge |
| A domain in Route 53, `.click` | 3 a year (`.link` 5, `.com` 16) | Prices from Route 53; a non-refundable purchase. A hosted zone also costs about 0.50 a month (**not verified**) |
| Session Manager, a few MB in S3 | about nothing | Not itemised |
| Data going out to the internet | **not priced here** | Expected to be tiny for a POC |

**What that means in practice**
- **One 2-hour session:** about 0.12 (VM 0.11 plus its address 0.01).
- **A test week of 5 sessions:** about 0.6 for the VM, plus 0.7 for the disk.
- **A two-week round** (6 sessions, disk kept, Elastic IP kept, a `.click` domain): about 7 in all. That is the size of the whole round; there is no budget alarm.
- **Worst case, VM left on for a month by mistake:** about 44 (41.6 for the VM and its address, 2.9 for the disk). The `shutdown -h +120` safety net limits a forgotten session to about 0.12.
- **No AWS Budget is used** (deleted 11 Nov 2026), so nothing warns you if the VM is left on. About 44 would be the worst case for a month.

## 2b. Rule 6 explained: ports 80 and 443, with an example

A **port** is a numbered door on the VM. **443** is the door for HTTPS: Claude Desktop on the second laptop knocks there. **80** is the door a certificate authority (Let's Encrypt) knocks on once, to check that the name really points at us before it issues the free certificate. The **security group** is the list at those doors saying who may come in.

**Example.** You are at home (address A), the tester is at the office (address B), and Let's Encrypt's checking computers are somewhere in the world (address C).
- **List says "only A and B":** you and the tester get in. Let's Encrypt (C) is turned away, so **there is no certificate**. Claude Desktop refuses plain `http` to another machine, so the second-person test cannot run.
- **List says "everyone" for 80 and 443:** Let's Encrypt gets in, the certificate is issued, and the tester connects from any network. **Strangers can also reach the door.** What they find is the server answering "who are you?" (401) to everything, because every call needs a valid Entra token. Port 22 and the dashboard port stay closed.

**What the opening costs us:** the VM will be seen by internet scanners. They cannot call a tool without a token, but they can fill our login log with refused attempts, and any flaw in the server software would be exposed. For a POC that is on for a few hours with synthetic data, behind sign-in, that is a reasonable trade.

**My recommendation:** open 80 and 443 to everyone **only while the VM is on** (it is stopped otherwise). After the certificate is issued, remove the rule for 80 (HTTPS needs only 443; renewals, due after about 60 days, are not in play for a few days). Locking 443 to the testers' addresses is not practical, because home and office addresses change.

## 2c. The temporary name

- **Not possible:** the name AWS gives every VM (`ec2-1-2-3-4.ap-southeast-2.compute.amazonaws.com`). Let's Encrypt does not issue certificates for it (older forum posts, 2019 and 2023; I did not check Let's Encrypt's own policy page). See [this community answer](https://community.letsencrypt.org/t/how-to-install-an-ssl-certificate-on-an-aws-ec2-instance/202218.md) and [Caddy's automatic HTTPS page](https://caddyserver.com/docs/automatic-https), which says a public name needs your own DNS record pointing at the server and ports 80 and 443 reachable.
- **Not recommended:** free "wildcard DNS" names from third parties. I could not confirm they work with Let's Encrypt, and they add an outside dependency.
- **Recommended:** a cheap domain from Route 53 (`.click`, about 3 a year), a record pointing at an Elastic IP, used only when the second-person test needs it. **Until then, steps A to H and J1 (the private tunnel) need no name and no cost.** Registering a domain is a purchase that needs your explicit go. Route 53 asks for contact details and sends a verification email (a registrant who does not confirm in time can lose the name: **verify** the period in Route 53).

## 2d. Cheat codes: switch the VM on and off to save money

**Written, not yet run** (the VM does not exist yet). Run these in your PowerShell terminal after `aws login`. Or tell me "start the VM" or "stop the VM" and I run them for you (they change the VM's state, so I wait for your word).

**Set two variables once per terminal window** (the instance id appears after step D; it looks like `i-0123456789abcdef0`):

```powershell
$R = "ap-southeast-2"
$IID = "i-PASTE-YOUR-INSTANCE-ID"
```

| I want to | Command |
|---|---|
| **See the state** (running, stopped) and the public address | `aws ec2 describe-instances --region $R --instance-ids $IID --query "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress]" --output text` |
| **Find the id** if you lost it (looks for our tag) | `aws ec2 describe-instances --region $R --filters "Name=tag:project,Values=ingenus-poc" --query "Reservations[].Instances[].[InstanceId,State.Name]" --output text` |
| **Turn OFF** (stop: no compute charge, the disk and data stay) | `aws ec2 stop-instances --region $R --instance-ids $IID` |
| **Wait until it is really off** | `aws ec2 wait instance-stopped --region $R --instance-ids $IID` |
| **Turn ON** | `aws ec2 start-instances --region $R --instance-ids $IID` |
| **Wait until it is on and healthy** (a few minutes) | `aws ec2 wait instance-running --region $R --instance-ids $IID; aws ec2 wait instance-status-ok --region $R --instance-ids $IID` |
| **Turn OFF everything of ours that is running** (a safety sweep) | `aws ec2 describe-instances --region $R --filters "Name=tag:project,Values=ingenus-poc" "Name=instance-state-name,Values=running" --query "Reservations[].Instances[].InstanceId" --output text` shows the ids; stop each with the Turn OFF line |

**After you turn it on**
1. The server, Postgres and Caddy start by themselves (the service is set to start at boot in step H). Check from the VM terminal: `systemctl is-active ingenus-mcp postgresql caddy` should print `active` three times (no `caddy` line until step I).
2. **The public address changes** each time unless you attached an Elastic IP (step I2). With the domain pointed at an Elastic IP nothing else changes. Without one, the address from the first table row is the new one; the tunnel in J1 is not affected because it goes through Session Manager.
3. Session Manager takes a minute or two to reconnect after the VM starts.

**Cost commands: see what our resources cost** (PowerShell; set `$R` and `$IID` first, as above)

**Why not by tag:** cost allocation tags can only be activated by the organisation's payer account, and this account got "Access denied" on 11 Nov 2026. So the tag `project` cannot be used in cost reports. **Instead we filter by usage type.** Everything we create is in Sydney, and Sydney usage types start with `APS2-`. The other `t3.medium` usage in this account (about 4.35 USD this month) has no such prefix (`BoxUsage:t3.medium`), which means N. Virginia, so it is not counted. This holds only while nobody else runs things in Sydney: check with `aws ec2 describe-instances --region $R --query "Reservations[].Instances[].[InstanceId,State.Name]" --output text` (it should list only our VM).

Each Cost Explorer call costs about 0.01 USD, and billing data can be up to 24 hours late, so a session shows up the next day.

| I want to | Command |
|---|---|
| **1. One-time: write the filter file** (our Sydney usage types) | `@'`<br>`{"Dimensions":{"Key":"USAGE_TYPE","Values":["APS2-BoxUsage:t3.medium","APS2-EBS:VolumeUsage.gp3","APS2-PublicIPv4:InUseAddress","APS2-PublicIPv4:IdleAddress","APS2-TimedStorage-ByteHrs"]}}`<br>`'@ \| Set-Content -Path "$env:USERPROFILE\ingenus-ce-filter.json" -Encoding ascii` |
| **2. Our cost this month so far** (a single number) | `$S=(Get-Date -Day 1).ToString("yyyy-MM-dd"); $E=(Get-Date).AddDays(1).ToString("yyyy-MM-dd"); aws ce get-cost-and-usage --time-period Start=$S,End=$E --granularity MONTHLY --metrics UnblendedCost --filter file://$env:USERPROFILE\ingenus-ce-filter.json --query "ResultsByTime[].[TimePeriod.Start,Total.UnblendedCost.Amount]" --output text` |
| **3. The same, split by item** (VM, disk, address, bucket) | `aws ce get-cost-and-usage --time-period Start=$S,End=$E --granularity MONTHLY --metrics UnblendedCost --filter file://$env:USERPROFILE\ingenus-ce-filter.json --group-by Type=DIMENSION,Key=USAGE_TYPE --query "ResultsByTime[].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]" --output text` |
| **4. This session so far** (an estimate from the launch time; only while the VM is running) | `$t = aws ec2 describe-instances --region $R --instance-ids $IID --query "Reservations[0].Instances[0].[State.Name,LaunchTime]" --output text; $state,$launch = $t -split "\s+"; if ($state -eq "running") { $h = ((Get-Date).ToUniversalTime() - [datetime]::Parse($launch).ToUniversalTime()).TotalHours; "{0:N1} h running, about {1:N2} USD so far" -f $h, ($h*0.0578) } else { "VM is $state" }` |
| **5. What still costs money while the VM is stopped** (our disks and addresses) | `aws ec2 describe-volumes --region $R --filters "Name=tag:project,Values=ingenus-poc" --query "Volumes[].[VolumeId,Size,State]" --output text; aws ec2 describe-addresses --region $R --filters "Name=tag:project,Values=ingenus-poc" --query "Addresses[].[PublicIp,AssociationId]" --output text` |

- **Status (11 Nov 2026):** commands 1, 2 and 5 ran against the account now (nothing of ours exists yet, so they returned 0 and nothing). The calculation in 4 was tested with a made-up launch time. Command 3 and all of them against a **real** VM are **not tested yet**.
- **Reading command 4:** the launch time resets each time the VM is started, so it shows the current session only. The price used is 0.0528 for the VM plus 0.005 for its address, per hour (section 2a).
- **Reading command 5:** every line listed is a charge that continues while the VM is stopped (the disk about 0.10 USD a day, an Elastic IP 0.12 a day). Empty means nothing is accruing.
- To see an earlier month, change `$S` and `$E`.

**A safety net on the VM so it can never run all night (optional, on the VM terminal)**
- **Run `sudo shutdown -h +120` at the start of every session, as the first command.** It switches the VM off in 2 hours (this **stops** it, because the default for "shutdown behavior" is Stop: **verify** it says Stop under **Advanced details** when you launch in step D).
- `sudo shutdown -c` cancels it if you need longer; run `sudo shutdown -h +120` again for another 2 hours.
- Starting the VM again later does **not** repeat it: run it every time.

**What stopping does and does not save** (I have not looked up prices)
- A stopped VM stops the compute charge. **The disk (EBS) still costs a little**, and an **Elastic IP still costs a little** while it exists: release it if you will be away for days (step M).
- **Stopping is not deleting.** Use Terminate (step M) only when finished.
- Each time before you leave: run the state command in row 1 and check it says `stopped`.

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
3. **Budget: not used (decided 11 Nov 2026).** The account's budgets count everything in the shared account, so a budget would not show what our VM costs. **Cost allocation tags cannot be used either:** they are managed by the organisation's payer account, and activating one gave "Access denied" here. To see what our resources cost, use the cost commands in section 2d (they filter by Sydney usage types). The two existing budgets (`My Monthly Cost Budget`, `da-monthly`) are not ours: do not touch them.

### C. Make the VM's badge, firewall and a place for the code

**Before every console step, read the region at the top right: it must say Asia Pacific (Sydney) `ap-southeast-2`.** On 11 Nov 2026 the console was on US East (N. Virginia): the security group was created there by mistake (found by a read-only check) and the S3 screen also showed `us-east-1`. Security groups, buckets and VMs belong to one region. The IAM role is global, so the region does not matter for C1. Opening Billing or IAM can switch the region shown, so check again each time.

1. **[YOU: Console] The role (badge).** Search **IAM** > **Roles** > **Create role** > Trusted entity type **AWS service** > Use case **EC2** > Next > search and tick **AmazonSSMManagedInstanceCore** > Next > Role name `ingenus-poc-ssm-role` > add tag `project=ingenus-poc` > **Create role**. **You should see:** the role listed. (AWS creates the matching instance profile of the same name when you use the EC2 use case: **verify** in step D that it appears in the list.)
2. **[YOU: Console] The firewall.** Search **EC2** > left menu **Security Groups** > **Create security group**. Name `ingenus-poc-sg`, description `Ingenus POC sandbox`, VPC: the default one. **Inbound rules** > **Add rule** twice: type **HTTP**, source **Anywhere-IPv4 (0.0.0.0/0)**; type **HTTPS**, source **Anywhere-IPv4**. **Do not add SSH.** Leave outbound as it is. Add the tag `project=ingenus-poc` > **Create security group**.
3. **[YOU: Console] The code bucket.** Search **S3** > **Create bucket** > a name that is unique (for example `ingenus-poc-transfer`), region as in B, leave **Block all public access ON** > tag `project=ingenus-poc` > **Create bucket**. Write the exact name down; I call it `BUCKET` below.
4. **[YOU: Console] Let the VM read that one bucket.** **IAM** > **Roles** > `ingenus-poc-ssm-role` > **Add permissions** > **Create inline policy** > **JSON** tab, paste (replace `BUCKET`):

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::BUCKET/*"}]}
```

Name it `ingenus-poc-read-code` > **Create policy**.

### D. Launch the VM

1. **[YOU: say go]** Tell me you are about to launch, and the budget cap is set.
2. **[YOU: Console]** **EC2** > **Instances** > **Launch instances**. Check the region at the top right is the one from B.
   - **Name:** `ingenus-poc-sandbox`.
   - **Application and OS Images:** choose **Ubuntu**; pick **Ubuntu Server 24.04 LTS**, **64-bit (x86)**. (Checked read-only on 11 Nov 2026: Canonical's images in this region are 24.04 LTS (`noble`), 26.04 LTS (`resolute`) and 26.10 (not an LTS). I recommend 24.04: it is mature, and the PostgreSQL package source surely supports it, which is not certain for 26.04 yet. The WSL test used 26.04, but our Python setup does not depend on the system Python. **Verify** the name shown on screen matches.)
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

### I. HTTPS in front (needs a domain name; skip until the second-person test needs HTTPS)

1. **[YOU: say go, then Console]** Register a cheap domain (a purchase: section 2c). **Route 53** > **Registered domains** > **Register domains** > type a name such as `ingenus-poc-<your initials>` and pick `.click` (about 3 USD a year, the price Route 53 showed me) > add to cart > fill in the contact details > purchase. Confirm the verification email within the time it states. Route 53 makes a **hosted zone** for the domain by itself.
2. **[YOU: Console]** **EC2** > **Elastic IPs** > **Allocate Elastic IP address** > tag `project=ingenus-poc` > **Allocate** > select it > **Actions > Associate Elastic IP address** > choose the instance > **Associate**. Write the address down.
3. **[YOU: Console]** **Route 53** > **Hosted zones** > your domain > **Create record**: leave the name empty (or `poc`), type **A**, value the Elastic IP > **Create records**. Check later with `nslookup <domain>` (it can take a few minutes). Use that name as `<domain>` below.
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
7. **[YOU: Console] Close port 80 once the certificate is issued** (agreed 11 Nov 2026). Step 6 answering `401` over `https` proves the certificate works. **EC2** > **Security Groups** > `ingenus-poc-sg` > **Inbound rules** > **Edit inbound rules** > delete the **HTTP (80)** row > **Save rules**. Leave **HTTPS (443)** as it is. **You should see:** `https://<domain>/mcp` still answers `401`. Open 80 again only if Caddy needs to renew (after about 60 days, so not in a few-day test) or the VM gets a new Elastic IP and a new certificate is needed.

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
- **Never leave the VM running overnight.** There is no budget alarm (decided 11 Nov 2026), so the 2-hour shutdown and your own check of the VM state (section 2d) are the only protection.

## 5. What this proves, and what it does not

**Proves (if it passes):** the server runs on Linux; pgvector installs from packages; HTTPS and the host-header check work with a real name; a second laptop signs in and gets the same figures; concurrent users are logged correctly on a real host; real memory and time numbers.

**Does not prove:** the network drive (not reachable from AWS); the Principal Architect's VM (a different account, OS and network); Ingenus's on-prem server (OS and Postgres UNKNOWN); real SAP, real contracts or any policy question; capacity.

## 6. Risks

| Risk | What we do |
|---|---|
| A forgotten VM or disk costs money | No budget alarm (decided 11 Nov): `shutdown -h +120` every session, stop when idle, my reminders, step M |
| Wrong account | Step B stops the run if it is not the sandbox |
| Ports 80 and 443 open to the world | Sign-in on (401 without a token), synthetic data only, stop when idle; port 22 and 8766 never open |
| Key or password leaks | Made on the VM, mode 600, never in the repo or chat; delete the Entra certificate at the end |
| Policy: files on AWS | Decision 7 |
| Linux surprises | Step A found one (Windows paths); the rest we meet on the VM |
| My commands are untested on this image | Each step shows what you should see; tell me when it differs and stop |

## 7. Inputs needed

| # | What | From |
|---|---|---|
| D1 | ~~A domain, and whether 80 and 443 may be open~~ | Decided by Sridhar (Aditya is busy): a temporary name (section 2c), ports as in section 2b. **Ports agreed by Sridhar on 11 Nov 2026:** 80 and 443 open to everyone only while the VM is on; remove the rule for 80 once the certificate is issued (step I7). **Still open:** a domain purchase of about 3 USD (Sridhar's go, only when HTTPS is needed). Tell Aditya when convenient |
| D2 | ~~The monthly budget cap~~ | Dropped (Sridhar, 11 Nov): no AWS Budget; see decision 4 |
| D3 | ~~May synthetic contracts sit on this VM?~~ | Yes (Sridhar, 11 Nov) |
| D4 | A second person and laptop with their own Claude account (also unlocks TP-4, TP-5, TP-9 and TP-12) | Sridhar |
| D5 | ~~The small fix in the path guard for Windows-style paths on Linux~~ | Done 11 Nov 2026 (Sridhar said do it); uncommitted |

## 8. Results (fill in as we go)

| Step | Result | Date |
|---|---|---|
| A, server on Linux (WSL) | 343 passed, 3 failed (Windows paths), 7 skipped; after the path-guard fix 353 passed, 0 failed, 7 skipped; server runs, 10 tools, chain intact | 11 Nov 2026 |
| B, account and region | `aws login` done; account **089020215064**, IAM user `sridhar.vetrivel` in groups `Administrators` and `Bedrock-POC`; region `ap-southeast-2`. **Confirmed as the TAC sandbox** by Sridhar from the console header (`TACSandbox (089020215064)`, the same number as the CLI). No EC2 instances in the region yet. The account already has two budgets (`My Monthly Cost Budget` 100, `da-monthly` 60) that are not ours: do not touch them | 11 Nov 2026 |
| C, role, firewall, bucket, policy | **Done and verified read-only, 11 Nov 2026.** Role `ingenus-poc-ssm-role` (tag, `AmazonSSMManagedInstanceCore`, instance profile of the same name). Firewall `sg-05188e7651da8a192` in the Sydney default VPC: inbound 80 and 443 from `0.0.0.0/0` only, no SSH. Bucket `ingenus-poc-transfer-089020215064-ap-southeast-2-an` in ap-southeast-2: public access blocked, SSE-S3, tag set, versioning never enabled. Inline policy `ingenus-poc-read-code`: `s3:GetObject` on that bucket only (simulated: GetObject allowed; Put, Delete, List and another bucket denied). A firewall made by mistake in us-east-1 was deleted | 11 Nov 2026 |
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
