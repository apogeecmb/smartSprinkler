import sqlite3 # sqlite3 module

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

