---
description: Ongoing card/board conventions for agents operating any Planka board — priority signalling, epics, description vs. comment discipline, and the substitutes for features Planka lacks natively.
---
# Planka Board Conventions — Policy

## Rules

- **Epics use one card's task list, not many sibling cards.** When a label or list needs a multi-step goal broken down (step zero to the goal), add a task list (checklist) inside a single card rather than spawning a flat card per step. Progress then reads directly off the card face as a completed-of-total count, instead of requiring every sibling card to be opened to gauge progress.
- **Description holds the current answer; comments hold the history.** A card's description is overwritten in place as understanding improves — it never grows into a log of what was tried or discussed. Anything that is timestamped narrative (what was considered, what changed, why) goes in comments instead. This is the same discipline the project's own description field already follows, applied one level down to every card.
- **Title prefixes are a fixed, closed vocabulary: `URGENT:`, `Parked:`, `Blocked:`.** Planka has no native priority field (an open, unresolved upstream feature request), so a prefix is the only priority/status signal visible without opening the card. Nothing outside this fixed set is used — an open vocabulary turns into private notation only the agent that wrote it can decode.
- **A "Waiting on..." card names its blocker in the title or the first line of the description.** The list itself only says a card is blocked, not on what; the blocker has to be legible from a scan of the list without opening every card in it.
- **Position is the only priority-ordering signal inside a list.** Top of list is most urgent. Reprioritizing means moving the card to a new position — never a second, competing scheme (e.g. a separate priority label or field).
- **Archive instead of delete when a card stops being relevant.** Planka's archive state is distinct from deletion and keeps the card's history retrievable; deleting a card destroys anything written into its description or comments.
- **Long-form material goes in an attachment, with a one-line pointer left in the description.** A description is for the current answer, not for pasting a full document; if the material is genuinely long (a drafted questionnaire, a photo, a PDF), attach it and describe in one line what it is.

## Rationale

Planka has no card-dependency graph, no priority field, and no structural distinction between a card's current answer and its history — three gaps this convention set exists to paper over with a small number of fixed, legible signals. Without an agreed convention, different agents (and humans) touching the same board drift into inconsistent card shapes and information silently gets buried in descriptions that expand into logs nobody re-reads. These rules keep any Planka board an agent operates predictable to the next agent or human who opens it cold, without requiring them to have been part of the conversation that set the convention.

## Scope

- Any Planka board operated by an agent, not limited to one project.
- Applies to card creation, card updates, and card review, whether performed by an agent or by a human collaborator working the same board.

## Enforcement

- Planka has no API-level way to enforce any of this — it is applied by whoever is touching the board, agent or human.
- A card that violates one of these (an unbounded description, an unnamed blocker, a title prefix outside the fixed set) is a hygiene defect to fix on sight, not a hard gate that blocks work.

## Exceptions

- None.

## See Also

- ~/.teleclaude/docs/apps/procedure/planka/onboard-project.md
