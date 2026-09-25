# ABM-3: Aether Drift
Anxiety Bois Modpack 3 private development repo

## Target Version: 26.1.2
Current development targets 26.1.2, but 26.2 or 26.3 should be considered viable options depending on the direction the modding comunity follows.

## Critical Mods
These are mods without which the pack as envisioned is not viable:

### Aether II
Intent is to set Aether II's spawn_in_aether = true and gate early progression around ore spawns on/around spawn.

### Create Aeronautics
Create Aeronautics - Aether II was the original concept for ABM 2 but could not be achieved due to version conflicts.

### Tetra Or SilentGear
Envisioned as core tool progression, Tetra prefered but currently updating to 1.21.

### FTB Quests Or Neoquests
Required as progression map and reward system.

## Mod and Config Control
https://github.com/packwiz/packwiz will be used to generate final mod manifests for modrinth/curseforge.
When updating the modlist, config files should be included in /config, and the manifest updated in /docs/config-manifest.toml - audit-configs.yml should be used to confirm all mods have configuration files present and that no configuation files from removed mods are still present. 

## Server/Client Handling
Server branch to be split-out in future.