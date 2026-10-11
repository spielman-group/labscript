# labscript test contract

A planning document for step 1 of the code-health campaign
(`issues/code_health_campaign.md` in the meta repo). It lists what each existing
test protects, for Ian's review, and is deleted when the revisions it leads to
are done.

Marks:

- **keep**: protects a real behaviour, and fails when that behaviour breaks.
- **rename**: keep, under a name that states the behaviour.
- **fix**: the behaviour is real, but the test cannot fail when it breaks.
- **cut**: protects nothing on the list; the category is given.

"Step 2.1" would mark a test that guards behaviour no one asked for. None does:
every behaviour below is upstream labscript's, although upstream has no tests.

Each test was checked by breaking its behaviour by hand in a scratch copy of
labscript and running the suite. In every case only that test failed.

## Totals

- Test files: 1, plus `conftest.py`, which holds no tests.
- Tests: 3.
- Lines: 161 in `tests/`, against 5036 core lines in `labscript/`.
- Marks: keep 2, rename 1, fix 0, cut 0.

## tests/test_compile_shot.py

- `test_a_shot_using_markers_waits_and_a_shutter_compiles`: a shot with time
  markers, a wait and a shutter compiles to a shot file holding the connection
  table and its markers and waits, readable as strings. **rename** →
  `test_a_compiled_shot_file_holds_its_markers_and_waits`. The present name
  promises only that the shot compiles. Broke the marker labels: failed. Broke
  the wait labels: failed.
- `test_the_shot_knows_how_long_it_runs`: `stop(t)` records the shot's length on
  the master pseudoclock, which BLACS reads to know how long the shot runs.
  **keep**. Broke `stop` to record `t + 1`: failed.
- `test_an_instruction_inside_a_later_ramp_is_refused`: compiling refuses an
  instruction that lands inside any ramp on an output, not only the first.
  **keep**. Broke `get_change_times` to check only the first ramp: failed.
