from sprinklerInterface import SprinklerInterface
import time
from datetime import datetime
import requests
import hashlib
from exceptions import ModuleException, BasicException

class OSPiInterface(SprinklerInterface):
    # Interface to OpenSprinkler per Firmware 2.1.8 API (May 25, 2018)
    # https://openthings.freshdesk.com/support/solutions/articles/5000716363-os-api-documents

    def __init__(self, path, numZones, pw):
        super().__init__(path, numZones, [])

        # Store password for api calls
        self.pw = hashlib.md5(pw.encode('utf-8')).hexdigest() 

        # Sprinkler program settings
        self.programFlag = 65 # enabled, weekday program schedule, fixed start time

    def getSprinklerTotals(self, zones, startTime, endTime):
        # Initialize output
        runTimes = dict()
        for zone in zones:
            runTimes.update({zone: {'totalRunTime': 0, 'lastRunTime': 0}})  
   
        # Retrieve log from OSPi
        log_r = requests.get(self.path + "jl", params = {'pw': self.pw, 'start': str(int(datetime.timestamp(startTime))), 'end': str(int(datetime.timestamp(endTime)))})
        # TODO put in result processing based on API information - need to check if json response or requested array of log times
        logEntries = log_r.json()
        
        # Parse and format log entries
        try: # check for result code
            if ('result' in logEntries):
                if (logEntries['result'] == 17): # date is out of range
                    raise ModuleException("OSPIInterface - Date range is not valid. Provided start time/end time: {}, {}".format(startTime, endTime), None, None) 
        except ModuleException as e:
            raise e
        except Exception as e:
            pass
        
        for entry in logEntries:
            try:
                if (entry[0] == 0): # special event record, not a run log
                    continue
                zone = entry[1] + 1
                if zone in zones: # Compile zone stats
                    duration = entry[2]     
                    runTimes[zone]['totalRunTime'] += duration
                    if entry[3] > runTimes[zone]['lastRunTime']: # zone run more recent last stored
                        runTimes[zone]['lastRunTime'] = entry[3]
            except TypeError as e:
                # Get traceback
                import traceback
                tb = traceback.format_exc()

                message = "OSPIInterface - An error occurred of type " + type(e).__name__ + " " + str(log_r.text) + " " + str(startTime) + " " + str(endTime)
                raise ModuleException(message, e, tb)
                
        return runTimes             
    
    def updateProgram(self, zoneNum, durationSec, runTimeEpoch):
        # Determine day of week
        dayOfWeek = int(time.strftime("%w", time.localtime(runTimeEpoch)))
        if dayOfWeek == 0: # Sunday (end of week for OSPi)
            dayOfWeek = 7
        days0 = 2**(dayOfWeek-1) # days0 byte

        # Start time (convert epoch to time of day in minutes)
        startTime = int((runTimeEpoch - (runTimeEpoch - (runTimeEpoch - time.altzone)%86400)) / 60)
    
        # Program settings
        zoneId = self.getZoneId(zoneNum)
        zones = [int(0)] * self.numZones
        zones[zoneNum-1] = durationSec # duration of zone to run
        progSettings = str([self.programFlag, days0, 0, [startTime, -1, -1, -1], zones]).replace(" ", "") 

        # Issue program change call to OpenSprinkler using HTTP API
        r_changeProgram = requests.get(self.path + "cp", params = {'pid': str(zoneId), 'name': "Zone" + str(zoneNum), 'pw': self.pw, 'v': progSettings})
        #print(r_changeProgram)

    def disableProgram(self, zoneNum):
        zoneId = self.getZoneId(zoneNum) 
        
        progSettings = str([self.programFlag-1, 1, 0, [0, -1, -1, -1], [int(0)]*self.numZones]).replace(" ", "") 
        try:
            r_disableProgram = requests.get(self.path + "cp", params = {'pid': str(zoneId), 'name': "Zone" + str(zoneNum), 'pw': self.pw, 'v': progSettings})
        except ConnectionError as e:
            import traceback
            tb = traceback.format_exc()

            message = "OSPIInterface - An error occurred of type " + type(e).__name__ + " " + str(log_r.text) + " " + str(startTime) + " " + str(endTime)
            raise ModuleException(message, e, tb)
        
    def getZoneId(self, zoneNum):
        return zoneNum-1

