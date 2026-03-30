import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.uic import loadUi
from PyQt5.QtGui import QImage, QPixmap

class ImageProcessor(QMainWindow):
    def __init__(self):
        super(ImageProcessor, self).__init__() 
        loadUi("./interface.ui",self)
        self.slider_red.valueChanged.connect(self.update_image)
        self.slider_green.valueChanged.connect(self.update_image)
        self.slider_blue.valueChanged.connect(self.update_image)
        self.slider_threshold.valueChanged.connect(self.update_image)
        self.slider_erosion.valueChanged.connect(self.update_image)
        self.slider_dilatacion.valueChanged.connect(self.update_image)
        self.slider_erosion2.valueChanged.connect(self.update_image)
        self.slider_dilatacion2.valueChanged.connect(self.update_image)
        self.checkBox_show_binary.stateChanged.connect(self.update_image)
        self.update_image()

    def update_image(self):
        red_value = self.slider_red.value()
        green_value = self.slider_green.value()
        blue_value = self.slider_blue.value()
        threshold = self.slider_threshold.value()

        # Raw image (no edits) — OpenCV loads as BGR
        image = cv2.imread('./images/test2/Fotografias/Tile_299937_559765.png')
        if image is None:
            return

        # Target color in BGR (sliders are R, G, B)
        specific_color = np.array([blue_value, green_value, red_value], dtype=np.uint8)
        lower_bound = np.clip(specific_color - threshold, 0, 255).astype(np.uint8)
        upper_bound = np.clip(specific_color + threshold, 0, 255).astype(np.uint8)

        # Binary mask: 255 (white) = detected color, 0 (black) = everything else
        mask = cv2.inRange(image, lower_bound, upper_bound)

        iteraciones_erosion = self.slider_erosion.value()
        iteraciones_dilatacion = self.slider_dilatacion.value()
        iteraciones_erosion2 = self.slider_erosion2.value()
        iteraciones_dilatacion2 = self.slider_dilatacion2.value()

        kernel = np.ones((5, 5), np.uint8)
        dilatacion = cv2.dilate(mask, kernel, iterations=iteraciones_dilatacion)
        erosion = cv2.erode(dilatacion, kernel, iterations=iteraciones_erosion)
        dilatacion2 = cv2.dilate(erosion, kernel, iterations=iteraciones_dilatacion2)
        mask_final = cv2.erode(dilatacion2, kernel, iterations=iteraciones_erosion2)

        show_binary = self.checkBox_show_binary.isChecked()
        if show_binary:
            # Binary view: white = detected color, black = rest
            height, width = mask_final.shape
            bytes_per_line = 1 * width
            q_image = QImage(mask_final.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
        else:
            # Color view: only the selected color visible (full color), rest black
            result_color = cv2.bitwise_and(image, image, mask=mask_final)
            result_rgb = cv2.cvtColor(result_color, cv2.COLOR_BGR2RGB)
            height, width, channels = result_rgb.shape
            bytes_per_line = channels * width
            q_image = QImage(result_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)

        pixmap = QPixmap.fromImage(q_image)
        self.label_red_value.setText(str(red_value))
        self.label_green_value.setText(str(green_value))
        self.label_blue_value.setText(str(blue_value))
        self.label_threshold_value.setText(str(threshold))
        self.label_erosion_value.setText(str(iteraciones_erosion))
        self.label_dilatacion_value.setText(str(iteraciones_dilatacion))
        self.label_erosion2_value.setText(str(iteraciones_erosion2))
        self.label_dilatacion2_value.setText(str(iteraciones_dilatacion2))
        self.label.setPixmap(pixmap)

def main():
    app = QApplication([])
    window = ImageProcessor()
    window.show()
    app.exec_()

if __name__ == "__main__":
    main()

'''
Color           R   G   B
Rojo oscuro     169 39  39
Rojo            242 78  66
Amarillo        255 207 67
Verde           22  224 152
'''