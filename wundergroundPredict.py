from weatherPredict import WeatherPredict
import requests

class WundergroundPredict(WeatherPredict):
# DEPRECATED: Weather Underground API has been deprecated due to purchase of Wunderground by IBM. 

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
            #f = request.urlopen(self.path + str(location) + '.json')
            f = requests.get(self.path + str(location) + '.json')
        except: # failed to get weather forecast
            return [] 

        # Parse json
        #json_string = f.read()
        #parsed_json = json.loads(json_string)
        parsed_json = f.json()
        forecast = parsed_json['forecast']['simpleforecast']['forecastday']
        # Get precipitation probabilities in desired time range
        precipProb = []
        for i in range(len(forecast)):
            if int(forecast[i]['date']['epoch']) > startTime:
                if int(forecast[i]['date']['epoch']) < endTime:
                    precipProb.append([int(forecast[i]['date']['epoch']),forecast[i]['pop']])
                    #print i, forecast[i]['date']['epoch'] 
                else: 
                    print("PrecipProb:", precipProb)
                    return precipProb
            
        print("PrecipProb:", precipProb)
        return precipProb
