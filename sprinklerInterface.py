import time

class SprinklerInterface:
    def __init__(self, path, numZones, log):
        self.path = path
        self.numZones = numZones
        self.log = log

    def getSprinklerTotals(zones, startTime, endTime):
        pass
    
    def updateProgram(self, zoneNum, durationSec, runTimeEpoch):
        pass

    def disableProgram(self, zoneNum):
        pass
