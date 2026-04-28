import re
from PIL import Image, ImageDraw, ImageFont
import os
'''
TODO: pick up stairs
sometimes called step1; step2
STEP1; STEP2    
othertimes not??
'''

def create_legend(legend_object, save_dir, file_name='legend.png'):
    # Font for text in the legend
    font_location = 'SEGOEUIL.TTF'#'C:\Windows\Fonts\Segoe UI\SEGOEUIL.TTF.ttf' #SEGOEUIL.TTF
    font = ImageFont.truetype(font_location, 16)
    # font = ImageFont.load_default()

    # Calculate the size of the legend image
    # find max width of text in legend
    labels = [legend_object[f]['label'] for f in legend_object]
    max_label_width = max([len(f) for f in labels]) * 5
    box_height = 20
    box_width = 20
    padding = 5
    text_padding = 40

    def find_col_max_width(indexes, labels):
        max_width = 0
        for i in indexes:
            if len(labels[i]) > max_width:
                max_width = len(labels[i])
        return max_width
    
    first_col_indexes = [f for f in range(len(labels)) if f % 4 ==0]
    second_col_indexes = [f for f in range(len(labels)) if f % 4 ==1]
    third_col_indexes = [f for f in range(len(labels)) if f % 4 ==2]
    fourth_col_indexes = [f for f in range(len(labels)) if f % 4 ==3]

    # change width and height about
    single_label_width = box_width + text_padding + padding * 4 + max_label_width
    legend_width = single_label_width * 4
    single_label_height = box_height + padding
    legend_height = 3 * (box_height + padding) + 2*padding
    max_label_widths = [(find_col_max_width(indexes, labels)*20 + padding + box_width) for indexes in [first_col_indexes, second_col_indexes, third_col_indexes, fourth_col_indexes]]

    # Create a new image for the legend
    legend_img = Image.new('RGB', (legend_width, legend_height), color = (255, 255, 255))
    d = ImageDraw.Draw(legend_img)

    # Starting position for the legend
    x_pos = [10, (max_label_widths[0] + 10), max_label_widths[1], max_label_widths[2] + max_label_widths[0] + 10]
    # x_pos = [x_pos[0],x_pos[1] ]
    y_pos = [10, single_label_height + 10, single_label_height + 10, single_label_height + 10]
    # x = 10
    y = 10
    counter = 0
    # Draw each item in the legend
    '''
        # TODO: more space per letter; less blank space
        change sizes of inserted legend and figures
    '''
    for name, sub_obj in legend_object.items():
        if sub_obj['points']:
            x = x_pos[counter % 4]
            y = y_pos[counter // 4]
            # Draw the color box
            if "leakage" in name.lower():
                d.line([x, (y+box_height/2), x + box_width, (y+box_height/2)], fill=sub_obj['legend_color'], width=5)
            elif sub_obj['shape'] == 'rect':
                if "door" in name.lower():
                    width = 4
                else:
                    width = 1
                d.rectangle([x, y, x + box_width, y + box_height], fill=sub_obj['color'], outline=sub_obj['outline'], width=width)
            else:
                d.ellipse([x, y, x + box_width, y + box_height], fill=sub_obj['color'], outline=sub_obj['outline'])

            # Draw the label text
            d.text((x + box_width + padding, y), sub_obj['label'], fill=(0,0,0), font=font)

            # Move to the next item position
            # move x to the right

            # y += box_height + padding
            counter += 1

    if save_dir:
        save_path = f"{save_dir}/{file_name}"
    else:
        save_path = file_name
    # Save the legend image
    # if __name__ == "__main__":
    #     legend_img.show()

    legend_img.save(save_path)

# TODO: scale for largest dimension (width or height)
def fds_draw(
        path_to_fds_file,
        save_dir,
        folder_name=None,
        z_cutoff_min=None,
        z_cutoff_max=None
):
        # -*- coding: utf-8 -*-

    border_width = 0
    #### Variables
    # find floor height; to cut off z
    # find main mesh z bottom and top
    # find fire location -> find mesh with fire init for z cutoff -> check that fire within bounds
    image_width = 1180
    image_width = 7650
    # z_cut_low = -0.1
    # z_cut_high = 6.0
    import os
    base_name = os.path.basename(path_to_fds_file)
    # remove .fds
    base_name = base_name.split('.')[0]
        
    file_name = base_name + '_drawing.png'
    if folder_name:
        file_name = folder_name + file_name
    # save_dir = 'dev_folder'
    # Initialize an empty list to store the coordinates of obstructions
    obstruction_coordinates = []
    fire_locations = []
    sprinkler_locations = []
    sensor_locations = []
    aov_locations = []
    inlet_locations = []
    mech_vent_locations = []
    flat_door_locations = []
    stair_door_locations = []
    misc_door_locations = []
    door_leakage_locations = []
    smoke_sensors = []
    mesh_lines = []
    step_obstructions = []

    def is_numeric(s):
        try:
            float(s)
            return True
        except ValueError:
            return False
    # Open the .fds file for reading
    with open(path_to_fds_file, 'r') as fds_file:
        # Iterate through each line in the file

        for line in fds_file:
            # TODO: get fire floor meshes; use height and floor as z cutoffs
            line = line.replace(" ", "")
            # Check if the line contains "&OBST" and "XB="
            if "&OBST" in line and "XB=" in line:
                if "Fire" in line and "SURF_IDS=" in line:
                    # extract coords for fire
                    xb_data = line.split("XB=")[1].split(",SURF")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    fire_locations.append(tuple(coordinates))
                    # TODO: find mesh max and min
                    pass
                else:
                    if "COLOR=" in line:
                        pass
                    # Extract the part of the line between "XB=" and "/"
                    xb_data = line.split("XB=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    # Split the coordinates into a list
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)][:6]
                    if "STEP" in line:
                        step_obstructions.append(tuple(coordinates)) # cutoff - 2m + 2m
                    # Append the coordinates to the list of obstructions
                    obstruction_coordinates.append(tuple(coordinates))
            
            elif "&DEVC" in line:
                if "SPRK" in line:
                    xb_data = line.split("XYZ=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    sprinkler_locations.append(tuple(coordinates))
                if "QUANTITY='" in line and "time" not in line.lower():
                    xb_data = line.split("XYZ=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    # xb_data = line.split("XYZ=")[1].split(",QUANTITY")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    sensor_locations.append(tuple(coordinates))
                if 'smoke' in line.lower():
                    xb_data = line.split("XYZ=")[1]
                    xb_data = re.split("/|,QUANTITY", xb_data)[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    smoke_sensors.append(tuple(coordinates))
            elif "&HOLE" in line:
                if "AOV" in line:
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    aov_locations.append(tuple(coordinates))
                elif "inlet" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    inlet_locations.append(tuple(coordinates))
                elif "door" in line.lower():
                    if "apt" in line.lower() or "apartment" in line.lower():
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        flat_door_locations.append(tuple(coordinates))
                    elif "stair" in line.lower():
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        stair_door_locations.append(tuple(coordinates))
                    else:
                        xb_data = line.split("XB=")[1].split("/")[0]
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                        misc_door_locations.append(tuple(coordinates))
            elif "&VENT" in line:
                if "inlet" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    mech_vent_locations.append(tuple(coordinates))
                elif "extract" in line.lower():
                    xb_data = line.split("XB=")[1].split("/")[0]
                    coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)]
                    mech_vent_locations.append(tuple(coordinates))
                elif "door" in line.lower():
                    if "top" in line.lower(): # if 2 top vents -> then not front door
                        # for now add all top vents to doors
                        xb_data = line.split("XB=")[1]
                        xb_data = re.split("/|,QUANTITY", xb_data)[0]
                        # Split the coordinates into a list
                        coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)][:6]
                        door_leakage_locations.append(tuple(coordinates))
            elif "&MESH" in line:
                xb_data = line.split("XB=")[1]
                xb_data = re.split("/|,QUANTITY", xb_data)[0]
                # Split the coordinates into a list
                coordinates = [float(coord) for coord in xb_data.split(',') if is_numeric(coord)][:6]
                mesh_lines.append(coordinates)

    fire_x1, fire_x2, fire_y1, fire_y2, fire_z1, fire_z2 = fire_locations[0] 
    meshes_fire_floor = [f for f in mesh_lines if f[-2] <= fire_z2 and f[-1] >= fire_z2]
    # find max and min for fire floor
    fire_floor_min_z = min([min(f[-1], f[-2]) for f in meshes_fire_floor])
    fire_floor_max_z = max([max(f[-1], f[-2]) for f in meshes_fire_floor])
    all_obstructions = obstruction_coordinates + fire_locations + sprinkler_locations + sensor_locations + aov_locations + inlet_locations
    lowest_x = min(min(coords[0], coords[1]) for coords in meshes_fire_floor)
    lowest_y = min(min(coords[0], coords[1]) for coords in meshes_fire_floor)
    highest_x = max(max(coords[2], coords[3]) for coords in meshes_fire_floor)
    highest_y = max(max(coords[2], coords[3]) for coords in meshes_fire_floor)
    # Find the lowest x1 value among all tuples
    lowest_x1 = lowest_x

    # Find the highest x2 value among all tuples
    highest_x2 = highest_x-lowest_x1

    lowest_y1 = lowest_y

    highest_y2 = highest_y

    delta_x = highest_x - lowest_x
    delta_y = highest_y - lowest_y
    diff_deltas = abs(delta_x - delta_y)
    print(file_name)
    print(f"delta_x: {delta_x}, delta_y: {delta_y}, diff_deltas: {diff_deltas}")
    print(f"lowest_x1: {lowest_x1}, lowest_y1: {lowest_y1}, highest_x2: {highest_x2}, highest_y2: {highest_y2}")

    # # Adjust image size to include the border
    b_width = 400
    image_width = image_width + 2 * b_width
    image_height = image_width + 2 * b_width
    if delta_x > delta_y:
        scale_denom = delta_x
        y_bump = delta_y*(1-(delta_y/delta_x))
        x_bump = 0
    else:
        scale_denom = delta_y
        y_bump = 0
        x_bump = delta_x*(1-(delta_x/delta_y))
    # Calculate the scaling factor for x1, x2, y1, y2
    scaling_factor = image_width # same as height
    # y_bump = 0
    def convert_single_point(coordinates, scaling_factor):
        updated_coordinates = []
        for coords in coordinates:
            x, y, z = coords
            x -= lowest_x1 # essentially lowest x starts at zero
            x += x_bump
            y+= y_bump
            y = highest_y2 - y # flip y - highest y should now be zero 
            x = int(x/scale_denom * scaling_factor) + b_width
            y = int(y/scale_denom * scaling_factor) + b_width
            updated_coordinates.append((x, y, z))
        return updated_coordinates
    # Process the coordinates and update the list of tuples
    def convert_points(coordinates, scaling_factor):
        updated_coordinates = []
        for coords in coordinates:
            x1, x2, y1, y2, z1, z2 = coords
            # Subtract the lowest x1 and y1 values and adjust y coordinates
            x1 -= lowest_x1
            x2 -= lowest_x1
            x1 += x_bump
            x2 += x_bump
            y1 += y_bump
            y1 = highest_y2 - y1
            y2 += y_bump
            y2 = highest_y2 - y2
            # Scale and convert to pixels
            x1 = int(x1/(scale_denom) * scaling_factor) + b_width
            x2 = int(x2/(scale_denom) * scaling_factor) + b_width
            y1 = int(y1/(scale_denom) * scaling_factor) + b_width
            y2 = int(y2/(scale_denom) * scaling_factor) + b_width
            y1, y2 = min(y1, y2), max(y1, y2)
            x1, x2 = min(x1, x2), max(x1, x2)
            updated_coordinates.append((x1, x2, y1, y2, z1, z2))


        # Sort the list of tuples based on the z2 values in ascending order
        sorted_obstruction_coordinates = sorted(updated_coordinates, key=lambda x: x[5])
        return sorted_obstruction_coordinates

    z_extent_threshold = 0.5  # Adjust this based on your specific scale or criteria

    # Filter obstructions to exclude floor slabs, focusing on z-dimension differences
    obstruction_coordinates = [f for f in obstruction_coordinates if abs(f[4] - f[5]) > z_extent_threshold]
    obstruction_coordinates = convert_points(obstruction_coordinates, scaling_factor)
    meshes_fire_floor = convert_points(meshes_fire_floor, scaling_factor)
    fire_locations = convert_points(fire_locations, scaling_factor)
    aov_locations = convert_points(aov_locations, scaling_factor)
    inlet_locations = convert_points(inlet_locations, scaling_factor)
    mech_vent_locations = convert_points(mech_vent_locations, scaling_factor)
    flat_door_locations = convert_points(flat_door_locations, scaling_factor)
    stair_door_locations = convert_points(stair_door_locations, scaling_factor)
    misc_door_locations = convert_points(misc_door_locations, scaling_factor)
    door_leakage_locations = convert_points(door_leakage_locations, scaling_factor)

    smoke_sensors = convert_single_point(smoke_sensors, scaling_factor)
    sprinkler_locations = convert_single_point(sprinkler_locations, scaling_factor)
    sensor_locations = convert_single_point(sensor_locations, scaling_factor)

    lowest_x1 = int(min(min(coords[0], coords[0]) for coords in meshes_fire_floor))
    lowest_y1 = int(min(coords[2] for coords in meshes_fire_floor))
    highest_y2 = int(max(coords[3] for coords in meshes_fire_floor))
    # Find the highest x2 value among all tuples
    highest_x2 = int(max(min(coords[1], coords[1]) for coords in meshes_fire_floor))


    # TODO: find mesh max and min with fire
    z_cut_low = fire_locations[0][-2] - 0.3
    z_cut_high = fire_locations[0][-1] + 3

    background_color = (255, 255, 255)  # White

    # Create an Image object
    width_image = int(highest_x2 + 2*b_width)
    height_image = int(highest_y2 + 2*b_width)
    image = Image.new("RGB", (width_image, height_image), background_color)

    # Create a drawing object to draw on the image
    draw = ImageDraw.Draw(image)

    # Define colors for rectangles
    outline_color = (64, 64, 64)  # Dark grey
    fill_color = (192, 192, 192)  # Light grey

    print(obstruction_coordinates)
    delta_for_holes = 0.19
    # Iterate through the list of coordinates and draw rectangles
    '''
        TODO: have cutoff z for obstructions etc
        get working for obst first then rect and circles
    '''
    def draw_circle(list, outline_color, fill_color, z_min, z_max, radius=80):
        for coords in list:
            x, y, z = coords
            if z >= z_min and z <= z_max:
                right_lower = (int(x) + radius, int(y) + radius) 
                left_upper = (int(x) - radius, int(y) - radius)
                draw.ellipse([left_upper, right_lower], outline=outline_color, fill=fill_color, width=5)

    def draw_rect(list, outline_color, fill_color, z_min, z_max, line_width=20, show_despite_z=False):
        for coords in list:
            x1, x2, y1, y2, z1, z2 = coords
            on_level = min(z1,z2) >= z_min and max(z1, z2) <= z_max
            if show_despite_z or on_level:
                left_upper = (int(x1), int(y1)) 
                right_lower = (int(x2), int(y2))
                draw.rectangle([left_upper, right_lower], outline=outline_color, fill=fill_color, width=line_width)

    def draw_obstructions(z_min, z_max, obst_coords=obstruction_coordinates):
        for coords in obst_coords:
            x1, x2, y1, y2, z1, z2 = coords 
            on_level = min(z1,z2) >= z_min and max(z1, z2) <= z_max
            if on_level:
                left_upper = (int(x1), int(y1))
                right_lower = (int(x2), int(y2))
                draw.rectangle([left_upper, right_lower], outline=outline_color, fill=fill_color)

    legend_object = {
        "fire": {
            "color": "red",
            "label": "Fire",
            "outline": "black",
            "width": 20,
            "shape": "rect",
            "points": fire_locations,
            "render_last": False  
        },
        "sprinkler": {
            "color": "blue",
            "label": "Suppression Head",
            "outline": "blue",
            "width": 10,
            "radius": 40,
            "shape": "circle",
            "points": sprinkler_locations,
            "render_last": True        
        },
        "sensor": {
            "color": "yellow",
            "label": "Point Sensor",
            "outline": "black",
            "width": 10,
            "radius": 40,
            "shape": "circle",
            "points": sensor_locations,  
            "render_last": True    
        },
        "aov": {
            "color": "white",
            "label": "AOV",
            "outline": "black",
            "width": 20,
            "shape": "rect",
            "points": aov_locations,
            "render_last": True
        },
        "inlet": {
            "color": "darkorange",
            "label": "Natural Air Inlet",
            "outline": "black",
            "width": 20,
            "shape": "rect",
            "points": inlet_locations,
            "render_last": False
        },
        "mech_vent": {
            "color": "green",
            "label": "Mechanical Extract (m3/s)", # change to include volume e.g. 4m3/s
            "outline": "green",
            "width": 20,
            "shape": "rect",
            "points": mech_vent_locations,
            "render_last": True
        },
        "flat_door": {
            "color": "black",
            "label": "Door",
            "outline": "green",
            "legend_outline_width": 40,
            "width": 20,
            "shape": "rect",
            "points": flat_door_locations,
            "render_last": False
        },
        "stair_door": {
            "color": "black",
            "label": "Stair Door",
            "legend_outline_width": 40,
            "outline": "blue",
            "width": 20,
            "shape": "rect",
            "points": stair_door_locations,
            "render_last": False
        },
        "misc_door": {
            "color": "green",
            "label": "Door",
            "outline": "black",
            "width": 1000,
            "shape": "rect",
            "points": misc_door_locations,
            "render_last": False
        },
        "door_leakage": {
            "color": "black",
            "label": "Door Leakage",
            "outline": "orange",
            "width": 25,
            "shape": "rect",
            "legend_shape": "line",
            "legend_color": "orange",
            "points": door_leakage_locations,
            "render_last": True
        },
        "mesh": {
            "color": None,
            "label": "Mesh",
            "outline": 'darkorchid',
            "width": 0.1,
            "shape": "rect",
            "points": meshes_fire_floor,
            "render_last": True
        },
        "smoke_sensors": {
            "color": "green",
            "label": "Smoke Detector",
            "outline": "black",
            "width": 10,
            "radius": 40,
            "shape": "circle",
            "points": smoke_sensors,
            "render_last": True
        }
    }
    z_min=fire_floor_min_z-4*delta_for_holes
    z_max=fire_floor_max_z+4*delta_for_holes
    # TODO: have higher z cutoff for stairs?? -> see if step is in the name
    if z_cutoff_min:
        z_min = z_cutoff_min-delta_for_holes 
    if z_cutoff_max:
        z_max = z_cutoff_max+delta_for_holes

    create_legend(legend_object, save_dir, f'{folder_name}_{base_name}_legend.png')

    def create_figure(legend_object, z_min, z_max, obstructions_rendered=False):
        for name, sub_obj in legend_object.items():
            if "leakage" in name and sub_obj['points']:
                pass
            if sub_obj['render_last'] and obstructions_rendered or not sub_obj['render_last'] and not obstructions_rendered:           
                if sub_obj['points']:
                    if sub_obj['shape'] == 'rect':
                        if name == 'mesh' or sub_obj['label'] == 'Fire' and len(sub_obj['points']) > 1:
                            # likely has rings
                            line_width = 1*5
                        elif name == 'door_leakage':
                            line_width = 25
                        else:
                            line_width = 5*10
                        if name == 'aov' or name == 'inlet':
                            show_despite_z = True
                        else:
                            show_despite_z = False
                        draw_rect(sub_obj['points'], sub_obj['outline'], sub_obj['color'], z_min, z_max, line_width, show_despite_z=show_despite_z)
                    else:
                        # if smaller delta between x and y, use smaller radius
                        draw_circle(sub_obj['points'], sub_obj['outline'], sub_obj['color'], z_min, z_max )
    create_figure(legend_object, z_min, z_max, obstructions_rendered=False)

    draw_obstructions(z_min, z_max)
    # draw steps
    create_figure(legend_object, z_min, z_max, obstructions_rendered=True)
    draw_obstructions(z_min-3, z_max+3, step_obstructions)
    if __name__ == "__main__":
        image.show()

    image.save(f"{save_dir}/{file_name}")

    return {"file_name": base_name, "height": height_image, "width": width_image}

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches

def create_inline_image(image_file, template, width=Inches(6), height=Inches(6)):
    return InlineImage(template, image_descriptor=image_file, width=width, height=height)

def create_scenarios_object(
                            proj_dir, 
                            doc, 
                            scenarios = ['Lounge_Fire_1', 'Lounge_Fire_2'], 
                            figure_objects = [{"width": 11268, "height":9470}]
                            ):
    scen_obj = []

    for idx, scenario in enumerate(scenarios):
        # remove underscores
        figure_object = figure_objects[0]
        width = figure_object['width']
        height = figure_object['height']
        # scenario = scenario.replace("_", " ")
        scen_dir = f"{proj_dir}\\{scenario}" # need to add underscores instead of spaces
        scen_obj.append(return_scenario_figure(scen_dir, doc, width, height, idx))
    return scen_obj

def return_scenario_figure(scen_dir, doc, width, height, index=0):
    scen_name = os.path.basename(scen_dir)
    root_path = os.path.dirname(scen_dir)
    current_scen_data = {
                        "index": index+1, 
                        "name": scen_name, 
                        "figure": {}, 
                        "legend": {}, 
                        }
    # create chart object for each
    # for now same object each time
    # find CC1 and legend.png in file name
    def is_drawing(file):
        return "legend" not in file and "drawing.png" in file
    def is_legend(file):
        return "legend.png" in file and "drawing" not in file

    height = 6 * (height/(width+height))
    legend_height = 2
    legend_width = 0.9
    for file in os.listdir(root_path): # needs to look in root folder or save images in sub 
        # loop through only drawing and legend
        if scen_name in file:
            if "legend.png" in file or "drawing.png" in file:
                if is_drawing(file):
                    image = create_inline_image(f"{root_path}/{file}", doc, width=Inches(6), height=Inches(height*2)) # should be taller
                    key = "figure"
                else:
                    image = create_inline_image(f"{root_path}/{file}", doc, width=Inches(legend_width*4), height=Inches(legend_height/4))
                    key = "legend"


                current_scen_data[key] = image
   
    return current_scen_data
 
def run_sub_report_draw():

    path_to_template = r'C:\Users\IanShaw\localProgramming\fd\templates\Drawing Report Template.docx'
    output_filename = r'C:\Users\IanShaw\localProgramming\fd\templates\output.docx'
    doc = DocxTemplate(path_to_template)
    scenarios = [ 
        "Lounge Fire 1", # perhaps return for single scenario at at time?
        "Lounge Fire 2"
    ]
    folder_path = r'CFD Test Output\test report folder'

    scen_obj = []
    for i in range(len(scenarios)):
        current_scen_data = {"index": i+1, "name": scenarios[i], "CC1_figure": {}, "CC1_figure": {},"PD1_figure": {},"PD2_figure": {}}
        current_scen_data["CC1_legend"] = create_inline_image(r'CFD Test Output\fds draw input report\CC1-2_legend.png', doc, width=Inches(1), height=Inches(2))
    
        current_scen_data["CC1_figure"] = create_inline_image(r'CFD Test Output\fds draw input report\Lounge_Fire_2-CC1-2_drawing.png', doc)
        scen_obj.append(current_scen_data)

    SCENARIO_DRAWINGS = scen_obj

    context = {
        "SCENARIO_DRAWINGS": SCENARIO_DRAWINGS
    }
    doc.render(context)
    doc.save(output_filename)

'''
    TODO: allow max and min z
'''
def run_report_draw(base_dir, folders=['Lounge_Fire_1', 'Lounge_Fire_2'], save_dir=None, z_min=None, z_max=None):
    # find all fds files
    # check if sub folders
    import os
    figure_objects = []
    # folders = []
    if not save_dir:
        save_dir = base_dir

    if folders:
        for folder in folders:
            folder_path = os.path.join(base_dir, folder)
            base_folder = os.path.basename(base_dir)
            for file in os.listdir(folder_path):
                if file.endswith(".fds"):
                    current = fds_draw(path_to_fds_file = rf"{folder_path}\{file}", save_dir = save_dir, folder_name = rf"{base_folder}-", z_cutoff_min=z_min, z_cutoff_max=z_max)
                    figure_objects.append(current)
                    # allow for further folders if nothing added
            if not figure_objects:    
                # for folder in folders:
                #     folder_path = os.path.join(base_dir, folder)
                for sub_folder in os.listdir(folder_path):
                        sub_folder_path = os.path.join(folder_path, sub_folder)
                        if os.path.isdir(sub_folder_path):
                            for file in os.listdir(sub_folder_path):
                            # find folders in folder
                                if file.endswith(".fds"):
                                    figure_objects.append(fds_draw(rf"{sub_folder_path}\{file}", folder_path, folder_name = rf"{base_folder}-{folder}-", z_cutoff_min=z_min, z_cutoff_max=z_max))
    else:
        for file in os.listdir(base_dir):
            if file.endswith(".fds"):
                current = fds_draw(path_to_fds_file = rf"{base_dir}\{file}", save_dir = save_dir, folder_name = rf"{base_folder}-", z_cutoff_min=z_min, z_cutoff_max=z_max)
                figure_objects.append(current)

    return figure_objects
def run_all_report_draw(doc, proj_dir, scenarios = ['Lounge_Fire_1', 'Lounge_Fire_2']):
    # scenarios should be taken from folder?? or sent in??
    figure_objects =run_report_draw(proj_dir, folders=scenarios) # creates figures in root folder
    # needs to change for scenario objects - one sub object
    SCENARIO_DRAWINGS = create_scenarios_object(proj_dir, doc, scenarios)
    return SCENARIO_DRAWINGS

'''
TODO: create exe file that changes any fds file to figure and legend
'''
if __name__ == "__main__":
    # Your code here
    import os
    path_to_template = r'C:\Users\IanShaw\localProgramming\fd\templates\Drawing Report Template.docx'
    output_filename = r'C:\Users\IanShaw\localProgramming\fd\templates\output.docx'
    doc = DocxTemplate(path_to_template)
    proj_dir = r'CFD Test Output\test report folder'
    # figure_objects = run_sub_report_draw()
    proj_dir = r'C:\Users\IanShaw\Dropbox\Projects CFD\43. 28 Drayson Mews\28 Drayson Mews'
    # figure_objects = run_all_report_draw(doc, proj_dir, scenarios = ['Lounge_Fire_1', 'Lounge_Fire_2'])
    proj_dir = r'C:\Users\IanShaw\Dropbox\Projects CFD\45. Evelyn Court\EOM Models\Models for Report'

    figure_objects =run_report_draw(proj_dir, save_dir=r'CFD Test Output\fds draw test', z_min=0, z_max=6)

