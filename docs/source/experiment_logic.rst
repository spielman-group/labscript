Experiment Logic
================

After the connection table, a script calls :py:func:`start() <labscript.labscript.start>`, commands its outputs, and ends with :py:func:`stop() <labscript.labscript.stop>`. Each command takes the time, in seconds from the start of the shot, at which it happens.

A running time variable
-----------------------

Most scripts keep a variable, conventionally ``t``, for the current time, and move it forward as they go. Ramps return how long they take, so ``t`` can follow them::

    start()
    t = 0
    analog_out.constant(t, 0)
    t += 1e-3
    t += analog_out.ramp(t, duration=10e-3, initial=0, final=1, samplerate=1e5)
    digital_out.go_high(t)
    t += 5e-3
    stop(t)

Commands need not be given in time order: labscript sorts them. How times are rounded to the clock is described in :doc:`timing`.

Waits
-----

:py:func:`wait(label, t, timeout=5) <labscript.labscript.wait>` pauses every pseudoclock at ``t`` until an external trigger resumes them, or until ``timeout`` seconds have passed. A wait takes no time on the script's timeline: the commands after it run as though no time passed. ``wait`` returns the time the pseudoclocks need to resume, which a script adds to ``t`` before its next command.

Ending the shot
---------------

:py:func:`stop(t) <labscript.labscript.stop>` ends the shot at ``t`` and compiles it. Outputs hold their last values until then. ``t`` must be the time of each clock line's last instruction, or at least one minimum update interval of that clock line after it.

Secondary pseudoclocks
----------------------

A secondary pseudoclock starts when the master triggers it. Calling its ``set_initial_trigger_time(t)`` before :py:func:`start() <labscript.labscript.start>` delays that first trigger, so that its program need not cover the time before it is needed.
