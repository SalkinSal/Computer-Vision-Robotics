"""
This package contains the classes of all nodes used for the framework. To get a dictionary
containing each class that extends `Node` (and `Node` itself), call `nodes.get_all_nodes()`.
"""

import pkgutil
import importlib
from pathlib import Path

from .node import Node # this needs to be hard-coded because we need the baseclass

def get_all_nodes():
    """
    Find all classes inside the package that extend the `Node` base class.

    Returns
    -------
    dict
        Dictionary of all classes that inherit from class `Node` (and class `Node` itself).
        Format: {"ClassName": executable object reference}
    """
    all_nodes = {}
    package_path = Path(__file__).parent
    # iterate over all modules (i.e. files) in the `nodes` package
    for importer, modname, ispkg in pkgutil.iter_modules([str(package_path)]):
        # import the module
        module = importlib.import_module(name=f".{modname}", package="nodes")
        # iterate over all items inside the module's dir() to identify the ones inheriting from Node
        for name in dir(module):
            # get a callable method rather than a string
            obj = getattr(module, name)
            if (isinstance(obj, type) # check if the object is a callable method
                and issubclass(obj, Node)): # also True for class Node itself
                if name not in all_nodes:
                    all_nodes[name] = obj
    return all_nodes