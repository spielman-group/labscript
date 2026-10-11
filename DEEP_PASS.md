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

## Seen for later steps

Each was re-checked on `CodeHealth` at 3510de2. All are upstream's code.

- **Step 2, duplication.** `StaticDDS.__init__` repeats `DDSQuantity`'s
  digital-gate setup (`outputs.py:2077-2088` and `1834-1846`), and its `enable`
  and `disable` (2119-2150) repeat `DDS`'s (1891-1922), testing `if self.gate:`
  where `DDS` tests `if self.gate is None`.
- **Step 4, dead code and compatibility leftovers.**
  - `labscript.py:108`, `config = compiler`, and 109, `no_warnings =
    suppress_all_warnings` ("Historical alias"). `no_warnings` is used in no
    repo, hyde included; `config` was not searched yet.
  - `labscript.py:28`, 710, 739 and 763: code marked
    `TO_DELETE:runmanager-batchompiler-agnostic`, globals loading kept for an
    old runmanager.
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
