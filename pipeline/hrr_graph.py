import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
import math
import os
from pathlib import Path

# from auto_report import scenario_names
from constants import growthRateObject, chart_config, devc_chart_constants, font_name_normal


logger = logging.getLogger(__name__)


class ChartPlotError(Exception):
    """Raised when a chart fails to plot. Carries the offending CSV path so
    the orchestrator can collect it as a non-fatal warning on the job."""

    def __init__(self, message: str, csv_path: str | None = None):
        super().__init__(message)
        self.csv_path = csv_path

from helper_functions import return_paths_to_files, find_worst_case_column_name, filter_dataframe_by_column_starting_with_string, read_from_csv_skip_first_row, get_column_prefix
from fds_output_utils import find_door_opening_times_with_close_defaults

brand_blues = {
    "light_blue": '#B5D8FE',
    "mid_blue": '#4798EA',
    "dark_blue": '#1A4A9C'
}
# graph_generation\MoE_Test\Graph_MoE_Test\Graph_MoE_Test.fds
def find_hrr_from_fds_file(path_to_file):
    ring_list = []
    name = os.path.basename(path_to_file)
    if "Kitchen" in path_to_file:
        sn = "Kitchen"
    else:
        sn = "Living Room"
    with open(path_to_file) as f:
        for line in f:
            line_stripped_lowercase = line.strip().lower()
            if line != None: 
                if "hrrpua" in line_stripped_lowercase:
                    print(line)
                    # find numbers in string
                    matching_numbers = re.findall("\d+", line_stripped_lowercase)
                    print(matching_numbers)
                    hrr_pua_value = int(matching_numbers[0])
                if ", SURF_IDS=\'Fire".lower() in line_stripped_lowercase:
                    regex = '\d*?\.\d+'
                    fire_position_array = re.findall(regex, line)
                    fire_area = abs(float(fire_position_array[0]) - float(fire_position_array[1])) * abs(float(fire_position_array[2]) - float(fire_position_array[3]))
                    print(fire_area)
                    hrr_value = fire_area * hrr_pua_value
                    # check if fire area is not none
                    # if none find each ring and add together
                    return hrr_value
                if ", SURF_IDS=\'Ring ".lower() in line_stripped_lowercase:
                    ring_list.append(line)
        # if rings found
        prog_HRR = []
        prog_time = []
        t = 0 
        if "PD1" in name:
            Simulation_Time = 1800
        else:
            Simulation_Time = 1200 

        if "PD1" in name:
            ylim = 300
            if "Kitchen" in sn:
                fgr = 0.0469

            else:
                fgr = 0.0117

            peak_time = 120 # sprinkler_activation # to be passed in
            peak_HRR = fgr*(peak_time**2)
            while t <= peak_time:
                prog_HRR.append(min(t**2*fgr, peak_HRR))
                prog_time.append(t)
                t = t+1
            while t <= Simulation_Time:
                prog_HRR.append(max(peak_HRR + (t - peak_time)*(0-peak_HRR)/120, 0))
                prog_time.append(t)
                t = t+1
        else:
            ylim = 2000    
            peak_HRR = 1500 
            if "Kitchen" in sn:
                fgr = 0.0469
            else:
                fgr = 0.0117
            while t <= Simulation_Time:
                prog_HRR.append(min(t**2*fgr, peak_HRR))
                prog_time.append(t)
                t = t+1   
        outer_ring = ring_list[-4:-1]
        # Initialize min and max values for x, y, z
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        # Extract and compute the min and max values
        for line in outer_ring:
            _, values= line.split('XB=')
            coords = [float(v) for v in values.split(',')[0:6]]
            min_x = min(min_x, coords[0], coords[1])
            max_x = max(max_x, coords[0], coords[1])
            min_y = min(min_y, coords[2], coords[3])
            max_y = max(max_y, coords[2], coords[3])
            min_z = min(min_z, coords[4], coords[5])
            max_z = max(max_z, coords[4], coords[5])

        # The outer corners of the fire
        outer_corners = {
            'min': (min_x, min_y, min_z),
            'max': (max_x, max_y, max_z)
        }
        fire_area = (max_x - min_x) * (max_y - min_y)
        hrr_value = fire_area * hrr_pua_value
        return hrr_value
                
                


def plot_legend(include_door_openings=False):
    if include_door_openings:
        cols = 3
    else:
        cols = 2
    bbox_position = (0.5,-0.37)
    plt.legend(bbox_to_anchor =bbox_position, ncol=cols,loc='lower center', fontsize = 8, frameon=False)

def compute_y_axis_bounds(max_axis_array, min_axis_array):
    to_the_nearest = 10

    def get_min_bound(element):
        if element ==0:
            return 0
        else:
            return element-10

    max_bounds = [element+10 for element in max_axis_array]
    min_bounds = [get_min_bound(element) for element in min_axis_array]
    max_from_lines = max(max_bounds)
    min_from_lines = min(min_bounds)
    max_axis = math.floor(max_from_lines/to_the_nearest) * to_the_nearest
    min_axis = math.ceil(min_from_lines/to_the_nearest) * to_the_nearest
    return max_axis, min_axis

def plot_bounds(x_min_axis, x_max_axis, y_min_axis, y_max_axis):
    plt.xlim([x_min_axis, x_max_axis])    ## limits x axis bounds
    plt.ylim([y_min_axis, y_max_axis])    ## limits y axis bounds

def plot_bounds_without_time_x_axis(line_y_max_array, line_y_min_array, x_column):
    y_max_axis, y_min_axis = compute_y_axis_bounds(line_y_max_array, line_y_min_array)

    x_max_axis, x_min_axis = compute_y_axis_bounds(x_column, x_column)
    plot_bounds(x_min_axis, x_max_axis, y_min_axis, y_max_axis)

def plot_bounds_time_on_x_axis(line_y_max_array, line_y_min_array, x_column):
    y_max_axis, y_min_axis = compute_y_axis_bounds(line_y_max_array, line_y_min_array)
    if type(x_column)==list:
        x_column = np.array(x_column)
    x_max_axis, x_min_axis = x_column.max(), x_column.min()
    plot_bounds(x_min_axis, x_max_axis, y_min_axis, y_max_axis)


def plot_line(x_data, y_data, label_text, line_color='blue', line_width=0.75, line_style="-", csv_path=None):
    try:
        plt.plot(x_data, y_data, color=line_color, linewidth=line_width, label=label_text, linestyle=line_style)
    except Exception as e:
        logger.warning(
            "plot_line failed for %r (csv_path=%s): %s", label_text, csv_path, e
        )
        raise ChartPlotError(
            f"Error plotting line {label_text!r}: {e}. CSV may have too few rows.",
            csv_path=csv_path,
        ) from e

def plot_tenable_line(tenable_limit):
    plt.axhline(y=tenable_limit, color='r', linestyle='--',label="Tenability Limit", linewidth=0.75)

def plot_verticle_line(x_line, line_label, color):
    if x_line != None:
        plt.axvline(x=x_line, color=color, linestyle='--',label=line_label, linewidth=0.75)

def plot_axes_labels_and_ticks(y_label_text, x_label_text="Time (Seconds)"):
    plt.xlabel(x_label_text, fontname = font_name_normal, fontsize = 10) 
    plt.xticks(fontname = font_name_normal, fontsize = 8)  

    plt.ylabel(y_label_text, fontname = font_name_normal, fontsize = 10) 
    plt.yticks(fontname = font_name_normal, fontsize = 8)   

def compute_programmed_HRR(row, programmed_growth_rate, max_HRR, steady_state=True):
    computed_hrr = (row['Time']**2) * programmed_growth_rate
    if not steady_state:
        return min(computed_hrr, max_HRR)
    else:
        return max_HRR

# TODO: steady state for MoE too
def chart_hrr(
            df,
            new_dir_path,
            max_model_hrr, # passed in as None for open plan??
            x_column_name='Time', 
            y_column_name='HRR', 
            programmed_growth_rate=growthRateObject["medium"],
            firefighting=False,
            filename = "Graph_hrr",
            door_openings = {'opening_apartment': 150.0, 'closing_apartment': 170.0, 'opening_stair': 160.0, 'closing_stair': 180.0},
    ):

    x_column = df[x_column_name]
    y_column = df[y_column_name]

    max_time = x_column.max()

    programmed_time = {'Time': list(range(0, int(max_time)+1))}
    programmed_df = pd.DataFrame(programmed_time)
    '''
    # TODO: how to handle below if gives NaN
    '''
    programmed_df['HRR'] = programmed_df.apply(
        lambda row: compute_programmed_HRR(
            row, 
            programmed_growth_rate, 
            max_model_hrr
            ), 
        axis=1 
        )
    if firefighting == True:
        programmed_df['HRR'] = programmed_df['HRR'].max()
    # TODO: send into charting function here
    line_y_max_array = [programmed_df['HRR'].max(), y_column.max()]
    line_y_min_array = [programmed_df['HRR'].min(), y_column.min()]
    chart_name = "Heat Release Rate"
    y_axis_units_abbreviated_for_graph = "kW"
    with plt.rc_context(chart_config):
        # TODO: pull plots from array 
        plt.plot(x_column, y_column, color = brand_blues['mid_blue'], linewidth = 0.75, label='Recorded HRR')  ## adds a line
        plt.plot(programmed_df['Time'], programmed_df['HRR'], color = 'red', linewidth = 0.75, linestyle='dotted', label='Programmed HRR')   ## adds another line
        # door_openings['opening_apartment'] = 60
        apt_open_label = ("flat door opens").capitalize()
        # TODO: remove below -> hack for office charts

        plot_verticle_line(x_line=door_openings['opening_apartment'], line_label=apt_open_label, color='blue')
        if firefighting == False:
            plot_verticle_line(x_line=door_openings['closing_apartment'], line_label=("flat door closes").capitalize(), color='m')
            plot_verticle_line(x_line=door_openings['closing_apartment']+120, line_label="2mins after Door Closes", color='g')
            include_door_openings = True
        else:
            include_door_openings = False
        plot_axes_labels_and_ticks(y_label_text=f'{chart_name} ({y_axis_units_abbreviated_for_graph})')
        plot_legend(include_door_openings=include_door_openings)
        
        plot_bounds_time_on_x_axis(line_y_max_array, line_y_min_array, x_column)
        plt.tight_layout() 
        save_chart_high_res(name_of_chart=filename, new_dir_path=new_dir_path)
        # plt.show()
        plt.close()

def chart_devc(
            df,
            new_dir_path, 
            x_column_name='Time', 
            y_column_name='cc_pres',
            second_y_column_name=None,
            y_axis_units_abbreviated_for_graph='Pa',
            tenable_limit=-60,
            chart_name='Pressure',
            chart_save_name = None,
            firefighting = False,
            door_openings = {'opening_apartment': 150.0, 'closing_apartment': 170.0, 'opening_stair': 160.0, 'closing_stair': 180.0},
            path_to_file=None
    ):
    is_pressure = False
    # TODO: rolling average only for pressure
    if y_axis_units_abbreviated_for_graph=='Pa':
        is_pressure = True
    x_column = df[x_column_name]
    y_column = df[y_column_name]

    print(f"[DEBUG] DataFrame shape: {df.shape}")
    print(f"[DEBUG] Max Time: {x_column.max()}")
    print(f"[DEBUG] Min Time: {x_column.min()}")
    print(f"[DEBUG] x_column shape: {x_column.shape}")
    print(f"[DEBUG] y_column shape: {y_column.shape}")

    def compute_y_rolling_average(y_column):

        y_average = [] 
        N = 10 
        half_n = int(N/2) # datapoints either side to be used in rolling mean
        index = 5
        for ind in range(half_n):# add nan to index zero to 4
            y_average.insert(0, np.nan)
        # range len - (index + 1)
        for index in range(half_n, len(y_column)-(half_n)):
            current_y_average = np.convolve(y_column[index-half_n:index+half_n], np.ones(N)/N, mode='valid')
            y_average.append(current_y_average[0])

        for ind in range(half_n):# add nan to index zero to 4
            y_average.append(np.nan)
        return y_average
    y_average = compute_y_rolling_average(y_column)

    print(f"[DEBUG] y_average shape: {np.array(y_average).shape}")
    print(f"[DEBUG] y_average sample: {y_average[:10]}")

    if second_y_column_name:
        second_y_column = df[second_y_column_name]
        second_y_average = compute_y_rolling_average(second_y_column)
    # push to array
    with plt.rc_context(chart_config):
        # TODO: pull plots from array if multiple plots required - incorporate hrr logic
        chart_label = chart_name
        if second_y_column_name:
            chart_label = f'{chart_name} 0-1m from stair door'
            second_chart_label = f'{chart_name} 1-2m from stair door'
    
            # chart_label = second_chart_label # TODO: remove this line

        if chart_name == "Pressure":
            recorded_label = f'Relative {chart_name}'
        else: 
            recorded_label = f'Recorded {chart_name}'
        if second_y_column_name:
            recorded_label = f'Recorded {chart_label}'
            second_recorded_label = f'Recorded {second_chart_label}'
            bottom_line_style = '-'
        else:
            bottom_line_style = '-'

        plot_line(x_data=x_column, y_data=y_column, label_text=recorded_label, line_style=bottom_line_style, line_color=brand_blues['mid_blue'], csv_path=path_to_file) # relative pressure
        if is_pressure:
            plot_line(x_data=x_column, y_data=y_average, label_text=(f'Rolling Average {chart_label}'), line_color="black", csv_path=path_to_file)

        if second_y_column_name:
            plot_line(x_data=x_column, y_data=second_y_column, label_text=second_recorded_label, line_style="dashdot", line_color="orange", csv_path=path_to_file) # relative pressure
            if is_pressure:
                plot_line(x_data=x_column, y_data=second_y_average, label_text=(f'Rolling Average {second_chart_label}'), line_style="-",line_color="brown", csv_path=path_to_file)

        plot_verticle_line(x_line=door_openings['opening_apartment'], line_label="flat door opens".capitalize(), color="blue")
        
        if tenable_limit != None:
            plot_tenable_line(tenable_limit=tenable_limit)
            # add 0-1m into max
            line_y_max_array = [y_column.max(),tenable_limit]
            line_y_min_array = [y_column.min(),tenable_limit]
            if second_y_column_name:
                line_y_max_array.append(second_y_column.max())
                line_y_min_array.append(second_y_column.min())

        else:
            line_y_max_array = [y_column.max()]
            line_y_min_array = [y_column.min()]

        if firefighting == False:
            plot_verticle_line(x_line=door_openings['closing_apartment'], line_label="flat door closes".capitalize(), color='m')
            plot_verticle_line(x_line=door_openings['closing_apartment']+120, line_label="2mins after Door Closes", color='g')
            include_door_openings = True
        else:
            include_door_openings = False

        plot_axes_labels_and_ticks(y_label_text=f'{chart_name} ({y_axis_units_abbreviated_for_graph})')
        plot_bounds_time_on_x_axis(line_y_max_array, line_y_min_array, x_column)
        plot_legend(include_door_openings=include_door_openings)
        plt.tight_layout() 
        save_chart_high_res(name_of_chart=chart_save_name or chart_name, new_dir_path=new_dir_path)
        print("break")
        plt.close()

def save_chart_high_res(name_of_chart, new_dir_path, dpi=1200):
    file_path = f'{new_dir_path}/{name_of_chart}_chart.png'
    if os.path.exists(file_path):
        os.remove(file_path)
    plt.savefig(file_path, format='png', dpi=dpi)
    plt.close()

# Likely should be after flat door opens - is this in the fds file??
def find_column_with_most_frequent_min(df):
    df['Min'] = df.idxmin(axis=1)
# find most frequent in min
    return df['Min'].mode() 


def run_devc_charts(path_to_file, path_to_fds_file, new_dir_path,firefighting=False):
    devc_df = read_from_csv_skip_first_row(path_to_file)
    door_openings = find_door_opening_times_with_close_defaults(path_to_file=path_to_fds_file)

    # Strip trailing device number to get column prefix
    dataframe_columns = devc_df.columns
    prefixes = []
    i = 0
    while i < len(dataframe_columns):
        prefixes.append(get_column_prefix(column_name=dataframe_columns[i]))
        i += 1

    devc_df_column_prefixes = list(dict.fromkeys(prefixes))

    # cut sd - not clear if important, or just if !=="SD"
    for column_prefix in devc_df_column_prefixes:
        has_column_config = False
        if column_prefix != "SD" and "SPRK" not in column_prefix and column_prefix !="Time":
            # access object
            for object_name in devc_chart_constants.keys():
                if "pres" in object_name:
                    object_name_temp = "pres"
                else:
                    object_name_temp = object_name
                if object_name_temp in column_prefix:
                    column_config = devc_chart_constants[object_name]
                    has_column_config = True
                    break

            if has_column_config:
                data_columns = filter_dataframe_by_column_starting_with_string(devc_df, column_prefix)

                def find_column_name_with_min(data_columns):
                    return data_columns.min().idxmin(axis=0)

                def find_column_name_with_max(data_columns):
                    return data_columns.max().idxmax(axis=0)

                def extract_fsa_distance(column_name):
                    """Extract distance number from FSA column suffix.
                    e.g. corridor_1_FSA_temp_2m -> 2, cc_FSA_temp_15m -> 15"""
                    prefix = get_column_prefix(column_name)
                    suffix = column_name[len(prefix):]  # e.g. '2m', '15m'
                    return int(suffix.replace('m', ''))
                # if fsa_temp: create chart for all columns
                # pass in naming convention for fs cc or stair
                if firefighting and 'FSA' in column_prefix and 'temp' in column_prefix:
                    # TODO: bespoke chart using max 30 secs after flat door opens
                    # TODO: read worst case temps from scenario object
                    time = door_openings['opening_apartment'] + 30
                    # find temp at time
                    # add to dictionary/new df
                    temp_index = devc_df['Time'].sub(time).abs().idxmin()
                    distance_list = []
                    temp_list = []
                    tenability_x0_list = []
                    tenability_x1_list = []
                    tenability_y0_list = []
                    tenability_y1_list = []                
                    tenable_limit_object = devc_chart_constants["temp_"]["tenable_limit_FSA"]
                    tenable_keys_list = [*tenable_limit_object]
                    # data_columns.rename(columns={'cc_FSA_temp_15m': 'cc_FSA_temp_8m'}, inplace=True)
                    # devc_df.rename(columns={'cc_FSA_temp_15m': 'cc_FSA_temp_8m'}, inplace=True)
                    tenable_cols = [f for f in data_columns.columns if '2' in f or '4' in f or '15' in f] # or '15' in f
                    applicable_cols = [f for f in data_columns.columns if '2' in f or '4' in f or '15' in f]
                    for column in applicable_cols: # limited to 2, 4 and 15 
                        # extract number
                        distance = extract_fsa_distance(column) # use for distance x axis
                        distance_list.append(distance)
                    if len(data_columns.columns) == 1:
                        # if only one in series plot using below:
                        chart_devc(
                            df=devc_df,
                            new_dir_path=new_dir_path, 
                            x_column_name='Time', 
                            y_column_name=column,
                            y_axis_units_abbreviated_for_graph=column_config["units_abbreviated_for_graph"],
                            tenable_limit=column_config["tenable_limit_FSA"][f'{distance}m'],
                            chart_name= column_config["chart_name"],
                            chart_save_name=f'{file_name_from_path(file_path=path_to_file)}_{column}',
                            firefighting=firefighting,
                            door_openings=door_openings,
                            path_to_file=path_to_file
                        )
                    else:
                        # TODO: move below into function?
                        for column in applicable_cols: # only for 2, 4 and 15
                            # extract number
                            distance = extract_fsa_distance(column) # use for distance x axis
                            temp = devc_df[column][temp_index:].max()
                            # slice data from from index onwards
                            temp_list.append(temp)
                            if column in tenable_cols:
                                # find tenable limit form config object
                                tenability_y = tenable_limit_object[f'{distance}m']
                                tenability_x0 = distance
                                # find index of distance
                                limit_index = tenable_keys_list.index(f'{distance}m')
                                if limit_index > 0:
                                    # setup for vertical ten line
                                    key_n_minus_1= tenable_keys_list[limit_index-1] # yn-1 to yn
                                    y_n_minus_1 = tenable_limit_object[key_n_minus_1]
                                    # yn - ten y
                                    tenability_y0_list.append(y_n_minus_1)
                                    tenability_y1_list.append(tenability_y)

                                if limit_index < (len(tenable_keys_list) - 1) and limit_index + 1 < len(distance_list): # what if only 1 or 2 distances used?
                                    # use next only if distance_list length allows
                                    x1_index = limit_index + 1
                                else:
                                    x1_index = limit_index
                                # tenability_x1 = tenable_limit_object[tenable_keys_list[x1_index]]
                                
                                tenability_x1 = distance_list[x1_index]

                                tenability_x0_list.append(tenability_x0)
                                tenability_x1_list.append(tenability_x1)
                            # add 1 to index

                        # chart from dots
                        # bring charting here/send to own function
                        with plt.rc_context(chart_config):
                            plt.scatter(x=distance_list, y=temp_list, label="Max Recorded Temperature later than 30s after Door Opens")
                            ''' remove this after'''
                            tenability_x0_list = [2, 4]
                            tenability_x1_list = [4, 15]
                            tenability_y0_vert_list = [160, 120]  
                            tenability_y1_vert_list = [120, 100] 
                            # TODO: find max distance in sensor list
                            # if < 4; have one horizontal only
                            # if > 4; if >= 15 have vertical line
                            vert_line_index = 0
                            for index in range(len(tenability_x0_list)):
                                if index == (len(tenability_x0_list) -1):
                                    label_text = "Tenability Limit"
                                else:
                                    label_text = None
                                # if in
                                if index == 0 or (index == 1 and max(distance_list) >= 4):
                                    y_h_line = tenable_limit_object[list(tenable_limit_object.keys())[index]]
                                    plt.hlines(y = y_h_line, xmin=tenability_x0_list[index], xmax=tenability_x1_list[index], color='r', linestyles='--', linewidth=0.75, label=label_text)
                                if max(distance_list) >= tenability_x1_list[vert_line_index]:
                                    plt.vlines(x = tenability_x1_list[index], ymin=tenability_y1_vert_list[vert_line_index], ymax=tenability_y0_vert_list[vert_line_index], color='r', linestyles='--', linewidth=0.75)
                                    vert_line_index += 1                                    
                                # plot 160 from 2 -4
                                # plot 120 from 4 to 15
                            plot_axes_labels_and_ticks(y_label_text=f'{column_config["chart_name"]} ({column_config["units_abbreviated_for_graph"]})', x_label_text="Distance from Flat Door (m)")
                            plot_legend()
                            
                            plot_bounds_without_time_x_axis(line_y_max_array=[max(temp_list), 160], line_y_min_array=[0], x_column=[0,*distance_list])
                            plt.tight_layout() 
                            save_chart_high_res(name_of_chart=f'{file_name_from_path(file_path=path_to_file)}_CC_Temp', new_dir_path=new_dir_path)
                            plt.close()
                            # plot_line(x_data=[*(tenability_x0_list, tenability_x1)], y_data=[60,60], label_text=None, line_color='red')
                            # plt.show()
                            print("done")
                            # draw tenability lines - dependent on devices and distances in corridor
                else: # i.e. both are not true (1 or none true): firefighting and column_prefix == 'cc_FSA_temp_':
                    # TODO: if stair in prefix, send two worst cases to chart_devc: 1-5 and 5-10

                    column_names=list(data_columns.columns)
                    is_stair = any("stair" in x for x in column_names)

                    new_df = find_worst_case_column_name(
                    worst_case_max_or_min=column_config["worst_case"], 
                    column_names=column_names,
                    df=devc_df,
                    is_stair=is_stair
                )
                    # if stair in columns
                    if is_stair:
                        second_y_column_name = 'worst_case_b'
                    else:
                        second_y_column_name = None
                    # TODO: IF stair vis/temp; second y value to be sent in i.e. worst_case_b from new_df
                    chart_devc(
                        df=new_df,#would be new df with max
                        new_dir_path=new_dir_path, 
                        x_column_name='Time', 
                        y_column_name='worst_case',
                        second_y_column_name=second_y_column_name,
                        y_axis_units_abbreviated_for_graph=column_config["units_abbreviated_for_graph"],
                        tenable_limit=column_config["tenable_limit_moe"],
                        chart_name= column_config["chart_name"],
                        chart_save_name=f'{file_name_from_path(file_path=path_to_file)}_{column_prefix}',
                        firefighting=firefighting,
                        door_openings=door_openings,
                        path_to_file=path_to_file
                    )

def file_name_from_path(file_path):
    return os.path.splitext(os.path.basename(file_path))[0]

# TODO: find path automatically
def run_hrr_charts(path_to_fds_file, path_to_hrr_file, new_dir_path,firefighting=False):
    model_hrr = find_hrr_from_fds_file(path_to_fds_file)
    hrr_df = read_from_csv_skip_first_row(path_to_hrr_file)
    # # TODO: remove below hack for office
    # if __name__ == '__main__':
    #     door_openings = {'opening_apartment': 180.0, 'closing_apartment': None, 'opening_stair': None, 'closing_stair': None} 
    # else: 
    #     door_openings = find_door_opening_times(path_to_file=path_to_fds_file)
    door_openings = find_door_opening_times_with_close_defaults(path_to_file=path_to_fds_file)
    chart_file = file_name_from_path(file_path=path_to_hrr_file)
    chart_hrr(hrr_df, new_dir_path=new_dir_path,max_model_hrr=model_hrr,firefighting=firefighting,filename=chart_file,door_openings=door_openings)



def run_CFD_charts(path_to_root_directory, scenario_names, new_dir_path):
    for index in range(len(scenario_names)):
        scenario_name = scenario_names[index]
        path_to_hrr_file, path_to_scen_directory, path_to_fds_file, path_to_devc_file, error_list = return_paths_to_files(scenario_name, dir_path=path_to_root_directory, new_folder_structure=True)

    # path_to_fds_file = 'graph_generation\MoE_Test\Graph_MoE_Test\Graph_MoE_Test.fds'
        
        if "FSA" in scenario_name:
            firefighting = True
        else:
            firefighting = False
        run_hrr_charts(path_to_fds_file, path_to_hrr_file,new_dir_path=new_dir_path,firefighting=firefighting)

        run_devc_charts(path_to_file=path_to_devc_file, path_to_fds_file=path_to_fds_file, new_dir_path=new_dir_path,firefighting=firefighting)


if __name__=='__main__':
    # TODO: run from report gen script
    # # C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final

    # path_to_root_directory = Path(r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Research CFD\1. Graph Generation\Test Cases\Test2")
    # path_to_root_directory = Path(r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Resi\Final')
    # path_to_root_directory = Path(r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\9. 100 Avenue Road\Jan 2023 Corridor Models")
    # # path_to_root_directory = Path(r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\22. Sweet Street\Office')
    # scenario_names = return_scenario_names(path_to_directory= path_to_root_directory)
    # new_dir_path = Path(__file__).parent / "chart_tests"
    # # scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios = create_scenario_object(path_to_directory="graph_generation")
    # # loop through names to find fds path etc
    # run_CFD_charts(path_to_root_directory, scenario_names, new_dir_path)
    project_name = "Blackhorse Lane FS3"
    new_dir_path = f"outputReports/{project_name}" #Path(__file__).parent / "outputReports"/f"{project_name}"
    if not os.path.isdir(new_dir_path):
        os.mkdir(new_dir_path)
    # os.mkdir(new_dir_path)
    firefighting = True
    # # path_to_file = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\26. Breams Building\FSA\FSA_devc - IS.csv'
    # # path_to_fds_file = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\26. Breams Building\FSA\FSA.fds'
    # # path_to_hrr_file = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\26. Breams Building\FSA\FSA_hrr.csv'
    # # path_to_file = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\31. Camp Hill Gardens Corridor\FS4_FSA\FS4_FSA\FS4_FSA_devc.csv'
    # path_to_file = r'C:\Users\IanShaw\Dropbox\Projects CFD\25. Claridges\P5P6 Stair\Models for Report\FS1 FSA\inletandextract_4m3_L8_devc.csv'

    # # path_to_fds_file = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\31. Camp Hill Gardens Corridor\FS4_FSA\FS4_FSA\FS4_FSA.fds'
    # path_to_fds_file = r'C:\Users\IanShaw\Dropbox\Projects CFD\25. Claridges\P5P6 Stair\Models for Report\FS1 FSA\inletandextract_4m3_L8.fds'

    # path_to_root_directory = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\31. Camp Hill Gardens Corridor\FS2_FSA_2'
    # path_to_root_directory = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\31. Camp Hill Gardens Corridor'
    path_to_root_directory = r"C:\Users\IanShaw\Fire Dynamics Group Limited\F Drive - Projects\230223 - East Road\6. Calculations\Completed runs for transfer"
    path_to_root_directory = r"C:\Users\IanShaw\Dropbox\Projects CFD\38. No1 Blackhorse Lane\S3 FSA\new"
    # path_to_file = fr'{path_to_root_directory}\FS5_MOE\FS5_MOE\FS5_MOE_devc.csv'
    # path_to_fds_file = fr'{path_to_root_directory}\FS5_MOE\FS5_MOE.fds'
    from os import listdir
    # FS5_MOE_devc.csv
    # TODO: allow for single folder; if no folder inside; don't list dir
    for current_name in listdir(path_to_root_directory):
        firefighting = "FSA" in current_name
        path_to_hrr_file, path_to_scen_directory, path_to_fds_file, path_to_devc_file, error_list = return_paths_to_files(scenario_name=current_name, dir_path=path_to_root_directory, new_folder_structure=True)
        run_hrr_charts(path_to_fds_file, path_to_hrr_file,new_dir_path=new_dir_path,firefighting=firefighting)
        run_devc_charts(path_to_devc_file, path_to_fds_file, new_dir_path,firefighting=firefighting)
