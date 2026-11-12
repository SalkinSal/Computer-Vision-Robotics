import traceback
import ev3_dc as ev3
import numpy as np

from utils.print_utils import print_locked as print
from utils.menu import Mode
from nodes.node import Node

class EV3Node(Node):
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

        self.wheel_radius = main_config["robot"]["wheel_radius"]
        self.width = main_config["robot"]["width"]

        try:
            self.ev3 = ev3.EV3(protocol=ev3.USB)
            self.vehicle = ev3.TwoWheelVehicle(
                radius_wheel=self.wheel_radius,
                tread=self.width,
                ev3_obj=self.ev3
            )
        except Exception as e:
            print("[bold][red]Couldn't connect to EV3!")
            print("[bold][red]Traceback:")
            traceback.print_exc()
            print("[bold yellow]Running Node [blue]ev3[/blue] as dummy node instead.")
            self.is_dummy = True
            print("[bold yellow]Continuing to run framework.")

        # these will be set at the start of the node's run 
        self.last_motor_pos = None


    # ================================
    #     RUN & RUN-STEP
    # ================================
    def run(self):
        """
        Publish an initial message to all topics before calling standard run().
        """
        self.update_msgs(init=True)

        super().run()


    def run_step(self):
        """
        Once per run loop, publish messages to all topics if there has been a change.
        """
        self.update_msgs()



    # ================================
    #     EV3 FUNCTIONS
    # ================================
    # NOTE JJ: Method taken from original "Introduction to Computer Vision and Robotics" class code;
    # minimally adapted for use with the framework.
    def move(self, speed:int, turn:int):
        """
        Send a movement command to the LEGO EV3 controller. The command
        makes the robot move at the given speed and turn for a short time.
        To achieve continuous driving, the method needs to be called repeatedly.

        Parameters
        ----------
        speed:  int
            Speed at which the robot should move. Clips speed at -100 (backwards) and 100 (forwards).
        turn:   int
            Speed at which the robot should turn. Clips turn speed at -100 (right) and 100 (left).
        """
        v_max = 1 
        w_max = 4*np.pi
        
        v = np.clip(v_max * speed / 100, -1 * v_max, v_max)
        w = np.clip(w_max * turn / 100, -1 * w_max, w_max)
        if speed == 0 and turn == 0:
            self.vehicle.stop(brake=False)
            return
        if w == 0:
            vl = v
            vr = v
        else:
            vl = w*(v/w - self.width/2)
            vr = w*(v/w + self.width/2)

        vr = int(np.copysign(np.ceil(np.abs(100 * vr)), vr))
        vl = int(np.copysign(np.ceil(np.abs(100 * vl)), vl))
        # normalise to avoid overflow
        if np.abs(vr) > 100 or np.abs(vl) > 100:
            vr, vl = np.round(100 * np.array([vr, vl]) / np.max(np.abs([vr, vl])))
        ops = b''.join((
            ev3.opOutput_Step_Speed,
            ev3.LCX(0),  # LAYER
            ev3.LCX(self.vehicle.port_left),  # NOS
            ev3.LCX(int(vl)),
            ev3.LCX(50),  # STEP1
            ev3.LCX(50),  # STEP2
            ev3.LCX(50),  # STEP3
            ev3.LCX(0),  # BRAKE
            
            ev3.opOutput_Step_Speed,
            ev3.LCX(0),  # LAYER
            ev3.LCX(self.vehicle.port_right),  # NOS
            ev3.LCX(int(vr)),
            ev3.LCX(50),  # STEP1
            ev3.LCX(50),  # STEP2
            ev3.LCX(50),  # STEP3
            ev3.LCX(0),  # BRAKE
            
            ev3.opOutput_Start,
            ev3.LCX(0),  # LAYER
            ev3.LCX(self.vehicle.port_left + self.vehicle.port_right),  # NOS
        ))

        self.vehicle.send_direct_cmd(
                self.vehicle._ops_pos() + ops,
                global_mem=8
            )

    def stop(self):
        """
        Send a stop command to the EV3 controller to stop driving.
        """
        if not self.is_dummy:
            self.vehicle.stop()

    # ================================
    #     TOPICS
    # ================================
    def update_msgs(self, init:bool=False):
        """
        Update all EV3 topics if there has been a change.

        Currently updates wheel_position and motor_movements.
        If no EV3 device is connected, this method will only publish an initial, empty message to each topic.
        
        Parameters
        ----------
        init: bool
            If True, overrides the check if anything has changed and publishes an initial message to all topics.
        """
        # if no ev3 device is connected, only publish one empty message upon startup.
        if init and self.is_dummy:
            self.publish_to_topic(topic_name="wheel_positions", msg=(0, 0))
            self.publish_to_topic(topic_name="motor_movements", msg=(0, 0))
            return            
        elif self.is_dummy:
            return
        # get current motor positions (in degree, calculated from when EV3 started)
        new_pos = [self.vehicle.motor_pos[0], self.vehicle.motor_pos[1]]

        # don't publish unless wheel position has changed (or init=True)
        if (not init) and (new_pos == self.last_motor_pos):
            return
        # publish wheel positions
        self.publish_to_topic(topic_name="wheel_positions", msg=(new_pos[0], new_pos[1]))
        self.last_motor_pos = new_pos

        # Convert to traveled distance (meters) for the differential drive model.
        l = np.deg2rad(new_pos[0]) * self.wheel_radius
        r = np.deg2rad(new_pos[1]) * self.wheel_radius

        # publish motor movement
        self.publish_to_topic(topic_name="motor_movements", msg=(l, r))



    # ================================
    #     SHUT-DOWN
    # ================================
    def stop_node(self):
        """
        Stop the EV3 vehicle if it is still running 
        before calling normal stop_node function.
        """
        self.stop()
        super().stop_node()


    # ================================
    #     AUXILIARY METHODS
    # ================================
    def switch_mode(self, new_mode:int, flush:bool=True):
        """
        Extend parent method so that when framework is in manual mode and no
        EV3 controller is connected, command-printing is turned off.
        (Otherwise there would be a constant stream of print-outs since the 
        robot controller sends one `move()` command per DT.)
        """
        super().switch_mode(new_mode, flush)

        # if manual mode is implemented and no EV3 block is connected...
        if self.is_dummy and Mode.MANUAL in Mode:
            # ... set dummy_print to False when switching into manual mode...
            if self.mode == Mode.MANUAL:
                self.dummy_print = False
            # ... and back to True for any other mode.
            else:
                self.dummy_print = True

        # NOTE JJ: I cannot adequately express how much I loathe that writing comments like this looks like they were written by ChatGPT...