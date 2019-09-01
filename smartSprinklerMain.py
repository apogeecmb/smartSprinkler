import yaml
from smartSprinklerExecute import execute

with open("/home/pi/smartSprinkler/smartSprinkler.yaml") as f:
    config = yaml.load(f, Loader=yaml.Loader)
	
execute(settings=config)
