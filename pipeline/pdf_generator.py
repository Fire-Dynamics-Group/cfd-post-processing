from PyPDF2 import PdfWriter, PdfReader, PdfMerger
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import cv2
import re

class GeneratePDFSlice:
    def __init__(self,
                 n_slice,
                 img_loc,
                 slice_type,
                 draw_block_input,
                 slice_min_value,
                 slice_max_value,
                 t_difference,
                 t_start,
                 output_loc,
                 output_name,
                 crop=True):

        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0

        # Store output location and name
        self.output_loc = output_loc
        self.output_name = output_name

        # Register Font
        pdfmetrics.registerFont(TTFont('SegoeUILight', 'Segoe UI Light.ttf'))

        # Slice Type Picker
        self.slice_name = slice_type
        self.slice_unit = self.slice_unit_selector()
        self.slice_cat = self.slice_cat_selector()

        if n_slice == 1:
            self.create_1_slice(n_slice, img_loc, t_difference, t_start, slice_min_value, slice_max_value, draw_block_input, crop)
        elif n_slice == 5:
            self.create_5_slice(n_slice, img_loc, t_difference, t_start, slice_min_value, slice_max_value, draw_block_input)
        else:  # n_slice == 9
            self.create_9_slice(n_slice, img_loc, t_difference, t_start, slice_min_value, slice_max_value, draw_block_input, crop)

    def slice_unit_selector(self):
        if self.slice_name == 'Temperature':
            return '\N{DEGREE SIGN}C'
        elif self.slice_name == 'Visibility':
            return 'm'
        elif self.slice_name == 'Velocity':
            return 'm/s'
        elif self.slice_name == 'Pressure':
            return 'Pa'
        else:
            return ''

    def slice_cat_selector(self):
        if self.slice_name == 'Visibility':
            return 1
        elif self.slice_name in ['Temperature', 'Pressure']:
            return 2
        else:
            return 3

    def get_trim_size(self, img, initial):
        image = cv2.imread(img)
        if image is None:
            raise ValueError(f"Failed to read image in get_trim_size: {img}")
        original = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (25, 25), 0)
        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        noise_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, noise_kernel, iterations=2)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        close = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, close_kernel, iterations=3)

        coords = cv2.findNonZero(close)
        if coords is None:
            # If no non-zero pixels found, return the whole image
            return image, original
            
        x, y, w, h = cv2.boundingRect(coords)

        if initial:
            pixel = 50
            self.x = x - pixel
            self.y = y - pixel
            self.w = w + 2 * pixel
            self.h = h + 2 * pixel
        return image, original

    def trim_image(self, img, initial):
        try:
            image, original = self.get_trim_size(img, initial)
            if image is None or original is None:
                raise ValueError(f"Failed to get trim size for image: {img}")
                
            # Ensure coordinates are within image bounds
            height, width = original.shape[:2]
            self.x = max(0, min(self.x, width - 1))
            self.y = max(0, min(self.y, height - 1))
            self.w = min(self.w, width - self.x)
            self.h = min(self.h, height - self.y)
            
            # Draw rectangle for debugging
            cv2.rectangle(image, (self.x, self.y), (self.x + self.w, self.y + self.h), (36, 255, 12), 2)
            
            # Ensure we have valid dimensions
            if self.w <= 0 or self.h <= 0:
                return original  # Return original if invalid dimensions
                
            crop = original[self.y:self.y + self.h, self.x:self.x + self.w]
            if crop is None or crop.size == 0:
                return original  # Return original if crop failed
                
            return crop
        except Exception as e:
            print(f"Error in trim_image: {str(e)}")
            # If anything fails, return the original image
            return cv2.imread(img)

    def write_drawing_title_block(self, draw_block_input):
        self.can.setFillColorRGB(0, 0, 0, alpha=1)
        self.can.setFont('SegoeUILight', 14)
        y_first_row = -777
        y_second_row = -806
        y_third_row = -831
        x_first_col = 440
        x_second_col = 810

        # project text
        self.can.drawString(x_first_col, y_first_row, draw_block_input[0])
        # client text
        self.can.drawString(x_first_col, y_second_row, draw_block_input[1])
        # scenario text
        self.can.drawString(x_first_col, y_third_row, draw_block_input[2])
        # slice location text
        self.can.drawString(x_second_col, y_first_row, draw_block_input[3])
        # date text
        self.can.drawString(x_second_col, y_second_row, draw_block_input[4])
        # drawn text
        self.can.drawString(x_second_col, y_third_row, draw_block_input[5])

    def write_color_bar(self, min_value, max_value):
        self.can.setFont('SegoeUILight', 12)
        difference = (max_value-min_value)/10
        x_location = 1130
        y_location = -823
        for i in range(11):
            self.can.drawString(x_location, y_location+78*i, f"{int(min_value+difference*i)}")

    def write_color_bar_unit(self):
        self.can.setFont('SegoeUILight', 7)
        x_location = 1110
        y_location = -18
        self.can.drawString(x_location, y_location, f"{self.slice_name.upper()} ({self.slice_unit})")

    def create_9_slice(self, n_slice, img_loc, t_difference, t_start, slice_min_value, slice_max_value, draw_block_input, crop):
        # Handle both directory paths and lists of image paths
        if isinstance(img_loc, list):
            img_list = img_loc
            folder_name = "output"
        else:
            img_list = [os.path.join(img_loc, f) for f in os.listdir(img_loc)]
            folder_name = os.path.basename(img_loc)
            
        # Verify first image can be read
        first_img = cv2.imread(img_list[0])
        if first_img is None:
            raise ValueError(f"Failed to read image: {img_list[0]}")
        im = first_img

        n_img = len(img_list)
        n_page = int(len(img_list) / n_slice)
        remaining_img = len(img_list) % n_slice

        img_width = 350
        img_height = 200

        # Create output directory if it doesn't exist
        os.makedirs(self.output_loc, exist_ok=True)

        repeat = n_page if n_img % 9 == 0 else n_page + 1
        for i in range(repeat):
            # Create Canvas
            self.packet = io.BytesIO()
            self.can = canvas.Canvas(self.packet, pagesize=A3)
            self.can.saveState()

            # Write Drawing Title Blocks and Color bar
            self.write_drawing_title_block(draw_block_input)
            self.write_color_bar(slice_min_value, slice_max_value)
            self.write_color_bar_unit()

            rep = remaining_img if i == n_page else 9
            for j in range(rep):
                text_x_location = 145 if t_start + (i * 9 + j) * t_difference < 100 else 140
                
                img_file = img_list[i * 9 + j]
                if crop:
                    initial = True if i == 0 and j == 0 else False
                    im = self.trim_image(img_file, initial)
                    if im is None:
                        raise ValueError(f"Failed to trim image: {img_file}")
                    crop_image_loc = os.path.join('temp', f'{i}_{j}.png')
                    os.makedirs('temp', exist_ok=True)
                    success = cv2.imwrite(crop_image_loc, im)
                    if not success:
                        raise ValueError(f"Failed to write cropped image: {crop_image_loc}")
                else:
                    crop_image_loc = img_file
                    im = cv2.imread(img_file)
                    if im is None:
                        raise ValueError(f"Failed to read image: {img_file}")

                offset_x = img_height/im.shape[0]*im.shape[1]
                offset_y = img_width/im.shape[1]*im.shape[0]

                x_location_1 = [0, 366, 367, -733, 366, 367, -733, 366, 367]
                x_location_2 = [img_width/2-offset_x/2, 366, 367, -733, 366, 367, -733, 366, 367]
                y_location_1 = [-img_height/2-offset_y/2-15, 0, 0, -250, 0, 0, -254, 0, 0]
                y_location_2 = [-img_height-5, 0, 0, -250, 0, 0, -254, 0, 0]

                text_loc_i = -248 - y_location_1[0]
                text_y_location = [text_loc_i, text_loc_i, text_loc_i,
                                 text_loc_i - 3, text_loc_i - 3, text_loc_i - 3,
                                 text_loc_i + 3, text_loc_i + 3, text_loc_i + 3]
                text_x_location2 = text_x_location/2
                text_y_location2 = [-43, -43, -43, -47, -47, -47, -40, -40, -40]

                if im.shape[0] < im.shape[1] and im.shape[0] < 0.7 * im.shape[1]:
                    self.can.translate(x_location_1[j], y_location_1[j])
                    self.can.drawImage(crop_image_loc, 13, 0, width=img_width, preserveAspectRatio=True, mask='auto',
                                     anchor='sw')
                    self.can.setFillColorRGB(0, 0, 0)
                    self.can.setFont('SegoeUILight', 16)
                    self.can.drawString(text_x_location, text_y_location[j], 
                                      f'{t_start + (i * 9 + j) * t_difference} Seconds')
                else:
                    self.can.translate(x_location_2[j], y_location_2[j])
                    self.can.drawImage(crop_image_loc, 15, -12, height=img_height, preserveAspectRatio=True, mask='auto',
                                     anchor='sw')
                    self.can.setFillColorRGB(0, 0, 0)
                    self.can.setFont('SegoeUILight', 16)
                    self.can.drawString(text_x_location2, text_y_location2[j], 
                                      f'{t_start + (i * 9 + j) * t_difference} Seconds')

            self.can.restoreState()
            self.can.save()

            # move to the beginning of the StringIO buffer
            self.packet.seek(0)
            new_pdf = PdfReader(self.packet)

            # read your template PDF
            file_template = os.path.join('template', f'9_{self.slice_cat}.pdf')
            existing_pdf = PdfReader(open(file_template, "rb"))

            # add the "watermark" (which is the new pdf) on the existing page
            page = existing_pdf.pages[0]
            output = PdfWriter()
            page.merge_page(new_pdf.pages[0])
            output.add_page(page)

            # Create output filename
            if repeat == 1:
                output_filename = self.output_name
            else:
                base, ext = os.path.splitext(self.output_name)
                output_filename = f"{base}_{i}{ext}"
            # Sanitize filename to avoid invalid path issues
            output_filename = os.path.basename(output_filename)
            # Write to the specified output location
            output_path = os.path.join(self.output_loc, output_filename)
            outputStream = open(output_path, "wb")
            output.write(outputStream)
            outputStream.close()
            print(f"Created PDF: {output_path}")

        # Clean up temporary files
        if os.path.exists('temp'):
            for f in os.listdir('temp'):
                os.remove(os.path.join('temp', f))
            os.rmdir('temp') 