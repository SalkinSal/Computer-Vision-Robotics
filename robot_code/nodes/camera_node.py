# NOTE JJ: This node was created by copying over code from the original 
# "Introduction to Computer Vision and Robotics" class and adapting it to the framework.
import time
import cv2
import numpy as np
import threading
import subprocess
import traceback

from utils.print_utils import print_locked as print, configure_printing
from nodes.node import Node

class CameraNode(Node):
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


        self.DEVICE = main_config.camera.device

        self.IM_WIDTH = main_config.camera.im_width         # default: 864
        self.IM_HEIGHT = main_config.camera.im_height       # default: 480
        self.FPS = main_config.camera.fps                   # default: 30

        # we can use a larger image, but opencv detectmarkers will get really slow!
        # self.IM_WIDTH = 1920
        # self.IM_HEIGHT = 1080
        # self.FPS = 30

        self.exposure_time = main_config.camera.exposure_time # between 1 and 5000
        self.gain = main_config.camera.gain # between 0 and 100
        # self.exposure = 400 # higher is brighter

        self.CAMERA_MATRIX = main_config.camera.camera_intrinsics.camera_matrix
        self.DIST_COEFFS = main_config.camera.camera_intrinsics.distortion_coefficients        

        self.cap = None
        self.set_camera_properties(self.exposure_time, self.gain)

        self.warm_up()

        # we run the camera in a separate thread to always get the latest frame
        self.camera_thread = threading.Thread(target=self.worker_thread)


    def run(self):
        """
        Extend the base run function to add flags needed for the camera thread
        and initiate the same.

        self.running and self.start_time will be set again once super().run() is called,
        but they are needed for the worker thread and setting them twice doesn't cause any issues.
        """
        self.running = True
        self.start_time = time.monotonic()
        self.time_last = self.start_time
        self.camera_thread.start()

        super().run()

    def shut_down(self):
        """
        Extend the base shut-down function to add orderly shut-down of the camera thread.
        """
        self.close_camera()
        super().shut_down()



    # NOTE JJ: this code is no longer up to date with the Raspberry Pi OS, so it has been truncated 
    # to the minimum that will allow the camera to remain operational. We will update this in future versions.
    def set_camera_properties(self, exposure_time=157, gain=50):
        """
        $ v4l2-ctl --all
        brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=0
        contrast 0x00980901 (int)    : min=0 max=64 step=1 default=22 value=22
        saturation 0x00980902 (int)    : min=0 max=128 step=1 default=64 value=64
        hue 0x00980903 (int)    : min=-40 max=40 step=1 default=0 value=0
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
        gamma 0x00980910 (int)    : min=72 max=500 step=1 default=110 value=110
        gain 0x00980913 (int)    : min=0 max=100 step=1 default=0 value=0
        power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=1 value=1
                                        0: Disabled
                                        1: 50 Hz
                                        2: 60 Hz
        white_balance_temperature 0x0098091a (int)    : min=2800 max=6500 step=1 default=4600 value=4600 flags=inactive
        sharpness 0x0098091b (int)    : min=0 max=6 step=1 default=3 value=3
        backlight_compensation 0x0098091c (int)    : min=0 max=2 step=1 default=1 value=1

        Camera Controls

        auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3
                                        1: Manual Mode
                                        3: Aperture Priority Mode
        exposure_time_absolute 0x009a0902 (int)    : min=1 max=5000 step=1 default=157 value=157 flags=inactive
        exposure_dynamic_framerate 0x009a0903 (bool)   : default=0 value=1
        """
        subprocess.call(f"v4l2-ctl -d {self.DEVICE} -c gain={gain}", shell=True)
        # subprocess.call(f"v4l2-ctl -d {self.DEVICE} -c auto_exposure=1,exposure_time_absolute={exposure_time},gain={gain}", shell=True)
        self.cap = cv2.VideoCapture(self.DEVICE, cv2.CAP_V4L2)

        # get all output formats by running:
        # $ v4l2-ctl -d /dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0 --list-formats-ext
        # note difference 'MJPG' (Motion-JPEG, compressed) and 'YUYV' (YUYV 4:2:2).
        # with MJPG we can get much higher fps

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.IM_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.IM_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, self.FPS)

    def worker_thread(self):
        """
        Main camera thread. Publishes images and current frame rate
        to the topic "camera_capture" as frequently as fps allows.
        """
        configure_printing(self.print_lock)
        while self.running:
            # get frame
            ret , frame = self.cap.read()

            time_now = time.time()
            elapsed_time = time_now - self.time_last
            cam_fps = int(np.rint(1/elapsed_time))
            if ret:
                # publish camera results to topic
                self.publish_to_topic("camera_capture", (cv2.flip(frame, -1), cam_fps))

            self.time_last = time_now

            if cam_fps < 10:
                print(f"[red] cam_fps {cam_fps}")



    def warm_up(self):
        """
        Warm up the camera upon start-up.
        """
        _, self.frame = self.cap.read()
        _, self.frame = self.cap.read()

    def close_camera(self):
        """
        Orderly shut down camera thread and release resources.
        """
        print("[blue]Camera closing...")

        self.camera_thread.join() # wait for thread to finish

        self.cap.release()
        print("[blue]Camera closed")


    # =====================================
    #     CAMERA ADJUSTMENT
    # =====================================
    # Preserved from the existing code.
    # auto_set_exposure() can be added to init or the start of the run-loop
    # and adapted as needed.

    def start_up(self):
        self.running = True

    def auto_set_exposure(self):
        brightness = self.get_brightness(self.frame)

        print("brightness", brightness)

        exposure_time = self.exposure_time
        while brightness < 100:
            exposure_time += 200

            print(f"[blue]increasing exposure to {self.exposure_time}")

            self.close_camera()
            self.set_camera_properties(exposure_time)
            self.exposure_time = exposure_time
            self.start_up()
            self.warm_up()
            brightness = self.get_brightness(self.frame)

            print("brightness", brightness)


    def get_brightness(self, img):
        # https://stackoverflow.com/questions/14243472/estimate-brightness-of-an-image-opencv
        if len(img.shape) == 3:
            # Colored RGB or BGR (*Do Not* use HSV images with this function)
            # create brightness with euclidean norm
            return np.average(np.linalg.norm(img, axis=2)) / np.sqrt(3)
        else:
            # Grayscale
            return np.average(img)


    def get_brightness_parameters(self, image, clip_hist_percent=10):
        """
        https://stackoverflow.com/questions/57030125/automatically-adjusting-brightness-of-image-with-opencv
        Perform contast enhancement of the image.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Calculate grayscale histogram
        hist = cv2.calcHist([gray],[0],None,[256],[0,256])
        hist_size = len(hist)

        # Calculate cumulative distribution from the histogram
        accumulator = []
        accumulator.append(float(hist[0]))
        for index in range(1, hist_size):
            accumulator.append(accumulator[index -1] + float(hist[index]))

        # Locate points to clip
        maximum = accumulator[-1]
        clip_hist_percent *= (maximum/100.0)
        clip_hist_percent /= 2.0

        # Locate left cut
        minimum_gray = 0
        while accumulator[minimum_gray] < clip_hist_percent:
            minimum_gray += 1

        # Locate right cut
        maximum_gray = hist_size -1
        while accumulator[maximum_gray] >= (maximum - clip_hist_percent):
            maximum_gray -= 1

        # Calculate alpha and beta values
        alpha = 255 / (maximum_gray - minimum_gray)
        beta = -minimum_gray * alpha

        self.auto_brightness_alpha = alpha
        self.auto_brightness_beta = beta

        print(f"[blue]auto brightness: alpha:{alpha}, beta:{beta}")

    def apply_brightness_params(self, img):
        if self.auto_brightness_alpha and self.auto_brightness_beta is not None:
            auto_result = cv2.convertScaleAbs(img, alpha=self.auto_brightness_alpha, beta=self.auto_brightness_beta)
            return auto_result
        return img