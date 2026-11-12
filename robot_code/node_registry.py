import time
import traceback
from multiprocessing import Queue

from utils.print_utils import print_locked as print
from utils.config_utils import Struct
from topic_registry import TopicRegistry
import nodes
from nodes import Node

class NodeRegistry:
    """
    The NodeRegistry instantiates all nodes and runs their admin on a meta-level.

    It uses the Context Manager pattern to ensure an orderly shut-down of all nodes
    if there is an error or the framework stops unexpectedly. To accomplish this,
    the Nodes and Queues are only instantiated in the enter() method, not at init().

    The registry sets up the system and command queues and keeps its own copy of each.
    That way, it can send commands to individual nodes, though at the moment 
    this is only used to send keypress-information to the MainNode.
    """

    # =====================================
    #     INIT & START
    # =====================================
    def __init__(self, t_reg:TopicRegistry, main_config:Struct, nodes_config:Struct):
        self.t_reg = t_reg
        self.main_config = main_config
        self.nodes_config = nodes_config

        self.nodes = {}

        self.main_queue = None # queue to send commands to main
        self.log_queue = None # queue to handle event logging across all nodes
        self.system_queues = {}
        self.own_queues = {}

    def __enter__(self):
        """
        When entering the context, instantiate all Queues and Nodes.

        Try to find the class specified for each node in the node config.
        If the class does not exist, give a warning and use the base Node class. 

        Returns
        -------
        NodeRegistry
            Reference to itself.
        """
        # create the system queues and standard queues for each node
        self.create_queues()

        # get a dictionary of all node classes from the nodes package
        all_classes = nodes.get_all_nodes()

        # create all nodes from the provided data
        for n_name, n_config in self.nodes_config["nodes"].items():
            # MainNode needs to be handled differently
            if n_name == 'main':
                node = all_classes['MainNode'](
                    name=n_name,
                    main_config=self.main_config,
                    node_config=n_config, 
                    own_queue=self.main_queue,
                    sys_queues=self.system_queues
                )
            elif n_name == 'logger':
                # only set up the logger node if logging is enabled in main config
                if self.main_config.log.logging == True:
                    # add all topics to the loger's subs list
                    n_config.topics.subs = [t for t in self.t_reg.topic_config.topics]

                    # instantiate logger 
                    node = all_classes['LoggerNode'](
                        name=n_name,
                        main_config=self.main_config,
                        node_config=n_config,
                        own_queue=self.log_queue,
                        sys_queue=self.system_queues[n_name],
                        topic_configs=self.create_topic_configs(n_name),
                        all_nodes_config=self.nodes_config,
                        all_topics_config=self.t_reg.topic_config
                    )
                else: 
                    # skip the end of the loop soo the logger is not added to the dictionary of all nodes
                    continue
            else:
                try:
                    # instantiate node using specified class
                    node = all_classes[n_config.class_name](
                        name=n_name,
                        main_config=self.main_config, 
                        node_config=n_config, 
                        own_queue=self.own_queues[n_name],
                        sys_queue=self.system_queues[n_name],
                        send_queues=self.set_send_queues(n_name),
                        topic_configs=self.create_topic_configs(n_name)
                        )
                except KeyError: # specified NodeClass does not exist
                    print(f"[bold][yellow]Node [blue]{n_name}[/blue] does not have an associated class name. Using standard [white]Node[/white] class instead!")
                    # instantiate base Node class instead and set dummy flag to True
                    n_config.is_dummy = True
                    node = nodes.Node(
                        name=n_name,
                        main_config=self.main_config, 
                        node_config=n_config, 
                        own_queue=self.own_queues[n_name],
                        sys_queue=self.system_queues[n_name],
                        send_queues=self.set_send_queues(n_name),
                        topic_configs=self.create_topic_configs(n_name)
                    )
                except:
                    print(f"[bold][red]Encountered error while trying to instantiate node [blue]{n_name}[/blue]!")
                    print("[bold][red]Traceback:")
                    traceback.print_exc()
                    print("[bold][yellow]Continuing to run framework.")

            self.nodes[n_name] = node
        return self

    def run_nodes(self):
        """
        Start all nodes.    
        """
        for node in self.nodes.values():
            node.start()
        time.sleep(0.2) # give nodes time to boot up
        print(f"[bold][green]Framework running!\nPress '{self.main_config.stop_key}' to exit.")



    # =====================================
    #     SETUP
    # =====================================
    # create the queues for each node 
    def create_queues(self):
        """
        Create system and command queues for each node and save the main
        and logging queues separately to give the registry acces to them.
        """

        # create queues and store them to dict of all queues
        for n in self.nodes_config.nodes.keys():
            # create system queues for every node except main
            if n != "main":
                self.system_queues[n] = Queue()
            self.own_queues[n] = Queue()

        # specially save the main and logging queues
        self.main_queue = self.own_queues["main"]
        self.log_queue = self.own_queues["logger"]

    def set_send_queues(self, node_name:str) -> dict:
        """
        Create a dictionary of send-queues for the specified node.
        
        If a node listed in the node config's list of queues was not included in the framework,
        the name of the node is added to the list of dummy queues in the node's config instead.
        
        Parameters
        ----------
        node_name:  str
            Name of the node in question.

        Returns
        -------
        dict
            Dictionary of send-queues (format: {"node_name": Queue})
        """
        queues = {}
        config = self.nodes_config.nodes[node_name]
        
        # every node (except Main itself) gets access to the main node's queue 
        queues["main"] = self.main_queue
        # only give the log queue if logging is enabled
        if self.main_config.log.logging == True:
            queues["logger"] = self.log_queue
        for q in config["queues"]:
            try:
                send_queue = self.own_queues[q]
                queues[q] = send_queue
            except KeyError: # node was not included
                print(f"[bold][yellow]Node [blue]{node_name}[/blue] cannot send commands to node [blue]{q}[/blue] since it was not included!")
                config.dummy_queues.append(q) # edited in place
        return queues

    def create_topic_configs(self, node_name:str) -> dict:
        """
        Create a nested dictionary that contains the topic-configs of each
        topic the given node publishes to or is subscribed to.

        Parameters
        ----------
        node_name:  str
            Name of the node in question.

        Returns
        -------
        dict
            Dictionary containing two dictionaries: 'pubs' and 'subs'.
            These contain the configs for topics using format {topic_name(str): config(dict/Struct)}.
        """
        t_dict = {'pubs': {}, 'subs': {}}

        n_topics = self.nodes_config["nodes"][node_name]["topics"]
        for t in n_topics.pubs:
            t_dict['pubs'][t] = self.t_reg.get_topic_config(t)
        for t in n_topics.subs:
            t_dict['subs'][t] = self.t_reg.get_topic_config(t)
        return t_dict
        

    # =====================================
    #     SHUT-DOWN
    # =====================================
    def __exit__(self, exc_type, exc, tb):
        """
        Shut down all nodes once stop key was pressed or after an error occurred,
        and release their associated resources.
    
        Nodes that failed to shut down orderly are terminated.

        Parameters
        ----------
        Default parameters for __exit__ method
        """
        self.main_queue.put(("stop_all", None))
        time.sleep(0.5) # give the nodes time to shut down

        # check if each node is shut down and terminate if not
        for name, node in self.nodes.items():
            if not node.is_alive(): # node already shut down
                continue
            node.stop_node() # if the shut-down was triggered by the stop key, this will have no effect

            # wait for node to finish running
            node.join(timeout=1.0)

            # if orderly shut-down failed, terminate node
            if node.is_alive():
                print(f"[bold][red]Node [blue]{name}[/blue] failed to shut down! Terminating process.")
                node.terminate()
                node.join()
                # NOTE: this *can* fail, but in that case, I would prefer the user call a keyboard interrupt rather than leaving the node running in

            # release resources associated with process object
            node.close()

    # =====================================
    #     AUXILIARY METHODS
    # =====================================
    def send_keypress(self, key:str):
        """
        Pass along keypress to the main node.

        Parameters
        ----------
        key: str
            Key that was pressed.
        """
        self.main_queue.put(("parse_keypress", (key)))

    def __str__(self):
        return f"NodeRegistry (Nodes: {[n for n in self.nodes.keys()]})"

    def __repr__(self):
        return f"NodeRegistry (Nodes: {[n for n in self.nodes.keys()]})"