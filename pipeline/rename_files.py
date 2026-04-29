from pathlib import Path
import os
from os import listdir
from os.path import isfile

from helper_functions import return_all_subfolders
# os.rename

path_to_root_directory = Path(r"C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\9. 100 Avenue Road\Jan 2023 Corridor Models\FS16_CoreB1_FSA")
print("break")

old = 'FS_10'
new = 'FS_16'
# change all files
for file in listdir(path_to_root_directory):
    if old in file:
        new_name = file.replace(old, new)
        os.rename(f'{path_to_root_directory}/{file}', f'{path_to_root_directory}/{new_name}')
# then access sub folder
sub_folders = return_all_subfolders(path_to_root_directory)
for sub in sub_folders:
    current_folder = f'{path_to_root_directory}/{sub}'
    for file in listdir(current_folder):
        if old in file:
            new_name = file.replace(old, new)
            os.rename(f'{path_to_root_directory}/{sub}/{file}', f'{path_to_root_directory}/{sub}/{new_name}')
# sub_folders need renamed too
# path to sub = f'{path_to_root_directory}/{sub_folders[i]}'
# all files in sub_folder
