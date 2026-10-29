#####################################################################
#                                                                   #
# /labscript.py                                                     #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Everything else, including `start()`, `stop()` and `wait()`. It also imports the
classes scripts use, so that `from labscript import *` provides them."""

import builtins
import os
import sys
import subprocess
import keyword
import threading
from functools import lru_cache
import numpy as np

import labscript_utils.h5_lock, h5py
import labscript_utils.properties
from labscript_utils.filewatcher import FileWatcher

from labscript_utils import dedent
from labscript_utils.properties import set_attributes

import labscript.functions as functions
from labscript_utils.unitconversions import *

# The classes scripts use, provided through `from labscript import *`:
from .base import Device, _check_name
from .compiler import compiler, _builtins_dict
from .constants import *
from .core import (
    ClockLine,
    IntermediateDevice,
    Pseudoclock,
    PseudoclockDevice,
    TriggerableDevice,
)
from .inputs import AnalogIn
from .outputs import (
    Output,
    AnalogOut,
    AnalogQuantity,
    DDS,
    DDSQuantity,
    DigitalOut,
    DigitalQuantity,
    Shutter,
    StaticDDS,
    StaticAnalogOut,
    StaticAnalogQuantity,
    StaticDigitalOut,
    StaticDigitalQuantity,
    Trigger,
)
from .utils import (
    LabscriptError,
    bitfield,
    config,
    fastflatten,
    max_or_zero,
    no_warnings,
    renamed_keyword,
    set_passed_properties,
    suppress_all_warnings,
    suppress_mild_warnings,
)

# Keeps subprocesses from launching with a visible command window.
if os.name == 'nt':
    startupinfo = subprocess.STARTUPINFO()
    # 1 is subprocess.STARTF_USESHOWWINDOW.
    startupinfo.dwFlags |= 1
else:
    startupinfo = None


class WaitMonitor(Trigger):

    @set_passed_properties(property_names={})
    def __init__(
        self,
        name,
        parent_device,
        connection,
        acquisition_device,
        acquisition_connection,
        timeout_device=None,
        timeout_connection=None,
        timeout_trigger_type='rising',
        **kwargs
    ):
        """Create a wait monitor.

        This is a device or devices, one of which:

        a) outputs pulses every time the master pseudoclock begins running (either at
           the start of the shot or after a wait

        b) measures the time in between those pulses in order to determine how long the
           experiment was paused for during waits

        c) optionally, produces pulses in software time that can be used to retrigger
           the master pseudoclock if a wait lasts longer than its specified timeout

        Parameters
        ----------
        name : str
            python variable to assign this wait monitor to.
        parent_device : :obj:`Device`
            The device with buffered digital outputs that should be used to produce
            the wait monitor pulses. This device must be one which is clocked by
            the master pseudoclock.
        connection : str
            The name of the output connection of parent_device that should be used
            to produce the pulses.
        acquisition_device : :obj:`Device`
            The device which is to receive those pulses as input, and that will
            measure how long between them. This does not need to be the same device
            as the wait monitor output device (corresponding to `parent_device` and
            `connection`). At time of writing, the only devices in labscript that
            can be a wait monitor acquisition device are NI DAQmx devices that have
            counter inputs.
        acquisition_connection : str
            The name of the input connection on `acquisition_device` that is to read
            the wait monitor pulses. The user must manually connect the output
            device (`parent_device`/`connection`) to this input with a cable, in
            order that the pulses can be read by the device. On NI DAQmx devices,
            the acquisition_connection should be the name of the counter to be used
            such as 'Ctr0'. The physical connection should be made to the input
            terminal corresponding to the gate of that counter.
        timeout_device : :obj:`Device`, optional
            The device that should be used to produce pulses in software time if a
            wait lasts longer than its prescribed timeout. These pulses can be
            connected to the trigger input of the master pseudoclock, via a digital
            logic to 'AND' it with other trigger sources, in order to resume the
            master pseudoclock upon a wait timing out. To produce these pulses
            during a shot requires cooperation between the acquisition device and
            the timeout device code, and at present this means only NI DAQmx devices
            can be used as the timeout device (though it need not be the same device
            as the acquisition device). If not set, timeout pulses will not be
            produced and the user must manually resume the master pseudoclock via
            other means, or abort a shot if the intended resumption mechanism fails.
        timeout_connection : str, optional
            Which connection on the timeout device should be used to produce timeout
            pulses. Since only NI DAQmx devices are supported at the moment, this
            must be a digital output on a port on the NI DAQmx device that is not
            being used. Most NI DAQmx devices have both buffered and unbuffered
            ports, so typically one would use one line of one of the unbuffered
            ports for the timeout output.
        timeout_trigger_type : str, optional
            The edge type to be used for the timeout signal, either `'rising'` or
            `'falling'`. Default `'rising'`.
        **kwargs
            Keyword arguments passed to :func:`Trigger.__init__`.

        Raises
        ------
        LabscriptError
            If a wait monitor already exists, if `parent_device` is not clocked by
            the master pseudoclock, or if only one of `timeout_device` and
            `timeout_connection` is given.
        """
        if compiler.wait_monitor is not None:
            raise LabscriptError(
                "Cannot instantiate a second WaitMonitor: "
                "there can be only be one in the experiment"
            )
        compiler.wait_monitor = self
        super().__init__(name, parent_device, connection, **kwargs)
        if not parent_device.pseudoclock_device.is_master_pseudoclock:
            raise LabscriptError(
                'The output device for monitoring wait durations must be clocked '
                'by the master pseudoclock device'
            )

        if (timeout_device is not None) != (timeout_connection is not None):
            raise LabscriptError(
                'Must specify both timeout_device and timeout_connection, or neither'
            )
        self.acquisition_device = acquisition_device
        self.acquisition_connection = acquisition_connection
        self.timeout_device = timeout_device
        self.timeout_connection = timeout_connection
        self.timeout_trigger_type = timeout_trigger_type


class _InternalWaitMonitorDevice:
    """A link in the chain that gives a pseudoclock device's own wait monitor a
    parent; it takes one child of its allowed type, and generates no code."""

    def add_device(self, device):
        if self.child_devices or not isinstance(device, tuple(self.allowed_children)):
            raise LabscriptError(
                f"{device.name} cannot be attached to {self.name}, which "
                f"{self.pseudoclock_device.name} uses internally for its wait monitor."
            )
        super().add_device(device)

    def generate_code(self, hdf5_file):
        pass


class _InternalWaitMonitorOutputs(_InternalWaitMonitorDevice, IntermediateDevice):
    allowed_children = [WaitMonitor]


class _InternalWaitMonitorClockLine(_InternalWaitMonitorDevice, ClockLine):
    allowed_children = [_InternalWaitMonitorOutputs]


class _InternalWaitMonitorPseudoclock(_InternalWaitMonitorDevice, Pseudoclock):
    allowed_children = [_InternalWaitMonitorClockLine]


def internal_wait_monitor_outputs(pseudoclock_device):
    """Return a new device to give `WaitMonitor` as its parent, acquisition and
    timeout device, for a pseudoclock device that times its own waits.

    It hangs from a pseudoclock and clock line of its own; none generates code.
    """
    name = pseudoclock_device.name
    pseudoclock = _InternalWaitMonitorPseudoclock(
        f'{name}__dummy_wait_pseudoclock', pseudoclock_device, '_'
    )
    clock_line = _InternalWaitMonitorClockLine(
        f'{name}__dummy_wait_clock_line', pseudoclock, '_'
    )
    return _InternalWaitMonitorOutputs(
        f'{name}_internal_wait_monitor_outputs', clock_line
    )


def save_time_markers(hdf5_file):
    """Save shot time markers to the shot file.

    Parameters
    ----------
    hdf5_file : :obj:`h5py:h5py.File`
        Handle to file to save to.
    """
    time_markers = compiler.time_markers
    dtypes = [('label', 'S256'), ('time', float), ('color', '(1,3)int')]
    data_array = np.zeros(len(time_markers), dtype=dtypes)
    for i, t in enumerate(time_markers):
        data_array[i] = time_markers[t]["label"], t, time_markers[t]["color"]
    hdf5_file.create_dataset('time_markers', data=data_array)


def generate_connection_table(hdf5_file):
    """Generate the connection table for the compiled shot.

    Parameters
    ----------
    hdf5_file : :obj:`h5py:h5py.File`
        Handle to file to save to.
    """
    connection_table = []

    for device in compiler.inventory:
        unit_conversion_parameters = device._properties['unit_conversion_parameters']
        serialised_unit_conversion_parameters = labscript_utils.properties.serialise(
            unit_conversion_parameters
        )

        properties = device._properties["connection_table_properties"]
        serialised_properties = labscript_utils.properties.serialise(properties)

        if hasattr(device, "BLACS_connection"):
            # Make sure it is a string!
            BLACS_connection = str(device.BLACS_connection)
        else:
            BLACS_connection = ""

            # A device without a BLACS tab cannot have a remote GUI or worker.
            if 'worker' in properties or 'gui' in properties:
                raise LabscriptError(
                    'You cannot specify a remote GUI or worker for a device '
                    f'({device.name}) that does not have a tab in BLACS'
                )

        if getattr(device, 'unit_conversion_class', None) is not None:
            c = device.unit_conversion_class
            unit_conversion_class_repr = f"{c.__module__}.{c.__name__}"
        else:
            unit_conversion_class_repr = repr(None)

        connection_table.append(
            (
                device.name,
                device.__class__.__name__,
                device.parent_device.name if device.parent_device else str(None),
                str(device.connection if device.parent_device else str(None)),
                unit_conversion_class_repr,
                serialised_unit_conversion_parameters,
                BLACS_connection,
                serialised_properties,
            )
        )

    connection_table.sort()
    vlenstring = h5py.special_dtype(vlen=str)
    connection_table_dtypes = [
        ('name', "S256"),
        ('class', vlenstring),
        ('parent', vlenstring),
        ('parent port', vlenstring),
        ('unit conversion class', vlenstring),
        ('unit conversion params', vlenstring),
        ('BLACS_connection', vlenstring),
        ('properties', vlenstring),
    ]
    connection_table_array = np.empty(
        len(connection_table), dtype=connection_table_dtypes
    )
    for i, row in enumerate(connection_table):
        connection_table_array[i] = row
    dataset = hdf5_file.create_dataset(
        'connection table',
        compression=compiler.compression,
        data=connection_table_array,
        maxshape=(None,),
    )

    if compiler.master_pseudoclock is None:
        master_pseudoclock_name = 'None'
    else:
        master_pseudoclock_name = compiler.master_pseudoclock.name
    dataset.attrs['master_pseudoclock'] = master_pseudoclock_name


# Caches vcs command results, keyed by the paths of files saved by
# save_labscripts(). The FileWatcher callback replaces an outdated entry.
_vcs_cache = {}
_vcs_cache_rlock = threading.RLock()


def _file_watcher_callback(name, info, event):
    with _vcs_cache_rlock:
        _vcs_cache[name] = _run_vcs_commands(name)

_file_watcher = FileWatcher(_file_watcher_callback)

# Absolute paths of imported modules' files, by the module's __file__ attribute if that
# is an absolute path:
_module_file_abspaths = {}


@lru_cache(None)
def _have_vcs(vcs):
    try:
        subprocess.check_output([vcs, '--version'])
        return True
    except FileNotFoundError:
        msg = f"""Warning: Cannot run {vcs} commands, {vcs} info for labscriptlib files
        will not be saved. You can disable this warning by setting
        [labscript]/save_{vcs}_info = False in labconfig."""
        sys.stderr.write(dedent(msg) + '\n')
        return False


def _run_vcs_commands(path):
    """Run some VCS commands on a file and return their output.

    The function is used to gather up version control system information so that
    it can be stored in the hdf5 files of shots. This is for convenience and
    complements the full copy of the file already included in the shot file.

    Whether hg and git commands are run is controlled by the `save_hg_info`
    and `save_git_info` options in the `[labscript]` section of the labconfig.

    Parameters
    ----------
    path : str
        The path with file name and extension of the file on which the commands
        will be run. The working directory will be set to the directory
        containing the specified file.

    Returns
    -------
    list of (tuple, str, str)
        A list of tuples, each containing information related to one vcs command
        of the form (command, info, err). The first entry in that tuple is itself
        a tuple of strings which was passed to subprocess.Popen() in order to run
        the command. Then info is a string that contains the text printed to
        stdout by that command, and err contains the text printed to stderr by the
        command.
    """
    module_directory, module_filename = os.path.split(path)
    vcs_commands = []
    if compiler.save_hg_info and _have_vcs('hg'):
        hg_commands = [
            ['log', '--limit', '1'],
            ['status'],
            ['diff'],
        ]
        for command in hg_commands:
            command = tuple(['hg'] + command + [module_filename])
            vcs_commands.append((command, module_directory))
    if compiler.save_git_info and _have_vcs('git'):
        git_commands = [
            ['branch', '--show-current'],
            ['describe', '--tags', '--always', 'HEAD'],
            ['rev-parse', 'HEAD'],
            ['diff', 'HEAD', module_filename],
        ]
        for command in git_commands:
            command = tuple(['git'] + command)
            vcs_commands.append((command, module_directory))

    # Start every command before waiting on any, so they run concurrently.
    process_list = []
    for command, module_directory in vcs_commands:
        process = subprocess.Popen(
            command,
            cwd=module_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
        )
        process_list.append((command, process))

    results = []
    for command, process in process_list:
        info, err = process.communicate()
        info = info.decode('utf-8')
        err = err.decode('utf-8')
        results.append((command, info, err))
    return results


def save_labscripts(hdf5_file):
    """Write the script files for the compiled shot to the shot file.

    If the labconfig `save_hg_info` or `save_git_info` options are `True`, also
    saves hg or git output for each labscriptlib module as attributes.

    Parameters
    ----------
    hdf5_file : :obj:`h5py:h5py.File`
        Handle to file to save to.
    """
    if compiler.labscript_file is not None:
        with open(compiler.labscript_file) as f:
            script_text = f.read()
    else:
        script_text = ''
    script = hdf5_file.create_dataset('script', data=script_text)
    script.attrs['name'] = (
        os.path.basename(compiler.labscript_file).encode()
        if compiler.labscript_file is not None
        else ''
    )
    script.attrs['path'] = (
        os.path.dirname(compiler.labscript_file).encode()
        if compiler.labscript_file is not None
        else sys.path[0]
    )
    try:
        import labscriptlib
    except ImportError:
        return
    prefix = os.path.dirname(labscriptlib.__file__)
    for module in list(sys.modules.values()):
        module_file = getattr(module, '__file__', None)
        if module_file is not None:
            path = _module_file_abspaths.get(module_file)
            if path is None:
                path = os.path.abspath(module_file)
                if os.path.isabs(module_file):
                    _module_file_abspaths[module_file] = path
            if path.startswith(prefix) and path.endswith(('.pyc', '.py')):
                if 'signature_bootstrap.py' in path or 'shibokensupport' in path:
                    # PySide6 internals
                    continue
                path = path.replace('.pyc', '.py')
                save_path = 'labscriptlib/' + path.replace(prefix, '').replace(
                    '\\', '/'
                ).replace('//', '/')
                if save_path in hdf5_file:
                    # A module can appear twice, e.g. __init__.py when a whole
                    # package is imported with `from labscriptlib.stages import *`.
                    continue
                with open(path) as f:
                    hdf5_file.create_dataset(save_path, data=f.read())
                with _vcs_cache_rlock:
                    if path not in _vcs_cache:
                        # Add file to watch list and create its entry in the cache.
                        _file_watcher.add_file(path)
                        _file_watcher_callback(path, None, None)
                    for command, info, err in _vcs_cache[path]:
                        attribute_str = command[0] + ' ' + command[1]
                        hdf5_file[save_path].attrs[attribute_str] = info + '\n' + err


def write_device_properties(hdf5_file):
    """Write device_properties for each device in the compiled shot to the shot file.

    Parameters
    ----------
    hdf5_file : :obj:`h5py:h5py.File`
        Handle to file to save to.
    """
    for device in compiler.inventory:
        device_properties = device._properties["device_properties"]

        # start_order and stop_order become device_properties only if the device
        # has a BLACS_connection, and are an error otherwise. The default is zero,
        # but pseudoclock devices stop first, so BLACS stops no other device while
        # one is still running its program.
        for attr_name in ['start_order', 'stop_order']:
            attr = getattr(device, attr_name)
            if hasattr(device, 'BLACS_connection'):
                if attr is None:
                    pseudoclock = isinstance(device, PseudoclockDevice)
                    attr = -1 if attr_name == 'stop_order' and pseudoclock else 0
                device_properties[attr_name] = attr
            elif attr is not None:
                msg = (
                    f'cannot set {attr_name} on device {device.name}, which does '
                    'not have a BLACS_connection attribute and thus is not started '
                    'and stopped directly by BLACS.'
                )
                raise TypeError(msg)

        # Every device has an empty 'added_properties' dict for data passed in from
        # experiment scripts; it alone does not warrant a group.
        if device_properties and device_properties != {'added_properties': {}}:
            if device.name not in hdf5_file['devices']:
                hdf5_file['/devices'].create_group(device.name)
            labscript_utils.properties.set_device_properties(
                hdf5_file, device.name, device_properties
            )


def generate_wait_table(hdf5_file):
    """Generate the wait table for the shot and save it to the shot file.

    Parameters
    ----------
    hdf5_file : :obj:`h5py:h5py.File`
        Handle to file to save to.
    """
    dtypes = [('label', 'S256'), ('time', float), ('timeout', float)]
    data_array = np.zeros(len(compiler.wait_table), dtype=dtypes)
    for i, t in enumerate(sorted(compiler.wait_table)):
        label, timeout = compiler.wait_table[t]
        data_array[i] = label, t, timeout
    dataset = hdf5_file.create_dataset('waits', data=data_array)
    if compiler.wait_monitor is not None:
        acquisition_device = compiler.wait_monitor.acquisition_device.name
        acquisition_connection = compiler.wait_monitor.acquisition_connection
        if compiler.wait_monitor.timeout_device is None:
            timeout_device = ''
        else:
            timeout_device = compiler.wait_monitor.timeout_device.name
        if compiler.wait_monitor.timeout_connection is None:
            timeout_connection = ''
        else:
            timeout_connection = compiler.wait_monitor.timeout_connection
        timeout_trigger_type = compiler.wait_monitor.timeout_trigger_type
    else:
        (
            acquisition_device,
            acquisition_connection,
            timeout_device,
            timeout_connection,
            timeout_trigger_type,
        ) = '', '', '', '', ''
    dataset.attrs['wait_monitor_acquisition_device'] = acquisition_device
    dataset.attrs['wait_monitor_acquisition_connection'] = acquisition_connection
    dataset.attrs['wait_monitor_timeout_device'] = timeout_device
    dataset.attrs['wait_monitor_timeout_connection'] = timeout_connection
    dataset.attrs['wait_monitor_timeout_trigger_type'] = timeout_trigger_type


def generate_code():
    """Compile a shot and save it to the shot file."""
    if compiler.hdf5_filename is None:
        raise LabscriptError(
            'hdf5 file for compilation not set. Please call labscript_init'
        )
    elif not os.path.exists(compiler.hdf5_filename):
        with h5py.File(compiler.hdf5_filename, 'w') as hdf5_file:
            hdf5_file.create_group('globals')
    with h5py.File(compiler.hdf5_filename, 'a') as hdf5_file:
        try:
            hdf5_file.create_group('devices')
            hdf5_file.create_group('calibrations')
        except ValueError:
            # The groups already exist, so this is not a fresh shot file.
            raise ValueError(
                f'The HDF5 file {compiler.hdf5_filename} already contains '
                'compilation data '
                '(possibly partial if due to failed compilation). '
                'Please use a fresh shot file. '
                'If this one was autogenerated by a previous compilation, '
                'and you wish to have a new one autogenerated, '
                'simply delete it and run again, or add the \'-f\' command line '
                'argument to automatically overwrite.'
            )
        for device in compiler.inventory:
            if device.parent_device is None:
                device.generate_code(hdf5_file)

        save_time_markers(hdf5_file)
        generate_connection_table(hdf5_file)
        write_device_properties(hdf5_file)
        generate_wait_table(hdf5_file)
        save_labscripts(hdf5_file)

        # Save shot properties:
        group = hdf5_file.create_group('shot_properties')
        set_attributes(group, compiler.shot_properties)


def trigger_all_pseudoclocks(t='initial'):
    """Trigger all pseudoclocks at time `t` and return the delay before devices can
    next take instructions."""
    # Must wait this long before providing a trigger, in case child clocks aren't
    # ready yet, but not at the start of the experiment.
    wait_delay = compiler.wait_delay
    if type(t) in [str, bytes] and t == 'initial':
        wait_delay = 0
    for pseudoclock in compiler.all_pseudoclocks:
        pseudoclock.trigger(t, compiler.trigger_duration)
    # A secondary takes instructions once its trigger delay has passed and its
    # slowest clock line can tick again after the tick it makes at the trigger. Whole
    # ticks are counted past that interval, with room for the triggering clock's
    # rounding of the trigger and this clock's rounding of the command.
    max_delay_time = 0
    for pseudoclock in compiler.all_pseudoclocks:
        if pseudoclock.is_master_pseudoclock:
            continue
        interval = max(
            [
                1.0 / clockline.clock_limit
                for child in pseudoclock.child_devices
                for clockline in child.child_devices
            ],
            default=0,
        )
        trigger_resolution = compiler.master_pseudoclock.clock_resolution
        ticks = int((interval + trigger_resolution) / pseudoclock.clock_resolution) + 2
        max_delay_time = max(
            max_delay_time,
            pseudoclock.trigger_delay + ticks * pseudoclock.clock_resolution,
        )
    # The trigger duration and the clock limit of the master clock can also limit
    # when devices can next be given instructions: take the longest 1.0/clock_limit
    # of every clockline on every pseudoclock of the master pseudoclock.
    master_pseudoclock_delay = max(
        1.0 / compiler.master_pseudoclock.clock_limit,
        max(
            [
                1.0 / clockline.clock_limit
                for pseudoclock in compiler.master_pseudoclock.child_devices
                for clockline in pseudoclock.child_devices
            ],
            default=0,
        ),
    )
    max_delay = max(
        compiler.trigger_duration + master_pseudoclock_delay, max_delay_time
    )
    return max_delay + wait_delay


def wait(label, t, timeout=5):
    """Command pseudoclocks to pause until resumed by an external trigger, or a
    timeout is reached.

    Parameters
    ----------
    label : str
        Unique name for wait.
    t : float
        Time, in seconds, at which experiment should begin the wait.
    timeout : float, optional
        Maximum length of the wait, in seconds. After this time, the pseudoclocks
        are automatically re-triggered.

    Returns
    -------
    float
        Time required for all pseudoclocks to resume execution once wait has
        completed.

    Raises
    ------
    LabscriptError
        If `label` is empty, or a wait already exists at `t` or with this `label`.
    """
    if not str(label):
        raise LabscriptError('Wait must have a name')
    max_delay = trigger_all_pseudoclocks(t)
    if t in compiler.wait_table:
        raise LabscriptError(f'There is already a wait at t={t}')
    if any(label == existing for existing, _ in compiler.wait_table.values()):
        raise LabscriptError(f'There is already a wait named {label}')
    compiler.wait_table[t] = str(label), float(timeout)
    return max_delay


def add_time_marker(t, label, color=None, verbose=False):
    """Add a marker for the specified time.

    These markers are saved in the HDF5 file. This allows one to label that time
    with a string label, and a color that applications may use to represent this
    part of the experiment. Runviewer displays these markers and allows one to
    manipulate the time axis based on them, and BLACS' progress bar plugin
    displays the name and colour of the most recent marker as the shot is running.

    Parameters
    ----------
    t : float
        Time of the marker, in seconds.
    label : str
        Label for the marker.
    color : tuple of int or str, optional
        The color may be specified as an RGB tuple, or a string of the color name
        such as 'red', or a string of its hex value such as '#ff8800'.
    verbose : bool, optional
        If `True`, also print the label and time, which can be useful to view
        during shot compilation.

    Raises
    ------
    ValueError
        If `color` is a string PIL cannot parse, or an RGB tuple with a value
        outside 0 to 255.
    """
    if isinstance(color, (str, bytes)):
        import PIL.ImageColor
        color = PIL.ImageColor.getrgb(color)
    if color is None:
        color = (-1, -1, -1)
    elif not all(0 <= n <= 255 for n in color):
        raise ValueError(f"Invalid RGB tuple {color}")
    if verbose:
        functions.print_time(t, label)
    compiler.time_markers[t] = {"label": label, "color": color}


def start():
    """Indicate the end of the connection table and the start of the experiment
    logic.

    Returns
    -------
    float
        Time required for all pseudoclocks to start execution.

    Raises
    ------
    LabscriptError
        If there is more than one master pseudoclock, or no toplevel devices.
    """
    compiler.start_called = True
    # Get and save some timing info about the pseudoclocks:
    pseudoclocks = [
        device for device in compiler.inventory if isinstance(device, PseudoclockDevice)
    ]
    compiler.all_pseudoclocks = pseudoclocks
    toplevel_devices = [
        device for device in compiler.inventory if device.parent_device is None
    ]
    master_pseudoclocks = [
        pseudoclock for pseudoclock in pseudoclocks if pseudoclock.is_master_pseudoclock
    ]
    if len(master_pseudoclocks) > 1:
        raise LabscriptError('Cannot have more than one master pseudoclock')
    if not toplevel_devices:
        raise LabscriptError('No toplevel devices and no master pseudoclock found')
    elif pseudoclocks:
        (master_pseudoclock,) = master_pseudoclocks
        compiler.master_pseudoclock = master_pseudoclock
        # Which pseudoclock requires the longest pulse in order to trigger it?
        compiler.trigger_duration = max(
            [
                pseudoclock.trigger_minimum_duration
                for pseudoclock in pseudoclocks
                if not pseudoclock.is_master_pseudoclock
            ],
            default=0,
        )

        trigger_clock_limits = [
            pseudoclock.trigger_device.clock_limit
            for pseudoclock in pseudoclocks
            if not pseudoclock.is_master_pseudoclock
        ]
        if len(trigger_clock_limits) > 0:
            min_clock_limit = min(trigger_clock_limits)
            min_clock_limit = min([min_clock_limit, master_pseudoclock.clock_limit])
        else:
            min_clock_limit = master_pseudoclock.clock_limit

        # Do not tick faster than the devices attached to the master pseudoclock can
        # handle.
        clockline_limits = [
            clockline.clock_limit
            for pseudoclock in master_pseudoclock.child_devices
            for clockline in pseudoclock.child_devices
        ]
        min_clock_limit = min(min_clock_limit, min(clockline_limits))

        if compiler.wait_monitor is not None:
            wait_monitor_minimum_pulse_width = getattr(
                compiler.wait_monitor.acquisition_device,
                'wait_monitor_minimum_pulse_width',
                0,
            )
            compiler.trigger_duration = max(
                compiler.trigger_duration, wait_monitor_minimum_pulse_width
            )

        # Provide this, or the minimum possible pulse, whichever is longer:
        compiler.trigger_duration = (
            max(2.0 / min_clock_limit, compiler.trigger_duration)
            + 2 * master_pseudoclock.clock_resolution
        )
        # Must wait this long before providing a trigger, in case child clocks aren't
        # ready yet:
        compiler.wait_delay = max(
            [
                pseudoclock.wait_delay
                for pseudoclock in pseudoclocks
                if not pseudoclock.is_master_pseudoclock
            ],
            default=0,
        )

        # Have the master clock trigger pseudoclocks at t = 0:
        max_delay = trigger_all_pseudoclocks()
    else:
        # No pseudoclocks, only other toplevel devices:
        compiler.master_pseudoclock = None
        compiler.trigger_duration = 0
        compiler.wait_delay = 0
        max_delay = 0
    return max_delay


def stop(t, target_cycle_time=None, cycle_time_delay_after_programming=False):
    """Indicate the end of an experiment at the given time, and initiate compilation
    of instructions, saving them to the HDF5 file. Configures some shot options.

    Parameters
    ----------
    t : float
        The end time of the experiment.
    target_cycle_time : float, optional
        How long, in seconds, after the previous shot was started, should this shot
        be started by BLACS. This allows one to run shots at a constant rate even if
        they are of different durations. If `None`, BLACS will run the next shot
        immediately after the previous shot completes. Otherwise, BLACS will delay
        starting this shot until the cycle time has elapsed. This is a request only,
        and may not be met if running/programming/saving data from a shot takes long
        enough that it cannot be met. This functionality requires the BLACS
        `cycle_time` plugin to be enabled in labconfig. Its accuracy is also limited
        by software timing, requirements of exact cycle times beyond software timing
        should be instead done using hardware triggers to Pseudoclocks. Default
        `None`.
    cycle_time_delay_after_programming : bool, optional
        Whether the BLACS cycle_time plugin should insert the required delay for the
        target cycle time *after* programming devices, as opposed to before
        programming them. This is more precise, but may cause some devices to output
        their first instruction for longer than desired, since some devices begin
        outputting their first instruction as soon as they are programmed rather
        than when they receive their first clock tick. If not set, the *average*
        cycle time will still be just as close to as requested (so long as there is
        adequate time available), however the time interval between the same part of
        the experiment from one shot to the next will not be as precise due to
        variations in programming time. Default `False`.

    Raises
    ------
    LabscriptError
        If `t` is zero.
    """
    if t == 0:
        raise LabscriptError(
            'Stop time cannot be t=0. Please make your run a finite duration'
        )
    for device in compiler.inventory:
        if isinstance(device, PseudoclockDevice):
            device.stop_time = t
    if target_cycle_time is not None:
        # Ensure we have a valid type for this
        target_cycle_time = float(target_cycle_time)
    compiler.shot_properties['target_cycle_time'] = target_cycle_time
    compiler.shot_properties['cycle_time_delay_after_programming'] = (
        cycle_time_delay_after_programming
    )
    generate_code()


def load_globals(hdf5_filename):
    """Load the globals of a shot file into the builtins used by the experiment
    script."""
    import labscript_utils.shot_utils
    params = labscript_utils.shot_utils.get_shot_globals(hdf5_filename)
    for name, value in params.items():
        _check_name(name, globals(), f'global in {hdf5_filename}')
        _builtins_dict[name] = value


def labscript_init(hdf5_filename, labscript_file=None, new=False, overwrite=False):
    """Initialise labscript and prepare for compilation.

    Parameters
    ----------
    hdf5_filename : str
        Path to shot file to compile.
    labscript_file : str, optional
        Path to the labscript file. If `None`, the file of the `__main__` module.
    new : bool, optional
        If `True`, ensure a new shot file is created.
    overwrite : bool, optional
        If `True`, overwrite existing shot file, if it exists.

    Raises
    ------
    LabscriptError
        If `new` is `False` and `hdf5_filename` does not exist.
    """
    # Save the builtins for restoration in labscript_cleanup.
    compiler.save_builtins_state()

    if new:
        # File creation is deferred to generate_code(), so that merely importing
        # labscript does not litter the filesystem with h5 files. An existing file
        # is deleted if overwrite is true, to get a fresh one.
        if os.path.exists(hdf5_filename) and overwrite:
            os.unlink(hdf5_filename)
    elif not os.path.exists(hdf5_filename):
        raise LabscriptError(f'Provided hdf5 filename {hdf5_filename} doesn\'t exist.')
    else:
        load_globals(hdf5_filename)

    compiler.hdf5_filename = hdf5_filename
    if labscript_file is None:
        import __main__
        labscript_file = __main__.__file__
    compiler.labscript_file = os.path.abspath(labscript_file)


def labscript_cleanup():
    """Restore builtins and the labscript module to their state before
    :func:`labscript_init` was called."""
    compiler.reset()
