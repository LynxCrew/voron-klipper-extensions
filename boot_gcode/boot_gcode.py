import logging


GCODE_MUTEX_DELAY = 0.2


class BootGcode:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode_macro = self.printer.load_object(config, "gcode_macro")
        self.boot_gcode = self.gcode_macro.load_template(config, "gcode", "")
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

    def _handle_ready(self):
        self._run_template()

    def _run_template(self):
        if not self.gcode.get_mutex().test():
            return self._run_gcode()
        self.delayed_gcode_timer = self.reactor.register_timer(
            lambda e: self._delayed_gcode_handler(e),
            self.reactor.monotonic() + GCODE_MUTEX_DELAY,
        )
        return None

    def _run_gcode(self):
        try:
            script = self.boot_gcode.render()
            res = self.gcode.run_script(script)
        except Exception as err:
            logging.exception("boot_gcode: gcode error: %s" % (str(err)))
            res = None
        return res

    def _delayed_gcode_handler(self, eventtime):
        if self.gcode.get_mutex().test():
            return eventtime + GCODE_MUTEX_DELAY
        self._run_gcode()
        self.reactor.unregister_timer(self.delayed_gcode_timer)
        return self.reactor.NEVER


def load_config(config):
    return BootGcode(config)
