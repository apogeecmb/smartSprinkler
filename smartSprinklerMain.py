import yaml
from smartSprinklerExecute import execute

with open("smartSprinkler/smartSprinkler.yaml") as f:
    config = yaml.load(f, Loader=yaml.Loader)

# Execute SmartSprinkler logic
if (config['enable'] == True): 	
    execute(settings=config)
