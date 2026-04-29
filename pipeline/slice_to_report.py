from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches
import os
import fitz  # PyMuPDF
from PIL import Image, ImageChops
from pdfgeneration import generate_overlay, apply_overlay

def trim(im):
    bg = Image.new(im.mode, im.size, im.getpixel((0, 0)))
    diff = ImageChops.difference(im, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)
    else:
        return trim(im.convert('RGB'))

'''
    TODO: place images considering the legend and spacing between cells

'''


def create_metric_temp_dirs(tmp_dir, metric):
    dirs = {
        "images": os.path.join(tmp_dir, metric, "images"),
        "overlays": os.path.join(tmp_dir, metric, "overlays"),
        "merged": os.path.join(tmp_dir, metric, "merged"),
    }

    for d in dirs:
        os.makedirs(dirs[d])

    return dirs

def calculate_grid_centers(corner_points, tol=0.2):
    # corner_points: list of (x, y) in cm, any order
    def cluster_and_sort(coords, tol=0.2):
        coords = sorted(coords)
        clusters = []
        for c in coords:
            found = False
            for cluster in clusters:
                if abs(cluster - c) < tol:
                    found = True
                    break
            if not found:
                clusters.append(c)
        return sorted(clusters)

    unique_x = cluster_and_sort([p[0] for p in corner_points], tol)
    unique_y = cluster_and_sort([p[1] for p in corner_points], tol)

    # Build 4x4 grid: grid[row][col] = (x, y)
    grid = [[None for _ in range(4)] for _ in range(4)]
    for x, y in corner_points:
        col = min(range(4), key=lambda i: abs(unique_x[i] - x))
        row = min(range(4), key=lambda i: abs(unique_y[i] - y))
        grid[row][col] = (x, y)

    # Calculate centers for 9 boxes
    centers = []
    for i in range(3):  # rows
        for j in range(3):  # cols
            tl = grid[i][j]
            tr = grid[i][j+1]
            bl = grid[i+1][j]
            br = grid[i+1][j+1]
            x_center = (tl[0] + tr[0] + bl[0] + br[0]) / 4
            y_center = (tl[1] + tr[1] + bl[1] + br[1]) / 4
            centers.append((x_center, y_center))
    return centers

def add_images_to_pdf_template(template_path, images, output_path):
    # Open the Word template
    doc = DocxTemplate(template_path)
    
    # Create inline images with specified dimensions
    inline_images = []
    for img_path in images[:9]:  # Only process up to 9 images
        img = Image.open(img_path)
        img = trim(img)  # Trim whitespace
        temp_path = f"temp_img_{len(inline_images)}.png"
        img.save(temp_path)
        inline_images.append(InlineImage(doc, image_descriptor=temp_path, width=Inches(6), height=Inches(4)))
    
    # Create context with image placeholders
    context = {f"IMAGE{i+1}": img for i, img in enumerate(inline_images)}
    
    # Render the template
    doc.render(context)
    doc.save(output_path)
    
    # Clean up temporary files
    for i in range(len(inline_images)):
        temp_path = f"temp_img_{i}.png"
        if os.path.exists(temp_path):
            os.remove(temp_path)

# Paths
template_docx_path = "templates/Standard Slice Files - 9 - Temperature.docx"
output_docx_path = "output.docx"

# List of image paths (should be 9 images for a 3x3 grid)
images = ["image cleaner/test.png"] * 9  # Using the same image 9 times for testing

add_images_to_pdf_template(template_docx_path, images, output_docx_path)


def add_slice_to_report(startup_path = "output.docx"):
    document_path = "template_9_image.docx"

    from docxtpl import DocxTemplate
    doc = DocxTemplate(document_path)
    # insert image
    def create_inline_image(image_file, template=doc, width=Inches(6), height=Inches(4)):
        return InlineImage(template, image_descriptor=image_file, width=width, height=height)
    # FDAI_grey.png
    first_chart = create_inline_image("outputSlices\FS_10_CoreB1_FSA\SOOT VISIBILITY_xslice0@60.00445secs_chart.png")

    context = {
        "IMAGE1": first_chart
        }
    
    import os
    doc.render(context)
    doc.save(startup_path) 
    os.startfile(startup_path)

# Example usage
add_slice_to_report()