# ADR-003: Revert-Only SRE Doctrine

**Date:** 2026-06-20  
**Status:** Accepted  
**Author:** Shane Louis Slabbert

---

## Context

The factory is operated by a single person. Production incidents will occur at unpredictable times, including 2 AM. The operator cannot be on-call 24/7. An automated incident response system is required. The question is: what should that system be allowed to do?

## Decision

**The SRE Agent may ONLY revert to the last known good deployment. It may not repair, patch, restart, or modify anything in production.**

## Rationale

Automated repair in production is more dangerous than the original incident. A system that attempts to fix code at 2 AM without human oversight can:
- Apply a patch that makes the problem worse
- Corrupt database state while attempting repair
- Mask the root cause, making forensic analysis impossible
- Create a second incident while resolving the first

Revert is a single, well-defined operation with a known outcome: return to the last deployment that was verified clean. The worst case is 2-5 minutes of downtime during the revert. This is acceptable. The worst case of automated repair is unbounded.

**The human receives at 7 AM, not 2 AM, because:**
- The system is self-healing (revert succeeded)
- Waking a person for a resolved incident reduces their effectiveness on the actual root cause analysis
- The forensic state is captured completely — nothing is lost by waiting

The human is woken immediately only if the revert itself fails — a rare event that genuinely requires manual intervention.

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Auto-restart the failing service | Masks root cause, may loop indefinitely |
| Apply hotfix automatically | Unreviewed code in production — violates the factory's core safety model |
| Page human immediately on any anomaly | Alert fatigue, human unavailable at 2 AM, revert is faster anyway |
| Do nothing, wait for human | Production down for hours — unacceptable |

## Consequences

- Every production deployment must have a clean rollback target
- Blue-green deployment is mandatory — the previous version must remain available for instant revert
- Forensic state capture runs before revert, not after — preserves evidence
- Incident reports are structured and stored in `/incidents/INC-{date}-{id}/`
- The SRE Agent's revert capability is tested via mandatory fire drill before every production promotion
