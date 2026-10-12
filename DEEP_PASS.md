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
     change: they gain both properties. Five devices also make their group
     with `create_group` rather than `Device.init_device_group` (`base.py:470`);
     they can switch in the same edit.
  6. blacs and runviewer: no change; they read the same properties as now.
- Not chosen: recording the shot's length among the shot properties beside
  `target_cycle_time`. That would hold the master's `stop_time` twice, and
  runviewer would need a fallback for archived shot files.
- Open, for Ian, before or with this work: the shot ends when the last
  pseudoclock finishes, not the master, and nothing ensures that.
  - labscript gives every pseudoclock device the same nominal end, the time
    passed to `stop()`, and refuses an instruction after it (`core.py:519`).
  - But a triggered pseudoclock runs on its own clock. It can physically
    finish after the master, through drift between free-running oscillators,
    trigger latency not modelled, or a closing instruction its hardware needs.
  - BLACS starts the master and declares the shot over when the master's
    worker alone reports done (`blacs/shot_execution.py:942-955`). It then
    moves every device to manual, so a secondary still running would be cut
    short.
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

## Seen for later steps

Each was re-checked on `CodeHealth` at 3510de2. All are upstream's code.

- **Step 4, dead code and compatibility leftovers.**
  - `labscript.py:108`, `config = compiler`, and 109, `no_warnings =
    suppress_all_warnings` ("Historical alias"). `no_warnings` is used in no
    repo, hyde included; `config` was not searched yet.
  - `labscript.py:28`, 710, 739 and 763: comments marking `load_globals` and
    `labscript_init`'s `load_globals_values` as
    `TO_DELETE:runmanager-batchompiler-agnostic`. The code is live:
    runmanager's `batch_compiler.py:59` calls `labscript_init` with the default
    `load_globals_values=True`, so only the stale markers would go.
  - `remote.py:43`, `SecondaryControlSystem`, used in no repo, hyde included.
  - `outputs.py:1201` binds `val = float(value)` and never uses it.
  - `example.py:231`, `my_ramp`, is never called and uses `functions`, which
    `example.py` never imports.
- **Step 6, style.**
  - `functions.py:86` and `outputs.py:736`: `sine4_reverse_ramp`'s docstrings
    say "decreasing", but it runs `sine4_ramp` backwards in time, from `final`
    to `initial`.
  - `PseudoclockDevice.do_checks(self, outputs)` (`core.py:827`) overrides
    `TriggerableDevice.do_checks(self)` (`core.py:697`) with a different
    signature.
  - `core.py:77`, 107 and 144: TODO comments, the last half-written.
  - `tests/test_compile_shot.py`'s module docstring and
    `docs/labscript-dev/intermediatedevice_example.py:105-111` narrate history.
  - The API pages no longer show `enable` and `disable` on `DDSQuantity` and
    `StaticDDS`, nor the static members on the static quantities, since the
    autosummary class template (`docs/source/_templates/autosummary-class.rst`)
    omits `:inherited-members:`. Inferred from the template; the docs were not
    built.
