import time # time module
import datetime
import json
import math
import copy
from enum import IntEnum
from astral import LocationInfo
import astral.sun
from exceptions import ModuleException, BasicException

class SSStatus(IntEnum):
    Requirement_Met = 0
    Watering = 1
    Reduced_Watering = 2
    Delayed = 3
    Delayed_Half_Met = 4 
    Unavailable = 5
    Forced_Run = 6

class ReportEnable(IntEnum):
    Disable = 0
    ErrorOnly = 1
    ErrorAndStatus = 2

class SmartSprinklerConfig(dict):
    def __init__(self, settings, sprinklerLog):
        
        try:
            self.loadConfig(settings, sprinklerLog)
        except Exception as err:
            raise err

    def loadConfig(self, settings, sprinklerLog):
        self.update(settings)

        # Location
        self['location'] = {'lat': self['location'][0], 'lon': self['location'][1], 'zipcode': self['location'][2], 'timezone': self['location'][3]}

        # Generate zone by zone config
        overrides = self['overrides'] if 'overrides' in self else None
        self.loadZoneConfig(overrides)

        # Check config
        if ("pws" in self): # Validate PWS config
            try:
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

    def loadZoneConfig(self, overrides):
        # Create zone-specific configuration 
        self.zoneConfig = dict()
        for idx, zone in enumerate(self['zones']):
            self.zoneConfig[zone] = {'zoneWateringRate': self['zoneWateringRate'][idx], 'weeklyWaterReq': self['weeklyWaterReq'][idx],
                'minWateringLength': self['minWateringLength'][idx], 'maxWateringLength': self['maxWateringLength'][idx]}
            if (overrides and zone in overrides):
                self.zoneConfig[zone]['overrides'] = overrides[zone]

def calculateSunRiseAndSet(location):
    # Create location
    loc = LocationInfo(('name', 'region', location['lat'], location['lon'], location['timezone'], 0))

    now = datetime.datetime.now()
    #sun = loc.sun()
    sun = astral.sun.sun(loc.observer, date=datetime.date.today())  
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sunrise = (sun['sunrise'].replace(tzinfo=None) - midnight).seconds
    sunset = (sun['sunset'].replace(tzinfo=None) - midnight).seconds
    
    return sunrise, sunset

class SmartSprinkler(object):
    def __init__(self, configSettings, sprinklerLog):
        self.config = SmartSprinklerConfig(configSettings, sprinklerLog)

    def calculateWeeklyWaterAvg(self, startOfCurWeek):
    # Calculate average weekly water total over desired averaging period
        
        # Calculate water total for each week
        weeklyTotals = [0] * (self.config['avgWeeks'] - 1)
        avgTotals = [0] * len(self.config['zones'])
        for week in range(1, self.config['avgWeeks']): # calculate water totals for previous weeks
            weekStart = startOfCurWeek - datetime.timedelta(days=7*week)
            weekEnd = weekStart + datetime.timedelta(days=7)

            _, _, _, weeklyTotals[i-1] = self.getWaterForPeriod(weekStart, weekEnd)

            # Calculate average water per week
            avgTotals = [avgTotals[zone] + weeklyTotals[i-1][zone] / (self.config['avgWeeks'] - 1) for zone in range(len(self.config['zones']))]
        
        return avgTotals

    def getTotalWaterForPeriod(self, startTime, endTime):
    # Calculate the total water (rain and sprinklers) for the requested time period 
        
        # Calculate total rain
        if (self.config.pws):
            try:
                # Get rainfall total
                rainTotal, lastTimeRain = self.config.pws.getRainfall(startTime, endTime, self.config['minRainAmount'])
                
            except ModuleException as err: # fatal error
                raise err
        else:
            rainTotal = 0.0
            lastTimeRain = 0.0
        
        # Calculate sprinkler time for this period
        if (self.config.sprinklerInterface):
            #syslog.syslog("sprinkler total lookup time:" + str(epochTimeBeginWeek))
            try:
                sprinklerTotal = self.config.sprinklerInterface.getSprinklerTotals(self.config['zones'], startTime, endTime)
            except BasicException as err:
                raise err
                #nonFatalException = err # store exception and continue    
            except ModuleException as err:
                raise err
            except Exception as err:
                raise err
                #nonFatalException = err # store exception and continue    

        else:
            sprinklerTotal = dict()
            for zone in zones:
                sprinklerTotal.update({zone: {'totalRunTime': 0, 'lastRunTime': 0}})  

        # Total water for this period by zone (rain and sprinklers)
        totalWater = [rainTotal + sprinklerTotal[self.config['zones'][i]]['totalRunTime']/60.0*self.config['zoneWateringRate'][i] for i in range(len(self.config['zones']))]
        
        return rainTotal, lastTimeRain, sprinklerTotal, totalWater
        
    def calculateWateringRequired(self, startOfCurWeek):
    # Calculate how much water is required this week

        # Calculate total water over averaging period
        endTime = startOfCurWeek
        startTime = endTime - datetime.timedelta(days=7*(self.config['avgWeeks']-1))
        _, _, _, totalWater = self.getTotalWaterForPeriod(startTime, endTime)
        print("Total water over averaging period:", totalWater, startTime, endTime)
 
        # Calculate water required this week to meet desired watering over average period
        wateringReq = [0] * len(self.config['zones'])
        for zone in range(len(wateringReq)):
            desiredWaterTotal = self.config['avgWeeks'] * self.config['weeklyWaterReq'][zone]
            wateringReq[zone] = desiredWaterTotal - totalWater[zone] # desired total minus actual water received 
            print("Calculated water required:", zone, desiredWaterTotal, wateringReq[zone])
        return wateringReq

    def applyOverrides(self, zone, totalWaterThisWeek, lastTimeWater, waterRequired, runDayEpoch):
        print("Applying overrides for zone {}".format(zone))
       
        newRun = None 
        if ('dailyWater' in self.config.zoneConfig[zone]['overrides']):
            # Check if daily water requirement already met
            _, _, _, totalWater = self.getTotalWaterForPeriod(runDayEpoch, runDayEpoch + datetime.timedelta(hours=24))
            waterToday = totalWater[self.config['zones'].index(zone) ]
            waterNeed = self.config.zoneConfig[zone]['overrides']['dailyWater'] - waterToday
            if (waterNeed > 0):
                # Schedule daily water requirement for last available daily run time
                wateringLength = math.ceil(waterNeed/self.config.zoneConfig[zone]['zoneWateringRate']*60.0) # needed length (seconds)
                runTime = self.getRunTime(self.config['desiredRunTimeOfDay'][-1], runDayEpoch, self.config)
                if (wateringLength >= self.config.zoneConfig[zone]['minWateringLength']):
                    newRun = [runTime, zone, wateringLength]
            else:
                print("Daily water override already met for zone {}".format(zone))           

        return newRun

    def runSprinklerLogic(self):
        nonFatalException = None    

        # Check enable status
        if (self.config['enable'] == False):
            # Disable all programs
            if (self.config.sprinklerInterface):
                for i in range(len(self.config['zones'])):
                    try:
                        self.config.sprinklerInterface.disableProgram(self.config['zones'][i])
                    except ModuleException as error: # Sprinkler interface maybe disabled or off
                        print("Could not connect to sprinkler interface.")
                        raise err
                        
            # Log status and exit
            timestamp = time.strftime("%H:%M:%S %m-%d-%Y")
            #try:
                #with open(self.config['logFile'], "a") as f:
                    # Write entry to log
            logEntry = {"timestamp": timestamp, "statusMsg": "Sprinklers currently disabled."}
            self.writeLogEntry(logEntry)
                    #logEntry = "{} - Status: Sprinklers currently disabled.".format(timestamp)
                    #f.write("\n" + logEntry)
            #except:
            #    pass 

            return

        waterRequired = self.config['weeklyWaterReq']
   
        # Determine important times (does not account for DST)
        currentTime = datetime.datetime.now()
        midnightToday = datetime.datetime(currentTime.year, currentTime.month, currentTime.day)
        currentDayOfWeek = (midnightToday.weekday() + 1) % 7
        startOfCurWeek = midnightToday - datetime.timedelta(days=currentDayOfWeek) # start week on Sunday
        midWeek = startOfCurWeek + datetime.timedelta(days=3) # midweek epoch for splitting up long watering times
        endOfCurWeek = startOfCurWeek + datetime.timedelta(days=7, seconds=-30) # subtraction of 30 seconds ensures end time is part of same week
        lastDayOfWeek = datetime.datetime(endOfCurWeek.year, endOfCurWeek.month, endOfCurWeek.day) # start of last day of week
        
        # Total water this week
        _, _, _, totalWaterThisWeek = self.getTotalWaterForPeriod(startOfCurWeek, endOfCurWeek)
       
        # Check for excess or deficit
        if (self.config['excessRollover'] or self.config['deficitMakeup']):
            # Determine water previous week
            if (self.config['excessRollover'] and self.config['deficitMakeup']):
                # Calculate previous week's water as average of previous 2 weeks to avoid feedback loop
                _, _, _, totalWaterLastWeek = self.getTotalWaterForPeriod(startOfCurWeek - datetime.timedelta(days=14), startOfCurWeek)
                totalWaterLastWeek = [zoneWater/2.0 for zoneWater in totalWaterLastWeek]

            else:
                _, _, _, totalWaterLastWeek = self.getTotalWaterForPeriod(startOfCurWeek - datetime.timedelta(days=7), startOfCurWeek)

            # Calculate excess or deficit
            waterAdj = [0]*len(totalWaterLastWeek)
            for idx,zone in enumerate(self.config['zones']):
                waterDelta = totalWaterLastWeek[idx] - self.config.zoneConfig[zone]['weeklyWaterReq']
                if (self.config['excessRollover'] and waterDelta > 0):
                    waterAdj[idx] -= waterDelta # subtract excess from watering requirement
                elif (self.config['deficitMakeup'] and waterDelta < 0):
                    waterAdj[idx] += -waterDelta # add deficit to watering requirement

            waterRequired = [req + adj for req, adj in zip(waterRequired, waterAdj)] 

        print("Water required:", waterRequired)

        # Determine last day of rain or water
        startOfLastWeek = startOfCurWeek - datetime.timedelta(days=7) 
        _, lastTimeRain, sprinklerTotal, _ = self.getTotalWaterForPeriod(startOfLastWeek, currentTime)
        print(lastTimeRain, sprinklerTotal)
        lastTimeWater = [datetime.datetime.fromtimestamp(max(lastTimeRain, sprinklerTotal[zone]['lastRunTime'])) for zone in sprinklerTotal]
        print("Last time water:", lastTimeWater)

        ### Update watering times
        wateringLength = [0]*len(self.config['zones'])
        nextDayToWater = [0]*len(self.config['zones'])
        status = [SSStatus.Requirement_Met]*len(self.config['zones'])
        runData = []
    
        # Check weather forecast 
        precipProb = []
        if (self.config.weatherPredict):
            try:    
                precipProb = self.config.weatherPredict.getPrecipProb(currentTime, endOfCurWeek, self.config['location']['zipcode'])
            except BasicException as err:
                nonFatalException = err # store exception and continue    
            except ModuleException as err:
                nonFatalException = err # store exception and continue    
                #raise err
        
        for idx,zone in enumerate(self.config['zones']):
            
            # Check for override
            if ('overrides' in self.config.zoneConfig[zone]):
                newRun = self.applyOverrides(zone, totalWaterThisWeek[idx], lastTimeWater[idx], waterRequired[idx], midnightToday)
                if (newRun):
                    runData.append(newRun)
                
                continue            

            newRun = []
            runNow = False
            if (currentTime > lastDayOfWeek): # last day of week so force sprinkler run
                runNow = True

            # Determine amount to water (in inches) and when to run sprinklers for zone, accounting for predicted weather
            nextDayToWater[idx], amountToWater, status[idx], runTime, timeChoice = self.getWateringUpdate(idx, totalWaterThisWeek[idx], lastTimeWater[idx], waterRequired[idx], self.config, startOfCurWeek, endOfCurWeek, runNow, precipProb)
            
            if amountToWater > 0: # need to run sprinklers in this zone
                ## Determine run duration
                wateringLength[idx] = math.ceil(amountToWater/self.config.zoneConfig[zone]['zoneWateringRate']*60.0) # requested length (seconds)
                # Do bounds checking
                wateringLength[idx] = max(wateringLength[idx], self.config.zoneConfig[zone]['minWateringLength']) # lower bound
                #wateringLength[zone] = min(wateringLength[zone], self.config['maxWateringLength'][zone]) # upper bound
                
                # Round run length to nearest minute
                #wateringLength[zone] = int(math.ceil(wateringLength[zone]/60.0)*60.0)
            
                # Check if longer than max run time
                if (wateringLength[idx] > self.config.zoneConfig[zone]['maxWateringLength']): # need to split run
                    print("Splitting run time for zone {} due to max length exceedance.".format(zone))
                    wateringLength[idx] = min(wateringLength[idx], self.config.zoneConfig[zone]['maxWateringLength']) # upper bound
                
                    if (runTime > (midWeek)): # run midweek
                        runTime = self.determineRunTime(self.config['desiredRunTimeOfDay'], midWeek, self.config, timeChoice) 
                
                # Store run time data
                newRun = [runTime, zone, wateringLength[idx]]
            
            else: # disable zone program    
                if (self.config.sprinklerInterface):
                    self.config.sprinklerInterface.disableProgram(zone)

            # Check for watering requirement exceeding maximum run length
            if ((waterRequired[idx] - totalWaterThisWeek[idx]) / self.config.zoneConfig[zone]['zoneWateringRate'] > self.config.zoneConfig[zone]['maxWateringLength']): # schedule watering of excess
                excessAmount = (waterRequired[idx] - totalWaterThisWeek[idx]) / self.config.zoneConfig[zone]['zoneWateringRate'] - self.config.zoneConfig[zone]['maxWateringLength'] # water excess over max length
                if (newRun): # update existing schedule run
                    newRun[2] = max(newRun[2], excessAmount) # update amount
                    if (currentTime < midWeek): # update time
                        runTime = min(newRun[0], midWeek) # run by midweek
                        newRun[0] = self.determineRunTime(self.config['desiredRunTimeOfDay'], runTime, self.config, timeChoice) 

                    else: # already past midweek
                        newRun[0] = self.determineRunTime(self.config['desiredRunTimeOfDay'], midnight, self.config, timeChoice) 
                
                else: # schedule run by midweek
                    runEpoch = max(midnight, midWeek)
                    runTime = self.determineRunTime(self.config['desiredRunTimeOfDay'], runEpoch, self.config, timeChoice)
                    wateringLength[idx] = excessAmount


            if (newRun): # add run to list
                runData.append(newRun)
                
        print("Watering lengths: " + str(wateringLength))

        # Modify sprinkler programs 
        logTime = 0
        if any(run[2] > 0 for run in runData): # Watering required by at least one zone
            # Sort by run times
            sortedRuns = sorted(runData, key=lambda tup: tup[0])    
            # Check for run time conflicts
            for i in range(1,len(sortedRuns)):
                for j in range(0,i):
                    if sortedRuns[i][0] == sortedRuns[j][0]: # same run start time so increment
                        sortedRuns[i][0] = sortedRuns[j][0] + datetime.timedelta(seconds=sortedRuns[j][2])
                    elif sortedRuns[i][0] > sortedRuns[j][0] and sortedRuns[i][0] < (sortedRuns[j][0] + datetime.timedelta(seconds=sortedRuns[j][2])): # scheduled to start while other station running
                        sortedRuns[i][0] = sortedRuns[j][0] + datetime.timedelta(sortedRuns[j][2])

            # Update programs
            if (self.config.sprinklerInterface):
                for run in sortedRuns:
                    self.config.sprinklerInterface.updateProgram(run[1], run[2], datetime.datetime.timestamp(run[0]))
        
        else: # No watering required - disable all programs
            if (self.config.sprinklerInterface):
                for i in range(len(self.config['zones'])):
                    self.config.sprinklerInterface.disableProgram(self.config['zones'][i])

        # Log execution data
        print(totalWaterThisWeek)
        logEntry = self.logStatus(self.config['logFile'], self.config['statusFile'], status, runData, totalWaterThisWeek, lastTimeWater, waterRequired)
        
        # Report status
        if (self.config.reportInt and self.config['reportEnable'] != ReportEnable.Disable):
            print(logEntry)
            if (nonFatalException): # exception occurred during execution
                exceptionStr = nonFatalException.message
            else:
                if (self.config['reportEnable'] == ReportEnable.ErrorOnly):
                    return # Status only reports disabled 

                exceptionStr = 'No exceptions occurred.'

            self.config.reportInt.post({'name': "smartSprinkler_status", 'data': [logEntry, exceptionStr]})

    def calculateRunTime(self, timeEntries, settings):
        """Converts inputted run time to a time of day in seconds."""
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
                return None
        else: # absolute time
            timeOfDay = rtime.split(":")
            timeOfDaySec = int(timeOfDay[0])*60*60 + int(timeOfDay[1])*60
        
        return timeOfDaySec

    def getRunTime(self, runTime, runDayEpoch, settings):
        timeEntries = runTime.split()
        timeOfDaySec = self.calculateRunTime(timeEntries, settings)
        runTime = runDayEpoch + datetime.timedelta(seconds=timeOfDaySec)
        
        return runTime

    def determineRunTime(self, desiredRunTimes, runDayEpoch, settings, timeChoice='first'):
        # Input desiredRunTimes are assumed to be monotonically increasing
        currentTime = datetime.datetime.now()
        runTime = None   
 
        for rtime in desiredRunTimes:
            timeEntries = rtime.split()
            timeOfDaySec = self.calculateRunTime(timeEntries, settings)
            # Check if time has already passed 
            if (timeOfDaySec and currentTime < (runDayEpoch + datetime.timedelta(seconds=timeOfDaySec))): # can run at this time
                runTime = runDayEpoch + datetime.timedelta(seconds=timeOfDaySec)
                if (timeChoice == 'first'): # looking for first valid run time
                    break

        if not runTime: # desired times already passed
            # Run tomorrow
            timeOfDay = desiredRunTimes[0].split(":")
            for rtime in desiredRunTimes:
                timeEntries = rtime.split()
                timeOfDaySec = self.calculateRunTime(timeEntries, settings)
                if (timeOfDaySec):
                    break
            runTime = runDayEpoch + datetime.timedelta(days=1,seconds=timeOfDaySec)
        
        return runTime

    def getWateringUpdate(self, zone, amountOfWater, lastTimeWater, weeklyWaterReq, config, startTime, endTime, runNow, precipProb): 
        """Calculate watering needs based on water to date and predicted weather."""
        ## Calculate next watering day
        nextDayToWater = -1
        amountToWater = -1
        status = SSStatus.Requirement_Met
        runTime = -1
        timeChoice = 'first'

        # Check if water requirement met
        if (weeklyWaterReq <= 0 or amountOfWater > 0.9*weeklyWaterReq): # within 10% of requirement
            print("Water requirement met for zone {}.".format(zone+1))
        else:
            print("Water requirement not met for zone {}. Determining next day to water.".format(zone+1))
   
            # Get precipitation forecast (for remainder of week)
            #precipProb = getPrecipProb(startTime, endTime, config['location'])
   
            # Find days where precipitation probability is greater than config['minPrecipProb']
            daysOfRain = []
            for i in range(len(precipProb)):
                if precipProb[i][1] >= config['minPrecipProb']:
                    daysOfRain.append(precipProb[i])
            #print("Days of rain:", daysOfRain)

            running = False
            if (runNow):
                print("Run now override for zone:", zone)
                waterTime = datetime.datetime.now()
                nextDayToWater = datetime.datetime(waterTime.year, waterTime.month, waterTime.day) # midnight
                #nextDayToWater = waterTime - (waterTime - time.altzone)%86400 # midnight of day to water
                amountToWater = weeklyWaterReq - amountOfWater
                status = SSStatus.Forced_Run
                #timeChoice = 'last' # use last available run time of day for forced runs
                running = True
            elif len(daysOfRain) > 0: # Rain predicted
                #print("Rain predicted")
                if (daysOfRain[0][0] - lastTimeWater).total_seconds() <= config['maxDaysBetweenWater']*86400:  # Delay watering
                    print("Delaying watering because rain is predicted before the maximum allowable days without water is exceeded.")
                    status = SSStatus.Delayed
                else: # Predicted rain too long from now so water (exceeds max days between water)
                    if amountOfWater >= 0.5*weeklyWaterReq: # at least half of weekly water requirement received so go ahead and delay
                        print("Half of weekly water requirement already met so wait for rain.")
                        status = SSStatus.Delayed_Half_Met
                    else:  # water a reduced amount in case of rain
                        print("Watering a reduced amount in case of rain")
                        waterTime = min(endTime, lastTimeWater + datetime.timedelta(days=config['maxDaysBetweenWater'])) 
                        if (waterTime < datetime.datetime.now()): # check for watering times in the past
                            waterTime = datetime.datetime.now()
                        nextDayToWater = datetime.datetime(waterTime.year, waterTime.month, waterTime.day) # midnight
                        #nextDayToWater = waterTime - (waterTime - time.altzone)%86400 # midnight of day to water
                        amountToWater = 0.5*(weeklyWaterReq - amountOfWater) # water half of remaining weekly requirement
                        status = SSStatus.Reduced_Watering
                        running = True
            else: # Rain not predicted so run sprinklers
                #print("Rain not predicted")
                waterTime = min(endTime, lastTimeWater + datetime.timedelta(days=config['maxDaysBetweenWater'])) 
            
                # Check for watering times in the past
                if (waterTime < datetime.datetime.now()):
                    waterTime = datetime.datetime.now()

                nextDayToWater = datetime.datetime(waterTime.year, waterTime.month, waterTime.day) # midnight
                amountToWater = weeklyWaterReq - amountOfWater
                status = SSStatus.Watering
                running = True
            
            if (running): # determine run time
                runTime = self.determineRunTime(config['desiredRunTimeOfDay'], nextDayToWater, config, timeChoice)

        return nextDayToWater, amountToWater, status, runTime, timeChoice

    def logStatus(self, logfile, statusfile, status, runData, totalWater, lastTimeWater, waterRequired):
        timestamp = time.strftime("%H:%M:%S %m-%d-%Y")

        logEntry = None   
 
        # Log to cumulative log file
        try:
            statusOut = []
            for zone in status:
                statusOut.append(str(zone))
            runDataOut = {}
            for zone in runData:
                timeStr = zone[0].strftime("%H:%M:%S %m-%d-%Y")
                runDataOut[zone[1]] = {'runTime': timeStr, 'runDuration': zone[2]}

            # Write entry to log
            lastTimeWaterStrs = [dt.strftime("%m-%d-%Y") for dt in lastTimeWater] 
            logEntry = {'timestamp': timestamp, 'zoneStatus': statusOut, 'runs': runDataOut, 'totalWater': totalWater, 'lastTimeWater': lastTimeWaterStrs, 'waterRequired': waterRequired}
            self.writeLogEntry(logEntry)  
        
        except Exception as e:
            pass
        
        return logEntry
   
    def writeLogEntry(self, logEntry):
        with open(self.config['logFile'], "a") as f:
            f.write(json.dumps(logEntry) + "\n")
