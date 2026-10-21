# 0009: the v1 POC VM is on AWS, provisioned by Aditya (not by Psiog IT on Azure)

**Date:** 21 Oct 2026 · **Status:** locked as an instruction; nothing built or provisioned yet · **Phase:** 1, v1 (`MCP-Server/`)

## SAID

- **Aditya's instruction, relayed by Sridhar on 21 Oct 2026:** do not depend on the Psiog IT team for an Azure VM. Aditya will
  provision the VM on **AWS**.

## Decision

**Purpose (Sridhar, 21 Oct 2026):** the AWS deployment exists to **QA multiple users calling the server at once and the logging** (audit and login log, check history), which one laptop cannot show. That is what "done" means for it, not a production-like rollout.

**Scope (Sridhar, 21 Oct 2026):** AWS is for the **POC completion only**. The deployment at Ingenus may be Azure (or on-prem; Ingenus leaned on-prem on 8 Oct, **SAID**). Nothing in the design may assume AWS: no AWS-only services in the code, and the settings stay host-neutral.

0. **Order (Sridhar, 21 Oct 2026):** build and test the whole project locally first; hosting on the AWS VM comes **last**.

1. The POC server (and the Postgres of decision 0008, if kept on the same VM) is hosted on a **VM on AWS that Aditya provisions**.
2. **Psiog IT is no longer on the path for the VM, its DNS name or its HTTPS certificate.** Steps 5 and 6 of
   [`psiog_it_steps_v1-4_v1-6.md`](../psiog_it_steps_v1-4_v1-6.md) are not sent to Psiog IT. Checklist item 2.1 now waits on Aditya.
3. This replaces "Psiog Azure once the VM exists" in decision 0008 and in the checklist for the POC only. Where Ingenus runs it later (Azure, on-prem or
   another) is a later decision, **UNKNOWN**.
4. Nothing else changes in the design: the server still checks Entra sign-in tokens and calls Microsoft Graph, which work from any host
   that can reach `login.microsoftonline.com` and `graph.microsoft.com`. The certificate key for the server app is made **on the AWS VM**
   (developer guide 5.1), and the VM uses service environment variables, not `.env`.

## UNKNOWN (ask Aditya)

- Whose AWS account, which region, and OS (the server runs on Windows or Linux; the code is untested on Linux).
- Who provides the **DNS name and HTTPS certificate** (the bridge refuses plain `http://` to another machine) and how: not decided.
- Whether Postgres runs on the same VM or as a managed AWS database; and the network rules (who may reach port 8765 / 443).
- **Entra tenant for the real sign-in:** the dev tenant (`vvrzl`) is ours for testing. Which tenant the AWS-hosted POC signs people in against,
  and who creates the app registrations there, is open. Psiog IT may still be needed for that, which is a different request from the VM.
- Whether the AWS VM may hold even synthetic contracts under Psiog's and Ingenus's policies (the rule today: synthetic or public data only).
- **The network drive (V1-8) cannot be reached from AWS** unless a private link to Ingenus exists; today it is tested on a local folder only.
  SharePoint and OneDrive are reachable over the internet through Graph.
