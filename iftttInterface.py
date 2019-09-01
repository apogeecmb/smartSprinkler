import requests
from reportInterface import ReportInterface

class IFTTTInterface(ReportInterface):
    def __init__(self, key):
        self.key = key
        self.url = "https://maker.ifttt.com/trigger/"
    
    def post(self, event):
        eventName = event['name']
        
        # Grab any data in the event
        payload = dict()
        if ('data' in event and len(event['data']) <= 3):
            for el in range(len(event['data'])):
                entry = "value" + str(el+1)
                payload[entry] = event['data'][el]
        
        # Create post request
        url = self.url + eventName + "/with/key/" + self.key
        r = requests.post(url, data=payload)

