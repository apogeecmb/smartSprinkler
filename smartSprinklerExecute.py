from smartSprinkler import SmartSprinkler
import time 
import yaml
import sys
from exceptions import ModuleException

def execute(settings=[], settingsFile=[], sprinklerLog=[]):
    ### Load config
    if (settingsFile):
        with open(settingsFile) as f:
            settings = yaml.load(f, Loader=yaml.Loader)
    elif (not settings):    
        print("SmartSprinklerExecute - No settings provided. Exiting.")
        sys.exit()

    try:     
        smartSprinkler = SmartSprinkler(settings, sprinklerLog)
    except ModuleException as err:
        errString = err.message + ": " + str(err.exception) + "\nTraceback: " + str(err.traceback)
        print(errString)
        sys.exit()
    except Exception as err:
        print("Exception while creating SmartSprinkler instance:", str(err))
        sys.exit()

    try:
        smartSprinkler.runSprinklerLogic()
    except ModuleException as err:
        # Report error
        errString = err.message + ": " + str(err.exception) + "\nTraceback: " + str(err.traceback)
        print(errString)
        if (smartSprinkler.config['reportEnable'] > 0 and smartSprinkler.config.reportInt):
            smartSprinkler.config.reportInt.post({'name': "smartSprinkler_error", 'data': [errString]})
    except Exception as err:
        import traceback
        tb = traceback.format_exc()
        
        errString = "An unexpected error of type " + type(err).__name__ + " occurred: " + str(err) + "\nTraceback: " + str(tb)
        print(errString)

        if (smartSprinkler.config['reportEnable'] > 0 and smartSprinkler.config.reportInt):
            smartSprinkler.config.reportInt.post({'name': "smartSprinkler_error", 'data': [errString]})
