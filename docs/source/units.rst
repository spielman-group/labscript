Units
=====

An output's values are in its hardware's base units, such as volts for an analog output, unless the output has a unit conversion class. Then any instruction can give its value in one of the class's units instead::

    AnalogOut(
        name='coil_current', parent_device=ni_card, connection='ao0',
        unit_conversion_class=BidirectionalCoilDriver,
        unit_conversion_parameters={'slope': 2, 'shift': 0},
    )
    ...
    coil_current.constant(t, 3, units='A')

labscript converts values to base units: a constant when it is added, and a ramp's samples when they are computed. The output's limits apply to the converted values. A DDS takes a class for each of its quantities: ``freq_conv_class``, ``amp_conv_class`` and ``phase_conv_class``, each with its own parameters.

The classes live in :py:mod:`labscript_utils.unitconversions`. Each subclasses ``UnitConversion``, names its ``base_unit`` and its ``derived_units``, and defines ``<unit>_to_base`` and ``<unit>_from_base`` for each derived unit. BLACS uses the same class to show the output in any of its units.
