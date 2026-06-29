# vendor/ — upstream tracking (reference only)

This directory tracks the original M5Stack StackChan project so dravix-os can always pull in
upstream changes **without ever modifying the robot's firmware**.

We treat upstream as **read-only reference**: face parameters, protocol details, asset names,
and behavior we may want to mirror in our own (separate) code. dravix-os never patches or
rebuilds the stock firmware — the robot updates through M5Stack's normal OTA/app channel.

## Add the upstream (run once)

```bash
make vendor-init
# == git submodule add https://github.com/m5stack/StackChan vendor/upstream
```

## Update later

```bash
make update-upstream
# == git submodule update --remote --merge vendor/upstream
```

Because our code lives *beside* upstream (not as patches on top of it), pulling new upstream
commits never produces merge conflicts with dravix-os.

> Note: `vendor/upstream/` is intentionally empty until you run `make vendor-init`.
