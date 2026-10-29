# labscript deep pass: upstream stage

Upstream's commits on `master..upstream/master` (to `b0c132c`) that the fork
lacked, ported by hand onto `CodeHealth`, with Ian's approval. `master` is not
merged. Each commit credits its upstream source.

## Ported

| Commit | What | From upstream |
| --- | --- | --- |
| `12e4c50` | Secondary pseudoclocks run the shared-trigger check; a parentless `TriggerableDevice` compiles; the trigger-edge-type error has its quote | `8f6ead7`, `4549021` |
| `6733938` | The last clock tick lasts one period of the slowest clock limit, or twice the longest minimum high time, with a test | `738bc7a` |
| `5793ff7` | A value beyond an output's limits by round-off, at most 1e-9 of their range, is clipped, not refused | `4549021` |
| `28afb52` | Static digital outputs and shutters start at `t0`; `DDS.pulse` always ends at zero amplitude, and `print_summary` works without a frequency; a DDS copies its `digital_gate` dict | `4549021` |
| `f4adf7d` | Clock-limit, high-time and stop-time errors name the outputs at each time | `4549021` |
| `fc29707` | No `from pylab import *`: scripts import numpy themselves | `7403564`, `45db558` |
| `c08c187`, `4007ca9` | Python 3.13 or later, the suite's floor (Ian) | `fe761f9`, raised |
| `e8c33f7` | `set_passed_properties` binds arguments with a signature made once | `98edcdc` |
| `0bc9763` | A device finds its pseudoclock device once, kept in a declared attribute | `8b0349a`, the cache only |

## Not taken

- `4549021`'s rounding of tick counts and time differences, and the speed-ups
  `f5fd7eb` and `ceb469f`: they rework timing code the fork has replaced, and
  are left to CompilerCleanup.
- The rest of `8b0349a` (the labscript-names and module-path caches), and
  `6dd7306`: the fork already writes property keys in declaration order, so its
  reordering does not apply, and its speed-up was not chosen.
- `StaticDDS.enable` and `disable` without a time: the fork requires a time
  (Ian).
- CI workflow syncs.

The rest of upstream's commits were already in the fork in other forms.

## Checks

- labscript's suite passes (14), and labscript-devices' (35, 1 skipped).
- The shot sweep, `ca6ce6d` against `c08c187`, with labscript-devices and
  zprocess pinned: every difference is intended. The `upstream_stage` cases
  show each fix. The final-tick change alters the last one to three rows of
  every pulse program, and nothing else.
- The two speed-ups compile every shot in the sweep identically: `21f061f`
  against `0bc9763`, 84 identical and 41 same refusal of 125.
