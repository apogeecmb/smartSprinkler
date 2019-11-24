from weatherPredict import WeatherPredict
import time, datetime, requests
import xml.etree.ElementTree as ET
from exceptions import ModuleException, BasicException

class NWSPredict(WeatherPredict):
# National Weather Service Digital Forecast Database REST Web Service Interface
# https://graphical.weather.gov/xml/rest.php#what

    def __init__(self):
        self.path = "https://graphical.weather.gov/xml/sample_products/browser_interface/ndfdXMLclient.php"

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
            # Pull forecast data from source server
            beginTimeString = datetime.datetime.fromtimestamp(startTime).strftime('%Y-%m-%dT%H:%M:%S') 
            endTimeString = datetime.datetime.fromtimestamp(endTime).strftime('%Y-%m-%dT%H:%M:%S') 

            payload = {'zipCodeList': location, 'product': 'time-series', 'begin': beginTimeString, 'end': endTimeString, 'pop12': 'pop12', 'qpf': 'qpf'} # 12-hour increment probability of precipitation and liquid precipitation amount

            r = requests.get(self.path, params=payload)
            if (r.ok == False):
                # Try get again
                r = requests.get(self.path, params=payload)
                
                if (r.ok == False):
                    message = "NWSPredict - Unable to get predict information."
                    raise BasicException(message)
                    
            # Parse xml
            try: 
                root = ET.fromstring(r.text)
            except ET.ParseError as e: # badly formed XML from NWS
                message = "NWSPredict - Badly formed XML received from NWS."
                raise BasicException(message)
                
            data = root.find('data')
            times = data.findall('time-layout') # start and end times
            params = data.find('parameters')
            prob_of_precip = params.find('probability-of-precipitation') # 12-hour probability of precipitation
            prob_time_key = prob_of_precip.attrib['time-layout'] # probability time key
            liquid_precip_amount = params.find('precipitation') # amount of liquid precipitation
            precip_time_key = liquid_precip_amount.attrib['time-layout']

            # Precip probability values
            probs = []
            for prob in prob_of_precip.findall('value'): 
                probs.append(int(prob.text))

            # Liquid preciptitation amounts
            precips = []
            for precip in liquid_precip_amount.findall('value'): 
                precips.append(float(precip.text))

            # Get times for data
            prob_times = []
            precip_times = []
            for time_layout in times:
                layout_key = time_layout.find('layout-key').text
                if (layout_key == prob_time_key): # probability times
                    start_times = time_layout.findall('start-valid-time')
                    end_times = time_layout.findall('end-valid-time')
                    prob_times = [[a[0].text, a[1].text] for a in zip(start_times, end_times)]
                elif (layout_key == precip_time_key):
                    start_times = time_layout.findall('start-valid-time')
                    end_times = time_layout.findall('end-valid-time')
                    precip_times = [[a[0].text, a[1].text] for a in zip(start_times, end_times)]
                
            # Return chance of precipitation for each day in inputted time period
            precipProbs = []
            currentDay = None
            currentMaxProb = 0
            for i in range(len(probs)): # Iterate through returned precipitation data
                #timeStr = prob_times[i][0][:-6] # strip time zone offset
                #day = datetime.datetime.strptime(timeStr, '%Y-%m-%dT%H:%M:%S').strftime('%d')
                timeStr = prob_times[i][0][0:10] # only interested in day
                day = time.mktime(time.strptime(timeStr, "%Y-%m-%d"))
                day = int(round(day))
            
                if (not currentDay): # first day
                    currentDay = day
                    currentMaxProb = probs[i]
                else:
                    if(day == currentDay): # same day
                        if (probs[i] > currentMaxProb): # greater probability for this day
                            currentMaxProb = probs[i]
                    else: # new day
                        # Store previous days probability
                        precipProbs.append([currentDay, currentMaxProb])

                        # Update current day information
                        currentDay = day
                        currentMaxProb = probs[i]
        
            # Add last day's information
            precipProbs.append([day, currentMaxProb])
        
        except Exception as e: # failed to get weather forecast
            # Get traceback
            import traceback
            tb = traceback.format_exc()

            message = "NWSPredict - An error occurred of type " + type(e).__name__
            raise ModuleException(message, e, tb)
        
        
        return precipProbs

