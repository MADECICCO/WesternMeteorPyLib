""" Aggregate trajectory results into one results file and generate plots of trajectory results. """

from __future__ import print_function, division, absolute_import


import os
import datetime

import numpy as np
import scipy.stats
import scipy.ndimage


from wmpl.Utils.Math import averageClosePoints, meanAngle, sphericalPointFromHeadingAndDistance
from wmpl.Utils.Physics import calcMass
from wmpl.Utils.Pickling import loadPickle
from wmpl.Utils.PlotCelestial import CelestialPlot
from wmpl.Utils.PlotMap import MapColorScheme
from wmpl.Utils.ShowerAssociation import associateShowerTraj, MeteorShower
from wmpl.Utils.SolarLongitude import jd2SolLonSteyaert
from wmpl.Utils.TrajConversions import jd2Date




### CONSTANTS ###
    
# Trajectory summary file name
TRAJ_SUMMARY_FILE = "trajectory_summary.txt"


# Minimum number of shower members to mark the shower
MIN_SHOWER_MEMBERS = 3

# Plot shower radius (deg)
PLOT_SHOWER_RADIUS = 3.0

### ###



def writeOrbitSummaryFile(dir_path, traj_list, P_0m=1210):
    """ Given a list of trajectory files, generate CSV file with the orbit summary. """

    def _uncer(traj, str_format, std_name, multi=1.0, deg=False, max_val=None, max_val_format="{:7.1e}"):
        """ Internal function. Returns the formatted uncertanty, if the uncertanty is given. If not,
            it returns nothing. 

        Arguments:
            traj: [Trajectory instance]
            str_format: [str] String format for the unceertanty.
            std_name: [str] Name of the uncertanty attribute, e.g. if it is 'x', then the uncertanty is 
                stored in uncertainties.x.
    
        Keyword arguments:
            multi: [float] Uncertanty multiplier. 1.0 by default. This is used to scale the uncertanty to
                different units (e.g. from m/s to km/s).
            deg: [bool] Converet radians to degrees if True. False by defualt.
            max_val: [float] Larger number to use the given format. If the value is larger than that, the
                max_val_format is used.
            max_val_format: [str]
            """

        if deg:
            multi *= np.degrees(1.0)

        if traj.uncertainties is not None:
            if hasattr(traj.uncertainties, std_name):

                # Get the value
                val = getattr(traj.uncertainties, std_name)*multi

                # If the value is too big, use scientific notation
                if max_val is not None:
                    if val > max_val:
                        str_format = max_val_format

                return str_format.format(val)

        
        return "None"

    # Sort trajectories by Julian date
    traj_list = sorted(traj_list, key=lambda x: x.jdt_ref)


    delimiter = "; "

    out_str =  ""
    out_str += "# Summary generated on {:s} UTC\n\r".format(str(datetime.datetime.utcnow()))

    header = ["   Beginning      ", "       Beginning          ", "  IAU", " IAU", "  Sol lon ", "  App LST ", "  RAgeo  ", "  +/-  ", "  DECgeo ", "  +/-  ", " LAMgeo  ", "  +/-  ", "  BETgeo ", "  +/-  ", "   Vgeo  ", "   +/- ", " LAMhel  ", "  +/-  ", "  BEThel ", "  +/-  ", "   Vhel  ", "   +/- ", "      a    ", "  +/-  ", "     e    ", "  +/-  ", "     i    ", "  +/-  ", "   peri   ", "   +/-  ", "   node   ", "   +/-  ", "    Pi    ", "  +/-  ", "     q    ", "  +/-  ", "     f    ", "  +/-  ", "     M    ", "  +/-  ", "      Q    ", "  +/-  ", "     n    ", "  +/-  ", "     T    ", "  +/-  ", "TisserandJ", "  +/-  ", "  RAapp  ", "  +/-  ", "  DECapp ", "  +/-  ", " Azim +E ", "  +/-  ", "   Elev  ", "  +/-  ", "  Vinit  ", "   +/- ", "   Vavg  ", "   +/- ", "   LatBeg   ", "  +/-  ", "   LonBeg   ", "  +/-  ", "  HtBeg ", "  +/-  ", "   LatEnd   ", "  +/-  ", "   LonEnd   ", "  +/-  ", "  HtEnd ", "  +/-  ", "Duration", " Peak ", " Peak Ht", " Mass kg", "  Qc ", "MedianFitErr", "Beg in", "End in", " Num", "     Participating    "]
    head_2 = ["  Julian date     ", "        UTC Time          ", "   No", "code", "    deg   ", "    deg   ", "   deg   ", " sigma ", "   deg   ", " sigma ", "   deg   ", " sigma ", "    deg  ", " sigma ", "   km/s  ", "  sigma", "   deg   ", " sigma ", "    deg  ", " sigma ", "   km/s  ", "  sigma", "     AU    ", " sigma ", "          ", " sigma ", "   deg    ", " sigma ", "    deg   ", "  sigma ", "    deg   ", "  sigma ", "   deg    ", " sigma ", "    AU    ", " sigma ", "   deg    ", " sigma ", "    deg   ", " sigma ", "     AU    ", " sigma ", "  deg/day ", " sigma ", "   years  ", " sigma ", "          ", " sigma ", "   deg   ", " sigma ", "   deg   ", " sigma ", "of N  deg", " sigma ", "    deg  ", " sigma ", "   km/s  ", "  sigma", "   km/s  ", "  sigma", "   +N deg   ", " sigma ", "   +E deg   ", " sigma ", "    km  ", " sigma ", "   +N deg   ", " sigma ", "   +E deg   ", " sigma ", "    km  ", " sigma ", "  sec   ", "AbsMag", "    km  ", "tau=0.7%", " deg ", "   arcsec   ", "  FOV ", "  FOV ", "stat", "        stations      "]
    out_str += "# {:s}\n\r".format(delimiter.join(header))
    out_str += "# {:s}\n\r".format(delimiter.join(head_2))

    # Add a horizontal line
    out_str += "# {:s}\n\r".format("; ".join(["-"*len(entry) for entry in header]))

    # Write lines of data
    for traj in traj_list:

        line_info = []

        line_info.append("{:20.12f}".format(traj.jdt_ref))
        line_info.append("{:26s}".format(str(jd2Date(traj.jdt_ref, dt_obj=True))))

        # Perform shower association
        shower_obj = associateShowerTraj(traj)
        if shower_obj is None:
            shower_no = -1
            shower_code = '...'
        else:
            shower_no = shower_obj.IAU_no
            shower_code = shower_obj.IAU_code

        line_info.append("{:>5d}".format(shower_no))
        line_info.append("{:>4s}".format(shower_code))


        # Geocentric radiant (equatorial and ecliptic)
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.la_sun)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.lst_ref)))
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.ra_g)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'ra_g', deg=True, max_val=100.0)))
        line_info.append("{:>+9.5f}".format(np.degrees(traj.orbit.dec_g)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'dec_g', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.L_g)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'L_g', deg=True, max_val=100.0)))
        line_info.append("{:>+9.5f}".format(np.degrees(traj.orbit.B_g)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'B_g', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(traj.orbit.v_g/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'v_g', multi=1.0/1000)))

        # Ecliptic heliocentric radiant
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.L_h)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'L_h', deg=True, max_val=100.0)))
        line_info.append("{:>+9.5f}".format(np.degrees(traj.orbit.B_h)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'B_h', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(traj.orbit.v_h/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'v_h', multi=1.0/1000)))

        # Orbital elements
        if abs(traj.orbit.a) < 1000:
            line_info.append("{:>11.6f}".format(traj.orbit.a))
        else:
            line_info.append("{:>11.2e}".format(traj.orbit.a))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'a', max_val=100.0)))
        line_info.append("{:>10.6f}".format(traj.orbit.e))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'e')))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.i)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'i', deg=True)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.peri)))
        line_info.append("{:>8s}".format(_uncer(traj, '{:.4f}', 'peri', deg=True)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.node)))
        line_info.append("{:>8s}".format(_uncer(traj, '{:.4f}', 'node', deg=True)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.pi)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'pi', deg=True)))
        line_info.append("{:>10.6f}".format(traj.orbit.q))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'q')))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.true_anomaly)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'true_anomaly', deg=True)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.mean_anomaly)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'mean_anomaly', deg=True)))
        if abs(traj.orbit.Q) < 1000:
            line_info.append("{:>11.6f}".format(traj.orbit.Q))
        else:
            line_info.append("{:>11.4e}".format(traj.orbit.Q))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'Q', max_val=100.0)))
        line_info.append("{:>10.6f}".format(np.degrees(traj.orbit.n)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'n', deg=True, max_val=100.0)))
        if traj.orbit.T < 1000:
            line_info.append("{:>10.6f}".format(traj.orbit.T))
        else:
            line_info.append("{:>10.4e}".format(traj.orbit.T))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'T', max_val=100.0)))
        line_info.append("{:>10.6f}".format(traj.orbit.Tj))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'Tj', max_val=100.0)))
        
        # Apparent radiant
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.ra_norot)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'ra_norot', deg=True, max_val=100.0)))
        line_info.append("{:>+9.5f}".format(np.degrees(traj.orbit.dec_norot)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'dec_norot', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.azimuth_apparent_norot)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'azimuth_apparent', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(np.degrees(traj.orbit.elevation_apparent_norot)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'elevation_apparent', deg=True, max_val=100.0)))
        line_info.append("{:>9.5f}".format(traj.orbit.v_init_norot/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'v_init', multi=1.0/1000)))
        line_info.append("{:>9.5f}".format(traj.orbit.v_avg_norot/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:7.4f}', 'v_avg', multi=1.0/1000)))

        # Begin/end point
        line_info.append("{:>12.6f}".format(np.degrees(traj.rbeg_lat)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'rbeg_lat', deg=True)))
        line_info.append("{:>12.6f}".format(np.degrees(traj.rbeg_lon)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'rbeg_lon', deg=True)))
        line_info.append("{:>8.4f}".format(traj.rbeg_ele/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.2f}', 'rbeg_ele', multi=1.0/1000)))
        line_info.append("{:>12.6f}".format(np.degrees(traj.rend_lat)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'rend_lat', deg=True)))
        line_info.append("{:>12.6f}".format(np.degrees(traj.rend_lon)))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.4f}', 'rend_lon', deg=True)))
        line_info.append("{:>8.4f}".format(traj.rend_ele/1000))
        line_info.append("{:>7s}".format(_uncer(traj, '{:.2f}', 'rend_ele', multi=1.0/1000)))

        
        
        # Compute the duration
        duration = max([np.max(obs.time_data[obs.ignore_list == 0]) for obs in traj.observations \
            if obs.ignore_station == False])

        # Compute the peak magnitude and the peak height
        peak_mags = [np.min(obs.absolute_magnitudes[obs.ignore_list == 0]) for obs in traj.observations \
            if obs.ignore_station == False]
        peak_mag = np.min(peak_mags)
        peak_ht = [obs.model_ht[np.argmin(obs.absolute_magnitudes[obs.ignore_list == 0])] for obs in traj.observations \
            if obs.ignore_station == False][np.argmin(peak_mags)]


        ### Compute the mass

        time_mag_arr = []
        avg_t_diff_max = 0
        for obs in traj.observations:

            # Skip ignored stations
            if obs.ignore_station:
                continue

            # If there are not magnitudes for this site, skip it
            if obs.absolute_magnitudes is None:
                continue

            # Compute average time difference
            avg_t_diff_max = max(avg_t_diff_max, np.median(obs.time_data[1:] - obs.time_data[:-1]))

            for t, mag in zip(obs.time_data, obs.absolute_magnitudes):
                if (mag is not None) and (not np.isnan(mag)):
                    time_mag_arr.append([t, mag])


        # Compute the mass
        time_mag_arr = np.array(sorted(time_mag_arr, key=lambda x: x[0]))
        time_arr, mag_arr = time_mag_arr.T
        
        # Average out the magnitudes
        time_arr, mag_arr = averageClosePoints(time_arr, mag_arr, avg_t_diff_max)

        # Compute the photometry mass
        mass = calcMass(np.array(time_arr), np.array(mag_arr), traj.orbit.v_avg_norot, P_0m=P_0m)

        ###


        # Meteor parameters (duration, peak magnitude, integrated intensity, Q angle)
        line_info.append("{:8.2f}".format(duration))
        line_info.append("{:+6.2f}".format(peak_mag))
        line_info.append("{:>8.4f}".format(peak_ht/1000))
        line_info.append("{:8.2e}".format(mass))

        # Convergence angle
        line_info.append("{:5.2f}".format(np.degrees(traj.best_conv_inter.conv_angle)))

        # Median fit error in arcsec
        line_info.append("{:12.2f}".format(3600*np.degrees(np.median([obs.ang_res_std for obs \
            in traj.observations if not obs.ignore_station]))))


        # Meteor begins inside the FOV
        fov_beg = None
        fov_beg_list = [obs.fov_beg for obs in traj.observations if (obs.ignore_station == False) \
            and hasattr(obs, "fov_beg")]
        if len(fov_beg_list) > 0:
            fov_beg = np.any(fov_beg_list)

        line_info.append("{:>6s}".format(str(fov_beg)))

        # Meteor ends inside the FOV
        fov_end = None
        fov_end_list = [obs.fov_end for obs in traj.observations if (obs.ignore_station == False) \
            and hasattr(obs, "fov_end")]
        if len(fov_end_list) > 0:
            fov_end = np.any(fov_end_list)

        line_info.append("{:>6s}".format(str(fov_end)))


        # Participating stations
        participating_stations = sorted([obs.station_id for obs in traj.observations \
            if obs.ignore_station == False])
        line_info.append("{:>4d}".format(len(participating_stations)))
        line_info.append("{:s}".format(",".join(participating_stations)))


        out_str += delimiter.join(line_info) + "\n\r"


    # Save the file to a trajectory summary
    traj_summary_path = os.path.join(dir_path, TRAJ_SUMMARY_FILE)
    with open(traj_summary_path, 'w') as f:
        f.write(out_str)

    print("Trajectory summary saved to:", traj_summary_path)





def plotSCE(x_data, y_data, color_data, sol_range, plot_title, colorbar_title, dir_path, \
    file_name, density_plot=False, plot_showers=False, shower_obj_list=None):

    ### PLOT SUN-CENTERED GEOCENTRIC ECLIPTIC RADIANTS ###

    fig = plt.figure(figsize=(16, 8), facecolor='k')


    # Init the allsky plot
    celes_plot = CelestialPlot(x_data, y_data, projection='sinu', lon_0=-90, ax=fig.gca())

    # ### Mark the sources ###
    # sources_lg = np.radians([0, 270, 180])
    # sources_bg = np.radians([0, 0, 0])
    # sources_labels = ["Helion", "Apex", "Antihelion"]
    # celes_plot.scatter(sources_lg, sources_bg, marker='x', s=15, c='0.75')

    # # Convert angular coordinates to image coordinates
    # x_list, y_list = celes_plot.m(np.degrees(sources_lg), np.degrees(sources_bg + np.radians(2.0)))
    # for x, y, lbl in zip(x_list, y_list, sources_labels):
    #     plt.text(x, y, lbl, color='w', ha='center', alpha=0.5)

    # ### ###

    fg_color = 'white'

    # Choose the colormap
    if density_plot:
        cmap_name = 'inferno'
        cmap_bottom_cut = 0.0
    else:
        cmap_name = 'viridis'
        cmap_bottom_cut = 0.2


    # Cut the dark portion of the colormap
    cmap = plt.get_cmap(cmap_name)
    colors = cmap(np.linspace(cmap_bottom_cut, 1.0, cmap.N))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list('cut_cmap', colors)


    ### Do a KDE density plot
    if density_plot:

        # Define extent and density
        lon_min = -180
        lon_max = 180
        lat_min = -90
        lat_max = 90
        delta_deg = 0.5

        lon_bins = np.linspace(lon_min, lon_max, int(360/delta_deg))
        lat_bins = np.linspace(lat_min, lat_max, int(180/delta_deg))

        # Rotate all coordinates by 90 deg to make them Sun-centered
        x_data = np.array(x_data)
        y_data = np.array(y_data)
        lon_corr = (np.degrees(x_data) + 90)%360

        # Do a sinus projection
        lon_corr_temp = np.zeros_like(lon_corr)
        lon_corr_temp[lon_corr > 180] = ((180 - lon_corr[lon_corr > 180] + 180)*np.cos(y_data[lon_corr > 180]))
        lon_corr_temp[lon_corr <= 180] = ((180 - lon_corr[lon_corr <= 180] - 180)*np.cos(y_data[lon_corr <= 180]))
        lon_corr = lon_corr_temp

        # Compute the histogram
        data, _, _ = np.histogram2d(lon_corr, 
            np.degrees(np.array(y_data)), bins=(lon_bins, lat_bins))

        # Apply Gaussian filter to it
        data = scipy.ndimage.filters.gaussian_filter(data, 1.0)*4*np.pi

        plt_handle = celes_plot.m.imshow(data.T, origin='lower', extent=[lon_min, lon_max, lat_min, lat_max],\
            #interpolation='gaussian', norm=matplotlib.colors.PowerNorm(gamma=1./2.), cmap=cmap)
            interpolation='gaussian', norm=matplotlib.colors.LogNorm(vmin=1.0, vmax=100), cmap=cmap)

        # Plot the colorbar
        ticks = [1, 5, 10, 20, 50, 100]
        cb = fig.colorbar(plt_handle, ticks=ticks, format="%.0f")


    else:
        
        ### Do a scatter plot

        # Compute the dot size which varies by the number of data points
        dot_size = 40*(1.0/np.sqrt(len(x_data)))
        if dot_size > 1:
            dot_size = 1

        # Plot the data
        plt_handle = celes_plot.scatter(x_data, y_data, color_data, s=dot_size, cmap=cmap)
    
        # Plot the colorbar
        cb = fig.colorbar(plt_handle)




    # Plot showers, if given
    if plot_showers and (shower_obj_list is not None):
        for shower_obj in shower_obj_list:

            # Compute the plotting coordinates
            lam = shower_obj.L_g - shower_obj.la_sun
            bet = shower_obj.B_g


            ### Plot a <PLOT_SHOWER_RADIUS> deg radius circle around the shower centre ###
            
            # Generate circle data points
            heading_arr = np.linspace(0, 2*np.pi, 50)
            bet_arr, lam_arr = sphericalPointFromHeadingAndDistance(bet, lam, heading_arr, \
                np.radians(PLOT_SHOWER_RADIUS))

            # Plot the circle
            celes_plot.plot(lam_arr, bet_arr, color='w', alpha=0.5)

            ### ###


            #### Plot the name of the shower ###

            # The name orientation is determined by the quadrant, so all names "radiate" from the 
            #   centre of the plot
            heading = 0
            lam_check = (lam - np.radians(270))%(2*np.pi)
            va = 'top'
            if lam_check < np.pi:
                ha = 'right'
                if bet > 0:
                    heading = -np.pi/4
                    va = 'bottom'
                else:
                    heading = -3*np.pi/4
            else:
                ha = 'left'
                if bet > 0:
                    heading = np.pi/4
                    va = 'bottom'
                else:
                    heading = 3*np.pi/4

            # Get the shower name location
            bet_txt, lam_txt = sphericalPointFromHeadingAndDistance(bet, lam, heading, \
                np.radians(PLOT_SHOWER_RADIUS))

            # Plot the shower name
            celes_plot.text(shower_obj.IAU_code, lam_txt, bet_txt, ha=ha, va=va, color='w', alpha=0.5)






            ### ###





    
    # Tweak the colorbar
    cb.set_label(colorbar_title, color=fg_color)
    cb.ax.yaxis.set_tick_params(color=fg_color)
    cb.outline.set_edgecolor(fg_color)
    plt.setp(plt.getp(cb.ax.axes, 'yticklabels'), color=fg_color)


    plt.title(plot_title, color=fg_color)

    # Plot solar longitude range and count
    sol_min, sol_max = sol_range
    # plt.annotate(u"$\lambda_{\u2609 min} =$" + u"{:>5.2f}\u00b0".format(sol_min) \
    #     + u"\n$\lambda_{\u2609 max} =$" + u"{:>5.2f}\u00b0".format(sol_max), \
    #     xy=(0, 1), xycoords='axes fraction', color='w', size=12, family='monospace')
    plt.annotate(u"Sol min = {:>6.2f}\u00b0".format(sol_min) \
        + u"\nSol max = {:>6.2f}\u00b0".format(sol_max)
        + "\nCount = {:d}".format(len(x_data)), \
        xy=(0, 1), xycoords='axes fraction', color='w', size=10, family='monospace')

    plt.tight_layout()

    plt.savefig(os.path.join(dir_path, file_name), dpi=100, facecolor=fig.get_facecolor(), \
        edgecolor='none')

    plt.close()

    ### ###



def generateTrajectoryPlots(dir_path, traj_list, plot_name='scecliptic', plot_vg=True, plot_sol=True, \
    plot_density=True, plot_showers=False):
    """ Given a path with trajectory .pickle files, generate orbits plots. """



    ### Plot Sun-centered geocentric ecliptic plots ###

    lambda_list = []
    beta_list = []
    vg_list = []
    sol_list = []

    shower_no_list = []
    shower_obj_dict = {}

    hypo_count = 0
    jd_min = np.inf
    jd_max = 0
    for traj in traj_list:

        # Reject all hyperbolic orbits
        if traj.orbit.e > 1:
            hypo_count += 1
            continue

        # Compute Sun-centered longitude
        lambda_list.append(traj.orbit.L_g - traj.orbit.la_sun)

        beta_list.append(traj.orbit.B_g)
        vg_list.append(traj.orbit.v_g/1000)
        sol_list.append(np.degrees(traj.orbit.la_sun))

        # Track first and last observation
        jd_min = min(jd_min, traj.jdt_ref)
        jd_max = max(jd_max, traj.jdt_ref)



        if plot_showers:

            # Perform shower association and track the list of all showers
            shower_obj = associateShowerTraj(traj)

            # If the trajectory was associated, sort it to the appropriate shower
            if shower_obj is not None:
                if shower_obj.IAU_no not in shower_no_list:
                    shower_no_list.append(shower_obj.IAU_no)
                    shower_obj_dict[shower_obj.IAU_no] = [shower_obj]
                else:
                    shower_obj_dict[shower_obj.IAU_no].append(shower_obj)



    # Compute mean shower radiant for all associated showers
    shower_obj_list = []
    if plot_showers and shower_obj_dict:
        for shower_no in shower_obj_dict:

            # Check if there are enough shower members for plotting
            if len(shower_obj_dict[shower_no]) < MIN_SHOWER_MEMBERS:
                continue

            la_sun_mean = meanAngle([sh.la_sun for sh in shower_obj_dict[shower_no]])
            L_g_mean = meanAngle([sh.L_g for sh in shower_obj_dict[shower_no]])
            B_g_mean = np.mean([sh.B_g for sh in shower_obj_dict[shower_no]])
            v_g_mean = np.mean([sh.v_g for sh in shower_obj_dict[shower_no]])

            # Init a new shower object
            shower_obj_mean = MeteorShower(la_sun_mean, L_g_mean, B_g_mean, v_g_mean, shower_no)

            shower_obj_list.append(shower_obj_mean)



    print("Hyperbolic percentage: {:.2f}%".format(100*hypo_count/len(traj_list)))

    # Compute the range of solar longitudes
    sol_min = np.degrees(jd2SolLonSteyaert(jd_min))
    sol_max = np.degrees(jd2SolLonSteyaert(jd_max))



    # Plot SCE vs Vg
    if plot_vg:
        plotSCE(lambda_list, beta_list, vg_list, (sol_min, sol_max), 
            "Sun-centered geocentric ecliptic coordinates", "$V_g$ (km/s)", dir_path, plot_name + "_vg.png", \
            shower_obj_list=shower_obj_list, plot_showers=plot_showers)


    # Plot SCE vs Sol
    if plot_sol:
        plotSCE(lambda_list, beta_list, sol_list, (sol_min, sol_max), \
            "Sun-centered geocentric ecliptic coordinates", "Solar longitude (deg)", dir_path, \
            plot_name + "_sol.png", shower_obj_list=shower_obj_list, plot_showers=plot_showers)
    

    
    # Plot SCE orbit density
    if plot_density:
        plotSCE(lambda_list, beta_list, None, (sol_min, sol_max), 
            "Sun-centered geocentric ecliptic coordinates", "Count", dir_path, plot_name + "_density.png", \
            density_plot=True, shower_obj_list=shower_obj_list, plot_showers=plot_showers)




def generateStationPlot(dir_path, traj_list, color_scheme='light'):
    """ Generate a plot of all stations participating in the trajectory estimation. """


    # Choose the color scheme
    cs = MapColorScheme()
    
    if color_scheme == 'light':
        cs.light()

    else:
        cs.dark()


    plt.figure(figsize=(19.2, 10.8))

    # Init the map
    m = Basemap(projection='cyl', resolution='i')

    # Draw the coast boundary and fill the oceans with the given color
    m.drawmapboundary(fill_color=cs.map_background)

    # Fill continents, set lake color same as ocean color
    m.fillcontinents(color=cs.continents, lake_color=cs.lakes, zorder=1)

    # Draw country borders
    m.drawcountries(color=cs.countries)
    m.drawstates(color=cs.states, linestyle='--')



    ### PLOT WORLD MAP ###

    # Group stations into countries
    country_dict = {}
    for traj in traj_list:

        for obs in traj.observations:

            # Extract country code
            country_code = obs.station_id[:2]

            if country_code not in country_dict:
                country_dict[country_code] = {}
            

            if obs.station_id not in country_dict[country_code]:
                country_dict[country_code][obs.station_id] = [obs.lat, obs.lon]



    # Plot stations in all countries
    for country_code in country_dict:

        station_dict = country_dict[country_code]

        # Extract lat/lon
        lat = np.degrees([station_dict[station_id][0] for station_id in station_dict])
        lon = np.degrees([station_dict[station_id][1] for station_id in station_dict])

        # Convert lat/lon to x/y
        x, y = m(lon, lat)

        plt.scatter(x, y, s=0.75, zorder=5, label="{:s}: {:d}".format(country_code, len(lat)))


    plt.legend(loc='lower left')

    plt.tight_layout()

    plt.savefig(os.path.join(dir_path, "world_map.png"), dpi=100)

    plt.close()

    ### ###





if __name__ == "__main__":

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.basemap import Basemap

    import argparse

    ### COMMAND LINE ARGUMENTS

    # Init the command line arguments parser
    arg_parser = argparse.ArgumentParser(description="""Given a folder with trajectory .pickle files, generate an orbit summary CSV file and orbital graphs.""",
        formatter_class=argparse.RawTextHelpFormatter)

    arg_parser.add_argument('dir_path', type=str, help='Path to the data directory. Trajectory pickle files are found in all subdirectories.')

    arg_parser.add_argument('-s', '--solstep', metavar='SOL_STEP', \
        help='Step in solar longitude for plotting (degrees). 2 deg by default.', type=float, default=2.0)

    # Parse the command line arguments
    cml_args = arg_parser.parse_args()

    ############################



    ### FILTERS ###

    # Minimum number of points on the trajectory for the station with the most points
    min_traj_points = 6

    # Minimum convergence angle (deg)
    min_qc = 5.0

    # Maximum eccentricity
    max_e = 1.5

    # Maximum radiant error (deg)
    max_radiant_err = 2.0

    # Maximum geocentric velocity error (percent)
    max_vg_err = 10.0

    # Begin/end height filters (km)
    max_begin_ht = 160
    min_end_ht = 20

    ### ###


    # Get a list of paths of all trajectory pickle files
    traj_list = []
    for entry in os.walk(cml_args.dir_path):

        dir_path, _, file_names = entry

        # Go through all files
        for file_name in file_names:

            # Check if the file is a pickel file
            if file_name.endswith("_trajectory.pickle"):

                # Load the pickle file
                traj = loadPickle(dir_path, file_name)

                
                # Skip those with no orbit solution
                if traj.orbit.ra_g is None:
                    continue


                ### MINIMUM POINTS
                ### Reject all trajectories with small number of used points ###
                points_count = [len(obs.time_data[obs.ignore_list == 0]) for obs in traj.observations \
                    if obs.ignore_station == False]

                if not points_count:
                    continue

                max_points = max(points_count)

                if max_points < min_traj_points:
                    # print("Skipping {:.2f} due to the small number of points...".format(traj.jdt_ref))
                    continue

                ###


                ### CONVERGENCE ANGLE                
                ### Reject all trajectories with a too small convergence angle ###

                if np.degrees(traj.best_conv_inter.conv_angle) < min_qc:
                    # print("Skipping {:.2f} due to the small convergence angle...".format(traj.jdt_ref))
                    continue

                ###


                ### MAXIMUM ECCENTRICITY ###

                if traj.orbit.e > max_e:
                    continue

                ###


                ### MAXIMUM RADIANT ERROR ###

                if traj.uncertainties is not None:
                    if np.degrees(np.hypot(traj.uncertainties.ra_g, \
                        traj.uncertainties.dec_g)) > max_radiant_err:

                        continue



                ### MAXIMUM GEOCENTRIC VELOCITY ERROR ###

                if traj.uncertainties is not None:
                    if traj.uncertainties.v_g > traj.orbit.v_g*max_vg_err/100:
                        continue

                ###


                ### HEIGHT FILTER ###

                if traj.rbeg_ele/1000 > max_begin_ht:
                    continue

                if traj.rend_ele/1000 < min_end_ht:
                    continue

                ###


                traj_list.append(traj)




    # Generate the orbit summary file
    print("Writing summary file...")
    writeOrbitSummaryFile(cml_args.dir_path, traj_list)

    # Generate summary plots
    print("Plotting all trajectories...")
    generateTrajectoryPlots(cml_args.dir_path, traj_list, plot_showers=False)

    # Generate station plot
    print("Plotting station plot...")
    generateStationPlot(cml_args.dir_path, traj_list)



    # Generate radiant plots per solar longitude (degrees)
    step = cml_args.solstep
    for sol_min in np.arange(0, 360 + step, step):
        sol_max = sol_min + step

        # Extract only those trajectories with solar longitudes in the given range
        traj_list_sol = [traj_temp for traj_temp in traj_list if \
            (np.degrees(traj_temp.orbit.la_sun) >= sol_min) \
            and (np.degrees(traj_temp.orbit.la_sun) < sol_max)]


        # Skip solar longitudes with no data
        if len(traj_list_sol) == 0:
            continue

        print("Plotting solar longitude range: {:.1f} - {:.1f}".format(sol_min, sol_max))


        # Plot graphs per solar longitude
        generateTrajectoryPlots(cml_args.dir_path, traj_list_sol, \
            plot_name="scecliptic_solrange_{:05.1f}-{:05.1f}".format(sol_min, sol_max), plot_sol=False, \
            plot_showers=True)
