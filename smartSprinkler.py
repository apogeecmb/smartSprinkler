import time # time module
import datetime
import json
import math
from enum import IntEnum
from astral import Location
from exceptions import ModuleException, BasicException

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
        
        try:
            self.loadConfig(settings)
        except Exception as err:
            raise err

    def loadConfig(self, settings):
        self.update(settings)

        # Location
        self['location'] = {'lat': self['location'][0], 'lon': self['location'][1], 'zipcode': self['location'][2], 'timezone': self['location'][3]}

        # Check config
        if ("pws" in self): # Validate PWS config
            try:
                blah
                if (self["pws"]["type"].lower() == "weewx"): # weeWX PWS
                    from weewxInterface import WeeWXInterface
                    self.pws = WeeWXInterface(self["pws"]["weatherDbFile"])
                else:
                    self.pws = None
            except Exception as e:
                message = "SmartSprinklerConfig - Error experienced while loading PWS information, of type " + type(e).__name__
                raise ModuleException(message, e, None)
        else:
            self.pws = None

        if ("sprinklerInterface" in self): # Validate sprinkler interface config
            try:
                if (self["sprinklerInterface"]["type"].lower() == "ospi"): # OSPi
                    from openSprinklerInterface import OSPiInterface
                    self.sprinklerInterface = OSPiInterface(self["sprinklerInterface"]["url"], len(self["zones"]), self["sprinklerInterface"]["pw"])
                else:
                    self.sprinklerInterface = None
            except Exception as e:
                message = "SmartSprinklerConfig - Error experienced while loading sprinkler interface information, of type " + type(e).__name__
                raise ModuleException(message, e, None)
        else:
            self.sprinklerInterface = None
        
        if ("weatherPredict" in self): # Validate weather predict config
            try:
                if (self["weatherPredict"]["type"].lower() == "wunderground"): # Wunderground
                    from wundergroundPredict import WundergroundPredict
                    self.weatherPredict = WundergroundPredict(self["weatherPredict"]["url"])
                elif (self["weatherPredict"]["type"].lower() == "nws"): # National Weather Service
                    from nwsPredict import NWSPredict
                    self.weatherPredict = NWSPredict()
                else:
                    self.weatherPredict = None
            except Exception as e:
                message = "SmartSprinklerConfig - Error experienced while loading weather predict interface information, of type " + type(e).__name__
                raise ModuleException(message, e, None)
        else:
            self.weatherPredict = None

        if ("reportInterface" in self): # Validate report interface config
            try:
                if (self["reportInterface"]["type"].lower() == "ifttt"): # IFTTT reporting
                    from iftttInterface import IFTTTInterface
                    self.reportInt = IFTTTInterface(self["reportInterface"]["key"])
                else:
                    self.reportInt = None
            except Exception as e:
                message = "SmartSprinklerConfig - Error experienced while loading report interface interface information, of type " + type(e).__name__
                raise ModuleException(message, e, None)
        else:
            self.reportInt = None


def calculateSunRiseAndSet(location):
    # Create location
    loc = Location(('Home', 'Alabama', location['lat'], location['lon'], location['timezone'], 0))
    sun = loc.sun()

    # Convert datetime to seconds of day
    now = datetime.datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sunrise = (sun['sunrise'].replace(tzinfo=None) - midnight).seconds
    sunset = (sun['sunset'].replace(tzinfo=None) - midnight).seconds
 
    return sunrise, sunset

class SmartSprinkler(object):
    def __init__(self, configSettings):
        self.config = SmartSprinklerConfig(configSettings)

    def runSprinklerLogic(self, sprinklerLog):
        nonFatalException = None    

        weeklyWaterReq = self.config['weeklyWaterReq']
    
        # Determine important times (does not account for DST)
        currentTime = int(time.time()) # UTC time in linux epoch
        epochTimeMidnight = (currentTime - (currentTime - time.altzone)%86400) # epoch time of midnight (correcting for timezone)
        currentDayOfWeek = int(time.strftime("%w")) # day of week 
        epochTimeBeginWeek = epochTimeMidnight - currentDayOfWeek*86400 # start week on Sunday
        epochTimeEndWeek = epochTimeBeginWeek+86400*7 - 30 # subtraction ensures end time is part of same week
        lastDayOfWeek = epochTimeEndWeek - 86400 # start of last day of week
        epochTimeMidWeek = epochTimeBeginWeek + (epochTimeEndWeek - epochTimeBeginWeek)/2.0
        startLastWeek = epochTimeBeginWeek-7*86400

        ### Get watering/rain statistics
        # Calculate total rain this week and last
        if (self.config.pws):
            # Get rainfall total this week
            rainfall, lastTimeOfRain = self.config.pws.getRainfall(epochTimeBeginWeek, epochTimeEndWeek, self.config['minRainAmount'])
            # Get rainfall total for previous week 
            lastWeekRain, timeRainLastWeek = self.config.pws.getRainfall(startLastWeek, epochTimeBeginWeek, self.config['minRainAmount'])
        else:
            rainfall = 0.0
            lastTimeOfRain = 0.0
            lastWeekRain = 0.0
            timeRainLastWeek = 0.0
        
        print("Rainfall this week: ", rainfall, lastTimeOfRain)

        if (rainfall < 0.0):
            rainfall = 0.0

        # Calculate sprinkler time this week
        if (self.config.sprinklerInterface):
            #syslog.syslog("sprinkler total lookup time:" + str(epochTimeBeginWeek))
            sprinklerTable = self.config.sprinklerInterface.getSprinklerTotals(self.config['sprinklerLogFile'],self.config['zones'],epochTimeBeginWeek, log=sprinklerLog)
            lastSprinklerTable = self.config.sprinklerInterface.getSprinklerTotals(self.config['sprinklerLogFile'],self.config['zones'],startLastWeek,epochTimeBeginWeek, log=sprinklerLog)
        else:
            sprinklerTable = dict()
            for zone in zones:
                sprinklerTable.update({zone: {'totalRunTime': 0, 'lastRunTime': 0}})  
            lastSprinklerTable = sprinklerTable

        # Total water by zone (rainfall and sprinklers)
        totalWater = [rainfall + sprinklerTable[self.config['zones'][i]]['totalRunTime']/60.0*self.config['zoneWateringRate'][i] for i in range(len(self.config['zones']))]
    
        # Check for time since last rain or water
        if (timeRainLastWeek > lastTimeOfRain): # no rain this week, but rained last 
            lastTimeOfRain = timeRainLastWeek
    
        totalWaterLastWeek = [lastSprinklerTable[self.config['zones'][i]]['totalRunTime']/60.0*self.config['zoneWateringRate'][i] + lastWeekRain for i in range(len(self.config['zones']))] # total water last week by zone

        # Add past week excess water to this week's total
        if (self.config['excessRollover']):  
            for i in range(len(totalWaterLastWeek)):
                if totalWaterLastWeek[i] > weeklyWaterReq[i]: # check for excess amount
                    totalWater[i] += totalWaterLastWeek[i] - weeklyWaterReq[i]
    
        print("Total water this week:", totalWater)

        # Calculate last day of rain or water
        lastTimeWater = [max(lastTimeOfRain,sprinklerTable[zone]['lastRunTime'],lastSprinklerTable[zone]['lastRunTime']) for zone in sprinklerTable]
    
        ### Update watering times
        wateringLength = [0]*len(self.config['zones'])
        nextDayToWater = [0]*len(self.config['zones'])
        status = [SSStatus.Requirement_Met]*len(self.config['zones'])
        runData = []
    
        # Check weather forecast 
        precipProb = []
        if (self.config.weatherPredict):
            try:    
                precipProb = self.config.weatherPredict.getPrecipProb(currentTime, epochTimeEndWeek, self.config['location']['zipcode'])
            except BasicException as err:
                nonFatalException = err # store exception and continue    
            except ModuleException as err:
                raise err
        
        for zone in range(len(self.config['zones'])):
            runNow = False
            if (currentTime > lastDayOfWeek): # last day of week so force sprinkler run
                runNow = True

            nextDayToWater[zone], amountToWater, status[zone], runTime = self.getWateringUpdate(zone, totalWater[zone], lastTimeWater[zone], weeklyWaterReq[zone], self.config, epochTimeBeginWeek, epochTimeEndWeek, runNow, precipProb)
    
            if amountToWater > 0: # need to run sprinklers in this zone
                ## Determine run time
                wateringLength[zone] = amountToWater/self.config['zoneWateringRate'][zone]*60.0 # requested length (seconds)
                # Do bounds checking
                wateringLength[zone] = max(wateringLength[zone], self.config['minWateringLength'][zone]) # lower bound
                wateringLength[zone] = min(wateringLength[zone], self.config['maxWateringLength'][zone]) # upper bound
                wateringLength[zone] = int(math.ceil(wateringLength[zone]/60.0)*60.0) # nearest minute in seconds
            
                # Store run time data
                runData.append([runTime, self.config['zones'][zone], wateringLength[zone]]) 
            else: # disable zone program    
                if (self.config.sprinklerInterface):
                    self.config.sprinklerInterface.disableProgram(self.config['zones'][zone])

        print("Watering lengths: " + str(wateringLength))

        # Modify sprinkler programs 
        logTime = 0
        if any(length > 0 for length in wateringLength): # Watering required by at least one zone
            # Sort by run times
            sortedRuns = sorted(runData, key=lambda tup: tup[0])    
            print(sortedRuns)
            # Check for run time conflicts
            for i in range(1,len(sortedRuns)):
                for j in range(0,i):
                    if sortedRuns[i][0] == sortedRuns[j][0]: # same run start time so increment
                        sortedRuns[i][0] = sortedRuns[j][0] + sortedRuns[j][2]
                    elif sortedRuns[i][0] > sortedRuns[j][0] and sortedRuns[i][0] < (sortedRuns[j][0] + sortedRuns[j][2]): # scheduled to start while other station running
                        sortedRuns[i][0] = sortedRuns[j][0] + sortedRuns[j][2]

            # Update programs
            if (self.config.sprinklerInterface):
                for run in sortedRuns:
                    self.config.sprinklerInterface.updateProgram(run[1], run[2], run[0])
        
        else: # No watering required - disable all programs
            if (self.config.sprinklerInterface):
                for i in range(len(self.config['zones'])):
                    self.config.sprinklerInterface.disableProgram(self.config['zones'][i])

        # Log execution data
        logEntry = self.logStatus(self.config['logFile'], self.config['statusFile'], status, runData, totalWater, lastTimeWater)
        
        # Report status
        if (self.config.reportInt):
            print(logEntry)
            if (nonFatalException): # exception occurred during execution
                exceptionStr = nonFatalException.message
            else:
                exceptionStr = 'No exceptions occurred.'
            self.config.reportInt.post({'name': "smartSprinkler_status", 'data': [logEntry, exceptionStr]})

    def determineRunTime(self, desiredRunTimes, runDayEpoch, settings, timeChoice='first'):
        # Input desiredRunTimes are assumed to be monotonically increasing
        epochTimeMidnight = int(runDayEpoch)
        currentTime = time.time()
    
        for rtime in desiredRunTimes:
            timeEntries = rtime.split()
            if (len(timeEntries) == 2): # relative time
                # Calculate offset
                offsetSign = timeEntries[1][0] # negative or positive offset
                offset = timeEntries[1][1:].split(":")
                offset = int(offsetSign + str(int(offset[0])*60*60 + int(offset[1])*60))
            
                # Calculate sunset and sunrise times
                sunrise, sunset = calculateSunRiseAndSet(settings['location'])

                # Apply offset to base
                if (timeEntries[0] == 'sunrise'):
                    # Add offset to sunrise time
                    timeOfDaySec = sunrise + offset
                elif (timeEntries[0] == 'sunset'):
                    # Add offset to sunset time
                    timeOfDaySec = sunset + offset
                else: # invalid base
                    # TODO - raise exception
                    print("Invalid time offset base")
                    continue # just skip this time for now
        
            else: # absolute time
                timeOfDay = rtime.split(":")
                timeOfDaySec = int(timeOfDay[0])*60*60 + int(timeOfDay[1])*60
    
            # Check if time has already passed 
            if (currentTime < (epochTimeMidnight + timeOfDaySec)): # can run at this time
                runTime = epochTimeMidnight + timeOfDaySec
                if (timeChoice == 'first'): # looking for first valid run time
                    break

        if not runTime: # desired times already passed
            # Run tomorrow
            timeOfDay = desiredRunTimes[0].split(":")
            timeOfDaySec = int(timeOfDay[0])*60*60 + int(timeOfDay[1])*60
            runTime = epochTimeMidnight + 86400 + timeOfDaySec

        return int(runTime)

    def getWateringUpdate(self, zone, amountOfWater, lastTimeWater, weeklyWaterReq, config, startTime, endTime, runNow, precipProb): 
        """Calculate watering needs based on water to date and predicted weather."""

        ## Calculate next watering day
        nextDayToWater = -1
        amountToWater = -1
        status = SSStatus.Requirement_Met
        runTime = -1
        timeChoice = 'first'

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
                timeChoice = 'last' # use last available run time of day for forced runs
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
                runTime = self.determineRunTime(config['desiredRunTimeOfDay'], nextDayToWater, config, timeChoice)

        return nextDayToWater, amountToWater, status, runTime

    def logStatus(self, logfile, statusfile, status, runData, totalWater, lastTimeWater):
        timestamp = time.strftime("%H:%M:%S %m-%d-%Y")
    
        # Log to cumulative log file
        try:
            with open(logfile, "a") as f:
                # Format data for log entry
                statusOut = []
                for zone in status:
                    statusOut.append(str(zone))
                runDataOut = []
                for zone in runData:
                    timeStr = time.strftime("%H:%M:%S %m-%d-%Y", time.localtime(zone[0]))
                    runDataOut.append([timeStr, zone[1], zone[2]])

                # Write entry to log
                logEntry = timestamp + " - " + "Status: " + str(statusOut) + ", Scheduled runs (start time, program number, zone, length): " + str(runDataOut) + ", Total water: " + str(totalWater) + ", Last time water: " + str(lastTimeWater)
                f.write("\n" + logEntry)
                return logEntry
        except:
            return None
    
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
    
