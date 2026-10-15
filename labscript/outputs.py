#####################################################################
#                                                                   #
# /outputs.py                                                       #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Classes for devices channels that are outputs"""

import sys
import warnings

import numpy as np

from . import functions
from .base import Device
from .compiler import compiler
from .constants import *
from .core import TriggerableDevice
from .utils import LabscriptError, set_passed_properties


def _renamed_keyword(kwargs, old, new, value):
    """Return `kwargs[old]` if given, warning that it will be removed, else `value`."""
    if old not in kwargs:
        return value
    warnings.warn(
        f"{old} will be removed from labscript; use {new}.", FutureWarning, stacklevel=3
    )
    return kwargs.pop(old)


class Output(Device):
    """Base class for all output classes."""

    description = "generic output"
    allowed_states = None
    dtype = np.float64
    scale_factor = 1

    @set_passed_properties(property_names={})
    def __init__(
        self,
        name,
        parent_device,
        connection,
        limits=None,
        unit_conversion_class=None,
        unit_conversion_parameters=None,
        default_value=None,
        **kwargs
    ):
        """Instantiate an Output.

        Parameters
        ----------
        name : str
            python variable name to assign the Output to.
        parent_device : :obj:`IntermediateDevice`
            Parent device the output is connected to.
        connection : str
            Channel of parent device output is connected to.
        limits : tuple, optional
            `(min,max)` allowed for the output.
        unit_conversion_class : :obj:`labscript_utils:labscript_utils.unitconversions`, optional
            Unit conversion class to use for the output.
        unit_conversion_parameters : dict, optional
            Dictionary or kwargs to pass to the unit conversion class.
        default_value : float, optional
            Default value of the output if no output is commanded.
        **kwargs
            Passed to :meth:`Device.__init__`.

        Raises
        ------
        LabscriptError
            Limits tuple is invalid or unit conversion class units don't line up.
        """
        super().__init__(name, parent_device, connection, **kwargs)

        self.instructions = {}
        # The time each instruction was asked for, by the tick it was rounded to:
        self._requested_times = {}
        if default_value is not None:
            self.default_value = default_value
        if not unit_conversion_parameters:
            unit_conversion_parameters = {}
        self.unit_conversion_class = unit_conversion_class
        self.set_properties(
            unit_conversion_parameters,
            {"unit_conversion_parameters": list(unit_conversion_parameters.keys())}
        )

        if unit_conversion_class is not None:
            self.calibration = unit_conversion_class(unit_conversion_parameters)
            for units in self.calibration.derived_units:
                # Each defined unit type needs conversions to and from base units.
                if not hasattr(self.calibration, f"{units}_to_base"):
                    raise LabscriptError(
                        f'The function "{units}_to_base" does not exist within the '
                        f'calibration "{self.unit_conversion_class}" used in output '
                        f'"{self.name}"'
                    )
                if not hasattr(self.calibration, f"{units}_from_base"):
                    raise LabscriptError(
                        f'The function "{units}_from_base" does not exist within the '
                        f'calibration "{self.unit_conversion_class}" used in output '
                        f'"{self.name}"'
                    )

        # A later conditional relies on self.limits being either a correct tuple or
        # None, so None is told apart from False here.
        if limits is not None:
            if not isinstance(limits, tuple) or len(limits) != 2:
                raise LabscriptError(
                    f'The limits for "{self.name}" must be tuple of length 2. '
                    'Eg. limits=(1, 2)'
                )
            if limits[0] > limits[1]:
                raise LabscriptError(
                    "The first element of the tuple must be lower than the second "
                    "element. Eg limits=(1, 2), NOT limits=(2, 1)"
                )
        self.limits = limits

    @property
    def clock_limit(self):
        """float: The parent clock line's clock limit."""
        parent = self.parent_clock_line
        return parent.clock_limit

    @property
    def trigger_delay(self):
        """float: The earliest time output can be commanded from this device after a
        trigger. This is nonzero on secondary pseudoclocks due to triggering delays.
        """
        parent = self.pseudoclock_device
        if parent.is_master_pseudoclock:
            return 0
        else:
            return parent.trigger_delay

    @property
    def wait_delay(self):
        """float: The earliest time output can be commanded from this device after a
        wait.

        It is the trigger delay of this output's pseudoclock device, plus, on the
        master pseudoclock, compiler.wait_delay: the master does not resume the
        secondary clocks until that long after a wait, so that they are ready for the
        trigger even after an extremely short wait.
        """
        delay = (
            compiler.wait_delay if self.pseudoclock_device.is_master_pseudoclock else 0
        )
        return self.trigger_delay + delay

    def get_all_outputs(self):
        """Get all children devices that are outputs.

        For ``Output``, this is `self`.

        Returns
        -------
        list
            List of children :obj:`Output`.
        """
        return [self]

    def apply_calibration(self, value, units):
        """Apply the calibration defined by the unit conversion class, if present.

        Parameters
        ----------
        value : float
            Value to apply calibration to.
        units : str
            Units to convert to. Must be defined by the unit conversion class.

        Returns
        -------
        float
            Converted value.

        Raises
        ------
        LabscriptError
            If no unit conversion class is defined or `units` not in that class.
        """
        if self.unit_conversion_class is None:
            raise LabscriptError(
                'You can not specify the units in an instruction for output '
                f'"{self.name}" as it does not have a calibration associated with it'
            )

        if units not in self.calibration.derived_units:
            raise LabscriptError(
                f'The units "{units}" does not exist within the calibration '
                f'"{self.unit_conversion_class}" used in output "{self.name}"'
            )

        return getattr(self.calibration, units + "_to_base")(value)

    def instruction_to_string(self, instruction):
        """Get a human readable description of an instruction.

        Parameters
        ----------
        instruction : dict or str
            Instruction to get description of, or a fixed instruction defined in
            :attr:`allowed_states`.

        Returns
        -------
        str
            Instruction description.
        """
        if isinstance(instruction, dict):
            return instruction["description"]
        elif self.allowed_states:
            return str(self.allowed_states[instruction])
        else:
            return str(instruction)

    def add_instruction(self, time, instruction, units=None):
        """Add a hardware instruction to the device instruction list.

        Parameters
        ----------
        time : float
            Time, in seconds, that the instruction begins.
        instruction : dict or float
            Instruction to add.
        units : str, optional
            Units instruction is in, if `instruction` is a `float`.

        Raises
        ------
        LabscriptError
            If time requested is not allowed or samplerate is too fast.
        """
        if not compiler.start_called:
            raise LabscriptError("Cannot add instructions prior to calling start()")
        requested = time
        time = self._round_time(time)
        if isinstance(instruction, dict):
            requested_end = instruction["end time"]
            for key in ("end time", "initial time"):
                instruction[key] = self._round_time(instruction[key])
        # Check that time is not negative or too soon after t=0:
        if time < self.t0:
            raise LabscriptError(
                f"{self.description} {self.name} has an instruction at t={time}s. "
                "Due to the delay in triggering its pseudoclock device, the earliest "
                f"output possible is at t={self.t0}."
            )
        # Check that this doesn't collide with previous instructions:
        if time in self.instructions.keys():
            previous = self._requested_times[time]
            if previous != requested:
                asked = (
                    f" (asked for at t={previous}s and t={requested}s, which fall on "
                    "one tick)"
                )
            else:
                asked = ""
            if not compiler.suppress_all_warnings:
                current_value = self.instruction_to_string(self.instructions[time])
                new_value = self.instruction_to_string(
                    self.apply_calibration(instruction, units)
                    if units and not isinstance(instruction, dict)
                    else instruction
                )
                sys.stderr.write(
                    f"WARNING: State of {self.description} {self.name} at t={time}s "
                    f"has already been set to {current_value}. Overwriting to "
                    f"{new_value}{asked}. (note: all values in base units where "
                    "relevant)\n"
                )
        # Check that ramps don't collide
        if isinstance(instruction, dict):
            # No ramps allowed if this output is on a slow clock:
            if not self.parent_clock_line.ramping_allowed:
                raise LabscriptError(
                    f"{self.description} {self.name} is on clockline that does not "
                    "support ramping. It cannot have a function ramp as an instruction."
                )
            # A ramp at this same time is being replaced, so does not count.
            for start, other in self.instructions.items():
                if not isinstance(other, dict) or start == time:
                    continue
                end = other["end time"]
                if start < time < end or start < instruction["end time"] < end:
                    start_value = self.instruction_to_string(other)
                    new_value = self.instruction_to_string(instruction)
                    raise LabscriptError(
                        f"State of {self.description} {self.name} from t = {start}s to "
                        f"{end}s has already been set to {start_value}. Cannot set to "
                        f"{new_value} from t = {time}s to {instruction['end time']}s."
                    )
            if time > instruction["end time"]:
                raise LabscriptError(
                    f"{self.description} {self.name} has been passed a function ramp "
                    f"{self.instruction_to_string(instruction)} with a negative "
                    "duration."
                )
            # A ramp shorter than a tick, or whose ends round to one tick, cannot be
            # sampled. Requested times are compared, so that float noise does not
            # refuse a ramp exactly one tick long.
            resolution = self.pseudoclock_device.clock_resolution
            if (
                requested_end < requested + resolution
                or time == instruction["end time"]
            ):
                raise LabscriptError(
                    f"{self.description} {self.name} has a ramp "
                    f"{instruction['description']} at t={requested}s lasting "
                    f"{requested_end - requested:g}s, which does not span a tick "
                    f"({resolution}s) of {self.pseudoclock_device.name}. Make it "
                    "longer than one tick."
                )
            if instruction["clock rate"] == 0:
                raise LabscriptError("A nonzero sample rate is required.")
        else:
            if units is not None:
                instruction = self.apply_calibration(instruction, units)
            if self.limits:
                if (instruction < self.limits[0]) or (instruction > self.limits[1]):
                    raise LabscriptError(
                        f"You cannot program the value {instruction} (base units) to "
                        f"{self.name} as it falls outside the limits "
                        f"({self.limits[0]} to {self.limits[1]})"
                    )
        # Re-insert, so that dict order is call order: of instructions on
        # one secondary tick, the one added last is kept.
        self.instructions.pop(time, None)
        self.instructions[time] = instruction
        self._requested_times[time] = requested

    def _round_time(self, t):
        """Round `t` to this output's ticks if its pseudoclock is the master.

        The master's ticks are known now. A secondary's times are rounded to its ticks
        once its trigger offsets are known, in `offset_instructions_from_trigger`.
        """
        pseudoclock = self.pseudoclock_device
        if pseudoclock is not None and pseudoclock.is_master_pseudoclock:
            return self.quantise_to_pseudoclock(t)
        return t

    def _trigger_offset(self, t, trigger_times):
        """The time to subtract from `t` to put it on this output's own clock.

        It is the first trigger time plus a trigger delay for each trigger before `t`.
        A trigger is before `t` if `t` falls on a later tick of the clock as it ran up
        to that trigger.
        """
        tick = self.quantise_to_pseudoclock
        offset = trigger_times[0]
        for trigger_time in sorted(trigger_times):
            if tick(t - offset) <= tick(trigger_time - offset):
                break
            offset += self.trigger_delay
        return offset

    def _add_ramp(
        self, t, duration, performed, description, samplerate, units, function, *args
    ):
        """Add a ramp from `t`, evaluating `function(duration, *args)` for the first
        `performed` seconds of it."""
        # Durations measured from the rounded start, on the same scale as the
        # sample times the function is evaluated at, so that their errors cancel:
        start = self._round_time(t)
        self.add_instruction(
            t,
            {
                "function": function((start + duration) - start, *args),
                "description": description,
                "initial time": t,
                "end time": t + performed,
                "span": (start + performed) - start,
                "clock rate": samplerate,
                "units": units,
            },
        )

    def do_checks(self, trigger_times):
        """Basic error checking to ensure the user's instructions make sense.

        Parameters
        ----------
        trigger_times : iterable
            Times to confirm don't conflict with instructions.

        Raises
        ------
        LabscriptError
            If a trigger time conflicts with an instruction.
        """
        # With no instructions, hold the default value for all time.
        if not self.instructions:
            if (
                not compiler.suppress_mild_warnings
                and not compiler.suppress_all_warnings
            ):
                sys.stderr.write(
                    f"WARNING: {self.name} has no instructions. It will be set to "
                    f"{self.instruction_to_string(self.default_value)} for all time.\n"
                )
            self.add_instruction(self.t0, self.default_value)
        # With no instruction at the initial time, start at the default value.
        # Compare ticks of this output's own clock, which a secondary's times are
        # rounded to only once its trigger offsets are applied.
        quantise = self.quantise_to_pseudoclock

        def tick(t):
            return quantise(t - self._trigger_offset(t, trigger_times))

        if tick(self.t0) not in {tick(t) for t in self.instructions}:
            if (
                not compiler.suppress_mild_warnings
                and not compiler.suppress_all_warnings
            ):
                sys.stderr.write(
                    f"WARNING: {self.name} has no initial instruction. It will "
                    "initially be set to "
                    f"{self.instruction_to_string(self.default_value)}.\n"
                )
            self.add_instruction(self.t0, self.default_value)
        # A ramp with no instruction after it holds its final value. Of instructions
        # on one tick, the one added last is kept.
        kept = {tick(t): instruction for t, instruction in self.instructions.items()}
        for instruction in kept.values():
            if (
                isinstance(instruction, dict)
                and tick(instruction["end time"]) not in kept
            ):
                self.add_instruction(
                    instruction["end time"],
                    instruction["function"](instruction["span"]),
                    instruction["units"],
                )
        for trigger_time in trigger_times:
            # Ticks of the clock as it ran up to this trigger:
            offset = self._trigger_offset(trigger_time, trigger_times)
            trigger_tick = quantise(trigger_time - offset)
            for t, inst in self.instructions.items():
                t_tick = quantise(t - offset)
                # Check no ramps are happening at the trigger time:
                if (
                    isinstance(inst, dict)
                    and t_tick < trigger_tick < quantise(inst["end time"] - offset)
                ):
                    raise LabscriptError(
                        f"{self.description} {self.name} has a ramp "
                        f"{inst['description']} from t = {inst['initial time']} to "
                        f"{inst['end time']}. This overlaps with a trigger at "
                        f"t={trigger_time}, and so cannot be performed."
                    )
                # Check that nothing is happening during the delay after the trigger.
                # A ramp on the trigger's own tick runs after it, so is checked too:
                if (
                    (
                        trigger_tick < t_tick
                        or isinstance(inst, dict) and t_tick == trigger_tick
                    )
                    and quantise(t - offset - self.trigger_delay) < trigger_tick
                ):
                    raise LabscriptError(
                        f"{self.description} {self.name} has an instruction at t={t}. "
                        f"This is too soon after a trigger at t={trigger_time}, "
                        "the earliest output possible after this trigger is at "
                        f"t={trigger_time + self.trigger_delay}"
                    )

    def offset_instructions_from_trigger(self, trigger_times):
        """Put every instruction on this output's own clock, by its trigger offset.

        Parameters
        ----------
        trigger_times : iterable
            Times of all trigger events.
        """
        offset_instructions = {}
        sources = {}
        for t, instruction in self.instructions.items():
            offset = self._trigger_offset(t, trigger_times)
            if isinstance(instruction, dict):
                offset_instruction = instruction.copy()
                # A ramp starting on a trigger's tick runs after the trigger, so its
                # end takes its own offset, as its end hold does.
                end = instruction["end time"]
                offset_instruction["end time"] = self.quantise_to_pseudoclock(
                    end - self._trigger_offset(end, trigger_times)
                )
                offset_instruction["initial time"] = self.quantise_to_pseudoclock(
                    instruction["initial time"] - offset
                )
            else:
                offset_instruction = instruction

            new_time = self.quantise_to_pseudoclock(t - offset)
            if new_time in offset_instructions:
                # As in add_instruction: warn, and keep the one added last.
                if not compiler.suppress_all_warnings:
                    sys.stderr.write(
                        f"WARNING: {self.description} {self.name} has instructions "
                        f"at t={self._requested_times[sources[new_time]]}s and "
                        f"t={self._requested_times[t]}s, which fall on one tick, "
                        f"t={new_time}s, of {self.pseudoclock_device.name}. Keeping "
                        "the one added last.\n"
                    )
            offset_instructions[new_time] = offset_instruction
            sources[new_time] = t
        self.instructions = offset_instructions

    def get_change_times(self):
        """Get the times this output changes state.

        Called when the parent Pseudoclock requests them.

        Returns
        -------
        list
            List of times output changes values.
        """
        times = list(self.instructions.keys())
        times.sort()

        current_dict_time = None
        for time in times:
            if isinstance(self.instructions[time], dict):
                current_dict_time = self.instructions[time]
            elif (
                current_dict_time is not None
                and current_dict_time["initial time"]
                < time
                < current_dict_time["end time"]
            ):
                raise LabscriptError(
                    f"{self.description} {self.name} has an instruction at "
                    f"t={time:.10f}s. This instruction collides with a ramp on this "
                    "output at that time. The collision "
                    f"{current_dict_time['description']} is happening from "
                    f"{current_dict_time['initial time']:.10f}s untill "
                    f"{current_dict_time['end time']:.10f}s"
                )

        self.times = times
        return times

    def get_ramp_times(self):
        """Get the start and stop times of this output's ramps.

        Called when the parent Pseudoclock requests them.

        Returns
        -------
        list
            List of (start, stop) times of ramps for this Output.
        """
        return [
            (t, instruction["end time"])
            for t, instruction in self.instructions.items()
            if isinstance(instruction, dict)
        ]

    def make_timeseries(self, change_times):
        """Make the list of this output's states at each time in `change_times`.

        Called when the parent Pseudoclock requests it. `change_times` are the times
        that one or more connected outputs in the same pseudoclock change state. By
        state is meant the instruction the output has at that time, rather than its
        value: a single value, a reference to a function for a ramp, etc. The list of
        states is stored in `self.timeseries` rather than returned.
        """
        self.timeseries = []
        i = 0
        time_len = len(self.times)
        for change_time in change_times:
            while i < time_len and change_time >= self.times[i]:
                i += 1
            self.timeseries.append(self.instructions[self.times[i - 1]])

    def expand_timeseries(self, all_times, flat_all_times_len):
        """Evaluate the ramp functions in `self.timeseries` at the times in `all_times`.

        This creates an array of output values at those times. These are the values
        that this output should update to on each clock tick, and are the raw values
        that should be used to program the output device. They are stored in
        `self.raw_output`.
        """
        # On a clock line without ramping, the timeseries is already fully expanded.
        if not self.parent_clock_line.ramping_allowed:
            self.raw_output = np.array(self.timeseries, dtype=np.dtype(self.dtype))
            return
        outputarray = np.empty((flat_all_times_len,), dtype=np.dtype(self.dtype))
        j = 0
        for i, time in enumerate(all_times):
            if np.iterable(time):
                time_len = len(time)
                if isinstance(self.timeseries[i], dict):
                    # Evaluate the functions at the midpoints of the timesteps, to
                    # remove the zero-order hold error introduced by sampling an
                    # analog signal:
                    try:
                        midpoints = time + 0.5 * (time[1] - time[0])
                    except IndexError:
                        # A one-element time array has no step size; the final
                        # midpoint is determined differently anyway.
                        midpoints = np.zeros(1)
                    # The first clock tick after this ramp ends is an array element or
                    # a single number, depending on whether another ramp follows.
                    next_time = (
                        all_times[i + 1][0]
                        if np.iterable(all_times[i + 1])
                        else all_times[i + 1]
                    )
                    midpoints[-1] = time[-1] + 0.5 * (next_time - time[-1])
                    # These are differences of absolute float times, so values carry
                    # float noise in their last bit, either way. Counting each sample's
                    # time in the ramp in whole ticks would make them exact.
                    outarray = self.timeseries[i]["function"](
                        midpoints - self.timeseries[i]["initial time"]
                    )
                    if self.timeseries[i]["units"] is not None:
                        outarray = self.apply_calibration(
                            outarray, self.timeseries[i]["units"]
                        )
                    if self.limits:
                        if (
                            (outarray < self.limits[0]) | (outarray > self.limits[1])
                        ).any():
                            raise LabscriptError(
                                f"The function {self.timeseries[i]['function']} called "
                                f'on "{self.name}" at t={midpoints[0]} generated a '
                                "value which falls outside the base unit limits "
                                f"({self.limits[0]} to {self.limits[1]})"
                            )
                else:
                    outarray = np.empty(time_len, dtype=self.dtype)
                    outarray.fill(self.timeseries[i])
                outputarray[j : j + time_len] = outarray
                j += time_len
            else:
                outputarray[j] = self.timeseries[i]
                j += 1
        del self.timeseries  # don't need this any more.
        self.raw_output = outputarray


class AnalogQuantity(Output):
    """Base class for :obj:`AnalogOut`.

    It is also used internally by :obj:`DDS`. You should never instantiate this
    class directly. Its ramps need a clock line with `ramping_allowed`; on one
    without, only constant values can be set.
    """

    description = "analog quantity"
    default_value = 0

    def _check_truncation(self, truncation, min=0, max=1):
        if not (min <= truncation <= max):
            raise LabscriptError(
                f"Truncation argument must be between {min} and {max} (inclusive), but "
                f"is {truncation}."
            )

    def ramp(self, t, duration, initial, final, samplerate, units=None, truncation=1.):
        """Command the output to perform a linear ramp.

        Defined by
        `f(t) = ((final - initial)/duration)*t + initial`

        Parameters
        ----------
        t : float
            Time, in seconds, to begin the ramp.
        duration : float
            Length, in seconds, of the ramp.
        initial : float
            Initial output value, at time `t`.
        final : float
            Final output value, at time `t+duration`.
        samplerate : float
            Rate, in Hz, to update the output.
        units
            Units the output values are given in, as specified by the unit
            conversion class.
        truncation : float, optional
            Fraction of ramp to perform. Must be between 0 and 1.

        Returns
        -------
        float
            Length of time ramp will take to complete.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            # If start and end value are the same, there is no need to ramp, and the
            # sample ticks etc. are saved.
            if initial == final:
                self.constant(t, initial, units)
                if (
                    not compiler.suppress_mild_warnings
                    and not compiler.suppress_all_warnings
                ):
                    sys.stderr.write(
                        f"WARNING: {self.__class__.__name__} '{self.name}' has the "
                        f"same initial and final value at time t={t:.10f}s with "
                        f"duration {duration:.10f}s. In order to save samples and "
                        "clock ticks this instruction is replaced with a constant "
                        "output.\n"
                    )
            else:
                self._add_ramp(
                    t, duration, truncation * duration, "linear ramp", samplerate,
                    units, functions.ramp, initial, final,
                )
        return truncation * duration

    def sine(
        self,
        t,
        duration,
        amplitude,
        angfreq,
        phase,
        dc_offset,
        samplerate,
        units=None,
        truncation=1.
    ):
        """Command the output to perform a sinusoidal modulation.

        Defined by
        `f(t) = amplitude*sin(angfreq*t + phase) + dc_offset`

        Parameters
        ----------
        t : float
            Time, in seconds, to begin the ramp.
        duration : float
            Length, in seconds, of the ramp.
        amplitude : float
            Amplitude of the modulation.
        angfreq : float
            Angular frequency, in radians per second.
        phase : float
            Phase offset of the sine wave, in radians.
        dc_offset : float
            DC offset of output away from 0.
        samplerate : float
            Rate, in Hz, to update the output.
        units
            Units the output values are given in, as specified by the unit
            conversion class.
        truncation : float, optional
            Fraction of duration to perform. Must be between 0 and 1.

        Returns
        -------
        float
            Length of time modulation will take to complete. Equivalent to
            `truncation*duration`.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration, "sine wave", samplerate, units,
                functions.sine, amplitude, angfreq, phase, dc_offset,
            )
        return truncation * duration

    def sine_ramp(
        self, t, duration, initial, final, samplerate, units=None, truncation=1.
    ):
        """Command the output to perform a ramp of one half period of a squared sine.

        Defined by
        `f(t) = (final-initial)*(sin(pi*t/(2*duration)))^2 + initial`

        Parameters
        ----------
        t : float
            Time, in seconds, to begin the ramp.
        duration : float
            Length, in seconds, of the ramp.
        initial : float
            Initial output value, at time `t`.
        final : float
            Final output value, at time `t+duration`.
        samplerate : float
            Rate, in Hz, to update the output.
        units
            Units the output values are given in, as specified by the unit
            conversion class.
        truncation : float, optional
            Fraction of ramp to perform. Must be between 0 and 1.

        Returns
        -------
        float
            Length of time ramp will take to complete.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration, "sinusoidal ramp", samplerate,
                units, functions.sine_ramp, initial, final,
            )
        return truncation * duration

    def sine4_ramp(
        self, t, duration, initial, final, samplerate, units=None, truncation=1.
    ):
        """Command the output to perform an increasing ramp of one half period of a
        quartic sine wave.

        Defined by
        `f(t) = (final-initial)*(sin(pi*t/(2*duration)))^4 + initial`

        Parameters
        ----------
        t : float
            Time, in seconds, to begin the ramp.
        duration : float
            Length, in seconds, of the ramp.
        initial : float
            Initial output value, at time `t`.
        final : float
            Final output value, at time `t+duration`.
        samplerate : float
            Rate, in Hz, to update the output.
        units
            Units the output values are given in, as specified by the unit
            conversion class.
        truncation : float, optional
            Fraction of ramp to perform. Must be between 0 and 1.

        Returns
        -------
        float
            Length of time ramp will take to complete.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration, "sinusoidal ramp", samplerate,
                units, functions.sine4_ramp, initial, final,
            )
        return truncation * duration

    def sine4_reverse_ramp(
        self, t, duration, initial, final, samplerate, units=None, truncation=1.
    ):
        """Command the output to perform `sine4_ramp` backwards in time.

        The output goes from `final` at `t` to `initial` at `t+duration`.

        Defined by
        `f(t) = (final-initial)*(sin(pi/2+pi*t/(2*duration)))^4 + initial`

        Parameters
        ----------
        t : float
            Time, in seconds, to begin the ramp.
        duration : float
            Length, in seconds, of the ramp.
        initial : float
            Output value the ramp ends at, at time `t+duration`.
        final : float
            Output value the ramp starts at, at time `t`.
        samplerate : float
            Rate, in Hz, to update the output.
        units
            Units the output values are given in, as specified by the unit
            conversion class.
        truncation : float, optional
            Fraction of ramp to perform. Must be between 0 and 1.

        Returns
        -------
        float
            Length of time ramp will take to complete.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration, "sinusoidal ramp", samplerate,
                units, functions.sine4_reverse_ramp, initial, final,
            )
        return truncation * duration

    def exp_ramp(
        self,
        t,
        duration,
        initial,
        final,
        samplerate,
        zero=0,
        units=None,
        truncation=None,
        truncation_type="linear",
        **kwargs,
    ):
        """Exponential ramp whose rate of change is set by an asymptotic value.

        The asymptotic value is the `zero` argument.

        Parameters
        ----------
        t : float
            time to start the ramp
        duration : float
            duration of the ramp
        initial : float
            initial value of the ramp (sans truncation)
        final : float
            final value of the ramp (sans truncation)
        samplerate : float
            rate to sample the function
        zero : float
            asymptotic value of the exponential decay/rise, i.e. limit as t --> inf
        units
            unit conversion to apply to specified values before generating raw output
        truncation : float, optional
            Where to truncate the ramp; its meaning depends on `truncation_type`.
        truncation_type : str
            * `'linear'` truncation stops the ramp when it reaches the value given by
              the truncation parameter, which must be between initial and final
            * `'exponential'` truncation stops the ramp after a period of
              truncation*duration. In this instance, the truncation parameter should
              be between 0 (full truncation) and 1 (no truncation).
        **kwargs
            The deprecated names `trunc` and `trunc_type`, for `truncation` and
            `truncation_type`.
        """
        truncation = _renamed_keyword(kwargs, "trunc", "truncation", truncation)
        truncation_type = _renamed_keyword(
            kwargs, "trunc_type", "truncation_type", truncation_type
        )
        if truncation is not None:
            if truncation_type == "linear":
                self._check_truncation(
                    truncation, min(initial, final), max(initial, final)
                )
                # Truncate the ramp when it reaches the value truncation
                trunc_duration = (
                    duration
                    * np.log((initial - zero) / (truncation - zero))
                    / np.log((initial - zero) / (final - zero))
                )
            elif truncation_type == "exponential":
                # Truncate the ramps duration by a fraction truncation
                self._check_truncation(truncation)
                trunc_duration = truncation * duration
            else:
                raise LabscriptError(
                    "Truncation type for exp_ramp not supported. Must be either linear "
                    "or exponential."
                )
        else:
            trunc_duration = duration
        if trunc_duration > 0:
            self._add_ramp(
                t, duration, trunc_duration, 'exponential ramp', samplerate, units,
                functions.exp_ramp, initial, final, zero,
            )
        return trunc_duration

    def exp_ramp_t(
        self,
        t,
        duration,
        initial,
        final,
        time_constant,
        samplerate,
        units=None,
        truncation=None,
        truncation_type="linear",
        **kwargs
    ):
        """Exponential ramp whose rate of change is set by the time_constant.

        Parameters
        ----------
        t : float
            time to start the ramp
        duration : float
            duration of the ramp
        initial : float
            initial value of the ramp (sans truncation)
        final : float
            final value of the ramp (sans truncation)
        time_constant : float
            1/e time of the exponential decay/rise
        samplerate : float
            rate to sample the function
        units
            unit conversion to apply to specified values before generating raw output
        truncation : float, optional
            Where to truncate the ramp; its meaning depends on `truncation_type`.
        truncation_type : str
            * `'linear'` truncation stops the ramp when it reaches the value given by
              the truncation parameter, which must be between initial and final
            * `'exponential'` truncation stops the ramp after a period of
              truncation*duration. In this instance, the truncation parameter should
              be between 0 (full truncation) and 1 (no truncation).
        **kwargs
            The deprecated names `trunc` and `trunc_type`, for `truncation` and
            `truncation_type`.
        """
        truncation = _renamed_keyword(kwargs, "trunc", "truncation", truncation)
        truncation_type = _renamed_keyword(
            kwargs, "trunc_type", "truncation_type", truncation_type
        )
        if truncation is not None:
            zero = (final - initial * np.exp(-duration / time_constant)) / (
                1 - np.exp(-duration / time_constant)
            )
            if truncation_type == "linear":
                self._check_truncation(
                    truncation, min(initial, final), max(initial, final)
                )
                trunc_duration = time_constant * np.log(
                    (initial - zero) / (truncation - zero)
                )
            elif truncation_type == 'exponential':
                self._check_truncation(truncation)
                trunc_duration = truncation * duration
            else:
                raise LabscriptError(
                    "Truncation type for exp_ramp_t not supported. Must be either "
                    "linear or exponential."
                )
        else:
            trunc_duration = duration
        if trunc_duration > 0:
            self._add_ramp(
                t, duration, trunc_duration, "exponential ramp with time consntant",
                samplerate, units,
                functions.exp_ramp_t, initial, final, time_constant,
            )
        return trunc_duration

    def piecewise_accel_ramp(
        self, t, duration, initial, final, samplerate, units=None, truncation=1.
    ):
        """Change the output so its second derivative follows one triangle wave period.

        Parameters
        ----------
        t : float
            Time, in seconds, at which to begin the ramp.
        duration : float
            Duration of the ramp, in seconds.
        initial : float
            Initial output value at time `t`.
        final : float
            Final output value at time `t+duration`.
        samplerate : float
            Update rate of the output, in Hz.
        units
            Units, defined by the unit conversion class, the value is in.
        truncation : float, optional
            Fraction of ramp to perform. Default 1.0.

        Returns
        -------
        float
            Time the ramp will take to complete.
        """
        self._check_truncation(truncation)
        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration,
                "piecewise linear accelleration ramp", samplerate, units,
                functions.piecewise_accel, initial, final,
            )
        return truncation * duration

    def square_wave(
        self,
        t,
        duration,
        amplitude,
        frequency,
        phase,
        offset,
        duty_cycle,
        samplerate,
        units=None,
        truncation=1.
    ):
        """A standard square wave.

        This method generates a square wave which starts HIGH (when its phase is
        zero) then transitions to/from LOW at the specified `frequency` in Hz.
        The `amplitude` parameter specifies the peak-to-peak amplitude of the
        square wave which is centered around `offset`. For example, setting
        `amplitude=1` and `offset=0` would give a square wave which transitions
        between `0.5` and `-0.5`. Similarly, setting `amplitude=2` and
        `offset=3` would give a square wave which transitions between `4` and
        `2`. To instead specify the HIGH/LOW levels directly, use
        `square_wave_levels()`.

        Note that because the transitions of a square wave are sudden and
        discontinuous, small changes in timings (e.g. due to numerical rounding
        errors) can affect the output value. This is particularly relevant at
        the end of the waveform, as the final output value may be different than
        expected if the end of the waveform is close to an edge of the square
        wave. Care is taken in the implementation of this method to avoid such
        effects, but it still may be desirable to call `constant()` after
        `square_wave()` to ensure a particular final value. The output value may
        also be different than expected at certain moments in the middle of the
        waveform due to the finite samplerate (which may be different than the
        requested `samplerate`), particularly if the actual samplerate is not a
        multiple of `frequency`.

        Parameters
        ----------
        t : float
            The time at which to start the square wave.
        duration : float
            The duration for which to output a square wave when `truncation` is
            set to `1`. When `truncation` is set to a value less than `1`, the
            actual duration will be shorter than `duration` by that factor.
        amplitude : float
            The peak-to-peak amplitude of the square wave. See above for an
            example of how to calculate the HIGH/LOW output values given the
            `amplitude` and `offset` values.
        frequency : float
            The frequency of the square wave, in Hz.
        phase : float
            The initial phase of the square wave. Note that the square wave is
            defined such that the phase goes from 0 to 1 (NOT 2 pi) over one
            cycle, so setting `phase=0.5` will start the square wave advanced by
            1/2 of a cycle. Setting `phase` equal to `duty_cycle` will cause the
            waveform to start LOW rather than HIGH.
        offset : float
            The offset of the square wave, which is the value halfway between
            the LOW and HIGH output values. Note that this is NOT the LOW output
            value; setting `offset` to `0` will cause the HIGH/LOW values to be
            symmetrically split around `0`. See above for an example of how to
            calculate the HIGH/LOW output values given the `amplitude` and
            `offset` values.
        duty_cycle : float
            The fraction of the cycle for which the output should be HIGH. This
            should be a number between zero and one inclusively. For example,
            setting `duty_cycle=0.1` will create a square wave which outputs
            HIGH over 10% of the cycle and outputs LOW over 90% of the cycle.
        samplerate : float
            The requested rate at which to update the output value. Note that
            the actual samplerate used may be different if, for example, another
            output of the same device has a simultaneous ramp with a different
            requested `samplerate`, or if `1 / samplerate` isn't an integer
            multiple of the pseudoclock's timing resolution.
        units : str, optional
            The units of the output values. If set to `None` then the output's
            base units will be used. Defaults to `None`.
        truncation : float, optional
            The actual duration of the square wave will be `duration *
            truncation` and `truncation` must be set to a value in the range
            [0, 1] (inclusively). Set to `1` to output the full duration of the
            square wave. Setting it to `0` will skip the square wave entirely.
            Defaults to `1.`.

        Returns
        -------
        float
            The actual duration of the square wave, accounting for `truncation`.
        """
        # Convert to values used by square_wave_levels, then call that method.
        level_0 = offset + 0.5 * amplitude
        level_1 = offset - 0.5 * amplitude
        return self.square_wave_levels(
            t,
            duration,
            level_0,
            level_1,
            frequency,
            phase,
            duty_cycle,
            samplerate,
            units,
            truncation,
        )

    def square_wave_levels(
        self,
        t,
        duration,
        level_0,
        level_1,
        frequency,
        phase,
        duty_cycle,
        samplerate,
        units=None,
        truncation=1.
    ):
        """A standard square wave.

        This method generates a square wave which starts at `level_0` (when its
        phase is zero) then transitions to/from `level_1` at the specified
        `frequency`. This is the same waveform output by `square_wave()`, but
        parameterized differently. See that method's docstring for more
        information.

        Parameters
        ----------
        t : float
            The time at which to start the square wave.
        duration : float
            The duration for which to output a square wave when `truncation` is
            set to `1`. When `truncation` is set to a value less than `1`, the
            actual duration will be shorter than `duration` by that factor.
        level_0 : float
            The initial level of the square wave, when the phase is zero.
        level_1 : float
            The other level of the square wave.
        frequency : float
            The frequency of the square wave, in Hz.
        phase : float
            The initial phase of the square wave. Note that the square wave is
            defined such that the phase goes from 0 to 1 (NOT 2 pi) over one
            cycle, so setting `phase=0.5` will start the square wave advanced by
            1/2 of a cycle. Setting `phase` equal to `duty_cycle` will cause the
            waveform to start at `level_1` rather than `level_0`.
        duty_cycle : float
            The fraction of the cycle for which the output should be set to
            `level_0`. This should be a number between zero and one inclusively.
            For example, setting `duty_cycle=0.1` will create a square wave which
            outputs `level_0` over 10% of the cycle and outputs `level_1` over
            90% of the cycle.
        samplerate : float
            The requested rate at which to update the output value. Note that
            the actual samplerate used may be different if, for example, another
            output of the same device has a simultaneous ramp with a different
            requested `samplerate`, or if `1 / samplerate` isn't an integer
            multiple of the pseudoclock's timing resolution.
        units : str, optional
            The units of the output values. If set to `None` then the output's
            base units will be used. Defaults to `None`.
        truncation : float, optional
            The actual duration of the square wave will be `duration *
            truncation` and `truncation` must be set to a value in the range
            [0, 1] (inclusively). Set to `1` to output the full duration of the
            square wave. Setting it to `0` will skip the square wave entirely.
            Defaults to `1.`.

        Returns
        -------
        float
            The actual duration of the square wave, accounting for `truncation`.
        """
        self._check_truncation(truncation)
        if duty_cycle < 0 or duty_cycle > 1:
            raise LabscriptError(
                "Square wave duty cycle must be in the range [0, 1] (inclusively) but "
                f"was set to {duty_cycle}."
            )

        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration, "square wave", samplerate, units,
                functions.square_wave, level_0, level_1, frequency, phase, duty_cycle,
            )
        return truncation * duration

    def customramp(self, t, duration, function, *args, **kwargs):
        """Define a custom function for the output.

        Parameters
        ----------
        t : float
            Time, in seconds, to start the function.
        duration : float
            Length in time, in seconds, to perform the function.
        function : callable
            Function handle that defines the output waveform. First argument is
            the relative time from function start, in seconds.
        *args
            Arguments passed to `function`.
        **kwargs
            Keyword arguments pass to `function`. Standard kwargs common to other
            output functions are: `units`, `samplerate`, and `truncation`. These
            kwargs are optional, but will not be passed to `function` if present.

        Returns
        -------
        float
            Duration the function is to be evaluated for. Equivalent to
            `truncation*duration`.
        """
        units = kwargs.pop("units", None)
        samplerate = kwargs.pop("samplerate")
        truncation = kwargs.pop("truncation", 1.)
        self._check_truncation(truncation)

        def custom_ramp_func(duration):
            return lambda t_rel: function(t_rel, duration, *args, **kwargs)

        if truncation > 0:
            self._add_ramp(
                t, duration, truncation * duration,
                f"custom ramp: {function.__name__}", samplerate, units,
                custom_ramp_func,
            )
        return truncation * duration

    def constant(self, t, value, units=None):
        """Set the output to a constant value at time `t`.

        Parameters
        ----------
        t : float
            Time, in seconds, to set the constant output.
        value : float
            Value to set.
        units
            Units, defined by the unit conversion class, the value is in.
        """
        # verify that value can be converted to float
        try:
            float(value)
        except (TypeError, ValueError, OverflowError):
            raise LabscriptError(
                f"Cannot set {self.name} to value={value} at t={t} as the value cannot "
                "be converted to float"
            )
        self.add_instruction(t, value, units)


class AnalogOut(AnalogQuantity):
    """Analog output for all devices that support timed analog outputs."""

    description = "analog output"


class _StaticQuantity:
    """Members shared by outputs that hold one value for the whole shot."""

    def get_change_times(self):
        """Enforce no change times.

        Returns
        -------
        list
            An empty list, as expected by the parent pseudoclock.
        """
        return []

    def make_timeseries(self, change_times):
        """Since output is static, does nothing."""
        pass

    def expand_timeseries(self, *args, **kwargs):
        """Define the `raw_output` attribute."""
        self.raw_output = np.array([self.static_value], dtype=self.dtype)

    @property
    def static_value(self):
        """float: The value of the static output."""
        if self._static_value is None:
            if (
                not compiler.suppress_mild_warnings
                and not compiler.suppress_all_warnings
            ):
                sys.stderr.write(
                    f"WARNING: {self.name} has no value set. It will be set to "
                    f"{self.instruction_to_string(self.default_value)}.\n"
                )
            self._static_value = self.default_value
        return self._static_value


class StaticAnalogQuantity(_StaticQuantity, Output):
    """Base class for :obj:`StaticAnalogOut`.

    It can also be used internally by other more complex output types.
    """

    description = "static analog quantity"
    default_value = 0.0
    """float: Value of output if no constant value is commanded."""

    @set_passed_properties(property_names={})
    def __init__(self, *args, **kwargs):
        """Instantiate the static analog quantity.

        Defines an internal tracking variable of the static output value and
        calls :func:`Output.__init__`.

        Parameters
        ----------
        *args
            Passed to :func:`Output.__init__`.
        **kwargs
            Passed to :func:`Output.__init__`.
        """
        Output.__init__(self, *args, **kwargs)
        self._static_value = None

    def constant(self, value, units=None):
        """Set the static output value of the output.

        Parameters
        ----------
        value : float
            Value to set the output to.
        units
            Units, defined by the unit conversion class, the value is in.

        Raises
        ------
        LabscriptError
            If static output has already been set to another value or the value
            lies outside the output limits.
        """
        if self._static_value is None:
            if units is not None:
                value = self.apply_calibration(value, units)
            if self.limits:
                minval, maxval = self.limits
                if not minval <= value <= maxval:
                    raise LabscriptError(
                        f"You cannot program the value {value} (base units) to "
                        f"{self.name} as it falls outside the limits "
                        f"({self.limits[0]} to {self.limits[1]})"
                    )
            self._static_value = value
        else:
            raise LabscriptError(
                f"{self.description} {self.name} has already been set to "
                f"{self._static_value} (base units). It cannot also be set to "
                f"{value} ({units if units is not None else 'base units'})."
            )


class StaticAnalogOut(StaticAnalogQuantity):
    """Static analog output for all devices that have constant outputs."""

    description = "static analog output"


class DigitalQuantity(Output):
    """Base class for :obj:`DigitalOut`.

    It is also used internally by other, more complex, output types.
    """

    description = "digital quantity"
    allowed_states = {1: "high", 0: "low"}
    default_value = 0
    dtype = np.uint32

    # Redefine __init__ so that you cannot define a limit or calibration for DO
    @set_passed_properties(property_names={"connection_table_properties": ["inverted"]})
    def __init__(self, name, parent_device, connection, inverted=False, **kwargs):
        """Instantiate a digital quantity.

        Parameters
        ----------
        name : str
            python variable name to assign the quantity to.
        parent_device : :obj:`IntermediateDevice`
            Device this quantity is attached to.
        connection : str
            Connection on parent device we are connected to.
        inverted : bool, optional
            If `True`, output is logic inverted.
        **kwargs
            Passed to :func:`Output.__init__`.
        """
        super().__init__(name, parent_device, connection, **kwargs)
        self.inverted = bool(inverted)

    def go_high(self, t):
        """Command the output to go high.

        Parameters
        ----------
        t : float
            Time, in seconds, when the output goes high.
        """
        self.add_instruction(t, 1)

    def go_low(self, t):
        """Command the output to go low.

        Parameters
        ----------
        t : float
            Time, in seconds, when the output goes low.
        """
        self.add_instruction(t, 0)

    def enable(self, t):
        """Command the output to enable.

        If `inverted=True`, this will set the output low.

        Parameters
        ----------
        t : float
            Time, in seconds, when the output enables.
        """
        if self.inverted:
            self.go_low(t)
        else:
            self.go_high(t)

    def disable(self, t):
        """Command the output to disable.

        If `inverted=True`, this will set the output high.

        Parameters
        ----------
        t : float
            Time, in seconds, when the output disables.
        """
        if self.inverted:
            self.go_high(t)
        else:
            self.go_low(t)

    def repeat_pulse_sequence(self, t, duration, pulse_sequence, period, samplerate):
        """Repeat a pulse sequence from time `t` until `t+duration`.

        This only works if the DigitalQuantity is on a fast clock.

        Parameters
        ----------
        t : float
            Time, in seconds, to start the pulse sequence.
        duration : float
            How long, in seconds, to repeat the sequence.
        pulse_sequence : list
            List of tuples, with each tuple of the form `(time, state)`.
        period : float
            Defines how long the final tuple will be held for before repeating
            the pulse sequence. In general, should be longer than the entire pulse
            sequence.
        samplerate : float
            How often to update the output, in Hz.

        Returns
        -------
        float
            The `duration`.

        Notes
        -----
        The samplerate should be significantly faster than the smallest time
        difference between two states in the pulse sequence, or else points in
        your pulse sequence may never be evaluated.

        The time points your pulse sequence is evaluated at may be different than
        you expect, if another output changes state between t and t+duration. As
        such, you should set the samplerate high enough that even if this rounding
        of time points occurs (to fit in the update required to change the other
        output) your pulse sequence will not be significantly altered.
        """
        self.add_instruction(
            t,
            {
                "function": functions.pulse_sequence(pulse_sequence, period),
                "description": "pulse sequence",
                "initial time": t,
                "end time": t + duration,
                "span": duration,
                "clock rate": samplerate,
                "units": None,
            }
        )

        return duration


class DigitalOut(DigitalQuantity):
    """Digital output class for use with all devices."""

    description = "digital output"


class StaticDigitalQuantity(_StaticQuantity, DigitalQuantity):
    """Base class for :obj:`StaticDigitalOut`.

    It can also be used internally by other, more complex, output types.
    """

    description = "static digital quantity"
    default_value = 0
    """float: Value of output if no constant value is commanded."""

    @set_passed_properties(property_names={})
    def __init__(self, *args, **kwargs):
        """Instantiate the static digital quantity.

        Defines an internal tracking variable of the static output value and
        calls :func:`Output.__init__`.

        Parameters
        ----------
        *args
            Passed to :func:`Output.__init__`.
        **kwargs
            Passed to :func:`Output.__init__`.
        """
        DigitalQuantity.__init__(self, *args, **kwargs)
        self._static_value = None

    def go_high(self):
        """Command a static high output.

        Raises
        ------
        LabscriptError
            If output has already been set low.
        """
        self._set_static(1)

    def go_low(self):
        """Command a static low output.

        Raises
        ------
        LabscriptError
            If output has already been set high.
        """
        self._set_static(0)

    def _set_static(self, value):
        if self._static_value is not None:
            raise LabscriptError(
                f"{self.description} {self.name} has already been set to "
                f"{self.instruction_to_string(self._static_value)}. It cannot "
                f"also be set to {value}."
            )
        self.add_instruction(0, value)
        self._static_value = value


class StaticDigitalOut(StaticDigitalQuantity):
    """Static digital output for all devices that have constant outputs."""

    description = "static digital output"


class Shutter(DigitalOut):
    """Customized version of :obj:`DigitalOut` that accounts for the open/close
    delay of a shutter automatically.

    When using the methods :meth:`open` and :meth:`close`, the shutter open
    and close times are precise without having to track the delays. Note:
    delays can be set using runmanager globals and periodically updated
    via a calibration.

    .. Warning::
        If the shutter is asked to do something at `t=0`, it cannot start
        moving earlier than that. This means the initial shutter states
        will have imprecise timing.
    """

    description = "shutter"

    @set_passed_properties(
        property_names={"connection_table_properties": ["open_state"]}
    )
    def __init__(
        self, name, parent_device, connection, delay=(0, 0), open_state=1, **kwargs
    ):
        """Instantiate a Shutter.

        Parameters
        ----------
        name : str
            python variable to assign the object to.
        parent_device : :obj:`IntermediateDevice`
            Parent device the digital output is connected to.
        connection : str
            Physical output port of the device the digital output is connected to.
        delay : tuple, optional
            Tuple of the (open, close) delays, specified in seconds: how long the
            shutter takes to open or close once commanded. `open(t)` and
            `close(t)` command it that much earlier, so that it is open or closed
            at `t`.
        open_state : int, optional
            Allowed values are `0` or `1`. Defines which state of the digital
            output opens the shutter.

        Raises
        ------
        LabscriptError
            If the `open_state` is not `0` or `1`.
        """
        inverted = not bool(open_state)
        super().__init__(name, parent_device, connection, inverted=inverted, **kwargs)
        self.open_delay, self.close_delay = delay
        self.open_state = open_state
        if self.open_state == 1:
            self.allowed_states = {0: "closed", 1: "open"}
        elif self.open_state == 0:
            self.allowed_states = {1: "closed", 0: "open"}
        else:
            raise LabscriptError(
                f"Shutter {self.name} wasn't instantiated with open_state = 0 or 1."
            )
        self.actual_times = {}

    def open(self, t):
        """Command the shutter to open at time `t`.

        Takes the open delay time into account.

        Note that the delay time will not be take into account the open delay if the
        command is made at t=0 (or other times less than the open delay). No warning
        will be issued for this loss of precision during compilation.

        Parameters
        ----------
        t : float
            Time, in seconds, when shutter should be open.
        """
        # A shutter asked to do something at t=0 cannot start moving earlier, so
        # initial shutter states have imprecise timing. This does not warn, as every
        # run would warn for every shutter; the documentation says so instead.
        t_calc = t - self.open_delay if t >= self.open_delay else 0
        self.actual_times[t] = {"time": t_calc, "instruction": 1}
        self.enable(t_calc)

    def close(self, t):
        """Command the shutter to close at time `t`.

        Takes the close delay time into account.

        Note that the delay time will not be take into account the close delay if the
        command is made at t=0 (or other times less than the close delay). No warning
        will be issued for this loss of precision during compilation.

        Parameters
        ----------
        t : float
            Time, in seconds, when shutter should be closed.
        """
        t_calc = t - self.close_delay if t >= self.close_delay else 0
        self.actual_times[t] = {"time": t_calc, "instruction": 0}
        self.disable(t_calc)

    def generate_code(self, hdf5_file):
        classname = self.__class__.__name__
        calibration_table_dtypes = [
            ("name", "S256"), ("open_delay", float), ("close_delay", float)
        ]
        if classname not in hdf5_file["calibrations"]:
            hdf5_file["calibrations"].create_dataset(
                classname, (0,), dtype=calibration_table_dtypes, maxshape=(None,)
            )
        metadata = (self.name, self.open_delay, self.close_delay)
        dataset = hdf5_file["calibrations"][classname]
        dataset.resize((len(dataset) + 1,))
        dataset[len(dataset) - 1] = metadata

    def get_change_times(self, *args, **kwargs):
        retval = super().get_change_times(*args, **kwargs)

        if len(self.actual_times) > 1:
            sorted_times = list(self.actual_times.keys())
            sorted_times.sort()
            for i in range(len(sorted_times) - 1):
                time = sorted_times[i]
                next_time = sorted_times[i + 1]
                instruction = self.actual_times[time]["instruction"]
                next_instruction = self.actual_times[next_time]["instruction"]
                state = "opened" if instruction == 1 else "closed"
                next_state = "open" if next_instruction == 1 else "close"
                # only look at instructions that contain a state change
                if instruction != next_instruction:
                    if (
                        self.actual_times[next_time]["time"]
                        < self.actual_times[time]["time"]
                    ):
                        sys.stderr.write(
                            f"WARNING: The shutter '{self.name}' is requested to "
                            f"{next_state} too early (taking delay into account) at "
                            f"t={next_time:.10f}s when it is still not {state} from "
                            f"an earlier instruction at t={time:.10f}s\n"
                        )
                elif (
                    not compiler.suppress_mild_warnings
                    and not compiler.suppress_all_warnings
                ):
                    sys.stderr.write(
                        f"WARNING: The shutter '{self.name}' is requested to "
                        f"{next_state} at t={next_time:.10f}s but was never {state} "
                        f"after an earlier instruction at t={time:.10f}s\n"
                    )
        return retval


class Trigger(DigitalOut):
    """Customized version of :obj:`DigitalOut` that tracks edge type."""

    description = "trigger device"
    allowed_children = [TriggerableDevice]

    @set_passed_properties(property_names={})
    def __init__(
        self, name, parent_device, connection, trigger_edge_type="rising", **kwargs
    ):
        """Instantiate a DigitalOut object that tracks the trigger edge type.

        Parameters
        ----------
        name : str
            python variable name to assign the quantity to.
        parent_device : :obj:`IntermediateDevice`
            Device this quantity is attached to.
        connection : str
            Connection on parent device we are connected to.
        trigger_edge_type : str, optional
            Allowed values are `'rising'` and `'falling'`.
        **kwargs
            Passed to :func:`Output.__init__`.
        """
        super().__init__(name, parent_device, connection, **kwargs)
        self.trigger_edge_type = trigger_edge_type
        if self.trigger_edge_type == "rising":
            self.enable = self.go_high
            self.disable = self.go_low
            self.allowed_states = {1: "enabled", 0: "disabled"}
        elif self.trigger_edge_type == "falling":
            self.enable = self.go_low
            self.disable = self.go_high
            self.allowed_states = {1: "disabled", 0: "enabled"}
        else:
            raise ValueError(
                "trigger_edge_type must be 'rising' or 'falling', not "
                f"'{trigger_edge_type}'."
            )
        # A list of the times this trigger has been asked to trigger:
        self.triggerings = []

    def trigger(self, t, duration):
        """Command a trigger pulse.

        Parameters
        ----------
        t : float
            Time, in seconds, for the trigger edge to occur.
        duration : float
            Duration of the trigger, in seconds.
        """
        assert duration > 0, "Negative or zero trigger duration given"
        if t != self.t0 and self.t0 not in self.instructions:
            self.disable(self.t0)

        # Compare ticks, not requested times: an edge pair within one tick is lost.
        start = self._round_time(t)
        end = self._round_time(t + duration)
        if start == end:
            raise LabscriptError(
                f"{self.description} {self.name} has a trigger at t = {t}s lasting "
                f"{duration}s, shorter than one tick "
                f"({self.pseudoclock_device.clock_resolution}s) of "
                f"{self.pseudoclock_device.name}. Its rise and fall would fall on the "
                "same tick, and the trigger would be lost. Make it at least one tick "
                "long."
            )
        for other_start, other_duration in self.triggerings:
            other_end = self._round_time(other_start + other_duration)
            other_start = self._round_time(other_start)
            # Check for overlapping exposures:
            if not (end < other_start or start > other_end):
                raise LabscriptError(
                    f"{self.description} {self.name} has two overlapping triggerings: "
                    f"one at t = {start}s for {duration}s, and another at "
                    f"t = {other_start}s for {other_duration}s."
                )
        self.enable(t)
        self.disable(t + duration)
        self.triggerings.append((t, duration))

    def add_device(self, device):
        if device.connection != "trigger":
            raise LabscriptError(
                f"The 'connection' string of device {device.name} "
                f"to {self.name} must be 'trigger', not '{device.connection}'"
            )
        super().add_device(device)


class _DDSBase(Device):
    """Frequency, amplitude and phase channels of a DDS, and its optional gate.

    Subclasses name the class of the three channels in `channel_class`.
    """

    @set_passed_properties(property_names={})
    def __init__(
        self,
        name,
        parent_device,
        connection,
        digital_gate=None,
        freq_limits=None,
        freq_conv_class=None,
        freq_conv_params=None,
        amp_limits=None,
        amp_conv_class=None,
        amp_conv_params=None,
        phase_limits=None,
        phase_conv_class=None,
        phase_conv_params=None,
        call_parents_add_device=True,
        **kwargs
    ):
        """Instantiate the channels, and the gate if one is given.

        Parameters
        ----------
        name : str
            python variable for the object created.
        parent_device : :obj:`IntermediateDevice`
            Device this output is connected to.
        connection : str
            Output of parent device this DDS is connected to.
        digital_gate : dict, optional
            Configures a digital output to use as an enable/disable gate for the
            output. Should contain keys `'device'` and `'connection'` with
            arguments for the `parent_device` and `connection` for instantiating
            the :obj:`DigitalOut`. All other (optional) keys are passed as kwargs.
        freq_limits : tuple, optional
            `(lower, upper)` limits for the frequency of the output
        freq_conv_class : :obj:`labscript_utils:labscript_utils.unitconversions`, optional
            Unit conversion class for the frequency of the output.
        freq_conv_params : dict, optional
            Keyword arguments passed to the unit conversion class for the frequency
            of the output.
        amp_limits : tuple, optional
            `(lower, upper)` limits for the amplitude of the output
        amp_conv_class : :obj:`labscript_utils:labscript_utils.unitconversions`, optional
            Unit conversion class for the amplitude of the output.
        amp_conv_params : dict, optional
            Keyword arguments passed to the unit conversion class for the amplitude
            of the output.
        phase_limits : tuple, optional
            `(lower, upper)` limits for the phase of the output
        phase_conv_class : :obj:`labscript_utils:labscript_utils.unitconversions`, optional
            Unit conversion class for the phase of the output.
        phase_conv_params : dict, optional
            Keyword arguments passed to the unit conversion class for the phase of
            the output.
        call_parents_add_device : bool, optional
            Have the parent device run its `add_device` method.
        **kwargs
            Keyword arguments passed to :func:`Device.__init__`.
        """
        # Device.__init__ without the parent's add_device, so that add_device, called
        # below, can check the channels set up here.
        super().__init__(
            name, parent_device, connection, call_parents_add_device=False, **kwargs
        )

        # Ask the parent device if it has default unit conversion classes it would like
        # us to use:
        if hasattr(parent_device, 'get_default_unit_conversion_classes'):
            classes = self.parent_device.get_default_unit_conversion_classes(self)
            default_freq_conv, default_amp_conv, default_phase_conv = classes
            # If the user has not overridden, use these defaults. If
            # the parent does not have a default for one or more of amp,
            # freq or phase, it should return None for them.
            if freq_conv_class is None:
                freq_conv_class = default_freq_conv
            if amp_conv_class is None:
                amp_conv_class = default_amp_conv
            if phase_conv_class is None:
                phase_conv_class = default_phase_conv

        self.frequency = self.channel_class(
            f"{self.name}_freq",
            self,
            "freq",
            freq_limits,
            freq_conv_class,
            freq_conv_params,
        )
        self.amplitude = self.channel_class(
            f"{self.name}_amp",
            self,
            "amp",
            amp_limits,
            amp_conv_class,
            amp_conv_params,
        )
        self.phase = self.channel_class(
            f"{self.name}_phase",
            self,
            "phase",
            phase_limits,
            phase_conv_class,
            phase_conv_params,
        )

        self.gate = None
        digital_gate = digital_gate or {}
        if "device" in digital_gate and "connection" in digital_gate:
            dev = digital_gate.pop("device")
            conn = digital_gate.pop("connection")
            self.gate = DigitalOut(f"{name}_gate", dev, conn, **digital_gate)
        # Did they only put one key in the dictionary, or use the wrong keywords?
        elif len(digital_gate) > 0:
            raise LabscriptError(
                'You must specify the "device" and "connection" for the digital gate '
                f"of {self.name}."
            )

        # The parent's add_device adds a gate if none was given and it supports one,
        # or raises if it gates itself (e.g. PulseBlaster). Subclasses that must run
        # more code first, such as PulseBlasterDDS, defer the call.
        if call_parents_add_device:
            self.parent_device.add_device(self)

    def enable(self, t):
        """Enable the Output.

        Parameters
        ----------
        t : float
            Time, in seconds, to enable the output at.

        Raises
        ------
        LabscriptError
            If the DDS is not instantiated with a digital gate.
        """
        if self.gate is None:
            raise LabscriptError(
                f"DDS {self.name} does not have a digital gate, so you cannot use the "
                "enable(t) method."
            )
        self.gate.go_high(t)

    def disable(self, t):
        """Disable the Output.

        Parameters
        ----------
        t : float
            Time, in seconds, to disable the output at.

        Raises
        ------
        LabscriptError
            If the DDS is not instantiated with a digital gate.
        """
        if self.gate is None:
            raise LabscriptError(
                f"DDS {self.name} does not have a digital gate, so you cannot use the "
                "disable(t) method."
            )
        self.gate.go_low(t)


class DDSQuantity(_DDSBase):
    """Used to define a DDS output.

    It is a container class, with properties that allow access to a frequency,
    amplitude, and phase of the output as :obj:`AnalogQuantity`.
    It can also have a gate, which provides enable/disable control of the output
    as :obj:`DigitalOut`.

    This class instantiates channels for frequency/amplitude/phase (and optionally the
    gate) itself.
    """

    description = 'DDS'
    allowed_children = [AnalogQuantity, DigitalOut, DigitalQuantity]
    channel_class = AnalogQuantity

    def setamp(self, t, value, units=None):
        """Set the amplitude of the output.

        Parameters
        ----------
        t : float
            Time, in seconds, when the amplitude is set.
        value : float
            Amplitude to set to.
        units
            Units that the value is defined in.
        """
        self.amplitude.constant(t, value, units)

    def setfreq(self, t, value, units=None):
        """Set the frequency of the output.

        Parameters
        ----------
        t : float
            Time, in seconds, when the frequency is set.
        value : float
            Frequency to set to.
        units
            Units that the value is defined in.
        """
        self.frequency.constant(t, value, units)

    def setphase(self, t, value, units=None):
        """Set the phase of the output.

        Parameters
        ----------
        t : float
            Time, in seconds, when the phase is set.
        value : float
            Phase to set to.
        units
            Units that the value is defined in.
        """
        self.phase.constant(t, value, units)

    def pulse(
        self,
        t,
        duration,
        amplitude,
        frequency,
        phase=None,
        amplitude_units=None,
        frequency_units=None,
        phase_units=None,
        print_summary=False,
    ):
        """Pulse the output.

        Parameters
        ----------
        t : float
            Time, in seconds, to start the pulse at.
        duration : float
            Length of the pulse, in seconds.
        amplitude : float
            Amplitude to set the output to during the pulse.
        frequency : float
            Frequency to set the output to during the pulse.
        phase : float, optional
            Phase to set the output to during the pulse.
        amplitude_units
            Units of `amplitude`.
        frequency_units
            Units of `frequency`.
        phase_units
            Units of `phase`.
        print_summary : bool, optional
            Print a summary of the pulse during compilation time.

        Returns
        -------
        float
            Duration of the pulse, in seconds.
        """
        if print_summary:
            functions.print_time(
                t,
                f"{self.name} pulse at {frequency/MHz:.4f} MHz "
                f"for {duration/ms:.3f} ms",
            )
        self.setamp(t, amplitude, amplitude_units)
        if frequency is not None:
            self.setfreq(t, frequency, frequency_units)
        if phase is not None:
            self.setphase(t, phase, phase_units)
        if amplitude != 0 and self.gate is not None:
            self.enable(t)
            self.disable(t + duration)
            self.setamp(t + duration, 0)
        return duration


class DDS(DDSQuantity):
    """DDS class for use with all devices that have DDS-like outputs."""


class StaticDDS(_DDSBase):
    """Static DDS class for use with all devices that have static DDS-like outputs.

    Its frequency, amplitude and phase hold one value for the whole shot,
    programmed before it starts, so its setters take no time.
    """

    description = "Static RF"
    allowed_children = [StaticAnalogQuantity, DigitalOut, StaticDigitalOut]
    channel_class = StaticAnalogQuantity

    def setamp(self, value, units=None):
        """Set the static amplitude of the output.

        Parameters
        ----------
        value : float
            Amplitude to set to.
        units
            Units that the value is defined in.
        """
        self.amplitude.constant(value, units)

    def setfreq(self, value, units=None):
        """Set the static frequency of the output.

        Parameters
        ----------
        value : float
            Frequency to set to.
        units
            Units that the value is defined in.
        """
        self.frequency.constant(value, units)

    def setphase(self, value, units=None):
        """Set the static phase of the output.

        Parameters
        ----------
        value : float
            Phase to set to.
        units
            Units that the value is defined in.
        """
        self.phase.constant(value, units)
