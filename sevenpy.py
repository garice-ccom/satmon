"""sevenpy
Glen Rice 2/8/11
V0.2.3 20140625

Built to run a field calibration on a Reson 7P reciever as outlined in Sam 
Greenaway's Thesis at the University of New Hampshire in 2010. This format
complies with the Reson Data Definition Format Document version 2.00. This
script currently assume a 7125. The class com7P handles packet formation and
general setup of tcp or udp sockets for communication with the 7P. The
command7P method is the primary way to assemble packets (commands) and send
them. Thanks goes to Tom Weber
"""

import socket, struct, time
import pylab as pl
from datetime import datetime
import threading

class com7P:
    """Communications with the Reson 7P, both packets and sockets"""
    
    def __init__(self, reson_address, device, ownip = ''):
        """Start by initializing the 7P information"""
        
        self.device = device
        # hard coding the enumerator (frequency indicator) to 0
        self.enumerator = 0
        # Set Socket Parameters
        self.host = reson_address
        self.port = 7000
        self.buf = 60000
        self.addr = (self.host,self.port)
        if len(ownip) == 0:
            self.ownip = socket.gethostbyname(socket.gethostname())
        else:
            self.ownip = ownip
        
        # Dictionary for counting packet numbers
        self.gain = {'level': 0, 'count': 0}

        # Packet Formats
        self.nf_fmt = '<2HI2H4I2HI' #36 bytes
        self.drf_fmt = '<2H4I2Hf2BH4I2H3I'  #64 bytes
        self.fmt7503 = '<Q2H4f2IfI5f2I5fIf3IfI7fH6fI2H2f2dH2IfIf4B7I'
        
    def NetFrame(self,packet):
        """The Network Frame Header format and fields. Ths method recieves 
        the subpacket and returns a packet ready to be passed to the 7P."""

        # Network Frame Values
        ProVer = 5
        Offset = struct.calcsize(self.nf_fmt)
        TotalPack = 1
        TotalRec = 1
        TransID = 1
        PackSize = struct.calcsize(self.nf_fmt) + len(packet)
        TotalSize = len(packet)
        SeqNum = 0
        DestDev = self.device
        DestEnum = self.enumerator
        SourceEnum = 0
        SourceID = 0

        self.nf = struct.pack(self.nf_fmt, ProVer, Offset, TotalPack, TotalRec,
        TransID,PackSize,TotalSize,SeqNum,DestDev,DestEnum,SourceEnum,SourceID)
        
        return self.nf + packet
        
    def DataRecord(self, recordtype, record):
        """The Data Record Frame format and fields. This uses the time stamp
        at time of creation for the time fields. It recieve the Reson Record 
        type and the associated data (correctly formated for transfer) and 
        returns a Reson Data Record Frame."""
        
        # Get the current time (UTC)
        now = datetime.utcnow().timetuple()
        #Data Record Frame Values
        ProVer = 5
        Offset = 60
        Sync = 65535
        Size = struct.calcsize(self.drf_fmt) + len(record) + 4 #4 is checksum
        DataOff = 0
        DataID = 0
        Year = now[0]
        Day = now[7]
        Sec = now[5]
        Hour = now[3]
        Min = now[4]
        Res = 1
        RecType = recordtype
        # Device is set when the class is initialized
        SysEnum = self.enumerator
        Res2 = 1
        Flag = 0
        Res3 = 0
        Res4 = 0
        Total = 0
        Frag = 0
        
        CheckSum = struct.pack('<I', Size - 4)
        self.drf = struct.pack(self.drf_fmt, ProVer, Offset, Sync, Size, 
        DataOff, DataID, Year, Day, Sec, Hour, Min, Res, RecType, self.device,
        SysEnum, Res2, Flag, Res3, Res4, Total, Frag) + record + CheckSum
        
        return self.drf
        
    def RecordType(self, datatype, data = ()):
        """The Data Record Type Header format and fields for a 7500 Record
        Type (remote control) or for a 7611 (absorption) or 7612 (spreading).
        The command type is sent with the appropriate data in a tuple to this
        method, and the correctly formated binary Reson Record Type Header 
        with data is returned. Ticket tracking"""
        # Ticket number is the the control ID, and Tracking number is zero.
        
        recordtype = 7500    #make all packets a 7500 packet unless otherwise
        if datatype == 'range':
            self.rth_fmt = '<2I2Qf'
            self.rth = struct.pack(self.rth_fmt, 1003, 1003, 0, 0, data)
        elif datatype == 'pingrate':
            self.rth_fmt = '<2I2Qf'
            self.rth = struct.pack(self.rth_fmt, 1004, 1004, 0, 0, data)
        elif datatype == 'power':
            self.rth_fmt = '<2I2Qf'
            self.rth = struct.pack(self.rth_fmt, 1005, 1005, 0, 0, data)
        elif datatype == 'pulse':
            self.rth_fmt = '<2I2Qf'
            self.rth = struct.pack(self.rth_fmt, 1006, 1006, 0, 0, data)
        elif datatype == 'gain':
            self.rth_fmt = '<2I2Qf'
            self.rth = struct.pack(self.rth_fmt, 1008, 1008, 0, 0, data)
        elif datatype == '7kmodetype':
            self.rth_fmt = '<2I2Q2H'
            # data[0] is the mode, where 0 = Beamformed, 1 = Autopilot, 2 = Raw I&Q
            # data[1] is the Automethod, which I don't know how to format...
            self.rth = struct.pack(self.rth_fmt, 1014, 1014, 0, 0, data[0], data[1])
        elif datatype == 'gaintype':
            # data values: 0 = TVG, 1 = Auto, 2 = Fixed 
            self.rth_fmt = '<2I2Q5I'
            self.rth = struct.pack(self.rth_fmt, 1017, 1017, 0, 0, data,
            0, 0, 0, 0)
        elif datatype == 'txwidth':
            self.rth_fmt = '<2I2Q2f'
            self.rth = struct.pack(self.rth_fmt, 1022, 1022, 0, 0, data[0], data[1])
        elif datatype == 'singlerequest':
            self.rth_fmt = '<2I2QI'
            self.rth = struct.pack(self.rth_fmt, 1050, 1050, 0, 0, data)
        elif datatype == 'selfrecordrequest':
            n = data[0]    # The number of records in the request
            print 'Subscribing to records',
            for n in data[1:]:
                print n,
            print '\n'
            RecList = ''
            for n in data[1:]:
                RecList += struct.pack('<I',n)
            self.rth_fmt = '<2I2QI'
            self.rth = struct.pack(self.rth_fmt, 1051, 1051, 0, 0, data[0]) + RecList
        elif datatype == 'stopallrequests':
            self.rth_fmt = '<2I2Q'
            self.rth = struct.pack(self.rth_fmt, 1052, 1052, 0 ,0)
        elif datatype == 'recordrequest':
            n = data[2]    # The number of records in the request
            print 'Subscribing to records',
            for i in xrange(1,n+1):
                print data[-i],
            print '\n'
            RecList = struct.pack('<I', data[-n])
            for i in xrange(1,n):
                RecList += struct.pack('<I',data[-i])
            ipaddress = self.makeip(self.ownip)
            self.rth_fmt = '<2I2QI2HI'
            self.rth = struct.pack(self.rth_fmt, 1053, 1053, 0, 0, ipaddress,
            data[0], data[1], data[2]) + RecList
        elif datatype == 'stoprequest':
            ipaddress = self.makeip(self.ownip)
            self.rth_fmt = '<2I2QI2H'
            self.rth = struct.pack(self.rth_fmt, 1054, 1054, 0 ,0, ipaddress,
            data[0], data[1])
            print "Canceling record subscription on port " + str(data[0])
        elif datatype == 'stopselfrecordrequest':
            n = data[0]    # The number of records in the request
            print 'Subscribing to records',
            for n in data[1:]:
                print n,
            print '\n'
            RecList = ''
            for n in data[1:]:
                RecList += struct.pack('<I',n)
            self.rth_fmt = '<2I2QI'
            self.rth = struct.pack(self.rth_fmt, 1056, 1056, 0, 0, data[0]) + RecList        
        elif datatype == 'snippetwindow':
            self.rth_fmt = '<2I2Q2I'
            self.rth = struct.pack(self.rth_fmt, 1103, 1103, 0, 0, data[0], data[1])
        elif datatype == 'snippettype':
            self.rth_fmt = '<2I2QI'
            self.rth = struct.pack(self.rth_fmt, 1105, 1105, 0, 0, data)
        elif datatype == 'specIQ':
            self.rth_fmt = '<2I2QH2IH'
            self.rth = struct.pack(self.rth_fmt, 1138, 1138, 0, 0, data[0], data[1], data[2], data[3])
            for element in data[4]:
                self.rth += struct.pack('H', element)
        elif datatype == 'start':
            self.rth_fmt = '<2I2QI256s'
            self.rth = struct.pack(self.rth_fmt, 1200, 1200, 0, 0, 0, data[0])
        elif datatype == 'stop':
            self.rth_fmt = '<2I2Q'
            self.rth = struct.pack(self.rth_fmt, 1201, 1201, 0, 0)
        elif datatype == 'absorption':
            self.rth_fmt = '<f'
            recordtype = 7611
            self.rth = struct.pack(self.rth_fmt, data)
        elif datatype == 'spreading':
            self.rth_fmt = '<f'
            recordtype = 7612
            self.rth = struct.pack(self.rth_fmt, data)
        else:
            print 'Data type not found'
            self.rth = ()
        
        return recordtype, self.rth 
        
    def makeip(self,iptext):
        """Forms the 7P expected ip address format from text"""
        ipbyte = [struct.pack('B', int(i)) for i in iptext.split('.')]
        ipaddress = ipbyte[3] + ipbyte[2] + ipbyte[1] + ipbyte[0]
        ipaddress, = struct.unpack('I',ipaddress)
        return ipaddress
        
    def makepacket(self, datatype, data = ()):
        recordtype, rth = self.RecordType(datatype,data)
        if len(rth) > 0:
            drf = self.DataRecord(recordtype, rth)
            packet = self.NetFrame(drf)
        return packet

    def sendUDP(self, packet):
        """Send a UPD packet to the Reson 7P for this object."""
                # Create socket
        self.UDPSock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        if not (self.UDPSock.sendto(packet,self.addr)):
            print "UDP message not sent!"
        UDPPort = self.UDPSock.getsockname()[1]
        self.UDPSock.shutdown(socket.SHUT_RD)
        self.UDPSock.close()
        return UDPPort
            
    def catchUDP(self, port, filename = ''):
        """Opens a recieving UDP connection with the 7P on the specified port
        and logs the traffic to the specified filename."""
        self.outUDPSock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.outUDPSock.settimeout(1)
        self.outUDPSock.bind((self.ownip, port))
        if len(filename) > 0:
            self.outfile = open(filename,'wb')
            print 'Writing to filename ' + filename
            tofile = True
        else:
            tofile = False
            print "Catching data on port " + str(port)
            datain = {}
            self.newdata = False
            self.new7018 = False
            self.new7038 = False
        while not self.stopUDP:
            try:
                packet,addr = self.outUDPSock.recvfrom(self.buf)
                if tofile:
                    #self.outfile.write(packet[36:])
                    self.tracksettings(packet)
                else:
                    packetsize = len(packet)
                    if packetsize > 48:
                        headersize = struct.unpack('I', packet[12:16])[0]
                        datasize = struct.unpack('I', packet[44:48])[0] + 36
                        if datasize == headersize and datasize == packetsize:
                            type = struct.unpack('I', packet[68:72])[0]
                            if type == 7000:
                                self.dataout = datain
                                self.newdata = True
                                datain = {}
                            elif type == 7018:
                                print "yup"
                                self.data7018 = packet[36:]
                                self.new7018 = True
                            elif type == 7038:
                                self.data7038 = packet[36:]
                                self.new7038 = True
                            else:
                                datain[str(type)] = packet[36:]
            except socket.timeout:
                continue
        if tofile:
            self.outfile.close()
                
    def closeUDP(self):
        """Close the receiving UDP socket."""
        self.outUDPSock.close()
        
    def tracksettings(self, data):
        """Increments the object mesg type counter based on provided data"""
        mesg, = struct.unpack('I',data[68:72])
        if mesg == 7000:
            gain, = struct.unpack('f',data[162:166])
            if self.gain['level'] == gain:
                self.gain['count'] += 1
                n = str(self.gain['count'])
                numb = len(n)+1
                if self.gain['count']>1 and self.gain['count'] % 10 == 0:
                    numb = int(pl.log10(self.gain['count'])) + 1
                print numb * '\b' + n,
            else:
                self.gain['level'] = gain
                self.gain['count'] = 0

    def getsettings(self):
        """gets a 7000 record and records initial settings""" 
        packet = self.makepacket('singlerequest', 7503)
        data = self.sendTCP(packet, True)
        if data is not None:
            self.settings = struct.unpack(self.fmt7503, data[64:-4])
    
    def setfreq(self):
        """gets the system settings and sets the object's system
        enumerator to the correct value for the frequency."""
        self.getsettings()
        if self.settings[3] == 100000:
            self.enumerator = 0
        elif self.settings[3] == 200000:
            self.enumerator = 0
        elif self.settings[3] == 396000:
            self.enumerator = 1
        else:
            print "unknown frequency in use"
            
    def catchnewTCP(self, port):
        """Opens a TCP connection on the provided port to reviece reson data.
        Once a connection is established the incoming data packets are stored
        in a dictionary labeled with the record number.  A 7000 record is
        assumed to be a new ping, the old ping is moved to a class variable
        called 'dataout' and a flag 'newdata' is set to 'True'."""
        self.incomingsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.incomingsocket.bind(("", port))
        self.incomingsocket.listen(0)
        print "Standing by for recieve connections on port ", port
        self.stopTCP = False
        reson_socket, address = self.incomingsocket.accept()
        print "Recieve connection established from ", address
        datain = {}
        self.newdata = False
        self.new7018 = False
        self.new7038 = False
        while not self.stopTCP:
            packet = reson_socket.recv(self.buf)
            packetsize = len(packet)
            if packetsize > 48:
                headersize = struct.unpack('I', packet[12:16])[0]
                datasize = struct.unpack('I', packet[44:48])[0] + 36
                if datasize == headersize and datasize == packetsize:
                    type = struct.unpack('I', packet[68:72])[0]
                    if type == 7000:
                        self.dataout = datain
                        self.newdata = True
                        datain = {}
                        datain[str(type)] = packet[36:]
                    elif type == 7018:
                        self.data7018 = packet[36:]
                        self.new7018 = True
                    elif type == 7038:
                        self.data7038 = packet[36:]
                        self.new7038 = True
                    else:
                        datain[str(type)] = packet[36:]
                # else:
                    # print "size mismatch:"
                    # print headersize,
                    # print datasize,
                    # print packetsize
        reson_socket.shutdown(socket.SHUT_RDWR)
        reson_socket.close()
        
    def _catchTCP(self, port):
        """
        Catches TCP messages over the prescribed port and puts them in a local
        buffer.
        """
        datain = {}
        self.stopTCPdata = False
        self.newdata = False
        self.new7018 = False
        self.new7038 = False
        while not self.stopTCPdata:
            packet = self.s.recv(self.buf)
            packetsize = len(packet)
            if packetsize > 48:
                headersize = struct.unpack('I', packet[12:16])[0]
                datasize = struct.unpack('I', packet[44:48])[0] + 36
                if datasize == headersize and datasize == packetsize:
                    dtype = struct.unpack('I', packet[68:72])[0]
                    if dtype == 7000:
                        self.dataout = datain
                        self.newdata = True
                        datain = {}
                        datain[str(dtype)] = packet[36:]
                    elif dtype == 7018:
                        self.data7018 = packet[36:]
                        self.new7018 = True
                    elif dtype == 7038:
                        self.data7038 = packet[36:]
                        self.new7038 = True
                    elif dtype == 7501:
                        pass
                    elif dtype == 7502:
                        rectype = struct.unpack(self.drf_fmt,packet[36:36+64])[12]
                        print 'Record',
                        print str(rectype),
                        if rectype == 7500:
                            mesgtype = struct.unpack('<I', data[100:104])[0]
                            errortype = struct.unpack('<I', data[120:124])[0]
                            print 'of message type ' + str(mesgtype),
                            print 'had an error of type ' + str(errortype) + ' and',
                        print 'was not sent successfully'
                    else:
                        datain[str(dtype)] = packet[36:]
                    print dtype
            
    def sendTCP(self, packet, databack = False):
        """Open TCP connection with Reson 7P for this object."""
        if not self.__dict__.has_key('s'):
            self.openTCP()
        port = self.s.getsockname()[1]
        threading.Thread(target = self._catchTCP, args = (port,)).start()
        self.s.send(packet)
        if not databack:
            self.stopTCPdata
        
    def command7P(self, datatype, data = (), sendTCP = True):
        packet = self.makepacket(datatype,data)
        if sendTCP:
            if datatype == 'selfrecordrequest':
                self.sendTCP(packet, databack = True)
            else:
                self.sendTCP(packet)
            port = self.s.getsockname()[1]
        else:
            port = self.sendUDP(packet)
        return port
        
    def openTCP(self):
        """Opens a TCP connection to the object address."""
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect(self.addr)
        print 'Contacting ' + self.host + ' from ' + self.ownip + ' via TCP'
        self.stopTCPdata = True

    def closeTCP(self):
        self.stopTCPdata = True
        self.s.shutdown(socket.SHUT_RDWR)
        self.s.close()
        del self.s
        
def main():
    print """\nReson 7125 Calibration V-0.1 (for experimental use)\n"""
    
    filetime = datetime.now()
    outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_cal.s7k" \
        % {'year': filetime.year,
        'month': filetime.month,
        'day': filetime.day,
        'hour': filetime.hour,
        'minute': filetime.minute
        }
    print 'Writing to filename ' + outfilename
    print
    print 'Please adjust the range scale to be appropraite for the water depth and press "Enter":'
    temp = raw_input('>> ')
    
    print 'Please enter the ip address of the Reson machine: ',
    reson_address = raw_input('>> ')
    
    validsonar = False
    while not validsonar:
        print 'Please enter the multibeam type (7125 or 7111): ',
        device = int(raw_input('>> '))
        if device == 7111 or device == 7125:
            validsonar = True
        else:
            print 'invalid sonar type'
            
    print 'Please enter the ip address of this machine: ',
    this_address = raw_input('>> ')
    
    # Set range of values for calibration and initialize setting on 7P
    reson = com7P(reson_address, device, this_address)
    reson.getsettings()
    freq = reson.settings[3] / 1000
    reson.command7P('absorption', 0)
    reson.command7P('spreading', 0)
    if device == 7125:
        gainrange = xrange(0, 84, 3)
        powerrange = xrange(190, 221, 5)
        reson.command7P('pulse', 0.000100)
        reson.command7P('power', 190)
        reson.command7P('gain', 0)
        reson.command7P('pingrate', 10)
    elif device == 7111:
        gainrange = xrange(0, 83, 3)
        powerrange = xrange(175, 231, 5)
        reson.command7P('pulse', 0.000200)
        reson.command7P('power', 175)
        reson.command7P('gain', 10)
        reson.command7P('pingrate', 20)
        
    filetime = datetime.now()
    outfilename = "%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d_%(freq)03dkHz_cal.s7k" \
        % {'year': filetime.year,
        'month': filetime.month,
        'day': filetime.day,
        'hour': filetime.hour,
        'minute': filetime.minute,
        'freq': freq
        }
    print 'Writing to filename ' + outfilename
    print

    numsnippets = 15
    numpings = 15
    reson.command7P('snippetwindow', (1, numsnippets)) # Set snippet window
    print 'Discharging the sonar projector capacitors, please wait',
    wait  = 8 #seconds
    for i in xrange(wait):
        time.sleep(1)
        print '.',
       # Open UDP socket for data flow
    reson.stopUDP = False
    
    # Begin sending (and recording) data and adjusting settings
    dataport = reson.command7P('selfrecordrequest',(4, 7000, 7006, 7008, 7027), sendTCP = False)
    threading.Thread(target = reson.catchUDP, args = (dataport,outfilename)).start()
    print 'beginning calibration'

    for power in powerrange:
        reson.command7P('power', power)
        for gain in gainrange:
            reson.command7P('gain',gain)
            while reson.gain['count'] >= numpings:
                reson.gain['count'] = 0
                continue
            while reson.gain['count'] < numpings:
                continue
    
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
    reson.command7P('snippetwindow', (0, 50)) # Turn off snippet window
    reson.closeTCP()

    # Reset 7P settings
    reson.command7P('absorption', reson.settings[34])
    reson.command7P('spreading', reson.settings[36])
    reson.command7P('snippetwindow', (0, 50)) # Turn off snippet window
        
if __name__ == '__main__':
    main()
        