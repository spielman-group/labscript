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
    from labscript_devices.DummyIntermediateDevice.labscript_devices import (
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

    def test_pseudoclocks_stop_before_other_devices(self):
        # BLACS stops the lowest stop_order first, and a pseudoclock's worker waits
        # for its program to end, so no device stops while one is still running.
        import labscript_utils.properties as properties

        self.compile_the_shot()

        with h5py.File(self.run_file, 'r') as f:
            pseudoclock, other = (
                properties.get(f, name, 'device_properties')['stop_order']
                for name in ('pseudoclock', 'intermediate_device')
            )
        self.assertLess(pseudoclock, other)

    def test_a_pseudoclock_refuses_clock_lines_beyond_its_limit(self):
        limited = textwrap.dedent(
            '''
            from labscript import ClockLine, Pseudoclock

            class AnyPseudoclocks(DummyPseudoclock):
                allowed_children = [Pseudoclock]
                max_pseudoclocks = None

            AnyPseudoclocks(name='pseudoclock')
            Pseudoclock('limited', pseudoclock, 'limited', max_clock_lines=1)
            ClockLine('first', limited, 'first')
            ClockLine('second', limited, 'second')
            '''
        )
        with open(self.script, 'w') as f:
            f.write(SHOT.replace("DummyPseudoclock(name='pseudoclock')\n", limited))
        with self.assertRaisesRegex(labscript.LabscriptError, 'can drive only 1'):
            self.compile_the_shot()

    def test_a_pseudoclock_device_can_time_its_own_waits(self):
        own_waits = textwrap.dedent(
            '''
            from labscript import Pseudoclock, WaitMonitor, internal_wait_monitor_outputs

            class OwnWaits(DummyPseudoclock):
                allowed_children = [Pseudoclock]
                max_pseudoclocks = None

            OwnWaits(name='pseudoclock')
            outputs = internal_wait_monitor_outputs(pseudoclock)
            WaitMonitor(
                'wait_monitor', outputs, 'internal', outputs, 'internal', outputs,
                'internal',
            )
            '''
        )
        with open(self.script, 'w') as f:
            f.write(SHOT.replace("DummyPseudoclock(name='pseudoclock')\n", own_waits))
        self.compile_the_shot()

    def test_a_slow_device_on_a_secondary_takes_commands_after_start_and_wait(self):
        # The delays start() and wait() return are the earliest a script may
        # command any device, including one on a secondary's slow clock line.
        script = textwrap.dedent(
            '''
            from labscript import start, stop, wait, DigitalOut, DDS
            from labscript_devices.DummyPseudoclock.labscript_devices import (
                DummyPseudoclock,
            )
            from labscript_devices.DummyIntermediateDevice.labscript_devices import (
                DummyIntermediateDevice,
            )
            from labscript_devices.PineBlaster.labscript_devices import PineBlaster
            from labscript_devices.NovaTechDDS9M.labscript_devices import NovaTechDDS9M

            DummyPseudoclock(name='pseudoclock')
            DummyIntermediateDevice(
                name='intermediate_device', parent_device=pseudoclock.clockline
            )
            DigitalOut(
                name='pine_out', parent_device=intermediate_device,
                connection='port0/line0',
            )
            PineBlaster(name='pine', trigger_device=pine_out, trigger_connection='t')
            NovaTechDDS9M(name='novatech', parent_device=pine.clockline, com_port='C')
            DDS(name='dds', parent_device=novatech, connection='dds 0')

            t = start()
            dds.setfreq(t, 10)
            delay = wait('a wait', 1)
            wait('b wait', 2)
            dds.setfreq(1 + delay, 20)
            dds.setfreq(2 + delay, 30)
            stop(3)
            '''
        )
        # Waits called out of time order compile as though called in it:
        swapped = script.replace(
            "delay = wait('a wait', 1)\nwait('b wait', 2)\n",
            "wait('b wait', 2)\ndelay = wait('a wait', 1)\n",
        )
        programs = []
        for order in (script, swapped):
            with h5py.File(self.run_file, 'w') as f:
                f.create_group('globals')
            with open(self.script, 'w') as f:
                f.write(order)
            self.compile_the_shot()
            with h5py.File(self.run_file, 'r') as f:
                programs.append(f['devices/pine/PULSE_PROGRAM'][()].tolist())
        self.assertNotEqual(script, swapped)
        self.assertEqual(programs[0], programs[1])

    def test_a_dds_value_reaches_its_device_in_range_or_is_refused(self):
        dds = textwrap.dedent(
            '''
            from labscript import DDS

            class DDSDevice(DummyIntermediateDevice):
                allowed_children = [DDS]

                def generate_code(self, hdf5_file):
                    for output in self.child_devices:
                        phase, _ = output.quantise_channel(
                            output.phase, 2**14 / 360, period=360
                        )
                        output.quantise_channel(
                            output.frequency, 10, limits=(0, 171e6)
                        )
                        group = self.init_device_group(hdf5_file)
                        group.create_dataset('phase', data=phase)

            DDSDevice(name='dds_device', parent_device=pseudoclock.clockline)
            DDS(name='dds', parent_device=dds_device, connection='dds 0')
            '''
        )
        # A NaN is refused even on a channel the device gives no limits:
        for value, refusal in (
            ('dds.setfreq(1, 200e6)', 'dds_freq has the value 2'),
            ("dds.setphase(1, float('nan'))", 'dds_phase has the value nan, which'),
        ):
            with self.subTest(value=value):
                with h5py.File(self.run_file, 'w') as f:
                    f.create_group('globals')
                with open(self.script, 'w') as f:
                    script = SHOT.replace('t = 0\n', dds + 't = 0\n')
                    f.write(script.replace('start()\n', f'start()\n{value}\n'))
                with self.assertRaisesRegex(labscript.LabscriptError, refusal):
                    self.compile_the_shot()
        # A phase just under a turn, or just below zero, wraps to the device's 0
        # rather than to one past its largest phase word:
        with h5py.File(self.run_file, 'w') as f:
            f.create_group('globals')
        with open(self.script, 'w') as f:
            script = SHOT.replace('t = 0\n', dds + 't = 0\n')
            phases = 'dds.setphase(1, 359.9999)\ndds.setphase(1.5, -1e-6)\n'
            f.write(script.replace('start()\n', 'start()\n' + phases))
        self.compile_the_shot()
        with h5py.File(self.run_file, 'r') as f:
            self.assertEqual(set(f['devices/dds_device/phase'][()]), {0})

    def test_a_digital_output_ramps_and_its_inverse_mirrors_it(self):
        outputs = textwrap.dedent(
            '''
            DigitalOut(name='plain', parent_device=intermediate_device,
                       connection='port0/line2')
            DigitalOut(name='inverse', parent_device=intermediate_device,
                       connection='port0/line3', inverted=True)

            def square(t, duration):
                return (t % 0.02) < 0.01
            '''
        )
        ramps = textwrap.dedent(
            '''
            plain.customramp(0.5, 0.1, square, samplerate=1e3)
            inverse.customramp(0.5, 0.1, square, samplerate=1e3)
            plain.customramp(1.5, 0.1, lambda t, duration: True, samplerate=1e3)
            inverse.customramp(1.5, 0.1, lambda t, duration: True, samplerate=1e3)
            '''
        )
        script = SHOT.replace('t = 0\n', outputs + 't = 0\n')
        with open(self.script, 'w') as f:
            f.write(script.replace('start()\n', 'start()\n' + ramps))
        self.compile_the_shot()
        with h5py.File(self.run_file, 'r') as f:
            values = f['devices/intermediate_device/OUTPUTS'][()]
        plain, inverse = values['plain'], values['inverse']
        self.assertEqual(set(plain), {0, 1})
        # Both hold the default, 0, until the ramp, and are each other's inverse
        # from then on, booleans included:
        both = plain + inverse
        self.assertEqual(list(both), sorted(both))
        self.assertEqual(set(both), {0, 1})

        with h5py.File(self.run_file, 'w') as f:
            f.create_group('globals')
        with open(self.script, 'w') as f:
            f.write(script.replace('start()\n', 'start()\n' + ramps.replace(
                'square, samplerate', 'lambda t, duration: 0.7, samplerate', 1
            )))
        with self.assertRaisesRegex(labscript.LabscriptError, r'\[0, 1\]'):
            self.compile_the_shot()

    def test_the_last_tick_is_long_enough_for_the_slowest_clock_line(self):
        # The tick at stop_time clocks out every clock line's last sample, so a
        # device on a slow line must see a whole period of its own.
        slow = textwrap.dedent(
            '''
            class SlowDevice(DummyIntermediateDevice):
                clock_limit = 1e4

            SlowDevice(name='slow_device', parent_device=pseudoclock.clockline)
            AnalogOut(name='slow_out', parent_device=slow_device, connection='ao0')
            '''
        )
        with open(self.script, 'w') as f:
            f.write(SHOT.replace('t = 0\n', slow + 't = 0\n'))
        self.compile_the_shot()
        with h5py.File(self.run_file, 'r') as f:
            # The last row is the stop instruction:
            last = f['devices/pseudoclock/PULSE_PROGRAM'][-2]
        # 100 us, at least, in 25 ns ticks:
        self.assertGreaterEqual(last['period'], 4000)

    def test_stop_one_interval_after_the_last_instruction_compiles(self):
        # The gap is one minimum update interval, whatever float noise the
        # quantised times carry.
        with open(self.script, 'w') as f:
            f.write(SHOT.replace(
                'stop(t)\n',
                'digital_out.go_low(t)\n'
                'stop(t + 1 / intermediate_device.parent_clock_line.clock_limit)\n',
            ))
        self.compile_the_shot()

    def test_a_static_dds_enabled_with_no_time_is_enabled_from_the_start(self):
        static_dds = textwrap.dedent(
            '''
            from labscript import StaticDDS
            from labscript_devices.NovaTechDDS9M.labscript_devices import NovaTechDDS9M

            NovaTechDDS9M(
                name='novatech', parent_device=pseudoclock.clockline, com_port='C'
            )
            StaticDDS(
                name='static_dds', parent_device=novatech, connection='dds 2',
                digital_gate={
                    'device': intermediate_device, 'connection': 'port0/line5'
                },
            )
            '''
        )
        script = SHOT.replace('t = 0\n', static_dds + 't = 0\n')
        with open(self.script, 'w') as f:
            f.write(script.replace('start()\n', 'start()\nstatic_dds.enable()\n'))
        self.compile_the_shot()
        with h5py.File(self.run_file, 'r') as f:
            gate = f['devices/intermediate_device/OUTPUTS']['static_dds_gate']
        self.assertEqual(gate[0], 1)

    def test_a_device_may_not_take_a_name_from_labscript(self):
        # `from labscript import *` would shadow the device in the script.
        with open(self.script, 'w') as f:
            f.write(SHOT.replace("name='analog_out'", "name='ms'"))
        with self.assertRaisesRegex(labscript.LabscriptError, 'from labscript import'):
            self.compile_the_shot()

    def test_a_pseudoclock_device_may_not_record_its_own_stop_time(self):
        own_stop_time = textwrap.dedent(
            '''
            class OwnStopTime(DummyPseudoclock):
                def generate_code(self, hdf5_file):
                    super().generate_code(hdf5_file)
                    self.set_property(
                        'stop_time', self.stop_time, location='device_properties'
                    )

            OwnStopTime(name='pseudoclock')
            '''
        )
        with open(self.script, 'w') as f:
            f.write(SHOT.replace("DummyPseudoclock(name='pseudoclock')\n", own_stop_time))
        with self.assertRaisesRegex(labscript.LabscriptError, 'labscript records'):
            self.compile_the_shot()

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
        # and the value 5 ns after the wait at t=2 starts at the resume. The ramp at
        # t=1.5 samples on every tick, and its ticks overrun its requested end.
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
            fast_out.ramp(
                1.5 + 10e-9, duration=1005e-9, initial=10, final=20, samplerate=1e9
            )
            fast_out.constant(2 + 5e-9, 3)
            '''
        )
        shot = SHOT.replace('\nt = 0\n', secondary + '\nt = 0\n')
        script = shot.replace('start()\n', 'start()\n' + instructions)
        with open(self.script, 'w') as f:
            f.write(script)
        self.compile_the_shot()

        import labscript_utils.properties as properties

        with h5py.File(self.run_file, 'r') as f:
            values = f['devices/fast_device/OUTPUTS']['fast_out']
            device_properties = properties.get(f, 'secondary', 'device_properties')
        self.assertEqual(values[0], 0, 'starts at the default, before the ramp')
        self.assertEqual(
            list(device_properties['trigger_times']), [0, 0.5, 2],
            'its start and each resume, in script time',
        )
        self.assertEqual(
            list(values).count(7), 1, 'kept at the ramp end, until the resume'
        )
        self.assertEqual(values[-1], 3)
        self.assertEqual(max(values), 20, 'no ramp value passes its final value')

        # A ramp on the wait's tick but before its resume would run in the delay, and
        # one shorter than a tick cannot be sampled within it:
        for old, new in [
            ('ramp(0.5,', 'ramp(0.5 - 20e-9,'),
            ('duration=1005e-9', 'duration=10e-9'),
            ('duration=1005e-9', 'duration=0'),
        ]:
            with open(self.script, 'w') as f:
                f.write(script.replace(old, new))
            with h5py.File(self.run_file, 'w') as f:
                f.create_group('globals')
            with self.subTest(new), self.assertRaises(labscript.LabscriptError):
                self.compile_the_shot()

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
