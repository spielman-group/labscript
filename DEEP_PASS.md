# labscript deep pass

A planning document for step 2 of the code-health campaign, the deep pass
(`issues/code_health_campaign.md` in the meta repo). It lists candidates for
Ian's review, one section per sub-step, and is deleted when the pass is done.
Nothing is removed until Ian has reviewed each entry.

## Step 1: behaviour no one asked for

No candidates. `CodeHealth` adds no behaviour over `master` that a user's
script can reach and that no one asked for.

How this was checked:

- **What the fork changed.** `git diff master CodeHealth` (two-dot), at
  3510de2, over the whole repo, and `git log master..CodeHealth --no-merges`,
  21 commits. In `labscript/` it is 14 lines added and 38 removed.
- **Request.** Each adding commit's message, and a grep of the meta repo's
  `CODEX.md` and `issues/*.md`.
- **Users considered.** labscript scripts, which every lab writes;
  labscript-devices; and runmanager's and blacs's reads of shot files.

Every change falls in one of these groups, none of them a candidate:

- **Ian's decisions from the mapping round:** the bitfield dtype (b517c76),
  the later-ramp collision check (6a69e17) and the two StaticDDS fixes (65a9264,
  56dcfc2).
- **Compatibility with current dependencies,** each needed for the suite to run
  at all and not changing what a script can do:
  - numpy 2 removed the `'a'` dtype alias (4674eaa in `labscript/`, 63c028c in
    the device-writing guide). `'S256'` is the same dtype, so shot files read
    back unchanged. `CODEX.md` records it as `Numpy2Fixes`.
  - the docs extra and Qt links moved to PyQt6 (3a4bf41, e7a5e4d), as the suite
    did.
  - setuptools_scm's scheme rename (e1e3d40), Ian's decision in
    labscript-utils.
- **Campaign work Ian approved:** `__version__` from
  `labscript_utils.versions.package_version` (4a9dcde, 101af5d), and the legacy
  Camera removed from `example.py` (2223f31).
- **Tests and their conftest,** which add no behaviour (48d8597 to b5d1a79,
  a056464, 3510de2).

`CONTRACT.md`, since deleted, marked no test "Step 2.1": every behaviour its
three tests protect is upstream's.

## Step 2: duplication

Each entry first asks whether the thing should exist, then where its one copy
lives. Line numbers are `CodeHealth` at 93b56d9. "Core lines" counts non-blank
lines, docstrings included. Users considered in every entry: labscript scripts
above all, labscript-devices' device classes, and runmanager's and blacs's
reads of shot files; the class names written to the connection table do not
change in any entry. Subclass and `isinstance` searches were `git grep` over
labscript, labscript-devices, labscript-utils, blacs, runmanager, runviewer,
lyse, labscript-optimization, labscript-agents and hyde, each beside a control
that matches.

### Inside labscript

#### 1. `StaticDDS` repeats `DDSQuantity`

- Copies: `outputs.py`, `DDSQuantity.__init__` (1733-1859) against
  `StaticDDS.__init__` (1979-2090); `DDS.enable` and `disable` (1891-1922),
  inherited from `DDSQuantity`, against `StaticDDS.enable` and `disable`
  (2119-2150).
- Should it exist: yes. NovaTechDDS9M and PhaseMatrixQuickSyn build static DDS
  channels.
- How they differ: the constructors differ only in making `StaticAnalogQuantity`
  rather than `AnalogQuantity` channels, in `StaticDDS` lacking the
  `call_parents_add_device` keyword, and in one full stop in the gate error.
  `enable` and `disable` behave the same. `setamp`, `setfreq` and `setphase`
  genuinely differ: the static ones take no time.
- Proposal: `StaticDDS` subclasses `DDSQuantity`, which names its channel class
  in a class attribute. `StaticDDS` keeps `description`, `allowed_children`,
  that attribute and its three setters, and loses its constructor, `enable` and
  `disable`. It would also inherit `DDSQuantity.pulse`, which calls the setters
  with a time and would silently set the amplitude to that time, so `StaticDDS`
  must refuse `pulse` too.
- Core lines: about 125 saved (constructor 109 and `enable`/`disable` 27, less
  about 10 added).
- Visible: a `StaticDDS` becomes an instance of `DDSQuantity`. No
  `allowed_children` names `DDSQuantity` (NovaTechDDS9M names `DDS` and
  `StaticDDS`; PulseBlaster and RFBlaster name `DDS`), and no `isinstance`
  check names it. `StaticDDS` gains the `call_parents_add_device` keyword.
  labscript-devices' `QuickSynDDS(StaticDDS)` overrides the constructor and
  `enable`, so it is unaffected.
- Other owners: none.
- **Outcome:** Done, 1096e13, as a shared base `_DDSBase` that `DDSQuantity` and `StaticDDS` both derive from (Ian's choice), so `StaticDDS` inherits no `pulse`. NovaTechDDS9M, QuickSynDDS and PulseBlasterDDS shots compile identically before and after.

#### 2. `StaticAnalogQuantity` and `StaticDigitalQuantity` repeat their static machinery

- Copies: `outputs.py`, `get_change_times`, `make_timeseries`,
  `expand_timeseries` and the `static_value` property, identical in
  `StaticAnalogQuantity` (1271-1301) and `StaticDigitalQuantity` (1473-1503).
  Also `StaticDigitalQuantity.go_high` and `go_low` (1441-1472), which differ
  only in the value.
- Should it exist: yes; static outputs are used by labscript-devices
  (ZaberStage subclasses `StaticAnalogQuantity`) and by `StaticDDS`.
- Proposal: one small base class holding the four members, which both classes
  inherit ahead of `Output` and `DigitalQuantity`; `go_high` and `go_low` call
  one private setter.
- Core lines: about 35 saved (26 for the machinery, about 12 for the setters,
  less the base class's header).
- Visible: no. Behaviour, class names and `isinstance` results against the
  existing classes are unchanged.
- Other owners: none.
- **Outcome:** Done, 8190a64: `_StaticQuantity`.

#### 3. `AnalogQuantity`'s ten ramp methods each build the same instruction

- Copies: `outputs.py`, the `add_instruction(t, {...})` block in `ramp` (592),
  `sine` (641), `sine_ramp` (683), `sine4_ramp` (721), `sine4_reverse_ramp`
  (759), `exp_ramp` (833), `exp_ramp_t` (903), `piecewise_accel_ramp` (940),
  `square_wave_levels` (1134) and `customramp` (1178): 133 lines. Each builds
  the same six keys, and nine repeat `round(t + duration, 10) - round(t, 10)`.
- Should it exist: yes; these methods are the language lab scripts are written
  in, and all stay public and unchanged.
- How they differ: only in the function, its description and the end time,
  which is `truncation*duration` or, in the two exponential ramps, a computed
  truncated duration.
- Proposal: one private method taking the start time, the duration performed,
  the function, the description, the sample rate and the units, which each ramp
  method calls.
- Core lines: about 75 saved.
- Visible: no; the instructions written are the same.
- Other owners: none.
- **Outcome:** Done, a6c9262, along Ian's direction that every ramp is an instance of customramp: all ten build their instruction through `Output._add_ramp`, the path customramp uses, placed on `Output` so a digital quantity could use it later. Calling the public `customramp` itself would have renamed every instruction to "custom ramp: ...", which reaches users in collision errors, so the shared path is its private core. `ramp`'s shortcut when `initial == final`, and each method's own truncation check, stay in the methods. The ramp shots compile identically.

#### 4. `load_globals` repeats `get_shot_globals`' conversions and `Device`'s name checks

- Copies:
  - `labscript.py:load_globals` (712-736) converts `np.bool_` to `bool` and
    null references to `None`, after calling labscript-utils'
    `shot_utils.get_shot_globals`, which already does both
    (`shot_utils.py:31-35`), so they never fire. It also opens the shot file and
    never reads it.
  - Its three name checks (716-727: already a name, a keyword, not an
    identifier) repeat `Device.__init__`'s (`base.py:127-141`). Both put names
    into builtins. `Device` raises `ValueError` for a non-identifier where
    `load_globals` raises `LabscriptError`.
- Should it exist: the conversions, once, in `get_shot_globals`. The name
  checks, once, in labscript, since only labscript knows its own namespace.
- Proposal: drop the conversions and the unused file open, and have both
  callers use one private name check that raises `LabscriptError`.
- Core lines: about 17 saved.
- Visible: a device given a name that is not an identifier would raise
  `LabscriptError` rather than `ValueError`, with the message reworded. A
  script would see this only by catching `ValueError` around a bad device
  name; no repo does. Values reach the script converted as before.
- Other owners: none.
- **Outcome:** Done, 50e702d. Both checks now test the caller's module namespace and builtins, as before, but no longer the checking function's own local variables, so a device named `start_order` or a global named `hdf5_filename` is now accepted. A global's error no longer names the shot file.

#### 5. `max_or_zero` is `max(..., default=0)`

- Copies: `utils.py:175`, `max_or_zero`, against the builtin `max` with
  `default=0`. All four callers (`labscript.py:553`, 557, 628 and 655) pass
  one list, where the two agree. Given several arguments they differ:
  `max_or_zero(0, 5)` returns 0.
- Should it exist: no; the builtin does the job.
- Proposal: the four callers use `max(..., default=0)`, and `max_or_zero` goes.
- Core lines: about 15 saved.
- Visible: `labscript.py` imports `max_or_zero`, so `from labscript import *`
  hands it to every script. No repo uses it; a lab's own script could.
- Other owners: none.
- **Outcome:** Done, cd41658: the callers use `max(..., default=0)`, and `max_or_zero` stays with a FutureWarning (Ian), since lab scripts may use it.

#### 6. `_builtins_dict` is defined three times

- Copies: `base.py:34`, `compiler.py:21` and `labscript.py:97`, each
  `builtins.__dict__`. `base.py` and `labscript.py` already import `compiler`.
- Proposal: keep `compiler.py`'s and import it in the other two.
- Core lines: 2 saved. Visible: no; the name is private.
- Other owners: none.
- **Outcome:** Done, 50e702d.

#### 7. `suppress_mild_warnings` and `suppress_all_warnings` share one body

- Copies: `utils.py`, two context managers identical but for the compiler
  attribute they set.
- Should it exist: both names, yes; scripts use them.
- Proposal: leave them. Sharing a body saves about 6 lines and adds
  indirection to two public functions a user reads.
- Core lines: 0.
- Other owners: none.
- **Outcome:** Left (Ian). Separately, both now restore their flag in `try`/`finally`, bab9b12.

#### 8. `Device` initialises `_properties` in two places

- Copies: `base.py`, `Device.__init__` (110-115) and `Device.set_property`
  (214-219) both create `self._properties` and its locations if missing.
- Proposal: leave it for now. The copy in `set_property` guards against a call
  made before `Device.__init__` has run, such as one from a subclass
  constructor that sets a property before calling it. Whether any caller does,
  and so whether one place can serve, is step 3's question, root causes.
- Core lines: 0 now.
- **Outcome:** Left for step 3.

#### 9. `is_remote_connection`, `is_clock_line` and `is_pseudoclock_device` repeat one pattern

- Copies: `utils.py:43`, 58 and 73, each a deferred, cached import followed by
  `isinstance`, with the same docstring.
- Proposal: leave it for step 3. The pattern exists to break a circular import
  between `Device` and its subclasses, so the question is whether that cycle
  can go.
- Core lines: 0 now.
- **Outcome:** Left for step 3.

### Between labscript and other repos

The candidates came from the librarian, whose two subagents read every copy at
`CodeHealth`. Each was then checked here in the source.

#### 10. Single-clock-line pseudoclocks repeat the same overrides in each device

- Copies, all in labscript-devices:
  - a `Pseudoclock.add_device` refusing a second `ClockLine`, in
    `CiceroOpalKellyXEM3001.py:67`, `DummyPseudoclock/labscript_devices.py:21`,
    `PineBlaster.py:24`, a copy of the dummy's apart from names,
    `RFBlaster.py:20` and `PrawnBlaster/labscript_devices.py:30`;
  - a `PseudoclockDevice.add_device` admitting one `Pseudoclock`, with the same
    error text, in the dummy (66), `PineBlaster.py` (70), `RFBlaster.py` (62),
    `PulseBlaster.py` (242) and `CiceroOpalKellyXEM3001.py` (189);
  - the internal pseudoclock, clock line and intermediate device behind a wait
    monitor, each with an empty `generate_code`, in `CiceroOpalKellyXEM3001.py`
    (82, 96, 109) and `PrawnBlaster/labscript_devices.py` (69, 89, 109).
- labscript has no means to say "one child of this kind"; `allowed_children`,
  enforced in `Device.add_device` (`base.py:345`), limits the kind only.
- Should it exist: the limits, yes, since each device has one clock output.
- Proposal: labscript's `Pseudoclock` and `PseudoclockDevice` take a class
  attribute limiting their clock lines and pseudoclocks, enforced in their
  `add_device`, and the devices drop their overrides. Whether labscript also
  provides the wait-monitor chain is a second question.
- Core lines: about 15 added in labscript, about 100 saved in labscript-devices.
- Visible: the error a user sees on miswiring a clock line changes its wording.
- Other owners: labscript-devices.
- **Outcome:** Done: labscript 2627de4 and 10bdafd, with a test; labscript-devices e806548 drops the overrides. The wait-monitor chain was not asked for.

#### 11. Pseudoclock devices write `is_master_pseudoclock` and `stop_time` themselves

The agreed plan, to be built in a later session. Nothing is changed yet.

- The problem: BLACS, runviewer and the device workers need two timing facts
  about every pseudoclock device, both of which labscript computes:
  - `stop_time`, its program's nominal end in its own time base. `stop()` gives
    every pseudoclock device the same end, and
    `PseudoclockDevice.offset_instructions_from_trigger` converts a secondary's
    into its own time base. BLACS's progress bar and runviewer read the
    master's; the dummy and PulseBlaster workers read their own.
  - `is_master_pseudoclock`, which the Cicero, PineBlaster and PrawnBlaster
    workers read, for example to decide which acts as the wait monitor.
- The cause: labscript computes both facts but leaves recording them to each
  device class, by convention, with nothing to enforce it. So six devices copy
  the same lines into their `generate_code` (Cicero, Dummy, PineBlaster and
  PrawnBlaster both facts; PulseBlaster and PulseBlaster_No_DDS `stop_time`
  only), and two record neither: RFBlaster and PrawnDO. PrawnDO is a
  pseudoclock in labscript's sense: a PrawnBlaster-based digital output board
  that subclasses `PseudoclockDevice`, runs its own program on its own clock
  and is triggered like a secondary. Read from the code, not run: runviewer
  and the progress bar would raise `KeyError` on a shot whose master is either
  of these two.
- The rule: a fact belongs to whoever computes it. labscript records what it
  computes; a device class records only what it computes about its own
  hardware.
- The plan:
  1. labscript: `PseudoclockDevice.generate_code` records both properties for
     every pseudoclock device, straight after `offset_instructions_from_trigger`
     has fixed `stop_time`. Every device already calls it first, since it also
     runs the checks and the trigger offsets.
  2. labscript: the two names belong to labscript. A pseudoclock device class
     that sets either fails at compile time, before anything reaches hardware,
     with an error naming the class and the property, saying that labscript
     records both for every pseudoclock device, and telling the author to
     delete the `set_property` call and where the docs explain it. It replaces
     the generic "set more than once" error, whichever side writes second.
     Pseudoclock devices written outside this install are not kept compatible;
     they get this error on their first compile.
  3. labscript: the device-writing guide in `docs/` gains a section on what
     labscript records for every pseudoclock device, that device classes must
     not set it, and what to delete when upgrading an old device.
  4. labscript: one test, that a pseudoclock device setting `stop_time` itself
     is refused with that error.
  5. labscript-devices: delete the six copies, landing together with 1 and 2,
     since either alone breaks the six devices. RFBlaster and PrawnDO need no
     change: they gain both properties. Five devices make their device group
     with `create_group` rather than `Device.init_device_group` (`base.py:470`):
     Cicero, PineBlaster and PulseBlaster among the six, and RFBlaster and
     PhaseMatrixQuickSyn. They can switch in the same edit.
  6. blacs and runviewer: no change; they read the same properties as now.
- Not chosen: recording the shot's length among the shot properties beside
  `target_cycle_time`. That would hold the master's `stop_time` twice, and
  runviewer would need a fallback for archived shot files.
- Open, for Ian, before or with this work: the shot ends when the last
  pseudoclock finishes, not the master, and nothing ensures that.
  - labscript gives every pseudoclock device the same nominal end, the time
    passed to `stop()`, and refuses an instruction after it (`core.py:520`).
  - But a triggered pseudoclock runs on its own clock. It can physically
    finish after the master, through drift between free-running oscillators,
    trigger latency not modelled, or a closing instruction its hardware needs.
  - BLACS starts the master and declares the shot over when the master's
    worker alone reports done (`blacs/shot_execution.py:942-955`). It then
    moves every device to manual. Whether a secondary still running is cut
    short depends on its worker: many block in `transition_to_manual` until
    their hardware has finished. Which secondary-pseudoclock workers do is
    not yet surveyed; that is labscript-devices' question.
  - The progress bar likewise shows the master's `stop_time` as the shot's
    length.
  - A fix belongs to BLACS: for example, wait for every pseudoclock device's
    worker to report done. Unless the shot's real end is wanted, the plan above
    does not depend on it.
- Core lines: about 15 added in labscript, plus the docs section; about 20
  removed from labscript-devices.
- Other owners: labscript-devices (step 5); blacs, if the open point is taken
  up.
- **Outcome:** Planned, as above (Ian). Not yet built.

#### 12. The connection table's layout is spelled out by its writer and readers

- Copies: labscript writes it (`labscript.py:222-280`: the column dtype, the
  `"None"` placeholder, the dataset name). labscript-utils reads it
  (`connections.py:215-258`, `properties.py:140-165`), and blacs names the
  dataset again (`shot_execution.py:427`, `front_panel_settings.py:70` and
  336-338).
- Should it exist: yes; it is the shot-file format.
- Proposal: leave it. The column names are the format itself; a shared
  definition would have to live in labscript-utils and save a few lines while
  binding the writer to a reader's module. Two findings belong to their owners:
  blacs's `device_base_class.py:218` compares `unit_conversion_class` with the
  string `"None"`, which `connections.py` has already turned into `None`, so it
  never fires. And labscript-utils reads old repr-format rows with a fallback in
  `connections.py` but not in `properties.get`.
- Core lines: 0 in labscript.
- Other owners: blacs and labscript-utils, for their findings only.
- **Outcome:** Left (Ian). The blacs and labscript-utils findings went to the coordinator.

#### 13. Unit constants are defined in labscript and runmanager

- Copies: `labscript/constants.py:16-37` and `runmanager/functions.py:16-23`,
  the same eight values; runmanager's serve the globals sandbox.
- Proposal: leave them. runmanager's GUI process does not import labscript,
  so sharing means a new labscript-utils module to save 8 lines.
- Core lines: 0.
- Other owners: none, unless Ian wants them shared.
- **Outcome:** Left (Ian).

#### 14. Smaller overlaps, left alone

- `labscript.py:378-379` decodes the version-control output by hand. Passing
  `text=True` to the `Popen` above would do it, saving 2 lines; it is
  simplification rather than duplication.
- `'__PrimaryBLACS'` is written in `remote.py:33` and read in
  `blacs/tab_base_classes.py:323`: a one-line name in the shot format.
- `bitfield` beside the bit packing in device workers (NI_DAQmx, PrawnDO,
  PulseBlaster): the workers do not import labscript, and the packing is
  labscript-devices' own question. `AlazarTechBoard.py:73` imports `bitfield`
  and never uses it.
- Clock-tick rounding in device `generate_code` methods, beside
  `Device.quantise_to_pseudoclock`, which needs a pseudoclock and cannot take
  bare values: labscript-devices' own question.
- The script name is written by runmanager (`script_basename`) and by labscript
  (the `script` dataset's `name`), which lyse reads. Different writers at
  different times.
- **Outcome:** Left (Ian).

## Step 3: root causes

Every guard in `labscript/` (try/except, hasattr, getattr with a default, and
special cases around them) was traced to its cause. All are upstream's. Line
numbers are `CodeHealth` at a423925. "Fired" means seen by running: a copy of
labscript logged each guard as it fired while every step 2 shot compiled (the
example, the test shot, NovaTech, QuickSyn, PulseBlaster, the ramps, globals
and the error paths) and labscript-devices' tests ran (41 passed).

### Fix the cause

#### 1. `Device` creates `_properties` in four places

- Where: `base.py:125` (`__init__`, "may be instantiated already"), 214
  (`set_property`), 302 (`get_property`) and 332 (`get_properties`).
- Cause: NI_DAQmx's constructor calls `set_property('__version__', ...)`
  (`NI_DAQmx/labscript_devices.py:315`) before `IntermediateDevice.__init__`
  (319). It is the only caller: the `set_property` and `__init__` guards fired
  for NI_PCIe_6363 and NI_PCI_6733 alone, and the `get_property` and
  `get_properties` guards never fired.
- Proposal:
  - NI_DAQmx sets the property after calling `IntermediateDevice.__init__`;
  - `Device.__init__` creates the storage unconditionally;
  - the two getter guards go;
  - `set_property` raises a clear `LabscriptError` if called before
    `Device.__init__`, saying to call it first, rather than tolerating it.
- Core lines: about 8 removed. Visible: only to a device written that way,
  which gets the clear error. Other owners: labscript-devices, two lines.
- **Outcome:** Done, 3f4f6d5, with labscript-devices d338970 moving NI_DAQmx's call. The two must reach any tier together: without d338970, every NI card fails to compile.

#### 2. The circular import behind `is_remote_connection`, `is_clock_line` and `is_pseudoclock_device`

- Where: `utils.py:43`, 58 and 73, each a deferred, cached import, used by
  `Device` in `base.py:157`, 166, 364-375 and 407-418.
- Cause: `Device` asks whether itself or a parent is a `ClockLine`, a
  `PseudoclockDevice` or a `_RemoteConnection`. Those classes live in modules
  that import `base`.
- Proposal:
  - The first two questions belong to the subclasses. `Device.pseudoclock_device`
    returns its parent's (or `None` at the top), and `PseudoclockDevice`
    overrides it to return itself. `Device.parent_clock_line` returns its
    parent's, `ClockLine` overrides it to return itself, and a device with no
    clock line above it raises a clear `LabscriptError` naming the device.
  - The third is a check of a user's `gui` or `worker` argument, made only when
    one is given. A function-local `from .remote import _RemoteConnection`
    there does it.
  - All three helpers and their module globals go.
- Evidence:
  - The catch-all `except` around the clock-line walk fires when a device has
    no clock line above it. Run on a top-level DummyPseudoclock, it gives
    "Couldn't find parent ClockLine of pc, what's going on? Original error was
    'NoneType' object has no attribute 'parent_device'."
  - The `except` around the pseudoclock walk can never fire, since its loop
    stops at `None`; it never fired.
  - No other repo uses the helpers (`git grep -w` exit 1 in labscript-devices,
    labscript-utils, blacs, runmanager, runviewer, lyse,
    labscript-optimization, labscript-agents and hyde).
- Core lines: about 50 removed. Visible: the error for a device with no clock
  line is reworded, for the better. Other owners: none.
- **Outcome:** Done, f58e840; the error reads "There is no ClockLine above pc, which has no parent." (fbe2f6c). It names the top device, since each parent answers in turn.

#### 3. The unit-conversion import is wrapped to warn on failure

- Where: `labscript.py:52-55`, `try: from labscript_utils.unitconversions
  import *` with a warning on `ImportError`.
- Cause, no longer real: `unitconversions` is part of labscript-utils, a hard
  dependency, and it imports. If it failed, scripts would warn and then fail
  later with a `NameError` on a conversion class.
- Proposal: a plain import, so a broken install raises with its cause.
- Core lines: 3 removed. Visible: no.
- **Outcome:** Done, 53d6fad.

#### 4. `IntermediateDevice` and `ClockLine` read `clock_limit` with `getattr`

- Where: `core.py:59`, 86 (`clock_limit`) and 91 (`minimum_clock_high_time`).
- Cause, real: DummyCamera, TriggerableCamera and ZaberStageController declare
  no `clock_limit`, since they have no clocked outputs. ClockLine's own comment
  (`core.py:108`) asks whether every intermediate device should have one.
- Proposal: `IntermediateDevice` declares `clock_limit = None`, meaning no limit
  of its own, and the reads become plain attributes.
  `minimum_clock_high_time` is a property of every `IntermediateDevice`, which
  is `ClockLine`'s only allowed child, so its `getattr` goes too.
- Core lines: about 0; the protocol becomes explicit. Visible: no.
- **Outcome:** Done, 4eec43a; the `minimum_clock_high_time` check for `None` went too, since nothing sets it.

#### 5. `AnalogQuantity.constant` uses a bare `except`

- Where: `outputs.py:1113-1119`, checking that the value converts to float.
- Proposal: catch `(TypeError, ValueError)`, and drop the unused `val`. The
  bare `except` also catches Ctrl-C.
- Core lines: 1 removed. Visible: no.
- **Outcome:** Done, e7051dc; `OverflowError` is caught as well, as the bare `except` did.

### Keep, with the reason

#### 6. `Pseudoclock.expand_change_times` skips outputs without a `timeseries`

- Where: `core.py:393`.
- Fired 48 times, all for static channels (`StaticAnalogQuantity`) under
  NovaTech's clock line. Static outputs never build a timeseries and never
  sweep, so skipping them is right. The test is the cheapest correct one.
- **Outcome:** Kept (Ian).

#### 7. Protocol checks with real absent cases

- `hasattr(device, 'BLACS_connection')` (`labscript.py:237`, 444): the device
  has a BLACS tab.
- `getattr(device, 'unit_conversion_class', None)` (247): only outputs have one.
- `hasattr(parent_device, 'get_default_unit_conversion_classes')`
  (`outputs.py:1666`): fired True for NovaTechDDS9M, False for PulseBlaster's
  direct outputs.
- `hasattr(self.calibration, ...)` (`outputs.py:88`, 96): checks a user's unit
  name.
- `hasattr(inst, name)` in `set_passed_properties` (`utils.py:129`): the
  documented override by an instance attribute.
- `hasattr(parent_device, "name")` (`core.py:45`): names a non-device parent a
  user passed, in the error.
- **Outcome:** Kept (Ian).

#### 8. Real external conditions

- git or hg missing (`_have_vcs`, `labscript.py:301`).
- No `labscriptlib` installed (395).
- Modules without `__file__` (401).
- A shot file already holding compilation data (509), turned into a clear
  error.
- **Outcome:** Kept (Ian).

#### 9. End-of-sequence cases expressed as exceptions

- `core.py:367`, warning that a clock line's last change precedes another's.
- `core.py:498`, re-raising unless at the last change time.
- `outputs.py:516`, a one-element ramp.
- `functions.py:218`, a scalar or an array.
- Each is a real case. Writing them as explicit checks is step 6's business.
- **Outcome:** Kept (Ian).

### Follow-up

#### 10. Why labs quantise their running time themselves

- Report: Ian's labs quantise `t` themselves, with `quantise_to_pseudoclock` or
  a home-made version, because otherwise the compiler gives puzzling errors.
- Reproduced, on the dummy pseudoclock (resolution 25 ns, minimum update
  interval 100 ns): a ramp from `t`, then `ao.constant` 0.3 ns after the
  ramp's end, as unequal arithmetic paths to "the same time" produce.
  - The ramp's end falls just short of a half-tick boundary, so the
    constant's time rounds to the next tick. Compiling fails with "Commands
    have been issued … at t=0.11 and t=0.110000025. This Pseudoclock cannot
    support update delays shorter than 1e-07 seconds." The user wrote one
    command at that time.
  - Both times fall within one tick. The shot compiles, but the constant is
    lost: the output stays at the ramp's final value, 1, where the script set
    5. No error and no warning.
  - With `t` quantised after every step, both compile and the output ends at
    5.
- The cause: instruction times are kept unquantised until after the checks
  that compare them.
  - `Output.add_instruction` rounds times only to 0.1 ns (`outputs.py:224`,
    227).
  - `Output.do_checks` then adds a "hold the final value" instruction at a
    ramp's end time unless an instruction sits at exactly that float
    (`outputs.py:345`). A time a fraction of a tick later does not count, so
    there are now two instructions within one tick.
  - `Output.offset_instructions_from_trigger` (`outputs.py:393`) quantises
    each time to the pseudoclock and stores it by its new time (418). Two
    instructions in one tick land on one key, and the hold, added later,
    silently replaces the user's. Two instructions either side of a tick
    boundary become 25 ns apart and fail the minimum-interval check in
    `Pseudoclock.collect_change_times`.
- A further effect, found by compiling 200 random sequences: quantising `t`
  by hand trades one error for another.
  - A ramp ends at its unquantised end time, and the next ramp starts at the
    quantised `t`, which can round below it.
  - `add_instruction` then refuses the overlap ("State of analog output … has
    already been set to linear ramp"). This happened in 37 sequences that
    compiled with raw `t`.
  - No sequence failed with raw `t` and passed with quantised `t`; the failure
    above needs times a fraction of a tick apart, which random durations rarely
    give.
- The fix at the cause: `add_instruction` quantises an instruction's time, and
  a ramp's start and end, to the output's pseudoclock as it stores them, in
  place of rounding to 0.1 ns.
  - Every later check then compares the times the hardware will use. An
    instruction at a ramp's end coincides with it, so no hold is added, and two
    instructions in one tick meet the existing "already been set" warning
    instead of one vanishing.
  - A ramp's function keeps the duration the user gave.
  - `offset_instructions_from_trigger` still re-quantises after subtracting a
    secondary pseudoclock's trigger offsets. It should refuse rather than
    overwrite when two instructions land on one time, as a check of the
    invariant.
  - With this, labs would no longer need to quantise `t` themselves.
- Ian's hypothesis, tested: do a long ramp's clock times drift from its
  intended sample times? Studied on the PulseBlaster, which his labs use.
  - How a ramp is clocked. `Pseudoclock.expand_change_times` (`core.py`)
    first rounds the sample period to a whole number of clock ticks. It then
    takes the sample times as start + k × that rounded period, evaluates the
    ramp at those times, and emits clock instructions of one tick, a loop of
    n − 2 repetitions, and a last step that reaches the next change time
    exactly.
  - So yes, the encoding is start plus n repetitions of one quantised step.
    But labscript's own sample times use the same quantised step, so the
    values are computed for the times the hardware plays. Every pseudoclock
    in labscript-devices converts with `int(round(step / resolution))`, which
    is exact here.
  - PulseBlaster (PB-DDSII-300, 26.67 ns ticks of two 75 MHz cycles), a
    10 ms ramp at 290 kHz, whose period is 129.31 ticks, compiled:
    - one 3,440 ns tick (129 ticks), a `LOOP` of 2,905 more, then a last
      step of 3,360 ns;
    - the ramp ends at 10 ms exactly, and the next instruction lands on time;
    - there are 2,907 samples where 2,900 were asked for. Against the
      requested 3,448.3 ns grid the samples drift by up to 21.6 µs (the
      effective rate is 290.7 kHz), but the waveform is right for the times
      played.
    - The dummy pseudoclock (25 ns) gave the same: steps of exactly 133 ticks,
      0 ns from the rounded-period grid, and the next instruction exactly on
      time.
  - So the hypothesis does not hold in labscript's compilation. It does not
    explain the collision errors either: those are raised before any device
    encodes its clock, and come from the sub-tick mechanism above.
  - One open question, on the hardware side, that would make it hold.
    - The PulseBlaster worker passes each delay to SpinAPI as float
      nanoseconds (`pb_inst_dds2`, `pb_inst_pbonly`).
    - Labscript's step lengths, though whole cycles in exact arithmetic,
      reach SpinAPI a few 1e-12 cycles below a whole cycle for about 9% of
      step lengths on every model checked (1,831 of 19,999 on the
      PB-DDSII-300, 1,239 on the USB model, 593 on the ESR-PRO-500).
    - If SpinAPI converts by truncation, each such looped step is one cycle
      short on every repetition. The error then compounds: about 39 µs over
      the ramp above, and everything after it on the master clock is early.
      If SpinAPI rounds to the nearest cycle, nothing happens.
    - SpinAPI is not installed here, so this is unverified. It is settled by
      reading SpinAPI's conversion, or by timing a long looped ramp on a
      PulseBlaster against the intended end. If it truncates, the fix is in
      labscript-devices: pass delays a whole number of cycles plus half a
      cycle, or rounded to the cycle, in ns.
  - The known PulseBlaster issue (labscript-devices `KNOWN_ISSUES.md`: a fixed
    `pulse_width` already a whole number of half-ticks is rounded up one more)
    does not compound this. It lengthens the high time, and the low time
    shrinks by the same amount, so the step is unchanged. Its effect is a lower
    `clock_limit`, so a fast ramp can be refused; only with a fixed
    `pulse_width`, not the default symmetric pulse.
  - Which PulseBlaster model each lab runs is not in the repos; connection
    tables are lab-local.
- **Outcome:** Built, da265dc..38e7279.
  - Times are rounded to clock ticks: on the master when an instruction is
    added, and on a secondary once, when its trigger offsets are applied. The
    0.1 ns rounding is removed.
  - Two instructions on one output in one tick warn and keep the one added
    last.
  - `Trigger.trigger` raises for a trigger whose rise and fall land on one tick,
    and for a sub-tick gap between triggers. Master pseudoclock only; the
    secondary gap is in `KNOWN_ISSUES.md`.
  - The float noise left in ramp values is accepted (Ian's option 1). The
    integer-tick fix is recorded in `KNOWN_ISSUES.md`, `docs/source/timing.rst`
    and a comment in `Output.expand_timeseries`.
  - Not ported to `UpstreamBugFixes`: the patch does not apply cleanly to its
    `outputs.py`, and that tree cannot compile here without the numpy 2 dtype
    fixes, so a port could not be verified.
  - The SpinAPI truncation question went to labscript-devices.
- **Validation fixes.** A Codex validation found that a secondary's times were
  compared in absolute ticks, though its own ticks are offset by its triggers.
  - Faults fixed. Fault 3 was also on `Development`; the others were
    regressions from this work:
    1. a value one tick after the start replaced the default start value;
    2. a value just after a wait missed the trigger's delay, so it resumed a
       tick late;
    3. a ramp's end hold, on the user's tick by the secondary's clock but not
       by the master's, replaced the user's value, the original bug;
    4. a same-tick replacement kept the replaced ramp's interval, so a later
       ramp inside it was refused.
  - The fix: `Output._trigger_offset` gives the offset that puts a time on the
    output's own clock. A trigger counts when the time is on a later tick of
    the clock as it ran up to that trigger, which is the tick the secondary's
    WAIT is written at. `do_checks` and `offset_instructions_from_trigger` both
    use it. `do_checks` adds a ramp's end hold only for ramps that survive,
    keeping the one added last on each tick. `ramp_limits` is removed:
    `get_ramp_times` and the overlap check read the ramps from
    `self.instructions`. The `stop()` doc now allows `t` at the last
    instruction.
  - Behaviour on the master changes only where a ramp is replaced on its own
    tick. A later ramp inside the replaced one's interval is now accepted, and
    of two ramps at one start, the one added last is kept in either order.
  - On a secondary, the "too soon after a trigger" check now compares the
    secondary's own ticks, and a ramp across a wait is now refused.
  - Found and recorded in `KNOWN_ISSUES.md`, not fixed: the too-soon-before
    check never fires; `stop(t)` exactly one interval after the last
    instruction is refused by float noise; on a secondary, a ramp replaced at a
    different time on its own tick still blocks a later ramp. Item 5 of the
    validation, the dependency floors, is separate and still open.
  - **Checks:** the reproductions fail before and pass after. The 52 test
    shots and the 9 RbChip sequences (a master PulseBlaster only) compile to
    identical shot files. Four new secondary cases with waits are also
    identical: two waits, a PulseBlaster secondary, `set_initial_trigger_time`,
    and a 41 ns delay. labscript's suite (6) and labscript-devices' (41) pass.
    One test, which fails on the old code, covers faults 1 to 3.
  - **Review:** one independent Opus review found fixes 1 to 3 correct at the
    cause and nothing blocking. Its points are taken: the test comment, a wait
    assertion, the offset docstring, and the KNOWN_ISSUES line for the
    secondary case.

## Step 4: dead code and compatibility leftovers

Line numbers are `CodeHealth` at ff893be. Every class, function and
module-level name in `labscript/` (142) was searched by whole word in the `.py`
files of labscript, labscript-devices, labscript-utils, blacs, runmanager,
lyse, runviewer, labscript-optimization, labscript-agents, labscript-suite,
zprocess and hyde. A control matched each name's own definition. Four names have
no use outside their definition: the first two entries below, and the public
methods in entry 7.

### Remove

#### 1. `SecondaryControlSystem` is never used

- Where: `remote.py:43-45`. Added in b798c58 (2017) for BLACS "secondary control
  systems", which were never built; its `port` has no default, unlike
  `RemoteBLACS`.
- Use: none in any repo. It is not in `from labscript import *`, since
  `labscript.py` does not import `remote`, so a script would have to import it
  from `labscript.remote` explicitly.
- Proposal: delete it. Lines: 3. Visible: only to such a script, which gets an
  `ImportError`.
- **Outcome:** Done, e58c5ba.

#### 2. `no_warnings` is a historical alias of `suppress_all_warnings`

- Where: `labscript.py:102`. `suppress_all_warnings` was first named
  `no_warnings` (e9cd64a, 2012), and the alias was kept on renaming.
- Use: none in any repo, but `from labscript import *` hands it to every script.
- Proposal: delete it, or give it the FutureWarning `max_or_zero` got, if a
  lab script might still use it. Lines: 1. Visible: a script using it gets a
  `NameError`, or the warning.
- **Outcome:** Kept with a FutureWarning (Ian), ea9c096: `no_warnings` warns, then behaves as `suppress_all_warnings`.

#### 3. `labscript_init`'s `load_globals_values` and the `TO_DELETE` markers

- Where: `labscript.py:26-33` (a "Notes for v3" comment), 703-704, 712-713 and
  736-739 (markers), and the `load_globals_values=True` parameter of
  `labscript_init` (714, 722, 737).
- History: in 2018 upstream planned to move globals loading from labscript to
  runmanager's batch compiler (660de86, f10af8b), and marked the labscript side
  for deletion. The move never happened. runmanager's `batch_compiler.py` calls
  `labscript_init` with the default on `master`, `Development` and `CodeHealth`
  alike, so `load_globals` is the live mechanism.
- Use of `load_globals_values`: no caller in any repo passes it.
- Proposal: delete the comment, the markers and the parameter; `load_globals`
  stays. Lines: about 14. Visible: a caller passing `load_globals_values` gets
  a `TypeError`; none is known.
- **Outcome:** Done, e31fc13.

#### 4. `example.py`'s `my_ramp` is uncalled and broken

- Where: `example.py:231-233`. It calls `functions.sine_ramp`, but `example.py`
  never imports `functions`.
- Use: none, in the file or anywhere else.
- Proposal: delete it. Lines: 3. Visible: no.
- **Outcome:** Done, eda8d35.

#### 5. `quantise_to_pseudoclock` converts sets, which no caller passes

- Where: `base.py:367-368`, the `set` branch, and the docstring at 357.
- Use: callers pass arrays, lists and floats (`core.py:216`, 264, 893-894;
  `outputs.py:408-435`), in labscript and labscript-devices.
- Proposal: drop the `set` branch and the docstring's mention of sets. Lines: 2.
  Visible: a set would come back as a list.
- **Outcome:** Done, e54f599; the method stays, as core language (Ian).

### Move the users, then remove

#### 6. `config` is an alias of `compiler`

- Where: `labscript.py:101`, `config = compiler`. labscript's settings once lived
  in a separate `config` object; the 2023 refactor (5345e6d) moved them onto
  `compiler`, so that they reset with it, and kept the name.
- Use: ten labscript-devices files import `config` from labscript (AlazarTech,
  Cicero, DummyIntermediateDevice, DummyPseudoclock, LightCrafterDMD, NovaTech,
  PhaseMatrixQuickSyn, PineBlaster, PulseBlaster_No_DDS and RFBlaster). They
  use it 21 times, all as `config.compression`.
- Proposal: labscript-devices imports `compiler` and reads
  `compiler.compression`, and the alias goes, in the same round.
- Lines: 1 in labscript. Visible: a lab's own device importing `config` gets
  an `ImportError`. Other owners: labscript-devices.
- **Outcome:** labscript-devices moved its 13 files to `compiler` (7ca9969; three more than listed, importing `config` in multi-line imports), and the device-writing guide too (2a76b38). `config` stays with a FutureWarning (Ian), ea9c096, since labs' own devices likely use it: it forwards reads and writes to `compiler`.

### Keep

#### 7. Public methods no repo calls

- `AnalogQuantity.piecewise_accel_ramp` and `DigitalQuantity.repeat_pulse_sequence`.
- They are part of the language lab scripts are written in, which no search of
  the repos can see. Keep.
- **Outcome:** Kept (Ian).

#### 8. `max_or_zero`

- Deprecated with a FutureWarning in step 2 (cd41658). It goes in a later
  round, once Ian judges that lab scripts have moved off it.
- **Outcome:** Kept (Ian).

#### 9. `import builtins` and `import keyword` in `labscript.py`

- Unused there since step 2, and kept only because `from labscript import *`
  hands every module-level name to scripts.
- Ian may drop them: a script relying on the star import for these two would
  need its own `import`.
- **Outcome:** Kept (Ian).

## Step 5: documents

Done, b65dbcb; no candidate round, under the lean rules.

- History narration replaced by what holds now: `compiler.py` (the warning
  settings on the compiler), `labscript.py` (the star import's purpose),
  `tests/test_compile_shot.py`'s module docstring, and the device guide's dtype
  comment (`docs/labscript-dev/intermediatedevice_example.py`).
- `functions.square_wave`: its phase tolerance was justified by "labscript
  rounds all times to multiples of 0.1 ns", no longer true. The tolerance stays
  (well below any tick, well above float error), under a truthful comment.
- Spent TODOs removed from `core.py`: whether intermediate devices need a clock
  limit (settled in step 3), and a robust clock-line lookup (step 3 added the
  clear error).
- `:inherited-members:` added to the autosummary class template. The docs build
  (Sphinx 8.2.3): `DDSQuantity` lists `enable` and `disable`, and
  `StaticAnalogQuantity` lists `get_change_times` and `static_value`;
  `timing.html` builds.
- The bad-global error names the shot file again (192ed67).

For Ian, which step 5 cannot settle:

- `sine4_reverse_ramp` (`functions.py:86`, `outputs.py`, `AnalogQuantity`): it
  runs from `final` at `t` to `initial` at `t + duration`, while its docstrings
  call it "decreasing" and say `initial` is the value at `t`. Either the
  behaviour or the docs is wrong.
- `exp_ramp` and `exp_ramp_t` still accept the old keywords `trunc` and
  `trunc_type`: a compatibility leftover, step 4's business.
- Open TODOs, wishes rather than spent: checking a clock line's connection
  against its pseudoclock (`core.py`, `ClockLine.__init__` and
  `Pseudoclock.add_device`, the latter with two commented-out lines);
  triggering one pseudoclock of a device rather than the device
  (`labscript.py`, `start`); intersphinx links for desktop-app and spinapi
  (`docs/source/conf.py`).
- The legacy documents `docs/Using the labscript API.docx` and
  `docs/labscript-dev/main.tex` (with its built `main.pdf`): not reviewed, since
  the first is binary; keep, update or drop.
  **Outcome:** content moved to the docs (882ed4e here, labscript-devices
  950712a), then the documents removed (96f20f5).
- The docs build gives 27 warnings, mostly autosummary failing to import numpy
  names that `labscript.core` star-imports, and one on `max_or_zero`'s
  docstring.

## Step 6: whole-file style

Every module, `example.py` and the tests were rewritten under labscript-style:
NumPy docstrings on the public surface (144 Google-style sections before, none
after), comments cut to the why in three lines or fewer, `class Foo:`,
zero-argument `super()`, and f-strings with identical text. Sonnet workers did
one module or group each, inputs.py first as the trial.

- **Commits:** e8a3df7 (inputs), 62be9da (example, tests), a570012
  (functions, utils), 564a66e (base, compiler, remote), f2a54cb (core),
  75d29a4 (outputs), 8bca5a1 (labscript.py), 33c0c4d (review fixes).
- **Code changes:** only `super()` where the class has one direct base (no
  class in labscript or labscript-devices inherits from two of these), f-strings,
  three unused locals, and line wraps. Each commit's code was compared with its
  parent's, docstrings ignored.
- **Checks:** the 52 test shots and 9 RbChip sequences compile to identical
  shot files against 268d127; labscript's and labscript-devices' suites pass;
  a clean-copy docs build gives 0 warnings.
- **Review:** one independent review found 24 places where text and code
  disagreed or a comment was too long; all were fixed in 33c0c4d.
- **Bug found and fixed:** `add_time_marker` never refused an RGB tuple outside
  0 to 255, since pylab's `all` took the generator as one true value
  (dcbf983, with a test).
- **Also:** `del core` became `globals().pop('core', None)`, which works on a
  numpy without the alias (972d8ab; on `UpstreamBugFixes` as 541d232, after
  the original fix as eeeb51d). The connection diagram's source is now an SVG
  that HTML uses directly, with a PNG rendered from it for the PDF (df1e3a6).
- **From the earlier survey:** `sine4_reverse_ramp`'s docstrings, the `core.py`
  TODOs, the narrating test docstring and the missing inherited members are
  fixed. `PseudoclockDevice.do_checks(self, outputs)` keeps its signature,
  which differs from `TriggerableDevice.do_checks(self)`, since a lab's own
  devices may override it; `generate_code` says why it bypasses the parent.
