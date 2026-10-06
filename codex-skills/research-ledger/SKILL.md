---
name: research-ledger
description: Maintain an evidence-linked ledger for long-running empirical engineering or research work. Use when experiments span many turns, conclusions evolve, the user asks what was learned, or prior knowledge must be separated from new findings.
---

This skill preserves the reasoning state of a long-running investigation, not just its activity history. It uses a project ledger as the authoritative map from questions to evidence while raw logs and chronological work logs remain authoritative for details.

# Research Ledger

## Workflow

1. Locate an explicitly named ledger or the nearest project `RESEARCH_LEDGER.md`. Create one from [the schema](references/schema.md) when the investigation has no durable synthesis.
2. At the start of relevant work, read the ledger before interpreting new evidence or proposing another experiment.
3. Before an experiment, state which open question or claim it can change. Do not repeat an experiment merely because its earlier conclusion fell out of chat context.
4. After material evidence, update the affected claim in place. Preserve its stable ID, scope, confidence, exact evidence path, and relationship to prior expectations.
5. Record rejected measurements and superseded interpretations. Say why they are invalid or narrower; never silently replace them.
6. Keep the ledger synthetic. Link raw logs, status JSON, commits, and detailed chronology instead of copying them.

## Reasoning Rules

- Separate **expected beforehand**, **newly measured**, **new mechanism/root cause**, and **still unknown**. Confirmation of an expectation is evidence, but not a newly invented insight.
- Scope every number to its platform and model. Do not mix synthetic memory latency, FPGA DDR behavior, and Linux end-to-end results.
- Distinguish primitive latency from workload speedup and latency hiding from bandwidth improvement.
- Prefer accepted matched controls. Label diagnostic, superseded, contaminated, or incomplete runs explicitly.
- When a result changes, retain the old claim under superseded findings and point to the replacement.
- Make summaries delta-first: what changed since the last synthesis, which previous conclusion it strengthens or overturns, and what remains unresolved. Provide the full baseline only when requested.
- Treat conversation memory as a locator, not evidence. Verify claims against current artifacts before updating the ledger.

## Maintenance

Update the ledger after a confirmed root cause, accepted benchmark, meaningful negative result, scope correction, or decision about the next experiment. Avoid routine status entries. Keep `WORK_LOG.md` chronological and the research ledger claim-oriented.
