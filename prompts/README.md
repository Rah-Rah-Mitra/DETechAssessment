# Prompts

This folder holds the instructions I authored and gave to my AI coding assistant for each section of the assessment. They are the *inputs* to the sessions, kept separately from [`prompt-logger/`](../prompt-logger), which contains the raw, unedited session captures (the *record* of those sessions). Each prompt defines the role, objective, constraints and — importantly — a checkpointed, human-in-the-loop protocol: the assistant delivers one stage at a time and stops for my review and explicit approval before continuing, so every design decision in `submission/` was reviewed and accepted by me before it was committed. The table below maps each prompt to the section it drove and the session log(s) that executed it.

| Prompt | Section | Session log(s) |
|---|---|---|
| [`section1_polars_pipeline.md`](section1_polars_pipeline.md) | Section 1 – Data Pipelines | [`10853dc6-bb12-440e-95c7-b4d4966ddb77.jsonl`](../prompt-logger/claude-code/10853dc6-bb12-440e-95c7-b4d4966ddb77.jsonl) |
| [`section2_database.md`](section2_database.md) | Section 2 – Databases | [`987361e7-57e5-463b-adc3-67becab8b3ec.jsonl`](../prompt-logger/claude-code/987361e7-57e5-463b-adc3-67becab8b3ec.jsonl) |
| [`section3_system_design.md`](section3_system_design.md) | Section 3 – System Design | [`0579bb73-681b-47a1-ae3a-52e90ca3651c.jsonl`](../prompt-logger/claude-code/0579bb73-681b-47a1-ae3a-52e90ca3651c.jsonl) (draw.io MCP setup), [`79f1f383-06db-49e7-b1c0-478e44efe3fa.jsonl`](../prompt-logger/claude-code/79f1f383-06db-49e7-b1c0-478e44efe3fa.jsonl) (diagram) |
| [`final_verification.md`](final_verification.md) | Pre-submission self-audit of all three sections; findings in [`verification_report.md`](verification_report.md) | [`507aa281-3fda-45fe-bd43-607dd0afd180.jsonl`](../prompt-logger/claude-code/507aa281-3fda-45fe-bd43-607dd0afd180.jsonl) |

The remaining two logs, `9bf87887-…` and `efdd74a4-…`, are short sessions containing only slash commands and local-command output; they carry no prompts and are kept because the pre-commit hook captures every session verbatim.
