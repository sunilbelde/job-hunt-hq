# Acting on the build report

`run build` prints `fix` lines for hard checks, which reject the resume until they pass, and `aim` lines for
targets. `out/check.json` has the same findings plus the page measurements. Bullets are named by their place
on the page and their sources, for example `j4#1 (from j4.b1)` for the first bullet under job j4.

## Hard checks

- `one_page`: the content spills onto a second page. Shorten bullets, or drop the least relevant ones
  (often in older jobs) or skills items the posting does not ask for.
- `fill_floor`: under 90% of the page is used. Restore relevant base bullets or detail.
- `overfull_line`: a line runs into the right margin, usually because of a long unbreakable string. Reword
  it so the line can break.
- `compile_failed`: the template did not compile. This should not happen with plain text; simplify the
  bullet named in the message.
- The content checks (`unknown_skill`, `missing_source`, `unsupported_number`, …): see rules.md.

## Targets

- `fill_target`: under 96% of the page is used, and the report says about how many lines are free. Use
  them for relevant base detail: restore a dropped bullet, or extend a bullet with detail from its own
  sources. Never add filler.
- `short_last_line`: the bullet's last line holds only a word or two. Trim a few words so it ends a line
  earlier, which frees a line, or extend it with detail from its own sources to fill the line.

## Sizes

A text line is about 12 pt high, and the page holds about 54 of them. A bullet line holds about 110
characters. The base resume itself fills 98.7% of the page, with three short last lines (j4.b1 to j4.b3),
so a full page needs no filler.

Hard checks must pass. Targets are best effort within the 5 builds.
