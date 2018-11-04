import json
from smartSprinklerExecute import execute

with open("/home/pi/smartSprinkler/smartSprinkler.json") as f:
    config = json.load(f)
	
execute(settings=config)
