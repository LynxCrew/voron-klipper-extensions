# voron-klipper-extensions
A set of Klipper extensions designed to improve operation of Voron printers.

## Available Extensions
| Extension | Description |
| :-- | :-- |
| [adaptive_bed_mesh](./adaptive_bed_mesh/) | This module enables adaptive bed mesh - bed mesh only the part of the bed that is being used. |
| [gcode_shell_command](./gcode_shell_command/) | A modified `gcode_shell_command.py` module that allows GCode execution based on command status. |
| [led_interpolate](./led_interpolate/) | Small module that generates smooth LED color transitions. |
| [settling_probe](./settling_probe/) | Module that modifies the probing method to (optionally) perform a single "settling" probe. |
| [state_notify](./state_notify/) | An enhanced printer state reporting. |

## Installation
1. Login to your RaspberryPi using an SSH client like PuTTY.
2. Clone this repository:
   ```sh
   git clone https://github.com/voidtrance/voron-klipper-extensions.git
   ```
3. Change directory to the new cloned repository:
   ```sh
   cd voron-klipper-extensions
   ```
4. Run the install script:
   ```sh
   ./install-extensions.sh
   ```
5. Add the following section to `moonraker.conf`:
   ```ini
   [update_manager voron-klipper-extensions]
   type: git_repo
   path: ~/voron-klipper-extensions
   origin: https://github.com/voidtrance/voron-klipper-extensions.git
   install_script: install-extensions.sh
   managed_services: klipper
   ```
## Contributing
If you'd like to contribute, please submit a pull request with your suggested
changes. When submitting changes, please follow the [coding style](coding-style.md).
