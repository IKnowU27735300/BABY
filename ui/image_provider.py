
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage


class CameraImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._current_image = QImage()

    def requestImage(self, id, size, requestedSize):
        return self._current_image

    def set_image(self, img):
        self._current_image = img



















