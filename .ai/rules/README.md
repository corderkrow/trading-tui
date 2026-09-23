# Project Rules

Rules for the trading-tui project (Python 3.12 · FastAPI backend · Textual TUI).
OpenCode V2 does not auto-load files in this folder — `AGENTS.md` points here,
so read this index at the start of a task and open every rule that applies.

## Layout

```
.ai/rules/
  README.md          # this index — update it when adding a rule
  <area>/
    RULES.md         # the rule for that area
    ...              # optional assets / specs for that rule
```

One folder per rule area. Folder name = area (`brand`, `adapters`, `tui`,
`alerts`, ...). The rule body always lives in `RULES.md`; supporting files sit
beside it.

## Rules

| Area  | File                                     | Applies to                                                                                          |
| ----- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| brand | [`brand/RULES.md`](./brand/RULES.md)     | All design, UI, styling, layout, colour, typography, and content-voice work. Mandatory before any design work. |
| brand | [`brand/brand.html`](./brand/brand.html) | Brand reference / spec (imagotipo, tokens).                                                          |

## Adding a rule

1. `mkdir .ai/rules/<area>`
2. Add `.ai/rules/<area>/RULES.md`
3. Add a row to the table above.
