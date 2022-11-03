from enum import Enum

class CloudRunError(Exception):
    pass


class CloudRunCommandState(Enum):
    UNKNOWN   = 0
    IDLE      = 1
    RUNNING   = 2
    DONE      = 3
    ABORTED_Q = 4
    ABORTED   = 5
