from time import asctime
from osgeo import gdal
#from pyroSAR.spatial import raster 
from spatialist import raster
import numpy as np
from osgeo.gdalconst import *
from astropy.convolution import convolve, Box2DKernel
import argparse
#import pyeemd
import logging
#from pyroSAR.envi import HDRobject 
from spatialist.envi import HDRobject
import datetime
import re
import os.path

#@profile
def quegan(infile, outfile, kernel, is_list=False,
                       nodata=0.0, max_memory=10000,dB=False):
    '''______________________________________________________________________________________________________________
    #|
    #|	NAME:
    #|	     quegan_multitemp_filter
    #|
    #|	PURPOSE:
    #|	     To apply a filter to a multitemporal set of coregistered SAR images to produce output images that are:
    #|              - individually unbiased
    #|              - have minimum variance (so minimum speckle)
    #|              - all have the same equivalent number of looks (ENL)
    #|              - have essentially the same resolution as the original data
    #|  DATE:
    #|	     23 October 2015 (Joao Carreiras, NCEO/U.Sheffield, UK# j.carreiras@sheffield.ac.uk)
    #|
    #|  Modified:
    #|		 28 October 2015 (Felix Cremer & Marcel Urban, FSU Jena)
    #|
    #|_____________________________________________________________________________________________________________
    '''
    logging.basicConfig(format='%(asctime)s /t %(levelname)s:%(message)s', level=logging.WARNING)
    #print "##########################################"
    #print "Start:", asctime()

    if not is_list:
        data = raster.Raster(infile)
        band_count = data.bands
    else:
       band_count = len(infile)
       data=raster.Raster(infile[0])



    # Import Layerstack

    logging.info('RASTER BAND COUNT:  %s', band_count)
    logging.info('Cols, Rows: %s, %s', data.cols, data.rows)
    mean_image = [[]for i in range(band_count)]
    #print mean_image
    ratio=[[]for i in range(band_count)]
    output=[[]for i in range(band_count)]
    src=[[]for i in range(band_count)]
    maxlines = max_memory//(data.cols*band_count*5*4/1048576.)
    logging.debug('Number of loops %s', int(round(data.rows/(maxlines-kernel+1)+0.5)))
    box = Box2DKernel(kernel)
    logging.debug('Kernelsize: %s',kernel)
    driver = gdal.GetDriverByName("ENVI")
    out = driver.Create(outfile, data.cols, data.rows, data.bands, GDT_Float32)
    for i in range(int(round(data.rows/(maxlines-kernel+1)+0.5))):
    # Loop through Bands and rows
        logging.debug('This is loop number %s', i)
        for band in range( band_count ):
            band += 1
            logging.debug('This is band number %s', band)
            if is_list:
                data = raster.Raster(infile[band])
                if data.nodata:
                    nodata = data.nodata
                

            indices = list(map(int, [(maxlines - kernel + 1) * i, (maxlines - kernel + 1) * i + maxlines]))
            #print(type(data.matrix(band)), indices, type(indices))
            srcband = np.split(data.matrix(band), indices, axis=0)[1]
            srcband[srcband== nodata] = np.nan
            if dB:
                #print 'dB'
                srcband = 10**(srcband/10)
            src[band-1] = srcband
            #print srcband.shape
            #print 'Test'
            #mean_image[band-1] = np.zeros(srcband)
            #print 'Test'
            #1st STEP: apply a mean filter (in this case 7x7) to each separate image to estimate local mean
            # (mean_image(*, *, k) = mean_filter(input(*, *, k), 7, 7, /arithmetic, invalid = 0.0))

            # todo: Change convolve function to generic filter
            mean_image[band-1] = convolve(srcband, box)
            mean_image[band-1][np.isnan(srcband)] = np.nan
            #print 'SRC', srcband
            #print 'Mean', mean_image[band-1]

            #2nd STEP: divide the original band by the filtered band
            # (ratio(*, *, k) = input(*, *, k)/mean_image(*, *, k))
            #print mean_image[band-1]
            #print 'Ratio'
            ratio[band-1] = srcband/mean_image[band-1]
            #print ratio[band-1]
            #print ratio[band-1]

        	
        #3rd step: calculate the average image from the ratio images
        #(mean_ratio(*, *) = mean(ratio(*, *, *), dimension = 3))    
        #print 'Done'
        mean_ratio = np.nanmean(ratio, axis=0)
        #print mean_ratio.shape
        #4th/final STEP works also on a band-by-band basis
        # for l = 0, (num_layers-1) do begin
            # output(*, *, l) = mean_image(*, *, l) * mean_ratio(*, *)
        # endfor
        logging.info('Begin of Output')
        for band in range(band_count):
            band += 1
            logging.debug('This is band number %s', band)
            output[band-1] = mean_image[band-1]*mean_ratio

            if i !=0:
                output[band-1] = np.delete(output[band-1], range((kernel-1) // 2), axis=0)
        #print 'Output:'
        #print output[1].shape

        for band in range(band_count):
            band+=1
           # print band
            #print i
            yoffset = int((maxlines-(kernel-1))*i+(kernel-1)/2)
            if i == 0:
                yoffset = 0
            maskout = out.GetRasterBand(band)
            maskout.WriteArray(output[band-1], 0, yoffset)
            maskout.FlushCache()
        output=[[]for i in range(band_count)]
    out.SetGeoTransform(data.raster.GetGeoTransform())
    out.SetProjection(data.raster.GetProjection())
        
    out = None
    
    #print "End:", asctime()
    #print "##########################################"
    
def quegan_cube(infile, outfile, kernel, time_kernel, is_list=False,
                       nodata=0.0, max_memory=10000):
    #print "##########################################"
    #print "Start:", asctime()

    if not is_list:
        data = raster.Raster(infile)
        band_count = data.bands
    else:
       band_count = len(infile)
       data=raster.Raster(infile[0])



    # Import Layerstack

    #print "RASTER BAND COUNT: ", band_count
    #print "Cols, Rows:"
    #print data.cols, data.rows
    mean_image = [[]for i in range(band_count)]
    ratio=[[]for i in range(band_count)]
    output=[[]for i in range(band_count)]
    maxlines = max_memory//(data.cols*band_count*3*4/1048576.)
    #print 'Anzahl Streifen:', int(round(data.rows/(maxlines-kernel+1)+0.5))
    box = Box2DKernel(kernel)
    driver = gdal.GetDriverByName("ENVI")
    out = driver.Create(outfile, data.cols, data.rows, data.bands, GDT_Float32)
    for i in range(int(round(data.rows/(maxlines-kernel+1)+0.5))):
    # Loop through Bands and rows
        #print 'Streifennummer: '
        #print i
        #print asctime()

        for band in range( band_count ):
            band += 1
            #print band
            if is_list:
                data = raster.Raster(infile[band])
                if data.nodata:
                    nodata = data.nodata
                
            #print 'BandNummer:'
            #print band
            #print asctime()
            srcband = np.split(data.matrix(band), [(maxlines-kernel+1)*i, (maxlines-kernel+1)*i+maxlines], axis=0)[1]
            srcband[srcband==nodata] = np.nan
            #print "Source", srcband
            #print srcband.shape
            #print 'Test'
            #mean_image[band-1] = np.zeros(srcband)
            #print 'Test'
            #1st STEP: apply a mean filter (in this case 7x7) to each separate image to estimate local mean
            # (mean_image(*, *, k) = mean_filter(input(*, *, k), 7, 7, /arithmetic, invalid = 0.0))

            # apply mean filter with the kernel size to the band
            mean_image[band-1] = convolve(srcband, box)
            mean_image[band-1][np.isnan(srcband)] = np.nan
            #print "mean_image", mean_image[band-1]
            #print mean_image[band-1]

            #2nd STEP: divide the original band by the filtered band
            ratio[band-1] = srcband/mean_image[band-1]
            #print "Ratio",ratio[band-1]
        	
        #3rd step: calculate the average image from the ratio images
        #(mean_ratio(*, *) = mean(ratio(*, *, *), dimension = 3))    
        #print 'Done'
        #mean_ratio = np.nanmean(ratio, axis=0)
        #print mean_ratio.shape
        #4th/final STEP works also on a band-by-band basis
        # for l = 0, (num_layers-1) do begin
            # output(*, *, l) = mean_image(*, *, l) * mean_ratio(*, *)
        # endfor
        #print 'Output'
        for band in range(band_count):
            #print band
            mean_ratio = ratio[band]
            #print mean_ratio
            num=1
            for time in range(1,(time_kernel-1)/2):
                if band+time in range(band_count):
                    mean_ratio+= np.nan_to_num(ratio[band+time])
                    num += 1
                if band-time in range(band_count):
                    mean_ratio+=np.nan_to_num(ratio[band-time])
                    num += 1
            #print mean_ratio
            #print "Num", num
            mean_ratio /= num

            #print 'BandNummer:'
            #print band
            #print asctime()
            #print mean_ratio
            output[band-1] = mean_image[band-1]*mean_ratio
            #print "Out:", output[band-1]

            if i !=0:
                output[band-1] = np.delete(output[band-1], range((kernel-1)/2), axis=0)
        #print 'Output:'
        #print output[1].shape
        
        
        

        for band in range(band_count):
            band+=1
           # print band
            #print i
            yoffset = int((maxlines-(kernel-1))*i+(kernel-1)/2)
            if i == 0:
                yoffset = 0
            maskout = out.GetRasterBand(band)
            maskout.WriteArray(output[band-1], 0, yoffset)
            maskout.FlushCache()
        output=[[]for i in range(band_count)]
    out.SetGeoTransform(data.raster.GetGeoTransform())
    out.SetProjection(data.raster.GetProjection())
        
    out = None
    
    #print "End:", asctime()
    #print "##########################################"

def emd_filter(infile, outfile, headerpath=None, nodata=0.0,log=True):
    #print "##########################################"
    #print "Start:", asctime()
    #print infile
    if not headerpath:
        headerpath=infile+'.hdr'

    if type(infile) is not list:
        data = raster.Raster(infile)
        band_count = data.bands
        data_arr = data.raster.ReadAsArray()
    else:
        raster_data = []
        data = raster.Raster(infile[0])
        for input in infile:
            raster_data.append(raster.Raster(input).raster.ReadAsArray())

        data_arr = np.concatenate(raster_data)
        raster_data = None
        band_count = data_arr.shape[0]
    #print data_arr.shape
    #print outfile
    header = HDRobject(headerpath)
    band_names = header.band_names
    #days = [datetime.datetime.strptime(re.search('[0-9]{8}', band).group(), '%Y%m%d') for band in band_names]

    data_arr[data_arr==nodata] = np.nan
    if log:
        data_arr = np.log(data_arr)


    output = np.zeros_like(data_arr)
    for row in xrange(data.rows):
        #print row, asctime()
        for col in xrange(data.cols):
            #print "Row and column:", row, col
            timeseries = data_arr[:, row, col]

            timeseries_masked = timeseries[np.logical_not(np.isnan(timeseries))]

            imf = pyeemd.ceemdan(timeseries_masked, num_imfs=3)[-1]
            #print len(imfs)
            '''
            try:
                imfs = deco.decompose()
            except ValueError:
                imfs = [np.zeros_like(timeseries_masked)]
                non_filtered+=1
            except TypeError:
                imfs=[np.zeros_like(timeseries_masked)]
                non_filtered+=1
            '''
            num_nan =0

            for i,time_point in enumerate(timeseries):
                if np.isnan(time_point):
                    num_nan +=1
                    output[i,row,col] = np.nan
                else:
                    output[i,row,col] += imf[i-num_nan]

            #print 'input', row,col,timeseries, timeseries.shape
            #print 'Output', row, col, output[:,row,col], output[:,row,col].shape
            #hhtvis.plot_imfs(timeseries_masked, np.asarray(range(len(timeseries_masked))), imfs)
    #return hht.EMD(timeseries).decompose()
    #print output
    if log:
        output = np.exp(output)

    driver = gdal.GetDriverByName("ENVI")
    out = driver.Create(outfile, data.cols, data.rows, band_count, GDT_Float32)

    for band in range(band_count):
        band += 1
        # print band
        # print i
        maskout = out.GetRasterBand(band)
        maskout.WriteArray(output[band - 1, :, :], 0)
        maskout.FlushCache()
    out.SetGeoTransform(data.raster.GetGeoTransform())
    out.SetProjection(data.raster.GetProjection())
    out = None
    head = HDRobject(outfile + '.hdr')
    #head.band_names = map(str, days)
    head.write()

    #print "End:", asctime()
    #print "##########################################"
    return None



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='The input file.')
    parser.add_argument('--kernel', '-k', default=3, help='The size of the moving window')
    parser.add_argument('--memory', '-m', default=10240, help='The size of the maximal ram')
    parser.add_argument('--nodata', '-n', default=0, help='The no data value')
    parser.add_argument('--islist', '-l',default=False, help='Is it a list?')
    parser.add_argument('--time', '-t', default=None, help='The number of scenes that should be averaged in the time axis. If it is not specified, all time steps are averaged.')
    parser.add_argument('--dB','-d', default=False,help='Is the data in dB?')
    parser.add_argument('--emd','-e',action='store_true', help='Use the EMD filter')
    parser.add_argument('--log',action='store_true', help='Use the EMD filterlogarithmically.')
    parser.add_argument('--verbose','-v',help='logging level')
    args = vars(parser.parse_args())
    
    infile = args['input']
    kernel = int(args['kernel'])

    #print infile
    outfile = os.path.splitext(infile)[0]
    #print outfile
    if args['time']:
        outfile = '_'.join([outfile, 'mtf', str(kernel)])
        outfile = '_'.join([outfile, 't', args['time']])
        quegan_cube(infile, outfile, kernel, int(args['time']), False, args['nodata'], args['memory'])
    elif args['emd']:
        log = 'log' if args['log'] else ''
        outfile = '_'.join([outfile,'emd',log])
        emd_filter(infile, outfile, nodata=args['nodata'],log = args['log'])
    else:
        outfile = '_'.join([outfile, 'mtf', str(kernel)])
        quegan(infile,outfile, kernel)
