"""
This module contains a wrapper method that handles printing in a 
multiprocessing environment without running into BlockingIOExceptions.
All files across the framework overwrite the standard `print()` with print_locked.

The docstring for print_locked() is adapted from the docstring for rich.print()
"""
from typing import Any, Optional, IO
from rich import print as rich_print

# ================================
#     PRINTING
# ================================
print_lock = None

def configure_printing(lock):
    """
    Set the print_lock for a process.

    This method needs to be called once for every process (i.e. once in the main process
    and once by each Node.) The lock is instantiated in the main config as the framework
    starts and is the same across all processes.

    Parameters
    ----------
    lock: multiprocessing.Lock
        The print_lock shared across all processes.
    """
    global print_lock
    print_lock = lock

def print_locked(
    *objects: Any,
    sep: str = " ",
    end: str = "\n",
    file: Optional[IO[str]] = None,
    flush: bool = False,       
):
    """
    Print object(s) supplied via positional arguments without causing blocking errors.
    This function has an identical signature to rich.print and the built-in print
    and calls rich.print in the background.

    Parameters
    ----------
    sep: str 
        Separator between printed objects. Defaults to " ".
    end: str
        Character to write at end of output. Defaults to "\n".
    file: IO[str]
        File to write to, or None for stdout. Defaults to None.
    flush: bool
        Has no effect as Rich always flushes output. Defaults to False.
    """
    if print_lock is None:
        # attempt to print anyway. Might cause BlockingIOError!
        rich_print(
            *objects, 
            sep=sep,
            end=end,
            file=file,
            flush=flush
        )
        return

    with print_lock:
        rich_print(
            *objects, 
            sep=sep,
            end=end,
            file=file,
            flush=flush
        )