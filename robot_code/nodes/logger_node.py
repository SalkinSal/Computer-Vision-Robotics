"""
THIS NODE IS NOT YET FULLY IMPLEMENTED!
It is only included in the framework if logging is set to `True` in the main config,
at which point every time a node sends a command or publishes a message to a topic,
a logging-command is sent to the logger. However, at the moment, this has no effect.
"""
import time
import datetime
import traceback
import json

from nodes.node import Node
from utils.print_utils import print_locked as print


class LoggerNode(Node):
    def __init__(self, 
                 name:str, 
                 main_config:dict,
                 node_config:dict, # config specific to this node, needed for init
                 own_queue,
                 sys_queue,
                 topic_configs:dict, # configs of each topic the node is subscribed to, needed for init
                 all_nodes_config,  # node config file, committed to log
                 all_topics_config): # topic config file, committed to log

        super().__init__(name=name,
                         main_config=main_config,
                         node_config=node_config, 
                         sys_queue=sys_queue, 
                         own_queue=own_queue,
                         topic_configs=topic_configs)

        self.mc = main_config
        self.nc = all_nodes_config
        self.tc = all_topics_config
        # self.log_method = main_config["log"]["log_type"]
        # self.log_file = main_config["log"]["log_file"]

        self.log = self.init_log()


    # =====================================
    #     CORE LOGGING FUNCTIONS
    # =====================================
    def log_cmd(self, msg_dict):
        pass
        # add incoming command to log

    def log_topic(self, msg_dict):
        pass
        # read message from topic and add to log


    # =====================================
    #     LOG ADMIN FUNCTIONS
    # =====================================

    def init_log(self):
        log = {
            "date": datetime.datetime.now(),
            "main_config": self.mc,
            "node_config": self.nc,
            "topic_config":self.tc
        }
        return log

    # preiodically write the log to the designated file
    def dump_log(self):
        pass

    def save_log(self):
        pass