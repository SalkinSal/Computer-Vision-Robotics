import time
import jsonpickle

from keypress_listener import KeypressListener

from utils.print_utils import print_locked as print, configure_printing

from utils.config_utils import load_all_configs
from topic_registry import TopicRegistry
from node_registry import NodeRegistry
from publisher import Publisher
from viewer_message import Message

MAIN_CONFIG_PATH = "configs/main_config.yaml"

class Main:
    def __init__(self):
        """
        Load the configs using the path specified above and instantiate
        the context-managed classes (key listener, registries) without starting them.
        """
        # = LOAD CONFIGS ===
        configs = load_all_configs(main_path=MAIN_CONFIG_PATH)
        if configs is None:
            print("[bold][red]Couldn't parse configs! Exiting framework.")
            raise Exception

        # set all configs as class attributes using specified abbreviations
        # e.g. main config = self.mc
        for cf_name in configs:
            self.__setattr__(cf_name, configs[cf_name])

        # = INSTANTIATE REGISTRIES ETC. ===
        self.t_reg = TopicRegistry(topic_config=self.tc)
        self.n_reg = NodeRegistry(
            t_reg=self.t_reg, main_config=self.mc, 
            nodes_config=self.nc)
        self.kl = KeypressListener()

        self.publisher = Publisher()        

        # set up multiprocessing-secure printing
        configure_printing(self.mc.print_lock)

        self.dt = self.mc.dt # robot time-step, default: 0.1 seconds
        self.dt_buffer = self.mc.dt_buffer * self.dt # convert fraction into seconds
        self.dt_warnings = True
        self.start_time = None
        self.next_step = None

        self.last_marker_timestamp = 0 # needed for publishing to the viewer

        self.running = False
        self.count = 0

    # =====================================
    #     MAIN RUN LOOP
    # =====================================
    def run(self):
        """
        Run loop of the main process.

        The method enters the contexts for registries, publisher, and keypress listener.
        Then it sets self.running to True and enters the run-loop.
        Once per DT (default 0.1 sec), the run loop...
            - sends any keypresses received to the MainNode (via the node registry) to parse
            - calls the pub_to_viewer method to publish data to the viewer. 
        """
        with self.kl, self.publisher, self.t_reg, self.n_reg:
            self.n_reg.run_nodes()
            self.running = True

            self.start_time = time.monotonic()
            self.next_step = self.start_time

            while self.running:
                # set deadline for this loop iteration:
                self.next_step += self.dt
                key = self.kl.get_keypress()
                if key is not None:
                    key = key.lower()
                    if key == self.mc["stop_key"]: # Default: 'x'
                        print(f"[bold][yellow]Stop key received. Shutting down.")
                        self.running = False
                    self.n_reg.send_keypress(key)

                # publish message to the viewer
                self.pub_to_viewer(count=self.count, timestamp=time.monotonic())

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


    # =====================================
    #     VIEWER
    # =====================================
    # NOTE JJ: Method adapted from recorder.py from the original "Introduction to Computer Vision and Robotics" framework.
    def pub_to_viewer(self, count:int, timestamp:float):
        """
        Collect data from various topics and publish 
        it as a message to viewer.

        This method accesses the topics through the topic registry
        and publishes null data if no new messages were found in the topics
        or the topics were not instantiated because they don't have a publisher.

        The minimum requirement for the viewer to show any data is the
        presence of a camera image. All other values can be set to 0,
        but the camera image is required.
        
        Parameters
        ----------
        count:      int
                    Count of the run loop iteration.
        timestamp:  float
                    Timestamp of the run loop iteration

        """
        # get lates camera image if camera is connected.
        if not self.t_reg.has_topic("camera_capture"):
            return
        img_msg = self.t_reg.read_message_from_topic(t_name="camera_capture", max_msgs=1) # only read the latest message
        if img_msg is None:
            return
        _, img, cam_fps = img_msg[0] # should only contain the latest image

        # get marker detections if available
        if not self.t_reg.has_topic("marker_detections"):
            marker_msg = None
        else:
            marker_msg = self.t_reg.read_message_from_topic(t_name="marker_detections", max_msgs=1) # only read the latest message
        if marker_msg is None: # topic does not exist or has no new messages
            ids, l_rs, l_alphas, l_pos = [[]]*4
        else:
            m_ts, img_ts, m_count, ids, l_rs, l_alphas, l_pos, draw_img = marker_msg[0]
            ids = ids[:m_count]
            l_rs = l_rs[:m_count]
            l_alphas = l_alphas[:m_count]
            l_pos = l_pos[:m_count]
    
            if m_count > 0 and self.last_marker_timestamp != m_ts:
                img=draw_img
                self.last_marker_timestamp = m_ts

        # get landmark poses if available
        if not self.t_reg.has_topic("landmark_poses"):
            landmark_msg = None
        else:
            landmark_msg = self.t_reg.read_message_from_topic(t_name="landmark_poses", max_msgs=1, new_only=False) # only read the latest message
        if landmark_msg is None: # topic does not exist or has no new messages
            est_ids, l_est_pos, l_est_errors = [[]]*3
        else:
            _, m_count, est_ids, l_est_pos, l_est_errors = landmark_msg[0]
            est_ids = est_ids[:m_count]
            l_est_pos = l_est_pos[:m_count]
            l_est_errors = l_est_errors[:m_count]

        # get robot pose if available
        if not self.t_reg.has_topic("robot_pose"):
            robot_msg = None
        else:
            robot_msg = self.t_reg.read_message_from_topic(t_name="robot_pose", max_msgs=1) # only read the latest message
        if robot_msg is None: # topic does not exist or has no new messages
            r_x, r_y, r_theta, r_error = (0, 0, 0, [0,0,0])
        else:
            _, r_x, r_y, r_theta, r_error = robot_msg[0]

        msg = Message(
            id = count,
            timestamp = timestamp,
            start = True,

            landmark_ids = ids,
            landmark_rs = l_rs,
            landmark_alphas = l_alphas,
            landmark_positions = l_pos,

            landmark_estimated_ids = est_ids,
            landmark_estimated_positions = l_est_pos,
            landmark_estimated_stdevs = l_est_errors,

            robot_position = [r_x, r_y],
            robot_theta = r_theta,
            robot_stdev = r_error,

            text = f"cam fps: {cam_fps}"
        )
        msg_str = jsonpickle.encode(msg, keys=True)
        # send message to the viewer
        self.publisher.publish_img(msg_str, img)

    def __str__(self):
        return "Class Main"

# =====================================
#     TESTING
# =====================================
def main_test():
    """
    Method placeholder to test functions outside the run loop,
    (e.g. config parsing, creation of the registries, etc.)
    """
    # Currently instantiates menu and registries and prints out an overview without 
    # actually starting the node processes.

    from utils.menu import Menu
    m = Main()

    with m.t_reg, m.n_reg:
        print("\n[bold bright_blue]MENU:")
        menu = Menu(m.mc)
        print(repr(menu))
        print("\n[bold bright_blue]NODE REGISTRY:")
        print(m.n_reg)
        print("\n[bold bright_blue]TOPICS:")
        for t_name, t in m.t_reg.topics.items():
            print(t)

if __name__ == '__main__':
    # uncomment to run main_test method instead of normal framework 
    # main_test()

    Main().run()
