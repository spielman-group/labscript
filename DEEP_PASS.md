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
| `3de300b` | Change-time intervals checked with numpy and rounded to 0.1 ns; `stop(t)` one interval after the last instruction compiles, with a test | `f5fd7eb`, `4549021` |
| `24427be` | Each clock line's ramps found once, waits looked up in a set; a ramp's tick count rounded to nine places | `f5fd7eb`, `4549021` |
| `0c520ce` | `make_timeseries` finds each change time's instruction with searchsorted | `f5fd7eb` |
| `e521161` | `Output.do_checks` gets the trigger delay once | `f5fd7eb` |
| `efcb901` | `set_passed_properties` returns the function when it has no properties, and binds arguments only when needed | `6dd7306` |
| `16fed4f` | Imported modules' absolute paths kept between shots | `8b0349a` |
| `4e4e371` | The release workflow, as upstream's | `adee8c1`, `cd154a1` |
| `9b4252c` | `StaticDDS.enable` and `disable` with no time act from the start of the shot (Ian), with a test | `4549021` |
| `a37f97c` | `round_time` rounds a scalar time to 0.1 ns; the stop-time gap uses it, the array checks keep `np.round` | `ceb469f` |
| `86d1195` | Trigger offsets precomputed, and each time's found by bisection over the same tick test; identical to the loop on 122,730 times | `f5fd7eb` |
| `e779ec3` | A device may not take a name that `from labscript import *` defines, checked against a cached set, with a test | `0f5ab3b`, `8b0349a` |

## Offered upstream

`UpstreamBugFixes` (`22af9d2`, on `b0c132c`) offers the fork's one shared
`_check_name` for device and global names, which upstream checks in two places
with different messages.

Every other upstream commit is ported or was already in the fork in another
form.

## Checks

- labscript's suite passes (14), and labscript-devices' (35, 1 skipped).
- The shot sweep, `ca6ce6d` against `c08c187`, with labscript-devices and
  zprocess pinned: every difference is intended. The `upstream_stage` cases
  show each fix. The final-tick change alters the last one to three rows of
  every pulse program, and nothing else.
- The two speed-ups compile every shot in the sweep identically: `21f061f`
  against `0bc9763`, 84 identical and 41 same refusal of 125.
- The rest of the stage compiles every shot in the sweep identically: `1653bba`
  against `e521161`, 84 identical and 41 same refusal of 125.
- `StaticDDS`, `round_time` and the bisection compile every shot in the sweep
  identically: `e8605c2` against `86d1195`, 84 identical and 41 same refusal of
  125.
- The device-name check compiles every shot in the sweep identically: `e1b89e0`
  against `e779ec3`, 84 identical and 41 same refusal of 125.
