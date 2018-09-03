import json
from smartSprinklerExecute import execute

# Override config with any settings present
with open("/home/pi/OSPi/data/smartSprinkler.json") as ospiSettings:
    settings = json.load(ospiSettings)

with open("/home/pi/smartSprinkler/smartSprinkler.json") as f:
    config = json.load(f)
	
# Override config with any settings present
config.update(settings)

execute(settings=config)
