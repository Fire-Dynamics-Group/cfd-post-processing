import tkinter as tk
from tkinter import filedialog, Scrollbar, Canvas
import os
import re
from slice_files import return_2d_slices, obtain_slice

class FDSGUI:
    def __init__(self, master):
        self.master = master
        master.title("FDS Slice Selector")
        master.geometry("800x600")  # Set the window size

        # # Frame for the time interval input
        # self.time_frame = tk.Frame(master)
        # self.time_frame.pack(fill=tk.X)

        # # Label and entry for time intervals
        # self.time_label = tk.Label(self.time_frame, text="Time Intervals:")
        # self.time_label.pack(side=tk.LEFT)
        # self.time_entry = tk.Entry(self.time_frame)
        # self.time_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Create the main layout frames
        self.left_frame = tk.Frame(master, width=200)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.central_frame = tk.Frame(master)
        self.central_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Frame for the time interval input in central column
        self.time_frame = tk.Frame(self.central_frame)
        self.time_frame.pack(fill=tk.X, pady=5)

        # Label and entry for time intervals
        self.time_label = tk.Label(self.time_frame, text="Time Intervals:")
        self.time_label.pack(side=tk.LEFT)
        self.time_entry = tk.Entry(self.time_frame)
        self.time_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Frame for the list of slice files and checkboxes in the left column
        self.canvas = Canvas(self.left_frame)
        self.scrollbar = Scrollbar(self.left_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.canvas = Canvas(self.left_frame)
        self.scrollbar = Scrollbar(self.left_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Button to select the directory containing slice files
        self.select_button = tk.Button(master, text="Select Directory", command=self.select_directory)
        self.select_button.pack()

        # Button to run the simulation
        self.run_button = tk.Button(master, text="Run Simulation", command=self.run_simulation)
        self.run_button.pack()

        # Variables to hold the selected directory and slice files
        self.directory = ''
        self.slice_files = []

    def select_directory(self):
        self.directory = filedialog.askdirectory()
        self.update_slice_list()

    def update_slice_list(self):
        # Clear the previous list
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        def find_constant_coordinate(line):
            # Regular expression to find extents in the line
            pattern = r'\[\d+\.\d+,\s*\d+\.\d+\]'
            matches = re.findall(pattern, line)
            extents = [tuple(map(float, match.strip('[]').split(','))) for match in matches]

            axis_names = ['X', 'Y', 'Z']
            for axis, (start, end) in zip(axis_names, extents):
                if start == end:
                    return f"{axis}={start}"
            return None

        if self.directory:
            self.slice_files = return_2d_slices(self.directory)
            self.check_vars = [tk.BooleanVar() for _ in self.slice_files]

            for i, file in enumerate(self.slice_files):
                checkbox = tk.Checkbutton(self.scrollable_frame, text=file, variable=self.check_vars[i])
                checkbox.pack(anchor='w')

    def run_simulation(self):
        selected_files = [self.slice_files[i] for i, checked in enumerate(self.check_vars) if checked.get()]
        selected_indexes = [i for i, checked in enumerate(self.check_vars) if checked.get()]
        # TODO: have error if no timesteps are selected
        time_intervals = self.time_entry.get()
        time_intervals = [float(f) for f in time_intervals.split(",")]
        obtain_slice(path_to_directory=self.directory, slices_chosen=selected_indexes, time_intervals=time_intervals, save_path=os.path.dirname(self.directory), save_in_cfd_folder=True)

        print("Selected Files:", selected_files)
        print("Time Intervals:", time_intervals)
        # Add your simulation running logic here

root = tk.Tk()
my_gui = FDSGUI(root)
root.mainloop()
