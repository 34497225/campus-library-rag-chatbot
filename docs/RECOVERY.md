# Database recovery runbook

This runbook covers recovery for the Neon PostgreSQL database used by the
Campus Library Chatbot. It separates the procedure that has been exercised
from the production point-in-time restore procedure that must still be
approved during a real incident.

## Recovery objectives

- **RPO (recovery point objective):** the maximum acceptable amount of data
  loss, measured between the selected recovery point and the incident.
- **RTO (recovery time objective):** the target time from declaring recovery
  until the database is usable and integrity checks pass.

The project has no contractual SLA. The current operational targets are:

| Situation | Working RPO target | Working RTO target |
| --- | ---: | ---: |
| Bad change on a development branch | Parent branch's latest state | 15 minutes |
| Production logical corruption | Latest verified point before corruption | 60 minutes |

These are engineering targets for a portfolio deployment, not measured SLOs.
The available production recovery point is limited by the Neon project's
configured history-retention window. Check that setting before every restore;
do not assume an older point remains available.

## Safety rules

1. Stop or place the application in maintenance mode before a production
   restore so that new writes do not race with recovery.
2. Never test destructive SQL on `production`. Create an isolated branch and
   pass its branch ID explicitly to every SQL or automation command.
3. Prefer a preview/temporary branch first. Validate it before changing the
   branch used by the application.
4. Record timestamps in UTC, the chosen recovery point, operator, reason and
   validation results. Never paste connection strings, passwords or JWTs into
   tickets, logs or this repository.
5. Keep the pre-restore state until validation and stakeholder approval are
   complete, then remove temporary branches to control cost and data exposure.

## Incident decision tree

```text
Service unhealthy
  ├─ Database reachable and schema current?
  │    ├─ No → inspect Render startup/Alembic logs and Neon status first
  │    └─ Yes
  ├─ Is corruption limited to a non-production child branch?
  │    ├─ Yes → reset child from parent (exercised procedure below)
  │    └─ No
  └─ Is a known-good production time inside history retention?
       ├─ Yes → preview a point-in-time restore, validate, then finalize
       └─ No → escalate; restore from the newest available external export
```

## Exercised procedure: reset an isolated child branch

Use this procedure when a disposable development or test branch must return to
its parent's current state.

1. Record the parent and child branch names and capture aggregate integrity
   results before the experiment.
2. Create a temporary child of `production` with a unique drill name.
3. Run simulated incident SQL only on the temporary branch.
4. Confirm the branch diverged. Use a marker table or aggregate counts; do not
   copy user email addresses or message content into the drill record.
5. Reset the child from its parent and preserve the pre-reset state under a
   temporary incident branch name.
6. Run the integrity queries below against the reset child.
7. Keep the preserved incident branch only long enough to confirm the expected
   divergence. Delete both temporary branches after the drill.

Resetting is destructive to the child branch. It is analogous to replacing the
child with the parent's current database state; it is not a substitute for a
historical production restore.

## Production point-in-time recovery

This path has deliberately **not** been finalized against production. In a real
incident, use Neon's Restore page and Time Travel Assist (or the equivalent API)
to inspect a read-only point inside the retention window.

1. Declare the incident, record the suspected corruption time in UTC and pause
   application writes.
2. Use Time Travel Assist to query candidate times without changing production.
3. Restore the selected point to a preview branch first.
4. Run all integrity checks and an application smoke test against the preview
   branch. Confirm the Alembic revision matches the deployed code.
5. Obtain approval for the measured data-loss window (RPO).
6. Finalize the restore only after approval. A finalized restore changes the
   active database state while preserving the previous state for rollback.
7. Verify `/health`, `/ready`, authentication, owner-scoped conversation CRUD
   and metrics. Resume writes only after these checks pass.
8. Retain the old state for the agreed observation window, then securely remove
   temporary/orphaned branches.

## Integrity queries

Run read-only checks first. These queries return metadata and counts rather than
PII or message contents.

```sql
SELECT version_num FROM alembic_version;

SELECT
  (SELECT count(*) FROM users) AS users_count,
  (SELECT count(*) FROM conversations) AS conversations_count,
  (SELECT count(*) FROM messages) AS messages_count;

SELECT count(*) AS orphan_conversations
FROM conversations AS c
LEFT JOIN users AS u ON u.id = c.user_id
WHERE u.id IS NULL;

SELECT count(*) AS orphan_messages
FROM messages AS m
LEFT JOIN conversations AS c ON c.id = m.conversation_id
WHERE c.id IS NULL;

SELECT count(*) AS invalid_roles
FROM messages
WHERE role NOT IN ('user', 'assistant');
```

Expected results:

- Alembic revision equals the revision expected by the deployed commit.
- Counts are consistent with the selected recovery point.
- Orphan and invalid-role counts are zero.
- API smoke tests preserve authentication and owner isolation.

## Exercise record: 2026-08-13

Scope: Neon Singapore project, temporary child branches only. Production was a
read-only parent and received no drill data.

| Check | Observed result |
| --- | --- |
| Baseline migration | `37b4f29eb2f9` |
| Baseline rows | users 0, conversations 0, messages 0 |
| Simulated incident | Added one temporary table and one marker row on the drill branch |
| Recovery action | Reset drill branch from `production`, preserving incident state temporarily |
| Control-plane reset time | 1.45 seconds |
| End-to-end verified recovery | Under 10 seconds in this small, idle project |
| Actual drill data loss | 0 business rows; only the intentional marker was discarded |
| Post-recovery integrity | Migration and table counts matched baseline; marker table absent |
| Cleanup | Drill and preserved-incident branches deleted; only production and development remained |

The timings above are a single drill measurement, not an RTO guarantee. A real
production restore may take longer because it includes incident analysis,
recovery-point selection, application coordination and stakeholder approval.

## Review cadence

- Repeat after schema changes that alter recovery checks.
- Repeat at least quarterly if the project becomes actively used.
- Review history retention and plan limits before each exercise.
- Record the date, selected point, measured RPO/RTO, validation failures and
  cleanup evidence without recording secrets or user content.

## References

- [Neon branching and recovery overview](https://neon.com/docs/guides/branching-intro)
- [Neon project restore-window configuration](https://neon.com/docs/manage/projects)
- [Neon MCP branch reset behavior](https://neon.com/docs/ai/neon-mcp-server)
