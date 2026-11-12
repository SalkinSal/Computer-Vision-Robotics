"""
The Menu class stores information about commands that can be triggered 
by key presses. It is instantiated and administered by the main node,
which receives the key presses from Main.

The Mode enum defines the different modes available to the system 
and sets their integer values.

For each mode, there is a dictionary of key presses and the commands
those key presses trigger.


Some keys are reserved, meaning they cannot be used in any 
of the mode-specific key press dictionaries. 
These keys are mostly used for switching modes or other meta-functions.
NOTE: The stop key (default: 'x') is defined in the main config, since it is needed
    in other places as well!
During init, the Menu ensures that no mode dicts use any keys from the reserved dict.

Key Dict Format: 
{
    "key": ("recipient", "method_name", args)
}

- key (str): the key that triggers the command.
- recipient (str or list of str): name(s) of target node(s) or "all".
    (The tuples are returned to the main node and sent on to other nodes from there.)
- method_name (str): name of the method.
- args (single element, tuple, or None): the arguments for the function call.
    If the function requires no arguments, put None.
    Single elements are automatically converted into tuples.
    If the method takes a tuple or list as its only arg, this needs to be wrapped in another tuple (cf. documentation).

"""

from enum import Enum
import traceback

from utils.print_utils import print_locked as print
from utils.config_utils import Struct

class Mode(Enum):
    IDLE = 0
    MANUAL = 1
    # add your own modes here

class Menu:
    def __init__(self, main_config:Struct):
        """
        Set up the menu's mode and the key dictionaries for each mode.
        The default starting mode is IDLE.

        Parameters
        ----------
        main_config:    Struct
            The framework's main config, needed to determine stop key. 
        """
        self.mode = Mode.IDLE
        self.last_mode = None
        stop_key = main_config.stop_key

        # ================================
        # RESERVED KEYS
        # ================================
        # E.g. for mode switching.
        # These must not be used in mode dictionaries!
        self.reserved = {
            stop_key: ("main", "stop_all", None), # Default: 'x', can be changed in main_config
            "q": ("main", "switch_mode", (0,)), # switch to idle mode
            "m": ("main", "switch_mode", (1,)), # switch to manual mode

        }

        # ================================
        #     KEYPRESS DICTIONARIES
        # ================================
        # Dictionary names must be lower-case version of modes in Mode-Enum!
        # Add your own methods and/or dictionaries below.

        self.idle = {
            
        }

        self.manual = {
            'w': ("robot_controller", "set_move", ('w',)),
            'a': ("robot_controller", "set_move", ('a',)),
            's': ("robot_controller", "set_move", ('s',)),
            'd': ("robot_controller", "set_move", ('d',)),
            'c': ("robot_controller", "stop", None),
        }

        # ================================

        self.check_reserved_keys()


    # ================================
    #     ADMIN METHODS
    # ================================
    def check_reserved_keys(self):
        """
        Ensure that no reserved keys are used in any of the mode dictionaries.
        """
        # run through each mode that has an associated mode dictionary
        for mode in Mode:
            try:
                mode_dict = getattr(self, mode.name.lower())
            except:
                #  give a warning if no key dictionary exists for a mode but continue
                print(f"[bold][yellow][white]Menu[/white] class has no key dictionary for mode [white]'{mode.name}'[/white].")
                continue

            # if a key in any dict is reserved, raise an exception
            for k in mode_dict:
                if k in self.reserved:
                    print(f"[bold][red]Key [white]'{k}'[/white] is reserved and cannot be used in key-dict [white]'self.{mode.name.lower()}'[/white]!")
                    raise Exception

        

    # depending on current mode, return the desired command and recipient node
    def parse_keypress(self, key:str) -> tuple:
        """
        Return a command and recipient node based on 
        the current mode and the pressed key.

        If the args specified in the key dict are a single value, 
        this is automatically wrapped in a tuple.
        If the args are a single value in the form of a list or tuple,
        they need to be wrapped in a tuple (with a comma before the closing paranthesis!). 

        Parameters
        ----------
        key: str
            The key that was pressed.
        
        Returns
        -------
        3-tuple or None
            rec (list or string):   Recipient(s).
            func (str):             Name of the function.
            args (tuple or None):   Parameter(s) for the function.
        """
        # select keypress dictionary based on current mode
        key_dict = getattr(self, self.mode.name.lower())
        
        if key in key_dict:
            ret = key_dict[key]
        elif key in self.reserved:
            ret= self.reserved[key]
        else:
            return None

        try:
            rec, func, args = ret
        except:
            print(f"[bold]{ret}[red] is not a valid keypress command! [/red][/bold]"
                  + f"({self.mode}, key: '{key}')")
            return
        # convert args to tuple if necessary
        if not isinstance(args, tuple):
            args = None if args is None else (args,)

        ret = (rec, func, args)
        return ret


    # ================================
    #     AUXILIARY METHODS
    # ================================ 
    def switch_mode(self, new_mode:int) -> bool:
        """
        Switch the menu to a new mode and preserve information about the previous mode.
        This method gets called by the main node.

        Parameters
        ----------
        new_mode:   int
            Numerical value of new Mode.

        Returns
        -------
        bool
            True if switch to new mode was sucessful, else False.
        """
        # assert that new_mode is int:
        if not isinstance(new_mode, int):
            print(f"[bold][red]Cannot switch mode, [white]new_mode[/white] needs to be int not [/red]{new_mode}[red]!")
            return
        if new_mode not in Mode:
            print(f"[bold][red]Cannot switch to mode with value [white]{new_mode}[/white]!")
            print("[bold]Currently implemented:")
            for m in Mode:
                print(f"{m}: {m.value}")
            return False
        self.last_mode = self.mode
        self.mode = Mode(new_mode)
        return True

    def __str__(self):
        return f"Menu (Mode: {self.mode})"

    def __repr__(self):
        return f"Menu (Modes: {[m for m in Mode]})"