"""
satmon.py
G.Rice 11/23/2011
V 0.2.7 20140625
A real time display of the estimated saturation state of a Reson 7k system.
The saturation values are provided by a field test designed by a UNH thesis by
S. Greenaway in 2011.  Provided saturation information and a connection to a
Reson system (using the 7006 record) the saturation state is updated real time.
"""

import matplotlib
matplotlib.interactive( True )
matplotlib.use( 'WXAgg' )
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib import pyplot as plt
import numpy as np
import wx
import time
from datetime import datetime
import os, sys
import threading
from scipy.interpolate import interp1d

import prr
import sevenpy
import resontvg
import find7Pcompression

class SatFrame(wx.Frame):
    """Satmon frame"""
    def __init__(self, parent, title, opts = []):
        wx.Frame.__init__(self, parent, title=title, size = (600,600))#, style = wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        
        # Catch the corner X close to stop the connection.
        wx.EVT_CLOSE(self, self.OnExit)
        
        # Setup where configuration is coming from, IO layer, and calibration data.
        satmonpath = os.getcwd().rsplit('\\',1)[0] + '\\Satmon'
        os.chdir(satmonpath)
        self.getconfig()
        self.io = Dataflowmanager(opts)
        try:
            cal100data = np.load(self.cal100)
            self.havecal100data = True
        except IOError:
            print 'No 100kHz calibration file found!'
            cal100data = np.array(([np.nan, np.nan],[np.nan, np.nan]))
            self.havecal100data = False
        try:
            cal200data = np.load(self.cal200)
            self.havecal200data = True
        except IOError:
            print 'No 200kHz calibration file found!'
            cal200data = np.array(([np.nan, np.nan],[np.nan, np.nan]))
            self.havecal200data = False
        try:
            cal400data = np.load(self.cal400)
            self.havecal400data = True
        except IOError:
            print 'No 400kHz calibration file found!'
            cal400data = np.array(([np.nan, np.nan],[np.nan, np.nan]))
            self.havecal400data = False
        self.fspstatus = 0  # find7Pcompression status
        
        # The general menu
        generalmenu = wx.Menu()
        docoption = generalmenu.Append(wx.ID_ANY, "&Documentation", " Open the Documentation")
        resetudpoption = generalmenu.Append(wx.ID_ANY, "&ResetUDP", " Reset the Reson UDP connection")
        resettcpoption = generalmenu.Append(wx.ID_ANY, "&ResetTCP", " Reset the Reson TCP connection")
        configoption = generalmenu.Append(wx.ID_ANY, "&Configuration", " Open the satconfig file")
        aboutoption = generalmenu.Append(wx.ID_ABOUT, "&About", " Information about this program")
        exitoption = generalmenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")
        self.Bind(wx.EVT_MENU, self.OpenDoc, docoption)
        self.Bind(wx.EVT_MENU, self.ResetResonUDP, resetudpoption)
        self.Bind(wx.EVT_MENU, self.ResetResonTCP, resettcpoption)
        self.Bind(wx.EVT_MENU, self.OpenSatconfig, configoption)
        self.Bind(wx.EVT_MENU, self.OnAbout, aboutoption)
        self.Bind(wx.EVT_MENU, self.OnExit, exitoption)     
        
        # The setup menu
        setupmenu = wx.Menu()
        fileoption = setupmenu.Append(wx.ID_ANY, "&From File...", "Run from a file")
        networkoption = setupmenu.Append(wx.ID_ANY, "From &Network...", "Run from a Reson Machine")
        self.Bind(wx.EVT_MENU, self.OnFile, fileoption)
        self.Bind(wx.EVT_MENU, self.OnNetwork, networkoption)
   
        # The plot menu
        plotmenu = wx.Menu()
        self.gainoption = plotmenu.AppendCheckItem(wx.ID_ANY, "Gain vs Receive")
        self.Bind(wx.EVT_MENU, self.GainPlot, self.gainoption)
        self.percentoption = plotmenu.AppendCheckItem(wx.ID_ANY, "Beam vs Percent Nonlinear")
        self.Bind(wx.EVT_MENU, self.PercentPlot, self.percentoption)
        self.noiseoption = plotmenu.AppendCheckItem(wx.ID_ANY, "Plot Noise")
        self.Bind(wx.EVT_MENU, self.NoisePlot, self.noiseoption)
        #waterfalloption = plotmenu.AppendCheckItem(wx.ID_ANY, "Corrected Backscatter Waterfall")
        #self.Bind(wx.EVT_MENU, self.WaterfallPlot, waterfalloption)
        # default to both basic plots
        self.gainoption.Check()
        self.percentoption.Check()
        self.whichplot = 3
            
        # Calibration menu
        calmenu = wx.Menu()
        collectionoption = calmenu.Append(wx.ID_ANY, "Collect Data")
        processoption = calmenu.Append(wx.ID_ANY, "Process Data")
        selectionoption = calmenu.Append(wx.ID_ANY, "Selection of Curve")
        inspectoption = calmenu.Append(wx.ID_ANY, "Inspection of Curve")
        comparisonoption = calmenu.Append(wx.ID_ANY, "Compare Curves")
        finalizeoption = calmenu.Append(wx.ID_ANY, "Finalize Curve")
        self.Bind(wx.EVT_MENU, self.runsevenpy, collectionoption)
        self.Bind(wx.EVT_MENU, self.extractcompression, processoption)
        self.Bind(wx.EVT_MENU, self.plotcompression, selectionoption)
        self.Bind(wx.EVT_MENU, self.inspectcurve, inspectoption)
        self.Bind(wx.EVT_MENU, self.compaircurve, comparisonoption)
        self.Bind(wx.EVT_MENU, self.savecurve, finalizeoption)
        
        # Sensitivity menu
        sensemenu = wx.Menu()
        elementacqoption = sensemenu.Append(wx.ID_ANY, "Collect Element Data")
        setbeamformoption = sensemenu.Append(wx.ID_ANY, "Set to Beamforming Mode")
        elementprocoption = sensemenu.Append(wx.ID_ANY, "Process Element Data")
        self.Bind(wx.EVT_MENU, self.getelemdata, elementacqoption)
        self.Bind(wx.EVT_MENU, self.setbeamform, setbeamformoption)
        self.Bind(wx.EVT_MENU, self.procelemdata, elementprocoption)
        
        
        # The menu bar
        menuBar = wx.MenuBar()
        menuBar.Append(generalmenu, "&General")
        menuBar.Append(setupmenu, "&Source")
        menuBar.Append(plotmenu, "&Plot")
        if self.mode == 'calibration':
            menuBar.Append(calmenu, "&Calibration")
            menuBar.Append(sensemenu, "&Elements")
        self.SetMenuBar(menuBar)
        
        # plotting pannel
        self.plotpanel = SatPanel(self, parent, cal100data = cal100data, cal200data = cal200data, cal400data = cal400data)

        # The button
        if self.vessel is None:
            startlabel = "Start - Unknown Vessel"
        else:
            startlabel = "Start - " + self.vessel
        self.thebutton = wx.Button(self, label = startlabel, size = (600, 20))
        self.Bind(wx.EVT_BUTTON, self.OnStart, self.thebutton)
      
        # arrange in the frame
        #vSizer = wx.BoxSizer(wx.VERTICAL)
        vSizer = wx.FlexGridSizer(2, 1, 0, 0)
        vSizer.Add(self.thebutton, 0, wx.ALIGN_CENTER | wx.EXPAND)
        vSizer.Add(self.plotpanel, 1, wx.ALIGN_CENTER | wx.EXPAND)
        vSizer.AddGrowableRow(1,1)
        vSizer.AddGrowableCol(0,1)
        self.SetSizer(vSizer)
        self.SetAutoLayout(True)
        vSizer.Fit(self)
    
    def OnStart(self, event):
        if self.io.frequency == 100000:
            if not self.havecal100data:
                self.SetMinimumMode()
            else:
                self.SetMaximumMode()
        if self.io.frequency == 200000:
            if not self.havecal200data:
                self.SetMinimumMode()
            else:
                self.SetMaximumMode()
        if self.io.frequency == 396000:
            if not self.havecal400data:
                self.SetMinimumMode()
            else:
                self.SetMaximumMode()
        if not self.io.go:
            threading.Thread(target = self.io.start).start()
            if self.io.type != '':
                self.thebutton.SetLabel("Stop")
                print "Starting... ",
                threading.Thread(target = self.plot).start()
        else:
            self.thebutton.SetLabel("Start")
            print "Stopping... ",
            self.io.stop()
            
    def SetMinimumMode(self):
        self.whichplot = 1
        self.gainoption.Check(True)
        self.percentoption.Check(False)
        self.percentoption.Enable(False)

    def SetMaximumMode(self):
        self.whichplot = 3
        self.percentoption.Enable(True)
        self.gainoption.Check(True)
        self.percentoption.Check(True)
            
    def GainPlot(self, event):
        if event.Checked():
            self.PlotOption(1)
        else:
            self.PlotOption(-1)
        
    def PercentPlot(self, event):
        if event.Checked():
            self.PlotOption(2)
        else:
            self.PlotOption(-2)
        
    def WaterfallPlot(self, event):
        if event.Checked():
            self.PlotOption(4)
        else:
            self.PlotOption(-4)
            
    def NoisePlot(self, event):
        if event.Checked() and hasattr(self.io,'getnoise'):
            self.io.getnoise = True
        else:
            self.io.getnoise = False
        
    def PlotOption(self, numplot):
        self.whichplot += numplot
        
    def plot(self):
        while self.io.go:
            self.plotpanel.draw(self.io.gains, self.io.intensity, self.io.power, self.io.frequency, self.whichplot, noise = self.io.noise)

    def OnFile(self, event):
        """Set for reading from a file."""
        dlg = wx.FileDialog(self, "Choose a file", "", "", "*.s7k", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetFilename()
            dirname = dlg.GetDirectory()
            print "Opening file...",
            self.io.fromfile(os.path.join(dirname, filename))
        dlg.Destroy()
        
    def OnNetwork(self, event):
        """Set for reading from a TCP network connection."""
        self.io.from7kcenter(self.sonartype, self.ipaddress, self.ownip)
        
    def OpenDoc(self, event):
        """Open the Saturation Monitor doc if available in the local directory."""
        try:
            status = os.system('"Saturation Monitor.htm"')
            if status == 1:
                print "Saturation Monitor V1.0.htm not found in local directory"
        except:
            print "failure to open file"
        
    def ResetResonUDP(self, event):
        """Reset the Reson UDP connection to the identified self ipaddress."""
        dlg = ChangePortDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
        if dlg.usevalues:
            reset = sevenpy.com7P(self.ipaddress, self.sonartype, self.ownip)
            reset.command7P('stoprequest',(dlg.dataport, 0))
            reset.closeUDP()
            # print 'Sent request to end UDP data connection on port ' + str(dlg.dataport)
        
    def ResetResonTCP(self, event):
        """Reset the Reson TCP connection to the identified self ipaddress."""
        dlg = ChangePortDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
        if dlg.usevalues:
            reset = sevenpy.com7P(self.ipaddress, self.sonartype, self.ownip)
            reset.command7P('stoprequest',(dlg.dataport, 1))
            reset.closeTCP()
            # print 'Sent request to end TCP data connection on port ' + str(dlg.dataport)
        
    def OpenSatconfig(self, event):
        """Open the satconfig.txt file for editing if in the local directory.
        Satmon must be restarted for changes to take effect."""
        try:
            status = os.system('satconfig.txt')
            if status == 1:
                print "Failed to open satconfig.txt. Is it in the local directory?"
            else:
                print "You must save satconfig.txt and restart Satmon for changes to take effect."
        except:
            print "failure to open file"
        
    def OnAbout(self,event):
        dlg = wx.AboutDialogInfo()
        dlg.SetName("Saturation Monitor")
        dlg.SetVersion("for Pydro 14.5")
        dlg.SetDescription("Reson Saturation Monitor")
        dlg.AddDeveloper("Glen Rice")
        dlg.AddDocWriter("See General > Documentation")
        wx.AboutBox(dlg)
        
    def OnExit(self, event):
        if self.io.go:
            print "Stopping... ",
            self.io.stop()
            time.sleep(1)
        if self.io.type == '7kcenter':
            self.io.stop7kcenter()
            time.sleep(1)
        print "Good bye"
        self.Destroy()
        
    def getconfig(self, infilename = 'satconfig.txt'):
        """Reads in the settings for the saturation monitor from an external 
        file.  The format needs to be 'propertyname: value'. A '#' at the
        beginning is recognized as a comment."""
        self.ipaddress = '127.0.0.1'
        self.sonartype = 7125
        self.mode = 'normal'
        self.cal100 = 'satcurve.npy'
        self.cal200 = 'satcurve.npy'
        self.cal400 = 'satcurve.npy'
        self.ownip = ''
        self.vessel = None
        try:
            infile = open(infilename, 'r')
            for line in infile:
                info = line.split()
                if len(info) == 1:
                    temp = info[0].split(':')
                    info = temp
                    if len(info) < 2:
                        print "bad satconfig.txt entry: " + info
                if len(info) >= 2:
                    if info[0].startswith('ipaddress'):
                        self.ipaddress = info[1]
                    elif info[0].startswith('sonartype'):
                        self.sonartype = int(info[1])
                    elif info[0].startswith('mode'):
                        self.mode = info[1]
                    elif info[0].startswith('calfile100kHz'):
                        self.cal100 = info[1]
                        print "reading 100kHz saturation curve from " + self.cal100
                    elif info[0].startswith('calfile200kHz'):
                        self.cal200 = info[1]
                        print "reading 200kHz saturation curve from " + self.cal200
                    elif info[0].startswith('calfile400kHz'):
                        self.cal400 = info[1]
                        print "reading 400kHz saturation curve from " + self.cal400
                    elif info[0].startswith('#'):
                        pass
                    elif info[0].startswith('ownip'):
                        self.ownip = info[1]
                    elif info[0].startswith('vessel'):
                        self.vessel = info[1]
                    else:
                        print "Unused entry type: " + info[0]
            infile.close()
        except IOError:
            print "No satconfig.txt file found. Using default settings."
        
                    
    def runsevenpy(self, event):
        """Run the sevenpy data collection routine for determining the gain
        rolloff curve."""
      
        # Set range of values for calibration and initialize setting on 7P
        reson = sevenpy.com7P(self.ipaddress, self.sonartype, self.ownip)
        reson.getsettings()
        freq = reson.settings[3] / 1000
        reson.command7P('absorption', 0)
        reson.command7P('spreading', 0)
        if self.sonartype == 7125:
            gainrange = xrange(0, 84, 3)
            powerrange = xrange(190, 221, 5)
            reson.command7P('pulse', 0.000100)
            reson.command7P('power', 190)
            reson.command7P('gain', 0)
            reson.command7P('pingrate', 10)
        elif self.sonartype == 7111:
            gainrange = xrange(0, 83, 3)
            powerrange = xrange(175, 231, 5)
            reson.command7P('pulse', 0.000200)
            reson.command7P('power', 175)
            reson.command7P('gain', 10)
            reson.command7P('pingrate', 20)
            
        filetime = datetime.now()
        if self.vessel is None:
            outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_%(freq)03dkHz_cal.s7k" \
                % {'year': filetime.year,
                'month': filetime.month,
                'day': filetime.day,
                'hour': filetime.hour,
                'minute': filetime.minute,
                'freq': freq
                }
        else:
            outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_%(vessel)s_%(freq)03dkHz_cal.s7k" \
                % {'year': filetime.year,
                'month': filetime.month,
                'day': filetime.day,
                'hour': filetime.hour,
                'minute': filetime.minute,
                'vessel': self.vessel,
                'freq': freq
                }
        print 'Writing to filename ' + outfilename
        print

        # numsnippets = 15
        numpings = 15
        # reson.command7P('snippetwindow', (1, numsnippets)) # Set snippet window
        print 'Discharging the sonar projector capacitors, please wait',
        wait  = 8 #seconds
        for i in xrange(wait):
            time.sleep(1)
            print '.',
           # Open UDP socket for data flow
        reson.stopUDP = False
        
        # Begin sending (and recording) data and adjusting settings
        dataport = reson.command7P('selfrecordrequest',(4, 7000, 7006, 7027, 7028), sendTCP = False)
        threading.Thread(target = reson.catchUDP, args = (dataport,outfilename)).start()
        print 'beginning calibration'

        for power in powerrange:
            reson.command7P('power', power)
            for gain in gainrange:
                reson.command7P('gain',gain)
                while reson.gain['count'] >= numpings:
                    reson.gain['count'] = 0
                print '\npower: ' + str(power) +', gain: ' + str(gain) + ', count: ',
                while reson.gain['count'] < numpings:
                    pass
        print '\n',
        
        # End sampling and close UDP socket
        reson.command7P('stoprequest',(dataport, 0))
        time.sleep(1)
        reson.stopUDP = True
        print 'Calibration complete'
        time.sleep(1)
        reson.closeUDP()

        # Reset 7P settings
        reson.command7P('absorption', reson.settings[34])
        reson.command7P('spreading', reson.settings[36])
        # reson.command7P('snippetwindow', (0, 50)) # Turn off snippet window
        reson.closeTCP()
    
    def extractcompression(self, event):
        """Run the first part of find7Pcompression."""
        dlg = wx.FileDialog(self, "Choose a file", "", "", "*_cal.s7k", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.rawfile = dlg.GetFilename()
            dirname = dlg.GetDirectory()
            self.proc = find7Pcompression.fsp(os.path.join(dirname, self.rawfile))
        dlg.Destroy()
        print "Beginning data extraction, please wait..."
        start = time.time()
        self.proc.finddepth()
        self.proc.extract()
        stop = time.time()
        print 'Elapsed time: ' + str(stop - start) + ' seconds.'
        print "Extraction complete.  Please move to next step."
        self.fspstatus = 1
        
    def plotcompression(self, event):
        """Run the second part of find7Pcompression."""
        if self.fspstatus >= 1:
            self.proc.process()
            if self.proc.havedata:
                self.proc.plot()
                self.fspstatus = 2
            else:
                print "Data quality is not sufficient to complete calibration."
        else:
            print "First extract data."
            
            
    def inspectcurve(self, event):
        """Inspect the curve created by this process."""
        if self.fspstatus >=2:
            if self.fspstatus == 2:
                self.proc.extractfitpoints()
                self.fspstatus = 3
        else:
            print 'First extract and process the data.'
        
    def compaircurve(self, event):
        """Compair to previous curve."""
        if self.fspstatus >=3:
            if self.fspstatus == 3:
                self.proc.clean_estpoints()
                self.fspstatus = 4
            dlg = wx.FileDialog(self, "Choose a file", "", "", "*.npy", wx.OPEN)
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetFilename()
                dirname = dlg.GetDirectory()
                oldcurve = np.load(os.path.join(dirname, filename))
                fig = find7Pcompression.pl.figure()
                ax = fig.add_subplot(111)
                ax.hold(True)
                ax.plot(oldcurve[:,0], oldcurve[:,1])
                ax.plot(self.proc.estpoints[:,0], self.proc.estpoints[:,1])
                ax.set_xlabel('Reson Applied Gain')
                ax.set_ylabel('System Measurement (dB)')
                ax.legend(('old values', 'this run'), loc = 4)
            dlg.Destroy()
        else:
            print 'First extract, process, and inspect the data.'
            

        
    def savecurve(self, event):
        """Save the curve as defined by this process."""
        if self.fspstatus >=3:
            if self.fspstatus == 3: 
                self.fspstatus = 4
            # save the curve with the same filename as the raw file it came from.
            self.proc.clean_estpoints()
            np.save(self.rawfile[:-4], self.proc.estpoints)
            print "new curve saved to " + self.rawfile[:-4] + '.npy'
            if self.proc.frequency == 200000:
                self.plotpanel.cal200data = self.proc.estpoints
                caltype = 'calfile200kHz'
            elif self.proc.frequency == 396000:
                self.plotpanel.cal400data = self.proc.estpoints
                caltype = 'calfile400kHz'
            elif self.proc.frequency == 100000:
                self.plotpanel.cal100data = self.proc.estpoints
                caltype = 'calfile100kHz'
            else:
                print "unknown frequency used in calibration"
            # get the current time and format
            nowtime = datetime.now()
            rightnow = "%(year)04d-%(month)02d-%(day)02d at %(hour)02d%(minute)02d" \
                % {'year': nowtime.year,
                'month': nowtime.month,
                'day': nowtime.day,
                'hour': nowtime.hour,
                'minute': nowtime.minute
                }
            try:
                infile = open('satconfig.txt', 'r')
                allfile = infile.read().split('\n')
                newfile = ''
                infile.close()
                linefound = False
                for line in allfile:
                    if line.startswith(caltype):
                        line = caltype + ': ' + self.rawfile[:-4] + '.npy # updated ' + rightnow
                        linefound = True
                    newfile += line + '\n'
                if not linefound:
                    newline = caltype + ': ' + self.rawfile[:-4] + '.npy # updated ' + rightnow + '\n'
                    newfile += newline
                outfile = open('satconfig.txt', 'w')
                outfile.write(newfile)
                outfile.close()
                print "satconfig.txt updated with new curve."
            except IOError:
                pass
        else:
            print 'First extract, process, and inspect the data.'
            
    def getelemdata(self, event):
        """
        Create a UDP connection to the 7kcenter and request the 7000 and
        7038 (element level) data records.
        """
        dlg = SetSpeedDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
        if dlg.usevalues:
            reson = sevenpy.com7P(self.ipaddress, self.sonartype, self.ownip)
            reson.getsettings()
            freq = reson.settings[3] / 1000
            filetime = datetime.now()
            if self.vessel is None:
                outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_%(freq)03dkHz_elem.s7k" \
                    % {'year': filetime.year,
                    'month': filetime.month,
                    'day': filetime.day,
                    'hour': filetime.hour,
                    'minute': filetime.minute,
                    'freq': freq
                    }
            else:
                outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_%(vessel)s_%(freq)03dkHz_%(speed)01dkts_elem.s7k" \
                    % {'year': filetime.year,
                    'month': filetime.month,
                    'day': filetime.day,
                    'hour': filetime.hour,
                    'minute': filetime.minute,
                    'vessel': self.vessel,
                    'freq': freq,
                    'speed': dlg.speed
                    }
            
            # Set range of values for calibration and initialize setting on 7P
            reson.command7P('absorption', 0)
            reson.command7P('spreading', 0)
            reson.command7P('power', 0)
            reson.command7P('gain', 0)
            reson.command7P('pingrate', 10)
            reson.command7P('7kmodetype', [2,0])
            if self.sonartype == 7125:
                numelements = 0  # zero gets you all elements
                gainrange = xrange(0, 84, 9)
                elemrange = range(numelements)
                #reson.command7P('specIQ',(16,0,220,numelements,elemrange))
                reson.command7P('range', 10)
            elif self.sonartype == 7111:
                numelements = 144
                gainrange = xrange(0, 84, 9)
                elemrange = range(numelements)
                reson.command7P('specIQ',(16,0,220,numelements,elemrange))
                reson.command7P('range', 100) # This needs to be changed to what gets you 200 samples for the 7111
            numpings = 15
            reson.stopUDP = False
            print 'Discharging the sonar projector capacitors, please wait',
            wait  = 4 #seconds
            for i in xrange(wait):
                time.sleep(1)
                print '.',
            
            # Begin sending (and recording) data and adjusting settings
            dataport = reson.command7P('selfrecordrequest',(2, 7000, 7038), sendTCP = False)
            threading.Thread(target = reson.catchUDP, args = (dataport,outfilename)).start()
            print 'beginning collection of element data'

            for gain in gainrange:
                reson.command7P('gain',gain)
                while reson.gain['count'] >= numpings:
                    reson.gain['count'] = 0
                print '\n',
                print str(gain) + ': ',
                while reson.gain['count'] < numpings:
                    pass
            print '\n',
            # End sampling and close UDP socket
            reson.command7P('stoprequest',(dataport, 0))
            time.sleep(1)
            reson.stopUDP = True
            print 'Element collection complete'
            time.sleep(1)
            reson.closeUDP()

            # Reset 7P settings
            reson.command7P('7kmodetype', [0,0])
            reson.command7P('absorption', reson.settings[34])
            reson.command7P('spreading', reson.settings[36])
            reson.command7P('power', reson.settings[14])
            reson.command7P('gain', reson.settings[15])
            reson.command7P('range', reson.settings[13])
            reson.command7P('pingrate', reson.settings[11])
            reson.closeTCP()
            del reson
        
    def setbeamform(self, event):
        """This method is to change the mode of the multibeam to beamforming."""
        reson = sevenpy.com7P(self.ipaddress, self.sonartype, self.ownip)
        reson.command7P('7kmodetype', [0,0])
        del reson
        
    def procelemdata(self, event):
        """Process and plot element level data as suggested by Sam.  The
        individual pings are restacked into an array for each gain setting."""
        dlg = wx.FileDialog(self, "Choose a file", "", "", "*.s7k", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.rawfile = dlg.GetFilename()
            dirname = dlg.GetDirectory()
            havefile = True
        else: havefile = False
        dlg.Destroy()
        if havefile:
            r = prr.x7kRead(os.path.join(dirname, self.rawfile))
            r.mapfile()
            print "mapping complete.  Processing data."
            # make sure there are 7038 records in the file
            if r.map.packdir.has_key('7038'):
                r.getrecord(7000, 0)
                frequency = r.packet.subpack.header[3]
                samplerate = r.packet.subpack.header[4]
                r.getrecord(7038, 0)
                # assuming the same number of samples throughout the file
                maxsamples = r.packet.subpack.header[4]
                numelements = r.packet.subpack.numelements
                # initialize stuff
                gainlist = {}
                mags = {}
                num7038 = len(r.map.packdir['7038'])
                dir7000 = np.asarray(r.map.packdir['7000'])
                # get the number of pings at each gain setting
                for pingnum in range(num7038):
                    tstamp = r.map.packdir['7038'][pingnum][1]
                    idx = np.nonzero(dir7000[:,1] == tstamp)[0]
                    if len(idx) == 1:
                        r.getrecord(7000, idx[0])
                        gain = str(r.packet.subpack.header[15])
                        if gainlist.has_key(gain):
                            gainlist[gain].append(pingnum)
                        else:
                            gainlist[gain] = [pingnum]
                # inialize arrays for all gain settings
                for gain in gainlist:
                    num = len(gainlist[gain])
                    mags[gain] = np.zeros((maxsamples * num, numelements))
                # get data from all pings
                pingcount = 0
                for gain in gainlist:
                    pointer = 0
                    for n,pingnum in enumerate(gainlist[gain]):
                        try:
							r.getrecord(7038,pingnum)
							numsamples = r.packet.subpack.numsamples
							pingcount +=1
							complete = str(int(100.0 * pingcount / num7038))
							b = (len(complete) + 2) * '\b'
							print b + complete + '%',
							end = pointer + numsamples
							mag = np.abs(r.packet.subpack.r.reshape(-1,numelements))
							mags[gain][pointer:end, :] = mag
                        except:
                            mags[gain][pointer:end, :] = np.nan
                        pointer += numsamples
                    mags[gain] = mags[gain][:pointer, :]
                print '\n',
                # reusing a variable name, sorry.  I'm not very creative.
                gainlist = [float(g) for g in mags.keys()]
                gainlist.sort()
                aveMag = np.zeros((len(gainlist), numelements))
                targetplotgain = 40     # the closest gain to this value is plotted
                lastval = 100           # just picked a large value...
                for idx, gain in enumerate(gainlist):
                    g_amp = mags[str(gain)]
                    #FFT by Sam Greenaway
                    #one side fft of magnitude, treat each element independently
                    C = np.average(g_amp, axis=0)	
                    #Tile average to remove average mag value before fft 
                    D = np.tile(C,(len(g_amp),1))
                    W = np.tile(np.hanning(len(g_amp)),(numelements,1)).T
                    aveMag[idx,:] = np.average(g_amp, axis = 0)
                    testval = np.abs(gain - targetplotgain)
                    if testval < lastval:
                        lastval = testval
                        A = (8/3)*(2/(samplerate*len(g_amp)))*np.abs(np.fft.rfft(np.multiply(W,(g_amp-D)), axis=0))**2
                        midg_amp = g_amp
                        midgain = str(gain)
                #average PSD - equivalent to ensemble avergaing across elements
                aA = np.average(A, axis=1)
                # the frequencies
                fn1S = np.linspace(0,samplerate/2,np.size(aA))
                # get rid of some warnings...
                idx = np.nonzero(midg_amp == 0)
                midg_amp[idx[0],idx[1]] = 1
                idx = np.nonzero(aveMag == 0)
                aveMag[idx[0],idx[1]] = 1
                # Plotting also by Sam... mostly
                f=plt.figure(figsize = (15,10))
                f.suptitle(self.rawfile)
                plt.subplot(2,2,1)
                plt.imshow(20*np.log10(midg_amp), aspect = 'auto')
                plt.title('Amplitude, ' + midgain + 'dB gain')
                plt.xlabel('element')
                plt.ylabel('sample')
                plt.colorbar()

                plt.subplot(2,2,2)
                plt.plot(gainlist,20*np.log10(aveMag))
                plt.title('Average Amplitude by Gain')
                plt.xlabel('gain')
                plt.ylabel('dB re 7125 Units')
                plt.grid()

                ax = plt.subplot(2,2,3)
                linelist = ax.plot(20*np.log10(aveMag).T)
                ax.set_title('Average Element Amplitude by Gain')
                ax.set_xlabel('element')
                ax.set_ylabel('dB re 7125 Units')
                ax.set_xlim([0, numelements])
                ax.grid()
                box = ax.get_position()
                ax.set_position([box.x0, box.y0, box.width*0.8, box.height])
                ax.legend(linelist, gainlist, loc = 'center left', bbox_to_anchor=(1,0.5))

                plt.subplot(2,2,4)
                plt.plot(fn1S,20*np.log10(aA))
                plt.title('One Sided PSD, '+ midgain +'dB Gain, ensemble averaged across elements')
                plt.xlabel('Hz')
                plt.ylabel('dB re 7125 Units/ Hz')
                plt.grid()

                plt.draw()
                print "Thanks Sam."
            else:
                print 'No 7038 data found. Make sure the latest Reson Feature Pack is installed.'
        

    
class SatPanel (wx.Panel):
    """The PlotPanel has a Figure and a Canvas. OnSize events simply set a 
    flag, and the actual resizing of the figure is triggered by an Idle 
    event."""
    def __init__(self, parent, color=None, dpi=None, cal100data = [], cal200data = [], cal400data = [], **kwargs):
        self.parent = parent
        # initialize Panel
        if 'id' not in kwargs.keys():
            kwargs['id'] = wx.ID_ANY
        if 'style' not in kwargs.keys():
            kwargs['style'] = wx.NO_FULL_REPAINT_ON_RESIZE
        wx.Panel.__init__( self, parent, **kwargs )

        # initialize matplotlib stuff
        self.figure = matplotlib.figure.Figure( None, dpi )
        self.canvas = FigureCanvasWxAgg( self, -1, self.figure )
        self.SetColor( color )

        self._SetSize()
        #self.draw()

        self._resizeflag = False

        self.Bind(wx.EVT_IDLE, self._onIdle)
        self.Bind(wx.EVT_SIZE, self._onSize)
        
        self.whichplots = 0
        self.cal100func = interp1d(cal100data[:,0], cal100data[:,1], bounds_error=False)
        self.cal100data = cal100data
        self.cal200func = interp1d(cal200data[:,0], cal200data[:,1], bounds_error=False)
        self.cal200data = cal200data
        self.cal400func = interp1d(cal400data[:,0], cal400data[:,1], bounds_error=False)
        self.cal400data = cal400data
        
    def SetColor(self, rgbtuple=None):
        """Set figure and canvas colours to be the same."""
        if rgbtuple is None:
            rgbtuple = wx.SystemSettings.GetColour( wx.SYS_COLOUR_BTNFACE ).Get()
        clr = [c/255. for c in rgbtuple]
        self.figure.set_facecolor( clr )
        self.figure.set_edgecolor( clr )
        self.canvas.SetBackgroundColour( wx.Colour( *rgbtuple ) )

    def _onSize(self, event):
        self._resizeflag = True

    def _onIdle(self, event):
        if self._resizeflag:
            self._resizeflag = False
            self._SetSize()

    def _SetSize(self):
        pixels = tuple( self.parent.GetClientSize() )
        self.SetSize( (pixels[0], pixels[1] - 20) )
        self.canvas.SetSize( (pixels[0], pixels[1] - 20) )
        pix = self.figure.get_dpi()
        self.figure.set_size_inches( float( pixels[0] )/pix,
                                     float( pixels[1] )/pix )

    def draw(self, gains, intensity, power, freq, whichplots = 7, noise = None):
        """Draw data."""
        maxgain = 83
        
        if freq == 100000:
            caldata = self.cal100data
            calfunc = self.cal100func
        if freq == 200000:
            caldata = self.cal200data
            calfunc = self.cal200func
        elif freq == 396000 or freq == 400000:
            caldata = self.cal400data
            calfunc = self.cal400func
        else:
            print "no known frequency found: " + str(freq)

        if self.whichplots != whichplots:
            self.whichplots = whichplots
            self.figure.clear()
            self.title = self.figure.suptitle('')
            if whichplots == 1:
                self.satplot = self.figure.add_subplot(111)
            elif whichplots == 2:
                self.intplot = self.figure.add_subplot(111)
                self.intplot.hold(False)
            elif whichplots == 3:
                self.satplot = self.figure.add_subplot(211)
                self.intplot = self.figure.add_subplot(212)
                self.intplot.hold(False)
                self.calmax = caldata[:,1].max()
            elif whichplots == 4:
                try:
                    numbeams = len(gains)
                    self.waterfallplot = self.figure.add_subplot(111)
                    self.waterfall = np.zeros((numbeams,numbeams))
                    self.waterfallplot.hold(False)
                except TypeError: # if intensity isn't an array remove the plot
                    self.whichplots = self.whichplots & 3
            elif whichplots == 5:
                self.satplot = self.figure.add_subplot(211)
                try:
                    numbeams = len(gains)
                    self.waterfallplot = self.figure.add_subplot(212)
                    self.waterfall = np.zeros((numbeams/2,numbeams))
                    self.waterfallplot.hold(False)
                except TypeError: # if intensity isn't an array remove the plot
                    self.whichplots = self.whichplots & 3
            elif whichplots == 6:
                self.intplot = self.figure.add_subplot(211)
                self.intplot.hold(False)
                try:
                    numbeams = len(gains)
                    self.waterfallplot = self.figure.add_subplot(212)
                    self.waterfall = np.zeros((numbeams/2,numbeams))
                    self.waterfallplot.hold(False)
                except TypeError: # if intensity isn't an array remove the plot
                    self.whichplots = self.whichplots & 3
            elif whichplots == 7:
                grid = matplotlib.gridspec.GridSpec(2,2)
                self.satplot = self.figure.add_subplot(221)
                self.intplot = self.figure.add_subplot(223)
                self.intplot.hold(False)
                try:
                    numbeams = len(gains)
                    self.waterfallplot = self.figure.add_subplot(grid[:,1])
                    self.waterfall = np.zeros((2*numbeams,numbeams))
                    self.waterfallplot.hold(False)
                except TypeError: # if intensity is not an array remove the plot
                    self.whichplots = self.whichplots & 3
        if self.whichplots & 1 == 1:
            self.satplot.plot(gains, intensity, 'o')
            self.satplot.hold(True)
            self.satplot.plot(caldata[:,0],caldata[:,1],'r')
            if noise is not None:
                self.satplot.plot([0,maxgain],[noise, noise + maxgain],'k')
            self.satplot.set_xlim((0,maxgain))
            self.satplot.set_ylim((0,95))
            self.satplot.set_xlabel('Applied Gain (dB)')
            self.satplot.set_ylabel('20log10(Magnitude)')
            self.satplot.hold(False)
        if self.whichplots & 2 == 2:
            percentsat = self.calmax + intensity - calfunc(gains) #
            try:
                beams = np.arange(len(intensity))
                self.intplot.bar(beams, percentsat, bottom = -self.calmax)
                self.intplot.axhline(y = 0, color = 'r')
                self.intplot.axhline(y = -10, color = 'y')
                self.intplot.set_xlim((0,len(intensity)))
                self.intplot.set_ylim((-self.calmax,10))
                self.intplot.set_xlabel('Beam Number')
                self.intplot.set_ylabel('20*log10(Magnitude / Saturation)')
            except TypeError:
                pass
        if self.whichplots & 4 == 4:
            self.waterfall[1:,:] = self.waterfall[:-1,:]
            self.waterfall[0,:] = intensity - gains - power
            self.waterfallplot.imshow(self.waterfall)
        self.title.set_text('Working at ' + str(freq) + ' Hz')
        self.canvas.print_figure('SaturationPlot')
            
class Dataflowmanager:
    """Designed to provide plottable data to the satplotpannel.  Acts as a
    layer between the data source and the display frame.  Uses the sevenpy 
    and prr modules to get data from the Reson machine and decode the packets."""
    def __init__(self, opts):
        self.go = False
        self.type = '' 
        self.power = 0
        self.gains = 0
        self.frequency = 200000
        self.intensity = 0
        
    def fromfile(self, infilename):
        """Initialize the file source."""
        self.infilename = infilename
        self.filesource = prr.x7kRead(infilename)
        self.filesource.mapfile()
        self.numrecords = len(self.filesource.map.packdir['7000'])
        self.filesource.getrecord(7000,0)
        self.datarate = self.filesource.packet.subpack.header[12]
        self.frequency = self.filesource.packet.subpack.header[3]
        self.samplerate = self.filesource.packet.subpack.header[4]
        if self.filesource.map.packdir.has_key('7018'):
            self.useWC = 7018
        elif self.filesource.map.packdir.has_key('7008'):
            self.filesource.getrecord(7008,0)
            sp = self.filesource.packet.subpack
            if sp.numsnip == sp.header[-5]:
                self.useWC = 7008
        else:
            self.useWC = None
        self.count = 0
        self.type = 'file'
        self.noise = None
        self.getnoise = False
        print "File opened and mapped.",
        
    def startfile(self):
        """Collects data at the file's specified rate and pass to the local
        buffer."""
        print "Beginning Data extraction from s7k file. ",
        while self.go:
            time.sleep(self.datarate)
            self.filesource.getrecord(7000, self.count)
            self.power = self.filesource.packet.subpack.header[14]
            gain = self.filesource.packet.subpack.header[15]
            absorption = self.filesource.packet.subpack.header[-4]
            spreading = self.filesource.packet.subpack.header[-2]
            self.datarate = self.filesource.packet.subpack.header[12]
            #print 'gain: ' + str(gain) + ', absorp: ' + str(absorption) + ', spread: ' + str(spreading)
            self.filesource.findpacket(7006, False)
            range = self.filesource.packet.subpack.data[0]
            intensity = self.filesource.packet.subpack.data[2]
            self.gains = resontvg.getsumgain(range, gain, absorption, spreading)
            tempindx = np.nonzero(intensity == 0)
            intensity[tempindx] = np.nan
            self.intensity = 20*np.log10(intensity)
            if self.useWC is not None and self.getnoise is True:
                self.filesource.findpacket(self.useWC, False)
                mag = self.filesource.packet.subpack.mag
                # average all the beams
                wc_avg = mag.mean(axis = 1)
                # find the first return and move back ten samples
                maxsample = wc_avg.argmax() - 10
                # find and remove the tvg curve
                samplerange = np.arange(maxsample) / self.samplerate
                tvgcurve= resontvg.getsumgain(samplerange, gain, absorption, spreading)
                self.noise = (wc_avg[:maxsample]-tvgcurve).mean()
            else:
                self.noise = None
            self.count += 1
            if self.count >= self.numrecords:
                self.count = 0
        
    def from7kcenter(self, sonar, reson_address, ownip):
        """Setup and request data via TCP from the provided sonar at the
        provided address and port."""
        self.reson = sevenpy.com7P(reson_address, sonar, ownip)
        self.reson.stopUDP = False
        self.getnoise = False
        self.noise = None
        self.dataport = self.reson.command7P('selfrecordrequest',(2, 7000, 7006))
        self.type = '7kcenter'
        
    def start7kdata(self):
        """Pulls data from the sevenpy buffer and extracts the information needed."""
        print "Beginning data extraction from UDP connection. ",
        while self.go:
            if self.reson.newdata:
                # pull data from the data stream buffer
                data = self.reson.dataout
                self.reson.newdata = False
                if data.has_key('7000') and data.has_key('7006'):
                    # check to make sure the time stamps of the packets are the same
                    if data['7000'][20:30] == data['7006'][20:30]:
                        subpacket7000 = prr.Data7000(data['7000'][64:-4])
                        subpacket7006 = prr.Data7006(data['7006'][64:-4])
                        intensity = subpacket7006.data[2]
                        tempindx = np.nonzero(intensity == 0)
                        intensity[tempindx] = np.nan
                        self.gains = resontvg.getsumgain(subpacket7006.data[0],\
                            subpacket7000.header[15], subpacket7000.header[-4],\
                            subpacket7000.header[-2])
                        self.intensity = 20*np.log10(intensity)
                        self.frequency = subpacket7000.header[3]
                    # else: print 'unmatching time stampes found!'
            if self.getnoise:
                threading.Thread(target = self.cycle7018).start()

        
    def stop7kcenter(self):
        """Stop the TCP data flow from the 7kcenter."""
        self.reson.stopTCP = True
        print "Stand by while properly closing connction to 7kcenter. """
        self.getnoise = False
        time.sleep(1)
        try:
            self.reson.command7P('stoprequest',(self.dataport, 1))
            self.reson.closeTCP()
        except:
            print 'Error: no connection to 7Kcenter made?'
        
    def start(self):
        if self.type == 'file':
            self.go = True
            self.startfile()
        elif self.type == '7kcenter':
            self.go = True
            self.start7kdata()
        else:
            print 'No I/O type set'
            
    def stop(self):
        self.go = False
   
    def cycle7018(self, cycle = 5):
        """
        Adds to the TCP connection and requests a 7018 record.  When the data 
        arrives it is processed and made available and the request is canceled.
        kwarg 'cycle' is the time between request for a new record.
        """
        self.getnoise = True
        while self.getnoise:
            self.start7018()
            self.proc7018()
            time.sleep(cycle)
        self.noise = None
        
    def start7018(self):
        """
        Opens a port and requests a 7018 record.
        """
        self.tempdataport = self.reson.command7P('selfrecordrequest',(1, 7018)) 
        
    def proc7018(self):
        """
        Waits for the next 7018, and when received it stops the request.
        The 7018 record is then processed into an estimate of the system noise
        floor given the current operating conditions.
        """
        # wait for a new record
        timer = 0
        while not self.reson.new7018 and timer < 1:
            time.sleep(0.1)
            timer += 0.1
        # stop the record request
        self.stop7018()
        if self.reson.new7018:
            # get the data
            subpack = prr.Data7018(self.reson7018.data7018[64:-4])
            # average all the beams
            wc_avg = subpack.mag.mean(axis = 1)
            # find the first return and move back ten samples
            maxsample = wc_avg.argmax() - 10
            # still need to remove gain and tvg here!!!
            print '!',
            self.noise = subpack.mag[:maxsample,:].mean()
            # make sure that we are ready for new data
            self.reson7018.new7018 = False
        
    def stop7018(self):
        """
        Closes any open requests for a 7018 record from the 7Kcenter.
        """
        self.reson.command7P('stopselfrecordrequest',(1, 7018))
    
class ChangePortDialog(wx.Dialog):
    """From an example at http://zetcode.com/wxpython/dialogs/"""
    def __init__(self, *args, **kw):
        super(ChangePortDialog, self).__init__(*args, **kw) 
            
        self.InitUI()
        self.SetSize((250, 200))
        self.SetTitle("Cancel Subscription")
        
        self.usevalues = False
        
    def InitUI(self):

        pnl = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        sb = wx.StaticBox(pnl, label='Satmon Machine')
        sbs = wx.StaticBoxSizer(sb, orient=wx.VERTICAL)        

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)        
        hbox1.Add(wx.StaticText(pnl, -1, 'IP Address'))
        self.ipaddrbox = wx.TextCtrl(pnl)
        hbox1.Add(self.ipaddrbox, flag=wx.LEFT, border=5)
        sbs.Add(hbox1)
        
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)        
        hbox2.Add(wx.StaticText(pnl, -1, 'Port'))
        self.portbox = wx.TextCtrl(pnl)
        hbox2.Add(self.portbox, flag=wx.LEFT, border=5)
        sbs.Add(hbox2)
        
        pnl.SetSizer(sbs)
       
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        okButton = wx.Button(self, label='Ok')
        closeButton = wx.Button(self, label='Close')
        hbox3.Add(okButton)
        hbox3.Add(closeButton, flag=wx.LEFT, border=5)

        vbox.Add(pnl, proportion=1, 
            flag=wx.ALL|wx.EXPAND, border=5)
        vbox.Add(hbox3, 
            flag=wx.ALIGN_CENTER|wx.TOP|wx.BOTTOM, border=10)

        self.SetSizer(vbox)
        
        okButton.Bind(wx.EVT_BUTTON, self.OnOkay)
        closeButton.Bind(wx.EVT_BUTTON, self.OnClose)
        
    def OnClose(self, e):
        self.Destroy()
        
    def OnOkay(self, e):
        self.dataport = int(self.portbox.GetValue())
        self.ipaddress = self.ipaddrbox.GetValue()
        if len(str(self.dataport)) > 0 and len(self.ipaddress) > 0:
            self.usevalues = True
        self.Destroy()
       
class SetSpeedDialog(wx.Dialog):
    """From an example at http://zetcode.com/wxpython/dialogs/"""
    def __init__(self, *args, **kw):
        super(SetSpeedDialog, self).__init__(*args, **kw) 
            
        self.InitUI()
        self.SetSize((250, 200))
        self.SetTitle("Set Vessel Speed")
        
        self.usevalues = False
        
    def InitUI(self):

        pnl = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        sb = wx.StaticBox(pnl, label='Enter vessel speed in integer knots')
        sbs = wx.StaticBoxSizer(sb, orient=wx.VERTICAL)        

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.speedbox = wx.TextCtrl(pnl)
        hbox1.Add(self.speedbox, flag=wx.LEFT, border=5)
        hbox1.Add(wx.StaticText(pnl, -1, ' Knots'))
        sbs.Add(hbox1)
        
        pnl.SetSizer(sbs)
       
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        okButton = wx.Button(self, label='Ok')
        closeButton = wx.Button(self, label='Close')
        hbox3.Add(okButton)
        hbox3.Add(closeButton, flag=wx.LEFT, border=5)

        vbox.Add(pnl, proportion=1, 
            flag=wx.ALL|wx.EXPAND, border=5)
        vbox.Add(hbox3, 
            flag=wx.ALIGN_CENTER|wx.TOP|wx.BOTTOM, border=10)

        self.SetSizer(vbox)
        
        okButton.Bind(wx.EVT_BUTTON, self.OnOkay)
        closeButton.Bind(wx.EVT_BUTTON, self.OnClose)
        
    def OnClose(self, e):
        self.Destroy()
        
    def OnOkay(self, e):
        self.usevalues = True
        self.speed = self.speedbox.GetValue()
        try:
            self.speed = int(self.speed)
            self.usevalues = True
        except:
            print "Invalid speed provided."
            self.usevalues = False
        self.Destroy()


def main():        
    app = wx.App(0)
    if len(sys.argv) > 1:
        opts = sys.argv[1:]
        frame = SatFrame(None, 'Reson 7K Saturation Monitor', opts = opts)
    else:
        frame = SatFrame(None, 'Reson 7K Saturation Monitor')
    frame.Show()
    app.MainLoop()
    
if __name__ == '__main__':
    main()