---
inclusion: auto
---

# GLPI Ticket Lifecycle — MANDATORY RULE

> **This rule is non-negotiable. It applies to every spec task execution in this workspace, no exceptions.**

---

## The Rule

**BEFORE starting any spec task**, you MUST call `create_server_ticket` via the `glpi-api-proxy` MCP server.

**AFTER completing any spec task**, you MUST call `list_server_tickets` to find the open ticket, then call `complete_server_ticket` to close it.

This is not optional. This is not best-effort. This is a hard requirement for every task.

---

## What to do if the proxy is unreachable

If `create_server_ticket` or `complete_server_ticket` fails or times out:

1. Log the failure clearly: `"GLPI ticket creation failed: <error>"`
2. **Continue with the task anyway** — do not block or abort
3. At the end of the task, note in your response that the GLPI ticket could not be created/closed and why

The proxy being down does NOT excuse skipping the attempt. You must always try.

---

## MCP Server

Server: `glpi-api-proxy`

Tools:
- `proxy_health()` — verify connectivity before attempting ticket ops
- `create_server_ticket(title, description, agent, urgency)` — open a ticket
- `list_server_tickets()` — list open tickets for SRV-GLPI-PROCESSOR
- `complete_server_ticket(ticket_id, solution)` — close a ticket

---

## Exact Steps — Task Start

1. Call `create_server_ticket` with:
   - `title`: the task name/number (e.g. "Task 3.1 — Implement ArchiveIngestionTool.load()")
   - `description`: one sentence describing what will be implemented
   - `agent`: `"kiro"` (always)
   - `urgency`: `3` (default, unless task is critical)
2. Note the returned `ticket_id` — you will need it to close the ticket

## Exact Steps — Task Complete

1. Call `list_server_tickets()` to find the open ticket matching this task
2. Call `complete_server_ticket(ticket_id, solution)` with:
   - `ticket_id`: the ID from step 1
   - `solution`: a brief description of what was implemented

---

## Connection Details

- Proxy URL: `http://100.112.16.115:8080` (Tailscale — preferred)
- GLPI Server: `http://100.105.152.56` (Tailscale)
- LAN fallback: `192.168.1.244:8080` → `192.168.1.33`
- Auth: OAuth Password Grant — handled internally by the MCP server
- Urgency scale: 1=very high · 2=high · 3=medium (default) · 4=low · 5=very low
- Server name in GLPI: `SRV-GLPI-PROCESSOR`

---

## Why this matters

Every task executed by Kiro in this workspace is tracked in GLPI for infrastructure auditability. Missing tickets break the audit trail. Always attempt the call.
