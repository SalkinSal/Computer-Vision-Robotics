from multiprocessing import Queue

from nodes.node import Node
from utils.config_utils import Struct
from utils.print_utils import print_locked as print
from utils.menu import Mode
import numpy as np

# Rename the class to fit the node's name and add the class name to the node config.
class Actuator(Node):
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
        if self.count % 10 == 0:
            self.sent_topic(f"auto {self.count}", 0)
        pass

    def sent_topic(self, msg_string, msg_product):
        print("sent_topic:", self.mode, msg_string, msg_product)
        ergebnis = self.publish_to_topic(
        topic_name="print_log",
        msg=(self.mode.name, msg_string, msg_product)
        )
        print("publish Ergebnis:", ergebnis)

    def print_message(self, msg):
        self.sent_topic(msg,0)
        print(msg)

        
    def product_list(self, liste: list):
        z = np.prod(liste)
        print(z)
        self.sent_topic("", z)
        self.publish_to_topic(topic_name="number_log",msg=(len(liste), liste, z),pad_arrays=True)

    # =====================================
    #     NODE FUNCTIONS
    # =====================================
    # Add any methods you want the node to be able to perform here.
    # Check the documentation to see which methods 
    # are already implemented in the base Node class.S