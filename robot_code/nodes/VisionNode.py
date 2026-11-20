import cv2
from flask import Flask, Response
from nodes.node import Node
import threading

class VisionNode(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.latest_frame = None
        self.app = Flask(__name__)

        @self.app.route('/')
        def video_feed():
            return Response(self.generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()

    def run_server(self):
        self.app.run(host='0.0.0.0', port=8080)

    def generate(self):
        while True:
            if self.latest_frame is not None:
                ret, jpeg = cv2.imencode('.jpg', self.latest_frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

    def run_step(self):
        msgs = self.read_topic(
        topic_name="camera_capture",
        max_msgs=1,
        new_only=True)
        if msgs is None:
            print("VisionNode: kein neues Bild")
            return
        timestamp, frame, cam_fps = msgs[0]
        self.latest_frame = frame
        print("VisionNode: Bild empfangen, fps =", cam_fps)