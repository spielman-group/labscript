Possible improvements
=====================

Improvements judged worth making, but larger than a small change.

* **Checking clock-line connections.** A :py:class:`ClockLine <labscript.core.ClockLine>` names its output on the pseudoclock device in ``connection``, but labscript does not check the name. A mistyped connection fails only later, when the device parses it in ``generate_code``, often as an unclear ``ValueError``. Only each device knows its valid names, so each pseudoclock device would declare them, and :py:meth:`Pseudoclock.add_device <labscript.core.Pseudoclock.add_device>` would check them.
* **Triggering one pseudoclock of a device.** labscript triggers a pseudoclock device as a whole, with one list of trigger times. A device whose pseudoclocks have separate trigger inputs, such as the PrawnBlaster's ``in_pins``, could have each triggered on its own, but trigger times would then have to be kept per pseudoclock throughout the compiler.
* **Exact ramp values.** Ramp values carry float noise in their last bit (see :doc:`timing`). Counting each sample's time within the ramp in whole clock ticks would make them exact.
