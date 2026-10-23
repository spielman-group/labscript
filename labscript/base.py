#####################################################################
#                                                                   #
# /base.py                                                          #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""The labscript base class for all I/O/Device classes"""

import keyword

import numpy as np

import labscript_utils.properties

from .compiler import compiler, _builtins_dict
from .utils import (
    LabscriptError,
    set_passed_properties
)


def _check_name(name, namespace, kind):
    """Raise unless `name` can be put into builtins as the name of a new `kind`."""
    if name in namespace or name in _builtins_dict:
        raise LabscriptError(
            f"{name} is already a name used by Python or labscript. "
            f"Please choose another name for this {kind}."
        )
    if keyword.iskeyword(name):
        raise LabscriptError(
            f"{name} is a reserved Python keyword. "
            f"Please choose another name for this {kind}."
        )
    if not name.isidentifier():
        raise LabscriptError(
            f"{name} is not a valid Python variable name. "
            f"Please choose another name for this {kind}."
        )


class Device:
    """Parent class of all device and input/output channels.

    You never instantiate this class directly, but it provides functionality
    that is available to all subclasses.
    """

    description = 'Generic Device'
    """Brief description of the device."""

    allowed_children = None
    """list: Defines types of devices that are allowed to be children of this device."""

    # Device.__init__ makes the properties, one dict per location:
    _properties = None

    @set_passed_properties(
        property_names = {"device_properties": ["added_properties"]}
    )
    def __init__(
        self,
        name,
        parent_device,
        connection,
        call_parents_add_device=True,
        added_properties={},
        gui=None,
        worker=None,
        start_order=None,
        stop_order=None,
        **kwargs,
    ):
        """Creates a Device.

        Parameters
        ----------
        name : str
            Python variable name to assign this device to.
        parent_device : :obj:`Device`
            Parent of this device.
        connection : str
            Connection on this device that links to parent.
        call_parents_add_device : bool, optional
            Flag to command device to call its parent device's add_device when
            adding a device.
        added_properties : dict, optional
            Saved with the device properties in the shot file.
        gui : :obj:`_RemoteConnection`, optional
            Remote connection that runs the BLACS GUI for this device. If `worker` is
            not given, it is also the worker.
        worker : :obj:`_RemoteConnection`, optional
            Remote connection that runs the worker for this device. Must be `gui`, or
            a child of it (of the primary BLACS if `gui` is not given).
        start_order : int, optional
            Priority when starting, sorted with all devices.
        stop_order : int, optional
            Priority when stopping, sorted with all devices; lowest stops first.
            The default is 0, or -1 for a pseudoclock device.
        **kwargs
            Other options to pass to parent.
        """
        if len(kwargs) != 0:
            raise LabscriptError(
                f"Invalid keyword arguments ({kwargs}) passed to '{name}'."
            )

        if self.allowed_children is None:
            self.allowed_children = [Device]
        self.name = name
        self.parent_device = parent_device
        self.connection = connection
        self.start_order = start_order
        self.stop_order = stop_order
        if start_order is not None and not isinstance(start_order, int):
            raise TypeError(
                f"Error when instantiating {name}. start_order must be an integer, not "
                f"{start_order.__class__.__name__} (the value provided was "
                f"{start_order})."
            )
        if stop_order is not None and not isinstance(stop_order, int):
            raise TypeError(
                f"Error when instantiating {name}. stop_order must be an integer, not "
                f"{stop_order.__class__.__name__} (the value provided was "
                f"{stop_order})."
            )
        self.child_devices = []

        locations = labscript_utils.properties.VALID_PROPERTY_LOCATIONS
        self._properties = {location: {} for location in locations}

        if parent_device and call_parents_add_device:
            # Subclasses overriding __init__ can pass call_parents_add_device=False
            # to run code between Device.__init__ and the parent's add_device, which
            # they must then call themselves.
            parent_device.add_device(self)

        _check_name(name, globals(), self.__class__.__name__)
        # Put self into the global namespace:
        _builtins_dict[name] = self

        compiler.inventory.append(self)

        if gui is not None or worker is not None:
            # remote imports this module, so it can only be imported once loaded
            from .remote import _RemoteConnection
            if gui is not None:
                # if no worker is specified, assume it is the same as the gui
                if worker is None:
                    worker = gui

                if not isinstance(gui, _RemoteConnection):
                    raise LabscriptError(
                        f"The 'gui' argument for {name} must be specified as a "
                        "subclass of _RemoteConnection"
                    )
            else:
                # just remote worker
                gui = compiler._PrimaryBLACS

            if not isinstance(worker, _RemoteConnection):
                raise LabscriptError(
                    f"The 'worker' argument for {name} must be specified as a "
                    "subclass of _RemoteConnection"
                )

            if worker != gui and worker not in gui.get_all_children():
                raise LabscriptError(
                    f"The remote worker ({worker.name}) for {name} must be a child of "
                    f"the specified gui ({gui.name}). Available gui children are: "
                    f"{gui.get_all_children()}"
                )

            self.set_property("gui", gui.name, "connection_table_properties")
            self.set_property("worker", worker.name, "connection_table_properties")

    def __repr__(self):
        return f"{self.name} ({self.__class__.__name__})"

    def set_property(self, name, value, location=None, overwrite=False):
        """Method to set a property for this device.

        Property will be stored in the connection table and used
        during connection table comparisons.

        Value must satisfy `eval(repr(value)) == value`.

        Parameters
        ----------
        name : str
            Name to save property value to.
        value
            Value to set property to.
        location : str, optional
            Specify a location to save property to, such as `'device_properties'` or
            `'connection_table_properties'`.
        overwrite : bool, optional
            If `True`, allow overwriting a property already set.

        Raises
        ------
        LabscriptError
            If `'location'` is not valid or trying to overwrite an existing property
            with `'overwrite'=False`.
        """
        valid_locations = labscript_utils.properties.VALID_PROPERTY_LOCATIONS
        if location is None or location not in valid_locations:
            raise LabscriptError(
                f"Device {self.name} requests invalid property assignment {location} "
                f"for property {name}"
            )

        if self._properties is None:
            raise LabscriptError(
                f"{type(self).__name__} sets the property {name} before calling "
                "Device.__init__, which creates the device's properties. Set it after."
            )
        selected_properties = self._properties[location]

        if name in selected_properties and not overwrite:
            raise LabscriptError(
                f"Device {self.name} has had the property {name} set more than once. "
                "This is not allowed unless the overwrite flag is explicitly set"
            )

        selected_properties[name] = value

    def set_properties(self, properties_dict, property_names, overwrite=False):
        """Add one or a bunch of properties packed into properties_dict.

        Parameters
        ----------
        properties_dict : dict
            Dictionary of properties and their values.
        property_names : dict
            Dictionary {key:val, ...} where each val is a list [var1, var2, ...] of
            variables to be pulled from properties_dict and added to the property
            location with name ``key``.
        overwrite : bool, optional
            Toggles overwriting of existing properties.
        """
        for location, names in property_names.items():
            if not isinstance(names, (list, tuple, set)):
                raise TypeError(
                    f"Names for {location} ({names}) must be a list, tuple, or set, "
                    f"not {names.__class__.__name__}."
                )
            properties_for_location = {
                key: val for key, val in properties_dict.items() if key in names
            }
            for (name, value) in properties_for_location.items():
                self.set_property(name, value, overwrite=overwrite, location=location)

    def get_property(self, name, location=None, *args, **kwargs):
        """Method to get a property of this device already set using
        :func:`Device.set_property`.

        If the property is not already set, a default value will be returned
        if specified as the argument after `'name'`, if there is only one argument
        after `'name'` and the argument is either not a keyword argument or is a
        keyword argument with the name `'default'`.

        Parameters
        ----------
        name : str
            Name of property to get.
        location : str, optional
            If not `None`, only search for `name` in `location`.
        default
            The default value. If not provided, an exception is raised if the value
            is not set.

        Returns
        -------
        object
            Property value.

        Raises
        ------
        LabscriptError
            If property not set and default not provided, or default conventions not
            followed.

        Examples
        --------
        Examples of acceptable signatures:

        >>> get_property('example')  # returned if set, or an exception raised
        >>> get_property('example', 7)  # 7 returned if 'example' is not set
        >>> get_property('example', default=7)  # 7 returned if 'example' is not set

        Example signatures that WILL ALWAYS RAISE AN EXCEPTION:

        >>> get_property('example', 7, 8)
        >>> get_property('example', 7, default=9)
        >>> get_property('example', default=7, x=9)
        """
        if len(kwargs) == 1 and 'default' not in kwargs:
            raise LabscriptError(
                f"A call to {self.name}.get_property had a keyword argument that was "
                "not name, location, or default"
            )
        if len(args) + len(kwargs) > 1:
            raise LabscriptError(
                f"A call to {self.name}.get_property has too many arguments and/or "
                "keyword arguments"
            )

        valid_locations = labscript_utils.properties.VALID_PROPERTY_LOCATIONS
        if (location is not None) and (location not in valid_locations):
            raise LabscriptError(
                f"Device {self.name} requests invalid property read location {location}"
            )

        for key, val in self._properties.items():
            if (location is None or key == location) and (name in val):
                return val[name]

        if 'default' in kwargs:
            return kwargs['default']
        elif len(args) == 1:
            return args[0]
        else:
            raise LabscriptError(
                f"The property {name} has not been set for device {self.name}"
            )

    def get_properties(self, location=None):
        """Get all properties in location.

        Parameters
        ----------
        location : str, optional
            Location to get properties from. If `None`, return all properties.

        Returns
        -------
        dict
            Dictionary of properties.
        """
        if location is not None:
            properties = self._properties.get(location, {})
        else:
            properties = {}
            for key, val in self._properties.items():
                properties.update(val)

        return properties

    def add_device(self, device):
        """Adds a child device to this device.

        Parameters
        ----------
        device : :obj:`Device`
            Device to add.

        Raises
        ------
        LabscriptError
            If `device` is not an allowed child of this device.
        """
        if any(
            [isinstance(device, DeviceClass) for DeviceClass in self.allowed_children]
        ):
            self.child_devices.append(device)
        else:
            raise LabscriptError(
                f"Devices of type {device.description} cannot be attached to devices "
                f"of type {self.description}."
            )

    @property
    def pseudoclock_device(self):
        """:obj:`PseudoclockDevice`: Stores the clocking pseudoclock, which may be
        itself."""
        if self.parent_device is None:
            return None
        return self.parent_device.pseudoclock_device

    def quantise_to_pseudoclock(self, times, ticks=False):
        """Quantises `times` to the resolution of the controlling pseudoclock.

        Parameters
        ----------
        times : :obj:`numpy:numpy.ndarray` or list or float
            Time, in seconds, to quantise.
        ticks : bool, optional
            If `True`, return whole clock ticks, as integers, instead of seconds.

        Returns
        -------
        same type as `times`
            Quantised times, or an int for a float `times` in ticks.
        """
        convert_back_to = None
        if not isinstance(times, np.ndarray):
            if isinstance(times, list):
                convert_back_to = list
            else:
                convert_back_to = int if ticks else float
            times = np.array(times)
        resolution = self.pseudoclock_device.clock_resolution
        times = (times / resolution).round()
        times = times.astype(np.int64) if ticks else times * resolution

        if convert_back_to is not None:
            times = convert_back_to(times)

        return times

    @property
    def parent_clock_line(self):
        """:obj:`ClockLine`: Stores the clocking clockline, which may be itself."""
        if self.parent_device is None:
            raise LabscriptError(
                f"There is no ClockLine above {self.name}, which has no parent."
            )
        return self.parent_device.parent_clock_line

    @property
    def t0(self):
        """float: The earliest time output can be commanded from this device at
        the start of the experiment. This is nonzero on secondary pseudoclock
        devices due to triggering delays."""
        parent = self.pseudoclock_device
        if parent is None or parent.is_master_pseudoclock:
            return 0
        else:
            return parent.trigger_times[0] + parent.trigger_delay

    def get_all_outputs(self):
        """Get all children devices that are outputs.

        Recursively calls ``get_all_outputs()`` on each child device. ``Output``'s will
        return a list containing just themselves.

        Returns
        -------
        list
            List of children :obj:`Output`.
        """
        all_outputs = []
        for device in self.child_devices:
            all_outputs.extend(device.get_all_outputs())
        return all_outputs

    def get_all_children(self):
        """Get all children devices for this device.

        Returns
        -------
        list
            List of children :obj:`Device`.
        """
        all_children = []
        for device in self.child_devices:
            all_children.append(device)
            all_children.extend(device.get_all_children())
        return all_children

    def generate_code(self, hdf5_file):
        """Generate hardware instructions for device and children, then save
        to h5 file.

        Will recursively call `generate_code` for all children devices.

        Parameters
        ----------
        hdf5_file : :obj:`h5py:h5py.File`
            Handle to shot file.
        """
        for device in self.child_devices:
            device.generate_code(hdf5_file)

    def init_device_group(self, hdf5_file):
        """Creates the device group in the shot file.

        Parameters
        ----------
        hdf5_file : :obj:`h5py:h5py.File`
            File handle to create the group in.

        Returns
        -------
        :class:`h5py:h5py.Group`
            Created group handle.
        """
        group = hdf5_file['/devices'].create_group(self.name)
        return group
