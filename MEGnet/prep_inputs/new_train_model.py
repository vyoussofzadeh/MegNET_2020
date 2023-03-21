#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug 22 11:49:16 2022

@author: jstout
"""

import pandas as pd
import MEGnet
from os import path as op
import os
import glob
from scipy.io import loadmat
import numpy as np

# =============================================================================
# Currently dropping smt datasets from CAMCAN - also need to add rest datasets
# =============================================================================
tmp=MEGnet.__path__[0]
class_table_path = op.join(tmp, 'prep_inputs', 'training', 'ICA_combined_participants.tsv')
class_table = pd.read_csv(class_table_path, sep='\t')
if 'Unnamed: 0' in class_table.columns:
    class_table.drop('Unnamed: 0', axis=1, inplace=True)
if 'idx' in class_table.columns:
    class_table.drop('idx', axis=1, inplace=True)



dataset_path = op.join(MEGnet.__path__[0], 'prep_inputs','training','ICAs')
dsets = glob.glob(op.join(dataset_path, '*_meg'))
dsets += glob.glob(op.join(dataset_path, '*-sss'))
dsets += glob.glob(op.join(dataset_path, '*_wrkmem'))
dsets += glob.glob(op.join(dataset_path, '*_rest'))
datasets = pd.DataFrame(dsets, columns=['dirname'])

def get_subjid(dirname):
    tmp = op.basename(dirname)
    return tmp.split('_')[0]

def get_type(dirname):
    '''Extract the task type from the dataset name'''
    if 'task' in dirname:
        return [i[5:] for i in op.basename(dirname).split('_') if i[0:4]=='task'][0]
    else:
        return op.basename(dirname).split('_')[-1]
        
    

datasets['subjid'] = datasets.dirname.apply(get_subjid)
datasets['type'] = datasets.dirname.apply(get_type)

final = pd.merge(class_table, datasets, left_on=['participant_id', 'TaskType'], right_on=['subjid','type'])
dropidx=final.loc[(final.participant_id=='sub-ON12688') & (final.type_y =='rest')].index
final = final.drop(index=dropidx)
dropidx = final[final.TaskType=='artifact'].index
final = final.drop(index=dropidx)
final.reset_index(inplace=True, drop=True)

def get_inputs(dataset_info):
    '''
    Load the MNE created datasets for each line of the dataframe corresponding
    to a single MEG acquisition

    Parameters
    ----------
    subj_info : pandas.series
        A line from the fully merged dataframe.

    Returns
    -------
    ts_ : numpy.ndarray
        ICA timeseries - ICA# X Samples
    spat_resized : numpy.ndarray
        ICA Spatial topography map - cropped by bounding box. 
        Shape of (20, 120, 120, 3)  -- (ICA, X, Y, Color)

    '''
    data_dir = dataset_info['dirname']
    ts_fname = op.join(data_dir, 'ICATimeSeries.mat')
    ts_ = loadmat(ts_fname)['arrICATimeSeries'].T
    assert type(ts_) is np.ndarray
    
    spat_ = [] 
    for i in range(1,21): spat_.append(loadmat(op.join(data_dir, f'component{str(i)}.mat'))['array'])
    assert len(spat_)==20
    spat_ = np.stack(spat_)
    assert spat_.shape == (20,180, 150, 3)
    
    spat_resized = spat_[:,25:-35,16:-14,:]
    class_vec = make_classification_vector(dataset_info)
    
    return ts_ , spat_resized, class_vec

def get_default_hcp():
    '''Load and return the hcp ICA dataset'''
    data_dir = op.join(MEGnet.__path__[0], 'example_data/HCP/100307/@rawc_rfDC_8-StoryM_resample_notch_band/ICA202DDisc')
    ts_ = loadmat(op.join(data_dir, 'ICATimeSeries.mat'))['arrICATimeSeries'].T
    
    # lSpatial.append(loadmat(os.path.join(strDataPathSpatial,f'component{intComp}.mat'))['array'][30:-30,15:-14,:])
    spat_ = []
    for i in range(1,21): spat_.append(loadmat(op.join(data_dir, f'component{str(i)}.mat'))['array'][30:-30,15:-15,:])
    spat_ = np.stack(spat_)
    return ts_, spat_

def test_fPredict():
    arrTimeSeries, arrSpatialMap = get_default_hcp()
    output = fPredictChunkAndVoting(kModel, 
                                    arrTimeSeries, 
                                    arrSpatialMap, 
                                    np.zeros((20,3)), #the code expects the Y values as it was used for performance, just put in zeros as a place holder.
                                    intModelLen=15000, 
                                    intOverlap=3750)
    arrPredicionsVote, arrGTVote, arrPredictionsChunk, arrGTChunk = output
    correct_out = [2, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 2, 0, 0]
    actual_out = arrPredicionsVote[:,0,:].argmax(axis=1)
    assert_vals = [np.equal(i,j) for i,j in zip(correct_out, actual_out)]
    assert False not in assert_vals


def _convert_strlist2intlist(strlist):
    '''Hack to fix formatting'''
    tmp_ = strlist.replace('"','').replace('[','').replace(' ','').replace(']','').replace("'","").split(',')
    if (tmp_=='') | (tmp_==[]) | (tmp_==['']):
        return []
    return [int(i) for i in tmp_]
    

def make_classification_vector(input_vec):
    '''Convert the separate labelled columns into a 20X1 vector of labels'''
    output = np.zeros(20, dtype=int) #Number of ICAs
    VEOG =  _convert_strlist2intlist(input_vec.eyeblink)
    HEOG = _convert_strlist2intlist(input_vec.Saccade)
    EKG = _convert_strlist2intlist(input_vec.EKG)
    output[VEOG] = 1 
    output[HEOG] = 3
    output[EKG] = 2
    return output

def extract_all_datasets(dframe):
    '''
    Loop over all datasets
    Load the spatial, temporal, and classIDs into numpy matrcies

    Parameters
    ----------
    dframe : TYPE
        DESCRIPTION.

    Returns
    -------
    TYPE
        DESCRIPTION.

    '''
    TS_test, SP_test, class_vec = [], [], []
    for idx,input_vec in dframe.iterrows():
        print(idx)
        print(input_vec)
        TS_tmp, SP_tmp, CLid_tmp = get_inputs(input_vec)
        if TS_tmp.shape[1] < 62750:
            continue
        TS_test.append(TS_tmp[:,:15000]) #62750])
        SP_test.append(SP_tmp)
        class_vec.append(CLid_tmp) 
    return np.vstack(TS_test), np.vstack(SP_test), np.stack(class_vec).flatten()

import tensorflow.keras.backend as K
def get_f1(y_true, y_pred): #taken from old keras source code
    true_positives = K.sum(K.round(K.clip(y_true * y_pred, 0, 1)))
    possible_positives = K.sum(K.round(K.clip(y_true, 0, 1)))
    predicted_positives = K.sum(K.round(K.clip(y_pred, 0, 1)))
    precision = true_positives / (predicted_positives + K.epsilon())
    recall = true_positives / (possible_positives + K.epsilon())
    f1_val = 2*(precision*recall)/(precision+recall+K.epsilon())
    return f1_val


    
    
# =============================================================================
# 
# =============================================================================
train_dir = op.join(MEGnet.__path__[0], 'prep_inputs','training')
np_arr_topdir = op.join(train_dir, 'Inputs')
arrTS_fname = op.join(np_arr_topdir, 'arrTS.npy')
arrSP_fname = op.join(np_arr_topdir, 'arrSP.npy')
arrC_ID_fname = op.join(np_arr_topdir, 'arrC_ID.npy')



from tensorflow import keras
# import tensorflow_addons as tfa
model_fname = op.join(MEGnet.__path__[0], 'model/MEGnet_final_model.h5')
kModel = keras.models.load_model(model_fname, compile=False)

#Get all 
if not os.path.exists(np_arr_topdir):
    if not op.exists(op.join(train_dir, 'ICAs')):
                     raise BaseException('Need to run make_links.sh')
    os.mkdir(np_arr_topdir)
    arrTimeSeries, arrSpatialMap, class_ID = extract_all_datasets(final)
    np.save(arrTS_fname, arrTimeSeries)
    np.save(arrSP_fname, arrSpatialMap)
    np.save(arrC_ID_fname, class_ID)    
else:
    arrTimeSeries = np.load(arrTS_fname)
    arrSpatialMap = np.load(arrSP_fname)
    class_ID = np.load(arrC_ID_fname)
    
assert arrTimeSeries.shape[0] == arrSpatialMap.shape[0]
assert class_ID.shape[0] == arrTimeSeries.shape[0]
assert final.__len__() == int(arrTimeSeries.shape[0]/20)

# =============================================================================
# Cross Validation
# =============================================================================
crossval_cols = ['Site', 'TaskType', 'Scanner', 'age', 'sex']
from MEGnet.prep_inputs import cvSplits
final['idx']=final.index
cv = cvSplits.main(kfolds=5, foldNormFields=crossval_cols, data_dframe=final)

#Use the following function to match the CV to the ICAs
def make_ica_subj_encoding(arrTimeSeries):
    '''Expand the coding for each subject by 20 - to match the number of ICAs'''
    lenval = arrTimeSeries.shape[0]
    idxs = range(lenval)
    test = [[i]*20 for i in range(int(lenval/20))]
    test = np.hstack(test)
    assert len(test) == len(idxs)
    return np.array([idxs, test]).T

def get_cv_npyArr(sample,
                    arrTimeSeries, 
                    arrSpatialMap,
                    class_ID
                    ):
    '''
    Return the numpy array for the test / train slice
    

    Parameters
    ----------
    sample : array of ints
        Cross validation sample of the dataframe indexes.
    outcode : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    '''
    cv_tr = sample['train_indx']
    cv_te = sample['test_indx']
    
    #ICA number is in column 0 and subject index is column2
    ica_code = make_ica_subj_encoding(arrTimeSeries)
    
    #Probably slow - but will work
    tr_idx = [ica_code[ica_code[:,1]==i] for i in cv_tr]
    tr_idx = np.vstack(tr_idx)
    
    te_idx = [ica_code[ica_code[:,1]==i] for i in cv_te]
    te_idx = np.vstack(te_idx)
    
    #Subsample the cv
    tr_sub = ica_code[tr_idx[:,0],0]
    te_sub = ica_code[te_idx[:,0],0]
    train={'sp':arrSpatialMap[tr_sub,:,:,:],
               'ts':arrTimeSeries[tr_sub,:],
               'clID':class_ID[tr_sub]}
    test={'sp':arrSpatialMap[te_sub,:,:,:],
               'ts':arrTimeSeries[te_sub,:],
               'clID':class_ID[te_sub]}
    return train, test

#Randomize input vectors before doing val split          <<<<       # Fix this must be a higherarchical shuffle
# rand_idx = list(range(arrTimeSeries.shape[0]))  #!!! Fix
# import random
# random.shuffle(rand_idx)  #This happens in place
# arrTimeSeries=arrTimeSeries[rand_idx,:]
# arrSpatialMap=arrSpatialMap[rand_idx,:,:]
# class_ID=class_ID[rand_idx]

NB_EPOCH = 30 # 15
BATCH_SIZE = 500 #  Approximately 12 or so examples per category in each batch
VERBOSE = 1
# OPTIMIZER = Adam()  #switch to AdamW
VALIDATION_SPLIT = 0.20

get_f1_met = tfa.metrics.F1Score(num_classes=4)#, threshold=0.5)  #This seems to errror out when used

kModel.compile(
    loss=keras.losses.SparseCategoricalCrossentropy(), #CategoricalCrossentropy(), 
    optimizer='Adam',
    #batch_size=BATCH_SIZE,
    #epochs=NB_EPOCH,
    #verbose=VERBOSE,
    metrics=[get_f1,'accuracy']
    )

class_weights={0:1, 1:10, 2:10, 3:10}

history=[]
for sample in cv:
    tr, te = get_cv_npyArr(sample,
                        arrTimeSeries, 
                        arrSpatialMap,
                        class_ID
                        )
                       
    history_tmp = kModel.fit(x=dict(spatial_input=arrSpatialMap, temporal_input=arrTimeSeries), y=class_ID,
                         batch_size=BATCH_SIZE, epochs=NB_EPOCH, verbose=VERBOSE, validation_split=VALIDATION_SPLIT,
                         class_weight=class_weights)
    history.append(history_tmp)




score = kModel.evaluate(x=dict(spatial_input=arrSpatialMap, temporal_input=arrTimeSeries), y=class_ID)
    
    
from matplotlib import pyplot as plt    
plt.plot(history.history['accuracy'])    
plt.plot(history.history['val_accuracy'])
plt.plot(history.history['get_f1'])

import pickle
def save_weights_and_history(history):
    with open('./trainHistoryDict', 'wb') as file_pi:
        pickle.dump(history.history, file_pi)

save_weights_and_history(history)
kModel.save('Model.hd5')
# =============================================================================
# 
# =============================================================================

#class_ID = class_ID.flatten()  #Make a 1D vector
#tmp = class_ID.flatten()

# #use the vote chunk prediction function to make a prediction on each input
# from MEGnet.label_ICA_components import fPredictChunkAndVoting
# output = fPredictChunkAndVoting(kModel, 
#                                 arrTimeSeries, 
#                                 arrSpatialMap, 
#                                 np.zeros((20,3)), #the code expects the Y values as it was used for performance, just put in zeros as a place holder.
#                                 intModelLen=15000, 
#                                 intOverlap=3750)
# arrPredicionsVote, arrGTVote, arrPredictionsChunk, arrGTChunk = output



# x, y = final.apply(get_inputs)


# arrTimeSeries, arrSpatialMap = get_inputs(final.loc[0])
