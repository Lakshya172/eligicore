# EligiCore UI — Midnight Bronze: Precision Edition

Design notes for the student frontend. Presentation only: nothing here changes an API
contract, a verdict, a count or what is stored.

## Audit of the first Midnight Bronze pass

| # | Issue | Decision |
|---|---|---|
| 1 | Surfaces were warm brown-black (`#141311`, `#1b1916`) and a bronze glow sat behind every page, so the product read brown rather than black. | Cool graphite surfaces (`#080a0d` → `#1d2228`) with neutral borders. Bronze appears only for actions, selection, focus, progress and the landing hero's single glow. |
| 2 | Motion ran long and was inconsistent: 400 ms page entry, 480 ms hero, staggered delays up to 240 ms. NN/g treats over 400 ms as sluggish; Material puts desktop transitions at 150–200 ms. | Five tokens: 100 ms press, 150 ms hover/controls, 200 ms panels and exits, 250 ms page and dialog entry, 300 ms hero (one-off). Entries decelerate, exits accelerate and run shorter. |
| 3 | The nav indicator faded in per item, so it never conveyed movement between destinations. Nothing was keyboard-first. | One sliding indicator moves between sidebar items. A quick-navigation dialog (Ctrl/⌘ K) and `/` to focus search give keyboard routes through the product. |
| 4 | Cards were nested inside cards (metric tiles, requirement rows, stats), each with a 14 px radius. The result felt soft and template-like. | Radii are 4/6/8/12. Metrics and evidence are rows divided by hairlines inside one surface, not cards in cards. |
| 5 | The landing page explained three steps, but the product has five (profile, discover, evidence, prepare, you submit). Fake macOS window dots made the preview look like a template. At 1024 px the hero stacked and left an empty band. | A five-step workflow that names only what exists. The preview is framed as an EligiCore panel, still labelled as an illustration. The two-column hero holds down to 960 px. |
| 6 | Save had text-only feedback; upload had no drop support and no visible progress. | A button loading state (spinner plus `aria-busy`, disabled so it can't submit twice). Drag-and-drop runs through the same validation and request as the file picker. An indeterminate bar shows only while the real request is in flight, with no invented percentage. |
| 7 | The dashboard showed counts without saying which profile they belonged to, and showed a spinner while loading. | An "evaluated against" strip read from the profile in this tab, a share of the evaluated total next to each count, and a skeleton that matches the final layout. |
| 8 | Monospace was used inconsistently. | Monospace is for technical values only: relevance scores, counts of checks, request references, profile values in evidence rows, and keyboard hints. |
| 9 | Icons used a heavy 2 px stroke at sizes from 12 to 20 px, and controls used 34/40/42/48 px heights. | Icons use a 1.75 px stroke at 14 px (metadata) or 16 px (default). Controls are 32/40/48 px, and inputs match buttons at 40 px. |
| 10 | The demo-catalogue notice was a large banner repeated on every app page. | A slim inline note with the same wording, which must stay visible. |

## System

**Colour.** All text tokens meet WCAG AA (4.5:1) on every surface they are used on; this is checked in the browser on every route.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#080a0d` | Page |
| `--surface` | `#0f1216` | Panels |
| `--surface-raised` | `#161a1f` | Hover, inset, selected |
| `--surface-overlay` | `#1b2026` | Dialog, menus |
| `--line` / `--line-strong` | `#21262d` / `#2d333b` | Separators / control borders |
| `--text` / `--text-2` / `--text-3` | `#f0ece5` / `#a7abb0` / `#868c93` | Primary / secondary / muted |
| `--bronze` / `--bronze-light` | `#b78a60` / `#d1a77e` | Action fill / accent text and focus |
| Status | green `#86b89a`, amber `#d6a965`, red `#d9837c`, blue `#93aecb` | Verdicts only; status is never bronze |

**Type.** Typefaces come from local stacks: no font files are shipped and nothing is requested from another host.

- **Display** (landing and page titles only): Instrument Serif, then Iowan Old Style, Palatino, Georgia.
- **UI**: Inter, then Geist, Segoe UI Variable, SF Pro, system-ui.
- **Mono**: JetBrains Mono, then Cascadia Mono, SF Mono, Consolas.
- **Weights and scale**: weights are limited to 400 and 600. Sizes step 11/12/13/14/15/16/18/22 px, with a fluid display size.
- **Numerals**: tabular wherever numbers are compared.

Self-hosting Instrument Serif and JetBrains Mono (for example via `@fontsource`) was considered and deferred. It would add a dependency and about 100 KB of font files, with a swap flash, to a presentation-only PR.

**Space and shape.** Spacing uses a 4 px base (4–96). Radii are 4, 6, 8 and 12 px. There are three elevation levels, with shadows only on overlays and the hero preview.

**Motion.**

| Token | Duration | Used for |
|---|---|---|
| `--t-press` | 100 ms | Button and row press |
| `--t-fast` | 150 ms | Hover, colour, focus |
| `--t-base` | 200 ms | Indicator slide, menu sheet, exits |
| `--t-enter` | 250 ms | Page and dialog entry |
| `--t-hero` | 300 ms | Landing hero, once |

| Easing | Curve | Used for |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.2, 0, 0, 1)` | Entries and state changes |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Exits |
| `--ease-move` | `cubic-bezier(0.3, 0, 0, 1)` | Things that travel |

Only `transform` and `opacity` animate. Nothing loops except the spinner, the skeleton sweep and the indeterminate progress bar, and each of those runs only while a real request is pending. `prefers-reduced-motion: reduce` makes every transition instant and stops the loops.

## References

- NN/g, [Animation duration](https://www.nngroup.com/articles/animation-duration/) and [animation usability](https://www.nngroup.com/articles/animation-usability/).
- Material, [Duration & easing](https://m1.material.io/motion/duration-easing.html).
- Atlassian, [Motion](https://atlassian.design/foundations/motion/).
- Linear, Vercel, Stripe and Raycast informed the principles: dense but calm hierarchy, keyboard routes, restrained colour, and numbers set in tabular figures. No layouts were copied.
