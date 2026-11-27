from multiprocessing import Queue
import cv2
import zmq

from nodes.node import Node
from utils.config_utils import Struct


class ViewerNode(Node):
    def __init__(
        self,
        name: str,
        main_config: Struct,
        node_config: Struct,
        own_queue: Queue,
        sys_queue: Queue,
        send_queues: dict,
        topic_configs: dict,
    ):
        super().__init__(
            name=name,
            main_config=main_config,
            node_config=node_config,
            sys_queue=sys_queue,
            own_queue=own_queue,
            send_queues=send_queues,
            topic_configs=topic_configs,
        )

        self.context = None
        self.publisher = None

    def run_step(self):
        # Initialize inside the node process
        if self.publisher is None:
            self.context = zmq.Context()
            self.publisher = self.context.socket(zmq.PUB)
            self.publisher.setsockopt(zmq.SNDHWM, 2)
            self.publisher.bind("tcp://0.0.0.0:5555")

        messages = self.read_topic(
            topic_name="camera_capture",
            max_msgs=1,
            new_only=True,
        )

        if messages is None:
            return

        timestamp, img, cam_fps = messages[0]

        # Convert RGB to BGR for OpenCV
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        # Compress image
        success, encoded = cv2.imencode(
            ".jpg", img,
            [cv2.IMWRITE_JPEG_QUALITY, 80],
        )

        if success:
            try:
                self.publisher.send(
                    encoded.tobytes(),
                    flags=zmq.NOBLOCK,
                )
            except zmq.Again:
                pass  # Drop frame rather than block the node
