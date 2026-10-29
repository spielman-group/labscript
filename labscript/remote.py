#####################################################################
#                                                                   #
# /remote.py                                                        #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the program labscript, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

"""Classes for configuring remote/secondary BLACS and/or device workers"""

from .compiler import compiler
from .labscript import Device, set_passed_properties


class _PrimaryBLACS(Device):
    pass


class _RemoteConnection(Device):
    @set_passed_properties(property_names={})
    def __init__(self, name, parent=None, connection=None):
        if parent is None:
            # define a hidden parent of top level remote connections so that
            # "connection" is stored correctly in the connection table
            if compiler._PrimaryBLACS is None:
                compiler._PrimaryBLACS = _PrimaryBLACS('__PrimaryBLACS', None, None)
            parent = compiler._PrimaryBLACS
        super().__init__(name, parent, connection)


class RemoteBLACS(_RemoteConnection):
    """A computer on which BLACS runs the worker processes of devices.

    Pass it as the `worker` argument of a device. The computer must run the zprocess
    remote server, which ``python -m labscript_utils.remote`` starts. BLACS does not
    support a `RemoteBLACS` as the `gui` argument of a device, or a `RemoteBLACS`
    with a parent.
    """

    def __init__(self, name, host, port=7341, parent=None):
        """Creates a RemoteBLACS.

        Parameters
        ----------
        name : str
            Python variable name to assign this connection to.
        host : str
            Host name or IP address of the computer.
        port : int, optional
            Port of the zprocess remote server on the computer.
        parent : :obj:`RemoteBLACS`, optional
            Remote connection through which this one is reached. If `None`, a hidden
            top-level BLACS is the parent.
        """
        super().__init__(name, parent, f"{host}:{port}")

