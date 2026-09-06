---
name: bp-branch-experimentation
description: Use when planning or running BlackParrot experiments that may fail, especially when deciding how to isolate them on branches, checkpoint working states, and revert unsuccessful lines of investigation cleanly.
---

# BlackParrot Branch Experimentation

Use this skill for experiment-heavy development where preserving a known-good state matters as much as trying the next idea.

## Goals

- isolate risky experiments from stable work
- make it cheap to revert failed ideas
- preserve the last verified state before each new line of work

## Preferred Structure

1. keep a stable branch with the last verified result
2. create a dedicated experiment branch for the next idea
3. make one meaningful change set at a time
4. checkpoint after each verified milestone

## When to Revert

Revert an experiment promptly if it:

- does not improve the measured result
- introduces ambiguous failures
- breaks previously known-good flows without clarifying the root cause
- mixes too many hypotheses at once

## Debugging vs Functional Work

Keep separate when practical:

- debug instrumentation
- cleanup
- structural refactor
- behavior-changing optimization

## Good Experiment Pattern

- baseline
- one hypothesis
- one implementation slice
- targeted test
- keep or revert based on evidence

## Reporting

After an experiment, say:

- what hypothesis was tested
- what changed
- what result was observed
- whether the branch should keep the change or revert it

