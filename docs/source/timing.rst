Timing and clock ticks
======================

Every output is clocked by a pseudoclock, which can change outputs only on its ticks, multiples of its ``clock_resolution``. labscript rounds every time a script gives to a tick, and every check that compares times compares ticks.

* On the master pseudoclock, a time is rounded to a tick when the instruction is added.
* A secondary pseudoclock counts its ticks from its trigger, which labscript knows only once all triggers are known. Its times are kept as given, then rounded to its ticks once, when its trigger delays are applied.
* Trigger and wait times are on the ticks of the pseudoclock that fires the trigger.

Ramps
-----

A ramp is sampled from its start up to, but not including, its end. The end belongs to the next instruction on that output. If no instruction falls on the end's tick, labscript adds one there that holds the ramp's final value.

The sample period is rounded to a whole number of ticks, and the last step is shortened or lengthened so that the next instruction lands on time. A ramp can therefore hold a few more or fewer samples than ``samplerate`` × ``duration``. Its values are computed for the times the hardware plays.

Two instructions in one tick
----------------------------

Two instructions on one output that fall on the same tick cannot both be played. labscript prints a warning naming both, and keeps the later one.

A trigger is different, since a lost edge stops a device from running. :py:meth:`Trigger.trigger <labscript.outputs.Trigger.trigger>` raises an error if a trigger is shorter than one tick, so that its rise and fall would land on the same tick. Two triggers whose gap is shorter than one tick count as overlapping, which also raises.

Residual float noise
--------------------

Ramp values are computed at sample times that are differences of absolute floating-point times. Compiled values therefore carry float noise in their last bit, in either direction: at most the last bit of a 32-bit value in a device's table. Counting each sample's time within the ramp in whole ticks would make every value exact, but this is not done yet.
