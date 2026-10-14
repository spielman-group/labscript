# Known issues

- `outputs.py`, `Output.expand_timeseries`: ramp values are evaluated at sample times that are differences of absolute float times, so compiled values carry float noise in their last bit, in either direction; counting each sample's time within the ramp in whole clock ticks would make them exact.
- `outputs.py`, `Trigger.trigger`: a trigger clocked by a secondary pseudoclock whose rise and fall land on one tick is not refused, since a secondary's times are rounded to ticks only in `offset_instructions_from_trigger`, which warns and keeps the fall, losing the trigger.
- `core.py`, `Pseudoclock.collect_change_times`: `stop(t)` exactly one minimum update interval after a clock line's last instruction is refused, since float noise in the quantised times makes the gap a fraction short.
- `outputs.py`, `Output.add_instruction`: on a secondary pseudoclock, a ramp replaced by an instruction on its own tick but at a different time still refuses a later ramp inside its interval, since a secondary's ticks are known only after its trigger offsets.
