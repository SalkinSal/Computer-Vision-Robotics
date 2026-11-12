import time
from multiprocessing import Queue

from nodes.node import Node
from utils.config_utils import Struct
from utils.menu import Menu, Mode
from utils.print_utils import print_locked as print


class MainNode(Node):
    def __init__(
            self,
            name:str,
            main_config:Struct,
            node_config:Struct,
            own_queue:Queue,
            sys_queues:dict):

        super().__init__(
            name=name,
            main_config=main_config,
            node_config=node_config,
            own_queue=own_queue)

        self.send_queues = sys_queues
        self.menu = Menu(main_config=main_config)

    # =====================================
    #     OVERWRITTEN METHODS
    # =====================================  
    def run(self):
        """
        Run loop, overrides base Node's standard run-loop.

        Since MainNode has no system queue, it only checks its command queue, 
        retrieves all commands sent there and executes them.
        The MainNode has no run-step method.
        """
        self.running = True
        print(f"Node [bold blue]{self.name}[/bold blue] running.")

        self.start_time = time.monotonic()
        self.next_step = self.start_time
        
        while self.running:
            # set deadline for this loop iteration:
            self.next_step += self.dt
          
            # check main queue and execute all commands inside
            self.check_queue(threshold=self.queue_threshold, max_msgs=0)
            
            # calculate time remaining in loop iteration
            dt_rest = self.next_step - time.monotonic()

            if dt_rest < 0: # Loop took longer than DT
                if self.dt_warnings:
                    print(f"[bold][yellow]Node [blue]{self.name}[/blue][yellow] exceded DT by [white]{-dt_rest:.4f}[/white] seconds!")
                # skip to the first deadline that has not passed yet
                while dt_rest < 0:
                    self.next_step += self.dt
                    dt_rest = self.next_step - time.monotonic()
                    # increment count to keep it more or less synced across the framework
                    self.count += 1 
            # pause process until the deadline for the next iteration is reached
            time.sleep(dt_rest)

            self.count +=1
        
        # orderly shut down once 'self.running' was set to false
        self.shut_down()

    def check_queue(self, threshold:int, max_msgs:int, sys_q:bool=False, flush:bool=False):
        """
        The main node has no system queue, so if `sys_q=True` 
        (e.g. flush-call during `stop_node()`), abort method.
        """
        if sys_q == True:
            return
        super().check_queue(threshold, max_msgs, sys_q, flush)


    # =====================================
    #     GENERAL COMMANDS
    # =====================================
    def parse_keypress(self, key:str):
        """
        Parses keypresses according to the menu and forwards commands to other
        nodes if necessary. Keypresses with no effect are silently discarded.

        Parameters
        ----------
        key: str
            The key that was pressed.
        """
        ret = self.menu.parse_keypress(key)
        if ret is None:
            # key has no associated command
            return
        try:
            recipients, command, args = ret
        except:
            print(f"[bold]{ret}[red] is not a valid keypress command! [/red][/bold]"
                  + f"({self.mode}, key: '{key}')")
            return
        # if command is inteded for the main node, execute the command
        if recipients == "main":
            self.parse_command(msg=(command, args))
        # otherwise, pass the command to the recipient node(s)
        else:
            self.send_to_queues(recipients=recipients, msg=(command, args))
    
    def switch_mode(self, new_mode:int):
        """
        Switch self and menu to new mode and send switch-command to all other nodes.
        
        Parameters
        ----------
        new_mode:   int
                    Numerical value of new Mode. (defined in utils.Menu)
        """
        # update the mode in the menu
        switched = self.menu.switch_mode(new_mode)
        if not switched: # there was a problem switching modes
            return
        print(f"[bold][green]Switching to [white]{Mode(new_mode,)}[/white]!")
        # send out switch-mode command to all nodes
        self.send_to_queues(recipients="all", msg=("switch_mode", (new_mode,)))

        # update own mode (but do not flush main queue!)
        super().switch_mode(new_mode, flush=False)

    def stop_all(self):
        """
        Send stop command to all nodes and execute own stop_node() method.
        """
        self.send_to_queues(recipients="all", msg=("stop_node", None))
        self.stop_node()