```markdown
# Prompts

This folder holds the instructions I authored and gave to my AI coding assistant for each section of the assessment. They are the *inputs* to the sessions, kept separately from [`prompt-logger/`](../prompt-logger), which contains the raw, unedited session captures (the *record* of those sessions). Each prompt defines the role, objective, constraints and — importantly — a checkpointed, human-in-the-loop protocol: the assistant delivers one stage at a time and stops for my review and explicit approval before continuing, so every design decision in `submission/` was reviewed and accepted by me before it was committed. The table below maps each prompt to the section it drove and the session log(s) that executed it.

| Prompt | Section | Session log(s) |
|---|---|---|
| `section1_polars_pipeline.md` | Section 1 – Data Pipelines | `prompt-logger/claude-code/<session-id>.jsonl` |
| `section2_database.md` | Section 2 – Databases | `prompt-logger/claude-code/<session-id>.jsonl` |
| `section3_system_design.md` | Section 3 – System Design | `prompt-logger/claude-code/<session-id>.jsonl` |
```

Fill in the session IDs after each commit (`ls prompt-logger/claude-code/`). If one prompt spanned several sessions, list them all in that cell.