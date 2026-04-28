import fdsreader as fds
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import os
from PIL import Image, ImageChops
from os import listdir


'''
    where are the templates??
'''


# Trimming function
def trim(im):
    bg = Image.new(im.mode, im.size, im.getpixel((0, 0)))
    diff = ImageChops.difference(im, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return im.crop(bbox)
    else:
        # Failed to find the borders, convert to "RGB"
        return trim(im.convert('RGB'))

# Function to trim and save image without resizing
def trim_and_save_image(image_path):
    with Image.open(image_path) as img:
        # Trim the white space
        trimmed_img = trim(img)
        
        # Save the trimmed image in PNG format
        trimmed_img.save(image_path, format='PNG')

# Function to save chart in high resolution and then trim the image
def save_chart_high_res(name_of_chart, new_dir_path, dpi=1200):
    if not os.path.exists(new_dir_path):
        os.makedirs(new_dir_path)
    
    file_path = f'{new_dir_path}/{name_of_chart}_chart.png'
    if os.path.exists(file_path):
        os.remove(file_path)
    plt.savefig(file_path, format='png', dpi=dpi)
    plt.close()
    
    # Trim the saved image without resizing
    trim_and_save_image(file_path)


quantity_types = ["PRESSURE", "SOOT VISIBILITY", "TEMPERATURE", "VELOCITY"]
quantity_type_config = {
    "TEMPERATURE": {
        "v_max": 60,
        "v_min": 20,
        "units": "°C",
        "cbar_reverse": False,
        "chart_name": 'Temperature',
        "tenable_limit_moe": 60,
    },
    "SOOT VISIBILITY": {
        "v_max": 10,
        "v_min": 0,
        "units": "m",
        "cbar_reverse": True,
        "chart_name": 'Visibility',
        "tenable_limit_moe": 10,
    },
    "PRESSURE": {
        "v_max": 0,
        "v_min": -100,
        "units": "Pa",
        "cbar_reverse": True,
        "chart_name": 'Relative Pressure',
        "tenable_limit_moe": -60,
    },
    "VELOCITY": {
        "v_max": 10,
        "v_min": 0,
        "units": "m/s",
        "cbar_reverse": False,
        "chart_name": 'Velocity',
        "tenable_limit_moe": 5,        
    }
    }
door_openings = {'opening_apartment': 150.0, 'closing_apartment': 170.0, 'opening_stair': 160.0, 'closing_stair': 180.0}


def return_2d_slices(path_to_directory):
    array = []
    slice_array = []
    sim = fds.Simulation(path_to_directory)
    t_slice = sim.slices
    for i in range(len(str(t_slice))-1):
    # end 1 before end
        char = str(t_slice)[i]
        next_char = str(t_slice)[i+1] 
        if char == "2" and next_char == "D":
            array.append("twoD")
        elif char == "3" and next_char == "D":
            array.append("threeD")
    for twoD_slice in [i for i, x in enumerate(array) if x == "twoD"]:
        slc = t_slice[twoD_slice]
        slice_array.append(slc)
    return slice_array

def obtain_slice(path_to_directory = r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final\L1_East_Core_FSA", door_openings=door_openings, t_max=300, t_start=60, interval_secs=40, save_in_cfd_folder=False, save_path=None, time_intervals=[60, 120, 180, 240, 300], slices_chosen=[0, 1, 2, 3]):
    # sim = fds.Simulation("./Graph_MoE_Test")
    
    sim = fds.Simulation(path_to_directory)
    def file_name_from_path(file_path):
        return os.path.splitext(os.path.basename(file_path))[0]

    project_name = os.path.basename(path_to_directory)
    if "office" not in project_name.lower():
        t_max = 300
    # create new folder
    if not save_in_cfd_folder:
        base_dir_path = '.\outputSlices'
        new_dir_path = f'{base_dir_path}\{project_name}'
    else:
        new_dir_path = f'{save_path}\{project_name}'

    print(f"\nSaving slices to: {os.path.abspath(new_dir_path)}")
    
    if not os.path.isdir(new_dir_path):
        os.mkdir(new_dir_path)

    if "FSA" in path_to_directory:
        firefighting = True
    else: 
        firefighting = False

    # color
    color_map =  [ # RGB then fourth entry is alpha
        [0.00000000e+00, 0.00000000e+00, 9.09982175e-01, 1.00000000e+00],
        [0.00000000e+00, 2.21568627e-01, 1.00000000e+00, 1.00000000e+00],
        [0.00000000e+00, 5.82352941e-01, 1.00000000e+00, 1.00000000e+00],
        [4.74383302e-02, 9.58823529e-01, 9.20303605e-01, 1.00000000e+00],
        [3.38393422e-01, 1.00000000e+00, 6.29348514e-01, 1.00000000e+00],
        [6.29348514e-01, 1.00000000e+00, 3.38393422e-01, 1.00000000e+00],
        [9.20303605e-01, 1.00000000e+00, 4.74383302e-02, 1.00000000e+00],
        [1.00000000e+00, 6.68845316e-01, 0.00000000e+00, 1.00000000e+00],
        [1.00000000e+00, 3.34785766e-01, 0.00000000e+00, 1.00000000e+00],
        [9.09982175e-01, 7.26216412e-04, 0.00000000e+00, 1.00000000e+00]
    ]

    def array2cmpa(X):
    # Assuming array is Nx3, where x3 gives RGB values
    # Append 1's for the alpha channel, to make X Nx4
        # X = np.c_[X,np.ones(len(X))]

        return matplotlib.colors.LinearSegmentedColormap.from_list('my_colormap', X)

    #     ]
    # TODO: Future -> allow gui input from this page -> folder name
    # TODO: name folder by current time for now

    # TODO: find all quantity/parameter types
    slice_params = [x for x in list(quantity_type_config.keys()) if x in str(sim.slices)]
    slice_array = return_2d_slices(path_to_directory)
    chosen_slices = [slice_array[i] for i in slices_chosen]
    # TODO: then loop through types
    # TODO: find if they are z slices etc
    slice_counter = 0
    for slice in chosen_slices: # not velocity
        current_slice = slice

        current_type = [x for x in quantity_types if x in current_slice.quantity.name]
        if current_type:
            current_type = current_type[0]
            print(f'starting {current_type}')
            
            color_map_reversed = color_map[::-1]
            cmap_reversed = array2cmpa(color_map_reversed)
            cmap_forward = array2cmpa(color_map)

            current_quantity_object = quantity_type_config[current_type]

            if current_quantity_object["cbar_reverse"]:
                current_cmap = cmap_reversed
            else:
                current_cmap = cmap_forward

            img = plt.imshow(
                                np.array([[0,1]]), 
                                # origin='lower',
                                vmin=current_quantity_object["v_min"],
                                vmax=current_quantity_object["v_max"],
                                cmap=current_cmap)
            img.set_visible(False)
            plt.axis('off')
            # add orientation of slice
            plt.colorbar(label=f'{current_quantity_object["chart_name"]} {current_quantity_object["units"]}')
            save_chart_high_res(name_of_chart=f'{current_type}_colourbar', new_dir_path=new_dir_path)
            # plt.show()
            plt.close()

            print(current_slice)
            '''
                TODO: have other sub function that shows all the twoD slices -> 
                then list sent in of required 
            '''
            slc = slice
            slc_data = slc.to_global()
            counter = 0
            # # try adding nan to smaller

            for time_step in time_intervals:

                it = slc.get_nearest_timestep(time_step)
                print(f"Time step: {it}")
                print(f"Simulation time: {slc.times[it]}")
                
                temp_slc_data = slc_data

                try:
                    # Handle different data structures
                    if isinstance(temp_slc_data, tuple):
                        if len(temp_slc_data) > 0:
                            current = temp_slc_data[0][it] if isinstance(temp_slc_data[0], list) else temp_slc_data[it]
                        else:
                            current = temp_slc_data[it]
                    else:
                        current = temp_slc_data[it]

                    if type(current) == list:
                        current = np.array(current, dtype=np.float64)

                    data = current.T

                    plt.imshow(data, 
                                origin='lower',
                                vmin=current_quantity_object["v_min"],
                                vmax=current_quantity_object["v_max"],
                                cmap=current_cmap,
                                interpolation='gaussian',
                            extent=slc.extent.as_list())

                    plt.axis('off') 
                    # get orientation of slice
                    if 'x' not in slice.extent_dirs:
                        orientation = 'x'               
                    elif 'y' not in slice.extent_dirs:
                        orientation = 'y'
                    else:
                        orientation = 'z'

                    name_of_chart = f'{current_type}_{orientation}slice{slice_counter}@{slc.times[it]}secs'

                    save_chart_high_res(name_of_chart, new_dir_path, 1200)      
                except (IndexError, TypeError) as e:
                    print(f"Warning: Could not process time step {time_step} for slice {slice_counter}: {str(e)}")
                    continue

                counter += 1
            slice_counter += 1


# Creates an instance of a simulation master-class which manages all data for a given simulation
test_resi = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Research CFD\1. Graph Generation\Test Cases\Test1\S1_FSA'
new_resi = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final\L1_West_Core_FSA'
latest_resi = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final\L1_East_Core_FSA'
desktop_resi = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final\L1_West_Core_FSA-DESKTOP-NASJ970'
west_l2 = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final\L2_West_Core_FSA'
path_to_root_directory = (r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\9. 100 Avenue Road\Jan 2023 Corridor Models")
fsa1 = r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\9. 100 Avenue Road\Jan 2023 Corridor Models\FS02-T-FSA"
sensitivity = r"C:\Users\IanShaw\Dropbox\Projects CFD\9. 100 Avenue Road\sensitivity run fs16\FS16_CoreB1_FSA\FS_10_CoreB1_FSA"
sensitivity = r"C:\Users\IanShaw\Dropbox\Projects CFD\0186 Claridges\Runs\FS01-FSA"
# setup loop for path_to_root_directory
def run_slice_loop(
            path_to_root_directory,
            save_path=None,
            runs_to_skip=None,
            runs_to_not_skip=None
):
    
    # TODO: send in time list for each run
    # get total runtime
    filenames = listdir(path_to_root_directory)
    for run in filenames:
        current_path = (f'{path_to_root_directory}\{run}')
        time_intervals=[60, 120, 180, 240, 300]
        # if runs_to_skip is None or runs_to_skip not in run:
        if len([f for f in (runs_to_not_skip) if f in run]) > 0:
            obtain_slice(
                path_to_directory=current_path, 
                save_in_cfd_folder=True, 
                save_path=save_path,
                time_intervals=time_intervals
                )
if __name__ == '__main__':
    slice_array = return_2d_slices(sensitivity)
    print(f"Found {len(slice_array)} 2D slices in the simulation")
    
    # Only choose slices that exist
    available_slices = list(range(len(slice_array)))
    print(f"Available slice indices: {available_slices}")
    
    # Use all available slices by default
    slices_chosen = available_slices
    print(f"Processing slices: {slices_chosen}")
    
    obtain_slice(path_to_directory=sensitivity, slices_chosen=slices_chosen)

    ''''
        TODO: after save -> add to template report
        do we need to trim white space?
    '''
