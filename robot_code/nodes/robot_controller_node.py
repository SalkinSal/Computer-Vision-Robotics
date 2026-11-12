import time
import numpy as np
import traceback

from nodes.node import Node
from utils.menu import Mode
from utils.print_utils import print_locked as print

class RobotControllerNode(Node):
    def __init__(self, 
                 name:str, 
                 main_config:dict,
                 node_config:dict, 
                 own_queue,
                 sys_queue, 
                 send_queues:dict,
                 topic_configs:dict):

        super().__init__(name=name,
                         main_config=main_config,
                         node_config=node_config, 
                         sys_queue=sys_queue, 
                         own_queue=own_queue, 
                         send_queues=send_queues,
                         topic_configs=topic_configs) 

        self.driving = False

        self.speed = 0
        self.turn = 0
        self.old_speed = 0
        self.old_turn = 0

    # =====================================
    #     RUN & RUN-STEP
    # =====================================       
    def run_step(self):
        """
        Control robot's behavior based on current mode.
        
        Currently only has functions for mode MANUAL.
        """
        if self.mode == Mode.MANUAL:
            self.move_man()

    # =====================================
    #     DRIVE FUNCTIONS
    # =====================================
    def stop(self):
        """
        Send stop command to ev3 node and update driving parameters. 
        """
        self.send_to_queues(recipients="ev3", msg=('stop', None))

        self.driving = False
        self.old_turn = self.turn
        self.old_speed = self.speed
        self.turn = 0
        self.speed = 0

    # -----------------------------
    #     MANUAL MODE 
    # -----------------------------
    def move_man(self):
        """
        Continuously send movement commands with current speed and turn to the ev3 node.
        """
        self.send_to_queues(recipients="ev3", msg=('move', (self.speed, self.turn)))

    
    # NOTE JJ: Method based on original "Introduction to Computer Vision and Robotics" class code.
    def set_move(self, char:str, speed_step:int=5, turn_step:int=5):
        """
        Set speed and turn based on keyboard input.

        Pressing 'W' while the robot is standing still (speed=0) or is moving forwards
        increases the movement speed by the speed_step up to a limit of 100.
        Pressing 'W' while the robot is moving backwards sets speed to 0.
        ('S' works the same for driving backwards.)

        Pressing 'A' while the robot is not turning (turn=0) or is turning left/counterclockwise
        increases the turning speed by turn_step up to a limit of 100. Pressing 'A' while the robot
        is turning right/clockwise sets the turning speed to 0.
        ('D' works the same for turning right/clockwise.)

        If speed = 0 and turn != 0, the robot spins in place. 

        Parameters
        ----------
        char:       str
            Keyboard input. Currently supports WASD.
        speed_step: int
            Amount by which speed should be increased/decreased, default: 5.
        turn_step:  int
            Amount by which turn should be increased/decreased, default: 5.
        """
        self.old_turn = self.turn
        self.old_speed = self.speed
        if char == "a":
            if self.turn >= 0:
                self.turn += turn_step
            else:
                self.turn = 0
        elif char == "d":
            if self.turn <= 0:
                self.turn -= turn_step
            else:
                self.turn = 0
        elif char == "w":
            if self.speed >= 0:
                self.speed += speed_step
            else:
                self.speed = 0
        elif char == "s":
            if self.speed <= 0:
                self.speed -= speed_step
            else:
                self.speed = 0
        
        # limit turn and speed
        self.speed = max(min(self.speed, 100), -100)
        self.turn = max(min(self.turn, 200), -200)
        print(f"speed: {self.speed} turn: {self.turn}")
    
    # -----------------------------
    #     ADD YOUR FUNCTIONS HERE
    # -----------------------------

    


    # =====================================
    #     HELPER FUNCTIONS
    # =====================================
    def switch_mode(self, new_mode:int, flush:bool=True):
        """
        Extend standard method to add stopping when mode is changed.
        """
        self.stop()
        super().switch_mode(new_mode, flush)
