import sqlite3 # sqlite3 module
import time # time module
from urllib import urlopen
import json
import ast
import syslog
from enum import IntEnum
from subprocess import call

class SSStatus(IntEnum):
    Requirement_Met = 0
    Watering = 1
    Reduced_Watering = 2
    Delayed = 3
    Delayed_Half_Met = 4 
    Unavailable = 5
    Forced_Run = 6

url = "http://127.0.0.1:9000/cp?pw=ospi"

class SmartSprinklerConfig(dict):
    def __init__(self, settings):
        self.loadConfig(settings)


    def loadConfig(self, settings):
        self.update(settings)

        # Check config
        if ("pws" in self): # Validate PWS config
            try:
                if (self["pws"]["type"].lower() == "weewx"): # weeWX PWS
                    self.pws = WeeWXInterface(self["pws"]["weatherDbFile"])
                else:
                    self.pws = None
            except:
                print("Error experienced while loading PWS information")
                raise
        else:
            self.pws = None

        if ("sprinklerInterface" in self): # Validate sprinkler interface config
            try:
                if (self["sprinklerInterface"]["type"].lower() == "ospi"): # OSPi
                    self.sprinklerInterface = OSPiInterface(self["sprinklerInterface"]["url"])
                else:
                    self.sprinklerInterface = None
            except:
                print("Error experienced while loading sprinkler interface information")
                raise
        else:
            self.sprinklerInterface = None
        
        if ("weatherPredict" in self): # Validate weather predict config
            try:
                if (self["weatherPredict"]["type"].lower() == "wunderground"): # Wunderground
                    self.weatherPredict = WundergroundPredict(self["weatherPredict"]["url"])
                else:
                    self.weatherPredict = None
            except:
                print("Error experienced while loading weather predict information")
                raise
        else:
            self.weatherPredict = None

            

class PWSInterface:
    def __init__(self, path):
        self.path = path

    def getRainfall(self, startTime, endTime, minRainAmount):
    # Calculates total rainfall between start and end times
    # Inputs:
    # startTime- start time of period to extract from database
    # endTime- end time of period to extract from database
    # 
    # Outputs:
    # rainfall- total rainfall between start and end times

        return -1.0, 0

class WeeWXInterface(PWSInterface):
    
    def getRainfall(self, startTime, endTime, minRainAmount):
        rainfall = 0.0
        lastDayOfRain = 0

        # Open connection to stats database
        conn = sqlite3.connect(self.path) 

        c = conn.cursor() # cursor to operate on database

        # Get rainfall table from database
        #c.execute('SELECT * FROM rain')
        c.execute('SELECT * FROM archive_day_rain WHERE dateTime BETWEEN ? AND ?', (startTime, endTime))

        rainTable = c.fetchall()

        # Compute total rainfall between start and end times
        #for i in range(startIndex, endIndex + 1):
        for i in range(len(rainTable)):
            if rainTable[i][5] > 0:
                rainfall += rainTable[i][5]
                if rainTable[i][5] > minRainAmount: # minimum rain amount to count as "rain day"
                    lastDayOfRain = rainTable[i][0]

        conn.close()
        
        
        return rainfall, lastDayOfRain 

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
        zoneId = getZoneId(zoneNum) 
        os_cmd = self.path + "&pid=" + str(zoneNum-1) + "&v=[0, 0, 0, 0, 0, 0, 0, " + str(zoneId) + "]&name=SmartSprinklerZone" + str(zoneNum)
        f = urlopen(os_cmd)
            
class WeatherPredict:
    def __init__(self, path):
        self.path = path

    def getPrecipProb(self, startTime, endTime, location):
        return []

class WundergroundPredict(WeatherPredict):
    def getPrecipProb(self, startTime, endTime, location):
    # Get precipitation probability for desired period
    # Inputs:
    # startTime- start time of interval to check for chance of precipitation
    # endTime- end time of interval to check for chance of precipitation
    # location- location to check for chance of precipitation
    #
    # Outputs:
    # precipProb- array of epoch time and and chance of precipitation for every day between start and end times

        try:
            f = urlopen(self.path + str(location) + '.json')
        except: # failed to get weather forecast
            return [] 

        # Parse json
        json_string = f.read()
        parsed_json = json.loads(json_string)
        forecast = parsed_json['forecast']['simpleforecast']['forecastday']

        # Get precipitation probabilities in desired time range
        precipProb = []
        for i in range(len(forecast)):
            if int(forecast[i]['date']['epoch']) > startTime:
                if int(forecast[i]['date']['epoch']) < endTime:
                    precipProb.append([int(forecast[i]['date']['epoch']),forecast[i]['pop']])
                    #print i, forecast[i]['date']['epoch'] 
                else: 
                    return precipProb
        
        return precipProb

def determineRunTime(desiredRunTimes, runDayEpoch):
    epochTimeMidnight = int(runDayEpoch)
    currentTime = time.time()
    
    runTime = []
    for rtime in desiredRunTimes:
        timeOfDay = rtime.split(":")
        timeOfDaySec = int(timeOfDay[0])*60*60 + int(timeOfDay[1])*60
    
        if currentTime < (epochTimeMidnight + timeOfDaySec): # can run at this time     
            runTime = epochTimeMidnight + timeOfDaySec
            break

    if not runTime: # desired times already passed
        # Run tomorrow
        timeOfDay = desiredRunTimes[0].split(":")
        timeOfDaySec = int(timeOfDay[0])*60*60 + int(timeOfDay[1])*60
        runTime = epochTimeMidnight + 86400 + timeOfDaySec

    return int(runTime)

# Schedule next watering day
def scheduleWateringDay(totalRain, weeklyWaterReq):
# Inputs:
# weeklyWaterReq- amount of water required during week
# totalRain- total rain already this week
   return 1

   
def getWateringUpdate(zone, amountOfWater, lastTimeWater, weeklyWaterReq, config, startTime, endTime, runNow, precipProb): 
# Calculate watering needs based on water to date and predicted weather

    ## Calculate next watering day
    nextDayToWater = -1
    amountToWater = -1
    status = SSStatus.Requirement_Met
    runTime = -1

    # Check if water requirement met
    if amountOfWater > 0.9*weeklyWaterReq: # within 10% of requirement
        print("Water requirement met.")
    else:
        print("Water requirement not met. Determining next day to water.")
   
        # Get precipitation forecast (for remainder of week)
        #precipProb = getPrecipProb(startTime, endTime, config['location'])
   
        # Find days where precipitation probability is greater than config['minPrecipProb']
        daysOfRain = []
        for i in range(len(precipProb)):
            if precipProb[i][1] >= config['minPrecipProb']:
                daysOfRain.append(precipProb[i])
        print("Days of rain:", daysOfRain)

        running = False
        if (runNow):
            print("Run now override for zone:", zone)
            waterTime = time.time()
            nextDayToWater = waterTime - (waterTime - time.altzone)%86400 # midnight of day to water
            amountToWater = weeklyWaterReq - amountOfWater
            status = SSStatus.Forced_Run
            running = True
        elif len(daysOfRain) > 0: # Rain predicted
            print("Rain predicted")
            if (daysOfRain[0][0] - lastTimeWater) <= config['maxDaysBetweenWater']*86400:  # Delay watering
                print("Delaying watering because rain is predicted before the maximum allowable days without water is exceeded.")
                status = SSStatus.Delayed
            else: # Predicted rain too long from now so water (exceeds max days between water)
                if amountOfWater >= 0.5*weeklyWaterReq: # at least half of weekly water requirement received so go ahead and delay
                    print("Half of weekly water requirement already met so wait for rain.")
                    status = SSStatus.Delayed_Half_Met
                else:  # water a reduced amount in case of rain
                    print("Watering a reduced amount in case of rain")
                    waterTime = min(endTime, lastTimeWater + config['maxDaysBetweenWater']*86400) 
                    if (waterTime < time.time()): # check for watering times in the past
                        waterTime = time.time() 
                    nextDayToWater = waterTime - (waterTime - time.altzone)%86400 # midnight of day to water
                    amountToWater = 0.5*(weeklyWaterReq - amountOfWater) # water half of remaining weekly requirement
                    status = SSStatus.Reduced_Watering
                    running = True
        else: # Rain not predicted so run sprinklers
            print("Rain not predicted")
            waterTime = min(endTime, lastTimeWater + config['maxDaysBetweenWater']*86400)  
            
            # Check for watering times in the past
            if (waterTime < time.time()):
                waterTime = time.time()

            nextDayToWater = waterTime - (waterTime - time.altzone)%86400 # midnight of day to water
            amountToWater = weeklyWaterReq - amountOfWater
            status = SSStatus.Watering
            running = True

        if (running): # determine run time
            runTime = determineRunTime(config['desiredRunTimeOfDay'], nextDayToWater)

    return nextDayToWater, amountToWater, status, runTime

def getZoneId(zoneNum):
    zoneId = 2**(zoneNum-1)
    return zoneId


def logStatus(logfile, statusfile, status, runData, totalWater, lastTimeWater):
    timestamp = time.strftime("%H:%M:%S %m-%d-%Y")
    
    # Log to cumulative log file
    try:
        with open(logfile, "a") as f:
            f.write("\n" + timestamp + " - " + "Status: " + str(status) + ", Scheduled runs (start time, program number, zone, length): " + str(runData) + ", Total water: " + str(totalWater) + ", Last time water: " + str(lastTimeWater))
    except:
        pass    
    
    # Log to current status file
    try:
        with open(statusfile, "w") as f:
            statusOut = []
            for entry in status:
                print(entry)
                statusOut.append(int(entry))
            currentStatus = {"timestamp": timestamp, "status": statusOut, "totalWater": totalWater, "lastTimeWater": lastTimeWater, "lastRun": timestamp}
            print(currentStatus)
            json.dump(currentStatus, f)         
    except:
        pass    
    
