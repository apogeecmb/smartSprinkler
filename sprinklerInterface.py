import time

class SprinklerInterface:
    def __init__(self, path, numZones):
        self.path = path
        self.numZones = numZones

    def getSprinklerTotals(zones, startTime, endTime, log=[]):
        pass
    
    def updateProgram(self, zoneNum, durationSec, runTimeEpoch):
        pass

    def disableProgram(self, zoneNum):
        pass
