import time # time module
import json
from enum import IntEnum

class SSStatus(IntEnum):
    Requirement_Met = 0
    Watering = 1
    Reduced_Watering = 2
    Delayed = 3
    Delayed_Half_Met = 4 
    Unavailable = 5
    Forced_Run = 6

class SmartSprinklerConfig(dict):
    def __init__(self, settings):
        self.loadConfig(settings)


    def loadConfig(self, settings):
        self.update(settings)

        # Check config
        if ("pws" in self): # Validate PWS config
            try:
                if (self["pws"]["type"].lower() == "weewx"): # weeWX PWS
                    from weewxInterface import WeeWXInterface
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
                    from openSprinklerInterface import OSPiInterface
                    self.sprinklerInterface = OSPiInterface(self["sprinklerInterface"]["url"], len(self["zones"]), self["sprinklerInterface"]["pw"])
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
                    from wundergroundPredict import WundergroundPredict
                    self.weatherPredict = WundergroundPredict(self["weatherPredict"]["url"])
                elif (self["weatherPredict"]["type"].lower() == "nws"): # National Weather Service
                    from nwsPredict import NWSPredict
                    self.weatherPredict = NWSPredict(self["weatherPredict"]["url"])
                else:
                    self.weatherPredict = None
            except:
                print("Error experienced while loading weather predict information")
                raise
        else:
            self.weatherPredict = None

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
    
