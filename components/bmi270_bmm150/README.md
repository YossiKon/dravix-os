# bmi270_bmm150 (vendored)

ESPHome driver for the Bosch BMI270 IMU (+BMM150 magnetometer over its AUX interface) —
the accelerometer inside the M5Stack CoreS3. Powers dravix-os's **shake → dizzy** reaction.

Vendored from [DennisGaida/m5stack-atoms3r-components](https://github.com/DennisGaida/m5stack-atoms3r-components)
@ `7829279a1450827a4c32fa0a8c67e14062bfc5ff` (MIT, see LICENSE — © 2025 dennis), with one
compatibility patch: ESPHome 2026.6 removed the trailing `stop` argument from
`I2CDevice::read_register` / `write_register`, so the five 4-argument call sites were
reduced to the 3-argument form (`stop=true` was their behavior, which is what the new
API does). Call sites are marked with `// dravix:` comments.

Why vendored rather than referenced: upstream targets an older ESPHome and no longer
compiles against the pinned toolchain; keeping the patched copy in-repo makes robot
builds reproducible.

**2026-11-27 (tag `components-v4`):** `write_register_()` logged the I2C error code (an int) with
`%s`. Harmless while the bus works, but on the first failed write (a stuck bus) the logger read the
code as a string pointer and the robot crashed in a boot loop. It is printed with `%d` now.
