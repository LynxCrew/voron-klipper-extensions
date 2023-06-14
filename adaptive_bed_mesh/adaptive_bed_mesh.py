# Klipper Adaptive Bed Mesh
#
# Copyright (C) 2023 Mitko Haralanov <voidtrance@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import math
import logging
import random
import gcode


class Point:
    def __init__(self, x, y):
        self.x = round(x, 5)
        self.y = round(y, 5)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __str__(self):
        return "%.02f,%.02f" % (self.x, self.y)


class PrintObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class AdaptiveMeshConfig:
    pass


class AdaptiveBedMesh:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")
        gcode_macro = self.printer.lookup_object("gcode_macro")
        self.prefix = gcode_macro.load_template(config, "start_gcode", "")
        self.suffix = gcode_macro.load_template(config, "end_gcode", "")
        self.gcode.register_command("ADAPTIVE_BED_MESH",
                                    self.cmd_ADAPTIVE_BED_MESH,
                                    False,
                                    desc=self.cmd_ADAPTIVE_BED_MESH_help)
        self.config = AdaptiveMeshConfig()
        self.config.relative_index = config.getboolean("relative_rri", False)
        self.config.cutoff = config.getfloat("cutoff_limit", 10.0,
                                             minval=1.0, maxval=50.0)
        self.config.margin = config.getfloat("margin", 0.0, minval=0.)
        self.config.fuzz_limit = config.getfloatlist("fuzz_limits",
                                                     (0.0, 0.0),
                                                     count=2)
        if self.config.fuzz_limit[1] > 3.0:
            raise config.error("Upper fuzz limit should be <= 3.0mm.")
        random.seed()

    def get_printed_objects(self, objects):
        logging.info("Objects: %s" % objects)
        printed_objects = []
        for obj in objects:
            box = []
            for coord in obj["polygon"]:
                box.append(Point(coord[0], coord[1]))
            printed = PrintObject(name=obj["name"],
                                  center=Point(*obj["center"]),
                                  box=box)
            printed_objects.append(printed)
        return printed_objects

    def get_print_area(self, objects, margin):
        min_x = min([99999] + [p.x for obj in objects for p in obj.box])
        min_y = min([99999] + [p.y for obj in objects for p in obj.box])
        max_x = max([0] + [p.x for obj in objects for p in obj.box])
        max_y = max([0] + [p.y for obj in objects for p in obj.box])

        min_x = max(0, min_x - margin)
        max_x = min(self.config.bed_size.x, max_x + margin)
        min_y = max(0, min_y - margin)
        max_y = min(self.config.bed_size.y, max_y + margin)
        return [Point(min_x, min_y), Point(min_x, max_y), Point(max_x, max_y), Point(max_x, min_y)]

    def get_adapted_bed_mesh_area(self, area):
        def fuzzer(value, minval=0, maxval=99999):
            fuzz = round(random.uniform(self.config.fuzz_limit[0],
                                        self.config.fuzz_limit[1]), 3)
            sign = random.choice([1, -1])
            new_value = value + (fuzz * sign)
            if value < minval or value > maxval:
                new_value = value + (fuzz * sign * -1)
            return new_value
        min_x = max(area[0].x, self.config.mesh_min.x)
        max_x = min(area[2].x, self.config.mesh_max.x)
        min_y = max(area[0].y, self.config.mesh_min.y)
        max_y = min(area[2].y, self.config.mesh_max.y)

        # Apply mesh area fuzzing
        min_x = fuzzer(min_x, self.config.orig_config["mesh_min"][0])
        min_y = fuzzer(min_y, self.config.orig_config["mesh_min"][1])
        max_x = fuzzer(max_x, self.config.orig_config["mesh_max"][0])
        max_y = fuzzer(max_y, self.config.orig_config["mesh_max"][1])
        return [Point(min_x, min_y), Point(min_x, max_y), Point(max_x, max_y), Point(max_x, min_y)]

    def compute_rri(self, mesh):
        if self.config.relative_index:
            rri_index = -1
            rri_distance = 999999
            for index, point in enumerate(mesh.kmesh.bmc.points):
                dx = abs(point[0] - mesh.adaptive.current_rri_coord[0])
                dy = abs(point[1] - mesh.adaptive.current_rri_coord[1])
                distance = (dx ** 2 + dy ** 2) ** 0.5
                if distance < rri_distance:
                    rri_index = index
                    rri_distance = distance
            if rri_index != -1:
                return rri_index
            else:
                return mesh.kmesh.bmc.relative_reference_index
        else:
            return int((mesh.adaptive.probes.x * mesh.adaptive.probes.y) / 2)

    def run_mesh(self, mesh, gcmd):
        mesh.kmesh.set_mesh(None)
        mesh.adaptive.current_rri_coord = mesh.kmesh.bmc.points[
            mesh.kmesh.bmc.relative_reference_index]
        mesh.kmesh.bmc.update_config(gcmd)
        mesh.kmesh.bmc.relative_reference_index = self.compute_rri(mesh)
        # Adaptive bed mesh does not support saving to named profiles
        mesh.kmesh.bmc._profile_name = "default"
        if self.prefix:
            script = self.prefix.render()
            self.gcode.run_script_from_command(script)
        mesh.kmesh.bmc.probe_helper.start_probe(gcmd)
        if self.suffix:
            script = self.suffix.render()
            self.gcode_run_script_from_command(script)

    cmd_ADAPTIVE_BED_MESH_help = "Adaptive Bed Mesh"

    def cmd_ADAPTIVE_BED_MESH(self, gcmd):
        cutoff = gcmd.get_float("CUTOFF_LIMIT", self.config.cutoff) / 100.0
        margin = gcmd.get_float("MARGIN", self.config.margin)
        exclude_objects = self.printer.lookup_object("exclude_object")
        mesh = AdaptiveMeshConfig()
        mesh.adaptive = AdaptiveMeshConfig()
        mesh.kmesh = self.printer.lookup_object("bed_mesh")
        objects = self.get_printed_objects(exclude_objects.objects)
        if not objects:
            self.run_mesh(mesh, gcmd)
            return

        reactor = self.printer.get_reactor()
        mesh.min = Point(*mesh.kmesh.bmc.mesh_min)
        mesh.max = Point(*mesh.kmesh.bmc.mesh_max)
        mesh.orig_config = mesh.bmc.orig_config
        logging.info("%s / %s" % (mesh.min, mesh.max))
        mesh.size = Point(mesh.max.x - mesh.min.x, mesh.max.y - mesh.min.y)
        logging.info("%s" % mesh.size)
        printer_config = self.printer.lookup_object("configfile")
        settings = printer_config.get_status(reactor.monotonic())["settings"]
        self.config.bed_size = Point(settings["stepper_x"]["position_max"],
                                     settings["stepper_y"]["position_max"])

        print_area = self.get_print_area(objects, margin)
        gcmd.respond_info("Print area: [%s]" %
                          ",".join(["[%s]" % x for x in print_area]))
        mesh.adaptive.area = self.get_adapted_bed_mesh_area(print_area)
        gcmd.respond_info("Adapted mesh area: [%s]" %
                          ",".join(["[%s]" % x for x in mesh.adaptive.area]))
        mesh.adaptive.size = Point(mesh.adaptive.area[2].x - mesh.adaptive.area[0].x,
                                   mesh.adaptive.area[2].y - mesh.adaptive.area[0].y)
        if mesh.adaptive.area[0] == self.config.mesh_min and \
                mesh.adaptive.area[2] == self.config.mesh_max:
            self.run_mesh(mesh, gcmd)
            return

        ratio = Point(mesh.adaptive.size.x / mesh.size.x,
                      mesh.adaptive.size.y / mesh.size.y)
        gcmd.respond_info("Ratio: [%s] / [%s] -> [%s]" %
                          (str(mesh.adaptive.size), str(mesh.size), str(ratio)))
        if ratio.x <= cutoff and ratio.y <= cutoff:
            gcmd.respond_info("Ratio less than cutoff. No mesh needed.")
            return

        mesh.adaptive.probes = Point(math.ceil(mesh.kmesh.bmc.mesh_config['x_count'] * ratio.x),
                                     math.ceil(mesh.kmesh.bmc.mesh_config['y_count'] * ratio.y))

        # Ensure that there are at least 3 probe points per axis
        mesh.adaptive.probes.x = max(mesh.adaptive.probes.x, 3)
        mesh.adaptive.probes.y = max(mesh.adaptive.probes.y, 3)
        mesh.adaptive.probes.x += 1 - (mesh.adaptive.probes.x % 2)
        mesh.adaptive.probes.y += 1 - (mesh.adaptive.probes.y % 2)
        gcmd.respond_info("Adapted probe counts: %s" % mesh.adaptive.probes)

        algorithm = mesh.kmesh.bmc.mesh_config['algo']
        probe_count_limits = {'lagrange': (0, 6), 'bicubic': (4, 9999)}
        if min(mesh.adaptive.probes.x, mesh.adaptive.probes.y) < probe_count_limits[algorithm][0] or \
                max(mesh.adaptive.probes.x, mesh.adaptive.probes.y) > probe_count_limits[algorithm][1]:
            idx = list(probe_count_limits.keys()).index(algorithm)
            algorithm = list(probe_count_limits.keys())[1 - idx]

        # Set BedMeshCalibrate object configuration
        params = {"ALGORITHM": algorithm}

        if mesh.bmc.radius is None:
            params.update({"MESH_MIN": str(mesh.adaptive.area[0]),
                           "MESH_MAX": str(mesh.adaptive.area[2]),
                           "PROBE_COUNT": "%s,%s" % (int(mesh.adaptive.probes.x),
                                                     int(mesh.adaptive.probes.y))})
        else:
            # For round beds, compute the radius by taking half the
            # mesh area diagonal.
            radius = round(math.sqrt(mesh.adaptive.size.x ** 2 +
                                     mesh.adaptive.size.y ** 2) / 2,
                           3)
            params.update({"MESH_RADIUS": str(radius),
                           "MESH_ORIGIN": "%s,%s" % (str(mesh.adaptive.area[0].x +
                                                         (mesh.adaptive.size.x / 2)),
                                                     str(mesh.adaptive.area[0].y +
                                                         (mesh.adaptive.size.y / 2))),
                          "ROUND_PROBE_COUNT": str(max(mesh.adaptive.probes.x,
                                                       mesh.adaptive.probes.y))})
        cmdline = " ".join(["BED_MESH_CALIBRATE"] +
                           ["%s=%s" % (k, v) for k, v in params.items()])
        gcmd.respond_info("GCode command: %s" % cmdline)
        _cmd = gcode.GCodeCommand(self.gcode, "BED_MESH_CALIBRATE", cmdline,
                                  params, True)

        # Trigger probing.
        self.run_mesh(mesh, _cmd)


def load_config(config):
    return AdaptiveBedMesh(config)
