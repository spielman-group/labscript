#####################################################################
#                                                                   #
# /functions.py                                                     #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Functional forms of analog output ramps.

These are not used directly; see the interfaces in `AnalogQuantity`/`AnalogOut`.
"""

import numpy as np

from .utils import print_time


def ramp(duration, initial, final):
    """Defines a linear ramp.

    f(t) = (final - initial)*t/duration + initial

    Parameters
    ----------
    duration : float
        Duration of ramp.
    initial : float
        Starting value of ramp.
    final : float
        Ending value of ramp.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    m = (final - initial) / duration
    return lambda t: m * t + initial


def sine(duration, amplitude, angfreq, phase, dc_offset):
    """Defines a sine wave.

    f(t) = amplitude*sin(angfreq*t + phase) + dc_offset

    Parameters
    ----------
    duration : float
        Not used.
    amplitude : float
        Amplitude of sine wave.
    angfreq : float
        Angular frequency of sine wave.
    phase : float
        Phase of sine wave.
    dc_offset : float
        Vertical offset of sine wave.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    return lambda t: amplitude * np.sin(angfreq * t + phase) + dc_offset


def sine_ramp(duration, initial, final):
    """Defines a square sinusoidally increasing ramp.

    f(t) = (final-initial)*(sin(pi*t/(2*duration)))^2 + initial

    Parameters
    ----------
    duration : float
        Length of time for the ramp to complete.
    initial : float
        Initial value of ramp.
    final : float
        Final value of ramp.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    return (
        lambda t: (final - initial) * (np.sin(np.pi * t / (2 * duration))) ** 2
        + initial
    )


def sine4_ramp(duration, initial, final):
    """Defines a quartic sinusoidally increasing ramp.

    f(t) = (final-initial)*(sin(pi*t/(2*duration)))^4 + initial

    Parameters
    ----------
    duration : float
        Length of time for the ramp to complete.
    initial : float
        Initial value of ramp.
    final : float
        Final value of ramp.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    return (
        lambda t: (final - initial) * (np.sin(np.pi * t / (2 * duration))) ** 4
        + initial
    )


def sine4_reverse_ramp(duration, initial, final):
    """Defines `sine4_ramp` run backwards in time: from `final` to `initial`.

    f(t) = (final-initial)*(sin(pi/2+pi*t/(2*duration)))^4 + initial

    Parameters
    ----------
    duration : float
        Length of time for the ramp to complete.
    initial : float
        Value the ramp ends at.
    final : float
        Value the ramp starts at.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    return (
        lambda t: (final - initial)
        * (np.sin(np.pi / 2 + np.pi * t / (2 * duration))) ** 4
        + initial
    )


def exp_ramp(duration, initial, final, zero):
    """Defines an exponential ramp via offset value.

    f(t) = (initial-zero)*e^(-rate*t) + zero
    rate = log((initial-zero)/(final-zero))/duration

    Parameters
    ----------
    duration : float
        Length of time for the ramp to complete.
    initial : float
        Initial value of ramp.
    final : float
        Final value of ramp.
    zero : float
        Zero offset of ramp.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    rate = 1 / duration * np.log((initial - zero) / (final - zero))
    return lambda t: (initial - zero) * np.exp(-rate * t) + zero


def exp_ramp_t(duration, initial, final, time_constant):
    """Defines an exponential ramp via time constant.

    f(t) = (initial-zero)*e^(-t/time_constant) + zero
    zero = (final-initial*e^(-duration/time_constant))/(1-e^(-duration/time_constant))

    Parameters
    ----------
    duration : float
        Length of time for the ramp to complete.
    initial : float
        Initial value of ramp.
    final : float
        Final value of ramp.
    time_constant : float
        Time constant of the exponential.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    zero = (final - initial * np.exp(-duration / time_constant)) / (
        1 - np.exp(-duration / time_constant)
    )
    return lambda t: (initial - zero) * np.exp(-t / time_constant) + zero


def piecewise_accel(duration, initial, final):
    """Defines a ramp from `initial` to `final` that starts and ends at rest.

    Its acceleration is a triangle wave, so the value is cubic in each third of
    `duration`.

    Parameters
    ----------
    duration : float
        Length of time for the acceleration to complete.
    initial : float
        Initial value.
    final : float
        Final value.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """
    a = final - initial
    return lambda t: initial + a * (
        (9.0 / 2 * t**3 / duration**3) * (t < duration / 3)
        + (
            -9 * t**3 / duration**3
            + 27.0 / 2 * t**2 / duration**2
            - 9.0 / 2 * t / duration
            + 1.0 / 2
        )
        * (t < 2 * duration / 3)
        * (t >= duration / 3)
        + (
            9.0 / 2 * t**3 / duration**3
            - 27.0 / 2 * t**2 / duration**2
            + 27.0 / 2 * t / duration
            - 7.0 / 2
        )
        * (t >= 2 * duration / 3)
    )


def square_wave(duration, level_0, level_1, frequency, phase, duty_cycle):
    """Defines a square wave that is `level_0` for the first part of each period.

    The output is `level_0` for phases in [0, `duty_cycle`) and `level_1` for the
    rest of the period, where the phase is ``(frequency*t + phase) % 1``.

    Parameters
    ----------
    duration : float
        Not used.
    level_0 : float
        Output value at the start of each period.
    level_1 : float
        Output value from `duty_cycle` to the end of each period.
    frequency : float
        Frequency of the wave.
    phase : float
        Phase of the wave, in periods (1 is a full period, not 2*pi).
    duty_cycle : float
        Fraction of each period, between 0 and 1, spent at `level_0`.

    Returns
    -------
    func
        Function that takes a single parameter `t`.
    """

    def square_wave_fixed_parameters(t):
        edge_phase_0_to_1 = duty_cycle
        wrapped_phases = (frequency * t + phase) % 1.0
        # A scalar t gives a scalar phase, which cannot be indexed below.
        wrapped_phases = np.array(wrapped_phases)

        # A phase just below a transition (within PHASE_TOLERANCE) is rounded up to
        # it so the output changes there. PHASE_TOLERANCE is half the phase advanced
        # in 0.1 ns: well below any clock tick, well above float error.
        TIME_TOLERANCE = 0.1e-9
        MIN_PHASE_STEP = frequency * TIME_TOLERANCE
        PHASE_TOLERANCE = MIN_PHASE_STEP / 2.0
        is_near_edge = np.isclose(
            wrapped_phases,
            edge_phase_0_to_1,
            rtol=0,
            atol=PHASE_TOLERANCE,
        )
        wrapped_phases[is_near_edge] = edge_phase_0_to_1
        # The level_1 -> level_0 transition is at phase 1, which wraps to 0.
        is_near_edge = np.isclose(
            wrapped_phases,
            1,
            rtol=0,
            atol=PHASE_TOLERANCE,
        )
        wrapped_phases[is_near_edge] = 0

        outputs = np.full_like(t, level_0)
        level_1_times = wrapped_phases >= edge_phase_0_to_1
        outputs[level_1_times] = level_1
        return outputs

    return square_wave_fixed_parameters


def pulse_sequence(pulse_sequence, period):
    """Returns a function that interpolates a pulse sequence.

    Relies on :obj:`numpy.digitize` to perform the interpolation.

    Parameters
    ----------
    pulse_sequence : :obj:`numpy:numpy.ndarray`
        2-D timeseries of change times and associated states.
    period : float
        How long, in seconds, to hold the final state before repeating the
        sequence.

    Returns
    -------
    func
        Interpolating function that takes a single parameter `t`. Only well
        defined if `t` falls within the `pulse_sequence` change times.
    """
    pulse_sequence = np.asarray(
        sorted(pulse_sequence, key=lambda x: x[0], reverse=True)
    )
    pulse_sequence_times = pulse_sequence[:, 0]
    pulse_sequence_states = pulse_sequence[:, 1]

    def pulse_function(t):
        try:
            len(t)
            is_array = True
        except TypeError:
            t = np.array([t])
            is_array = False

        times = t % period
        indices = np.digitize(times, pulse_sequence_times, right=False)
        states = pulse_sequence_states[indices]

        if is_array:
            return states
        else:
            return states[0]

    return pulse_function
