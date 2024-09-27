# NEW: ORTOOLS installation needed (python -m pip install ortools)
# delete fab module in testbench (clk definition needed)
# do a run without supertiles just with submodules

import FABulous
import fabric_generator.automatic_opt_fabric_gen.netlist_rearrange as netListOpt
import fabric_generator.automatic_opt_fabric_gen.pin_rearrange as pinOpt
import fabric_generator.automatic_opt_fabric_gen.config as genConfig
import fabric_generator.automatic_opt_fabric_gen.general as generalFunctions
from dataclasses import dataclass
from operator import attrgetter
from collections import Counter
from typing import List
from pathlib import Path
import subprocess as sp
import logging
import os
import re
import shutil
import configparser


# storing tiles to generate
@ dataclass
class tileOpenLane():
    name: str
    height: int
    width: int
    locationX: int
    locationY: int


# logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="[%(levelname)s]-%(asctime)s - %(message)s", level=logging.INFO)


class optimizeGenerator():
    # flow config variables
    macroConfig = {}
    coreConfig = []
    ol_run_name = "auto_run"
    fabulousRunName = "eFPGA"
    ramName = "BlockRAM_1KB"
    configPath = 'automated_config.ini'
    openlaneDir = ""
    starterTile = ""
    mostCommonTile = ""
    projectDir = ""
    noSupPath = ""
    pdkPath = ""
    ramGenerate = False
    optFlag = False
    generateRTL = False
    iterations = 1
    standardTileSize = 300
    terminateTilesHeight = 200
    targetDensity = 0.5
    densitySteps = 0.02
    marginFab = 100
    marginTiles = 40
    marginFabCore = 10
    marginRAM = 100
    ramHeight = 446.23  # demo RAM (1KB)
    ramWidth = 600      # demo RAM (1KB)

    # CSV map
    fabricGen: FABulous
    allTile = []
    tilesToGenerateOL = []
    fabricTileMap = []
    tilePinOrderPos = {}

    def __init__(self, shell, args, fabricGen, allTile, csvFile, projectDir):
        self.fabricGen = fabricGen
        self.allTile = allTile
        self.csvFile = csvFile
        self.projectDir = projectDir
        fabricDims = []
        fabricDims = [[], []]

        # Read fabric.csv
        if not csvFile.endswith(".csv"):
            raise ValueError("File must be a csv file")
        if not os.path.exists(csvFile):
            raise ValueError(f"File {csvFile} does not exist")

        with open(csvFile, 'r') as f:
            file = f.read()
            file = re.sub(r"#", "", file)
            f.close()
        if fabricDescription := re.search(
                r"FabricBegin(.*?)FabricEnd", file, re.MULTILINE | re.DOTALL):
            fabricDescription = fabricDescription.group(1)
        else:
            raise ValueError('Cannot find FabricBegin and FabricEnd in csv file')

        # check if config file exists
        if not Path(self.configPath).is_file():
            genConfig.generateAutoConfig(self.configPath)
            raise ValueError('Configuration file for automated flow was not generated. It is now generated automatically. Please check the configuration file and rerun again.')


        # Automated flow configuration
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(self.configPath)

        # check for sections, their necessary options and read configuration
        if not config.has_section("General"):
            raise ValueError(f"Define [General] section in {self.configPath}")
        if not config.has_section("OpenLaneMacro_DEFAULT"):
            raise ValueError(f"Define [OpenLaneMacro_DEFAULT] section in {self.configPath}")
        if not config.has_section("OpenLaneCore"):
            raise ValueError(f"Define [OpenLaneCore] section in {self.configPath}")
        if not config.has_section("Dimensions"):
            raise ValueError(f"Define [Dimensions] section in {self.configPath}")
        if not config.has_option("General", "OpenLane_path"):
            raise ValueError(f"Define OpenLane_path in [General] section in {self.configPath}")
        self.openlaneDir = config['General']['OpenLane_path']
        if not config.has_option("General", "SupertileFreeRunPath"):
            raise ValueError(f"Define SupertileFreeRunPath in [General] section in {self.configPath}")
        if not config.has_option("General", "PDKPath"):
            raise ValueError(f"Define PDKPath in [General] section in {self.configPath}, for demo RAM placement")
        if not config.has_option("General", "TargetDensityStart"):
            logger.warning(f"You can define TargetDensityStart in [General] section in {self.configPath}")
        else:
            self.targetDensity = float(config['General']['TargetDensityStart'])
        if not config.has_option("General", "TerminateTilesStartHeight"):
            logger.warning(f"You can define TerminateTilesStartHeight in [General] section in {self.configPath}")
        else:
            self.terminateTilesHeight = int(config['General']['TerminateTilesStartHeight'])
        if config.has_option("General", "RAMEnable"):
            self.ramGenerate = config['General'].getboolean('RAMEnable')
        if config.has_option("General", "MarginRAM"):
            self.marginRAM = int(config['General']['MarginRAM'])
        if config.has_option("General", "´DensityStepsPercent"):
            self.densitySteps = int(config['General']['´DensityStepsPercent']) * 0.01

        self.pdkPath = config['General']['PDKPath']
        self.noSupPath = config['General']['SupertileFreeRunPath']

        # Parse tilemap and fill dimension with standard values
        fabricDescription = fabricDescription.split("\n")
        for f in fabricDescription:
            lineTemp = f.split(",")
            lineTemp = ' '.join(lineTemp).split()
            if lineTemp:
                self.fabricTileMap.append(lineTemp)

        for tileRow in self.fabricTileMap:
            for tileColumn in tileRow:
                # fabricDims[0]: X-Axis; fabricDims[1]: Y-Axis
                fabricDims[0].append(self.standardTileSize)
                fabricDims[1].append(self.standardTileSize)
        fabricDims = list(list(map(int, fabricDims[0]))), list(list(map(int, fabricDims[1])))

        # tiles to generate and add dimensions
        tilesToGenerateOL = []
        tileNameBuffer = []
        for rowCount, tileRow in enumerate(self.fabricTileMap):
            for columnCount, tileColumn in enumerate(tileRow):
                if tileColumn not in tileNameBuffer:
                    tilesToGenerateOL.append(tileOpenLane(tileColumn, fabricDims[1][rowCount], fabricDims[0][columnCount], columnCount, rowCount))
                tileNameBuffer.append(tileColumn)
        self.tilesToGenerateOL = tilesToGenerateOL

        # find and place starter tile on top of generate tile list
        mostCommonTile = Counter(tileNameBuffer)
        self.mostCommonTile = mostCommonTile.most_common(1)[0][0]

        if config.has_option("General", "StarterTile"):
            self.starterTile = config['General']['StarterTile']
        else:
            self.starterTile = self.mostCommonTile
            logger.warning("Starter Tile for resizing not defined. This could lead to a significant computing time increase. The most occuring tile will be taken.")

        starterTileFound = False
        foundAt = int
        for index, tile in enumerate(self.tilesToGenerateOL):
            if tile.name == self.starterTile:
                starterTileFound = True
                foundAt = index
        if starterTileFound:
            self.tilesToGenerateOL[0], self.tilesToGenerateOL[foundAt] = self.tilesToGenerateOL[foundAt], self.tilesToGenerateOL[0]
        else:
            logger.error(f"Starter tile {self.starterTile} does not exist. Check spelling.")

        # resize flow config
        if config.has_option("General", "ResizeTilesOptimizations"):
            self.optFlag = config['General'].getboolean('ResizeTilesOptimizations')
            if self.optFlag: 
                logger.info("Automatic resizing optimization flow of the tiles enabled")

        # Dimensions Config
        if config.has_option("Dimensions", "StarterTileWidth"):
            self.tilesToGenerateOL[0].width = int(config['Dimensions']["StarterTileWidth"])
        if config.has_option("Dimensions", "StarterTileHeight"):
            self.tilesToGenerateOL[0].height = int(config['Dimensions']["StarterTileHeight"])
        tileFound = False
        for dim in config["Dimensions"]:
            if "_Width" in dim:
                dimName = dim.removesuffix('_Width')
                for index, tile in enumerate(self.tilesToGenerateOL):
                    if tile.name == dimName:
                        tileFound = True
                        foundAt = index
                    if tileFound:
                        self.tilesToGenerateOL[foundAt].width = int(config['Dimensions'][dim])
                        tileFound = False

        # Config margins core
        if config.has_option("General", "ResizeOptimizationsIterations"):
            self.iterations = int(config['General']['ResizeOptimizationsIterations'])
        if config.has_option("General", "MarginTiles"): 
            self.marginTiles = int(config['General']['MarginTiles'])
        if config.has_option("General", "MarginFab"): 
            self.marginFab = int(config['General']['MarginFab'])
        if config.has_option("General", "MarginFabCore"): 
            self.marginFabCore = int(config['General']['MarginFabCore'])
        if config.has_option("General", "OpenLaneRunName"):
            self.ol_run_name = config['General']['OpenLaneRunName'] 
        if config.has_option("General", "FABulousRunName"):
            self.fabulousRunName = config['General']['FABulousRunName'] 
        if config.has_option("General", "GenerateRTL"): 
            self.generateRTL = config['General'].getboolean('GenerateRTL') 
        
        # OpenLane macro Specified and DEFAULT Config
        tilesConfig = config.sections()
        for tileConfig in tilesConfig:
            if "OpenLaneMacro_" in tileConfig:
                self.macroConfig[tileConfig.removeprefix("OpenLaneMacro_")] = config[tileConfig]
        # OpenLane Core Config
        self.coreConfig = config["OpenLaneCore"]

        # execute FABulous flow for RTL generation
        if self.generateRTL:
            shell.do_load_fabric()
            shell.do_gen_all_tile()
            shell.do_gen_fabric()
            shell.do_gen_top_wrapper()

        # change makefile of OpenLane to disable graphics
        f = open(f"{self.openlaneDir}/Makefile")
        data = f.readlines()
        f.close()
        searchLine = "$(ENV_START) -ti $(OPENLANE_IMAGE_NAME)-$(DOCKER_ARCH)"

        for i, line in enumerate(data):
            if searchLine in line: 
                data[i] = line.replace("-ti", "-i")
        with open(f"{self.openlaneDir}/Makefile", "w") as f:
            f.writelines(data)
            f.close()

    def getSupertileName(self, tileName):
        name = ""
        for superTile in self.fabricGen.fabric.superTileDic:
            for subTile in self.fabricGen.fabric.superTileDic[superTile].tiles:
                if subTile.name == tileName:
                    name = superTile
        return name

    def getSupertileClock(self, tileName):
        clock = False
        clock = self.fabricGen.fabric.superTileDic[tileName].withUserCLK
        if not clock:
            for tile in self.fabricGen.fabric.superTileDic[tileName].tiles:
                if not clock:
                    clock = self.fabricGen.fabric.getTileByName(tile.name).getUserCLK()
        return clock

    # generate pin_order.cfg
    def generate_pin_order_config(self, tile, ioPos, cornerPos):
        portOrder = {}
        withUserCLK = True

        # check for external ports
        externalPorts = []
        externalBEL = self.fabricGen.fabric.getTileByName(tile.name).getExternalTileIONames()
        for i in externalBEL:
            externalPorts.extend(i.externalOutput)
            externalPorts.extend(i.externalInput)
        if externalBEL:
            withUserCLK = max(externalBEL, key=attrgetter('withUserCLK')).withUserCLK

        # User Clock in tile?
        if not withUserCLK:
            withUserCLK = self.fabricGen.fabric.getTileByName(tile.name).getUserCLK()
        if not withUserCLK:
            superTile = ""
            superTile = self.getSupertileName(tile.name)
            if superTile:
                withUserCLK = self.getSupertileClock(superTile)

        # handle tile ports and their cardinal position depending on tile position on tilemap
        portsObj = self.fabricGen.fabric.getTileByName(tile.name).getNorthSidePorts()
        for port in portsObj:
            portOrder[port.name] = "Top"
        portOrder["FrameStrobe_O"] = "Top"
        if tile.locationY == 0 and externalPorts and tile.locationX != 0:
            for port in externalPorts:
                portOrder[port] = "Top"
        if withUserCLK:
            portOrder["UserCLKo"] = "Top"
        portsObj = self.fabricGen.fabric.getTileByName(tile.name).getSouthSidePorts()
        for port in portsObj:
            portOrder[port.name] = "Bottom"
        portOrder["FrameStrobe"] = "Bottom"
        if tile.locationY == max(self.tilesToGenerateOL, key=attrgetter('locationY')).locationY and externalPorts and tile.locationX != max(self.tilesToGenerateOL, key=attrgetter('locationY')).locationY:
            for port in externalPorts:
                portOrder[port] = "Bottom"
        if withUserCLK:
            portOrder["UserCLK"] = "Bottom"
        portsObj = self.fabricGen.fabric.getTileByName(tile.name).getEastSidePorts()
        for port in portsObj:
            portOrder[port.name] = "Right"
        if not cornerPos and (ioPos not in ["Top", "Bottom"]): 
            portOrder["FrameData_O"] = "Right"
        if tile.locationX == max(self.tilesToGenerateOL, key=attrgetter('locationX')).locationX and externalPorts:
            for port in externalPorts:
                portOrder[port] = "Right"
        portsObj = self.fabricGen.fabric.getTileByName(tile.name).getWestSidePorts()
        for port in portsObj:
            portOrder[port.name] = "Left"
        if not cornerPos and (ioPos not in ["Top", "Bottom"]): 
            portOrder["FrameData"] = "Left"
        if tile.locationX == 0 and externalPorts and tile.locationY != 0:
            for port in externalPorts:
                portOrder[port] = "Left"

        return portOrder, externalPorts

    def parse(self, line: str) -> List[str]:
        return line.split()

    # shrink or enlarge tile area depending on last run / iteration
    def resizeTile(self, tileID: int, tileEnlargePrevious: bool, tileEnlargeCurrent: bool, firstRun: bool, resize: str):
        fixedOrderComplete = False
        if firstRun:
            firstRun = False
            tileEnlargePrevious = tileEnlargeCurrent
            if tileEnlargePrevious:
                # make tile larger
                if resize == 'Both':
                    self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
                    self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                elif resize == 'Width':
                    self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                elif resize == 'Height':
                    self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
            else:
                # make tile smaller
                if resize == 'Both':
                    self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
                    self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                elif resize == 'Width':
                    self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                elif resize == 'Height':
                    self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
        else:
            # revert last changes
            if tileEnlargePrevious != tileEnlargeCurrent:
                fixedOrderComplete = True
                if tileEnlargePrevious:
                    if resize == 'Both':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                    elif resize == 'Width':
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                    elif resize == 'Height':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
                else:
                    if resize == 'Both':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                    elif resize == 'Width':
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                    elif resize == 'Height':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
                tileEnlargePrevious = False 
            # keep on increasing / decreasing size
            else:
                if tileEnlargePrevious:
                    if resize == 'Both':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                    elif resize == 'Width':
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width + 1
                    elif resize == 'Height':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height + 1
                else:
                    if resize == 'Both':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                    elif resize == 'Width':
                        self.tilesToGenerateOL[tileID].width = self.tilesToGenerateOL[tileID].width - 1
                    elif resize == 'Height':
                        self.tilesToGenerateOL[tileID].height = self.tilesToGenerateOL[tileID].height - 1
        return fixedOrderComplete, tileEnlargePrevious, firstRun

    # find min size of a tile with optimizations
    def resizeTileOptFlow(self, indexTile, prevPinDistances, resizeDim, ioPos, pinOrderChange, isSuperTileColumn, cornerPos, lastTermLoop):
        logger.info("----------------------------------------------------")
        logger.info(f"CURRENT TILE NAME: {self.tilesToGenerateOL[indexTile].name}")
        logger.info("----------------------------------------------------")
        logger.info("Generating tiles in OpenLane flow with tile resizing and start sizes defined in 'automated_config.ini'")
        fixedOrderComplete = False
        tileEnlarge = False
        firstRun = True
        tileName = self.tilesToGenerateOL[indexTile].name
        openlane_make = f"cd {self.openlaneDir}; make mount"
        currentTileDensity = self.targetDensity
        densityManipulated = False

        # write logfile for tile
        logFile = f"{self.openlaneDir}/designs/{tileName}/iteration_resize_log.txt"
        generalFunctions.writeLog([f"Resize {tileName} \n"], logFile, "w")

        synthesisFile = f"{self.openlaneDir}/designs/{tileName}/src/{tileName}.v"

        generalFunctions.writeLog(["Start resizing without optimizations \n"], logFile, "a")
        logger.info("Start resizing without optimizations")

        combinDict = {}
        pinDistance = {}
        pinDistanceTemp = {}
        pinOrderChangeTile = {}
        pinOrderChangeTile = pinOrderChange 

        # which side the pins are placed on and fix order based on prev Tile
        pinSides, externUnused = self.generate_pin_order_config(self.tilesToGenerateOL[indexTile], ioPos, cornerPos)
        initCombinDict = generalFunctions.initialRunCombinDict(synthesisFile, self.fabricGen.fabric.frameBitsPerRow, self.fabricGen.fabric.maxFramesPerCol, pinSides) 
        combinDict, pinOrderChangeRun = generalFunctions.fixUpdateOrder("", initCombinDict, pinOrderChange, resizeDim, ioPos, isSuperTileColumn, cornerPos, lastTermLoop)

        # shrink tile as far as possible without optimizations
        while not fixedOrderComplete:
            generalFunctions.writeLog([f"Current Height:{self.tilesToGenerateOL[indexTile].height} ; Current Width:{self.tilesToGenerateOL[indexTile].width} ; Current Density: {currentTileDensity}\n "], logFile, "a")
            logger.info(f"Current Height:{self.tilesToGenerateOL[indexTile].height} --- Current Width:{self.tilesToGenerateOL[indexTile].width} --- Current Density: {currentTileDensity}")
            # config
            logger.info(f"Generate OpenLane config files for tile: {self.tilesToGenerateOL[indexTile].name}")
            genConfig.generate_OpenLane_config(self.openlaneDir, self.tilesToGenerateOL[indexTile], self.macroConfig, True, currentTileDensity)

            # edit ioplacer.tcl
            logger.info("Define pinorder in ioplacer.tcl")
            if resizeDim == "Height" and cornerPos:
                pinDistanceTemp = genConfig.ioPlace(self.tilesToGenerateOL[indexTile], combinDict, self.openlaneDir, prevPinDistances, resizeDim, cornerPos, isSuperTileColumn)
            else:
                pinDistanceTemp = genConfig.ioPlace(self.tilesToGenerateOL[indexTile], combinDict, self.openlaneDir, prevPinDistances, resizeDim, ioPos, isSuperTileColumn)

            # run openlane flow on the tiles
            logger.info(f"Start OpenLane flow for tile: {tileName}")
            tile_command = f"./flow.tcl -design {tileName} -tag {self.ol_run_name} -overwrite"
            proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
            proc.communicate(tile_command)
            proc.stdout.close()
            proc.terminate()
            logger.info(f"OpenLane flow for {tileName} complete.")

            # check for errors
            tileEnlargeCurrent = generalFunctions.check_flow(self.openlaneDir, tileName, False, logger, self.ol_run_name)

            if not tileEnlargeCurrent:
                generalFunctions.copyAndOverwrite(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}",
                                                  f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}_temp_success")
                pinDistance = pinDistanceTemp
                densityManipulated = False
 
            # Supertile only basically. Run only one time and no resizing if too small keep increasing
            if not resizeDim:
                fixedOrderComplete = True
            else:
                # shrink / enlarge tile area
                fixedOrderComplete, tileEnlarge, firstRun = self.resizeTile(indexTile, tileEnlarge, tileEnlargeCurrent, firstRun, resizeDim)
            # if fixed order complete increase density and try to rerun
            if resizeDim and fixedOrderComplete and not densityManipulated and currentTileDensity <= (1 - self.densitySteps) and not tileEnlarge and ioPos != "Bottom" and ioPos != "Top": 
                densityManipulated = True
                fixedOrderComplete = False
                firstRun = True
                currentTileDensity += self.densitySteps
                currentTileDensity = round(currentTileDensity, 2)
                pinDistance = pinDistanceTemp
            elif (currentTileDensity != self.targetDensity and densityManipulated):
                currentTileDensity -= self.densitySteps
                currentTileDensity = round(currentTileDensity, 2)
                self.resizeTile(indexTile, True, False, False, resizeDim) 
                fixedOrderComplete = True
        if resizeDim:
            generalFunctions.copyAndOverwrite(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}_temp_success",
                                              f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}")
        logger.info(f"Optimization free resizing for tile {tileName} finished")
        generalFunctions.writeLog([f"Finished Height:{self.tilesToGenerateOL[indexTile].height} ; Finished Width:{self.tilesToGenerateOL[indexTile].width} ; Finished Density:{currentTileDensity}\n",
                                   "----------------------------------------------------------------------------------------------------- \n"], logFile, "a")

        notSuccessRun = False
        logger.info(f"Start optimizing pinorder and netlist for {tileName} for {self.iterations} iterations")
        generalFunctions.writeLog(["Start resizing with optimizations \n"], logFile, "a")

        # shrink tile as far as possible with optimizations (not supported for IO Tiles yet)
        print(f"resizeDim: {resizeDim}   , ioPos: {ioPos}")
        print(tileName)
        firstRun = True
        superColumn = False
        failCounter = 0
        if self.getSupertileName(self.tilesToGenerateOL[indexTile].name):
            superColumn = True
        if resizeDim and not ioPos and not superColumn and self.optFlag:
            try:
                os.makedirs(f"{self.openlaneDir}/designs/{tileName}/statistics")
            except OSError:
                pass

            for i in range(self.iterations):
                logger.info(f"Pin and netlist rearrange iteration: {i+1}")

                # shrink because previous shrink run was successfull
                if not notSuccessRun:
                    failCounter = 0
                    # save previous run
                    generalFunctions.copyAndOverwrite(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}",
                                     f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}_temp_success")
                    pinDistance = pinDistanceTemp
                    pinOrderChangeTile = pinOrderChangeRun

                    # shrink
                    self.resizeTile(indexTile, False, False, False, resizeDim)
                    generalFunctions.writeLog([f"Current Height:{self.tilesToGenerateOL[indexTile].height} ; "
                                               f"Current Width:{self.tilesToGenerateOL[indexTile].width} ;"
                                               f"Current Density:{currentTileDensity}  [Try: shrink] \n"],
                                               logFile, "a")
                    logger.info(f"Current Height:{self.tilesToGenerateOL[indexTile].height} --- Current Width:{self.tilesToGenerateOL[indexTile].width} --- Current Density: {currentTileDensity} [Try: shrink]")

                    # move initial def and synthesis file
                    defFile = f"{self.openlaneDir}/designs/{tileName}/{tileName}.def"
                    synthesisFile = f"{self.openlaneDir}/designs/{tileName}/{tileName}.synthesis.v"
                    shutil.copyfile(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}/results/final/def/{tileName}.def", defFile)
                    shutil.copyfile(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}/results/synthesis/{tileName}.v", synthesisFile)

                    portPairs, noConnection = generalFunctions.generate_pin_pairs(synthesisFile, self.fabricGen, tileName)

                    # netlist rearrangment 
                    logger.info(f"start rearrange netlist for tile {tileName}")
                    nOpt = netListOpt.netListRearrange(defFile, synthesisFile, f"{self.projectDir}/Tile/{tileName}/{tileName}_ConfigMem")
                    nOpt.plotIteration(f"{self.openlaneDir}/designs/{tileName}/statistics/iteration_{i}")
                    nOpt.ConfigBitoptimizationWithAssignment()
                    nOpt.rewire_tile_netlist()

                    synthesisFile = f"{self.openlaneDir}/designs/{tileName}/{tileName}.synthesis.opt.v"  
                    
                    logger.info(f"start rearrange pins for tile {tileName}")
                    placement = pinOpt.placementRearrange(defFile, synthesisFile, f"{self.openlaneDir}/designs/{tileName}", pinSides, portPairs)
                    swapTable = placement.arrangePinPlacement(noConnection)
                    layerTable = placement.arrangePinLayer(swapTable)

                    # reset to first run state
                    firstRun = True

                    # prepare the pin combination dictionary
                    combinDict = {}
                    side = ["Top", "Bottom", "Left", "Right"]
                    for i in side:
                        l = {}
                        for j in range(1, 6):
                            l[j] = []
                        combinDict[i] = l

                    # put all the data into a single dictionary order by side
                    for p in placement.allPin:
                        layer = 0
                        for i in layerTable:
                            if p in layerTable[i]:
                                layer = i
                                break
                        if placement.allPin[p]["side"] in side:
                            combinDict[placement.allPin[p]["side"]][layer].append(p)

                    # keep initial order for not resized sides and take new calculated ones for resized sides 
                    combinDict, pinOrderChangeRun = generalFunctions.fixUpdateOrder(combinDict, initCombinDict, pinOrderChange, resizeDim, ioPos, isSuperTileColumn, "", False)

                    # generate new config file without pinorder.cfg and with synthesis source
                    logger.info("Generate new config file")
                    logger.info(f"Generate OpenLane config files for tile: {self.tilesToGenerateOL[indexTile].name}")
                    genConfig.generate_OpenLane_config(self.openlaneDir, self.tilesToGenerateOL[indexTile], self.macroConfig, False, currentTileDensity)

                    # edit ioplacer.tcl
                    logger.info("Define pinorder in ioplacer.tcl")
                    pinDistanceTemp = genConfig.ioPlace(self.tilesToGenerateOL[indexTile], combinDict, self.openlaneDir, prevPinDistances, resizeDim, ioPos, isSuperTileColumn)

                    # run openlane flow on the tiles
                    logger.info(f"Start OpenLane flow for tile: {tileName}")
                    tile_command = f"./flow.tcl -design {tileName} -tag {self.ol_run_name} -overwrite"
                    proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
                    proc.communicate(tile_command)
                    proc.stdout.close()
                    proc.terminate()
                    logger.info(f"OpenLane flow for {tileName} complete.")

                    # check for errors
                    notSuccessRun = generalFunctions.check_flow(self.openlaneDir, tileName, False, logger, self.ol_run_name)

                # re-run with same sizes because previous shrink run was unsuccessfull
                else:
                    failCounter += 1
                    if failCounter == 2:
                        currentTileDensity += self.densitySteps
                    # take temporary unfinished flow '.def'
                    defFile = f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}/results/placement/{tileName}.def"
                    synthesisFile = f"{self.openlaneDir}/designs/{tileName}/{tileName}.synthesis.opt.v"

                    generalFunctions.writeLog([f"Current Height:{self.tilesToGenerateOL[indexTile].height} ; Current Width:{self.tilesToGenerateOL[indexTile].width} ; Current Density:{currentTileDensity} [Try: re-order]\n"], logFile, "a")
                    logger.info(f"Current Height:{self.tilesToGenerateOL[indexTile].height} --- Current Width:{self.tilesToGenerateOL[indexTile].width} --- Current Density: {currentTileDensity} [Try: re-order]")
                    portPairs, noConnection = generalFunctions.generate_pin_pairs(synthesisFile, self.fabricGen, tileName)

                    # netlist rearrangment
                    logger.info(f"start rearrange netlist for tile {tileName}")
                    nOpt = netListOpt.netListRearrange(defFile, synthesisFile, f"{self.projectDir}/Tile/{tileName}/{tileName}_ConfigMem")
                    nOpt.ConfigBitoptimizationWithAssignment()
                    nOpt.rewire_tile_netlist()

                    # pin rearrangment
                    logger.info(f"start rearrange pins for tile {tileName}")
                    placement = pinOpt.placementRearrange(defFile, synthesisFile, f"{self.openlaneDir}/designs/{tileName}", pinSides, portPairs)
                    swapTable = placement.arrangePinPlacement(noConnection)
                    layerTable = placement.arrangePinLayer(swapTable)

                    # prepare the pin combination dictionary
                    combinDict = {}
                    side = ["Top", "Bottom", "Left", "Right"]
                    for i in side:
                        l = {}
                        for j in range(1, 6):
                            l[j] = []
                        combinDict[i] = l

                    # put all the data into a single dictionary order by side
                    for p in placement.allPin:
                        layer = 0
                        for i in layerTable:
                            if p in layerTable[i]:
                                layer = i
                                break
                        if placement.allPin[p]["side"] in side:
                            combinDict[placement.allPin[p]["side"]][layer].append(p)

                    # keep initial order for not resized sides and take new calculated ones for resized sides
                    combinDict, pinOrderChangeRun = generalFunctions.fixUpdateOrder(combinDict, initCombinDict, pinOrderChange, resizeDim, ioPos, isSuperTileColumn, "", False)

                    # generate new config file without pinorder.cfg and with synthesis source
                    logger.info("Generate new config file")
                    logger.info(f"Generate OpenLane config files for tile: {self.tilesToGenerateOL[indexTile].name}")
                    genConfig.generate_OpenLane_config(self.openlaneDir, self.tilesToGenerateOL[indexTile], self.macroConfig, False, currentTileDensity)

                    # edit ioplacer.tcl
                    logger.info("Define pinorder in ioplacer.tcl")
                    pinDistanceTemp = genConfig.ioPlace(self.tilesToGenerateOL[indexTile], combinDict, self.openlaneDir, prevPinDistances, resizeDim, ioPos, isSuperTileColumn)

                    # run openlane flow on the tiles
                    logger.info(f"Start OpenLane flow for tile: {tileName}")
                    tile_command = f"./flow.tcl -design {tileName} -tag {self.ol_run_name} -overwrite"
                    proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
                    proc.communicate(tile_command)
                    proc.stdout.close()
                    proc.terminate()
                    logger.info(f"OpenLane flow for {tileName} complete.")

                    # check for errors 
                    notSuccessRun = generalFunctions.check_flow(self.openlaneDir, tileName, False, logger, self.ol_run_name)

            logger.info(f"Resizing with optimizations for tile {tileName} finished")

            if notSuccessRun:  
                generalFunctions.copyAndOverwrite(f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}_temp_success",
                                                  f"{self.openlaneDir}/designs/{tileName}/runs/{self.ol_run_name}")
                pinDistance = pinDistanceTemp
                pinOrderChangeTile = pinOrderChangeRun
                # revert size
                self.resizeTile(indexTile, False, True, False, resizeDim)

            generalFunctions.writeLog([f"Finished Height:{self.tilesToGenerateOL[indexTile].height} ; Finished Width:{self.tilesToGenerateOL[indexTile].width} ; Finished Density: {currentTileDensity} \n",
                                       "----------------------------------------------------------------------------------------------------- \n"], logFile, "a")
            logger.info(f"Finished Height:{self.tilesToGenerateOL[indexTile].height} --- Finished Width:{self.tilesToGenerateOL[indexTile].width} --- Finished Density: {currentTileDensity}")
            nOpt.reset()
            placement.reset()
        else:
            # pinDistance = prevPinDistances  #TODO pin distance correction?
            pinOrderChangeTile = pinOrderChange
            if (cornerPos or ioPos or superColumn):
                pinOrderChangeTile = pinOrderChangeRun

        return pinDistance, pinOrderChangeTile

    # Generate all tiles in one specific column
    def propagateColumnInMap(self, columnIndex, initTileIndex, pinDistancePrevTile, pinOrderChangePrevTile, ioSide):
        fabricColumn = []
        generatedTiles = []
        ioTiles = {}
        isSuperColumn = False

        generatedTiles.append(self.tilesToGenerateOL[initTileIndex].name)
        generatedTiles.append("NULL")

        # read in column of fabric
        for tile in self.fabricTileMap:
            fabricColumn.append(tile[columnIndex])
        heightColumn = len(fabricColumn[1:])

        # go down in fabric column
        for index, item in enumerate(fabricColumn[1:]):
            index = index + 1
            # part of super tile
            if (item not in generatedTiles and index != heightColumn):
                # search for tile
                tileIndex: int
                for index, tile in enumerate(self.tilesToGenerateOL):
                    if tile.name == item:
                        tileIndex = index
                        break

                # change width and height to init tile in column
                self.tilesToGenerateOL[tileIndex].width = self.tilesToGenerateOL[initTileIndex].width
                self.tilesToGenerateOL[tileIndex].height = self.tilesToGenerateOL[initTileIndex].height

                # keep height and keep the width
                if self.getSupertileName(self.tilesToGenerateOL[tileIndex].name):
                    isSuperColumn = True

                self.resizeTileOptFlow(tileIndex, pinDistancePrevTile, "", ioSide, pinOrderChangePrevTile, isSuperColumn, "", False)
                generatedTiles.append(item)

                # check if generated tile size bigger for Supertile column. Regenerate all previous tiles with bigger size.
                if isSuperColumn:
                    errors = generalFunctions.check_flow(self.openlaneDir, self.tilesToGenerateOL[tileIndex].name, False, logger, self.ol_run_name)
                    if errors:
                        # rerun resizing on current tile
                        pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(tileIndex, pinDistancePrevTile, "Width", "", pinOrderChangePrevTile, False, "", False)
                        # change width 
                        self.tilesToGenerateOL[initTileIndex].width = self.tilesToGenerateOL[tileIndex].width
                        # regenerate previous tile
                        self.resizeTileOptFlow(initTileIndex, pinDistanceTile, "", ioSide, pinOrderChangeTile, isSuperColumn, "", False)

            # Terminate Tile
            elif item not in generatedTiles:
                # search for tile
                tileIndex: int
                for index, tile in enumerate(self.tilesToGenerateOL):
                    if tile.name == item:
                        tileIndex = index
                        break

                # change width to init tile and height to config
                self.tilesToGenerateOL[tileIndex].width = self.tilesToGenerateOL[initTileIndex].width
                self.tilesToGenerateOL[tileIndex].height = self.terminateTilesHeight

                # resize height but keep the width
                if ioSide:
                    ioSidetemp = ioSide
                else:
                    ioSidetemp = "Bottom"
                if self.getSupertileName(self.tilesToGenerateOL[tileIndex].name):
                    isSuperColumn = True
                pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(tileIndex, pinDistancePrevTile, "Height", ioSidetemp, pinOrderChangePrevTile, isSuperColumn, "Bottom", False)
                generatedTiles.append(item)
                ioTiles[item] = [pinDistanceTile, pinOrderChangeTile]

        # look if IO- / terminate-tile up in fabric
        if fabricColumn[0] not in generatedTiles:
            # search for tile
            tileIndex: int
            for index, tile in enumerate(self.tilesToGenerateOL):
                if tile.name == fabricColumn[0]:
                    tileIndex = index
                    break

            # change width to init tile and height to config
            self.tilesToGenerateOL[tileIndex].width = self.tilesToGenerateOL[initTileIndex].width
            self.tilesToGenerateOL[tileIndex].height = self.terminateTilesHeight

            if ioSide:
                ioSidetemp = ioSide
            else:
                ioSidetemp = "Top"
            if self.getSupertileName(self.tilesToGenerateOL[tileIndex].name):
                isSuperColumn = True
            pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(tileIndex, pinDistancePrevTile, "Height", ioSidetemp, pinOrderChangePrevTile, isSuperColumn, "Top", False)
            ioTiles[fabricColumn[0]] = [pinDistanceTile, pinOrderChangeTile]

        return generatedTiles, ioTiles

    def run(self):
        pinDistanceInitialTile = {}
        pinOrderChangeInitialTile = {}
        """

        # Generating Openlane Tile designs folder structure
        logger.info("Generating OpenLane Tile designs folder structure")
        openlane_make = f"cd {self.openlaneDir}; make mount"
        for tile in self.tilesToGenerateOL:
            proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
            tile_command = f"./flow.tcl -design {tile.name} -init_design_config -add_to_designs;"
            proc.communicate(tile_command)
            proc.stdout.close()
            proc.terminate()
        logger.info("Finish generating")

        # Move RTL from FABulous to Openlane folder structure
        logger.info("Moving Tile RTL to Openlane designs folder")
        for tile in self.tilesToGenerateOL:
            nameSuperTile = self.getSupertileName(tile.name)
            if nameSuperTile:
                tile_dir = f"{self.projectDir}/Tile/{nameSuperTile}/{tile.name}"
            else:
                tile_dir = f"{self.projectDir}/Tile/{tile.name}"
            for subdir, dirs, files in os.walk(tile_dir):
                for file in files:
                    if (file[-2:] == '.v'):
                        shutil.copyfile(os.path.join(tile_dir, file), f"{self.openlaneDir}/designs/{tile.name}/src/{file}")
            shutil.copyfile(os.path.join(f"{self.projectDir}/Test", "fabulous_tb.v"), f"{self.openlaneDir}/designs/{tile.name}/src/fabulous_tb.v")
            shutil.copyfile(os.path.join(f"{self.projectDir}/Fabric", "models_pack.v"), f"{self.openlaneDir}/designs/{tile.name}/src/models_pack.v")

        # ------------------------------------------------------------------------------------------------------------------------------
        # generate RAM (Current version just possible with the 1KB RAM)
        # ------------------------------------------------------------------------------------------------------------------------------
        if self.ramGenerate:
            # generate folder structure with OL
            logger.info("Generating OpenLane RAM macro folder structure")
            openlane_make = f"cd {self.openlaneDir}; make mount"
            proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
            tile_command = f"./flow.tcl -design {self.ramName} -init_design_config -add_to_designs;"
            proc.communicate(tile_command)
            proc.stdout.close()
            proc.terminate()
            logger.info("Finish generating")

            # modify folder structure for macro hardening
            try:
                os.makedirs(f"{self.openlaneDir}/designs/{self.ramName}/gds")
                os.makedirs(f"{self.openlaneDir}/designs/{self.ramName}/lef")
                os.makedirs(f"{self.openlaneDir}/designs/{self.ramName}/src/BB")
            except OSError:
                pass

            # move verilog and sky130 macro files to source
            shutil.copyfile(f"{self.pdkPath}/libs.ref/sky130_sram_macros/gds/sky130_sram_1kbyte_1rw1r_32x256_8.gds", f"{self.openlaneDir}/designs/{self.ramName}/gds/sky130_sram_1kbyte_1rw1r_32x256_8.gds")
            shutil.copyfile(f"{self.pdkPath}/libs.ref/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef", f"{self.openlaneDir}/designs/{self.ramName}/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef")
            shutil.copyfile(f"{self.pdkPath}/libs.ref/sky130_sram_macros/verilog/sky130_sram_1kbyte_1rw1r_32x256_8.v", f"{self.openlaneDir}/designs/{self.ramName}/src/BB/sky130_sram_1kbyte_1rw1r_32x256_8.v")
            shutil.copyfile(f"{self.noSupPath}/Fabric/{self.ramName}.v", f"{self.openlaneDir}/designs/{self.ramName}/src/{self.ramName}.v")

            # delete entries in io placer
            pinTcl = ["\n", "place_pins {*}$arg_list -random_seed 42 -hor_layers $HMETAL -ver_layers $VMETAL \n", "\n", "write"]
            f = open(f"{self.openlaneDir}/scripts/openroad/ioplacer.tcl")
            data = f.readlines()
            f.close()

            cutIndex = [i for i, s in enumerate(data) if 'place_pin' in s]
            if min(cutIndex):
                cutIndex = min(cutIndex)
                data = data[:cutIndex]
                data.extend(pinTcl)
                with open(f"{self.openlaneDir}/scripts/openroad/ioplacer.tcl", "w") as f:
                    f.writelines(data)
                    f.close()

            # modify RAM name
            f = open(f"{self.openlaneDir}/designs/{self.ramName}/src/{self.ramName}.v")
            data = f.readlines()
            f.close()
            for index, line in enumerate(data):
                data[index] = line.replace('sram_1rw1r_32_256_8_sky130', 'sky130_sram_1kbyte_1rw1r_32x256_8')
            with open(f"{self.openlaneDir}/designs/{self.ramName}/src/{self.ramName}.v", "w") as f:
                f.writelines(data)
                f.close()

            # modify RAM verilog (add "/// sta-blackbox")
            lineEdit = ["/// sta-blackbox \n"]
            f = open(f"{self.openlaneDir}/designs/{self.ramName}/src/BB/sky130_sram_1kbyte_1rw1r_32x256_8.v")
            data = f.readlines()
            f.close()
            lineEdit.extend(data)
            with open(f"{self.openlaneDir}/designs/{self.ramName}/src/BB/sky130_sram_1kbyte_1rw1r_32x256_8.v", "w") as f:
                f.writelines(lineEdit)
                f.close()

            # generate RAM config
            genConfig.ramMacroConfig(self.openlaneDir, self.ramName, self.ramHeight, self.ramWidth)

            # generate macro_placement.cfg
            with open(f"{self.openlaneDir}/designs/{self.ramName}/macro_placement.cfg", "w") as f:
                f.writelines("memory_cell 50 23 N")
                f.close()

            # run OL flow on RAM Tile
            logger.info("Start OpenLane flow for RAM")
            tile_command = f"./flow.tcl -design {self.ramName} -tag {self.ol_run_name} -overwrite"
            proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
            proc.communicate(tile_command)
            proc.stdout.close()
            proc.terminate()
            logger.info("OpenLane flow for RAM complete.")

        # ------------------------------------------------------------------------------------------------------------------------------
        # resize flow for initial tile
        # ------------------------------------------------------------------------------------------------------------------------------
        # run either flow with optimizations or without depending on optFlag
        logger.info(f"Generating tiles in OpenLane flow with tile resizing and start sizes defined in {self.configPath}")

        # run optimized resizing flow on starter tile
        pinDistanceInitialTile, pinOrderChangeInitialTile = self.resizeTileOptFlow(0, "", "Both", "", "", False, "", False)

        # ------------------------------------------------------------------------------------------------------------------------------
        # rest of the tiles in fabric
        # ------------------------------------------------------------------------------------------------------------------------------
        pinDistanceTile = {} 
        pinOrderChangeTile = {}
        terminateTilesInfo = {}
        finishedTiles = []
        tileColumn: int

        # find first column of starter tile in fabric
        for line in self.fabricTileMap:
            if self.tilesToGenerateOL[0].name in line:
                tileColumn = line.index(self.tilesToGenerateOL[0].name)
                break

        # go through init tile column
        finishedTilesTemp, terminateTiles = self.propagateColumnInMap(tileColumn, 0, pinDistanceInitialTile, pinOrderChangeInitialTile, "")
        finishedTiles.extend(finishedTilesTemp)
        terminateTilesInfo.update(terminateTiles)

        # propagate columns to the right of the starter tile to find min width of other columns
        for stepRight in range(tileColumn + 1, len(self.fabricTileMap[1])):
            # search for tile
            foundAt: int
            for index, tile in enumerate(self.tilesToGenerateOL):
                if tile.name == self.fabricTileMap[1][stepRight]:
                    foundAt = index
                    break
            # change width and height to init tile
            if self.fabricTileMap[1][stepRight] not in finishedTiles:
                self.tilesToGenerateOL[foundAt].height = self.tilesToGenerateOL[0].height
            # IO-Column
            if stepRight == (len(self.fabricTileMap[1])-1):
                pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(foundAt, pinDistanceInitialTile, "Width", "Right", pinOrderChangeInitialTile, False, "", False)
                finishedTilesTemp, unusedTerminateTiles = self.propagateColumnInMap(stepRight, foundAt, pinDistanceTile, pinOrderChangeTile, "Right")
                terminateTilesInfo.update(unusedTerminateTiles)
                finishedTiles.extend(finishedTilesTemp)
            # Normal Column
            elif self.fabricTileMap[1][stepRight] not in finishedTiles:
                pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(foundAt, pinDistanceInitialTile, "Width", "", pinOrderChangeInitialTile, False, "", False)
                finishedTilesTemp, terminateTiles = self.propagateColumnInMap(stepRight, foundAt, pinDistanceTile, pinOrderChangeTile, "")
                finishedTiles.extend(finishedTilesTemp)
                terminateTilesInfo.update(terminateTiles)

        # propagate columns to the left of the starter tile to find min width of other columns
        for stepLeft in reversed(range(0, tileColumn)):
            # search for tile
            foundAt: int
            for index, tile in enumerate(self.tilesToGenerateOL):
                if tile.name == self.fabricTileMap[1][stepLeft]:
                    foundAt = index
                    break
            # change width and height to init tile
            if self.fabricTileMap[1][stepLeft] not in finishedTiles:
                self.tilesToGenerateOL[foundAt].height = self.tilesToGenerateOL[0].height
            # IO-Column
            if stepLeft == 0:
                pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(foundAt, pinDistanceInitialTile, "Width", "Left", pinOrderChangeInitialTile, False, "", False)
                finishedTilesTemp, unusedTerminateTiles = self.propagateColumnInMap(stepLeft, foundAt, pinDistanceTile, pinOrderChangeTile, "Left")
                finishedTiles.extend(finishedTilesTemp)
                terminateTilesInfo.update(unusedTerminateTiles)
            # Normal Column  
            elif self.fabricTileMap[1][stepLeft] not in finishedTiles:
                pinDistanceTile, pinOrderChangeTile = self.resizeTileOptFlow(foundAt, pinDistanceInitialTile, "Width", "", pinOrderChangeInitialTile, False, "", False)
                finishedTilesTemp, terminateTiles = self.propagateColumnInMap(stepLeft, foundAt, pinDistanceTile, pinOrderChangeTile, "")
                finishedTiles.extend(finishedTilesTemp)
                terminateTilesInfo.update(terminateTiles)

        # ------------------------------------------------------------------------------------------------------------------------------
        # generate terminate tiles with same dimensions and pin order on sides
        # ------------------------------------------------------------------------------------------------------------------------------
        # max height for terminate north tiles
        heightTerminate = 0
        maxHeightTileIndex = 0
        terminateNorthTilesIndexes = []
        completedNorthTilesIndexes = []
        leftTileIndex = 0
        rightTileIndex = 0

        if self.fabricTileMap[0][0] != "NULL":
            # search for tile
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == self.fabricTileMap[0][0]:
                    leftTileIndex = index
                    break
        if self.fabricTileMap[0][-1] != "NULL":
            # search for tile
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == self.fabricTileMap[0][-1]:
                    rightTileIndex = index
                    break

        for tile in self.fabricTileMap[0]:
            if tile != "NULL":
                # search for tile
                foundAt: int
                for index, tileSearch in enumerate(self.tilesToGenerateOL):
                    if tileSearch.name == tile:
                        foundAt = index
                        break
                if heightTerminate < self.tilesToGenerateOL[foundAt].height:
                    heightTerminate = self.tilesToGenerateOL[foundAt].height
                    maxHeightTileIndex = foundAt
                terminateNorthTilesIndexes.append(foundAt)

        # generate all terminate north tiles with max height and pin order
        completedNorthTilesIndexes.append(maxHeightTileIndex)
        for tileIndex in terminateNorthTilesIndexes:
            if tileIndex not in completedNorthTilesIndexes:
                # change height to reference tile
                self.tilesToGenerateOL[tileIndex].height = heightTerminate

                # keep height and keep the width
                if tileIndex == leftTileIndex:
                    iopos = "Left"
                    cornerpos = "Top"
                elif tileIndex == rightTileIndex:
                    iopos = "Right"
                    cornerpos = "Top"
                else:
                    iopos = "Top"
                    cornerpos = ""

                # determine if special case of terminate tile and or supertile column
                isSuperColumn = False
                for index, tile in enumerate(self.fabricTileMap[0]):
                    if tile == self.tilesToGenerateOL[tileIndex].name:
                        underTile = self.fabricTileMap[1][index]
                if self.getSupertileName(underTile):
                    isSuperColumn = True
                if self.tilesToGenerateOL[tileIndex].name == self.fabricTileMap[0][0] or self.tilesToGenerateOL[tileIndex].name == self.fabricTileMap[0][-1]:
                    isSuperColumn = True

                self.resizeTileOptFlow(tileIndex, terminateTilesInfo[self.tilesToGenerateOL[tileIndex].name][0], "", iopos, terminateTilesInfo[self.tilesToGenerateOL[tileIndex].name][1], False, cornerpos, isSuperColumn)
                completedNorthTilesIndexes.append(tileIndex)

        # max height for terminate south tiles
        heightTerminate = 0
        maxHeightTileIndex = 0
        terminateSouthTilesIndexes = []
        completedSouthTilesIndexes = []
        leftTileIndex = 0
        rightTileIndex = 0

        if self.fabricTileMap[-1][0] != "NULL":
            # search for tile
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == self.fabricTileMap[0][0]:
                    leftTileIndex = index
                    break
        if self.fabricTileMap[-1][-1] != "NULL":
            # search for tile
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == self.fabricTileMap[0][-1]:
                    rightTileIndex = index
                    break

        for tile in self.fabricTileMap[-1]:
            if tile != "NULL":
                # search for tile
                foundAt: int
                for index, tileSearch in enumerate(self.tilesToGenerateOL):
                    if tileSearch.name == tile:
                        foundAt = index
                        break
                if heightTerminate < self.tilesToGenerateOL[foundAt].height:
                    heightTerminate = self.tilesToGenerateOL[foundAt].height
                    maxHeightTileIndex = foundAt
                terminateSouthTilesIndexes.append(foundAt)

        # generate all terminate south tiles with max height and pin order
        completedSouthTilesIndexes.append(maxHeightTileIndex)
        for tileIndex in terminateSouthTilesIndexes:
            if tileIndex not in completedSouthTilesIndexes:
                # change height to reference tile
                self.tilesToGenerateOL[tileIndex].height = heightTerminate

                # keep height and keep the width
                if tileIndex == leftTileIndex:
                    iopos = "Left"
                    cornerpos = "Bottom"
                elif tileIndex == rightTileIndex:
                    iopos = "Right"
                    cornerpos = "Bottom"
                else:
                    iopos = "Bottom"
                    cornerpos = ""

                isSuperColumn = False
                for index, tile in enumerate(self.fabricTileMap[-1]):
                    if tile == self.tilesToGenerateOL[tileIndex].name:
                        aboveTile = self.fabricTileMap[-2][index]
                if self.getSupertileName(aboveTile):
                    isSuperColumn = True
                if (self.tilesToGenerateOL[tileIndex].name == self.fabricTileMap[-1][0] or self.tilesToGenerateOL[tileIndex].name == self.fabricTileMap[-1][-1]):
                    isSuperColumn = True

                self.resizeTileOptFlow(tileIndex, terminateTilesInfo[self.tilesToGenerateOL[tileIndex].name][0], "", iopos, terminateTilesInfo[self.tilesToGenerateOL[tileIndex].name][1], False, cornerpos, isSuperColumn)
                completedSouthTilesIndexes.append(tileIndex)

        # delete entries in io placer
        pinTcl = ["\n", "place_pins {*}$arg_list -random_seed 42 -hor_layers $HMETAL -ver_layers $VMETAL \n", "\n", "write"]
        f = open(f"{self.openlaneDir}/scripts/openroad/ioplacer.tcl")
        data = f.readlines()
        f.close()

        cutIndex = [i for i, s in enumerate(data) if 'place_pin' in s]
        cutIndex = min(cutIndex)
        data = data[:cutIndex]
        data.extend(pinTcl)
        with open(f"{self.openlaneDir}/scripts/openroad/ioplacer.tcl", "w") as f:
            f.writelines(data)
            f.close()
        """
        # ------------------------------------------------------------------------------------------------------------------------------
        # fabric hardening
        # ------------------------------------------------------------------------------------------------------------------------------
        # generate fabric folder structure with OL
        logger.info("Generating OpenLane fabric macro folder structure")
        openlane_make = f"cd {self.openlaneDir}; make mount"
        proc = sp.Popen(openlane_make,shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
        tile_command = f"./flow.tcl -design {self.fabulousRunName} -init_design_config -add_to_designs;"
        proc.communicate(tile_command)
        proc.stdout.close()
        proc.terminate()

        # folder structure for hardening the core
        try:
            os.makedirs(f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros")
            os.makedirs(f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/gds")
            os.makedirs(f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/lef")
            os.makedirs(f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB")
        except OSError:
            pass

        # move gds, lef, verilog files
        for tile in self.tilesToGenerateOL:
            if tile.name != "NULL":
                shutil.copyfile(f"{self.openlaneDir}/designs/{tile.name}/runs/{self.ol_run_name}/results/final/verilog/gl/{tile.name}.v", f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB/{tile.name}.v")
                shutil.copyfile(f"{self.openlaneDir}/designs/{tile.name}/runs/{self.ol_run_name}/results/final/gds/{tile.name}.gds", f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/gds/{tile.name}.gds")
                shutil.copyfile(f"{self.openlaneDir}/designs/{tile.name}/runs/{self.ol_run_name}/results/final/lef/{tile.name}.lef", f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/lef/{tile.name}.lef")

        if self.ramGenerate:
            shutil.copyfile(f"{self.openlaneDir}/designs/{self.ramName}/runs/{self.ol_run_name}/results/final/verilog/gl/{self.ramName}.v", f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB/{self.ramName}.v")
            shutil.copyfile(f"{self.openlaneDir}/designs/{self.ramName}/runs/{self.ol_run_name}/results/final/gds/{self.ramName}.gds", f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/gds/{self.ramName}.gds")
            shutil.copyfile(f"{self.openlaneDir}/designs/{self.ramName}/runs/{self.ol_run_name}/results/final/lef/{self.ramName}.lef", f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/lef/{self.ramName}.lef")

        # move eFPGA fabric verilog files
        for subdir, dirs, files in os.walk(f"{self.noSupPath}/Fabric"):
            for file in files:
                if file != "BlockRAM_1KB.v":
                    shutil.copyfile(os.path.join(f"{self.noSupPath}/Fabric", file), f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/{file}")

        # calculate fabric height
        fabricTileHeightTotal = 0
        rowNum = 0
        tileHeights = []
        for tile in self.fabricTileMap:
            # search for tile
            foundAt: int
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == tile[1]:
                    foundAt = index
                    break
            # find tile width
            fabricTileHeightTotal += self.tilesToGenerateOL[foundAt].height
            tileHeights.append(self.tilesToGenerateOL[foundAt].height)
            rowNum += 1

        # calculate fabric width
        fabricTileWidthTotal = 0
        columnNum = 0
        tileWidths = []
        for tile in self.fabricTileMap[1]:
            # search for tile
            foundAt: int
            for index, tileSearch in enumerate(self.tilesToGenerateOL):
                if tileSearch.name == tile:
                    foundAt = index
                    break
            # find tile width
            fabricTileWidthTotal += self.tilesToGenerateOL[foundAt].width
            tileWidths.append(self.tilesToGenerateOL[foundAt].width)
            columnNum += 1

        # generate macro_placement.cfg
        configTilePlacement = ""
        macroHooks = "["
        #xStep = fabricWidth / columnNum
        #yStep = fabricHeight / rowNum
        heightPos = fabricTileHeightTotal + self.marginFab + self.marginFabCore + (rowNum -1) * self.marginTiles
        for y, column in enumerate(self.fabricTileMap):
            widthPos = self.marginFabCore + self.marginFab
            #heightPos -= tileHeights[y]
            for x, tile in enumerate(column):
                if tile != "NULL":
                    configTilePlacement += f"eFPGA_inst.Tile_X{x}Y{y}_{tile} {widthPos} {heightPos} N \n"
                    macroHooks += f"\"eFPGA_inst.Tile_X{x}Y{y}_{tile} vccd1 vssd1 vccd1 vssd1,\","
                widthPos += (tileWidths[x] + self.marginTiles)
            heightPos -= (self.marginTiles + tileHeights[y])

        # RAM placement
        if self.ramGenerate:
            ramBlocksCount = int(fabricTileHeightTotal / (self.ramHeight + self.marginRAM))

            heightPos += fabricTileHeightTotal + self.marginFab + self.marginFabCore + (rowNum -1) * self.marginTiles
            #self.ramHeight + self.marginRAM
            maxWidthPos = self.marginFabCore + self.marginFab + fabricTileWidthTotal + ((rowNum -1) * self.marginTiles) + self.marginRAM
            for i in range(ramBlocksCount):
                heightPos -= self.ramHeight
                configTilePlacement += f"Inst_BlockRAM_{i} {maxWidthPos + self.marginRAM} {heightPos} N \n"
                macroHooks += f"\"Inst_BlockRAM_{i} vccd1 vssd1 vccd1 vssd1,\","
                heightPos -= self.marginRAM
        else:
            self.ramWidth = 0
            self.marginRAM = 0

        macroHooks = macroHooks[:-1] + "]"
        with open(f"{self.openlaneDir}/designs/{self.fabulousRunName}/macros/macro_placement.cfg", "w") as f:
            f.writelines(configTilePlacement)
            f.close()

        # change height and width because of halo between tiles
        fabricTileHeightTotal += (rowNum -1) * self.marginTiles 
        fabricTileWidthTotal += (rowNum -1) * self.marginTiles

        # generate config.json for faric macro
        tileNames = []
        for tile in self.tilesToGenerateOL:
            tileNames.append(tile.name)
        logger.info(f"Generate OpenLane core config files for core: {self.fabulousRunName}")
        genConfig.generateCoreConfig(self.openlaneDir, self.fabulousRunName, fabricTileHeightTotal, fabricTileWidthTotal + self.marginRAM, tileNames, macroHooks, self.marginFabCore, self.marginFab, self.ramWidth, self.coreConfig, self.fabulousRunName, self.targetDensity, self.marginRAM)

        # add black box comment to black box files to avoid STA check
        for subdir, dirs, files in os.walk(f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB"):
            for file in files:
                src = open(f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB/{file}", "r")
                staLine = "/// sta-blackbox \n"
                data = src.readlines()
                data.insert(0, staLine)
                src.close()
                src = open(f"{self.openlaneDir}/designs/{self.fabulousRunName}/src/BB/{file}", "w")
                src.writelines(data)
                src.close()
                
        # cut STA 
        f = open(f"{self.openlaneDir}/scripts/tcl_commands/synthesis.tcl") 
        data = f.readlines()
        f.close()

        cutIndex = [i for i, s in enumerate(data) if 'run_sta' in s]
        cutIndex = min(cutIndex)
        for index, line in enumerate(data[cutIndex:]):
            if line.rstrip():
                data[cutIndex + index] = "#" + data[cutIndex + index]
            else:
                break

        with open(f"{self.openlaneDir}/scripts/tcl_commands/synthesis.tcl","w") as f:
            f.writelines(data)
            f.close()

        # run OL flow on fabric
        logger.info(f"Start OpenLane flow for fabric {self.fabulousRunName}")
        tile_command = f"./flow.tcl -design {self.fabulousRunName} -tag {self.ol_run_name} -overwrite"
        proc = sp.Popen(openlane_make, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, encoding='utf8')
        proc.communicate(tile_command)
        proc.stdout.close()
        proc.terminate()
        logger.info(f"OpenLane flow for fabric {self.fabulousRunName} complete.")

        # change makefile of OpenLane to enable graphics for user again
        f = open(f"{self.openlaneDir}/Makefile")
        data = f.readlines()
        f.close()
        searchLine = "$(ENV_START) -i $(OPENLANE_IMAGE_NAME)-$(DOCKER_ARCH)"

        for i, line in enumerate(data):
            if searchLine in line:
                data[i] = line.replace("-i", "-ti")
        with open(f"{self.openlaneDir}/Makefile", "w") as f:
            f.writelines(data)
            f.close()

        # reverse comment STA check
        f = open(f"{self.openlaneDir}/scripts/tcl_commands/synthesis.tcl")
        data = f.readlines()
        f.close()

        cutIndex = [i for i, s in enumerate(data) if '#    run_sta' in s]
        cutIndex = min(cutIndex)
        for index, line in enumerate(data[cutIndex:]):
            if line.rstrip():
                data[cutIndex + index] = data[cutIndex + index][1:]
            else:
                break

        with open(f"{self.openlaneDir}/scripts/tcl_commands/synthesis.tcl","w") as f:
            f.writelines(data)
            f.close()
