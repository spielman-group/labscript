# Known issues

- `outputs.py`, `Output.expand_timeseries`: ramp values are evaluated at sample times that are differences of absolute float times, so compiled values carry float noise in their last bit, in either direction; counting each sample's time within the ramp in whole clock ticks would make them exact.
- `outputs.py`, `Trigger.trigger`: a trigger clocked by a secondary pseudoclock whose rise and fall land on one tick is not refused, since a secondary's times are rounded to ticks only in `offset_instructions_from_trigger`, which warns and keeps the fall, losing the trigger.
- `core.py`, `Pseudoclock.collect_change_times`: `stop(t)` exactly one minimum update interval after a clock line's last instruction is refused, since float noise in the quantised times makes the gap a fraction short.
- `outputs.py`, `Output.add_instruction`: on a secondary pseudoclock, a ramp replaced by an instruction on its own tick but at a different time still refuses a later ramp inside its interval, since a secondary's ticks are known only after its trigger offsets.
- `outputs.py`, `Output.expand_timeseries`: a ramp whose start rounds down to a tick and whose end rounds up is stretched by up to a tick, so on a clock whose shortest step is under two ticks its last value can pass its final value (a 25.2 ns ramp from 0 to 1 at 5018.4 ns, on a 6 ns-delay secondary with 25 ns ticks, outputs 1.488). Also upstream.
- `core.py`, `Pseudoclock.expand_change_times`: a ramp whose sample period is under half a tick has it rounded to zero and raises `ZeroDivisionError`, not a `LabscriptError`. Also upstream.
- `functions.py`, `ramp`: a linear ramp of zero duration raises `ZeroDivisionError` when built, before `Output.add_instruction` can refuse it as shorter than a tick. Also upstream.
