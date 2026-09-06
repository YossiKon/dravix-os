# scs9009 (vendored, patched)

Vendored from [m5stack/esphome-yaml](https://github.com/m5stack/esphome-yaml)
`components/scs9009` @ `238ba9825e7874d5626709631dae6be92e861b17` (MIT, see LICENSE — © 2025 m5stack), with one deliberate patch:
**the driver no longer blocks ESPHome's main loop.**

Why: on the StackChan the stock driver slept inside the main loop — `delay(200)` on every
position write plus `delay(travel_time + 100 ms)` before releasing the holding torque, and a
serial read that busy-waited up to 500 ms per missing byte. A head nod measured 1158 ms of
blocked loop on the robot, and the speaker's ISR queue overflowed right after every move; the
voice assistant's 512 ms microphone buffer dropped audio the same way ("Okay Nabu" heard
nothing). No configuration option fixes that.

What changed (every line is marked `// dravix:`):

- `ftservo/scs9009_servo.cpp`: no `delay(200)` after a position write; `release_torque_after()`
  is a `set_timeout` (the servo is a Component); one `ESP_LOGI` at setup so a boot log proves
  this driver is the one compiled in.
- `scs9009.cpp`: the per-byte serial read timeout is 50 ms instead of 500 ms (a real reply
  takes about a millisecond at 1 Mbps).


Re-sync procedure when taking a BSP update: copy the upstream folder over this one, re-apply
the `// dravix:` lines (a `git diff` against the previous vendored copy shows them all).
