import configparser


# generate config.json file for a OpenLane tile,
# small needed difference between initial automatic run and follow ups
def generate_OpenLane_config(openlaneDir, tile, macroConfig, initial_run,
                             density):
    # flow depandent configuration values
    if initial_run:
        configText = [
            "{\n", f"\"DESIGN_NAME\": \"{tile.name}\",\n",
            "\"VERILOG_FILES\": \"dir::src/*.v\",\n",
            "\"FP_SIZING\": \"absolute\",\n",
            f"\"DIE_AREA\": \"0 0 {tile.width}.0 {tile.height}.0\",\n",
            f"\"CORE_AREA\": \"5 5 {tile.width - 5}.0 {tile.height - 5}.0\",\n",
            "\"FP_PDN_CORE_RING\": 0,\n", "\"RT_MAX_LAYER\": \"met4\",\n"
        ]
    else:
        configText = [
            "{\n", f"\"DESIGN_NAME\": \"{tile.name}\",\n",
            f"\"VERILOG_FILES\": \"dir::{tile.name}.synthesis.opt.v\",\n",
            "\"SYNTH_READ_BLACKBOX_LIB\": true,\n",
            "\"SYNTH_ELABORATE_ONLY\": true,\n",
            "\"FP_SIZING\": \"absolute\",\n",
            f"\"DIE_AREA\": \"0 0 {tile.width}.0 {tile.height}.0\",\n",
            f"\"CORE_AREA\": \"5 5 {tile.width - 5}.0 {tile.height - 5}.0\",\n"
            "\"FP_PDN_CORE_RING\": 0,\n", "\"RT_MAX_LAYER\": \"met4\",\n"
        ]

    # user defined configuration values
    if tile.name in macroConfig:
        for configLine in macroConfig[tile.name]:
            configText.append(
                f"\"{configLine}\": {macroConfig[tile.name][configLine]},\n")
    else:
        default = "DEFAULT"
        for configLine in macroConfig[default]:
            configText.append(
                f"\"{configLine}\": {macroConfig[default][configLine]},\n")
    configText.append("\"FP_PDN_MULTILAYER\": \"false\",\n")
    configText.append(f"\"PL_TARGET_DENSITY\": {density}\n")
    configText.append("}")

    with open(f"{openlaneDir}/designs/{tile.name}/config.json", "w") as f:
        f.writelines(configText)
        f.close()


# generate config.json file for whole OpenLane core
def generateCoreConfig(openlaneDir, coreName, tileHeightArea, tileWidthArea, tiles, hooks,
                       marginFABCore, marginFab, ramWidth, coreConfig,
                       designName, density, marginRAM):
    # flow depandent configuration values
    gds = ""
    lefs = ""
    for tileName in tiles:
        if tileName != "NULL":
            gds += f"\"dir::macros/gds/{tileName}.gds\", "
            lefs += f"\"dir::macros/lef/{tileName}.lef\", "
    gds += "\"dir::macros/gds/BlockRAM_1KB.gds\""
    lefs += "" "\"dir::macros/lef/BlockRAM_1KB.lef\""

    configText = [
        "{\n", f"\"DESIGN_NAME\": \"eFPGA_top\",\n",
        "\"VERILOG_FILES\": \"dir::src/*.v\",\n",
        "\"VERILOG_FILES_BLACKBOX\": \"dir::src/BB/*.v\",\n",
        f"\"DIE_AREA\": \"0 0 {tileWidthArea + 2*(marginFABCore+marginFab) + ramWidth + marginRAM}.0 {tileHeightArea + 2*(marginFABCore+ marginFab)}.0\",\n",
        f"\"CORE_AREA\": \"{marginFABCore}.0 {marginFABCore}.0 {tileWidthArea + marginFABCore + 2*marginFab + marginRAM}.0 {tileHeightArea + marginFABCore + 2*marginFab}.0\",\n",
        "\"MACRO_PLACEMENT_CFG\": \"dir::macros/macro_placement.cfg\",\n",
        f"\"EXTRA_LEFS\": [{lefs}],\n", f"\"EXTRA_GDS_FILES\": [{gds}],\n",
        "\"FP_PDN_MULTILAYER\": 1,\n"
    ]

    # user defined configuration values
    for configLine in coreConfig:
        configText.append(
            f"\"{configLine}\": {coreConfig[configLine]},\n")
    #configText.append(f"\"FP_PDN_MACRO_HOOKS\": {hooks}")  
    configText.append(f"\"PL_TARGET_DENSITY\": {density}\n")
    configText.append("}")

    with open(f"{openlaneDir}/designs/{coreName}/config.json", "w") as f:
        f.writelines(configText)
        f.close()


# generate config.json file for OpenLane RAM
def ramMacroConfig(openlaneDir, name, height, width):
    configText = [
        "{\n", f"\"DESIGN_NAME\": \"{name}\",\n",
        "\"VERILOG_FILES\": \"dir::src/*.v\",\n",
        "\"VERILOG_FILES_BLACKBOX\": \"dir::src/BB/*.v\",\n",
        "\"CLOCK_PORT\": \"clk\",\n", "\"CLOCK_PERIOD\": 40,\n",
        "\"FP_PDN_MULTILAYER\": false,\n", "\"FP_SIZING\": \"absolute\",\n",
        f"\"DIE_AREA\": \"0 0 {width} {height}\",\n",
        "\"MACRO_PLACEMENT_CFG\": \"dir::macro_placement.cfg\",\n",
        "\"EXTRA_LEFS\": \"dir::lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef\",\n",
        "\"EXTRA_GDS_FILES\": \"dir::gds/sky130_sram_1kbyte_1rw1r_32x256_8.gds\",\n",
        "\"VDD_NETS\": [\"vccd1\"],\n", "\"GND_NETS\": [\"vssd1\"],\n",
        "\"RT_MAX_LAYER\": \"met4\",\n", "\"FP_PDN_CORE_RING\": 0,\n",
        "\"RUN_LVS\": 0\n", "}"
    ]
    with open(f"{openlaneDir}/designs/{name}/config.json", "w") as f:
        f.writelines(configText)
        f.close()


# generate initial config for automatic script
def generateAutoConfig(configName):
    configText = configparser.ConfigParser()
    configText.optionxform = str
    configText["General"] = {
        "OpenLane_path": "/path/to/OpenLane",
        "FABuloSupertileFreeRunPathus_path":
        "/path/to/FABulous/run/just/with/subtiles",
        "PDKPath": "/home/user/.volare/sky130A",
        "StarterTile": "LUT4AB",
        "ResizeTilesOptimizations": "True",
        "ResizeOptimizationsIterations": "20",
        "DensityStepsPercent": "2",
        "OpenLaneRunName": "automatic_run",
        "FABulousRunName": "eFPGA",
        "RAMEnable": "False",
        "MarginTiles": "20",
        "MarginFab": "30",
        "MarginFabCore": "10",
        "GenerateRTL": "True",
        "TargetDensityStart": "0.6",
        "TerminateTilesStartHeight": "100.0",
        "MarginRAM": "100"
    }
    configText["Dimensions"] = {
        "StarterTileWidth": "270",
        "StarterTileHeight": "270",
        "LUT4AB_Width": "200",
        "False_Width": "200"
    }
    configText["OpenLaneMacro_DEFAULT"] = {
        "CLOCK_PORT": "\"UserCLK\"",
        "CLOCK_PERIOD": "40",
        "FP_IO_VLENGTH": "0.7",
        "FP_IO_HLENGTH": "0.7",
        "VDD_NETS": "[\"vccd1\"]",
        "GND_NETS": "[\"vssd1\"]",
        "FP_IO_HLAYER": "\"met3\"",
        "FP_IO_VLAYER": "\"met2\"",
        "FP_IO_MIN_DISTANCE": "1"
    }
    configText["OpenLaneMacro_TileName"] = {
        "CLOCK_PORT": "\"UserCLK\"",
        "CLOCK_PERIOD": "40",
        "FP_IO_VLENGTH": "0.7",
        "FP_IO_HLENGTH": "0.7",
        "VDD_NETS": "[\"vccd1\"]",
        "GND_NETS": "[\"vssd1\"]",
        "FP_IO_HLAYER": "\"met3\"",
        "FP_IO_VLAYER": "\"met2\"",
        "FP_IO_MIN_DISTANCE": "1"
    }
    configText["OpenLaneCore"] = {
        "PDK": "\"sky130A\"",
        "CLOCK_PORT": "\"CLK\"",
        "CLOCK_PERIOD": "80",
        "SYNTH_NO_FLAT": "1",
        "FP_SIZING": "absolute",
        "VDD_NETS": "[\"vccd1\"]",
        "GND_NETS": "[\"vssd1\"]",
        "FP_IO_VEXTEND": "4.8",
        "FP_IO_HEXTEND": "4.8",
        "FP_IO_VLENGTH": "0.7",  # 2.4
        "FP_IO_HLENGTH": "0.7",  # 2.4
        "FP_IO_VTHICKNESS_MULT": "4",
        "FP_IO_HTHICKNESS_MULT": "4",
        "FP_IO_MIN_DISTANCE": "1",
        "FP_PDN_CORE_RING": "1",
        "FP_PDN_CORE_RING_VWIDTH": "1.6",  # 3.1
        "FP_PDN_CORE_RING_HWIDTH": "1.6",  # 3.1
        "FP_PDN_CORE_RING_VOFFSET": "1.6",  # 14
        "FP_PDN_CORE_RING_HOFFSET": "1.6",  # 14
        "FP_PDN_CORE_RING_VSPACING": "1.6",  # 1.7
        "FP_PDN_CORE_RING_HSPACING": "1.6",  # 1.7
        "PL_TARGET_DENSITY": "0.7"
    }
    with open(configName, "w") as f:
        configText.write(f)
        f.close()


# rewrite ioplacer.tcl to place pins at fixed positions and metal layers
def ioPlace(tile, combinDict, openlaneDir, prevPosGrid, resize, ioSide,
            isSuperTile):
    margin = 5
    pinWidth = 0.38
    pinDepth = 0.7
    maxHeight = tile.height - margin * 2
    maxWidth = tile.width - margin * 2
    posGrid = {}

    # edit ioplacer.tcl
    placerTcl = []
    for side in combinDict:
        posGrid[side] = []
        for layer in combinDict[side]:
            distanceBetweenPins: float = 0
            position: float = 0
            # should be multiple of 5 (MANUFACTURINGGRID 0.005)
            if resize == 'Both':
                if side in ['Top', 'Bottom']:
                    distanceBetweenPins = round(
                        ((maxWidth - 2) / (len(combinDict[side][layer]) + 1)),
                        2)
                else:
                    distanceBetweenPins = round(
                        ((maxHeight - 2) / (len(combinDict[side][layer]) + 1)),
                        2)

            elif resize == 'Height':
                if side in ['Top', 'Bottom']:
                    distanceBetweenPins = prevPosGrid[side]
                    if isSuperTile:
                        if side == "Top":
                            distanceBetweenPins = prevPosGrid["Bottom"]
                        elif side == "Bottom":
                            distanceBetweenPins = prevPosGrid["Top"]
                    if side == ioSide:
                        distanceBetweenPins = round(
                            ((maxWidth - 2) /
                             (len(combinDict[side][layer]) + 1)), 2)
                else:
                    distanceBetweenPins = round(
                        ((maxHeight - 2) / (len(combinDict[side][layer]) + 1)),
                        2)

            elif resize == 'Width':
                if side in ['Top', 'Bottom']:
                    distanceBetweenPins = round(
                        ((maxWidth - 2) / (len(combinDict[side][layer]) + 1)),
                        2)
                else:
                    distanceBetweenPins = prevPosGrid[side]
                    if side == ioSide:
                        distanceBetweenPins = round(
                            ((maxHeight - 2) /
                             (len(combinDict[side][layer]) + 1)), 2)

            elif not resize:
                # only for terminate tiles last height iteration loop
                # through all terminate tiles
                if not prevPosGrid:
                    if side in ['Top', 'Bottom']:
                        distanceBetweenPins = round(
                            ((maxWidth - 2) /
                             (len(combinDict[side][layer]) + 1)), 2)
                    else:
                        distanceBetweenPins = round(
                            ((maxHeight - 2) /
                             (len(combinDict[side][layer]) + 1)), 2)
                # Super tiles and no resize
                else:
                    if side in ['Top', 'Bottom']:
                        distanceBetweenPins = prevPosGrid[side]
                    else:
                        distanceBetweenPins = prevPosGrid[side]
                    if isSuperTile:
                        if side == "Top":
                            distanceBetweenPins = prevPosGrid["Bottom"]
                        elif side == "Bottom":
                            distanceBetweenPins = prevPosGrid["Top"]
                        else:
                            distanceBetweenPins = prevPosGrid[side]

            for pin in combinDict[side][layer]:
                position = position + distanceBetweenPins

                if pin != "NULL":
                    if side == 'Top':
                        pinTcl = [
                            "\n",
                            f"place_pin -pin_name {pin} -layer met{layer} -location {{{position + margin + 1} {maxHeight + margin * 2}}} -pin_size {{{pinWidth} {pinDepth}}} -force_to_die_boundary  \n"
                        ]
                    elif side == 'Bottom':
                        pinTcl = [
                            "\n",
                            f"place_pin -pin_name {pin} -layer met{layer} -location {{{position + margin + 1} {0}}} -pin_size {{{pinWidth} {pinDepth}}} -force_to_die_boundary  \n"
                        ]
                    elif side == 'Left':
                        pinTcl = [
                            "\n",
                            f"place_pin -pin_name {pin} -layer met{layer} -location {{{0} {position + margin + 1}}} -pin_size {{{pinDepth} {pinWidth}}} -force_to_die_boundary  \n"
                        ]
                    elif side == 'Right':
                        pinTcl = [
                            "\n",
                            f"place_pin -pin_name {pin} -layer met{layer} -location {{{maxWidth + margin * 2} {position + margin + 1}}} -pin_size {{{pinDepth} {pinWidth}}} -force_to_die_boundary   \n"
                        ]
                    placerTcl.extend(pinTcl)

            posGrid[side] = distanceBetweenPins
    pinTcl = [
        "\n",
        "place_pins {*}$arg_list -random_seed 42 -hor_layers $HMETAL -ver_layers $VMETAL \n",
        "\n", "write"
    ]
    placerTcl.extend(pinTcl)

    f = open(f"{openlaneDir}/scripts/openroad/ioplacer.tcl")
    data = f.readlines()
    f.close()

    # replace place_pins with generated placement
    cutIndex = [i for i, s in enumerate(data) if 'place_pin' in s]
    if min(cutIndex):
        cutIndex = min(cutIndex)
        data = data[:cutIndex]
    data.extend(placerTcl)
    with open(f"{openlaneDir}/scripts/openroad/ioplacer.tcl", "w") as f:
        f.writelines(data)
        f.close()

    return posGrid
