"""dravix-os — companion OS layer for the M5Stack StackChan robot."""

import os

# The running build version. The container/CI bakes DRAVIX_VERSION (= the add-on
# version) into the image so the dashboard badge reflects what's actually running;
# falls back to a dev marker for local/source runs.
__version__ = os.getenv("DRAVIX_VERSION") or "dev"
