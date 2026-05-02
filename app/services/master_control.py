from app.system.master.master_control import *


class MasterControlService(MasterControl):
    """Backward-compatible wrapper for older orchestration wiring."""

    def __init__(self, data_dir: str | None = None):
        super().__init__()
        self._data_dir = data_dir
