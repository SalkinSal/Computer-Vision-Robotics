from multiprocessing import Queue

from nodes.node import Node
from utils.config_utils import Struct
from utils.print_utils import print_locked as print
from utils.menu import Mode

# Rename the class to fit the node's name and add the class name to the node config.
class TemplateNode(Node):
    def __init__(self, 
                 name:str, 
                 main_config:Struct,
                 node_config:Struct, 
                 own_queue:Queue,
                 sys_queue:Queue, 
                 send_queues:dict,
                 topic_configs:dict):

        super().__init__(name=name,
                         main_config=main_config,
                         node_config=node_config, 
                         sys_queue=sys_queue, 
                         own_queue=own_queue, 
                         send_queues=send_queues,
                         topic_configs=topic_configs)

    # ------
    # Any init-functionality beyond the base node goes here
    # ------

    # =====================================
    #     RUN STEP
    # =====================================
    def run_step(self):
        """
        This function is called once per run-loop interval.
        Any logic the node should execute once durcing every loop iteration goes here.
        """
        pass

    # =====================================
    #     NODE FUNCTIONS
    # =====================================
    # Add any methods you want the node to be able to perform here.
    # Check the documentation to see which methods 
    # are already implemented in the base Node class.