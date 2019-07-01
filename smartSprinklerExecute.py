from smartSprinklerLogic import *
import time 
import math
import json
import syslog

def execute(settings=[], settingsFile=[], sprinklerLog=[]):
    ### Load config
    if (settingsFile):
        with open(settingsFile) as f:
            settings = json.load(f)
    elif (not settings):    
        # error
        pass

    config = SmartSprinklerConfig(settings)
    weeklyWaterReq = config['weeklyWaterReq']

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
    if (config.pws):
        # Get rainfall total this week
        rainfall, lastTimeOfRain = config.pws.getRainfall(epochTimeBeginWeek, epochTimeEndWeek, config['minRainAmount'])
        # Get rainfall total for previous week 
        lastWeekRain, timeRainLastWeek = config.pws.getRainfall(startLastWeek, epochTimeBeginWeek, config['minRainAmount'])
    else:
        rainfall = 0.0
        lastTimeOfRain = 0.0
        lastWeekRain = 0.0
        timeRainLastWeek = 0.0
        
    print("Rainfall this week: ", rainfall, lastTimeOfRain)

    if (rainfall < 0.0):
        rainfall = 0.0

    # Calculate sprinkler time this week
    if (config.sprinklerInterface):
        #syslog.syslog("sprinkler total lookup time:" + str(epochTimeBeginWeek))
        sprinklerTable = config.sprinklerInterface.getSprinklerTotals(config['sprinklerLogFile'],config['zones'],epochTimeBeginWeek, log=sprinklerLog)
        lastSprinklerTable = config.sprinklerInterface.getSprinklerTotals(config['sprinklerLogFile'],config['zones'],startLastWeek,epochTimeBeginWeek, log=sprinklerLog)
    else:
        sprinklerTable = dict()
        for zone in zones:
            sprinklerTable.update({zone: {'totalRunTime': 0, 'lastRunTime': 0}})  
        lastSprinklerTable = sprinklerTable

    # Total water by zone (rainfall and sprinklers)
    totalWater = [rainfall + sprinklerTable[config['zones'][i]]['totalRunTime']/60.0*config['zoneWateringRate'][i] for i in range(len(config['zones']))]
    
    # Check for time since last rain or water
    if (timeRainLastWeek > lastTimeOfRain): # no rain this week, but rained last 
        lastTimeOfRain = timeRainLastWeek
    
    totalWaterLastWeek = [lastSprinklerTable[config['zones'][i]]['totalRunTime']/60.0*config['zoneWateringRate'][i] + lastWeekRain for i in range(len(config['zones']))] # total water last week by zone

    # Add past week excess water to this week's total
    if (config['excessRollover']):  
        for i in range(len(totalWaterLastWeek)):
            if totalWaterLastWeek[i] > weeklyWaterReq[i]: # check for excess amount
                totalWater[i] += totalWaterLastWeek[i] - weeklyWaterReq[i]
    
    print("Total water this week:", totalWater)

    # Calculate last day of rain or water
    lastTimeWater = [max(lastTimeOfRain,sprinklerTable[zone]['lastRunTime'],lastSprinklerTable[zone]['lastRunTime']) for zone in sprinklerTable]
    
    ### Update watering times
    wateringLength = [0]*len(config['zones'])
    nextDayToWater = [0]*len(config['zones'])
    status = [SSStatus.Requirement_Met]*len(config['zones'])
    runData = []
    
    # Check weather forecast 
    precipProb = []
    if (config.weatherPredict):
        precipProb = config.weatherPredict.getPrecipProb(currentTime, epochTimeEndWeek, config['location'])
    for zone in range(len(config['zones'])):
        runNow = False
        if (currentTime > lastDayOfWeek): # last day of week so force sprinkler run
            runNow = True
            

        nextDayToWater[zone], amountToWater, status[zone], runTime = getWateringUpdate(zone, totalWater[zone], lastTimeWater[zone], weeklyWaterReq[zone], config, epochTimeBeginWeek, epochTimeEndWeek, runNow, precipProb)
    
        if amountToWater > 0: # need to run sprinklers in this zone
            ## Determine run time
            wateringLength[zone] = amountToWater/config['zoneWateringRate'][zone]*60.0 # requested length (seconds)
            # Do bounds checking
            wateringLength[zone] = max(wateringLength[zone], config['minWateringLength'][zone]) # lower bound
            wateringLength[zone] = min(wateringLength[zone], config['maxWateringLength'][zone]) # upper bound
            wateringLength[zone] = int(math.ceil(wateringLength[zone]/60.0)*60.0) # nearest minute in seconds
            
            # Store run time data
            runData.append([runTime, config['zones'][zone], wateringLength[zone]]) 
        else: # disable zone program    
            if (config.sprinklerInterface):
                config.sprinklerInterface.disableProgram(config['zones'][zone])

    print("Watering lengths: " + str(wateringLength))

    # Modify sprinkler programs 
    logTime = 0
    if any(length > 0 for length in wateringLength): # Watering required by at least one zone

        # Determine run times
        #for i in range(len(config['zones'])):
            #if wateringLength[i] > 0: # watering required
                
                # Determine next available run time
                #runTime = determineRunTime(config['desiredRunTimeOfDay'], nextDayToWater[i])
                #runData.append([runTime, i, config['zones'][i], wateringLength[i]]) 
            #else: # no watering - disable program
            #   disableProgram(i, config['zones'][i])

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
        if (config.sprinklerInterface):
            for run in sortedRuns:
                config.sprinklerInterface.updateProgram(run[1], run[2], run[0])
        
    else: # No watering required - disable all programs
        if (config.sprinklerInterface):
            for i in range(len(config['zones'])):
                config.sprinklerInterface.disableProgram(config['zones'][i])

    # Log execution data
    logStatus(config['logFile'], config['statusFile'], status, runData, totalWater, lastTimeWater)

#os_cmd = url + "&v=[65, " + str(days0) + ", 0, [" + str(timeOfDaySec/60) + ", 0, " + str(interval) +", 0]," + durEntry + "]&name=SmartSprinklerProgram"
#print("OS cmd: " + os_cmd)

#os_cmd = url + "&v=[1, " + days0 + ", 0, , 0, 36, 0],[300,600,600,600]]&name=SmartSprinklerProgram")

# Need to keep a log of total water and rain since weather log only has rain totals


    #os_cmd = url + "&pid=" + str(zoneNum-1) + "&v=[0, " + str(days0) + ", 0, 0, 0, 0, 0, " + str(zoneId) + "]&name=SmartSprinklerZone" + str(zoneNum)
