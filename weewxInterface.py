from pwsInterface import PWSInterface
from exceptions import ModuleException
import sqlite3 # sqlite3 module

class WeeWXInterface(PWSInterface):
    
    def getRainfall(self, startTime, endTime, minRainAmount):
        rainfall = 0.0
        lastDayOfRain = 0

        try:
            # Open connection to stats database
            conn = sqlite3.connect(self.path) 

            c = conn.cursor() # cursor to operate on database

            # Get rainfall table from database
            c.execute('SELECT * FROM archive_day_rain WHERE dateTime BETWEEN ? AND ?', (startTime, endTime))

            rainTable = c.fetchall()

            # Compute total rainfall between start and end times
            for i in range(len(rainTable)):
                if rainTable[i][5] > 0:
                    rainfall += rainTable[i][5]
                    if rainTable[i][5] > minRainAmount: # minimum rain amount to count as "rain day"
                        lastDayOfRain = rainTable[i][0]

            conn.close()

        except Exception as e:
            # Get traceback
            import traceback
            tb = traceback.format_exc()
            
            message = "WeeWXInterface - An error occurred of type " + type(e).__name__
            raise ModuleException(message, e, tb)
        
        return rainfall, lastDayOfRain 

