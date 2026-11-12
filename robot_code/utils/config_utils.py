"""
This module contains the Struct class used to turn dictionaries into objects that can be
addressed using simpler syntax, as well as functions for loading configs from yaml files
and sending them to the config parser. The actual parsing happens in utils/config_parser.py.

When running this file as __main__, the main() function calculates the memory size needed for
all topics in the current implementation.
"""

import os
import yaml
import traceback

try:
    from utils.config_parser import parse_configs
    from utils.print_utils import print_locked as print
except: # this module is being called from somwhere other than main.py
    from rich import print
    from config_parser import parse_configs
    from message_utils import calculate_memory_size
    print("[yellow][bold]Modified imports in config_utils!")

# NOTE JJ: This class is adapted from the Struct in the code from the "Introduction
# to Computer Vision and Robotics" class but strongly updated and extended to allow
# function as a dict as well as Struct.
class Struct(dict):
    """
    Wrapper class that allows dictionaries to be accessed using class syntax.
    
    E.g. for a config dict, you can call config.x instead of config["x"],
    though the latter also works. All other standard dictionary functions 
    (.keys(), .items(), etc.) are retained at the same time.
    (cf Documentation for more details.)

    "I made this because doing cfg['x'] all the time is dumb."
    [Comment retained from original code because it's funny XD]
    """
    def __init__(self, data:dict=None):
        """
        Recursively transforms all dicts inside data into Struct objects.

        Parameters
        ----------
        data: dict/None
            Dictionary that will be turned into Struct.
            Passing None creates a Struct with an empty internal dict.
            All dictionary keys must be strings to be used as class attributes.
        """
        # allow creating emtpy Struct by calling Struct() without args
        data = {} if data is None else data
        wrapped = {}
        # wrap all dictionary empties to turn nested dicts into Structs
        for k, v in data.items():
            wrapped[k] = self.wrap(v)

        # instantiate internal dict by calling dict.__init__() on wrapped data 
        super().__init__(wrapped)
        # set internal dict keys as class attributes
        for name in data.keys():
            setattr(self, name, self[name])


    def wrap(self, value):
        """
        Recursively turn every dict inside value into a Struct.

        Parameters
        ----------
        value: Any
            Single value or iterable to be parsed.
        
        Returns
        -------
        Any
            Value or iterable of original type with wrapped values inside,
            i.e. Struct if value is dict, value unchanged otherwise 
        """
        # if value is iterable, wrap every item inside individually
        if isinstance(value, (tuple, list, set, frozenset)):
            return type(value)([self.wrap(v) for v in value])
        # if value is Struct it's already fully parsed and can be returned as is
        elif isinstance(value, Struct):
            return value
        # if value is dict, turn it into a Struct. Otherwise return unchanged
        else:
            return Struct(value) if isinstance(value, dict) else value

    def __setattr__(self, name:str, value):
        """
        When setting an attribute, also add the new name and value to the 
        internal dict as a (key: value) pair.
        
        Parameters
        ----------
        name: str
            Attribute/dict key to be updated.
        value: Any
            New attribute/dict value.
        """
        # wrap new value recursively in Struct if applicable
        wrapped = self.wrap(value)
        # set/update class attribute
        super().__setattr__(name, wrapped)
        # add/update value in internal dict
        super().__setitem__(name, wrapped)

    def __setitem__(self, key:str, value):
        """
        When adding/updating a value in internal dict, also add/update
        the class attribute.

        Parameters
        ----------
        key: str
            Dictionary key/attribute name to be added/updated.
        value: Any
            New dict/attribute value.
        """
        # wrap new value recursively in Struct if applicable
        wrapped = self.wrap(value)
        # add/update value in internal dict
        super().__setitem__(key, wrapped)
        # set/update class attribute
        super().__setattr__(key, wrapped)

    def __delattr__(self, name:str):
        """
        Delete class attribute and also delete corresponding item from internal dict.
        
        Parameters
        ----------
        name: str
            Name of class attribute/dict key to be deleted.
        """
        # delete class attribute
        super().__delitem__(name)
        # delete item from internal dict
        super().__delattr__(name)

    def __delitem__(self, key:str):
        """
        Delete item from internal dict and also delete corresponding class attribute.
        Parameters
        ----------
        key: str
            Dict key/name of class attribute to be deleted.
        """
        # delete item from internal dict
        super().__delitem__(key)
        # delete class attribute
        super().__delattr__(key)




# ================================
#     LOAD CONFIGS
# ================================
def load_all_configs(main_path:str, path_mod:str="") -> Struct:
    """
    Load all configs from their respective yaml files, run them through the
    config parser, and return them collected in a single Struct object.

    The path for the main config is defined in main.py, the paths to all other configs
    are defined in the main config.

    Parameters
    ----------
    main_path: str
        The path to the main config (relative to main.py).
    path_mod: str
        Modifier to add to start of filepaths in case this module is called from somwhere other than main.py (default: "").

    Returns
    -------
    Struct/None
        A dictionary of all configs using their names as keys or 
        None if an error occurs during loading or parsing.
        If there are abbreviations listed for configs in the main_config
        (e.g. "tc" for "topic_config"), those are used as keys instead.
    """
    # load main config
    mc = load_config(filepath=path_mod+main_path)

    if mc is None: # error during parsing
        return None

    configs = {"mc": mc}

    # load all other configs
    cfs = mc.configs
    for name, data in cfs.items():
        # try to load config, return None if there is an error
        cf = load_config(path_mod+data.path)
        if cf is None:
            return None

        # use abbreviation if applicable
        if data.abbr is not None: 
            name = data.abbr
        
        # add config to dictionary
        configs[name] = cf

    # turn the configs dictionary into a struct as well
    configs = Struct(configs)

    # run the configs through the config parser
    success = parse_configs(configs)
    if not success: # there was an error during config parsing
        return None

    return configs


# This is a mix of my code and the old code

def load_config(filepath:str) -> Struct:
    """
    Load a single config from a yaml file and return it as a Struct.

    Parameters
    ----------
    filepath: str
        Path to the config file (modified by load_all_configs if needed).

    Returns
    -------
    Struct/None
        The config as a Struct or None if there was an error.
    """
    if os.path.isfile(filepath):
        with open(filepath, "r") as f:
            try:
                yaml_parsed = yaml.safe_load(f)

                return Struct(yaml_parsed)
            except yaml.YAMLError:
                print(f"[bold][red]Error parsing yaml file [white]'{filepath}'[/white]!")
                print("[bold][red]Traceback:")
                traceback.print_exc()
            except:
                print(f"[bold][red]Error while trying to load config [white]'{filepath}'[/white]!")
                print("[bold][red]Traceback:")                
                traceback.print_exc()
    
    else:
        print(f"[bold][red]Could not find file [white]'{filepath}'[/white]!")
        return None


# =====================================
#     MAIN
# =====================================
def main():
    """
    Check that all datatypes inside the topic config are valid and 
    give a read-out of each topic's size as well as the total size.
    """

    MAIN_PATH = "configs/main_config.yaml"
    from config_utils import load_all_configs

    configs = load_all_configs(
        main_path=MAIN_PATH,
        path_mod="../"
    )
    if configs is None: # error during loading or parsing
        return
    tc = configs.tc
    total_memory = 0

    for t, t_config in tc.topics.items():
        dtypes = t_config.dtypes
        t_size = calculate_memory_size(
            dtype_formats=dtypes.formats,
            bl=t_config.buffer_length)
        print(f"Topic [bold bright_blue]{t}[bold bright_blue] requires\t{t_size} Bytes")
        total_memory += t_size

    print(f"Total memory needed for topics: {total_memory} Bytes ({total_memory/10e5} MB)")


if __name__ == "__main__":
    main()
