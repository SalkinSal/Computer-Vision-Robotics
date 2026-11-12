import time
import traceback
import queue
from multiprocessing import Process, Queue
from multiprocessing.shared_memory import SharedMemory
import numpy as np
from typing import Literal

from topic import Topic, TopType
from utils.menu import Mode
from utils.config_utils import Struct
from utils.print_utils import print_locked as print, configure_printing


class Node(Process):
    # =====================================
    #     SETUP
    # =====================================
    def __init__(self, 
                 name:str,
                 main_config:Struct,
                 node_config:Struct, 
                 own_queue:Queue=None, 
                 sys_queue:Queue=None, 
                 send_queues:dict=None,
                 topic_configs:dict=None):
        
        # run Process.__init__()
        super().__init__() 
        
        self.name = name
        self.config = node_config

        self.mode = Mode.IDLE
        self.last_mode = None

        # timekeeping
        self.dt = main_config.dt
        self.dt_warnings = True
        self.dt_buffer = main_config.dt_buffer * self.dt # convert fraction into seconds
        self.start_time = None
        self.next_step = None

        # set up multiprocessing-safe printing
        self.print_lock = main_config.print_lock
        configure_printing(self.print_lock)

        # Set up queues
        self.sys_queue = sys_queue # system queue (receives commands from MainNode)
        self.queue = own_queue # queue through which commands are sent to this node
        self.send_queues = send_queues # queues this node can send commands to
        self.dummy_queues = node_config.dummy_queues # list of queues whose nodes weren't included

        # Settings for queue admin
        self.queue_threshold = main_config.queue_threshold # queue size after which there will be a warning
        self.max_queue_msgs = main_config.max_queue_msgs # number of messages retrieved from command queue by default
        self.is_dummy = self.config.is_dummy
        self.dummy_print = True # print commands received if this node was instantiated as a dummy

        # Instantiate topics if the node publishes/subscribes to any
        self.pubs, self.subs = self.topic_init(topic_configs=topic_configs)

        # General flags
        self.logging = main_config.log.logging
        self.running = False
        self.count = 0

        print(f"Node [bold blue]{self.name}[/bold blue] initialized.")

   
    
    # =====================================
    #     RUN LOOP
    # =====================================
    def run(self):
        """
        Main run loop of the node.

        The method sets self.running to True then enters the run loop.
        For each iteration, the run loop...
            - calculates the end of this iteration's desired interval (DT)
            - checks the node's system queue and executes all commands found there
            - checks the node's command queue and executes a set number of commands found there (default: 1)
            - executes the run_step method
            - checks how long the loop took for the iteration
                - if it took less time than DT, the node sleeps (non-busy wait) until DT threshold is reached
                - if it took longer, the node gives a warning (can be turned off)
        
        Once self.running was set to False, the method exits the run-loop and initiates an orderly shut-down.
        """
        self.running = True
        print(f"Node [bold blue]{self.name}[/bold blue] running.")

        self.start_time = time.monotonic()
        self.next_step = self.start_time
        
        while self.running:
            # set deadline for this loop iteration
            self.next_step += self.dt

            # check system queue and run all commands inside
            self.check_queue(threshold=self.queue_threshold, max_msgs=0, sys_q=True)
            # check command queue and execute commands up to the maximum number
            self.check_queue(threshold=self.queue_threshold, max_msgs=self.max_queue_msgs)

            # execute the node's normal run-logic
            self.run_step()
            
            # calculate time remaining in loop iteration
            dt_rest = self.next_step - time.monotonic()
            if dt_rest < 0: # Loop took longer than DT
                if self.dt_warnings and abs(dt_rest) > self.dt_buffer:
                    print(f"[bold][yellow]Node [blue]{self.name}[/blue][yellow] exceded DT by [white]{-dt_rest:.4f}[/white] seconds!")
                # skip to first deadline that has not passed yet
                while dt_rest < 0:
                    self.next_step += self.dt
                    dt_rest = self.next_step - time.monotonic()
                    # increment count to keep it more or less synced across the framework
                    self.count += 1 
            # pause process until the deadline for the next iteration is reached
            time.sleep(dt_rest)
            self.count += 1

        # orderly shut down once 'self.running' was set to false
        self.shut_down()

    # =====================================
    #     RUN STEP
    # =====================================
    def run_step(self):
        """
        This function is called once per run-loop.
        Any logic the node should execute once durcing every loop iteration goes here.
        """
        pass

    # =====================================
    #     QUEUES
    # =====================================
    def check_queue(self, threshold:int, max_msgs:int, sys_q:bool=False, flush:bool=False):
        """
        Retrieve messages from the node's system or command queue 
        and run the received commands.

        Parameters
        ----------
        threshold:  int
                    Approximate size the queue can reach before the method prints a warning (0 to omit all warnings).
        max_msgs:   int
                    How many messages should be retrieved at most. max=0 retrieves every message in the queue.        
        sys_q:      bool
                    Whether to check the node's system queue instead of the command queue.
        flush:      bool
                    If True will discard any retrieved messages rather than execute them.
        
        Returns
        -------
        None
        """
        msg_count = 0
        # set which queue should be checked
        if sys_q:
            target_queue = self.sys_queue
        else:
            target_queue = self.queue

        while True:
            try:
                msg = target_queue.get_nowait()
                # if there is nothing in the queue, the method exits here!
            except queue.Empty:
                return
            except Exception:
                print(f"[bold][red]Node [blue]{self.name}[/blue] encountered an error "
                    + f"while checking its {"system" if sys_q else "command"} queue!")
                print("[bold][red]Traceback:")
                traceback.print_exc()
                print("[bold][yellow]Continuing to run framework.")
                return
            msg_count +=1

            # give a warning if the queue's approximate size exceeds the threshold
            qsize = target_queue.qsize()
            if threshold and qsize > threshold:
                print(f"[bold][yellow]Node [blue]{self.name}[/blue] has [white]{qsize}[/white] " + 
                    f"elements in its {"system" if sys_q else "command"} queue!")
            
            if not flush:
                # execute the command sent to the queue (unless you're flushing the queue)
                self.parse_command(msg)

            # check if maximum number of messages was retrieved
            if max_msgs != 0 and msg_count >= max_msgs:
                return

    def send_to_queues(self, recipients, msg:tuple, log_msg:bool=True):
        """
        Send message to recipients' queues.

        This method checks the message being sent to make sure the arguments of the 
        function given are either None or wrapped in a tuple. If sending a tuple as
        the sole argument, it needs to be wrapped in an additional tuple!
        
        If logging is enabled, every sent message is logged.

        Parameters
        ----------
        recipients: list or string
                    Name of a single recipient nodes, a list of recipient names, or "all".
        msg:        tuple
                    Message with format ('method_name', args) where args are None or a tuple of args.
        log_msg:    bool
                    True except when sending `log` command to logger (to avoid recursive logging).
        """
        # log the message if logging is enabled and this isn't a logging command
        if self.logging and log_msg:
            self.log(is_topic=False, timestamp=time.time_ns(), rec=recipients, content=msg)

        # wrap single recipient in list for uniform handling
        if not isinstance(recipients, list):            
            if recipients == "all":
                recipients = list(self.send_queues.keys())
            else:
                recipients = [recipients]

        # assert that the argument given for the message is None or a tuple
        cmd, args = msg
        if not isinstance(args, tuple) and args is not None:
            # wrap args in a tuple
            msg = (cmd, (args,))

        # assert that valid recipients given
        for rec in recipients:
            if rec in self.send_queues:
                self.send_queues[rec].put(msg)
            elif rec in self.dummy_queues:
                print(f"Node [blue]{self.name}[/blue] sent command [white]{cmd}[/white] with arguments " +
                      f"{args} to dummy queue [blue]{rec}[/blue].")
            else:    
                print(f"[bold][red]Node [blue]{self.name}[/blue] cannot access the queue for node "
                      + f"[blue]{rec}[/blue]!\nIntended Command:")
                print(msg)
                print("[bold][yellow]Continuing to run framework.")
        
    def flush_queue(self, sys_q:bool=False):
        """
        Flush the node's command or system queue.

        Since multiprocessing.Queue.size() and .empty() are unreliable, flushing is achieved
        by retrieving every entry from the queue without executing any of them.

        Parameters
        ----------
        sys_q: bool
            Whether to flush the system queue instead of the command queue.
        """
        self.check_queue(threshold=0, max_msgs=0, sys_q=sys_q, flush=True)


    # =====================================
    #     TOPICS
    # =====================================
    def topic_init(self, topic_configs:dict) -> tuple:
        """
        Initialize all topics the node publishes or subscribes to.

        Parameters
        ----------
        topic_configs:  dict
                        Dictionary containing topic configs for each topic the node publishes or subscribes to.
        
        Returns
        -------
        tuple of two dicts
            One dictionary each for topics the node publishes to (pub_tops) and subscribes to (sub_tops).
            Format: ("topic name": TopicObject).
            Dictionaries are empty if there are no pub/sub topics.
        """
        if topic_configs is None:
            return {}, {}
        
        # initialize topics this node publishes to
        pubs = topic_configs["pubs"]
        pub_tops = {}
        for t_name, t_config in pubs.items():
            pub_tops[t_name] = Topic(type=TopType.PUB, name=t_name, config=t_config)

        # initialize topics this node subscribes to
        subs = topic_configs["subs"]
        sub_tops = {}
        for t_name, t_config in subs.items():
            sub_tops[t_name] = Topic(type=TopType.SUB, name=t_name, config=t_config)

        return pub_tops, sub_tops

    def publish_to_topic(self, topic_name:str, msg, pad_arrays:bool=False, casting:bool=True) -> bool:
        """
        Publish a message to a specified topic.

        Message must be a list, tuple, or numpy ndarray. The messages validity will be checked.
        If a multidimensional message field (a list or array of lists) has fewer entries
        than defined as maximum in the config pad_arrays needs to be True to avoid an error.
        The user is responsible for ensuring that all elements in a multidimensional message field
        are of the same data type.

        Parameters
        ----------
        topic_name: str
                    Name of topic to publish to.
        msg:        list, tuple, or np.ndarray
                    The message, formatted as defined in the topic config.
        pad_arrays: bool
                    Whether to pad multidimensional message fields with fewer entries than the max defined in the config.
        casting:    bool
                    Whether to allow numpy safe-casting when publishing the message.
        
        Returns
        -------
        bool
            True if publishing was successful, else False.
        """
        # Check if node is subscribed to the topic in question
        if topic_name not in self.pubs:
            print(f"[bold][red]Node [blue]{self.name}[/blue] is not the publisher "
                  + f"of topic [bright_blue]{topic_name}[/bright_blue]!\n"
                  + "[yellow]Continuing to run framework.")
            return False
        
        timestamp = time.time_ns() # get timestamp in nanoseconds (see documentation)
        published = self.pubs[topic_name].publish(timestamp, msg, pad_arrays=pad_arrays, casting=casting)

        # log the message if it was published succesfully and logging is enabled
        if self.logging and published:
            # inform the logger a message has been published to the topic
            self.log(is_topic=True, timestamp=timestamp, rec=topic_name)

        return published
        

    def read_topic(self, topic_name:str,max_msgs:int=0, new_only:bool=True) -> list:
        """
        Retrieve messages from topic.

        Either get only new messages if there are any, up to a maximum number
        or get a set number of messages, whether they are new or not.
        In either case, all messages in the topic are marked as read/not new.

        Parameters
        ----------
        topic_name: str
                    Name of the topic to retrieve messages from.
        max_msgs:   int
                    How many messages to retrieve (starting with the newest). 0 gets all new messages if there are any.
        new_only:   bool
                    Whether to get only new messages or the max number of messages whether already read or not.
                    If new_only is False, max_msgs must not be 0!

        Returns
        -------
        list or None
            List containing one or more messages or None if messages could not be retrieved or there were no new messages.
        """
        # Check if node is subscribed to the topic in question
        if topic_name not in self.subs:
            print(f"[bold][red]Node [blue]{self.name}[/blue] is not subscribed to topic [bright_blue]{topic_name}[/bright_blue]!\n"
                  + "[yellow]Continuing to run framework.")
            return None
        # retrieve messages
        msgs = self.subs[topic_name].get_msg(max_msgs, new_only)
        return msgs

    def get_synced_message(
        self,
        topic_name:str,
        timestamp:int,
        max_distance:int=0,
        field_name:str="timestamp",
        direction:Literal["newer", "older", "nearest"]="nearest"
        ) -> tuple:
        """
        Retrieve message from topic that's closest to the timestamp.

        Calling this function does not influence which messages are marked as read.

        Parameters
        ----------
        t_name:     str
                    Name of the topic.
        timestamp : float
            The timestamp to sync messages to.
        max_distance: int
            Maximum distance between timestamp and message in seconds, default: DT/2.
        field_name: str
            Name of the message field to sync to. default="timestamp".
        direction : {"older", "newer", "nearest"}, default="nearest"
            Search direction:
            - "older": Closest message at or before the timestamp.
            - "newer": Closest message at or after the timestamp.
            - "nearest": Closest message overall.

        Returns
        -------
        tuple or None
            Message closest to timestamp within given parameters or None if no such message was found.
        """

        # set the threshold to DT/2 if it wasn't specified otherwise
        if max_distance == 0:
            max_distance = self.dt / 2

        return self.subs[topic_name].get_synced_msg(timestamp,max_distance,field_name,direction)

    # =====================================
    #     LOGGING
    # =====================================
    def log(self, is_topic:bool, timestamp:int, rec, content=None):
        """
        Send content to the logger to be added to the log.

        If logging is enabled, this method gets called every time a command is sent through queues
        or if a message is published to a topic. In the latter case, the logger is simply informed
        that publishing happened and consequently retrieves the message from the topic.  

        Parameters
        ----------
        is_topic:   bool
                    True if message was published to topic, False if command was sent to node(s).
        timestamp:  int
                    Timestamp when message was published or command was sent.
        rec:        string or list
                    Name(s) of the node(s) or topic that a command or message was sent/published to.
        content:    tuple or None
                    Command-message sent to node(s) or None if message was published to topic.
        """
        msg_dict = {
            "sender": self.name,
            "timestamp": timestamp,
            "recipients": rec,
            "content": content
        }

        # send the info to the logger Node
        if is_topic: # tell logger node to read latest topic entry:
            funct = "log_topic"
        else:
            funct="log_cmd"
        # create the message to be sent to the logger
        msg = (funct, (msg_dict,))
        # send message to logger and make sure this command is not logged to avoid recursion
        self.send_to_queues(recipients="logger", msg=msg, log_msg=False)


    # =====================================
    #     SHUT-DOWN 
    # =====================================
    def stop_node(self):
        """
        Initiate graceful node shut-down.

        Sets flag 'running' to false so run loop will exit and call shut-down function,
        and flushes any remaining commands from the system and command queues.
        This method is called by the main node when it receives the shut-down key or
        by the node registry if it exits unexpectedly.
        """
        self.running = False
        self.flush_queue()
        self.flush_queue(sys_q=True)

    def shut_down(self):
        """
        Run orderly shut-down of node process. This always includes closing all topics
        and can be extended to handle any other functionality needed upon closing a node.
        """
        print(f'Node [bold blue]{self.name}[/bold blue] finished running.')
        self.close_topics()

    def close_topics(self):
        """
        Close all topics the node publishes or subscribes to, releasing their shared memory.
        """
        # close all topics to unlink shared memory
        for t in (list(self.pubs.values()) + list(self.subs.values())):
            t.close() 

    

    # ================================
    #     AUXILIARY METHODS 
    # ================================
    def parse_command(self, msg):
        """
        Parse and execute a command received through the node's queues. 

        The command-message must consist of the name of a valid function
        and a tuple containing the arguments that function requires or None
        if no arguments are required.
        If a command does not exist the method will print an error or the 
        full command message if the node is a dummy.

        Parameters
        ----------
        msg:    tuple
                ("func_name", (args,)/None) - Function (and arguments) to be executed.
        """
        # try to parse the message as command and args
        try:
            cmd, args = msg
        except:
            print(f"[bold][red]Cannot interpret message [white]'{msg}'[/white] " + 
                  f"sent to node [blue]{self.name}[/blue] as a command!")
            print("[bold][red]Traceback:")
            traceback.print_exc()
            print("[bold][yellow]Continuing to run framework.")
            return

        # try to execute the command        
        try:
            method = getattr(self, cmd, None)
            if callable(method):
                method(*args if args is not None else ())
            elif self.is_dummy:
                if self.dummy_print == True:
                    print(f"Dummy Node [bold blue]{self.name}[/bold blue] received command '{cmd}' with arguments: {args}.")     
            else:
                print(f"[bold][red]Node [blue]{self.name}[/blue] does not have a method [white]{cmd}[red]!")
        except:
            if self.is_dummy:
                if self.dummy_print == True:
                    print(f"Dummy Node [blue]{self.name}[/blue] received command '{cmd}' with arguments: {args}.")     
                return
            print(f"[bold][red]Node [blue]{self.name}[red] encountered an error while executing command [white]'{cmd}'[/white]!")
            print("[bold][red]Traceback:")
            traceback.print_exc()
            print("[bold][yellow]Continuing to run framework.")

    def ping(self):
        """
        Ping the node.
        """
        print(f"Node [bold blue]{self.name}[/bold blue] (class {self.__class__.__name__}) got pinged!")

    def switch_mode(self, new_mode:int, flush:bool=True):
        """
        Save current mode to self.last_mode, (optionally) flush the command queue,
        and switch to new mode.

        Parameters
        ----------
        new_mode:   int
                    Numerical value of new Mode. (defined in utils.Menu)
        flush:      bool
                    True if command queue should be flushed. (Default: True)
        """
        if flush:
            self.flush_queue()
        self.last_mode = self.mode
        self.mode = Mode(new_mode)
    
    def __str__(self):
        return f"Node {self.name}"

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"