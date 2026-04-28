import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape
from reportlab.lib.pagesizes import A4, A3
from reportlab.lib.units import cm

from pdfrw import PageMerge
from pdfrw import PdfReader
from pdfrw import PdfWriter


def generate_overlay(metric_temp_dirs, template_config, image_filenames, sorted_image_times, overlay_number):
    c = canvas.Canvas(
        os.path.join(metric_temp_dirs["overlays"], "%s.pdf" % overlay_number),
        pagesize=landscape(A3)
    )

    image_coords_list = template_config["image_coords"]
    time_textbox_coords_list = template_config["time_textbox_coords"]

    for i in range(len(image_coords_list)):
        image_coords = image_coords_list[i]
        time_textbox_coords = time_textbox_coords_list[i]

        if i >= len(sorted_image_times):
            break

        image_filename = image_filenames[sorted_image_times[i]]

        height = image_coords[3] - image_coords[1]
        width = image_coords[2] - image_coords[0]

        x, y = image_coords[0:2]

        time_x = time_textbox_coords[0] + (time_textbox_coords[2] - time_textbox_coords[0]) / 2
        time_y = time_textbox_coords[1] + (time_textbox_coords[3] - time_textbox_coords[1]) / 2 - 0.15

        time = round(float(os.path.splitext(image_filename)[0].split("_")[-1][:-1]) / 5) * 5

        c.drawCentredString(
            time_x * cm,
            time_y * cm,
            str(time) + " Seconds",
        )

        c.drawImage(
            os.path.join(metric_temp_dirs["images"], image_filename),
            x * cm,
            y * cm,
            width * cm,
            height * cm,
            preserveAspectRatio=True,
        )

    c.rotate(270)
    c.save()


def get_pdf_info(path):
    pdf = PdfReader(path)

    print(pdf.keys())
    print(pdf.Info)
    print(pdf.Root.keys())


def concatenate(paths, output):
    writer = PdfWriter()

    for path in paths:
        reader = PdfReader(path)

        writer.addpages(reader.pages)

    writer.write(output)


def apply_overlay(template_dir, template_name, metric_name, metric_temp_dirs):
    template_path = os.path.join(template_dir, "%s - %s.pdf" % (template_name, metric_name))

    for filename in os.listdir(metric_temp_dirs["overlays"]):
        base_pdf = PdfReader(template_path)
        overlay_pdf = PdfReader(os.path.join(metric_temp_dirs["overlays"], filename))
        overlay_page = overlay_pdf.pages[0]
        overlay_page.rotate = None

        base_page = base_pdf.pages[0]
        merger = PageMerge(base_page)
        merger.add(overlay_page).render()

        writer = PdfWriter()
        writer.write(os.path.join(metric_temp_dirs["merged"], filename), base_pdf)


class DimensionParams(object):
    def __init__(self, start, shift, n):
        self.start = start
        self.shift = shift
        self.n = n

    def get_value(self, i):
        return self.start + self.shift * i


class ImageDimensions(object):
    def __init__(self, width, height):
        self.width = width
        self.height = height
