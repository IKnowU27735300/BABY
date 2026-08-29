# Baby Hive Protocol

## Overview

The Baby Hive is a filesystem-based multi-agent coordination system.
Agents communicate via message passing through shared inbox/outbox directories,
coordinate through a shared planning board, and track work via a task ledger.

## Message Schema (FIPA-Lite Speech Acts)

Every message is a JSON file in an agent's `inbox/` directory.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique message ID (12-char hex) |
| `from_agent` | string | Sender agent ID |
| `to_agent` | string | Recipient: agent ID, "broadcast", or "god" |
| `act` | string | Speech act (see below) |
| `subject` | string | Short subject line |
| `body` | string | Full message body |
| `timestamp` | float | Unix timestamp |
| `reply_to` | string | ID of message being replied to |
| `metadata` | dict | Arbitrary metadata |

### Speech Acts

| Act | Description |
|-----|-------------|
| `request` | Ask an agent to perform a task |
| `inform` | Share information or results |
| `propose` | Suggest a plan or approach |
| `query` | Ask a question |
| `agree` | Accept a proposal or task |
| `refuse` | Decline a proposal or task |
| `done` | Signal task completion |

## Message Flow

1. Agent writes message JSON to its `outbox/`
2. Router polls all outboxes every 2 seconds
3. Router redacts secrets, then copies to recipient's `inbox/`
4. Recipient processes message, moves it to `inbox/.done/`
5. Recipient may reply via its own `outbox/`

## Targeting

- **Direct**: `to_agent = "agent_id"` — routed to specific agent
- **Broadcast**: `to_agent = "broadcast"` — copied to all agents' inboxes
- **God**: `to_agent = "god"` — routed to the orchestrator agent

## Task Management

Tasks are tracked in `tasks.json` with dependency DAG support.

### Statuses

| Status | Description |
|--------|-------------|
| `todo` | Not started, waiting for dependencies |
| `doing` | Currently in progress |
| `blocked` | Waiting on external input |
| `done` | Completed successfully |

### Dependencies

Tasks can declare dependencies on other task IDs. A task becomes "ready"
when all its dependencies are in `done` status.

## Memory Structure

Each agent's `memory.md` follows a 3-region structure:

```markdown
# Memory — <name> (<id>)

## Pinned facts
<important facts that are never condensed>

## Condensed history
<recursive summary of evicted sections>

## Recent
<recently added sections>
```

## Security

- All API keys and secrets are redacted before messages leave the main process
- Secret patterns: PEM keys, JWTs, sk-, xoxb-, ghp_, AKIA, AIza, bearer tokens
- Agents should never log or transmit raw secrets




