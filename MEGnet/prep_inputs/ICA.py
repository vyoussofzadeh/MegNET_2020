#!/usr/bin/env python
# coding: utf-8

# TODO:  Apply bad channel finder for fif prior to ICA 
# READ HCP ICAs in using MNE-hcp
# Write out images as front end for MEGNET
# Write out time chunks for MEGNET

import os
import numpy as np
import matplotlib.pyplot as plt
import mne
from mne.preprocessing import ICA
from scipy.spatial import ConvexHull, convex_hull_plot_2d
from scipy import interpolate

# =============================================================================
# Helper Functions
# =============================================================================

# function to transform Cartesian coordinates to spherical coordinates
# theta = azimuth
# phi = elevation

def cart2sph(x, y, z):
    xy = np.sqrt(x*x + y*y)
    r = np.sqrt(x*x + y*y + z*z)
    theta = np.arctan2(y,x)
    phi = np.arctan2(z,xy)
    return r, theta, phi

# function to transform 2d polar coordinates to Cartesian
def pol2cart(rho,phi):
    x = rho * np.cos(phi)
    y = rho * np.sin(phi)
    return x,y

# function to transform 2d Cartesian coodinates to polar coordinates
def cart2pol(x,y):
    r = np.sqrt(x*x + y*y)
    theta = np.arctan2(y,x)
    return r,theta
# re-write of the MNE python function make_head_outlines() without the nose and ears, with expansion 
# of the outline to 1.01 

def make_head_outlines_new(sphere, pos, outlines, clip_origin):
    """Check or create outlines for topoplot."""
    assert isinstance(sphere, np.ndarray)
    x, y, _, radius = sphere
    del sphere

    ll = np.linspace(0, 2 * np.pi, 101)
    head_x = np.cos(ll) * radius*1.01 + x
    head_y = np.sin(ll) * radius*1.01 + y
    dx = np.exp(np.arccos(np.deg2rad(12)) * 1j)
    dx, dy = dx.real, dx.imag
    
    outlines_dict = dict(head=(head_x, head_y))
    
    # Make the figure encompass slightly more than all points
    mask_scale = 1.
    # We probably want to ensure it always contains our most
    # extremely positioned channels, so we do:
    mask_scale = max(
            mask_scale, np.linalg.norm(pos, axis=1).max() * 1.01 / radius)
    
    outlines_dict['mask_pos'] = (mask_scale * head_x, mask_scale * head_y)
    clip_radius = radius * mask_scale
    outlines_dict['clip_radius'] = (clip_radius,) * 2
    outlines_dict['clip_origin'] = clip_origin      
    
    return outlines_dict

# =============================================================================
# 
# =============================================================================

def raw_preprocess(raw, mains_freq=None):
    resample_freq = 250
    #notch_freqs = range(mains_freq, int(resample_freq * 2/3), mains_freq)
    raw.notch_filter(mains_freq) #notch_freqs)
    raw.resample(resample_freq)
    raw.filter(1.0, 100)
    return raw
    
     
def calc_ica(raw, file_base=None, mains_freq=60, 
             save=False, seedval=0):
    ica = ICA(n_components=20, random_state=seedval, method='infomax')
    ica.fit(raw)
    if save==True:
        out_filename = file_base + '_{}-ica.fif'.format(str(seedval))
        ica.save(out_filename)
    return ica

def main(filename, outbasename=None, mains_freq=60, 
             save_preproc=False, save_ica=False, seedval=0,
             results_dir='/fast/results_ica'):
    raw = read_raw(filename)
    raw = raw_preprocess(raw, mains_freq)
    
    #Set output names
    if outbasename != None:
        file_base = outbasename #Necessary for 4D datasets
    else:
        file_base = os.path.basename(filename)
        file_base = os.path.splitext(file_base)[0]
    
    if save_preproc==True:
        raw.save(file_base+'_250srate_meg.fif') #Save with EEG
    raw.pick_types(meg=True, eeg=False, ref_meg=False)
    
    ica = calc_ica(raw, file_base=file_base, mains_freq=mains_freq, 
                   save=save_ica, seedval=seedval)
    
    circle_pos = sensor_pos2circle(raw, ica)
    
    for comp in np.arange(0,ica.n_components,1):
        data = np.dot(ica.mixing_matrix_[:,comp].T,ica.pca_components_[:ica.n_components_])
        
        out_fname = f'{results_dir}/{file_base}-ica-{str(comp)}.png'
        circle_plot(circle_pos=circle_pos, 
                    data=data, 
                    out_fname=out_fname)
        
    
    

def test_main():
    filename = '/fast/BIDS_HV_V1/bids/sub-ON02747/ses-01/meg/sub-ON02747_ses-01_task-airpuff_run-01_meg.ds'
    raw = read_raw(filename)
    assert raw.compensation_grade == 3
    assert isinstance(raw, mne.io.ctf.ctf.RawCTF)
    
    filename = '/tmp/test/MNE-sample-data/MEG/sample/sample_audvis_raw.fif'
    raw = read_raw(filename)
    assert isinstance(raw, mne.io.fiff.raw.Raw)
    
def read_raw(filename):
    '''
    Use the appropriate MNE io reader for the MEG type
    For CTF/.ds datasets, gradient compensation will be checked and applied if
    needed.

    Parameters
    ----------
    filename : Path or PathStr
        Path to file

    Returns
    -------
    Raw MNE instance

    '''
    ext = os.path.splitext(filename)[-1]
    if ext == '.fif':
        raw = mne.io.read_raw_fif(filename, preload=True)
    elif ext == '.ds':
        raw = mne.io.read_raw_ctf(filename, preload=True, 
                                  system_clock='ignore', clean_names=True)
        if raw.compensation_grade != 3:
            raw.apply_gradient_compensation(3)
    #XXX Hack -- figure out the correct way to identify 4D/BTI data
    #Do we need to do ref compensation calculation?
    elif filename[-4:]=='rfDC':
        raw = mne.io.read_raw_bti(filename, preload=True, head_shape_fname=None)
    #XXX Hack - Confirm KIT assignment
    elif ext == '.sqd':
        raw = mne.io.read_raw_kit(filename, preload=True)
    return raw


def test_reader():
    filename = '/fast/BIDS_HV_V1/bids/sub-ON02747/ses-01/meg/sub-ON02747_ses-01_task-airpuff_run-01_meg.ds'
    raw = read_raw(filename)
    assert raw.compensation_grade == 3
    assert isinstance(raw, mne.io.ctf.ctf.RawCTF)
    
    filename = '/tmp/test/MNE-sample-data/MEG/sample/sample_audvis_raw.fif'
    raw = read_raw(filename)
    assert isinstance(raw, mne.io.fiff.raw.Raw)



def sensor_pos2circle(raw, ica):
    '''
    Project the sensor positions to a unit circle and return positions
    Currently works with MNE chan_type == mag  (includes CTF ax gradiometers)

    Parameters
    ----------
    raw : mne.io.{fiff,ds}.raw.Raw
        Mne format dataset.  
    ica : mne.preprocessing.ica.ICA
        MNE ICA instance

    Returns
    -------
    pos_new : numpy.ndarray 
        Position of channels projected to the unit circle. (#chans X 2)

    '''
    num_chans = len(raw.ch_names)
    n_components = ica.n_components
    # extract magnetometer positions
    data_picks, pos, merge_channels, names, ch_type, sphere, clip_origin = \
        mne.viz.topomap._prepare_topomap_plot(ica, 'mag')
    
    #Extract channel locations
    # 'loc' has 12 elements, the location plus a 3x3 orientation matrix 
    tmp_ = [i['loc'][0:3] for i in raw.info['chs']]
    channel_locations3d = np.stack(tmp_)
    
    tmp_ = np.array([cart2sph(*i) for i in channel_locations3d])
    channel_locations_3d_spherical = tmp_ #np.transpose(tmp_) 
    
    TH=channel_locations_3d_spherical[:,1]
    PHI=channel_locations_3d_spherical[:,2]
    
    # project the spherical locations to a plane
    # this calculates a new R for each coordinate, based on PHI
    # then transform the projection to Cartesian coordinates
    channel_locations_2d=np.zeros([num_chans,2])
    newR=np.zeros((num_chans,))
    newR = 1 - PHI/np.pi*2
    channel_locations_2d=np.transpose(pol2cart(newR,TH))
    X=channel_locations_2d[:,0]
    Y=channel_locations_2d[:,1]
    
    # use ConvexHull to get the sensor indices around the edges, 
    # and scale their radii to a unit circle
    hull = ConvexHull(channel_locations_2d)
    Border=hull.vertices
    Dborder = 1/newR[Border]
    
    # Define an interpolation function of the TH coordinate to define a scaling factor for R
    FuncTh=np.hstack([TH[Border]-2*np.pi, TH[Border], TH[Border]+2*np.pi]) #.reshape((57,));  #<<<< 57 doesnt work - does this need to be here
    funcD=np.hstack((Dborder,Dborder,Dborder))
    finterp = interpolate.interp1d(FuncTh,funcD);
    D = finterp(TH)
    
    # Apply the scaling to every radii coordinate and transform back to Cartesian coordinates
    newerR=np.zeros((num_chans,))
    for i in np.arange(0,num_chans):
        newerR[i] = min(newR[i]*D[i],1)
    [Xnew,Ynew]=pol2cart(newerR,TH)
    pos_new=np.transpose(np.vstack((Xnew,Ynew)))
    return pos_new



def circle_plot(circle_pos=None, data=None, out_fname=None):
    '''Generate the plot and save'''
    # create a circular outline without nose and ears, and get coordinates
    outlines_new = make_head_outlines_new(np.array([0,0,0,1]),
                                          circle_pos,
                                          'head',
                                          (0,0))
    outline_coords=np.array(outlines_new['head'])
    fig, _ = mne.viz.plot_topomap(data,circle_pos,
                                sensors=False,
                                outlines=outlines_new,
                                extrapolate='head',
                                sphere=[0,0,0,1.0],
                                contours=0,res=128,
                                show=False)
    fig.figure.savefig(out_fname)
    
    


