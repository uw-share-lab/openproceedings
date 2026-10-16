# A message to a busy background agent is read after its turn, so a decision sent that way can arrive after the PR merges

**Key lesson:** Put every decision a background agent needs before merging in its brief (the spawn prompt), or confirm the agent has acknowledged a later message before it queues the PR with `gh pr merge --auto`, because a message sent to an agent that is mid-turn or about to go idle is often read only after that turn ends.

- **Date:** 2026-10-16 · **Task:** n/a (the 2026-10-16 batch) · **Area:** tooling
- **Artifacts:** PRs #142, #155, #156 and #158; the follow-up tasks filed on branch `chore/friday-followups-2026-10-16`; `.claude/skills/pr-workflow/SKILL.md` §Several sessions on one machine

## What we set out to do
Run the day's batch with a lead session coordinating several background agents, one PR each, and send owner
decisions and review results to those agents as they came in.

## What we learned
- **A message to a busy agent waits for its turn to end.** A message sent to a background agent that is
  mid-turn, or about to finish and go idle, is often read only once that turn is over. By then the agent
  may already have queued its PR, and the merge queue merges it without waiting (evidence: the lead
  session's report of the 2026-10-16 batch).
- **Four results reached their PRs after the merge:** the owner's override wording for PR #142, the
  served-note clause for PR #155, and late security findings on PRs #156 and #158. Each one became a
  follow-up task instead of a fix in its own PR.

## Dead ends — don't repeat these
- Sending a decision the PR depends on as a mid-flight message and assuming the agent will act on it before
  it queues. Recognise it when the decision is still being made after the agent has started work: hold the
  merge (tell the agent not to queue until it hears back), or wait for the agent to say it has the message.

## Decisions (and what would change them)
- Decisions an agent needs before merging go in its brief, or the lead waits for the agent's acknowledgement
  before the agent queues → a message is not seen until the agent's turn ends → would change if messages
  interrupted a running turn.

## Follow-ups
- The late findings from PRs #142, #155, #156 and #158 were filed as follow-up tasks by the lead session on
  `chore/friday-followups-2026-10-16`.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/pr-workflow/SKILL.md` §Several sessions on one
  machine (the closest owner of how parallel sessions are coordinated; no agent or CLAUDE.md covers briefing).
- Test or hook added? — no: this is how the lead briefs and messages agents, and no hook sees messages.
