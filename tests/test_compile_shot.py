"""Compiling shots all the way to a shot file, as runmanager does: what the file
holds, how long the shot runs, and what the compiler refuses."""
import os
import sys
import tempfile
import textwrap
import unittest
from types import ModuleType

import labscript_utils.h5_lock  # must precede h5py, as labscript itself does
import h5py

import labscript


SHOT = textwrap.dedent(
    '''
    from labscript import (
        start, stop, add_time_marker, wait, AnalogOut, DigitalOut, Shutter,
    )
    from labscript_devices.DummyPseudoclock.labscript_devices import (
        DummyPseudoclock,
    )
    from labscript_devices.DummyIntermediateDevice import (
        DummyIntermediateDevice,
    )

    DummyPseudoclock(name='pseudoclock')
    DummyIntermediateDevice(
        name='intermediate_device', parent_device=pseudoclock.clockline
    )
    AnalogOut(
        name='analog_out', parent_device=intermediate_device, connection='ao0'
    )
    DigitalOut(
        name='digital_out',
        parent_device=intermediate_device,
        connection='port0/line0',
    )
    Shutter(
        name='shutter',
        parent_device=intermediate_device,
        connection='port0/line1',
        delay=(0.0, 0.0),
    )

    t = 0
    add_time_marker(t, 'Start')
    start()
    t += 1
    digital_out.go_high(t)
    shutter.open(t)
    t += 1
    wait('a wait', t, timeout=5)
    t += 1
    add_time_marker(t, 'Stop')
    stop(t)
    '''
)


class CompileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.script = os.path.join(self.directory, 'a_shot.py')
        with open(self.script, 'w') as f:
            f.write(SHOT)
        self.run_file = os.path.join(self.directory, 'a_shot.h5')
        # A run file as runmanager makes one: globals and nothing else.
        with h5py.File(self.run_file, 'w') as f:
            f.create_group('globals')

        self.saved_main = sys.modules.get('__main__')
        self.saved_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.saved_cwd)
        if self.saved_main is not None:
            sys.modules['__main__'] = self.saved_main
        try:
            labscript.labscript_cleanup()
        except Exception:
            pass

    def compile_the_shot(self):
        """Compile it the way runmanager's batch compiler does."""
        module = ModuleType('__main__')
        module.__file__ = self.script
        sys.modules['__main__'] = module
        os.chdir(self.directory)
        try:
            labscript.labscript_init(self.run_file, labscript_file=self.script)
            with open(self.script) as f:
                code = compile(f.read(), self.script, 'exec', dont_inherit=True)
            exec(code, module.__dict__)
        finally:
            labscript.labscript_cleanup()

    def test_a_compiled_shot_file_holds_its_markers_and_waits(self):
        self.compile_the_shot()

        with h5py.File(self.run_file, 'r') as f:
            for group in (
                'connection table',
                'devices',
                'script',
                'shot_properties',
                'time_markers',
                'waits',
            ):
                self.assertIn(group, f, f'{group} is written by a full compile')
            # The tables whose dtypes are the risk, read back as strings:
            self.assertEqual(
                [row['label'].decode() for row in f['time_markers'][:]],
                ['Start', 'Stop'],
            )
            self.assertEqual(
                [row['label'].decode() for row in f['waits'][:]], ['a wait']
            )
            self.assertIn(
                b'pseudoclock', [row['name'] for row in f['connection table'][:]]
            )

    def test_the_shot_knows_how_long_it_runs(self):
        # BLACS asks the master pseudoclock's stop_time how long to wait, so a
        # shot that compiles without one runs in no time at all and looks like
        # a shot that never ran.
        import labscript_utils.properties as properties

        self.compile_the_shot()

        with h5py.File(self.run_file, 'r') as f:
            properties_ = properties.get(f, 'pseudoclock', 'device_properties')
        self.assertEqual(properties_['stop_time'], 3)

    def test_an_instruction_inside_a_later_ramp_is_refused(self):
        ramps = textwrap.dedent(
            '''
            analog_out.ramp(t, duration=0.25, initial=0, final=1, samplerate=100)
            analog_out.ramp(t + 0.5, duration=0.25, initial=0, final=1, samplerate=100)
            analog_out.constant(t + 0.6, 0.5)
            '''
        )
        with open(self.script, 'w') as f:
            f.write(SHOT.replace('shutter.open(t)\n', 'shutter.open(t)\n' + ramps))
        with self.assertRaises(labscript.LabscriptError):
            self.compile_the_shot()

    def test_a_secondary_keeps_its_times_on_its_own_ticks(self):
        # 25 ns ticks offset 13 ns from the master's: the start and the ramp share a
        # master tick but not their own, and the ramp's end and the constants share
        # their own, where the last call wins. A ramp at a wait starts at its resume,
        # and the value 5 ns after the wait at t=2 starts at the resume.
        secondary = textwrap.dedent(
            '''
            from labscript import ClockLine, PseudoclockDevice

            class Secondary(DummyPseudoclock):
                clock_limit = 1e9
                trigger_delay = 13e-9

                def __init__(self, name, trigger_device, trigger_connection):
                    PseudoclockDevice.__init__(
                        self, name, trigger_device, trigger_connection
                    )
                    self._pseudoclock = type(pseudoclock.pseudoclock)(
                        name=f'{name}_pseudoclock', pseudoclock_device=self,
                        connection='pseudoclock',
                    )
                    self._clock_line = ClockLine(
                        name=f'{name}_clock_line', pseudoclock=self.pseudoclock,
                        connection='internal',
                    )

            class FastDevice(DummyIntermediateDevice):
                clock_limit = 1e9

            Secondary('secondary', intermediate_device, 'port0/line7')
            FastDevice(name='fast_device', parent_device=secondary.clockline)
            AnalogOut(name='fast_out', parent_device=fast_device, connection='ao0')
            '''
        )
        instructions = textwrap.dedent(
            '''
            fast_out.ramp(26e-9, duration=986e-9, initial=5, final=1, samplerate=1e7)
            fast_out.constant(1024e-9, 6)
            fast_out.constant(1023e-9, 5)
            fast_out.constant(1024e-9, 7)
            wait('b wait', 0.5)
            fast_out.ramp(0.5, duration=1005e-9, initial=1, final=2, samplerate=1e7)
            fast_out.constant(2 + 5e-9, 3)
            '''
        )
        shot = SHOT.replace('\nt = 0\n', secondary + '\nt = 0\n')
        with open(self.script, 'w') as f:
            f.write(shot.replace('start()\n', 'start()\n' + instructions))
        self.compile_the_shot()

        with h5py.File(self.run_file, 'r') as f:
            values = f['devices/fast_device/OUTPUTS']['fast_out']
        self.assertEqual(values[0], 0, 'starts at the default, before the ramp')
        self.assertEqual(
            list(values).count(7), 1, 'kept at the ramp end, until the resume'
        )
        self.assertEqual(values[-1], 3)

    def test_a_time_marker_refuses_an_invalid_colour(self):
        with self.assertRaises(ValueError):
            labscript.add_time_marker(0, 'marker', color=(300, 0, 0))

    def test_a_pseudoclock_refuses_children_beyond_its_limit(self):
        for extra in (
            "ClockLine(name='extra', pseudoclock=pseudoclock.pseudoclock, "
            "connection='flag 1')",
            "type(pseudoclock.pseudoclock)(name='extra', "
            "pseudoclock_device=pseudoclock, connection='clock 2')",
        ):
            with self.subTest(extra=extra):
                with open(self.script, 'w') as f:
                    f.write(
                        'from labscript import ClockLine\n'
                        + SHOT.replace('stop(t)\n', f'{extra}\nstop(t)\n')
                    )
                with self.assertRaises(labscript.LabscriptError):
                    self.compile_the_shot()


if __name__ == '__main__':
    unittest.main()
