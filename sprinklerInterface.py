import time # time module
from urllib import urlopen
import ast
import syslog
from subprocess import call

class SprinklerInterface:
    def __init__(self, path):
        self.path = path
        pass

    def getSprinklerTotals(logFile, zones, startTime, endTime=time.time(), log=[]):
        pass
    
    def updateProgram(self, zoneNum, durationSec, runTimeEpoch):
        pass

    def disableProgram(self, zoneNum):
        pass

class OSPiInterface(SprinklerInterface):
    
    def getSprinklerTotals(self, logFile, zones, startTime, endTime=time.time(), log=[]):
    
        runTimes = dict()
        zoneStatus = dict()
        for zone in zones:
            runTimes.update({zone: {'totalRunTime': 0, 'lastRunTime': 0}})  
            zoneStatus.update({zone: {'status': 0, 'startTime': -1}})
    
        call(["cp", logFile, "/home/pi/tempLog"])
        #if (log):
        #   logEntries = log
        #else:
        with open("/home/pi/tempLog",'r') as f1:
            logEntries = f1.readlines()
        with open("/home/pi/outLog" + str(time.time()),'w') as f2:  
            for i in range(len(logEntries)):
                line = logEntries[i]
                #entry = ast.literal_eval(line)
                if type(line) is str:
                    line = ast.literal_eval(line)
                timestamp = line['date'] + " " + line['start']
                timestamp_epoch = time.mktime(time.strptime(timestamp, "%Y-%m-%d %H:%M:%S"))
                f2.write(str(line) + "\n")
                f2.write(str(timestamp_epoch) + " " + str(startTime) + " " + str(endTime) + "\n")
                if (timestamp_epoch > startTime and timestamp_epoch < endTime): # within desired period
                    zone = line['station'] + 1
                    if zone in zones: # 
                        duration = line['duration'].split(":")
                        duration = int(duration[0])*60 + int(duration[1])
                        runTimes[zone]['totalRunTime'] += duration
                        f2.write(str(zone) + " " + timestamp + " " + str(duration) + "\n")
                        if timestamp_epoch > runTimes[zone]['lastRunTime']: # later run time
                            runTimes[zone]['lastRunTime'] = timestamp_epoch

        syslog.syslog("runTimes: " + str(runTimes))
        return runTimes

    def updateProgram(self, zoneNum, durationSec, runTimeEpoch):
        # Determine day of week
        dayOfWeek = int(time.strftime("%w", time.localtime(runTimeEpoch)))
        if dayOfWeek == 0: # Sunday (end of week for OSPi)
            dayOfWeek = 7
        days0 = 2**(dayOfWeek-1) # days0 byte
        # Start time (convert epoch to time of day in minutes)  
        startTime = int((runTimeEpoch - (runTimeEpoch - (runTimeEpoch - time.altzone)%86400)) / 60)

        zoneId = getZoneId(zoneNum)
        durationMin = durationSec / 60
    
        os_cmd = self.path + "&pid=" + str(zoneNum-1) + "&v=[1, " + str(days0) + ", 0, " + str(startTime) + ", " + str(startTime + durationMin) + ", " + str(durationMin) + ", " + str(durationSec) + ", " + str(zoneId) + "]&name=SmartSprinklerZone" + str(zoneNum)
        f = urlopen(os_cmd)

    def disableProgram(self, zoneNum):
        zoneId = self.getZoneId(zoneNum) 
        os_cmd = self.path + "&pid=" + str(zoneNum-1) + "&v=[0, 0, 0, 0, 0, 0, 0, " + str(zoneId) + "]&name=SmartSprinklerZone" + str(zoneNum)
        f = urlopen(os_cmd)
            
    def getZoneId(self, zoneNum):
        zoneId = 2**(zoneNum-1)
        return zoneId

