#####################################################################
#                                                                   #
# /core.py                                                          #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Core classes containing common device functionality - these are used in
labscript-devices when adding support for a hardware device."""

import sys

import numpy as np

from .base import Device
from .compiler import compiler
from .utils import LabscriptError, fastflatten, set_passed_properties


class IntermediateDevice(Device):
    """Base class for all devices that are to be clocked by a pseudoclock."""

    clock_limit = None
    """float: Fastest rate, in Hz, this device can be clocked at, or `None` for no
    limit of its own."""

    @set_passed_properties(property_names={})
    def __init__(self, name, parent_device, **kwargs):
        """Provides some error checking to ensure parent_device is a
        :obj:`ClockLine`.

        Calls :func:`Device.__init__`.

        Parameters
        ----------
        name : str
            python variable name to assign to device
        parent_device : :obj:`ClockLine`
            Parent ClockLine device.
        **kwargs
            Keyword arguments passed to :func:`Device.__init__`.

        Raises
        ------
        LabscriptError
            If `parent_device` is not a :obj:`ClockLine`.
        """
        self.name = name
        # This should be checked here because it should only be connected a clockline.
        # The allowed_children attribute of parent classes doesn't prevent this from
        # being connected to something that accepts an instance of 'Device' as a child
        if parent_device is not None and not isinstance(parent_device, ClockLine):
            if not hasattr(parent_device, "name"):
                parent_device_name = (
                    "Unknown: not an instance of a labscript device class"
                )
            else:
                parent_device_name = parent_device.name
            raise LabscriptError(
                f"Error instantiating device {name}. The parent ({parent_device_name}) "
                "must be an instance of ClockLine."
            )

        super().__init__(name, parent_device, "internal", **kwargs)

    @property
    def minimum_clock_high_time(self):
        if self.clock_limit is None:
            return 0

        # Convert clock limit to minimum pulse period and then divide by 2 to
        # get minimum half period. This is the fastest assuming the minimum high
        # time corresponds to half the fastest clock pulse supported.
        return 1/self.clock_limit/2


class ClockLine(Device):
    description = "Generic ClockLine"
    allowed_children = [IntermediateDevice]
    _clock_limit = None
    _minimum_clock_high_time = 0

    @property
    def parent_clock_line(self):
        return self

    @set_passed_properties(property_names={})
    def __init__(self, name, pseudoclock, connection, ramping_allowed=True, **kwargs):
        super().__init__(name, pseudoclock, connection, **kwargs)
        self.ramping_allowed = ramping_allowed

    def add_device(self, device):
        super().add_device(device)
        # Update clock limit if this new device is slower than all others attached
        if (
            device.clock_limit is not None
            and (self._clock_limit is None or device.clock_limit < self.clock_limit)
        ):
            self._clock_limit = device.clock_limit
        # Update minimum clock high time if this new device requires a longer one.
        self._minimum_clock_high_time = max(
            device.minimum_clock_high_time, self._minimum_clock_high_time
        )

    @property
    def clock_limit(self):
        """float: Clock limit for this line, typically set by speed of child
        Intermediate Devices."""
        # A property so that no child overwrites this value itself; add_device
        # above calculates the limit.
        if self._clock_limit is None:
            return self.parent_device.clock_limit
        return self._clock_limit

    @property
    def minimum_clock_high_time(self):
        """float: The minimum time a clock tick must be in the logical high state"""
        return self._minimum_clock_high_time


class Pseudoclock(Device):
    """Parent class of all pseudoclocks.

    You won't usually interact with this class directly, unless you are implementing a
    new PseudoclockDevice in labscript-devices. It provides common functionality for
    generating pseudoclock instructions.
    """

    description = "Generic Pseudoclock"
    allowed_children = [ClockLine]
    max_clock_lines = None
    """int: How many clock lines this pseudoclock can drive, or `None` for any
    number."""

    @set_passed_properties(property_names={})
    def __init__(
        self, name, pseudoclock_device, connection, max_clock_lines=None, **kwargs
    ):
        """Creates a Pseudoclock.

        Parameters
        ----------
        name : str
            python variable name to assign the device instance to.
        pseudoclock_device : :obj:`PseudoclockDevice`
            Parent pseudoclock device
        connection : str
            Connection on this device that links to parent
        max_clock_lines : int, optional
            How many clock lines this pseudoclock can drive. If `None`, the class's
            `max_clock_lines`.
        **kwargs
            Passed to `Device()`.
        """
        if max_clock_lines is not None:
            self.max_clock_lines = max_clock_lines
        super().__init__(name, pseudoclock_device, connection, **kwargs)
        self.clock_limit = pseudoclock_device.clock_limit
        self.clock_resolution = pseudoclock_device.clock_resolution

    def add_device(self, device):
        clock_lines = [d.name for d in self.child_devices if isinstance(d, ClockLine)]
        if (
            self.max_clock_lines is not None
            and isinstance(device, ClockLine)
            and len(clock_lines) >= self.max_clock_lines
        ):
            raise LabscriptError(
                f"{self.name} can drive only {self.max_clock_lines} clock line(s), so "
                f"{device.name} cannot be added. Use {', '.join(clock_lines)} instead."
            )
        super().add_device(device)

    def collect_change_times(self, all_outputs, outputs_by_clockline):
        """Asks all connected outputs for a list of times that they change state.

        Takes the union of all of these times. Note
        that at this point, a change from holding-a-constant-value
        to ramping-through-values is considered a single state
        change. The clocking times will be filled in later in the
        expand_change_times function, and the ramp values filled in with
        expand_timeseries.

        Parameters
        ----------
        all_outputs : list
            List of all outputs connected to this pseudoclock.
        outputs_by_clockline : dict
            List of all outputs connected to this pseudoclock, organized by
            clockline.

        Returns
        -------
        all_change_times : list
            List of all change times.
        change_times : dict
            Dictionary of all change times organised by which clock they are
            attached to.
        """
        change_times = {}
        all_change_times = []
        ramps_by_clockline = {}
        for clock_line, outputs in outputs_by_clockline.items():
            change_times.setdefault(clock_line, [])
            ramps_by_clockline.setdefault(clock_line, [])
            for output in outputs:
                output_change_times = output.get_change_times()
                change_times[clock_line].extend(output_change_times)
                all_change_times.extend(output_change_times)
                ramps_by_clockline[clock_line].extend(output.get_ramp_times())

        if not all_change_times:
            all_change_times.append(0)
        all_change_times.append(self.parent_device.stop_time)
        # include trigger times in change_times, so that pseudoclocks always
        # have an instruction immediately following a wait:
        all_change_times.extend(self.parent_device.trigger_times)

        # If a clockline has a change time during a ramp on another clockline, the
        # ramping clockline must break its loop at that time.
        all_change_times_numpy = np.array(all_change_times)
        all_change_times_numpy = self.quantise_to_pseudoclock(
            all_change_times_numpy
        )

        for clock_line, ramps in ramps_by_clockline.items():
            for ramp_start_time, ramp_end_time in ramps:
                # Add a change time to this clockline at any time in all_change_times
                # that falls inside the ramp.
                indices = np.where(
                    (ramp_start_time < all_change_times_numpy) &
                    (all_change_times_numpy < ramp_end_time)
                )
                for idx in indices[0]:
                    change_times[clock_line].append(all_change_times_numpy[idx])

        all_change_times = list(set(all_change_times_numpy))
        all_change_times.sort()

        # Check that the pseudoclock can handle updates this fast
        for i, t in enumerate(all_change_times[:-1]):
            dt = all_change_times[i+1] - t
            if dt < 1.0/self.clock_limit:
                raise LabscriptError(
                    "Commands have been issued to devices attached to "
                    f"{self.name} at t={t} and t={all_change_times[i+1]}. "
                    "This Pseudoclock cannot support update delays shorter "
                    f"than {1.0/self.clock_limit} seconds."
                )

        # For each clockline, make sure there is a change time for triggers,
        # stop_time and t=0, and check that no change times are too close together.
        for clock_line, change_time_list in change_times.items():
            # include trigger times in change_times, so that pseudoclocks always
            # have an instruction immediately following a wait:
            change_time_list.extend(self.parent_device.trigger_times)

            # If the device has no children, we still need it to have a
            # single instruction. So we'll add 0 as a change time:
            if not change_time_list:
                change_time_list.append(0)

            change_time_list = self.quantise_to_pseudoclock(change_time_list)

            # Get rid of duplicates if trigger times were already in the list:
            change_time_list = list(set(change_time_list))
            change_time_list.sort()

            # Also add the stop time as as change time. First check that it
            # isn't too close to the time of the last instruction:
            if not self.parent_device.stop_time in change_time_list:
                dt = self.parent_device.stop_time - change_time_list[-1]
                if abs(dt) < 1.0/clock_line.clock_limit:
                    raise LabscriptError(
                        "The stop time of the experiment is "
                        f"t={self.parent_device.stop_time}, but the last "
                        f"instruction for a device attached to {self.name} is "
                        f"at t={change_time_list[-1]}. One or more connected "
                        "devices cannot support update delays shorter than "
                        f"{1.0/clock_line.clock_limit} seconds. Please set the "
                        "stop_time a bit later."
                    )

                change_time_list.append(self.parent_device.stop_time)

                # Sorting puts stop_time in the middle if it is before the last
                # instruction. That is a user error, left uncaught here so the device
                # with instructions after stop_time can report it in more detail.
                change_time_list.sort()

            # index to keep track of in all_change_times
            j = 0
            # Check that no two instructions are too close together:
            for i, t in enumerate(change_time_list[:-1]):
                dt = change_time_list[i+1] - t
                if dt < 1.0/clock_line.clock_limit:
                    raise LabscriptError(
                        "Commands have been issued to devices attached to "
                        f"clockline {clock_line.name} at t={t} and "
                        f"t={change_time_list[i+1]}. One or more connected "
                        f"devices on ClockLine {clock_line.name} cannot "
                        "support update delays shorter than "
                        f"{1.0/clock_line.clock_limit} seconds"
                    )

                all_change_times_len = len(all_change_times)
                # increment j until we reach the current time
                while all_change_times[j] < t and j < all_change_times_len-1:
                    j += 1
                # j now indexes all_change_times at "t". Check that the next change
                # time is not so close that this clock tick would be shorter than the
                # minimum clock high time.
                dt = all_change_times[j+1] - t
                if dt < (2 * clock_line.minimum_clock_high_time):
                    raise LabscriptError(
                        "Commands have been issued to devices attached to "
                        f"{self.name} at t={t} and t={all_change_times[j+1]}. "
                        "One or more connected devices on ClockLine "
                        f"{clock_line.name} cannot support clock ticks with a "
                        "digital high time shorter than "
                        f"{clock_line.minimum_clock_high_time} which is more "
                        "than half the available time between the event at "
                        f"t={t} on ClockLine {clock_line.name} and the next "
                        "event on another ClockLine."
                    )

            # because we made the list into a set and back to a list, it is now
            # a different object so modifying it won't update the list in the
            # dictionary. So store the updated list in the dictionary
            change_times[clock_line] = change_time_list
        return all_change_times, change_times

    def expand_change_times(self, all_change_times, change_times, outputs_by_clockline):
        """For each time interval delimited by change_times, constructs an array of
        times at which the clock for this device needs to tick.

        If the interval has all outputs having constant values, then only the start
        time is stored. If one or more outputs are ramping, then the clock ticks at
        the maximum clock rate requested by any of the outputs. Also produces a
        higher level description of the clocking; self.clock. This list contains the
        information that facilitates programming a pseudo clock using loops.
        """
        all_times = {}
        clock = []
        clock_line_current_indices = {}
        for clock_line, outputs in outputs_by_clockline.items():
            clock_line_current_indices[clock_line] = 0
            all_times[clock_line] = []

        for i, time in enumerate(all_change_times):
            if time in self.parent_device.trigger_times[1:]:
                # A wait instruction:
                clock.append("WAIT")

            enabled_clocks = []
            enabled_looping_clocks = []

            # update clock_line indices
            for clock_line in clock_line_current_indices:
                try:
                    while (
                        change_times[clock_line][clock_line_current_indices[clock_line]]
                        < time
                    ):
                        clock_line_current_indices[clock_line] += 1
                except IndexError:
                    # Fix the index to the last one
                    clock_line_current_indices[clock_line] = (
                        len(change_times[clock_line]) - 1
                    )
                    sys.stderr.write(
                        f"WARNING: ClockLine {clock_line.name} has it's last change "
                        f"time at t={change_times[clock_line][-1]:.15f} but another "
                        f"ClockLine has a change time at t={time:.15f}. "
                        "This should never happen, as the last change time should "
                        "always be the time passed to stop(). Perhaps you have an "
                        "instruction after the stop time of the experiment?"
                        "\n"
                    )

                # Let's work out which clock_lines are enabled for this instruction
                if (
                    time
                    == change_times[clock_line][clock_line_current_indices[clock_line]]
                ):
                    enabled_clocks.append(clock_line)

            # what's the fastest clock rate?
            maxrate = 0
            local_clock_limit = self.clock_limit  # the Pseudoclock clock limit
            for clock_line in enabled_clocks:
                for output in outputs_by_clockline[clock_line]:
                    if not hasattr(output, "timeseries"):
                        continue
                    # If the output is sweeping and has the highest clock rate so
                    # far, store its clock rate as maxrate:
                    output_instruction = output.timeseries[
                        clock_line_current_indices[clock_line]
                    ]
                    if isinstance(output_instruction, dict):
                        if clock_line not in enabled_looping_clocks:
                            enabled_looping_clocks.append(clock_line)

                        if output_instruction["clock rate"] > maxrate:
                            maxrate = output_instruction["clock rate"]

                        # Only ramping clock_lines need checking here: non-ramping
                        # ones had their clock_limit checked in collect_change_times()
                        if local_clock_limit > clock_line.clock_limit:
                            local_clock_limit = clock_line.clock_limit

            if maxrate:
                # round to the nearest clock rate the pseudoclock can actually support
                period = 1/maxrate
                quantised_period = period/self.clock_resolution
                # At least one tick; the clock limit check below refuses it if
                # that is too fast:
                quantised_period = max(1, round(quantised_period))
                period = quantised_period*self.clock_resolution
                maxrate = 1/period
            if maxrate > local_clock_limit:
                raise LabscriptError(
                    f"At t = {time} sec, a clock rate of {maxrate} Hz was requested. "
                    f"One or more devices connected to {self.name} cannot support "
                    f"clock rates higher than {local_clock_limit} Hz."
                )

            if maxrate:
                # If there was ramping at this timestep, how many clock ticks fit before
                # the next instruction?
                n_ticks, remainder = np.divmod(
                    (all_change_times[i+1] - time)*maxrate, 1
                )
                n_ticks = int(n_ticks)
                # Can we squeeze the final clock cycle in at the end?
                if remainder and remainder/float(maxrate) >= 1/float(local_clock_limit):
                    # Yes we can. Clock speed will be as
                    # requested. Otherwise the final clock cycle will
                    # be too long, by the fraction 'remainder'.
                    n_ticks += 1
                duration = n_ticks/float(maxrate)  # avoiding integer division
                ticks = np.linspace(time, time + duration, n_ticks, endpoint=False)

                for clock_line in enabled_clocks:
                    if clock_line in enabled_looping_clocks:
                        all_times[clock_line].append(ticks)
                    else:
                        all_times[clock_line].append(time)

                if n_ticks > 1:
                    # If n_ticks is only one, this step has reps=0 and does nothing,
                    # so only include it if n_ticks > 1.
                    if n_ticks > 2:
                        # Split the ramp into an initial clock tick, during which the
                        # slow clock ticks, and the rest of the ramping time, during
                        # which the slow clock does not tick.
                        clock.append(
                            {
                                "start": time,
                                "reps": 1,
                                "step": 1/float(maxrate),
                                "enabled_clocks": enabled_clocks,
                            }
                        )
                        clock.append(
                            {
                                "start": time + 1/float(maxrate),
                                "reps": n_ticks - 2,
                                "step": 1/float(maxrate),
                                "enabled_clocks": enabled_looping_clocks,
                            }
                        )
                    else:
                        clock.append(
                            {
                                "start": time,
                                "reps": n_ticks - 1,
                                "step": 1/float(maxrate),
                                "enabled_clocks": enabled_clocks,
                            }
                        )

                # The last clock tick's duration depends on the next step.
                clock.append(
                    {
                        "start": ticks[-1],
                        "reps": 1,
                        "step": all_change_times[i+1] - ticks[-1],
                        "enabled_clocks": enabled_clocks
                        if n_ticks == 1
                        else enabled_looping_clocks,
                    }
                )
            else:
                for clock_line in enabled_clocks:
                    all_times[clock_line].append(time)

                try:
                    # If there was no ramping, here is a single clock tick:
                    clock.append(
                        {
                            "start": time,
                            "reps": 1,
                            "step": all_change_times[i+1] - time,
                            "enabled_clocks": enabled_clocks,
                        }
                    )
                except IndexError:
                    if i != len(all_change_times) - 1:
                        raise
                    if self.parent_device.stop_time > time:
                        # There is no next instruction. Hold the last clock
                        # tick until self.parent_device.stop_time.
                        raise LabscriptError(
                            "This shouldn't happen -- stop_time should always be equal "
                            "to the time of the last instruction. Please report a bug."
                        )
                    # Error if stop_time has been set to less than the time of the
                    # last instruction:
                    elif self.parent_device.stop_time < time:
                        raise LabscriptError(
                            f"{self.description} {self.name} has more instructions "
                            f"(at t={time:.15f}) after the experiment's stop time "
                            f"(t={self.parent_device.stop_time:.15f})."
                        )
                    # If stop_time equals the time of the last instruction, still
                    # output that instruction so the number of clock ticks matches the
                    # number of points in the Output.raw_output arrays. The tick is on
                    # every clock line, so it meets every line's limits, as every other
                    # tick does.
                    else:
                        enabled_clocks = list(outputs_by_clockline)
                        step = max(
                            [1.0 / self.clock_limit]
                            + [
                                max(
                                    1.0 / clock_line.clock_limit,
                                    2 * clock_line.minimum_clock_high_time,
                                )
                                for clock_line in enabled_clocks
                            ]
                        )
                        clock.append(
                            {
                                "start": time,
                                "reps": 1,
                                "step": step,
                                "enabled_clocks": enabled_clocks,
                            }
                        )

        return all_times, clock

    def get_outputs_by_clockline(self):
        """Obtain all outputs by clockline.

        Returns
        -------
        all_outputs : list
            List of all outputs, obtained from :meth:`get_all_outputs`.
        outputs_by_clockline : dict
            Dictionary of outputs, organised by clockline.
        """
        outputs_by_clockline = {}
        for clock_line in self.child_devices:
            if isinstance(clock_line, ClockLine):
                outputs_by_clockline[clock_line] = []

        all_outputs = self.get_all_outputs()
        for output in all_outputs:
            clock_line = output.parent_clock_line
            assert clock_line.parent_device == self
            outputs_by_clockline[clock_line].append(output)

        return all_outputs, outputs_by_clockline

    def generate_clock(self):
        """Generate the pseudoclock and configure outputs for each tick
        of the clock.
        """
        all_outputs, outputs_by_clockline = self.get_outputs_by_clockline()

        # Get change_times for all outputs, and also grouped by clockline
        all_change_times, change_times = self.collect_change_times(
            all_outputs, outputs_by_clockline
        )

        for clock_line, clock_line_change_times in change_times.items():
            for output in outputs_by_clockline[clock_line]:
                # Expand the instructions for each change time on this clock line
                output.make_timeseries(clock_line_change_times)

        # Generate the clock meta data for the Pseudoclock, and every time point each
        # clock line will tick (expanding ramps)
        all_times, self.clock = self.expand_change_times(
            all_change_times, change_times, outputs_by_clockline
        )

        # Flatten the clock line times for the child devices to write instruction
        # tables
        self.times = {}
        for clock_line, time_array in all_times.items():
            self.times[clock_line] = fastflatten(time_array, np.dtype(float))

        for clock_line, outputs in outputs_by_clockline.items():
            clock_line_len = len(self.times[clock_line])
            for output in outputs:
                # evaluate the output at each time point the clock line will tick at
                output.expand_timeseries(all_times[clock_line], clock_line_len)

    def generate_code(self, hdf5_file):
        self.generate_clock()
        super().generate_code(hdf5_file)


class TriggerableDevice(Device):
    """A triggerable version of :obj:`Device`.

    This class is for devices that do not require a pseudoclock, but do require a
    trigger. This enables them to have a Trigger device as a parent.
    """

    trigger_edge_type = "rising"
    """str: Type of trigger. Must be `'rising'` or `'falling'`."""
    minimum_recovery_time = 0
    """float: Minimum time required before another trigger can occur."""
    trigger_device = None
    """:obj:`Trigger`: The trigger this device is attached to, or `None` if it is
    parentless."""

    @set_passed_properties(property_names={})
    def __init__(self, name, parent_device, connection, parentless=False, **kwargs):
        """Instantiate a Triggerable Device.

        Parameters
        ----------
        name : str
            python variable name to assign to this device.
        parent_device : :obj:`Device`
            Parent device that provides the trigger.
        connection : str
            Connection on the parent device.
        parentless : bool, optional
            Set to `True` if this device does not require a parent.
        **kwargs
            Passed to :meth:`Device.__init__`.

        Raises
        ------
        LabscriptError
            If trigger type of this device does not match the trigger type of the
            parent Trigger.
        """
        from .labscript import Trigger

        if None in [parent_device, connection] and not parentless:
            raise LabscriptError(
                "No parent specified. If this device does not require a parent, set "
                "parentless=True"
            )
        if isinstance(parent_device, Trigger):
            if self.trigger_edge_type != parent_device.trigger_edge_type:
                raise LabscriptError(
                    f"Trigger edge type for {name} is '{self.trigger_edge_type}', but "
                    f"existing Trigger object {parent_device.name} has edge type "
                    f"'{parent_device.trigger_edge_type}'"
                )
            self.trigger_device = parent_device
        elif parent_device is not None:
            # Instantiate a trigger object to be our parent:
            self.trigger_device = Trigger(
                f"{name}_trigger", parent_device, connection, self.trigger_edge_type
            )
            parent_device = self.trigger_device
            connection = "trigger"

        self.__triggers = []
        super().__init__(name, parent_device, connection, **kwargs)

    def trigger(self, t, duration):
        """Request parent trigger device to produce a trigger.

        Parameters
        ----------
        t : float
            Time, in seconds, to produce a trigger.
        duration : float
            Duration, in seconds, of the trigger pulse.
        """
        if self.trigger_device is None:
            raise LabscriptError(
                f"{self.description} {self.name} has no trigger device, so it cannot "
                "be triggered."
            )
        # On the tick of the clock that fires the trigger, so that requests from
        # devices sharing it compare equal:
        t = self.trigger_device._round_time(t)
        # Only ask for a trigger if another device attached to the same trigger has
        # not already requested it:
        already_requested = False
        for other_device in self.trigger_device.child_devices:
            if other_device is not self:
                for other_t, other_duration in other_device.__triggers:
                    if t == other_t and duration == other_duration:
                        already_requested = True
        if not already_requested:
            self.trigger_device.trigger(t, duration)

        # Check for triggers too close together (check for overlapping triggers already
        # performed in Trigger.trigger()):
        start = t
        end = t + duration
        for other_t, other_duration in self.__triggers:
            other_start = other_t
            other_end = other_t + other_duration
            if (
                abs(other_start - end) < self.minimum_recovery_time
                or abs(other_end - start) < self.minimum_recovery_time
            ):
                raise ValueError(
                    f"{self.description} {self.name} has two triggers closer together "
                    f"than the minimum recovery time: one at t = {start:.15f}s for "
                    f"{duration}s, and another at t = {other_start:.15f}s for "
                    f"{other_duration}s. "
                    f"The minimum recovery time is {self.minimum_recovery_time}s."
                )

        self.__triggers.append([t, duration])

    def do_checks(self):
        """Check that all devices sharing a trigger device have triggers when
        this device has a trigger.

        Raises
        ------
        LabscriptError
            If correct triggers do not exist for all devices.
        """
        if self.trigger_device is None:
            return
        for device in self.trigger_device.child_devices:
            if device is not self:
                for trigger in self.__triggers:
                    if trigger not in device.__triggers:
                        start, duration = trigger
                        raise LabscriptError(
                            f"TriggerableDevices {self.name} and {device.name} share a "
                            f"trigger. {self.name} has a trigger at {start}s for "
                            f"{duration}s, but there is no matching trigger for "
                            f"{device.name}. Devices sharing a trigger must have "
                            "identical trigger times and durations."
                        )

    def generate_code(self, hdf5_file):
        self.do_checks()
        super().generate_code(hdf5_file)


class PseudoclockDevice(TriggerableDevice):
    """Device that implements a pseudoclock.

    labscript records the device properties `is_master_pseudoclock` and
    `stop_time`, the end of the device's program in its own time base, for every
    pseudoclock device, and `trigger_times`, the script times its program starts and
    resumes from, each trigger plus any `wait_delay`, for every one but the master.
    A subclass must not set `is_master_pseudoclock` or `stop_time` itself.
    """

    description = "Generic Pseudoclock Device"
    allowed_children = [Pseudoclock]
    max_pseudoclocks = None
    """int: How many pseudoclocks this device has, or `None` for any number."""
    trigger_edge_type = "rising"
    # How long after a trigger the next instruction is actually output:
    trigger_delay = 0
    # How long a trigger line must remain high/low in order to be detected:
    trigger_minimum_duration = 0
    # How long after the start of a wait instruction the device is actually capable
    # of resuming:
    wait_delay = 0

    @property
    def pseudoclock_device(self):
        return self

    @set_passed_properties(property_names={})
    def __init__(self, name, trigger_device=None, trigger_connection=None, **kwargs):
        """Instantiates a pseudoclock device.

        Parameters
        ----------
        name : str
            python variable to assign to this device.
        trigger_device : :obj:`DigitalOut`, optional
            Sets the parent triggering output. If `None`, this is considered the
            master pseudoclock.
        trigger_connection : str, optional
            Must be provided if `trigger_device` is provided. Specifies the channel
            of the parent device.
        **kwargs
            Passed to :meth:`TriggerableDevice.__init__`.
        """
        if trigger_device is None:
            for device in compiler.inventory:
                if (
                    isinstance(device, PseudoclockDevice)
                    and device.is_master_pseudoclock
                ):
                    raise LabscriptError(
                        f"There is already a master pseudoclock device: {device.name}. "
                        "There cannot be multiple master pseudoclock devices - please "
                        "provide a trigger_device for one of them."
                    )
            super().__init__(
                name, parent_device=None, connection=None, parentless=True, **kwargs
            )
        else:
            # The parent device declared was a digital output channel: the following
            # will automatically instantiate a Trigger for it and set it as
            # self.trigger_device:
            super().__init__(
                name,
                parent_device=trigger_device,
                connection=trigger_connection,
                **kwargs
            )
            # Ensure that the parent pseudoclock device is the master pseudoclock.
            if not self.trigger_device.pseudoclock_device.is_master_pseudoclock:
                raise LabscriptError(
                    "All secondary pseudoclock devices must be triggered by a device "
                    "being clocked by the master pseudoclock device. Pseudoclocks "
                    "triggering each other in series is not supported."
                )
        self.trigger_times = []
        self.initial_trigger_time = 0

    def add_device(self, device):
        pseudoclocks = [
            d.name for d in self.child_devices if isinstance(d, Pseudoclock)
        ]
        if (
            self.max_pseudoclocks is not None
            and isinstance(device, Pseudoclock)
            and len(pseudoclocks) >= self.max_pseudoclocks
        ):
            raise LabscriptError(
                f"{self.description} {self.name} can have only "
                f"{self.max_pseudoclocks} pseudoclock(s), so {device.name} cannot be "
                f"added. Use {', '.join(pseudoclocks)} instead."
            )
        super().add_device(device)

    @property
    def is_master_pseudoclock(self):
        """bool: Whether this device is the master pseudoclock."""
        return self.parent_device is None

    def set_initial_trigger_time(self, t):
        """Sets the initial trigger time of the pseudoclock.

        The initial trigger time of the master pseudoclock is always 0 and cannot be
        changed.

        Parameters
        ----------
        t : float
            Time, in seconds, to trigger this device.

        Raises
        ------
        LabscriptError
            If called after `start()`, or on the master pseudoclock.
        """
        if compiler.start_called:
            raise LabscriptError(
                "Initial trigger times must be set prior to calling start()"
            )
        if self.is_master_pseudoclock:
            raise LabscriptError(
                "Initial trigger time of master clock is always zero, it cannot be "
                "changed."
            )
        else:
            # On the tick of the clock that fires the trigger:
            self.initial_trigger_time = self.trigger_device._round_time(t)

    def trigger(self, t, duration, wait_delay=0):
        """Ask the trigger device to produce a digital pulse of a given duration
        to trigger this pseudoclock.

        Parameters
        ----------
        t : float
            Time, in seconds, to trigger this device.
        duration : float
            Duration, in seconds, of the trigger pulse.
        wait_delay : float, optional
            Time, in seconds, to delay the trigger.
        """
        if isinstance(t, str) and t == "initial":
            t = self.initial_trigger_time
        # Trigger times are rounded as the triggering clock rounds its own times:
        if self.is_master_pseudoclock:
            t = self.quantise_to_pseudoclock(t)
            if compiler.wait_monitor is not None:
                # Make the wait monitor pulse to signify starting or resumption of the
                # experiment:
                compiler.wait_monitor.trigger(t, duration)
            self.trigger_times.append(t)
        else:
            t = self.trigger_device._round_time(t)
            super().trigger(t, duration)
            self.trigger_times.append(self.trigger_device._round_time(t + wait_delay))
        # In time order, which the trigger offsets count in, whatever order waits
        # were called in:
        self.trigger_times.sort()

    def do_checks(self, outputs):
        """Basic error checking to ensure the user's instructions make sense.

        Parameters
        ----------
        outputs : list
            List of outputs to check.
        """
        TriggerableDevice.do_checks(self)
        for output in outputs:
            output.do_checks(self.trigger_times)

    def offset_instructions_from_trigger(self, outputs):
        """Offset instructions for child devices by the appropriate trigger times.

        Parameters
        ----------
        outputs : list
            List of outputs to offset.
        """
        for output in outputs:
            output.offset_instructions_from_trigger(self.trigger_times)

        if not self.is_master_pseudoclock:
            # Store the unmodified initial_trigger_time
            initial_trigger_time = self.trigger_times[0]
            # Adjust the stop time relative to the last trigger time
            self.stop_time = (
                self.stop_time
                - initial_trigger_time
                - self.trigger_delay * len(self.trigger_times)
            )

            # Modify the trigger times themselves so that we insert wait instructions
            # at the right times:
            self.trigger_times = [
                t - initial_trigger_time - i*self.trigger_delay
                for i, t in enumerate(self.trigger_times)
            ]

        # quantise the trigger times and stop time to the pseudoclock clock resolution
        self.trigger_times = self.quantise_to_pseudoclock(self.trigger_times)
        self.stop_time = self.quantise_to_pseudoclock(self.stop_time)

    def set_property(self, name, value, location=None, overwrite=False):
        if (
            name in ('is_master_pseudoclock', 'stop_time')
            and location == 'device_properties'
            and self._properties is not None
            and name in self._properties[location]
        ):
            raise LabscriptError(
                f"{type(self).__name__} sets the device property {name}, which "
                "labscript records for every pseudoclock device. Delete the "
                "set_property call that sets it; see the PseudoclockDevice "
                "documentation."
            )
        super().set_property(name, value, location, overwrite)

    def generate_code(self, hdf5_file):
        outputs = self.get_all_outputs()
        self.do_checks(outputs)
        if not self.is_master_pseudoclock:
            # The script times its program resumes from, each trigger plus any
            # wait_delay as the trigger device rounded it, before the offsets:
            trigger_times = [float(t) for t in self.trigger_times]
            self.set_property(
                'trigger_times', trigger_times, location='device_properties'
            )
        self.offset_instructions_from_trigger(outputs)
        self.set_property(
            'is_master_pseudoclock',
            self.is_master_pseudoclock,
            location='device_properties',
        )
        self.set_property('stop_time', self.stop_time, location='device_properties')
        # TriggerableDevice.generate_code would call do_checks() without the outputs
        # this class's do_checks needs.
        Device.generate_code(self, hdf5_file)

