# Design review: timing and ramps

Are the ramp fixes patches on a bad design? Mostly yes. Of the 19 timing faults
found so far, 16 come from one cause: a time is held in four representations,
converted between them at a dozen places, and each fix aligned one comparison.
Section 3 proposes one representation and compares it with fixing the three open
faults in place.

## 1. Map

Origin: **U** upstream (`master`); **E** this campaign's earlier rounds (da265dc,
9da73ba, 8b37365, 283da78); **R** the rounds 8221c8b…4edefc5.

| Step | What it does to a time | Origin |
| --- | --- | --- |
| `Output.add_instruction` | Master: start and ramp ends rounded to master ticks (`_round_time`). Secondary: kept as given. | U rounded all to 0.1 ns; E |
| `add_instruction`, same tick | `time in self.instructions`: rounded floats on the master, raw floats on a secondary. | U; E |
| `add_instruction`, ramp overlap | `start < time < end` on the stored floats. | U; R reads `instructions` |
| `add_instruction`, sub-tick ramp | Requested end < requested start + one tick, or rounded ends equal. | R (4edefc5) |
| `_add_ramp` | Function built with the requested duration, measured from the rounded start; `span` likewise. | U `round(t+d,10)-round(t,10)`; E |
| `Trigger.trigger` | Rise and fall rounded and compared; master clock only. | E (9da73ba) |
| `PseudoclockDevice.trigger`, `set_initial_trigger_time` | Trigger times rounded on the firing clock's ticks. | U 0.1 ns; E (283da78) |
| `_trigger_offset` | `T0 + k·delay`, k the triggers on an earlier tick of the clock as it ran to them. | R (8221c8b) |
| `Output.do_checks` | `quantise(t - _trigger_offset(t))` for the start value, end holds and kept-per-tick; trigger-in-ramp and too-soon-after compare `quantise(t - offset)`. | U raw floats; R (8221c8b, ea8eed5) |
| `Output.offset_instructions_from_trigger` | Key `quantise(t - offset(t))`; ramp start by its offset, end by its own; same tick keeps the last call. | U; R (68b4298, f516187) |
| `PseudoclockDevice.offset_instructions_from_trigger` | Trigger times and stop time less `T0 + i·delay`, quantised. | U |
| `Pseudoclock.collect_change_times` | Quantised again; `set()` of floats; ramp interiors by float `<`; `dt < 1/clock_limit`, `abs(stop - last) < 1/clock_limit`, `dt < 2·high_time` in float seconds. | U |
| `Pseudoclock.expand_change_times` | Period `round(1/rate/res)·res`, which can be 0; `divmod(gap·rate, 1)`; squeeze `remainder/rate ≥ 1/limit`; `np.linspace` ticks; `time in trigger_times[1:]` for WAIT. | U |
| `Output.make_timeseries` | Float `>=` of change times. | U |
| `Output.expand_timeseries` | Midpoints `time + ½(time[1]-time[0])`, last from the next change time; value `f(midpoint - initial time)`, a difference of absolute floats. | U |
| Device code (labscript-devices) | `int(round(step/clock_resolution))` or `np.rint(diff(times)/res)` back to ticks: PineBlaster, PrawnBlaster, PrawnDO, DummyPseudoclock, Cicero. | U |

## 2. Diagnosis

Four representations are in use:

- **S**, requested seconds on the master's axis, as the script gives them;
- **M**, master ticks, held as floats `k·res`;
- **O**, the output's own ticks: on a secondary, `(t - T0 - k·delay)/res`,
  known only once every wait is declared;
- **F**, floats re-derived from M or O in the pseudoclock, which devices round
  back to O.

`add_instruction` works in M on the master and S on a secondary. `_add_ramp`
defines the ramp in S (its duration) anchored in M or O (its start).
`do_checks` computes O ad hoc at each comparison; `offset_instructions_from_trigger`
produces O as floats; the pseudoclock assumes F floats are exact multiples of a
tick and compares them for equality; `expand_timeseries` samples an S-defined
function on an O grid. There is no single point where a time becomes a tick.
Upstream deferred all of it and rounded to 0.1 ns meanwhile; the campaign moved
rounding forward for the master only, since a secondary's ticks are not known
until its waits are.

| Fault | Mismatch |
| --- | --- |
| End hold a fraction of a tick before the next instruction (da265dc) | checks in S at 0.1 ns, playback in M |
| Trigger rise and fall in one tick lost (9da73ba) | S compared, M played |
| Secondary times a tick off (8b37365) | M used where O is needed |
| Secondary trigger times on the wrong clock (283da78) | M against O |
| Three validation faults: start value replaced, value after a wait late, end hold replacing a user value (8221c8b) | checks in M, playback in O |
| A replaced ramp's interval kept (8221c8b) | a second record of ramps, not updated (not representation) |
| Of distinct times on one tick, the later call lost (f516187) | keyed by S, merged in O |
| Ramp end offset by its start's trigger count (68b4298) | one ramp converted to O with two offsets |
| Ramp on a trigger's tick, inside the delay (ea8eed5) | O tick equality hid an S time in the delay |
| Sub-tick ramps: `IndexError`, values past the end (4edefc5) | duration in S, span in O |
| **Open:** 25.2 ns ramp outputs 1.488 | duration in S, samples on O |
| **Open:** sample period under half a tick, `ZeroDivisionError` | a missing floor of one tick (not representation) |
| **Open:** zero-length linear ramp, `ZeroDivisionError` | the function is built before any check (order, not representation) |
| `stop(t)` one interval after the last instruction refused | F subtraction against a float limit |
| Secondary: a replaced ramp still blocks a later one | overlap checked in S, replacement made in O |
| Secondary trigger in one tick not refused | refusal needs O, unknown at the call |
| Float noise in ramp values | S differences of absolute times |

The first open fault is an algorithm error, as Ian suspected. The function's
end is `start_rounded + duration`, in S; the ramp's last tick is `end_rounded`,
in O, up to a tick later or earlier. Where the shortest step is under two ticks the last
midpoint passes the function's end. It is not confined to sub-tick-scale
ramps: on the test secondary (25 ns ticks, 6 ns delay, 40 MHz), a 1000.2 ns
ramp from 0 to 1 at 5018.4 ns outputs 1.0123, on `Development` too. A clock
whose shortest step is under two ticks is unusual (in labscript-devices, the
PulseBlaster ESR-Pro 200's 5 ns ticks at 200 MHz allow it), but the mismatch is
there on every clock: the ramp reaches its final value up to a tick before or
after its end.

Small cases run for this review, on `CodeHealth`: the 25.2 ns and 1000.2 ns
overshoots; `ZeroDivisionError` at 1 GHz on the master and 100 MHz on the
secondary; `ZeroDivisionError` for `ramp(t, 0, …)` while `sine_ramp(t, 0, …)`
gets the sub-tick `LabscriptError`; `stop(0.3 + 1e-6)` refused while 0.1, 0.7,
1.1 and 2.3 pass; a replaced secondary ramp refusing a later one, the same shot
on the master accepted; and all ten samples of a 10 µs ramp at t = 0.3 s off by
up to 7e-12.

## 3. Proposal

**One conversion, then integers.** `add_instruction` records the requested time
and the instruction, in call order, and keeps only checks that need no tick:
`start()` called, limits, units, ramping allowed, a nonzero sample rate. At
compile, once trigger times are final, one function turns each requested time
into an integer tick of the output's own clock,
`round((t - T0 - k·delay)/res)`, with k from `_trigger_offset` (on the master
T0 and the delay are 0). Trigger times become ticks of the firing and the
triggered clock the same way. Nothing else converts a float to a tick.

- Instructions are a dict of tick to instruction, filled in call order, so the
  last call on a tick wins and warns, on the master and secondaries alike.
- A ramp is a start tick, a tick count n ≥ 1 and a sample period p =
  `max(1, round(1/(rate·res)))` ticks. Samples are at `start + j·p`, values at
  `(j·p + p/2)·res` from the start, the last at the midpoint to the next change
  tick. This is the integer-tick improvement `timing.rst` describes.
- Every check compares integers: start value, end holds, collisions, ramp
  overlap, ramp across a trigger, too soon after a trigger, sub-tick ramps, and
  the minimum interval as `m = ceil(1/(clock_limit·res))` ticks, computed once
  with a tolerance.
- `collect_change_times` and `expand_change_times` work on integer ticks:
  sets, `divmod` and `arange` are exact.
- At the device boundary nothing changes: `times`, the clock's `start` and
  `step`, `stop_time`, `trigger_times` and `raw_output` stay float seconds,
  `tick·res`, and devices that round back get the exact tick.

**Replaces** `_round_time`, `_requested_times`, the per-check tick closures in
`do_checks`, the two offsets in `offset_instructions_from_trigger`, the
requested-time sub-tick test, the float `set` and comparisons in
`collect_change_times`, `linspace` and float `divmod` in `expand_change_times`,
and absolute-time midpoints in `expand_timeseries`. **Size:** the pipeline is
about 900 code lines in 20 methods; some 600 are rewritten into about 450, a
diff of roughly 1,000 lines, plus about ten behaviour tests. labscript-devices:
PrawnDO passes float `times` to `make_timeseries` and needs a one-line change.

**User-visible changes.** No script, shot-file layout or device interface
changes. The seven faults in section 2 that are still open are gone by
construction: each becomes a `LabscriptError` or compiles. Collision warnings
and ramp-overlap errors on the master come at `stop()`, not at the call. Every
ramp's values change in their last bits, so "identical shot files" stops being
the regression check; a tolerance comparison replaces it. One decision is
Ian's, the ramp's definition on its ticks:

- (a) the function spans the ramp's ticks, so it starts and ends exactly where
  the hardware does, and its slope changes by up to a tick in the duration
  (2.5% for the 1000.2 ns case on 25 ns ticks, 2.5e-5 for 1 ms); or
- (b) it keeps the requested duration, and samples past its end take the final
  value, so the slope is as asked and the last samples hold.

Both end the overshoot. (a) matches how every other time is rounded.

**Against fixing in place.** The three open faults are about ten lines: clamp or
rescale the sample times (the same a-or-b decision), floor the period at one
tick, and refuse a zero duration before the function is built. That is a day's
work with identical shot files elsewhere. It leaves four open faults of the
same kind, and every future check must again choose the right representation
at its comparison, which is how the last rounds' five code commits arose. The rewrite is the
compiler's most cross-cutting code, needs a validation pass like this
campaign's, moves the fork further from upstream, and cannot go to
`UpstreamBugFixes`.

**Recommendation:** the rewrite, as its own effort, with the three fixes inside
it. If it waits, the in-place fixes are cheap and lose nothing, provided (a) or
(b) is chosen once and kept.
