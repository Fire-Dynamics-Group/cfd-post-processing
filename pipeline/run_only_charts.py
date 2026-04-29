# run hrr_graph.py => to be standalone exe file or similar
import os
import PySimpleGUI as sg

from os import listdir

from hrr_graph import return_paths_to_files, run_hrr_charts, run_devc_charts
'''
    TODO: allow just charts for general CFD 
    LATER: loop through folder with multiple runs; and only one to be selected
    Inputs required:
        project name
        new dir path
        if firefighting i.e. if FSA in name?

    LATER:
'''

# GUI input boxes etc in layout
layout = [
       [sg.Text("Path to runs' root directory:"), sg.Input(key="PATH", do_not_clear=True)], 
       [sg.Text("Project Name:"), sg.Input(key="PROJECT_NAME", do_not_clear=True)],       
        # have popup saying x runs will be taken as FSA and y MOE
        # LATER: have output path
        [sg.Button("Create Charts"), sg.Exit()], 
]

window = sg.Window("Chart Generator", layout, element_justification="right")

while True:
    event, values = window.read()
    if event == sg.WIN_CLOSED or event == "Exit":
        break
    if event == "Create Charts":
        pass
        if values['PATH']:
            values['PATH'] = r"{}".format(values['PATH'])
        path_to_root_directory = f"{values['PATH']}"
        project_name = values['PROJECT_NAME']
        charts_folder = "outputCharts"
        new_dir_path = f"{charts_folder}/{project_name}"
        if not os.path.isdir(charts_folder):
            os.mkdir(charts_folder)
        if not os.path.isdir(new_dir_path):
            os.mkdir(new_dir_path)
        '''
            TODO: get it to work for final folder too
        '''

        sub_folders = [f for f in listdir(path_to_root_directory) if os.path.isdir(f'{path_to_root_directory}/{f}')]
        if len(sub_folders) == 0:
            sub_folders = [os.path.basename(os.path.dirname(path_to_root_directory))]
            path_to_root_directory = os.path.dirname(path_to_root_directory)
        
        for current_name in sub_folders:
            firefighting = "FSA" in current_name
            path_to_hrr_file, path_to_scen_directory, path_to_fds_file, path_to_devc_file, error_list = return_paths_to_files(scenario_name=current_name, dir_path=path_to_root_directory, new_folder_structure=True)
            run_hrr_charts(path_to_fds_file, path_to_hrr_file,new_dir_path=new_dir_path,firefighting=True)
            run_devc_charts(path_to_devc_file, path_to_fds_file, new_dir_path,firefighting=True)


