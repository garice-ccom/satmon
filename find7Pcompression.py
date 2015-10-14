"""find7Pcompression
Glen Rice 3/10/11
V0.2.5 20140625

This processes the output of the power / gain cycling experiment used in the
UNH thesis by Sam Greenaway and provides a table of the 1dB compression points
as well as the offsets between different gain curves.
"""

import pylab as pl
import time, sys
import wx

#junk for the lasso stuff
from matplotlib.widgets import Lasso
import matplotlib.mlab
#from matplotlib.nxutils import points_inside_poly
from matplotlib.path import Path as mpl_path
from matplotlib.colors import colorConverter
from matplotlib.collections import RegularPolyCollection
from matplotlib.collections import LineCollection

import copy

import prr

class fsp:
    def __init__(self, infilename = 'calfile.s7k'):
        self.calfile = prr.x7kRead(infilename)
        self.calfile.mapfile()
        self.settings = {}
        self.settings['power'] = []
        self.settings['gain'] = []
        
        self.num7006 = len(self.calfile.map.packdir['7006'])
        self.calfile.getrecord(7006,0)
        self.numbeams = self.calfile.packet.subpack.header[3]
        
        self.calfile.getrecord(7000,0)
        self.pulselen = self.calfile.packet.subpack.header[6]
        self.samplerate = self.calfile.packet.subpack.header[4]
        self.frequency = self.calfile.packet.subpack.header[3]
        self.windowlen = 2 * self.pulselen
        
        if self.calfile.map.packdir.has_key('7008'):
            self.bstype = 7008
            self.calfile.getrecord(7008, 0)
            num7008beams = self.calfile.packet.subpack.numbeams
            if self.numbeams != num7008beams:
                print "WARNING! The number of beams in the depth record do not equal",
                print "the number of beams in the snippet record. 7006: " + str(self.numbeams),
                print " beams, 7008: " + str(num7008beams) + " beams."
        elif self.calfile.map.packdir.has_key('7028'):
            self.bstype = 7028
        else:
            print "No usable backscatter record found!"
            self.bstype = None
        
    def finddepth(self, showdepth = False):
        """find all the 7006 ranges that have both good colinearity and
        brightness, and bin them and use the bin with the maximum number as
        the depth for that beam."""
        print "Extracting depth information...",
        depth = pl.zeros((self.num7006, self.numbeams))
        depth[:,:] = pl.nan
        flagmask = pl.zeros(self.numbeams, dtype=int)
        flagmask[:] = 3
        for i in xrange(self.num7006):
            self.calfile.getrecord(7006, i)
            pingflags = pl.asarray(self.calfile.packet.subpack.data[1, :], dtype=int)
            indx = pl.find((flagmask & pingflags) == 3)
            depth[i, indx] = self.calfile.packet.subpack.data[0,indx]    
        print "estimating the depth...",
        depthmax = pl.nanmax(depth)
        self.depthbins = pl.arange(0, depthmax + self.windowlen, self.windowlen)
        self.depthestimate = pl.zeros(self.numbeams)
        for j in xrange(self.numbeams):
            h = pl.histogram(depth[:, j], bins = self.depthbins)
            self.depthestimate[j] = h[1][h[0].argmax()]
        print "depth estimation completed, binning beams."
        # sort beams with similar ranges into a list
        self.beamlisting = []
        for bin in self.depthbins:
            indx = pl.find((self.depthestimate < bin + self.windowlen) 
                & (self.depthestimate >= bin - self.windowlen))
            if len(indx > 0):
                self.beamlisting.append(indx)
        if showdepth:
            fig = pl.figure()
            ax = fig.add_subplot(111)
            ax.plot(depth.T, 'x')
            ax.plot(self.depthestimate,'o')
            ax.set_xlabel('Beam Number')
            ax.set_ylabel('Time (seconds)')
            ax.set_title('Bottom Detections')
            pl.xlim((0,self.numbeams))
            ymin, ymax = pl.ylim()
            pl.ylim((ymax, ymin))
            ax.grid()
            pl.draw()
        
    def extract (self, graph = False):
        """
        Added to act as a switchboard for the backscatter record type for
        minimal changes from the earlier code to maintain compatibility with
        the ROV1/SV1 Reson 7125s.
        """
        if self.bstype == 7008:
            self.extract7008(graph)
        elif self.bstype == 7028:
            self.extract7028(graph)
        
    def extract7008(self,  graph = False):
        """extract the data from a s7k file written by the sevenpy script.
        Returns a ping list for amplitude, power and gain settings, and 
        beam sections."""
        
        num7008 = len(self.calfile.map.packdir['7008'])
        r7000 = pl.array(self.calfile.map.packdir['7000'])
        self.pingdata = pl.zeros((num7008,3,len(self.beamlisting)))
        print 'Processing ' + str(num7008) + ' pings, at           ',

        if graph:
            pl.hold(False)
        for i in xrange(num7008):
            #get 7008 max amplitude
            self.calfile.getrecord('7008',i)
            amp = self.calfile.packet.subpack.mag
            # get the start and end samples for each beam
            pingdepth = self.calfile.packet.subpack.beams[:, 1:] / self.samplerate
            # get the range of snippets that are in the depth window
            depthmask = ((self.depthestimate < pingdepth[:, 1]) & (self.depthestimate > pingdepth[:, 0]))
            # filter the snippets according to the mask
            amp *= depthmask
            ts7008 = self.calfile.packet.gettime()
            if graph:
                self.calfile.packet.subpack.plot()
                pl.draw()
            
            #get settings from corisponding 7000 packet
            indx7000 = pl.find(ts7008 == r7000[:,1])
            if len(indx7000) == 0:
                num7008 -= 1
            elif len(indx7000) > 1:
                print 'more than one 7000 record with matching time stamp!'
            else:
                self.calfile.getrecord('7000', indx7000[0])
                power = self.calfile.packet.subpack.header[14]
                gain = self.calfile.packet.subpack.header[15]         
                if power not in self.settings['power'] and power != 0:
                    self.settings['power'].append(power)
                if gain not in self.settings['gain'] and gain !=0:
                    self.settings['gain'].append(gain)
                for k, indx in enumerate(self.beamlisting):
                    self.pingdata[i, :, k] = amp[:, indx].max(), power, gain
            if i % 10 == 0:
                sys.stdout.write('\b\b\b\b\b\b\b\b\b\b%(percent)02d percent' %{'percent':100 * i / num7008})
        self.calfile.close()
        print '\n' + str(num7008) + 'records used.'
        self.settings['power'].sort()
        self.settings['gain'].sort()
        self.pingdata = self.pingdata[:num7008]        
        
    def extract7028(self,  graph = False):
        """
        Extract 7028 data from a s7k file written by the sevenpy script.
        Returns a ping list for amplitude, power and gain settings, and 
        beam sections.
        """
        
        num7028 = len(self.calfile.map.packdir['7028'])
        r7000 = pl.array(self.calfile.map.packdir['7000'])
        self.pingdata = pl.zeros((num7028,3,len(self.beamlisting)))
        print 'Processing ' + str(num7028) + ' pings, at           ',

        if graph:
            pl.hold(False)
        j = 0
        for i in xrange(num7028):
            #get 7028 max amplitude
            self.calfile.getrecord('7028',i)
            if self.calfile.packet.subpack.snippets is not None:
                snip = self.calfile.packet.subpack.snippets.T
                maxbeam = self.calfile.packet.subpack.maxbeam
                n,m = snip.shape
                amp = pl.zeros((n,self.numbeams))
                amp[:,:] = pl.nan
                amp[:,:maxbeam] = snip
                # get the start and end samples for each beam
                desc = self.calfile.packet.subpack.descriptor.astype(pl.np.int)
                pingdepth = pl.zeros((self.numbeams,2))
                pingdepth[desc[:,0],:] = desc[:,[1,3]]/ self.samplerate
                # get the range of snippets that are in the depth window
                depthmask = ((self.depthestimate < pingdepth[:, 1]) & (self.depthestimate > pingdepth[:, 0]))
                # filter the snippets according to the mask
                amp *= depthmask
                ts7028 = self.calfile.packet.gettime()
                if graph:
                    self.calfile.packet.subpack.plot()
                    pl.draw()
                
                #get settings from corisponding 7000 packet
                indx7000 = pl.find(ts7028 == r7000[:,1])
                if len(indx7000) == 0:
                    num7028 -= 1
                elif len(indx7000) > 1:
                    print 'more than one 7000 record with matching time stamp!'
                else:
                    self.calfile.getrecord('7000', indx7000[0])
                    power = self.calfile.packet.subpack.header[14]
                    gain = self.calfile.packet.subpack.header[15]         
                    if power not in self.settings['power'] and power != 0:
                        self.settings['power'].append(power)
                    if gain not in self.settings['gain'] and gain !=0:
                        self.settings['gain'].append(gain)
                    for k, indx in enumerate(self.beamlisting):
                        self.pingdata[j, :, k] = pl.nanmax(amp[:, indx]), power, gain
                j += 1
            if i % 10 == 0:
                sys.stdout.write('\b\b\b\b\b\b\b\b\b\b%(percent)02d percent' %{'percent':100 * i / num7028})
        self.calfile.close()
        print '\n' + str(num7028) + 'records used.'
        self.settings['power'].sort()
        self.settings['gain'].sort()
        self.pingdata = self.pingdata[:num7028]
        
    def process(self):
        """rearranges the ping data into a matrix of max amplitude of
        dimensions corrisponding to the power, gain and beam sections."""
        MINSAMPLES = 5
        datadim = self.pingdata.shape
        self.pingmax = pl.zeros((len(self.settings['power']), len(self.settings['gain']), datadim[2]))

        for i, power in enumerate(self.settings['power']):
            for j, gain in enumerate(self.settings['gain']):
                for k in xrange(datadim[2]):
                    sampleindx = pl.find((self.pingdata[:, 1, k]  == power) & (self.pingdata[:, 2, k] == gain))
                    if len(sampleindx)  >  MINSAMPLES:
                        temp = self.pingdata[sampleindx[-MINSAMPLES:], 0, k]
                        tempmax = temp.max()
                        if tempmax == 0:
                            self.pingmax[i, j, k] = pl.NaN
                        else:
                            self.pingmax[i, j, k] = temp.max()
                    else:
                        self.pingmax[i, j, k] = pl.NaN

        #The following section removes settings that were collected erroniously.
        #gain settings first
        null = pl.zeros((len(self.settings['gain']), datadim[2]))
        powershortlist = []
        self.havedata = True  # this is an ugly workaround...
        for i, power in enumerate(self.settings['power']):
            test = pl.isnan(self.pingmax[i, :, :] )
            if test.all():
                powershortlist.append(i)
                print 'removing ' + str(power) + ' power setting.'
        for i in powershortlist:
            try:
                self.settings['power'].pop(i)
            except IndexError:
                self.havedata = False
        if self.havedata:
            self.pingmax = pl.delete(self.pingmax, powershortlist, 0)
            #then power settings
            null = pl.zeros((len(self.settings['power']), datadim[2]))
            gainshortlist = []
            for i, gain in enumerate(self.settings['gain']):
                test = pl.isnan(self.pingmax[:, i, :])
                if test.all():
                    gainshortlist.append(i)
                    print 'removing ' + str(gain) + ' gain setting.'
            for i in gainshortlist:
                try:
                    self.settings['gain'].pop(i)
                except IndexError:
                    self.havedata = False
            if self.havedata:
                self.pingmax = pl.delete(self.pingmax, gainshortlist, 1)
                #remove the power and gain to normalize
                self.pingmax = 20*pl.log10(self.pingmax)
                for i, power in enumerate(self.settings['power']):
                    for j, gain in enumerate(self.settings['gain']):
                        self.pingmax[i, j, :] = self.pingmax[i, j, :] - power - gain

    def plot(self):
        self.i = 0
        self.j = 0
        self.lms = []
        self.skipinc = 4
        self.numsections = self.pingmax.shape[2]
        if self.numsections > 60:
            self.numsections = 60
        for section in range(0, self.numsections, self.skipinc):
            minpower = pl.asarray(self.settings['power']).min()
            maxpower = pl.asarray(self.settings['power']).max()
            mags = self.pingmax[:,:,section]
            maskedmags = pl.ma.array(mags, mask = pl.isnan(mags))
            maxintensity = maskedmags.max()
            minintensity = maskedmags.min()
            self.fig = pl.figure()
            self.ax = self.fig.add_subplot(111, xlim=(minpower - 10,maxpower + 10), ylim=(minintensity - 10,maxintensity + 10), autoscale_on=False)
            self.ax.set_xlabel('Reported Power (dB)')
            self.ax.set_ylabel('Corrected 20*log10(recieved magnitude)')
            title = 'Range bin ' + str(section)
            self.ax.set_title(title)
            self.ax.grid()
            self.lms.append(LassoManager(self.ax, self.settings['power'], maskedmags))
            pl.draw()
            
            
    def extractfitpoints(self):
        """find the system output as a function of gain."""
        self.estpoints = pl.zeros((len(self.settings['gain']),2))
        self.estpoints[:,0] = self.settings['gain']
        self.estpoints[:,1] = pl.nan
        power = self.settings['power']
        powermaxidx = len(power)
        gain = self.settings['gain']
        self.fig = pl.figure()
        self.ax = self.fig.add_subplot(111)
        pl.hold(True)
        sectionlist = []
        for lmscount, section in enumerate(range(0, self.numsections, self.skipinc)):
            if len(self.lms[lmscount].badpoints) > 0:
                magarray = self.pingmax[:, :, section]
                gainlist = []
                maglist = []
                sectionlist.append(str(section))
                for gainindx in range(len(gain)):
                    indx = pl.find(pl.invert(pl.isnan(self.pingmax[:, gainindx, section])))
                    if len(indx) > 0:
                        powerindx = indx[-1]
                        #remove values that are either at the minimum or maximum powersetting
                        if powerindx != 0 and powerindx != powermaxidx:
                            # and the actual power for the min setting
                            thispower = power[powerindx]
                            thisgain = gain[gainindx]
                            # get back to the original reported magnitude by removing the
                            # gain and power that was applied previously
                            unadjusted_mag = self.pingmax[powerindx, gainindx, section] + thisgain + thispower
                            if pl.isnan(self.estpoints[gainindx,1]):
                                self.estpoints[gainindx,1] = unadjusted_mag
                            elif unadjusted_mag < self.estpoints[gainindx,1]:
                                self.estpoints[gainindx,1] = unadjusted_mag
                            maglist.append(unadjusted_mag)
                            gainlist.append(thisgain)
                self.ax.plot(gainlist, maglist,'.')
        # get the index of all points that have no estimate
        ind = pl.find(pl.isnan(self.estpoints[:,1]))
        temp = pl.arange(len(ind))
        # adapt the index array for removing earlier points
        ind = ind - temp
        temp = self.estpoints.tolist()
        # remove those points
        for i in ind:
            temp.pop(i)
        # add a regression to get the 0 and 83 gain values
        if temp[0][0] != 0:
            temp2 = pl.array(temp)
            a, b = pl.polyfit(temp2[:3,0], temp2[:3,1], 1)
            temp.insert(0,[0,b])
        if temp[-1][0] < 83:
            temp2 = pl.array(temp)
            temp.append([83,temp2[:,1].max()])
        self.estpoints = pl.ma.array(temp, mask = pl.isnan(temp))
        #self.ax.plot(self.estpoints[:,0],self.estpoints[:,1])
        self.ax.set_xlabel('Reson Applied Gain (dB)')
        self.ax.set_ylabel('System Measurement (dB)')
        self.ax.set_title('All Extracted Points')
        self.ax.legend(sectionlist, loc = 'lower right')
        self.ax.grid()
        self.extractedlm = LassoManager(self.ax, self.estpoints[:,0], self.estpoints[:,1])

        
    def clean_estpoints(self):
        """Removes NaN from the estpoints that result from cleaning by the user
        in the extractfitpoints method."""
        temp = self.estpoints.tolist()
        indx = 0
        while indx < len(temp):
            if pl.isnan(temp[indx][1]):
                temp.pop(indx)
            else:
                indx+=1
        self.estpoints = pl.array(temp)
        
        
    def regress(self):
        """regresses to find the gain vs system saturation curve"""
        a, b = pl.polyfit(self.estpoints[:,0], self.estpoints[:,1], 1)
        x = pl.arange(0, 90)
        y = b + a * x
        print 'Intercept: ' + str(b)
        print 'Slope: ' + str(a)
        pl.figure()
        pl.plot(x, y, 'g')
        pl.plot(self.estpoints[:,0], self.estpoints[:,1],'ro')
        pl.xlabel('Reson Applied Gain (dB)')
        pl.ylabel('System Measurement (dB)')
        pl.title('Saturation Fit with selected points')
        
    def seriesplot(self, rangebin):
        fig = pl.figure()
        ax1 = fig.add_subplot(411)
        ax1.plot(self.pingdata[:, 1, rangebin])
        pl.ylabel('Reported Power')
        ax2 = fig.add_subplot(412, sharex = ax1)
        ax2.plot(self.pingdata[:, 2, rangebin])
        pl.ylabel('Reported Gain')
        ax3 = fig.add_subplot(413, sharex = ax1)
        logmag = 20 * pl.log10(self.pingdata[:, 0, rangebin])
        ax3.plot(logmag)
        pl.ylabel('Measured 20log(Mag)')
        ax4 = fig.add_subplot(414, sharex = ax1)
        corlogmag = logmag - self.pingdata[:, 1, rangebin] - self.pingdata[:, 2, rangebin]
        ax4.plot(corlogmag)
        pl.ylabel('Corrected 20log(Mag)')
        pl.xlabel('Sample Number')
        
        
    def copy(self, fsp_instance):
        self.settings = copy.deepcopy(fsp_instance.settings)
        self.pingdata = copy.deepcopy(fsp_instance.pingdata)
        self.skipinc = copy.deepcopy(fsp_instance.skipinc)
        self.numsections = copy.deepcopy(fsp_instance.numsections)
        if "pingmax" in fsp_instance.__dict__:
            print "copying pingmax too..."
            self.pingmax = copy.deepcopy(fsp_instance.pingmax)
        
        
    def dothis(self):
        pl.ion()
        if self.bstype is not None:
            start = time.time()
            self.finddepth()
            self.extract()
            self.process()
            self.plot()
            stop = time.time()
            print 'Elapsed time: ' + str(stop - start) + ' seconds.'
        else:
            "No useful backscatter record found."
        
        
    def dothat(self):
        self.extractfitpoints()
        self.clean_estpoints()
        pl.np.save('satcurve',self.estpoints)

        
class LassoManager:
    def __init__(self, ax, x, y):
        self.axes = ax
        self.canvas = ax.figure.canvas
        self.y = y.T
        self.x = x

        self.Nxy = self.y.shape
        self.badpoints = []

        fig = ax.figure
        if len(self.Nxy) > 1:
            pl.plot(x, y)
            for series in self.y:
                self.collection = RegularPolyCollection(
                    fig.dpi, 6, sizes=(100,),
                    offsets = zip(x, series),
                    transOffset = ax.transData)
                ax.add_collection(self.collection)
        else:
            temp = []
            temp.append(zip(x, self.y))
            curve = LineCollection(temp)
            ax.add_collection(curve)

        self.cid = self.canvas.mpl_connect('button_press_event', self.onpress)

        
    def callback(self, verts):
        if len(self.Nxy) > 1:
            for j, series in enumerate(self.y):
                # ind = pl.np.nonzero(points_inside_poly(zip(self.x, series), verts))[0]
                ind = pl.np.nonzero(mpl_path(verts).contains_points(zip(self.x, series)))[0]
                for i in range(self.Nxy[1]):
                    if i in ind:
                        self.badpoints.append([i, j, self.y[j, i]])
                        self.axes.collections[j]._offsets[i,1] = pl.nan
                        self.y[j,i] = pl.nan
        else:
            cleanedpoints = self.axes.collections[0]._paths[0].vertices.tolist()
            # ind = pl.np.nonzero(points_inside_poly(cleanedpoints, verts))[0]
            ind = pl.np.nonzero(mpl_path(verts).contains_points(cleanedpoints))[0]
            removedcount = 0
            for i in range(len(cleanedpoints)):
                if i in ind:
                    self.badpoints.append([i, self.x[i], self.y[i]])
                    out = cleanedpoints.pop(i - removedcount)
                    self.axes.collections[0]._paths[0].vertices = pl.asarray(cleanedpoints)
                    original_indx = pl.find(self.x == out[0])
                    self.y[original_indx] = pl.nan
                    removedcount += 1
        self.canvas.draw_idle()
        self.canvas.widgetlock.release(self.lasso)
        del self.lasso
        
        
    def onpress(self, event):
        if self.canvas.widgetlock.locked(): return
        if event.inaxes is None: return
        self.lasso = Lasso(event.inaxes, (event.xdata, event.ydata), self.callback)
        # acquire a lock on the widget drawing
        self.canvas.widgetlock(self.lasso)
        