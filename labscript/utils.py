#####################################################################
#                                                                   #
# /utils.py                                                         #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Utility functions"""

import contextlib
from inspect import getcallargs
from functools import wraps
import warnings

import numpy as np

from .compiler import compiler


def print_time(t, description):
    """Print time with a descriptive string.

    Useful debug tool to print time at a specific point in the shot, during shot
    compilation. Helpful when the time is calculated.

    Parameters
    ----------
    t : float
        Time to print.
    description : str
        Descriptive label to print with it.
    """
    print(f"t={t:.9f}s: {description}")


def set_passed_properties(property_names=None):
    """Decorator for device __init__ methods that saves arguments as properties.

    Argument values as passed to __init__ will be saved, with the exception that if an
    instance attribute exists after __init__ has run that has the same name as an
    argument, the instance attribute will be saved instead of the argument value. This
    allows code within __init__ to process default arguments before they are saved.

    Internally, all properties are accessed by calling
    :obj:`self.get_property() <Device.get_property>`.

    Parameters
    ----------
    property_names : dict
        A dictionary {key:val}, where each ``val`` is a list [var1, var2, ...] of
        instance attribute names and/or method call arguments (of the decorated
        method). Values of the instance attributes/method call arguments will be
        saved to the location specified by ``key``.
    """
    property_names = property_names or {}

    def decorator(func):
        @wraps(func)
        def new_function(inst, *args, **kwargs):
            return_value = func(inst, *args, **kwargs)

            call_values = getcallargs(func, inst, *args, **kwargs)

            # In declaration order, so that a shot file's bytes are reproducible:
            all_property_names = dict.fromkeys(
                name for names in property_names.values() for name in names
            )

            property_values = {}
            for name in all_property_names:
                # If there is an instance attribute with that name, use that, otherwise
                # use the call value:
                if hasattr(inst, name):
                    property_values[name] = getattr(inst, name)
                else:
                    property_values[name] = call_values[name]

            inst.set_properties(property_values, property_names)

            return return_value

        return new_function

    return decorator


def renamed_keyword(kwargs, old, new, value, where):
    """Return `kwargs[old]`, warning that `where` will drop it for `new`, if it was
    given, or else `value`.

    For a renamed keyword argument whose old name still works for now: `kwargs` is
    the callable's `**kwargs`, from which `old` is removed.
    """
    if old not in kwargs:
        return value
    warnings.warn(
        f"{where}'s {old} will be removed; use {new}.", FutureWarning, stacklevel=3
    )
    return kwargs.pop(old)


def fastflatten(inarray, dtype):
    """A faster way of flattening our arrays than pylab.flatten.

    pylab.flatten returns a generator which takes a lot of time and memory to convert
    into a numpy array via array(list(generator)). The problem is that generators
    don't know how many values they'll return until they're done. This algorithm
    produces a numpy array directly by first calculating what the length will be. It
    is several orders of magnitude faster. Note that we can't use
    numpy.ndarray.flatten here since our inarray is really a list of 1D arrays of
    varying length and/or single values, not a N-dimensional block of homogeneous data
    like a numpy array.

    Parameters
    ----------
    inarray : list
        List of 1-D arrays to flatten.
    dtype : data-type
        Type of the data in the arrays.

    Returns
    -------
    :obj:`numpy:numpy.ndarray`
        Flattened array.
    """
    total_points = np.sum(
        [len(element) if np.iterable(element) else 1 for element in inarray]
    )
    flat = np.empty(total_points, dtype=dtype)
    i = 0
    for val in inarray:
        if np.iterable(val):
            flat[i : i + len(val)] = val[:]
            i += len(val)
        else:
            flat[i] = val
            i += 1
    return flat


def max_or_zero(*args, **kwargs):
    """Returns max of the arguments or zero if sequence is empty.

    Deprecated: use ``max(..., default=0)``.

    This protects the call to `max()` which would normally throw an error on an empty
    sequence.

    Parameters
    ----------
    *args
        Items to compare.
    **kwargs
        Passed to `max()`.

    Returns
    -------
    object
        Max of ``*args``, or 0 if empty.
    """
    warnings.warn(
        "max_or_zero will be removed from labscript; use max(..., default=0).",
        FutureWarning,
        stacklevel=2,
    )
    if not args:
        return 0
    if not args[0]:
        return 0
    else:
        return max(*args, **kwargs)


def bitfield(arrays, dtype):
    """Converts a list of arrays of ones and zeros into a single array of unsigned ints.

    Parameters
    ----------
    arrays : list
        List of numpy arrays consisting of ones and zeros.
    dtype : data-type
        Type to convert to; the unsigned ints are of this datatype.

    Returns
    -------
    :obj:`numpy:numpy.ndarray`
        Numpy array with data type `dtype`.
    """
    n = {np.uint8: 8, np.uint16: 16, np.uint32: 32}
    if np.array_equal(arrays[0], 0):
        y = np.zeros(
            max([len(arr) if np.iterable(arr) else 1 for arr in arrays]), dtype=dtype
        )
    else:
        y = np.array(arrays[0], dtype=dtype)
    for i in range(1, n[dtype]):
        if np.iterable(arrays[i]):
            y |= arrays[i] << i
    return y


@contextlib.contextmanager
def suppress_mild_warnings(state=True):
    """A context manager which modifies compiler.suppress_mild_warnings

    Allows the user to suppress (or show) mild warnings for specific lines. Useful when
    you want to hide/show all warnings from specific lines.

    Parameters
    ----------
    state : bool, optional
        The new state for ``compiler.suppress_mild_warnings``. Defaults to ``True``.
    """
    previous_warning_setting = compiler.suppress_mild_warnings
    compiler.suppress_mild_warnings = state
    try:
        yield
    finally:
        compiler.suppress_mild_warnings = previous_warning_setting


@contextlib.contextmanager
def suppress_all_warnings(state=True):
    """A context manager which modifies compiler.suppress_all_warnings

    Allows the user to suppress (or show) all warnings for specific lines. Useful when
    you want to hide/show all warnings from specific lines.

    Parameters
    ----------
    state : bool, optional
        The new state for ``compiler.suppress_all_warnings``. Defaults to ``True``.
    """
    previous_warning_setting = compiler.suppress_all_warnings
    compiler.suppress_all_warnings = state
    try:
        yield
    finally:
        compiler.suppress_all_warnings = previous_warning_setting


def no_warnings(state=True):
    """Deprecated: use ``suppress_all_warnings``."""
    warnings.warn(
        "no_warnings will be removed from labscript; use suppress_all_warnings.",
        FutureWarning,
        stacklevel=2,
    )
    return suppress_all_warnings(state)


class _Config:
    """Deprecated: labscript's settings are attributes of ``compiler``."""

    def __getattr__(self, name):
        _warn_config()
        return getattr(compiler, name)

    def __setattr__(self, name, value):
        _warn_config()
        setattr(compiler, name, value)


def _warn_config():
    warnings.warn(
        "config will be removed from labscript; use compiler instead.",
        FutureWarning,
        stacklevel=3,
    )


config = _Config()


class LabscriptError(Exception):
    """A *labscript* error.

    This is used to denote an error within the labscript suite itself.
    Is a thin wrapper of :obj:`Exception`.
    """
