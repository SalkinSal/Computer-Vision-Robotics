"""
This module contains functionality to check the formatting and validity of message configs
and of the messages being published to a topic. It also has the functions for formatting and
padding multidimensional messages.
"""

import traceback
import numpy as np
from math import prod

try:
    from utils.print_utils import print_locked as print
except:
    from rich import print
    print("[bold][yellow]Modified imports in message_utils!")

# =====================================
#     SETUP METHODS
# =====================================
def check_msg_fmt(t_name:str, dtypes) -> bool:
    """
    Check whether a topic's message dtypes are formatted correctly, specifically:
        - the number of field names and field formats is the same.
        - each message field has a valid numpy datatype.
        - the format for multidimensional fields is valid.

    Parameters
    ----------
    t_name: str
        Name of the topic
    dtypes: Struct or dict
        Struct containing the names and numpy dtypes of each message field as defined in the topic_config.
    
    Returns
    -------
    bool
        True if config format is correct, else False.
    """
    # assert same number of names and formats
    if len(dtypes.names) != len(dtypes.formats):
        print(f"[bold][red]Number of names and formats for message fields in topic [bright_blue]{t_name}[/bright_blue] does not match!")
        return False

    # check if all message formats are valid
    for f_name, f_fmt in zip(dtypes.names, dtypes.formats):
        # account for multidimensional fields
        if isinstance(f_fmt, (list, tuple)):
            # check that format has two elemetns, dtype and dimensions
            if len(f_fmt) != 2:
                print(f"[bold][red]The dtype config for multidimensional message field [white]'{f_name}'[/white] "
                      + f"in topic [bright_blue]{t_name}[/bright_blue] is formatted incorrectly!")
                return False
            # check formating for multidimensional message fields
            # unpack the tuple into the np dtype and the field size 
            f_fmt, _ = f_fmt
        try:
            _ = np.dtype(f_fmt)
        except:
            print(f"[bold][red]Unsupported dtype string [white]'{f_fmt}'[/white] for field "
                  + f"[white]'{f_name}'[/white] in topic [bright_blue]{t_name}[/bright_blue].")
            return False

    # no errors found
    return True


def calculate_memory_size(dtype_formats:list, bl:int) -> int:
    """
    Calculate the memory requirements for a topic's ring buffer.

    Parameters
    ----------
    dtype_formats: list
        List of numpy data type formats as provided by the topic config.
    bl: int
        The topic's buffer length.
    
    Returns
    -------
    int
        Number of bytes required for the topic's ring buffer.
    """
    length = bl + 1 # +1 to account for head
    
    size = 0
    # multiply number of bytes per data type with length of buffer +1
    for t in dtype_formats:
        # check if it's a tuple/list, i.e. multidimensional array
        if isinstance(t, tuple):
            dt, dims = t
            add_size = prod(dims) * np.dtype(dt).itemsize * length 
        else:
            add_size = np.dtype(t).itemsize * length
        size += add_size
    return size



# =====================================
#     MESSAGE-CHECKING & PADDING
# =====================================
def format_message(
        t_name:str,
        timestamp:int,
        message,
        dtypes,
        pad_arrays:bool=False,
        casting:bool=True) -> tuple:
    """
    Assert that a given message conforms to dtypes in topic config and 
    pad multi-dimensional message-fields where needed.
    
    Parameters
    ----------
    t_name: str
        Name of the topic the message is being published to.
    timestamp: int
        Message timestamp (default: time.time_ns()).
    message: tuple/list/np.ndarray
        The message to be published.
    dtypes: Struct
        The message data types from the topic config parsed as a Struct object.
    pad_arrays: bool
        Whether to pad multi-dimensional message fields with less entries than the defined maximum (default=False).
    casting: bool
        Whether to allow safe numpy casting (e.g. int -> float, bool-> int), default= True.

    Returns
    -------
    tuple/None
        The formatted message or None if there was an error. 
    """
    # assert that message is ndarray, list or tuple
    if isinstance(message, (tuple, list)):
        # turn message into simpe list so we can insert timestamp
        message = list(message)
    else:
        error_msg = f"Message must be a list or tuple!"
        print_error_message(t_name, error_msg, message)
        return None

    # add timestamp to the start of the message
    message.insert(0, timestamp)

    # check that message has enough fields
    if len(message) != len(dtypes.names):
        error_msg= f"Message has [white]{len(message)}[/white] elements instead of [white]{len(dtypes.names)}[/white]!"
        print_error_message(t_name, error_msg, message)
        return None
    
    # check if message fields can be safely cast into required dtypes
    zip_msg = zip(dtypes.names, dtypes.formats, message)
    for i, (f_name, f_fmt, f_value) in enumerate(zip_msg):
        # multi-dimensional fields need to be checked separately
        if isinstance(f_fmt, tuple):
            formatted = format_nd_field(
                t_name=t_name,
                f_name=f_name,
                f_fmt=f_fmt,
                value=f_value,
                pad_arrays=pad_arrays,
                casting=casting,
                msg=message)
            if formatted is None:
                # error during fromatting
                return None
            message[i] = formatted

        else:
            if not check_dtype(
                t_name=t_name,
                f_name=f_name,
                f_fmt=f_fmt,
                value=f_value,
                casting=casting,
                msg=message
                ):
                # data type of message field is incorrect
                return None
    return tuple(message) # needs to be tuple to insert into buffer

def format_nd_field(
        t_name:str,
        f_name:str,
        f_fmt:tuple,
        value,
        pad_arrays:bool=False,
        casting:bool=True,
        msg:list=None
        ) -> np.ndarray:
    """
    Check format of a multi-dimensional message field and add padding if needed.

    It is the responsibility of the programmer to ensure that all elements of a
    multi-dimensional message field are of the same data type.
    We currently use empty padding for arrays that are shorter than the defined field size.
    This method assumes that the config-check was run when initializing the framework,
    i.e. before trying to publish any messages. It does not check whether the fied format
    provided in the config is valid. 
    

    Parameters
    ----------
    t_name:     str
        Name of the topic the message is being published to.
    f_name:     str
        Name of the message field.
    f_fmt:      tuple
        The format of the message field as defined in the topic config.
    value:      tuple/list/np.ndarray
        Value of the message field to be checked.
    pad_arrays: bool
        Whether to pad multi-dimensional message fields with less entries than the defined maximum (default=False).
    casting: bool
        Whether to allow safe numpy casting (e.g. int -> float, bool-> int), default= True.
    msg:    list
        The message to be published (included for error printing).

    Returns
    -------
    Optional(np.ndarray):
        Array in the shape needed for the message field or None if there was an error.
    """
    np_type, field_shape = f_fmt

    # if casting is disabled, check that the dtype matches the defined type
    if not casting:
        field_array = np.asarray(value) # casts values to broadest element included (cf. documentation)
        if not check_dtype(
            t_name=t_name,
            f_name=f_name, 
            f_fmt=np_type,
            value= field_array.flat[0], # representative element from array
            casting=casting,
            msg=msg
        ):
            return None

    # if casting, try to turn the message field into a np-array of given dtype
    else:
        try:
            field_array = np.asarray(value, dtype=np_type)
        except:
            error_msg = f"[bold][red]Could not convert field [white]'{f_name}'[/white] into np.ndarray of dtype [white]'{np_type}'[/white]."
            print_error_message(t_name, error_msg, msg)
            print("[bold][red]Traceback:")
            traceback.print_exc()
            print("[yellow][bold]Continuing to run framework.")
            return None

    # check the array shape
    msg_shape = field_array.shape
    if msg_shape == field_shape:
        # message field is already of the correct shape -> return as 
        return field_array

    # check that number of dimensions correct
    if len(msg_shape) != len(field_shape):
        error_msg = (f"[bold][red]Field [white]'{f_name}'[/white] has [white]{len(msg_shape)}[/white] "
            + f"dimensions instead of [white]{len(field_shape)}[/white]!")
        print_error_message(t_name, error_msg, msg)
        return None
    
    
    # Iterate over all dimensions. If one dimension has too many elements 
    # (or too few and pad_arrays=False), abort and return None.
    # Otherwise, add a tuple to the list of padding-widths with fmt: (pad-before (always 0), pad-after)
    pad_width = [] 
    for dim_index, (msg_dim, field_dim) in enumerate(zip(msg_shape, field_shape)):
        if msg_dim > field_dim: # too many entries
            error_msg = (f"[bold][red]Dimension [white]{dim_index}[/white] of field [white]'{f_name}'[/white] "
                    + f"has too many elements ([white]{msg_dim}[/white], max is [white]{field_dim}[/white]).")
            print_error_message(t_name, error_msg, msg)
            return None
        elif msg_dim < field_dim and not pad_arrays: # too few entries, padding=False
            error_msg = (f"[bold][red]Dimension [white]{dim_index}[/white] of field [white]'{f_name}'[/white] "
                         + f"has too few elements ([white]{msg_dim}[/white] instead of [white]{field_dim}[/white]) "
                         + "and padding is disabled.")
            print_error_message(t_name, error_msg, msg)
            return None
        # else: number of entries correct, or too low but padding is enabled
        pad_width.append((0, field_dim - msg_dim))

    # pad the array to desired shape on each axis
    padded_array = np.pad(field_array, pad_width, mode="empty")

    return padded_array

def check_dtype(t_name:str, f_name:str, f_fmt:str, value, casting:bool=True, msg=None) -> bool:
    """
    Check whether the datatype of a value provided for a message field 
    matches the data type set for that field in the topic config.

    This method handles both standard Python types and numpy.dtypes.
    This method assumes that the config-check was run when initializing
    the framework, i.e. before trying to publish any messages, so it 
    does not check whether the dtype provided in the config is valid. 

    Parameters
    ----------
    t_name:     str
        Name of the topic the message is being published to.
    f_name:     str
        Name of the message field.
    f_fmt:      str
        The data type of the message field as defined in the topic config.
    value:      int/float/bool/str
        Value of the message field to be checked.
    casting:    bool
        Whether to allow safe numpy casting (e.g. int -> float, bool-> int), default= True.
    msg:        list
        The message to be published (included for error printing).

    Returns
    -------
    bool
        Whether the format was correct or not.
    """
    correct = True
    expected = np.dtype(f_fmt)

    if expected.kind in "iu": # integer or unsigned integer
        dtypes = (int, np.integer)
        if casting:
            # bool can safely be cast to int
            dtypes += (bool, np.bool_)
        if not isinstance(value, dtypes):
            correct = False

    elif expected.kind == "f": # float
        dtypes = (float, np.floating)
        if casting:
            # bool and int can safely be cast to float
            dtypes += (int, np.integer, bool, np.bool_)
        if not isinstance(value, dtypes):
            correct = False

    elif expected.kind == "b": # boolean
        if isinstance(value, (bool, np.bool_)):
            pass # correct
        elif casting and isinstance(value, (int, np.integer)):
            # make sure numerical value can be cast as boolean
            if not (value == 0 or value == 1):
                correct=False
        else: # not bool or a number that can be cast to bool
            correct = False

    elif expected.kind == "U": # Unicode string
        # get maximum permitted length of the string
        max_len = np.dtype(f_fmt).itemsize // 4 # 1 Unicode char = 4 Bytes 
        if not isinstance(value, str):
            # we are not allowing casting of numbers to strings
            correct = False
        elif len(value) > max_len:
            error_msg = f"The string in field [white]'{f_name}'[/white] must not be longer than [white]{max_len}[/white] characters!"
            print_error_message(t_name, error_msg, msg)
            return False

    if not correct:
        error_msg= f"Field [white]'{f_name}'[/white] should be of type [white]'{f_fmt}'[/white]!"
        print_error_message(t_name, error_msg, msg)
    
    return correct

# =====================================
#     AUXILIARY METHODS
# =====================================
def print_error_message(t_name:str, error_msg:str, orig_msg=None):
    """
    Print error message if something went wrong during formatting a message.

    Parameters
    ----------
    t_name:     str
        Name of the topic.
    error_msg:  str
        Error messsage.
    orig_msg:   tuple/list/np.ndarray
        The original message.
    """
    print(f"[bold][red]Could not publish message to topic [bright_blue]{t_name}[/bright_blue]! " + error_msg)
    if orig_msg is not None:
        print("[bold][red]Original message:")
        print(orig_msg)
    print("[bold][yellow]Continuing to run framework.")

