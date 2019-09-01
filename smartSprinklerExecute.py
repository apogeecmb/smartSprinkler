from smartSprinkler import SmartSprinkler
import time 
import json
from exceptions import ModuleException, PredictException

def execute(settings=[], settingsFile=[], sprinklerLog=[]):
    ### Load config
    if (settingsFile):
        with open(settingsFile) as f:
            settings = json.load(f)
    elif (not settings):    
        # error
        pass

    smartSprinkler = SmartSprinkler(settings)

    try:
        smartSprinkler.runSprinklerLogic(sprinklerLog)
    except ModuleException as err:
        # Report error
        errString = err.message + ": " + str(err.exception) + "\n" + err.traceback
        print(errString)
        if (smartSprinkler.config.reportInt):
            smartSprinkler.config.reportInt.post({'name': "smartSprinkler_error", 'data': [errString]})
    except Exception as err:
        errString = "An unexpected error of type " + type(err).__name__ + " occurred: " + str(err)
        print(errString)
        if (smartSprinkler.config.reportInt):
            smartSprinkler.config.reportInt.post({'name': "smartSprinkler_error", 'data': [errString]})
