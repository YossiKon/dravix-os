# m5ioe1 (vendored)

M5Stack's driver for the StackChan's IO expander and its 12-LED light bar, copied from
github.com/m5stack/esphome-yaml at commit `238ba9825e7874d5626709631dae6be92e861b17`
(MIT License, Copyright (c) 2025 m5stack; see LICENSE). M5Stack's own README.md is kept as is.

## Why vendored

ESPHome 2026.11 replaced `AddressableLight::get_view_internal()` with a colour accessor, so the
upstream light no longer compiles (`'get_view_internal' marked 'override', but does not
override`). Measured in this repo's CI on ESPHome 2026.11.1; there is no configuration-level fix.

## The patch

Every changed line is marked `// dravix:` (light/m5ioe1_light.h and .cpp). On ESPHome 2026.11+ the
light exposes its existing RGB888 buffer through `light::CorrectedBufferColorAccessor` (the same
pattern as ESPHome's `esp32_rmt_led_strip`); on older ESPHome it keeps the original
`get_view_internal()`. The hardware write path is unchanged.

## Re-sync

Copy upstream `components/m5ioe1` over this folder, re-apply the marked lines, commit, create a
new `components-vN` tag, and point `deploy/esphome/v2/components.yaml` at it.
