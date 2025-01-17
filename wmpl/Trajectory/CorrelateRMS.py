""" Script which automatically pairs meteor observations from different RMS stations and computes
    trajectories. 
"""

from __future__ import print_function, division, absolute_import

import os
import sys
import re
import argparse
import json
import copy
import datetime

import numpy as np

from wmpl.Formats.CAMS import loadFTPDetectInfo
from wmpl.Trajectory.CorrelateEngine import TrajectoryCorrelator, TrajectoryConstraints
from wmpl.Utils.Math import generateDatetimeBins
from wmpl.Utils.Pickling import savePickle
from wmpl.Utils.TrajConversions import jd2Date



### CONSTANTS ###

# Name of the ouput trajectory directory
OUTPUT_TRAJ_DIR = "trajectories"

# Name of json file with the list of processed directories
JSON_DB_NAME = "processed_trajectories.json"

### ###


class DatabaseJSON(object):
    def __init__(self, db_file_path):

        self.db_file_path = db_file_path

        # List of processed directories (keys are station codes)
        self.processed_dirs = {}

        # List of trajectories (keys are trajectory reference julian dates)
        self.trajectories = {}

        # Load the database from a JSON file
        self.load()


    def load(self):
        """ Load the database from a JSON file. """

        if os.path.exists(self.db_file_path):
            with open(self.db_file_path) as f:
                self.__dict__ = json.load(f)


    def save(self):
        """ Save the database of processed meteors to disk. """

        with open(self.db_file_path, 'w') as f:
            self2 = copy.deepcopy(self)
            f.write(json.dumps(self2, default=lambda o: o.__dict__, indent=4, sort_keys=True))


    def addProcessedDir(self, station_name, rel_proc_path):
        """ Add the processed directory to the list. """

        if station_name in self.processed_dirs:
            if not rel_proc_path in self.processed_dirs[station_name]:
                self.processed_dirs[station_name].append(rel_proc_path)


    def addTrajectory(self, traj, met_obs_list):
        """ Add a computed trajectory to the list. """

        pass        

        # if traj.jdt_ref not in self.trajectories:
        #     self.trajectories[traj.jdt_ref] = traj.toJSON()




class MeteorPointRMS(object):
    def __init__(self, frame, time_rel, x, y, ra, dec, azim, alt, mag):
        """ Container for individual meteor picks. """

        # Frame number since the beginning of the FF file
        self.frame = frame
        
        # Relative time
        self.time_rel = time_rel

        # Image coordinats
        self.x = x
        self.y = y
        
        # Equatorial coordinates (J2000, deg)
        self.ra = ra
        self.dec = dec

        # Horizontal coordinates (J2000, deg), azim is +E of due N
        self.azim = azim
        self.alt = alt

        self.intensity_sum = None

        self.mag = mag


class MeteorObsRMS(object):
    def __init__(self, station_code, reference_dt, platepar, data, rel_proc_path):
        """ Container for meteor observations with the interface compatible with the trajectory correlator
            interface. 
        """

        self.station_code = station_code

        self.reference_dt = reference_dt
        self.platepar = platepar
        self.data = data

        # Path to the directory with data
        self.rel_proc_path = rel_proc_path

        self.processed = False 
        self.paired = False

        # Mean datetime of the observation
        self.mean_dt = self.reference_dt + datetime.timedelta(seconds=np.mean([entry.time_rel \
            for entry in self.data]))

        
        ### Estimate if the meteor begins and ends inside the FOV ###

        self.fov_beg = False
        self.fov_end = False

        half_index = len(data)//2


        # Find angular velocity at the beginning per every axis
        dxdf_beg = (self.data[half_index].x - self.data[0].x)/(self.data[half_index].frame \
            - self.data[0].frame)
        dydf_beg = (self.data[half_index].y - self.data[0].y)/(self.data[half_index].frame \
            - self.data[0].frame)

        # Compute locations of centroids 2 frames before the beginning
        x_pre_begin = self.data[0].x - 2*dxdf_beg
        y_pre_begin = self.data[0].y - 2*dydf_beg

        # If the predicted point is inside the FOV, mark it as such
        if (x_pre_begin > 0) and (x_pre_begin <= self.platepar.X_res) and (y_pre_begin > 0) \
            and (y_pre_begin < self.platepar.Y_res):

            self.fov_beg = True

        # If the starting point is not inside the FOV, exlude the first point
        else:
            self.data = self.data[1:]


        # Find angular velocity at the ending per every axis
        dxdf_end = (self.data[-1].x - self.data[half_index].x)/(self.data[-1].frame \
            - self.data[half_index].frame)
        dydf_end = (self.data[-1].y - self.data[half_index].y)/(self.data[-1].frame \
            - self.data[half_index].frame)

        # Compute locations of centroids 2 frames after the end
        x_post_end = self.data[-1].x + 2*dxdf_end
        y_post_end = self.data[-1].y + 2*dydf_end

        # If the predicted point is inside the FOV, mark it as such
        if (x_post_end > 0) and (x_post_end <= self.platepar.X_res) and (y_post_end > 0) \
            and (y_post_end <= self.platepar.Y_res):
            
            self.fov_end = True

        # If the ending point is not inside fully inside the FOV, exclude it
        else:
            self.data = self.data[:-1]

        ### ###



class PlateparDummy:
    def __init__(self, **entries):
        """ This class takes a platepar dictionary and converts it into an object. """
        self.__dict__.update(entries)



class RMSDataHandle(object):
    def __init__(self, dir_path):
        """ Handles data interfacing between the trajectory correlator and RMS data files on disk. 
    
        Arguments:
            dir_path: [str] Path to the directory with data files. 
        """

        self.dir_path = dir_path

        print("Using directory:", self.dir_path)

        # Load the list of stations
        station_list = self.loadStations()

        # Load database of processed folders
        self.db = DatabaseJSON(os.path.join(self.dir_path, JSON_DB_NAME))

        # Find unprocessed meteor files
        self.processing_list = self.findUnprocessedFolders(station_list)


    def loadStations(self):
        """ Load the station names in the processing folder. """

        station_list = []

        for dir_name in os.listdir(self.dir_path):

            # Check if the dir name matches the station name pattern
            if os.path.isdir(os.path.join(self.dir_path, dir_name)):
                if re.match("^[A-Z]{2}[A-Z0-9]{4}$", dir_name):
                    print("Using station:", dir_name)
                    station_list.append(dir_name)
                else:
                    print("Skipping directory:", dir_name)


        return station_list



    def findUnprocessedFolders(self, station_list):
        """ Go through directories and find folders with unprocessed data. """

        processing_list = []

        skipped_dirs = 0

        # Go through all station directories
        for station_name in station_list:

            station_path = os.path.join(self.dir_path, station_name)

            # Add the station name to the database if it doesn't exist
            if station_name not in self.db.processed_dirs:
                self.db.processed_dirs[station_name] = []

            # Go through all directories in stations
            for night_name in os.listdir(station_path):

                night_path = os.path.join(station_path, night_name)
                night_path_rel = os.path.join(station_name, night_name)

                # Extract the date and time of directory, if possible
                try:
                    night_dt = datetime.datetime.strptime("_".join(night_name.split("_")[1:3]), \
                        "%Y%m%d_%H%M%S")
                except:
                    print("Could not parse the date of the night dir: {:s}".format(night_path))
                    night_dt = None

                # If the night path is not in the processed list, add it to the processing list
                if night_path_rel not in self.db.processed_dirs[station_name]:
                    processing_list.append([station_name, night_path_rel, night_path, night_dt])

                else:
                    skipped_dirs += 1


        if skipped_dirs:
            print("Skipped {:d} processed directories".format(skipped_dirs))

        return processing_list



    def initMeteorObs(self, station_code, ftpdetectinfo_path, platepars_recalibrated_dict):
        """ Init meteor observations from the FTPdetectinfo file and recalibrated platepars. """

        # Load station coordinates
        if len(list(platepars_recalibrated_dict.keys())):
            
            pp_dict = platepars_recalibrated_dict[list(platepars_recalibrated_dict.keys())[0]]
            pp = PlateparDummy(**pp_dict)
            stations_dict = {station_code: [np.radians(pp.lat), np.radians(pp.lon), pp.elev]}

            # Load the FTPdetectinfo file
            meteor_list = loadFTPDetectInfo(ftpdetectinfo_path, stations_dict)

        else:
            meteor_list = []


        return meteor_list



    def loadUnprocessedObservations(self, processing_list, dt_range=None):
        """ Load unprocessed meteor observations. """

        # Go through folders for processing
        met_obs_list = []
        for station_code, rel_proc_path, proc_path, night_dt in processing_list:

            # Check that the night datetime is within the given range of times, if the range is given
            if (dt_range is not None) and (night_dt is not None):
                dt_beg, dt_end = dt_range

                # Skip all folders which are outside the limits
                if (night_dt < dt_beg) or (night_dt > dt_end):
                    continue



            ftpdetectinfo_name = None
            platepar_recalibrated_name = None

            # Find FTPdetectinfo and platepar files
            for name in os.listdir(proc_path):
                    
                # Find FTPdetectinfo
                if name.startswith("FTPdetectinfo") and name.endswith('.txt') and \
                    (not "backup" in name) and (not "uncalibrated" in name):
                    ftpdetectinfo_name = name
                    continue

                if name == "platepars_all_recalibrated.json":
                    platepar_recalibrated_name = name
                    continue

            # Skip these observations if no data files were found inside
            if (ftpdetectinfo_name is None) or (platepar_recalibrated_name is None):
                print("Skipping {:s} due to missing data files...".format(rel_proc_path))

                # Add the folder to the list of processed folders
                self.db.addProcessedDir(station_code, rel_proc_path)

                continue

            # Save database to mark those with missing data files
            self.db.save()


            # Load platepars
            with open(os.path.join(proc_path, platepar_recalibrated_name)) as f:
                platepars_recalibrated_dict = json.load(f)

            # If all files exist, init the meteor container object
            cams_met_obs_list = self.initMeteorObs(station_code, os.path.join(proc_path, \
                ftpdetectinfo_name), platepars_recalibrated_dict)

            # Format the observation object to the one required by the trajectory correlator
            for cams_met_obs in cams_met_obs_list:

                # Get the platepar
                pp_dict = platepars_recalibrated_dict[cams_met_obs.ff_name]
                pp = PlateparDummy(**pp_dict)

                # Init meteor data
                meteor_data = []
                for entry in zip(cams_met_obs.frames, cams_met_obs.time_data, cams_met_obs.x_data,\
                    cams_met_obs.y_data, cams_met_obs.azim_data, cams_met_obs.elev_data, \
                    cams_met_obs.ra_data, cams_met_obs.dec_data, cams_met_obs.mag_data):

                    frame, time_rel, x, y, azim, alt, ra, dec, mag = entry

                    met_point = MeteorPointRMS(frame, time_rel, x, y, np.degrees(ra), np.degrees(dec), \
                        np.degrees(azim), np.degrees(alt), mag)

                    meteor_data.append(met_point)


                # Init the new meteor observation object
                met_obs = MeteorObsRMS(station_code, jd2Date(cams_met_obs.jdt_ref, dt_obj=True), pp, \
                    meteor_data, rel_proc_path)

                print(station_code, met_obs.reference_dt, rel_proc_path)

                met_obs_list.append(met_obs)


        return met_obs_list



    def getPlatepar(self, met_obs):
        """ Return the platepar of the meteor observation. """

        return met_obs.platepar



    def getUnprocessedObservations(self):
        """ Returns a list of unprocessed meteor observations. """

        return self.unprocessed_observations


    def findTimePairs(self, met_obs, unprocessed_observations, max_toffset):
        """ Finds pairs in time between the given meteor observations and all other observations from 
            different stations. 

        Arguments:
            met_obs: [MeteorObsRMS] Object containing a meteor observation.
            unprocessed_observations: [list] A list of MeteorObsRMS objects which will be paired in time with
                the given object.
            max_toffset: [float] Maximum offset in time (seconds) for pairing.

        Return:
            [list] A list of MeteorObsRMS instances with are offten in time less than max_toffset from 
                met_obs.
        """

        found_pairs = []

        # Go through all meteors from other stations
        for met_obs2 in unprocessed_observations:

            # Take only observations from different stations
            if met_obs.station_code == met_obs2.station_code:
                continue

            # Take observations which are within the given time window
            if abs((met_obs.mean_dt - met_obs2.mean_dt).total_seconds()) <= max_toffset:
                found_pairs.append(met_obs2)


        return found_pairs



    def saveTrajectoryResults(self, traj, save_plots):
        """ Save trajectory results to the disk. """


        # Generate the name for the output directory (add list of country codes at the end)
        output_dir = os.path.join(self.dir_path, OUTPUT_TRAJ_DIR, \
            jd2Date(traj.jdt_ref, dt_obj=True).strftime("%Y%m%d_%H%M%S.%f")[:-3] + "_" \
            + "_".join(list(set([obs.station_id[:2] for obs in traj.observations]))))

        # Save the report
        traj.saveReport(output_dir, traj.file_name + '_report.txt', uncertainties=traj.uncertainties, 
            verbose=False)

        # Save the picked trajectory structure
        savePickle(traj, output_dir, traj.file_name + '_trajectory.pickle')

        # Save the plots
        if save_plots:
            traj.save_results = True
            traj.savePlots(output_dir, traj.file_name, show_plots=False)
            traj.save_results = False



    def markObservationAsProcessed(self, met_obs):
        """ Mark the given meteor observation as processed. """

        self.db.addProcessedDir(met_obs.station_code, met_obs.rel_proc_path)



    def addTrajectory(self, traj, met_obs_list):
        """ Add the resulting trajectory to the database. """

        self.db.addTrajectory(traj, met_obs_list)



    def finish(self):
        """ Finish the processing run. """

        # Save the processed directories to the DB file
        self.db.save()

        # Save the list of processed meteor observations

        



if __name__ == "__main__":

    # Set matplotlib for headless running
    import matplotlib
    matplotlib.use('Agg')


    ### COMMAND LINE ARGUMENTS

    # Init the command line arguments parser
    arg_parser = argparse.ArgumentParser(description="""Automatically compute trajectories from RMS data in the given directory. 
The directory structure needs to be the following, for example:
    ./ # root directory
        /HR0001/
            /HR0001_20190707_192835_241084_detected
                ./FTPdetectinfo_HR0001_20190707_192835_241084.txt
                ./platepars_all_recalibrated.json
        /HR0004/
            ./FTPdetectinfo_HR0004_20190707_193044_498581.txt
            ./platepars_all_recalibrated.json
        /...

In essence, the root directory should contain directories of stations (station codes need to be exact), and these directories should
contain data folders. Data folders should have FTPdetectinfo files together with platepar files.""",
        formatter_class=argparse.RawTextHelpFormatter)

    arg_parser.add_argument('dir_path', type=str, help='Path to the root data directory. Trajectory helper files will be stored here as well.')

    arg_parser.add_argument('-t', '--maxtoffset', metavar='MAX_TOFFSET', \
        help='Maximum time offset between the stations. Default is 5 seconds.', type=float, default=10.0)

    arg_parser.add_argument('-s', '--maxstationdist', metavar='MAX_STATION_DIST', \
        help='Maximum distance (km) between stations of paired meteors. Default is 300 km.', type=float, \
        default=300.0)

    arg_parser.add_argument('-m', '--minerr', metavar='MIN_ARCSEC_ERR', \
        help="Minimum error in arc seconds below which the station won't be rejected. 30 arcsec by default.", \
        type=float)

    arg_parser.add_argument('-M', '--maxerr', metavar='MAX_ARCSEC_ERR', \
        help="Maximum error in arc seconds, above which the station will be rejected. 180 arcsec by default.", \
        type=float)

    arg_parser.add_argument('-v', '--maxveldiff', metavar='MAX_VEL_DIFF', \
        help='Maximum difference in percent between velocities between two stations. Default is 25 percent.', \
        type=float, default=25.0)

    arg_parser.add_argument('-p', '--velpart', metavar='VELOCITY_PART', \
        help='Fixed part from the beginning of the meteor on which the initial velocity estimation using the sliding fit will start. Default is 0.4 (40 percent), but for noisier data this should be bumped up to 0.5.', \
        type=float, default=0.40)

    arg_parser.add_argument('-d', '--disablemc', \
        help='Disable Monte Carlo.', action="store_true")

    arg_parser.add_argument('-l', '--saveplots', \
        help='Save plots to disk.', action="store_true")


    arg_parser.add_argument('-r', '--timerange', metavar='TIME_RANGE', \
        help="""Only compute the trajectories in the given range of time. The time range should be given in the format: "(YYYYMMDD-HHMMSS,YYYYMMDD-HHMMSS)".""", \
            type=str)


    # Parse the command line arguments
    cml_args = arg_parser.parse_args()

    ############################


    # Init trajectory constraints
    trajectory_constraints = TrajectoryConstraints()
    trajectory_constraints.max_toffset = cml_args.maxtoffset
    trajectory_constraints.max_station_dist = cml_args.maxstationdist
    trajectory_constraints.max_vel_percent_diff = cml_args.maxveldiff
    trajectory_constraints.run_mc = not cml_args.disablemc
    trajectory_constraints.save_plots = cml_args.saveplots

    if cml_args.minerr is not None:
        trajectory_constraints.min_arcsec_err = cml_args.minerr

    if cml_args.maxerr is not None:
        trajectory_constraints.max_arcsec_err = cml_args.maxerr



    # Clock for measuring script time
    t1 = datetime.datetime.utcnow()

    # Init the data handle
    dh = RMSDataHandle(cml_args.dir_path)


    # If there is nothing to process, stop
    if not dh.processing_list:
        print()
        print("Nothing to process!")
        print("Probably everything is already processed.")
        print("Exiting...")
        sys.exit()



    # If the time range to use is given, use it
    event_time_range = None
    if cml_args.timerange is not None:

        # Extract time range
        time_beg, time_end = cml_args.timerange.strip("(").strip(")").split(",")
        dt_beg = datetime.datetime.strptime(time_beg, "%Y%m%d-%H%M%S")
        dt_end = datetime.datetime.strptime(time_end, "%Y%m%d-%H%M%S")

        print("Custom time range:")
        print("    BEG: {:s}".format(str(dt_beg)))
        print("    END: {:s}".format(str(dt_end)))

        event_time_range = [dt_beg, dt_end]


    ### GENERATE MONTHLY TIME BINS ###
    
    # Find the range of datetimes of all folders (take only those after the year 2000)
    proc_dir_dts = [entry[3] for entry in dh.processing_list if entry[3] is not None]
    proc_dir_dts = [dt for dt in proc_dir_dts if dt > datetime.datetime(2000, 1, 1, 0, 0, 0)]

    # Determine the limits of data
    proc_dir_dt_beg = min(proc_dir_dts)
    proc_dir_dt_end = max(proc_dir_dts)

    # Split the processing into monthly chunks
    dt_bins = generateDatetimeBins(proc_dir_dt_beg, proc_dir_dt_end, bin_days=30)

    print()
    print("ALL TIME BINS:")
    print("----------")
    for bin_beg, bin_end in dt_bins:
        print("{:s}, {:s}".format(str(bin_beg), str(bin_end)))


    ### ###


    # Go through all chunks in time
    for bin_beg, bin_end in dt_bins:

        print()
        print("PROCESSING TIME BIN:")
        print(bin_beg, bin_end)
        print("-----------------------------")
        print()

        # Load data of unprocessed observations
        dh.unprocessed_observations = dh.loadUnprocessedObservations(dh.processing_list, \
            dt_range=(bin_beg, bin_end))

        # Run the trajectory correlator
        tc = TrajectoryCorrelator(dh, trajectory_constraints, cml_args.velpart, data_in_j2000=True)
        tc.run(event_time_range=event_time_range)


    
    print("Total run time: {:s}".format(str(datetime.datetime.utcnow() - t1)))