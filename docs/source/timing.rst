Timing and clock ticks
======================

Every output is clocked by a pseudoclock, which can change outputs only on its ticks, multiples of its ``clock_resolution``. labscript rounds the times a script gives to these ticks.

* On the master pseudoclock, a time is rounded to a tick when the instruction is added, and the checks on it compare ticks.
* A secondary pseudoclock counts its ticks from its trigger, which labscript knows only once all triggers are known. Its times are kept as given, then rounded to its ticks once, when its trigger delays are applied. Until then, the checks made when an instruction is added compare its times as given, and the later checks compare them rounded to its tick spacing.
* A trigger's time is rounded the way the clock that fires it rounds its own times. The wait table in the shot file keeps wait times as the script gave them.

Ramps
-----

A ramp is sampled from its start up to, but not including, its end. The end belongs to the next instruction on that output. If no instruction falls on the end's tick, labscript adds one there that holds the ramp's final value.

The sample period is rounded to a whole number of ticks, at least one, and the last step is shortened or lengthened so that the next instruction lands on time. A ramp can therefore hold a few more or fewer samples than ``samplerate`` × ``duration``. Each value is computed at the midpoint of the sample the hardware plays, measured from the ramp's start tick. The ramp keeps the duration it was given, so its ticks can run past its end by up to a tick; a sample whose midpoint is past the end holds the final value.

Two instructions in one tick
----------------------------

Two instructions on one output that fall on the same tick cannot both be played. labscript prints a warning and keeps the one added last.

A trigger is different, since a lost edge stops a device from running. :py:meth:`Trigger.trigger <labscript.outputs.Trigger.trigger>` raises an error if a trigger's rise and fall would land on the same tick. Two triggers whose edges would land on the same tick count as overlapping, which also raises. These checks cover triggers clocked by the master pseudoclock only.

Residual float noise
--------------------

Ramp values are computed at sample times that are differences of absolute floating-point times, so compiled values carry float noise in their last bits, in either direction. Typically this is the last bit of a 32-bit value in a device's table, and it grows with the slope of the ramp. Counting each sample's time within the ramp in whole ticks would make every value exact, but this is not done yet.
