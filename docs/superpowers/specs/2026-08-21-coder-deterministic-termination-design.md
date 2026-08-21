# Coder Agent Deterministic Termination Design

## Problem

`coder_agent` currently relies on the model to call `exit_tool` or return no
tool calls. When the model keeps calling tools, the loop reaches the fixed
`MAX_TOOL_ROUNDS = 20` limit. The implementation then collects whatever files
exist and reports `code_done`, even though the loop did not terminate normally.
This wastes model calls and can misreport an incomplete project as successful.

## Goal

Make new-project generation terminate deterministically as soon as every file
required by `architecture.file_list` exists and is non-empty. If the hard round
limit is exhausted without a valid completion condition, return an explicit
error instead of reporting success.

## Non-goals

- Do not reduce `MAX_TOOL_ROUNDS`; it remains a safety ceiling.
- Do not change the model router, prompts, tool permissions, RAG, Reviewer, or
  Builder behavior.
- Do not infer completion of modify-mode work from file existence because those
  files already exist before modification starts.

## Completion Rules

The ReAct loop can complete successfully through one of the existing explicit
signals:

1. The model calls `exit_tool`.
2. The model returns no tool calls, preserving the existing direct-output
   fallback.

New-project mode adds one deterministic signal:

3. After a tool-call batch, every normalized path in
   `architecture.file_list` exists under `project_dir`, is a regular file, and
   is non-empty, and no tool failed in that batch.

When rule 3 is satisfied, the harness stops the loop immediately and sends the
collected files to the existing Reviewer. The Reviewer remains responsible for
code quality; the Coder loop only decides structural generation completeness.

Modify mode continues to require rule 1 or rule 2. File coverage cannot prove
that requested edits were applied.

## Round-limit Handling

The implementation records whether the loop ended through a valid completion
rule. If all rounds are consumed without one:

- new mode reports an error containing the missing required paths, or a generic
  incomplete-termination message when all paths exist but tool failures remain;
- modify mode reports that the tool-round limit was exhausted without an
  explicit completion signal;
- neither mode sets `phase = "code_done"`.

This prevents a partial filesystem snapshot from being presented as a normal
Coder result.

## Observability

Coder logs will state the termination reason:

- explicit `exit_tool`;
- direct model result/no tool calls;
- all required files created;
- round limit exhausted, including missing paths when applicable.

No new external tracing or metrics dependency is introduced.

## Tests

Focused unit tests will use a deterministic fake LLM and real temporary file
tools to verify:

1. New mode exits after the first round when all required files are created,
   even when the model omits `exit_tool`.
2. New mode returns an error when the round limit is exhausted with required
   files missing.
3. Existing explicit `exit_tool` completion still succeeds.
4. Modify mode cannot claim success solely because existing files are present
   when the round limit is exhausted.

After focused tests pass, the relevant Python Agent test suite will run as a
regression check.
