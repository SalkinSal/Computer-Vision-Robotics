from multiprocessing import Queue

from nodes.node import Node
from utils.config_utils import Struct
from utils.print_utils import print_locked as print
from utils.menu import Mode

# Rename the class to fit the node's name and add the class name to the node config.
class Controller(Node):
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
        self.print_topic()
        self.print_numbers()

        pass
    def send_print_message(self, recipient, msg):
        self.send_to_queues(
            recipients="actuator",
            msg=("print_message", "Hello World")) # ("function name", args))

    def send_numbers(self,recipient,msg: list):
        self.send_to_queues(recipients="actuator",msg=("product_list", (msg,)))

    def print_topic(self):
        msgs = self.read_topic(topic_name="print_log", max_msgs=0, new_only=True)
        if msgs is None:
            return
        for msg in msgs:
            timestamp, mode, print_string, product = msg
            print(f"[LOG] {mode} | text: {print_string} | product: {product}")

    def print_numbers(self):
        msgs = self.read_topic(topic_name="number_log", max_msgs=0, new_only=True)
        if msgs is None:
            return
        for msg in msgs:
            timestamp, count, numbers, product = msg
            print(f"[NUMBERS] {numbers[:count]} -> product: {product}")
                
    # =====================================
    #     NODE FUNCTIONS
    # =====================================
    # Add any methods you want the node to be axble to perform here.
    # Check the documentation to see which methods 
    # are already implemented in the base Node class.