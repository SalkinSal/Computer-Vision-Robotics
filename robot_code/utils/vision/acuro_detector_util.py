"""Detect ArUco markers and estimate their 3D poses using OpenCV.

Positions (tvec) are in the camera coordinate frame and use the same
unit as ``marker_size``. Rotations (rvec) describe marker-to-camera
orientation in Rodrigues axis-angle representation.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
import yaml
from matplotlib import pyplot as plt


class AcuroDetectorUtil:
    """Detect and annotate ArUco marker positions and orientations.

    Parameters
    ----------
    camera_matrix : array-like, shape (3, 3)
        Intrinsic camera matrix for the input images.
    distortion_coefficients : array-like
        Lens distortion coefficients for the input images.
    marker_size : float
        Physical marker side length, usually in metres.
    undistort : bool, default True
        Undistort images before marker detection. Pose estimation then
        uses the corresponding new camera matrix and zero distortion.
    dictionary_id : int, default cv2.aruco.DICT_ARUCO_ORIGINAL
        ArUco dictionary used to generate the printed markers.
    """

    def __init__(
        self,
        marker_size: float = 10,
        *,
        undistort: bool = True,
        dictionary_id: int = cv2.aruco.DICT_ARUCO_ORIGINAL,
    ) -> None:
        if marker_size <= 0:
            raise ValueError("marker_size must be positive")

        with open(r"../../configs/main_config.yaml", 'r') as stream:
            camera_intrinsics = yaml.safe_load(stream)['camera']['camera_intrinsics']
        # print(camera_intrinsics)
        self.camera_matrix = np.array(camera_intrinsics["camera_matrix"]["data"]).reshape((3,3))
        self.distortion_coefficients = np.array(camera_intrinsics["distortion_coefficients"]["data"]).reshape(-1, 1)
        self.marker_size = float(marker_size)
        self.undistort = undistort
        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        parameters = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(dictionary, parameters)

        half = self.marker_size / 2.0
        # Corner order matches cv2.aruco: TL, TR, BR, BL.
        self._object_corners = np.array(
            [
                [-half,  half, 0.0],
                [ half,  half, 0.0],
                [ half, -half, 0.0],
                [-half, -half, 0.0],
            ],
            dtype=np.float32,
        )

    def _detect(self, img: np.ndarray):
        if img is None or img.ndim not in (2, 3):
            raise ValueError("img must be a grayscale or BGR image")
        if img.ndim == 3 and img.shape[2] != 3:
            raise ValueError("img must be a grayscale or 3-channel BGR image")

        if self.undistort:
            height, width = img.shape[:2]
            new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
                self.camera_matrix,
                self.distortion_coefficients,
                (width, height),
                alpha=0,
                newImgSize=(width, height),
            )
            frame = cv2.undistort(
                img,
                self.camera_matrix,
                self.distortion_coefficients,
                None,
                new_camera_matrix,
            )
            camera_matrix = new_camera_matrix
            distortion = np.zeros_like(self.distortion_coefficients)
        else:
            frame = img.copy()
            camera_matrix = self.camera_matrix
            distortion = self.distortion_coefficients

        gray = (
            frame
            if frame.ndim == 2
            else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        )
        corners, ids, _rejected = self._detector.detectMarkers(gray)

        markers = []
        if ids is not None:
            for marker_id, marker_corners in zip(ids.flatten(), corners):
                pixel_corners = np.asarray(marker_corners, dtype=np.float32).reshape(4, 2)
                success, rvec, tvec = cv2.solvePnP(
                    self._object_corners,
                    pixel_corners,
                    camera_matrix,
                    distortion,
                    flags=cv2.SOLVEPNP_IPPE_SQUARE,
                )
                if not success:
                    continue

                markers.append(
                    {
                        "id": int(marker_id),
                        "center": pixel_corners.mean(axis=0),
                        "corners": pixel_corners,
                        "position": tvec.flatten(),
                        "rotation": rvec.flatten(),
                        "rotation_matrix": cv2.Rodrigues(rvec)[0],
                    }
                )
        return frame, markers, camera_matrix, distortion

    def find_detectors(self, img: np.ndarray) -> list[dict]:
        """Find markers and return IDs, pixel centers, corners, and 3D poses.

        Each result contains ``position`` (x, y, z), ``rotation``
        (Rodrigues vector), and ``rotation_matrix`` (3x3), all relative
        to the camera. Returns an empty list if no markers are found.

        ``center`` and ``corners`` are pixel locations in the *undistorted*
        image when ``undistort=True``.
        """
        _frame, markers, _camera_matrix, _distortion = self._detect(img)
        return markers

    def mark_detectors(self, img: np.ndarray) -> np.ndarray:
        """Return a copy of the image with marker outlines, IDs, and axes.

        If ``undistort=True``, the returned annotated image is undistorted.
        The original image is never modified.
        """
        frame, markers, camera_matrix, distortion = self._detect(img)
        annotated = (
            cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            if frame.ndim == 2
            else frame.copy()
        )

        for marker in markers:
            cv2.aruco.drawDetectedMarkers(
                annotated,
                [marker["corners"].reshape(1, 4, 2)],
                np.array([[marker["id"]]], dtype=np.int32),
            )
            cv2.drawFrameAxes(
                annotated,
                camera_matrix,
                distortion,
                marker["rotation"].reshape(3, 1),
                marker["position"].reshape(3, 1),
                self.marker_size * 0.5,
            )
        return annotated

if __name__ == '__main__':
    img = cv2.imread(r"1.jpg")
    detector = AcuroDetectorUtil()
    new_img = detector.mark_detectors(img)
    plt.imshow(cv2.cvtColor(new_img, cv2.COLOR_BGR2RGB))
    plt.savefig("1_marked.jpg")
