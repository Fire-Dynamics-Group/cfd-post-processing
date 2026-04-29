import json
import os
import shutil
from PIL import Image
from PIL import ImageChops
from pdfgeneration import apply_overlay
from pdfgeneration import concatenate
from pdfgeneration import generate_overlay

from config import TEMPLATE_DIR

ALLOWED_FILE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def get_template_list():
    template_paths = []

    template_path = os.path.join(os.path.dirname(__file__), "templates/config")

    for filename in os.listdir(template_path):
        if os.path.splitext(filename)[1] not in [".json"]:
            continue

        template_paths.append(filename.replace(".config.json", ""))

    return template_paths


def get_source_images(source_dir):
    source_image_paths = []

    for filename in os.listdir(source_dir):
        if os.path.splitext(filename)[1] not in ALLOWED_FILE_EXTENSIONS:
            continue

        source_image_paths.append(os.path.join(source_dir, filename))

    return source_image_paths


def get_template_config(template_name):
    template_path = os.path.join(TEMPLATE_DIR, "config", template_name + ".config.json")

    with open(template_path) as template_file:
        return json.loads(template_file.read())


def trim_image(im):
    bg = Image.new(im.mode, im.size, im.getpixel((0,0)))
    diff = ImageChops.difference(im, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)


def crop_images(metric_source_dir, metric_target_dir, template):
    for image_path in get_source_images(metric_source_dir):
        img = Image.open(image_path)

        height, width = img.height, img.width

        image_crop_right = template["image_crop"]["right"]
        image_crop_bottom = template["image_crop"]["bottom"]

        im2 = img.crop(box=(0, 0, width - image_crop_right, height - image_crop_bottom))
        im2 = trim_image(im2)

        save_path = os.path.join(metric_target_dir, os.path.split(image_path)[1])
        im2.save(save_path)


def create_metric_temp_dirs(tmp_dir, metric):
    dirs = {
        "images": os.path.join(tmp_dir, metric, "images"),
        "overlays": os.path.join(tmp_dir, metric, "overlays"),
        "merged": os.path.join(tmp_dir, metric, "merged"),
    }

    for d in dirs:
        os.makedirs(dirs[d])

    return dirs


def generate_report(source_dir, target_dir, template_name):
    temp_dir = os.path.join(target_dir, "tmp")

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    os.makedirs(temp_dir, exist_ok=True)

    template_config = get_template_config(template_name)

    num_images_per_template = len(template_config["image_coords"])

    for metric_name in os.listdir(source_dir):
        metric_temp_dirs = create_metric_temp_dirs(temp_dir, metric_name)
        metric_source_dir = os.path.join(source_dir, metric_name)

        crop_images(metric_source_dir, metric_temp_dirs["images"], template_config)

        image_filenames = {
            round(float(filename.split("_")[-1].split("s.")[0])): filename
            for filename
            in os.listdir(metric_temp_dirs["images"])
        }

        sorted_image_times = sorted(list(image_filenames.keys()))

        start_index = 0
        end_index = num_images_per_template
        overlay_number = 0

        num_files = len(os.listdir(metric_temp_dirs["images"]))

        while True:
            generate_overlay(
                metric_temp_dirs,
                template_config,
                image_filenames,
                sorted_image_times[start_index: end_index],
                overlay_number,
            )

            if end_index >= num_files:
                break

            start_index = end_index
            end_index = start_index + num_images_per_template
            overlay_number += 1

        apply_overlay(TEMPLATE_DIR, template_name, metric_name, metric_temp_dirs)

    to_concatenate = []

    merged_paths = [os.path.join(temp_dir, folder, "merged") for folder in os.listdir(temp_dir)]

    for merged_path in merged_paths:
        keyed_merged_paths = {
            int(os.path.splitext(os.path.split(p)[-1])[0]): p
            for p
            in os.listdir(merged_path)
            if os.path.splitext(p)[1] == ".pdf"
        }

        to_concatenate.extend([
            os.path.join(merged_path, filename)
            for filename
            in [keyed_merged_paths[key] for key in sorted(keyed_merged_paths)]
        ])

    output_path = os.path.join(target_dir, "output.pdf")

    concatenate(to_concatenate, output_path)


if __name__ == "__main__":
    source_dir = r"C:\Users\IanShaw\Dropbox\Projects CFD\59. Riber Castle\Riber_Castle_Test3"
    target_dir_root = "Documents"
    template_names = [
        "Single Slice File - 1",
        "Long Slice Files - 5",
        "Standard Slice Files - 9",
    ]

    for i in range(len(template_names)):
        template_name = template_names[i]
        target_dir = os.path.join(target_dir_root, str(i))

        generate_report(source_dir, target_dir, template_name)

