# Known issues

- `outputs.py`, `Output.expand_timeseries`: ramp values are evaluated at sample times that are differences of absolute float times, so compiled values carry float noise in their last bit, in either direction; counting each sample's time within the ramp in whole clock ticks would make them exact.
